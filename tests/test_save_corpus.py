"""Save corpus regression tests for Stellaris save extraction.

Tests that verify:
1. No crashes when processing saves
2. Reasonable output (non-empty, expected fields present)
3. Consistent results between Rust and regex extraction modes

Currently uses test_save.sav as baseline. Add more saves to SAVE_CORPUS dict as they become available.
"""

import os
import sys
import time
from pathlib import Path

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stellaris_save_extractor import SaveExtractor

# Try to import Rust bridge for mode comparison tests
try:
    from stellaris_companion.rust_bridge import session as rust_session

    RUST_BRIDGE_AVAILABLE = True
except ImportError:
    RUST_BRIDGE_AVAILABLE = False
    rust_session = None


# --- Save Corpus Configuration ---

SAVE_CORPUS = {
    "test_save.sav": {
        "description": "Base test save - mid-to-late game organic empire",
        "type": "base_game",
        "stage": "late",
        "empire_type": "organic",
        "required": True,
    },
}


# --- Fixtures ---


@pytest.fixture(scope="module")
def project_root():
    """Return the project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture(scope="module")
def test_save_path(project_root):
    """Return path to test_save.sav, skip if not found."""
    path = project_root / "test_save.sav"
    if not path.exists():
        pytest.skip(f"Test save file not found at {path}")
    return path


@pytest.fixture(scope="module")
def extractor(test_save_path):
    """Create a SaveExtractor with Rust session (module-scoped for performance)."""
    if not RUST_BRIDGE_AVAILABLE:
        pytest.skip("Rust bridge not available")
        return

    with rust_session(test_save_path):
        extractor = SaveExtractor(str(test_save_path))
        yield extractor


# --- Basic Functionality Tests ---


class TestSaveCorpusBasics:
    """Basic tests that verify extraction doesn't crash and returns valid data."""

    def test_metadata_extraction(self, extractor):
        """Metadata extraction returns expected fields."""
        meta = extractor.get_metadata()

        assert isinstance(meta, dict)
        assert "date" in meta
        assert "version" in meta

    def test_complete_briefing_no_crash(self, extractor):
        """Complete briefing extraction doesn't crash."""
        briefing = extractor.get_complete_briefing()

        assert isinstance(briefing, dict)
        assert len(briefing) > 0


# --- Rust vs Regex Mode Comparison Tests ---


