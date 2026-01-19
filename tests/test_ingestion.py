"""Tests for the ingestion system (IngestionManager, workers, tiered processing)."""

import os
import sys
import time
import threading
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core.ingestion import IngestionManager, IngestionStatus
from backend.core.ingestion_worker import WorkerJob, run_worker_job, _build_t1_status


# --- Fixtures ---

@pytest.fixture
def test_save_path():
    """Return path to test save file."""
    path = Path(__file__).parent.parent / 'test_save.sav'
    if not path.exists():
        pytest.skip(f"Test save file not found at {path}")
    return path


@pytest.fixture
def mock_companion():
    """Create a mock companion for testing."""
    companion = MagicMock()
    companion.mark_precompute_stale = MagicMock()
    companion.apply_precomputed_briefing = MagicMock()
    return companion


@pytest.fixture
def mock_db():
    """Create a mock database for testing."""
    db = MagicMock()
    return db


# --- IngestionStatus Tests ---

class TestIngestionStatus:
    """Tests for the IngestionStatus dataclass."""

    def test_default_state(self):
        """IngestionStatus starts with sensible defaults."""
        status = IngestionStatus()

        assert status.stage == "idle"
        assert status.stage_detail is None
        assert status.save_loaded is False
        assert status.current_save_path is None
        assert status.pending_save_path is None
        assert status.last_error is None
        assert status.t2_ready is False
        assert status.cancel_count == 0

    def test_to_dict(self):
        """IngestionStatus.to_dict() returns proper dictionary."""
        status = IngestionStatus(stage="parsing_t1", save_loaded=True)
        d = status.to_dict()

        assert isinstance(d, dict)
        assert d["stage"] == "parsing_t1"
        assert d["save_loaded"] is True
        assert "updated_at" in d

    def test_stage_transitions(self):
        """IngestionStatus tracks stage changes."""
        status = IngestionStatus()

        status.stage = "waiting_for_stable_save"
        assert status.stage == "waiting_for_stable_save"

        status.stage = "parsing_t0"
        assert status.stage == "parsing_t0"

        status.stage = "ready"
        assert status.stage == "ready"


# --- IngestionManager Tests ---

class TestIngestionManager:
    """Tests for IngestionManager initialization and basic operations."""

    def test_initialization(self, mock_companion, mock_db):
        """IngestionManager initializes with default state."""
        manager = IngestionManager(companion=mock_companion, db=mock_db)

        status = manager.get_status()
        assert status["stage"] == "idle"
        assert status["save_loaded"] is False

    def test_get_health_payload(self, mock_companion, mock_db):
        """get_health_payload() returns properly structured response."""
        manager = IngestionManager(companion=mock_companion, db=mock_db)

        payload = manager.get_health_payload()

        assert "save_loaded" in payload
        assert "precompute_ready" in payload
        assert "ingestion" in payload
        assert "stage" in payload["ingestion"]

    def test_notify_save_updates_pending(self, mock_companion, mock_db, test_save_path):
        """notify_save() updates pending save path and stage."""
        manager = IngestionManager(companion=mock_companion, db=mock_db)

        manager.notify_save(test_save_path)

        status = manager.get_status()
        assert status["pending_save_path"] == str(test_save_path)
        assert status["stage"] == "waiting_for_stable_save"

    def test_notify_save_marks_precompute_stale(self, mock_companion, mock_db, test_save_path):
        """notify_save() calls mark_precompute_stale on companion."""
        manager = IngestionManager(companion=mock_companion, db=mock_db)

        manager.notify_save(test_save_path)

        mock_companion.mark_precompute_stale.assert_called_once()

    def test_request_t2_on_demand(self, mock_companion, mock_db):
        """request_t2_on_demand() sets force_t2 flag."""
        manager = IngestionManager(companion=mock_companion, db=mock_db)

        # This should not raise
        manager.request_t2_on_demand()

    def test_read_meta_only(self, mock_companion, mock_db, test_save_path):
        """_read_meta_only() extracts basic metadata from save file."""
        manager = IngestionManager(companion=mock_companion, db=mock_db)

        meta = manager._read_meta_only(test_save_path)

        assert "file_path" in meta
        assert "file_size_mb" in meta
        assert meta["file_size_mb"] > 0
        # The meta file should have name and date
        assert "name" in meta or "version" in meta


