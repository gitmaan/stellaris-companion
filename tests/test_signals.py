"""Tests for backend.core.signals module.

Tests the SnapshotSignals builder which produces normalized, resolved data
from SaveExtractor for events and chronicle processing.
"""

import os
import sys
from unittest.mock import MagicMock

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core.signals import (
    _clean_war_name_part,
    _extract_diplomacy_signals,
    _extract_edicts_signals,
    _extract_leader_signals,
    _extract_policies_signals,
    _extract_systems_signals,
    _extract_technology_signals,
    _extract_war_signals,
    _resolve_war_name_from_block,
    build_snapshot_signals,
)

# --- Fixtures ---


@pytest.fixture
def mock_extractor():
    """Create a mock SaveExtractor for testing."""
    extractor = MagicMock()

    # Mock get_player_empire_id
    extractor.get_player_empire_id.return_value = 0

    # Mock get_leaders
    extractor.get_leaders.return_value = {
        "leaders": [
            {
                "id": 1,
                "class": "admiral",
                "level": 3,
                "name": "Admiral Korath",
                "date_added": "2200.01.01",
            },
            {
                "id": 2,
                "class": "scientist",
                "level": 5,
                "name": "Dr. Zyx",
            },
        ]
    }

    # Mock get_wars
    extractor.get_wars.return_value = {
        "player_at_war": False,
        "wars": [
            {"name": "Ubaric-Ziiran War"},
        ],
    }

    # Mock get_diplomacy
    extractor.get_diplomacy.return_value = {
        "allies": [{"id": 1, "name": "Friendly Empire"}],
        "rivals": [{"id": 2, "name": "Enemy Empire"}],
        "defensive_pacts": [],
        "non_aggression_pacts": [],
        "commercial_pacts": [],
        "migration_treaties": [],
        "sensor_links": [],
        "closed_borders": [],
        "relations": [],
    }

    # Mock get_technology
    extractor.get_technology.return_value = {
        "researched_techs": ["tech_lasers_1", "tech_shields_1", "tech_colony_ship"],
        "in_progress": {
            "physics": {"tech": "tech_lasers_2", "progress": 50},
            "society": {"tech": "tech_colonization_1", "progress": 30},
            "engineering": None,
        },
    }

    # Mock get_megastructures
    extractor.get_megastructures.return_value = {
        "megastructures": [
            {"id": 0, "type": "dyson_sphere_5", "status": "complete"},
            {"id": 1, "type": "ring_world_2", "status": "building"},
        ],
        "by_type": {"dyson_sphere_5": 1, "ring_world_2": 1},
    }

    # Mock get_crisis_status
    extractor.get_crisis_status.return_value = {
        "crisis_active": False,
        "crisis_type": None,
    }

    # Mock get_fallen_empires
    extractor.get_fallen_empires.return_value = {
        "fallen_empires": [
            {
                "name": "Ancient Preservers",
                "status": "dormant",
                "archetype": "xenophile",
                "military_power": 100000,
            },
        ],
        "dormant_count": 1,
        "awakened_count": 0,
        "war_in_heaven": False,
    }

    # Mock _get_player_country_entry for policies/edicts
    extractor._get_player_country_entry.return_value = {
        "active_policies": [
            {"policy": "war_philosophy", "selected": "liberation_wars"},
            {"policy": "economic_policy", "selected": "balanced"},
        ],
        "edicts": [
            {"edict": "capacity_subsidies"},
            {"edict": "research_subsidies"},
        ],
    }

    # Mock get_starbases
    extractor.get_starbases.return_value = {
        "count": 12,
        "by_level": {"starbase_outpost": 8, "starbase_starport": 3, "starbase_starhold": 1},
    }

    # Mock get_strategic_geography
    extractor.get_strategic_geography.return_value = {
        "border_neighbors": [],
        "chokepoints": [],
        "empire_centroid": None,
        "total_player_systems": 12,
    }

    return extractor


@pytest.fixture
def minimal_briefing():
    """Create a minimal briefing dict for testing."""
    return {"meta": {"player_id": 0}}


