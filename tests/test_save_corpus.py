"""Save corpus regression tests for Stellaris save extraction.

Tests that verify:
1. No crashes when processing saves
2. Reasonable output (non-empty, expected fields present)
3. Consistent results between Rust and regex extraction modes

Save types to support (as corpus expands):
- Base game (no DLC)
- Various DLC combinations
- Popular mods (Gigastructural Engineering, etc.)
- Early game (<2250), mid game (2250-2400), late game (>2400)
- Different empire types: organic, machine, hive mind

Currently uses test_save.sav as baseline. Add more saves to SAVE_CORPUS dict as they become available.
"""

import os
import sys
import time
from pathlib import Path

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from save_extractor import SaveExtractor

# Try to import Rust bridge for mode comparison tests
try:
    from rust_bridge import _get_active_session
    from rust_bridge import session as rust_session

    RUST_BRIDGE_AVAILABLE = True
except ImportError:
    RUST_BRIDGE_AVAILABLE = False
    rust_session = None
    _get_active_session = lambda: None


# --- Save Corpus Configuration ---

# Define available test saves and their characteristics
# Add new saves here as they become available
SAVE_CORPUS = {
    "test_save.sav": {
        "description": "Base test save - mid-to-late game organic empire",
        "type": "base_game",  # base_game, dlc, mod
        "stage": "late",  # early (<2250), mid (2250-2400), late (>2400)
        "empire_type": "organic",  # organic, machine, hive_mind
        "required": True,  # If True, skip all tests if missing
    },
    # Future saves to add:
    # 'early_game.sav': {'type': 'base_game', 'stage': 'early', 'empire_type': 'organic'},
    # 'machine_empire.sav': {'type': 'dlc', 'stage': 'mid', 'empire_type': 'machine'},
    # 'hive_mind.sav': {'type': 'dlc', 'stage': 'mid', 'empire_type': 'hive_mind'},
    # 'gigastructures_mod.sav': {'type': 'mod', 'stage': 'late', 'empire_type': 'organic'},
}


# --- Fixtures ---


@pytest.fixture(scope="module")
def project_root():
    """Return the project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture(scope="module")
def available_saves(project_root):
    """Return dict of available saves (those that exist on disk)."""
    available = {}
    for save_name, meta in SAVE_CORPUS.items():
        save_path = project_root / save_name
        if save_path.exists():
            available[save_name] = {**meta, "path": save_path}
    return available


@pytest.fixture(scope="module")
def test_save_path(project_root):
    """Return path to test_save.sav, skip if not found."""
    path = project_root / "test_save.sav"
    if not path.exists():
        pytest.skip(f"Test save file not found at {path}")
    return path


@pytest.fixture(scope="module")
def extractor(test_save_path):
    """Create a SaveExtractor instance (module-scoped for performance)."""
    return SaveExtractor(str(test_save_path))


# --- Helper Functions ---


def get_saves_by_type(available_saves: dict, save_type: str) -> list:
    """Get saves matching a specific type (base_game, dlc, mod)."""
    return [(name, meta) for name, meta in available_saves.items() if meta.get("type") == save_type]


def get_saves_by_stage(available_saves: dict, stage: str) -> list:
    """Get saves matching a specific game stage (early, mid, late)."""
    return [(name, meta) for name, meta in available_saves.items() if meta.get("stage") == stage]


def get_saves_by_empire_type(available_saves: dict, empire_type: str) -> list:
    """Get saves matching a specific empire type (organic, machine, hive_mind)."""
    return [
        (name, meta)
        for name, meta in available_saves.items()
        if meta.get("empire_type") == empire_type
    ]


# --- Basic Functionality Tests ---


class TestSaveCorpusBasics:
    """Basic tests that verify extraction doesn't crash and returns valid data."""

    def test_corpus_has_at_least_one_save(self, available_saves):
        """At least one save file is available for testing."""
        assert len(available_saves) > 0, "No test saves found in corpus"

    def test_extractor_initialization(self, test_save_path):
        """SaveExtractor initializes without crashing."""
        extractor = SaveExtractor(str(test_save_path))
        assert extractor is not None
        assert hasattr(extractor, "gamestate")
        assert len(extractor.gamestate) > 0

    def test_metadata_extraction(self, extractor):
        """Metadata extraction returns expected fields."""
        meta = extractor.get_metadata()

        assert isinstance(meta, dict)
        assert "date" in meta
        assert "version" in meta

    def test_player_status_extraction(self, extractor):
        """Player status extraction returns expected fields."""
        player = extractor.get_player_status()

        assert isinstance(player, dict)
        # Should have basic player info
        assert "empire_name" in player or "name" in player or len(player) > 0

    def test_resources_extraction(self, extractor):
        """Resources extraction returns expected structure."""
        resources = extractor.get_resources()

        assert isinstance(resources, dict)
        # Should have some resource information
        assert "stockpiles" in resources or "income" in resources or len(resources) > 0

    def test_diplomacy_extraction(self, extractor):
        """Diplomacy extraction returns expected structure."""
        diplomacy = extractor.get_diplomacy()

        assert isinstance(diplomacy, dict)
        # Can have empty relations in some game states
        assert isinstance(diplomacy.get("relations", []), list)

    def test_leaders_extraction(self, extractor):
        """Leaders extraction returns expected structure."""
        leaders = extractor.get_leaders()

        assert isinstance(leaders, dict)
        leader_list = leaders.get("leaders", [])
        assert isinstance(leader_list, list)

    def test_technology_extraction(self, extractor):
        """Technology extraction returns expected structure."""
        tech = extractor.get_technology()

        assert isinstance(tech, dict)

    def test_fleets_extraction(self, extractor):
        """Fleets extraction returns expected structure."""
        fleets = extractor.get_fleets()

        assert isinstance(fleets, dict)

    def test_planets_extraction(self, extractor):
        """Planets extraction returns expected structure."""
        planets = extractor.get_planets()

        assert isinstance(planets, dict)

    def test_complete_briefing_no_crash(self, extractor):
        """Complete briefing extraction doesn't crash."""
        briefing = extractor.get_complete_briefing()

        assert isinstance(briefing, dict)
        assert len(briefing) > 0


