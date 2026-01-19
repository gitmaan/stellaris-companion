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
    started = time.time()
    try:
        tier = job["tier"]
        save_path = job["save_path"]

        extractor = SaveExtractor(str(save_path))

        if tier == "t1":
            payload = {"status": _build_t1_status(extractor=extractor)}
            out_q.put({"ok": True, "payload": payload, "worker_pid": os.getpid()})
            return

        if tier == "t2":
            briefing = extractor.get_complete_briefing()

            # Add history/event enrichment for DB + recap/event detection.
            try:
                from backend.core.history import build_history_enrichment

                history = build_history_enrichment(
                    gamestate=getattr(extractor, "gamestate", None),
                    player_id=briefing.get("meta", {}).get("player_id") if isinstance(briefing, dict) else None,
                )
                if history:
                    briefing = dict(briefing)
                    briefing["history"] = history
            except Exception:
                pass

            briefing_json = json.dumps(briefing, ensure_ascii=False, separators=(",", ":"), default=str)
            meta = briefing.get("meta", {}) if isinstance(briefing, dict) else {}

            payload = {
                "briefing_json": briefing_json,
                "meta": meta if isinstance(meta, dict) else {},
                "identity": briefing.get("identity") if isinstance(briefing, dict) else None,
                "situation": briefing.get("situation") if isinstance(briefing, dict) else None,
                "save_hash": _compute_save_hash_from_briefing(briefing) if isinstance(briefing, dict) else None,
                "game_date": meta.get("date") if isinstance(meta, dict) else None,
                "duration_ms": (time.time() - started) * 1000,
            }
            out_q.put({"ok": True, "payload": payload, "worker_pid": os.getpid()})
            return

        out_q.put({"ok": False, "error": f"Unknown tier: {tier}", "worker_pid": os.getpid()})
    except Exception as e:
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