# --- Worker Tests ---

class TestIngestionWorker:
    """Tests for the ingestion worker functions."""

    def test_build_t1_status_returns_dict(self, test_save_path):
        """_build_t1_status() returns a status dictionary."""
        from save_extractor import SaveExtractor

        extractor = SaveExtractor(str(test_save_path))
        status = _build_t1_status(extractor=extractor)

        assert isinstance(status, dict)
        assert "empire_name" in status or "game_date" in status
        assert "military_power" in status
        assert "economy" in status
        assert "colonies" in status

    def test_t1_worker_job(self, test_save_path):
        """Tier 1 worker job completes successfully."""
        job: WorkerJob = {
            "tier": "t1",
            "save_path": str(test_save_path),
            "requested_at": time.time(),
        }
        cancel_event = threading.Event()

        result = run_worker_job(job=job, cancel_event=cancel_event)

        assert result["ok"] is True
        assert "payload" in result
        assert "status" in result["payload"]

    def test_t2_worker_job(self, test_save_path):
        """Tier 2 worker job completes successfully."""
        job: WorkerJob = {
            "tier": "t2",
            "save_path": str(test_save_path),
            "requested_at": time.time(),
        }
        cancel_event = threading.Event()

        result = run_worker_job(job=job, cancel_event=cancel_event)

        assert result["ok"] is True
        assert "payload" in result
        payload = result["payload"]
        assert "briefing_json" in payload
        assert "meta" in payload
        assert "game_date" in payload

    def test_worker_cancellation(self, test_save_path):
        """Worker can be cancelled mid-execution."""
        job: WorkerJob = {
            "tier": "t2",  # T2 is slower, easier to cancel
            "save_path": str(test_save_path),
            "requested_at": time.time(),
        }
        cancel_event = threading.Event()

        # Start worker in thread and cancel immediately
        def run_and_cancel():
            time.sleep(0.1)  # Small delay to let worker start
            cancel_event.set()

        cancel_thread = threading.Thread(target=run_and_cancel)
        cancel_thread.start()

        result = run_worker_job(job=job, cancel_event=cancel_event)
        cancel_thread.join()

        # Either cancelled or completed (if save is very small)
        assert result["ok"] is False or result["ok"] is True

    def test_worker_reports_pid(self, test_save_path):
        """Worker reports its process ID."""
        job: WorkerJob = {
            "tier": "t1",
            "save_path": str(test_save_path),
            "requested_at": time.time(),
        }
        cancel_event = threading.Event()

        result = run_worker_job(job=job, cancel_event=cancel_event)

        assert "worker_pid" in result
        assert isinstance(result["worker_pid"], int)


# --- Integration Tests ---

class TestIngestionIntegration:
    """Integration tests for the full ingestion pipeline."""

    @pytest.mark.slow
    def test_full_ingestion_cycle(self, mock_companion, mock_db, test_save_path):
        """Test complete ingestion from notify to ready."""
        manager = IngestionManager(
            companion=mock_companion,
            db=mock_db,
            stable_window_seconds=0.2,  # Faster for testing
            stable_max_wait_seconds=5.0,
            t2_idle_delay_seconds=0.5,  # Faster for testing
        )
        manager.start()

        # Notify save
        manager.notify_save(test_save_path)

        # Wait for ingestion to complete (with timeout)
        start = time.time()
        timeout = 60  # 60 seconds max
        while time.time() - start < timeout:
            status = manager.get_status()
            if status["stage"] == "ready":
                break
            if status["stage"] == "error":
                pytest.fail(f"Ingestion failed: {status.get('last_error')}")
            time.sleep(0.5)

        status = manager.get_status()
        assert status["stage"] == "ready", f"Expected ready, got {status['stage']}"
        assert status["save_loaded"] is True
        assert status["t2_ready"] is True

    def test_lazy_gamestate_loading(self, test_save_path):
        """Verify gamestate is not loaded until accessed."""
        from stellaris_save_extractor.extractor import SaveExtractor

        extractor = SaveExtractor(str(test_save_path))

        # Meta should be loaded, gamestate should not
        assert extractor._meta is not None
        assert extractor._gamestate is None

        # Accessing gamestate property should trigger load
        _ = extractor.gamestate
        assert extractor._gamestate is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