@pytest.fixture
def briefing_with_cached_sections():
    """Briefing shaped like get_complete_briefing() output for cache tests."""
    return {
        "meta": {"player_id": 0},
        "leadership": {
            "leaders": [{"id": "1", "class": "official", "name": "Ruler One"}],
            "count": 1,
            "by_class": {"official": 1},
        },
        "military": {
            "wars": {"player_at_war": False, "wars": [], "active_war_count": 0},
            "megastructures": {"megastructures": [], "by_type": {}},
        },
        "diplomacy": {
            "allies": [],
            "rivals": [],
            "defensive_pacts": [],
            "non_aggression_pacts": [],
            "commercial_pacts": [],
            "migration_treaties": [],
            "sensor_links": [],
            "closed_borders": [],
            "relations": [],
            "treaties": [],
        },
        "technology": {"researched_techs": [], "in_progress": {}},
        "fallen_empires": {
            "fallen_empires": [],
            "dormant_count": 0,
            "awakened_count": 0,
            "war_in_heaven": False,
        },
        "defense": {"count": 0, "by_level": {}, "starbases": []},
        "endgame": {
            "crisis": {"crisis_active": False, "crisis_type": None},
            "lgate": {
                "lgate_enabled": False,
                "lgate_opened": False,
                "insights_collected": 0,
                "insights_required": 7,
            },
            "menace": {"has_crisis_perk": False, "menace_level": 0, "crisis_level": 0},
            "great_khan": {
                "marauders_present": False,
                "marauder_count": 0,
                "khan_risen": False,
                "khan_status": None,
                "khan_country_id": None,
            },
        },
        "projects": {"precursor_progress": {}},
        "progression": {
            "ascension_perks": {"ascension_perks": []},
            "traditions": {"by_tree": {}, "count": 0},
            "galactic_community": {
                "community_formed": False,
                "player_is_member": False,
                "council_members": [],
                "members_count": 0,
            },
        },
        "strategic_geography": {
            "border_neighbors": [],
            "chokepoints": [],
            "empire_centroid": None,
            "total_player_systems": 0,
        },
    }


# --- Tests for build_snapshot_signals ---


class TestBuildSnapshotSignals:
    """Tests for the main build_snapshot_signals function."""

    def test_handles_empty_briefing(self, mock_extractor):
        """Handles empty briefing gracefully."""
        result = build_snapshot_signals(extractor=mock_extractor, briefing={})
        assert isinstance(result, dict)
        assert result["player_id"] is None

    def test_handles_non_dict_briefing(self, mock_extractor):
        """Handles non-dict briefing gracefully."""
        result = build_snapshot_signals(extractor=mock_extractor, briefing=None)
        assert isinstance(result, dict)
        assert result["player_id"] is None

    def test_prefers_briefing_cached_sections(self, briefing_with_cached_sections):
        """Uses briefing-backed data instead of re-calling extractor methods."""
        extractor = MagicMock()
        extractor.get_player_empire_id.return_value = 0
        extractor._get_player_country_entry.return_value = {
            "ruler": 1,
            "active_policies": [],
            "edicts": [],
        }

        # These should be served from briefing (no extractor calls).
        for method_name in (
            "get_leaders",
            "get_wars",
            "get_diplomacy",
            "get_technology",
            "get_megastructures",
            "get_crisis_status",
            "get_fallen_empires",
            "get_starbases",
            "get_ascension_perks",
            "get_lgate_status",
            "get_menace",
            "get_great_khan",
            "get_galactic_community",
            "get_traditions",
            "get_special_projects",
            "get_strategic_geography",
        ):
            getattr(extractor, method_name).side_effect = AssertionError(
                f"{method_name} should not be called when briefing provides cached data"
            )

        result = build_snapshot_signals(extractor=extractor, briefing=briefing_with_cached_sections)
        assert isinstance(result, dict)
        assert result.get("player_id") == 0


# --- Tests for _extract_leader_signals ---


class TestExtractLeaderSignals:
    """Tests for _extract_leader_signals function."""

    def test_handles_empty_leaders(self, mock_extractor):
        """Handles empty leaders list gracefully."""
        mock_extractor.get_leaders.return_value = {"leaders": []}
        result = _extract_leader_signals(mock_extractor)

        assert result["count"] == 0
        assert result["leaders"] == []


# --- Tests for _extract_war_signals ---


class TestExtractWarSignals:
    """Tests for _extract_war_signals function."""

    def test_handles_no_wars(self, mock_extractor):
        """Handles no active wars."""
        mock_extractor.get_wars.return_value = {
            "player_at_war": False,
            "wars": [],
        }
        result = _extract_war_signals(mock_extractor)

        assert result["player_at_war"] is False
        assert result["count"] == 0


# --- Tests for _extract_diplomacy_signals ---


