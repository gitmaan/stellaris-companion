"""Tests for the ingestion system (IngestionManager, workers, tiered processing)."""

import os
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core.ingestion import IngestionManager
from backend.core.ingestion_worker import WorkerJob, run_worker_job

# --- Fixtures ---


@pytest.fixture
def test_save_path():
    """Return path to test save file."""
    path = Path(__file__).parent.parent / "test_save.sav"
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


# --- IngestionManager Tests ---


class TestIngestionManager:
    """Tests for IngestionManager initialization and basic operations."""

    def test_initialization(self, mock_companion, mock_db):
        """IngestionManager initializes with default state."""
        manager = IngestionManager(companion=mock_companion, db=mock_db)

        status = manager.get_status()
        assert status["stage"] == "idle"
        assert status["save_loaded"] is False

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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