@pytest.mark.skipif(not RUST_BRIDGE_AVAILABLE, reason="Rust bridge not available")
class TestRustRegexConsistency:
    """Tests that verify Rust and regex modes produce consistent results."""

    def test_metadata_consistency(self, test_save_path):
        """Metadata extraction is consistent between Rust and regex modes."""
        # Regex mode
        extractor_regex = SaveExtractor(str(test_save_path))
        meta_regex = extractor_regex.get_metadata()

        # Rust session mode
        with rust_session(test_save_path) as _:
            extractor_rust = SaveExtractor(str(test_save_path))
            meta_rust = extractor_rust.get_metadata()

        # Core fields should match
        assert meta_regex.get("date") == meta_rust.get("date")
        assert meta_regex.get("version") == meta_rust.get("version")

    def test_player_id_consistency(self, test_save_path):
        """Player empire ID is consistent between modes."""
        # Regex mode
        extractor_regex = SaveExtractor(str(test_save_path))
        player_id_regex = extractor_regex.get_player_empire_id()

        # Rust session mode
        with rust_session(test_save_path) as _:
            extractor_rust = SaveExtractor(str(test_save_path))
            player_id_rust = extractor_rust.get_player_empire_id()

        assert player_id_regex == player_id_rust

    def test_leaders_count_consistency(self, test_save_path):
        """Leaders count is consistent between modes."""
        # Regex mode
        extractor_regex = SaveExtractor(str(test_save_path))
        leaders_regex = extractor_regex.get_leaders()
        count_regex = len(leaders_regex.get("leaders", []))

        # Rust session mode
        with rust_session(test_save_path) as _:
            extractor_rust = SaveExtractor(str(test_save_path))
            leaders_rust = extractor_rust.get_leaders()
            count_rust = len(leaders_rust.get("leaders", []))

        # Counts should match exactly
        assert count_regex == count_rust, (
            f"Leader count mismatch: regex={count_regex}, rust={count_rust}"
        )

    def test_diplomacy_relations_count_consistency(self, test_save_path):
        """Diplomacy relations count is consistent between modes."""
        # Regex mode
        extractor_regex = SaveExtractor(str(test_save_path))
        diplo_regex = extractor_regex.get_diplomacy()
        count_regex = len(diplo_regex.get("relations", []))

        # Rust session mode
        with rust_session(test_save_path) as _:
            extractor_rust = SaveExtractor(str(test_save_path))
            diplo_rust = extractor_rust.get_diplomacy()
            count_rust = len(diplo_rust.get("relations", []))

        # Counts should match (Rust may be more accurate due to no truncation)
        # Allow Rust to have >= regex count (Rust doesn't truncate)
        assert count_rust >= count_regex, (
            f"Rust found fewer relations than regex: {count_rust} < {count_regex}"
        )

    def test_complete_briefing_fields_consistency(self, test_save_path):
        """Complete briefing has same top-level fields in both modes."""
        # Regex mode
        extractor_regex = SaveExtractor(str(test_save_path))
        briefing_regex = extractor_regex.get_complete_briefing()

        # Rust session mode
        with rust_session(test_save_path) as _:
            extractor_rust = SaveExtractor(str(test_save_path))
            briefing_rust = extractor_rust.get_complete_briefing()

        # Same top-level keys
        keys_regex = set(briefing_regex.keys())
        keys_rust = set(briefing_rust.keys())

        assert keys_regex == keys_rust, (
            f"Key mismatch: only in regex={keys_regex - keys_rust}, only in rust={keys_rust - keys_regex}"
        )


# --- Performance Regression Tests ---


@pytest.mark.slow
class TestPerformance:
    """Performance regression tests."""

    def test_complete_briefing_time(self, test_save_path):
        """Complete briefing completes in reasonable time."""
        extractor = SaveExtractor(str(test_save_path))

        start = time.time()
        briefing = extractor.get_complete_briefing()
        elapsed = time.time() - start

        assert briefing is not None
        # Without Rust session, regex-only should complete within 30s for most saves
        # This is a conservative limit - actual time depends on save size
        assert elapsed < 30, f"Briefing took too long: {elapsed:.1f}s"

    @pytest.mark.skipif(not RUST_BRIDGE_AVAILABLE, reason="Rust bridge not available")
    def test_rust_session_briefing_time(self, test_save_path):
        """Complete briefing with Rust session completes much faster."""
        with rust_session(test_save_path) as _:
            extractor = SaveExtractor(str(test_save_path))

            # Warm up (first call may be slower due to parsing)
            extractor.get_complete_briefing()

            # Measure subsequent calls
            times = []
            for _ in range(3):
                start = time.time()
                briefing = extractor.get_complete_briefing()
                times.append(time.time() - start)

            avg_time = sum(times) / len(times)

            assert briefing is not None
            # Rust session should be much faster - target is <3s average
            # This is a generous limit to account for CI variance
            assert avg_time < 5, f"Rust briefing too slow: {avg_time:.2f}s avg"


# --- Data Quality Tests ---


class TestDataQuality:
    """Tests that verify extracted data quality."""

    def test_no_none_in_critical_fields(self, extractor):
        """Critical fields don't have unexpected None values."""
        meta = extractor.get_metadata()

        # Date should always be present
        assert meta.get("date") is not None
        # Version should always be present
        assert meta.get("version") is not None

    def test_player_status_has_name(self, extractor):
        """Player status includes empire name."""
        player = extractor.get_player_status()

        # Should have some form of name
        has_name = (
            player.get("empire_name") is not None
            or player.get("name") is not None
            or player.get("adjective") is not None
        )
        assert has_name, "Player status missing name fields"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