# --- Save Type Coverage Tests ---


class TestSaveTypeCoverage:
    """Tests that verify coverage of different save types."""

    def test_base_game_saves_available(self, available_saves):
        """At least one base game save is available."""
        base_game_saves = get_saves_by_type(available_saves, "base_game")
        # We expect at least test_save.sav
        if not base_game_saves:
            pytest.skip("No base_game saves available in corpus")
        assert len(base_game_saves) >= 1

    def test_dlc_saves_coverage(self, available_saves):
        """Check DLC save coverage (informational, may skip)."""
        dlc_saves = get_saves_by_type(available_saves, "dlc")
        if not dlc_saves:
            pytest.skip("No DLC saves available in corpus yet - add saves with DLC content")
        assert len(dlc_saves) >= 1

    def test_mod_saves_coverage(self, available_saves):
        """Check mod save coverage (informational, may skip)."""
        mod_saves = get_saves_by_type(available_saves, "mod")
        if not mod_saves:
            pytest.skip("No mod saves available in corpus yet - add saves with mod content")
        assert len(mod_saves) >= 1


# --- Game Stage Coverage Tests ---


class TestGameStageCoverage:
    """Tests that verify coverage of different game stages."""

    def test_early_game_saves_coverage(self, available_saves):
        """Check early game save coverage (informational, may skip)."""
        early_saves = get_saves_by_stage(available_saves, "early")
        if not early_saves:
            pytest.skip("No early game saves available in corpus yet - add saves from before 2250")
        assert len(early_saves) >= 1

    def test_mid_game_saves_coverage(self, available_saves):
        """Check mid game save coverage (informational, may skip)."""
        mid_saves = get_saves_by_stage(available_saves, "mid")
        if not mid_saves:
            pytest.skip("No mid game saves available in corpus yet - add saves from 2250-2400")
        assert len(mid_saves) >= 1

    def test_late_game_saves_coverage(self, available_saves):
        """Check late game save coverage."""
        late_saves = get_saves_by_stage(available_saves, "late")
        # test_save.sav should be late game
        if not late_saves:
            pytest.skip("No late game saves available in corpus")
        assert len(late_saves) >= 1


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

    def test_leaders_have_required_fields(self, extractor):
        """Leaders have required fields."""
        leaders = extractor.get_leaders()
        leader_list = leaders.get("leaders", [])

        if not leader_list:
            pytest.skip("No leaders in save")

        for leader in leader_list[:5]:  # Check first 5
            # Leaders should have at least an ID or class
            assert leader.get("id") is not None or leader.get("class") is not None

    def test_resources_have_stockpiles(self, extractor):
        """Resources include stockpile information."""
        resources = extractor.get_resources()

        stockpiles = resources.get("stockpiles", {})
        # Should have at least energy and minerals
        assert "energy" in stockpiles or "minerals" in stockpiles or len(stockpiles) > 0


# --- Corpus Expansion Helpers ---


class TestCorpusMetadata:
    """Tests for corpus metadata and documentation."""

    def test_corpus_config_has_descriptions(self):
        """All corpus entries have descriptions."""
        for save_name, meta in SAVE_CORPUS.items():
            assert "description" in meta, f"{save_name} missing description"

    def test_corpus_config_has_required_fields(self):
        """All corpus entries have required metadata fields."""
        required_fields = ["type", "stage", "empire_type"]

        for save_name, meta in SAVE_CORPUS.items():
            for field in required_fields:
                assert field in meta, f"{save_name} missing {field}"

    def test_corpus_types_are_valid(self):
        """Corpus type values are from allowed set."""
        valid_types = {"base_game", "dlc", "mod"}

        for save_name, meta in SAVE_CORPUS.items():
            assert meta.get("type") in valid_types, (
                f"{save_name} has invalid type: {meta.get('type')}"
            )

    def test_corpus_stages_are_valid(self):
        """Corpus stage values are from allowed set."""
        valid_stages = {"early", "mid", "late"}

        for save_name, meta in SAVE_CORPUS.items():
            assert meta.get("stage") in valid_stages, (
                f"{save_name} has invalid stage: {meta.get('stage')}"
            )

    def test_corpus_empire_types_are_valid(self):
        """Corpus empire_type values are from allowed set."""
        valid_empire_types = {"organic", "machine", "hive_mind"}

        for save_name, meta in SAVE_CORPUS.items():
            assert meta.get("empire_type") in valid_empire_types, (
                f"{save_name} has invalid empire_type"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
