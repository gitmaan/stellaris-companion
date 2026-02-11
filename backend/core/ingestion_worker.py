from __future__ import annotations

import contextlib
import logging
import multiprocessing as mp
import os
import time
from typing import Any, Literal, TypedDict

from backend.core.json_utils import json_dumps
from backend.core.utils import compute_save_hash_from_briefing
from stellaris_save_extractor import SaveExtractor


class WorkerJob(TypedDict):
    tier: Literal["t2"]
    save_path: str
    requested_at: float


class WorkerResult(TypedDict, total=False):
    ok: bool
    error: str
    payload: dict[str, Any]
    worker_pid: int


def _process_main(job: WorkerJob, out_q: mp.Queue[dict[str, Any]]) -> None:
    # Configure logging for subprocess (parent's config doesn't propagate)
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(message)s")
    logger = logging.getLogger("stellaris.worker")

    def log_timing(label: str, elapsed: float) -> None:
        logger.debug("[TIMING] %s: %.1fms", label, elapsed * 1000)

    started = time.time()
    timings: dict[str, float] = {}

    try:
        tier = job["tier"]
        save_path = job["save_path"]

        # Use session mode to parse save once and reuse for all extractor calls
        t0 = time.time()
        from stellaris_companion.rust_bridge import session as rust_session

        timings["import_rust_bridge"] = time.time() - t0

        t0 = time.time()
        ctx = rust_session(save_path)
        ctx.__enter__()
        timings["rust_session_start"] = time.time() - t0
        log_timing("Rust session started", timings["rust_session_start"])

        try:
            t0 = time.time()
            extractor = SaveExtractor(str(save_path))
            timings["extractor_init"] = time.time() - t0
            log_timing("SaveExtractor init", timings["extractor_init"])

            if tier == "t2":
                t0 = time.time()
                briefing = extractor.get_complete_briefing()
                timings["briefing"] = time.time() - t0
                log_timing("get_complete_briefing", timings["briefing"])

            # Add history/event enrichment for DB + recap/event detection.
            try:
                t0 = time.time()
                from backend.core.history import build_history_enrichment
                from backend.core.signals import build_snapshot_signals

                # Build signals from Rust session (fast, resolved names)
                # Signals provides: leaders, wars, diplomacy - all with resolved names
                t_signals = time.time()
                signals = build_snapshot_signals(extractor=extractor, briefing=briefing)
                timings["signals_build"] = time.time() - t_signals
                log_timing("Signals build (Rust-backed)", timings["signals_build"])

                # Build history enrichment with precomputed signals
                # Signals-backed fields (leaders/wars/diplomacy) use resolved names
                # Remaining fields (galaxy/techs/policies/edicts/etc.) use gamestate if needed
                player_id = (
                    briefing.get("meta", {}).get("player_id")
                    if isinstance(briefing, dict)
                    else None
                )
                history = build_history_enrichment(
                    gamestate=None,  # Signals provide all critical data
                    player_id=player_id,
                    precomputed_signals=signals,
                )

                if history:
                    briefing = dict(briefing)
                    briefing["history"] = history
                timings["history_enrichment"] = time.time() - t0
                log_timing("History enrichment (total)", timings["history_enrichment"])
            except Exception as e:
                timings["history_enrichment"] = 0
                logger.warning("History enrichment error: %s", e)

            t0 = time.time()
            briefing_json = json_dumps(briefing, default=str)
            timings["json_serialize"] = time.time() - t0
            log_timing("JSON serialize", timings["json_serialize"])

            briefing_meta = briefing.get("meta", {}) if isinstance(briefing, dict) else {}
            extractor_meta = extractor.get_metadata() if isinstance(briefing, dict) else {}
            worker_meta: dict[str, Any] = {}
            if isinstance(extractor_meta, dict):
                worker_meta.update(extractor_meta)
            if isinstance(briefing_meta, dict):
                worker_meta.update(briefing_meta)

            with contextlib.suppress(Exception):
                missing_dlcs = extractor.get_missing_dlcs()
                if isinstance(missing_dlcs, list):
                    worker_meta["missing_dlcs"] = missing_dlcs

            payload = {
                "briefing_json": briefing_json,
                "meta": worker_meta,
                "identity": (briefing.get("identity") if isinstance(briefing, dict) else None),
                "situation": (briefing.get("situation") if isinstance(briefing, dict) else None),
                "save_hash": (
                    compute_save_hash_from_briefing(briefing)
                    if isinstance(briefing, dict)
                    else None
                ),
                "game_date": worker_meta.get("date"),
                "duration_ms": (time.time() - started) * 1000,
                "timings": timings,
            }

            timings["total"] = time.time() - started
            log_timing("TOTAL (t2)", timings["total"])

            # Log timing summary
            summary_lines = [
                f"  {k}: {v * 1000:.1f}ms" for k, v in sorted(timings.items(), key=lambda x: -x[1])
            ]
            logger.info("[TIMING SUMMARY]\n%s", "\n".join(summary_lines))

            out_q.put({"ok": True, "payload": payload, "worker_pid": os.getpid()})
            return
        finally:
            t0 = time.time()
            ctx.__exit__(None, None, None)
            log_timing("Rust session close", time.time() - t0)
    except Exception as e:
        logger.error("Worker error: %s", e, exc_info=True)
        out_q.put({"ok": False, "error": str(e), "worker_pid": os.getpid()})


def run_worker_job(*, job: WorkerJob, cancel_event: Any) -> WorkerResult:
    """Run a worker job in a separate process, allowing hard cancellation.

    Cancellation is process-based (terminate/kill), so stale work stops consuming CPU/RAM.
    """
    ctx = mp.get_context("spawn")
    q: mp.Queue[dict[str, Any]] = ctx.Queue(maxsize=1)
    proc = ctx.Process(target=_process_main, args=(job, q), daemon=True)
    proc.start()

    worker_pid = proc.pid or None

    try:
        while True:
            if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
                try:
                    if proc.is_alive():
                        proc.terminate()
                except Exception:
                    pass
                proc.join(timeout=0.5)
                try:
                    if proc.is_alive():
                        proc.kill()
                except Exception:
                    pass
                proc.join(timeout=0.5)
                return {
                    "ok": False,
                    "error": "cancelled",
                    "worker_pid": worker_pid or 0,
                }

            try:
                msg = q.get(timeout=0.1)
                if isinstance(msg, dict):
                    msg.setdefault("worker_pid", worker_pid or 0)
                    return msg  # type: ignore[return-value]
            except Exception:
                pass

            if not proc.is_alive():
                proc.join(timeout=0.1)
                # Attempt to pull a final message if it exited quickly.
                try:
                    msg = q.get_nowait()
                    if isinstance(msg, dict):
                        msg.setdefault("worker_pid", worker_pid or 0)
                        return msg  # type: ignore[return-value]
                except Exception:
                    pass
                return {
                    "ok": False,
                    "error": "worker exited without result",
                    "worker_pid": worker_pid or 0,
                }
    finally:
        try:
            if proc.is_alive():
                proc.terminate()
        except Exception:
            pass
        proc.join(timeout=0.1)
