from __future__ import annotations

import logging
import threading
import time
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import json

from backend.core.history import record_snapshot_from_briefing
from backend.core.ingestion_worker import WorkerJob, run_worker_job
from backend.core.database import DEFAULT_KEEP_FULL_BRIEFINGS_RECENT

logger = logging.getLogger(__name__)

IngestionStage = Literal[
    "idle",
    "waiting_for_stable_save",
    "parsing_t0",
    "parsing_t1",
    "precomputing_t2",
    "persisting",
    "ready",
    "error",
]


@dataclass
class IngestionStatus:
    stage: IngestionStage = "idle"
    stage_detail: str | None = None
    updated_at: float = field(default_factory=time.time)

    save_loaded: bool = False
    current_save_path: str | None = None
    current_save_mtime: float | None = None

    pending_save_path: str | None = None
    pending_requested_at: float | None = None

    last_error: str | None = None

    t0_meta: dict[str, Any] = field(default_factory=dict)
    t1_status: dict[str, Any] | None = None
    t2_ready: bool = False
    t2_meta: dict[str, Any] = field(default_factory=dict)
    t2_game_date: str | None = None
    t2_updated_at: float | None = None
    t2_last_duration_ms: float | None = None
    t2_last_save_hash: str | None = None

    cancel_count: int = 0
    worker_pid: int | None = None
    worker_tier: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class IngestionManager:
    """Coordinates save ingestion with latest-only scheduling and process cancellation.

    Tier 0: cheap metadata from save zip (meta only).
    Tier 1: status snapshot (runs in a worker process).
    Tier 2: full complete briefing + history/event enrichment (runs in a worker process).
            Tier 2 is scheduled only when the save stream is idle or on-demand (first chat).
    """

    def __init__(
        self,
        *,
        companion: Any,
        db: Any,
        stable_window_seconds: float = 0.6,
        stable_max_wait_seconds: float = 10.0,
        t2_idle_delay_seconds: float = 12.0,
    ) -> None:
        self._companion = companion
        self._db = db

        self._stable_window_seconds = max(0.2, float(stable_window_seconds))
        self._stable_max_wait_seconds = max(2.0, float(stable_max_wait_seconds))
        self._t2_idle_delay_seconds = max(3.0, float(t2_idle_delay_seconds))

        self._lock = threading.RLock()
        self._wakeup = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="ingestion-manager")
        self._started = False

        self._request_id = 0
        self._force_t2 = False
        self._last_save_event_at: float | None = None

        self._active_worker: threading.Thread | None = None
        self._active_worker_job: WorkerJob | None = None
        self._active_worker_cancel: threading.Event | None = None

        self._status = IngestionStatus()

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
            self._thread.start()

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            payload = self._status.to_dict()
        db = self._db
        if db is not None:
            try:
                payload["db"] = db.get_db_stats()
                payload["db"]["keep_full_briefings_recent"] = DEFAULT_KEEP_FULL_BRIEFINGS_RECENT
                payload["db"]["keep_full_briefings_first"] = True
            except Exception:
                payload["db"] = {"keep_full_briefings_recent": DEFAULT_KEEP_FULL_BRIEFINGS_RECENT, "keep_full_briefings_first": True}
        return payload

    def get_health_payload(self) -> dict[str, Any]:
        with self._lock:
            meta = dict(self._status.t2_meta or {}) if self._status.t2_ready else dict(self._status.t0_meta or {})
            empire_name = meta.get("empire_name") or meta.get("name")
            game_date = meta.get("date") or self._status.t2_game_date
            payload = {
                "save_loaded": bool(self._status.save_loaded),
                "empire_name": empire_name,
                "game_date": game_date,
                "precompute_ready": bool(self._status.t2_ready),
                "ingestion": {
                    "stage": self._status.stage,
                    "stage_detail": self._status.stage_detail,
                    "updated_at": self._status.updated_at,
                    "last_error": self._status.last_error,
                    "current_save_path": self._status.current_save_path,
                    "pending_save_path": self._status.pending_save_path,
                    "worker_pid": self._status.worker_pid,
                    "worker_tier": self._status.worker_tier,
                    "t2_game_date": self._status.t2_game_date,
                    "t2_updated_at": self._status.t2_updated_at,
                    "t2_last_duration_ms": self._status.t2_last_duration_ms,
                    "cancel_count": self._status.cancel_count,
                },
            }
        db = self._db
        if db is not None:
            try:
                payload["ingestion"]["db"] = db.get_db_stats()
            except Exception:
                pass
        return payload

    def get_latest_t1_status(self) -> dict[str, Any] | None:
        with self._lock:
            return dict(self._status.t1_status) if isinstance(self._status.t1_status, dict) else None

    def notify_save(self, save_path: Path) -> None:
        path = Path(save_path)
        with self._lock:
            self._request_id += 1
            self._last_save_event_at = time.time()
            self._status.pending_save_path = str(path)
            self._status.pending_requested_at = self._last_save_event_at
            self._status.stage = "waiting_for_stable_save"
            self._status.stage_detail = "save event received"
            self._status.updated_at = time.time()
            self._status.last_error = None
            self._status.t2_ready = False
            self._status.t2_meta = {}
            self._status.t2_game_date = None
            self._status.t2_updated_at = None
            self._force_t2 = False
            self._cancel_active_worker_locked()
            try:
                self._companion.mark_precompute_stale()
            except Exception:
                pass
            self._wakeup.set()

    def request_t2_on_demand(self) -> None:
        with self._lock:
            self._force_t2 = True
            self._wakeup.set()

    # --- internals ---

    def _set_stage_locked(self, stage: IngestionStage, detail: str | None = None) -> None:
        self._status.stage = stage
        self._status.stage_detail = detail
        self._status.updated_at = time.time()

    def _cancel_active_worker_locked(self) -> None:
        if self._active_worker_cancel is not None:
            self._active_worker_cancel.set()
        self._active_worker_cancel = None
        self._active_worker = None
        self._active_worker_job = None

    def _read_meta_only(self, save_path: Path) -> dict[str, Any]:
        with zipfile.ZipFile(save_path, "r") as z:
            meta_text = z.read("meta").decode("utf-8", errors="replace")
        parsed: dict[str, Any] = {
            "file_path": str(save_path),
            "file_size_mb": save_path.stat().st_size / (1024 * 1024),
            "modified": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(save_path.stat().st_mtime)),
        }
        for line in meta_text.split("\n"):
            if "=" in line and "flag" not in line.lower():
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"')
                if key in {"version", "name", "date"}:
                    parsed[key] = value
        return parsed

    def _wait_for_stable_save(self, save_path: Path, request_id: int) -> bool:
        """Wait until save file is stable and readable as a zip/meta."""
        stable_for = 0.0
        last_mtime = None
        last_size = None
        started = time.time()

        while time.time() - started < self._stable_max_wait_seconds:
            with self._lock:
                if request_id != self._request_id:
                    return False

            try:
                stat = save_path.stat()
            except FileNotFoundError:
                stable_for = 0.0
                time.sleep(0.2)
                continue

            if last_mtime is None:
                last_mtime = stat.st_mtime
                last_size = stat.st_size
                stable_for = 0.0
                time.sleep(0.2)
                continue

            if stat.st_mtime == last_mtime and stat.st_size == last_size:
                stable_for += 0.2
            else:
                stable_for = 0.0
                last_mtime = stat.st_mtime
                last_size = stat.st_size

            if stable_for >= self._stable_window_seconds:
                try:
                    self._read_meta_only(save_path)
                    return True
                except (zipfile.BadZipFile, KeyError):
                    stable_for = 0.0
                    time.sleep(0.25)
                    continue
                except Exception:
                    stable_for = 0.0
                    time.sleep(0.25)
                    continue

            time.sleep(0.2)

        return False

    def _run(self) -> None:
        while True:
            self._wakeup.wait(timeout=0.5)
            self._wakeup.clear()

            with self._lock:
                request_id = self._request_id
                pending = self._status.pending_save_path
                force_t2 = self._force_t2

            if not pending:
                with self._lock:
                    if self._status.stage != "ready":
                        self._set_stage_locked("idle")
                continue

            save_path = Path(pending)

            with self._lock:
                self._set_stage_locked("waiting_for_stable_save", "waiting for file stability")

            if not self._wait_for_stable_save(save_path, request_id=request_id):
                continue

            with self._lock:
                if request_id != self._request_id:
                    continue
                self._set_stage_locked("parsing_t0", "reading meta")

            try:
                meta = self._read_meta_only(save_path)
                mtime = save_path.stat().st_mtime
            except Exception as e:
                with self._lock:
                    self._status.last_error = f"Tier 0 failed: {e}"
                    self._set_stage_locked("error", "tier 0 failed")
                continue

            with self._lock:
                if request_id != self._request_id:
                    continue
                self._status.save_loaded = True
                self._status.current_save_path = str(save_path)
                self._status.current_save_mtime = mtime
                self._status.t0_meta = meta
                self._status.pending_save_path = None
                self._status.pending_requested_at = None
            self._status.t1_status = None
            self._status.t2_ready = False
            self._status.t2_meta = {}
            self._set_stage_locked("parsing_t1", "computing status snapshot")

            # Tier 1 worker (cancelable)
            t1 = self._run_worker_tier("t1", save_path=save_path, request_id=request_id)
            if t1 is None:
                continue

            with self._lock:
                if request_id != self._request_id:
                    continue
                self._status.t1_status = t1
                # Ready for UI status, but Tier 2 is still pending.
                self._status.stage_detail = "status snapshot ready"
                self._status.updated_at = time.time()

            # Tier 2 scheduling: idle-only unless forced by chat.
            if not force_t2:
                while True:
                    with self._lock:
                        if request_id != self._request_id:
                            break
                        last_event = self._last_save_event_at
                        if self._force_t2:
                            break
                    if last_event and time.time() - last_event >= self._t2_idle_delay_seconds:
                        break
                    time.sleep(0.25)

            with self._lock:
                if request_id != self._request_id:
                    continue
                self._force_t2 = False
                self._set_stage_locked("precomputing_t2", "building complete briefing")

            t2 = self._run_worker_tier("t2", save_path=save_path, request_id=request_id)
            if t2 is None:
                continue

            briefing_json = t2.get("briefing_json")
            t2_meta = t2.get("meta")
            identity = t2.get("identity")
            situation = t2.get("situation")
            save_hash = t2.get("save_hash")
            game_date = t2.get("game_date")
            duration_ms = t2.get("duration_ms")

            if not isinstance(briefing_json, str) or not briefing_json:
                with self._lock:
                    self._status.last_error = "Tier 2 returned empty briefing"
                    self._set_stage_locked("error", "tier 2 failed")
                continue

            with self._lock:
                if request_id != self._request_id:
                    continue
                self._set_stage_locked("persisting", "saving snapshot and activating cache")

            # Persist + activate cache (main process only).
            try:
                parsed = json.loads(briefing_json)
                if isinstance(parsed, dict):
                    record_snapshot_from_briefing(
                        db=self._db,
                        save_path=save_path,
                        save_hash=save_hash if isinstance(save_hash, str) else None,
                        briefing=parsed,
                    )
            except Exception as e:
                logger.warning("snapshot_persist_failed error=%s", e)

            try:
                self._companion.apply_precomputed_briefing(
                    save_path=save_path,
                    briefing_json=briefing_json,
                    game_date=str(game_date) if game_date is not None else None,
                    identity=identity if isinstance(identity, dict) else None,
                    situation=situation if isinstance(situation, dict) else None,
                    save_hash=save_hash if isinstance(save_hash, str) else None,
                )
            except Exception as e:
                with self._lock:
                    self._status.last_error = f"Failed to activate cache: {e}"
                    self._set_stage_locked("error", "activation failed")
                continue

            with self._lock:
                if request_id != self._request_id:
                    continue
                self._status.t2_ready = True
                self._status.t2_meta = dict(t2_meta) if isinstance(t2_meta, dict) else {}
                self._status.t2_game_date = str(game_date) if game_date is not None else None
                self._status.t2_updated_at = time.time()
                self._status.t2_last_duration_ms = float(duration_ms) if duration_ms is not None else None
                self._status.t2_last_save_hash = save_hash if isinstance(save_hash, str) else None
                self._status.last_error = None
                self._set_stage_locked("ready", "complete briefing ready")

    def _run_worker_tier(self, tier: Literal["t1", "t2"], *, save_path: Path, request_id: int) -> dict[str, Any] | None:
        cancel_event = threading.Event()
        job: WorkerJob = {
            "tier": tier,
            "save_path": str(save_path),
            "requested_at": time.time(),
        }
        with self._lock:
            self._active_worker_job = job
            self._active_worker_cancel = cancel_event
            self._status.worker_tier = tier
            self._status.worker_pid = None

        result: dict[str, Any]
        try:
            result = run_worker_job(job=job, cancel_event=cancel_event)
        except Exception as e:
            result = {"ok": False, "error": str(e)}

        with self._lock:
            self._cancel_active_worker_locked()
            self._status.worker_pid = None
            self._status.worker_tier = None

        if request_id != self._request_id:
            return None

        if result.get("error") == "cancelled":
            with self._lock:
                self._status.cancel_count += 1
            return None

        if not result.get("ok"):
            err = result.get("error") or "unknown error"
            with self._lock:
                self._status.last_error = f"{tier} failed: {err}"
                self._set_stage_locked("error", f"{tier} failed")
            return None
        if isinstance(result.get("worker_pid"), int):
            with self._lock:
                self._status.worker_pid = int(result["worker_pid"])
                self._status.worker_tier = tier

        payload = result.get("payload") if isinstance(result.get("payload"), dict) else None
        return payload or {}