class TestExtractDiplomacySignals:
    """Tests for _extract_diplomacy_signals function."""

    def test_allies_are_sorted_ids(self, mock_extractor):
        """Allies are returned as sorted list of IDs."""
        result = _extract_diplomacy_signals(mock_extractor)

        assert isinstance(result["allies"], list)
        # Should be integers
        for ally_id in result["allies"]:
            assert isinstance(ally_id, int)

    def test_handles_empty_diplomacy(self, mock_extractor):
        """Handles empty diplomacy data."""
        mock_extractor.get_diplomacy.return_value = {}
        result = _extract_diplomacy_signals(mock_extractor)

        assert result["allies"] == []
        assert result["rivals"] == []


# --- Tests for _extract_technology_signals ---


class TestExtractTechnologySignals:
    """Tests for _extract_technology_signals function."""

    def test_techs_are_sorted(self, mock_extractor):
        """Tech list is sorted."""
        result = _extract_technology_signals(mock_extractor)

        techs = result["techs"]
        assert techs == sorted(techs)

    def test_handles_empty_technology(self, mock_extractor):
        """Handles empty technology data."""
        mock_extractor.get_technology.return_value = {}
        result = _extract_technology_signals(mock_extractor)

        assert result["techs"] == []
        assert result["count"] == 0


# --- Tests for _extract_policies_signals ---


class TestExtractPoliciesSignals:
    """Tests for _extract_policies_signals function."""

    def test_policies_as_dict_mapping(self, mock_extractor):
        """Policies are returned as policy_name -> selected_value dict."""
        result = _extract_policies_signals(mock_extractor)

        assert "war_philosophy" in result["policies"]
        assert result["policies"]["war_philosophy"] == "liberation_wars"


# --- Tests for _extract_edicts_signals ---


class TestExtractEdictsSignals:
    """Tests for _extract_edicts_signals function."""

    def test_edicts_are_sorted_unique(self, mock_extractor):
        """Edicts are returned as sorted unique list."""
        result = _extract_edicts_signals(mock_extractor)

        edicts = result["edicts"]
        assert edicts == sorted(set(edicts))


# --- Tests for _extract_systems_signals ---


class TestExtractSystemsSignals:
    """Tests for _extract_systems_signals function."""

    def test_count_matches_starbases(self, mock_extractor):
        """System count matches starbase count."""
        result = _extract_systems_signals(mock_extractor)
        assert result["count"] == 12


# --- Tests for helper functions ---


class TestCleanWarNamePart:
    """Tests for _clean_war_name_part helper function."""

    def test_removes_spec_prefix(self):
        """Removes SPEC_ prefix."""
        assert _clean_war_name_part("SPEC_Ubaric") == "Ubaric"

    def test_removes_adj_prefix(self):
        """Removes ADJ_ prefix."""
        assert _clean_war_name_part("ADJ_Human") == "Human"

    def test_removes_prescripted_prefix(self):
        """Removes PRESCRIPTED_ prefix and cleans species pattern."""
        # Note: "humans1" -> "Humans" (title case of base, number stripped)
        assert _clean_war_name_part("PRESCRIPTED_adjective_humans1") == "Humans"

    def test_handles_species_number_pattern(self):
        """Handles species name followed by number."""
        # Species patterns like "humans1" are title-cased with number stripped
        assert _clean_war_name_part("humans1") == "Humans"
        assert _clean_war_name_part("molluscoid5") == "Molluscoid"

    def test_handles_empty_string(self):
        """Handles empty string."""
        assert _clean_war_name_part("") == ""

    def test_handles_underscores(self):
        """Converts underscores to spaces."""
        assert _clean_war_name_part("war_name_test") == "War Name Test"


class TestResolveWarNameFromBlock:
    """Tests for _resolve_war_name_from_block helper function."""

    def test_handles_simple_string(self):
        """Returns simple string names directly."""
        assert _resolve_war_name_from_block("Test War") == "Test War"

    def test_handles_none(self):
        """Returns None for None input."""
        assert _resolve_war_name_from_block(None) is None

    def test_handles_empty_string(self):
        """Returns None for empty string."""
        assert _resolve_war_name_from_block("") is None
        assert _resolve_war_name_from_block("   ") is None

    def test_handles_war_vs_adjectives_pattern(self):
        """Resolves war_vs_adjectives pattern."""
        name_block = {
            "key": "war_vs_adjectives",
            "variables": [
                {"key": "1", "value": "Ubaric"},
                {"key": "2", "value": "Ziiran"},
                {"key": "3", "value": "War"},
            ],
        }
        result = _resolve_war_name_from_block(name_block)
        assert result == "Ubaric-Ziiran War"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
