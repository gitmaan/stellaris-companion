from __future__ import annotations

import hashlib
import json
import multiprocessing as mp
import os
import time
from typing import Any, Literal, TypedDict

from save_extractor import SaveExtractor


class WorkerJob(TypedDict):
    tier: Literal["t1", "t2"]
    save_path: str
    requested_at: float


class WorkerResult(TypedDict, total=False):
    ok: bool
    error: str
    payload: dict[str, Any]
    worker_pid: int


def _compute_save_hash_from_briefing(briefing: dict[str, Any]) -> str | None:
    meta = briefing.get("meta", {}) if isinstance(briefing, dict) else {}
    military = briefing.get("military", {}) if isinstance(briefing, dict) else {}
    date = meta.get("date")
    empire_name = meta.get("empire_name") or meta.get("name")
    mil = military.get("military_power")
    if date is None and empire_name is None and mil is None:
        return None
    key_data = f"{date}|{mil}|{empire_name}"
    return hashlib.md5(key_data.encode("utf-8", errors="replace")).hexdigest()[:8]


def _build_t1_status(*, extractor: SaveExtractor) -> dict[str, Any]:
    status_data = {
        "empire_name": extractor.get_metadata().get("name") or extractor.get_player_status().get("empire_name"),
        "game_date": extractor.get_metadata().get("date") or extractor.get_player_status().get("date"),
    }

    player = extractor.get_player_status()
    resources = extractor.get_resources()
    wars_data = extractor.get_wars()

    net = resources.get("net_monthly", {}) if isinstance(resources.get("net_monthly", {}), dict) else {}
    colonies_data = player.get("colonies", {}) if isinstance(player.get("colonies", {}), dict) else {}

    status_data.update(
        {
            "military_power": player.get("military_power", 0),
            "economy": {
                "energy": net.get("energy", 0),
                "minerals": net.get("minerals", 0),
                "alloys": net.get("alloys", 0),
                "food": net.get("food", 0),
                "consumer_goods": net.get("consumer_goods", 0),
                "tech_power": player.get("tech_power", 0),
                "economy_power": player.get("economy_power", 0),
            },
            "colonies": colonies_data.get("total_count", 0),
            "pops": colonies_data.get("total_population", 0),
            "active_wars": [
                {
                    "name": war.get("name"),
                    "attackers": war.get("attackers", []),
                    "defenders": war.get("defenders", []),
                }
                for war in (wars_data.get("wars", []) if isinstance(wars_data, dict) else [])
            ],
        }
    )

    return status_data


def _process_main(job: WorkerJob, out_q: "mp.Queue[dict[str, Any]]") -> None:
    import sys

    def log_timing(label: str, elapsed: float) -> None:
        print(f"[TIMING] {label}: {elapsed*1000:.1f}ms", file=sys.stderr, flush=True)

    started = time.time()
    timings: dict[str, float] = {}

    try:
        tier = job["tier"]
        save_path = job["save_path"]

        # Use session mode to parse save once and reuse for all extractor calls
        t0 = time.time()
        from rust_bridge import session as rust_session
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

            if tier == "t1":
                t0 = time.time()
                payload = {"status": _build_t1_status(extractor=extractor)}
                timings["t1_build"] = time.time() - t0
                log_timing("T1 status build", timings["t1_build"])

                timings["total"] = time.time() - started
                log_timing("TOTAL (t1)", timings["total"])
                out_q.put({"ok": True, "payload": payload, "worker_pid": os.getpid()})
                return

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
                player_id = briefing.get("meta", {}).get("player_id") if isinstance(briefing, dict) else None
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
                print(f"[TIMING] History enrichment error: {e}", file=sys.stderr, flush=True)

            t0 = time.time()
            briefing_json = json.dumps(briefing, ensure_ascii=False, separators=(",", ":"), default=str)
            timings["json_serialize"] = time.time() - t0
            log_timing("JSON serialize", timings["json_serialize"])

            meta = briefing.get("meta", {}) if isinstance(briefing, dict) else {}

            payload = {
                "briefing_json": briefing_json,
                "meta": meta if isinstance(meta, dict) else {},
                "identity": briefing.get("identity") if isinstance(briefing, dict) else None,
                "situation": briefing.get("situation") if isinstance(briefing, dict) else None,
                "save_hash": _compute_save_hash_from_briefing(briefing) if isinstance(briefing, dict) else None,
                "game_date": meta.get("date") if isinstance(meta, dict) else None,
                "duration_ms": (time.time() - started) * 1000,
                "timings": timings,
            }

            timings["total"] = time.time() - started
            log_timing("TOTAL (t2)", timings["total"])

            # Print timing summary
            print(f"\n[TIMING SUMMARY]", file=sys.stderr, flush=True)
            for k, v in sorted(timings.items(), key=lambda x: -x[1]):
                print(f"  {k}: {v*1000:.1f}ms", file=sys.stderr, flush=True)
            print("", file=sys.stderr, flush=True)

            out_q.put({"ok": True, "payload": payload, "worker_pid": os.getpid()})
            return
        finally:
            t0 = time.time()
            ctx.__exit__(None, None, None)
            log_timing("Rust session close", time.time() - t0)

        out_q.put({"ok": False, "error": f"Unknown tier: {tier}", "worker_pid": os.getpid()})
    except Exception as e:
        import traceback
        print(f"[TIMING] Error: {e}\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        out_q.put({"ok": False, "error": str(e), "worker_pid": os.getpid()})


def run_worker_job(*, job: WorkerJob, cancel_event: Any) -> WorkerResult:
    """Run a worker job in a separate process, allowing hard cancellation.

    Cancellation is process-based (terminate/kill), so stale work stops consuming CPU/RAM.
    """
    ctx = mp.get_context("spawn")
    q: "mp.Queue[dict[str, Any]]" = ctx.Queue(maxsize=1)
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
                return {"ok": False, "error": "cancelled", "worker_pid": worker_pid or 0}

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
                return {"ok": False, "error": "worker exited without result", "worker_pid": worker_pid or 0}
    finally:
        try:
            if proc.is_alive():
                proc.terminate()
        except Exception:
            pass
        proc.join(timeout=0.1)
