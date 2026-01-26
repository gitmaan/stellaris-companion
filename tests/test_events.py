"""Tests for backend.core.events module.

Tests the event detection system which computes derived events by comparing
two game snapshots (previous vs current).
"""

import os
import sys

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core.events import (
    DetectedEvent,
    _extract_crisis,
    _extract_diplomacy_sets,
    _extract_edicts,
    _extract_empire_names,
    _extract_fallen_empires,
    _extract_galaxy_settings,
    _extract_megastructures,
    _extract_player_leaders,
    _extract_policies,
    _extract_system_count,
    _extract_tech_list,
    _extract_war_names,
    _get_empire_name,
    _get_leader_name,
    _normalize_federation,
    _parse_year,
    _pct_change,
    _safe_float,
    _safe_int,
    _sign_changed,
    compute_events,
)

# --- Fixtures ---


@pytest.fixture
def base_prev_snapshot():
    """Create a base previous snapshot for testing."""
    return {
        "meta": {"date": "2250.01.01", "player_id": 0},
        "military": {"military_power": 10000, "military_fleets": 5},
        "territory": {"colonies": {"total_count": 3}},
        "technology": {"tech_count": 10},
        "economy": {
            "net_monthly": {
                "energy": 50.0,
                "alloys": 20.0,
                "consumer_goods": 10.0,
                "food": 15.0,
                "minerals": 100.0,
            }
        },
        "diplomacy": {"federation": None},
        "history": {
            "wars": {"wars": []},
            "leaders": {"leaders": []},
            "diplomacy": {"allies": [], "rivals": [], "treaties": {}, "empire_names": {}},
            "galaxy": {"mid_game_start": 50, "end_game_start": 150},
            "techs": {"techs": []},
            "policies": {"policies": {}},
            "edicts": {"edicts": []},
            "megastructures": {"megastructures": []},
            "crisis": {"active": False, "type": None},
            "fallen_empires": {"fallen_empires": [], "war_in_heaven": False},
            "systems": {"system_count": 10},
        },
    }


@pytest.fixture
def base_curr_snapshot():
    """Create a base current snapshot for testing."""
    return {
        "meta": {"date": "2260.01.01", "player_id": 0},
        "military": {"military_power": 15000, "military_fleets": 7},
        "territory": {"colonies": {"total_count": 5}},
        "technology": {"tech_count": 15},
        "economy": {
            "net_monthly": {
                "energy": 75.0,
                "alloys": 30.0,
                "consumer_goods": 15.0,
                "food": 20.0,
                "minerals": 150.0,
            }
        },
        "diplomacy": {"federation": None},
        "history": {
            "wars": {"wars": []},
            "leaders": {"leaders": []},
            "diplomacy": {"allies": [], "rivals": [], "treaties": {}, "empire_names": {}},
            "galaxy": {"mid_game_start": 50, "end_game_start": 150},
            "techs": {"techs": []},
            "policies": {"policies": {}},
            "edicts": {"edicts": []},
            "megastructures": {"megastructures": []},
            "crisis": {"active": False, "type": None},
            "fallen_empires": {"fallen_empires": [], "war_in_heaven": False},
            "systems": {"system_count": 12},
        },
    }


# --- Tests for helper functions ---


class TestSafeInt:
    """Tests for _safe_int helper function."""

    def test_converts_int(self):
        """Converts int to int."""
        assert _safe_int(42) == 42

    def test_converts_float(self):
        """Converts float to int."""
        assert _safe_int(42.9) == 42

    def test_converts_string(self):
        """Converts numeric string to int."""
        assert _safe_int("42") == 42

    def test_returns_none_for_none(self):
        """Returns None for None input."""
        assert _safe_int(None) is None

    def test_returns_none_for_invalid(self):
        """Returns None for non-numeric string."""
        assert _safe_int("not a number") is None


class TestSafeFloat:
    """Tests for _safe_float helper function."""

    def test_converts_float(self):
        """Converts float to float."""
        assert _safe_float(42.5) == 42.5

    def test_converts_int(self):
        """Converts int to float."""
        assert _safe_float(42) == 42.0

    def test_converts_string(self):
        """Converts numeric string to float."""
        assert _safe_float("42.5") == 42.5

    def test_returns_none_for_none(self):
        """Returns None for None input."""
        assert _safe_float(None) is None

    def test_returns_none_for_invalid(self):
        """Returns None for non-numeric string."""
        assert _safe_float("not a number") is None


class TestPctChange:
    """Tests for _pct_change helper function."""

    def test_calculates_increase(self):
        """Calculates percentage increase."""
        result = _pct_change(100, 150)
        assert result == 0.5  # 50% increase

    def test_calculates_decrease(self):
        """Calculates percentage decrease."""
        result = _pct_change(100, 75)
        assert result == -0.25  # 25% decrease

    def test_returns_none_for_zero_before(self):
        """Returns None when before value is zero."""
        assert _pct_change(0, 100) is None

    def test_returns_none_for_none_values(self):
        """Returns None when either value is None."""
        assert _pct_change(None, 100) is None
        assert _pct_change(100, None) is None


class TestSignChanged:
    """Tests for _sign_changed helper function."""

    def test_positive_to_negative(self):
        """Detects change from positive to negative."""
        assert _sign_changed(10, -5) is True

    def test_negative_to_positive(self):
        """Detects change from negative to positive."""
        assert _sign_changed(-10, 5) is True

    def test_same_sign(self):
        """Returns False when sign is unchanged."""
        assert _sign_changed(10, 20) is False
        assert _sign_changed(-10, -20) is False

    def test_returns_false_for_none(self):
        """Returns False when either value is None."""
        assert _sign_changed(None, 10) is False
        assert _sign_changed(10, None) is False


class TestNormalizeFederation:
    """Tests for _normalize_federation helper function."""

    def test_returns_none_for_no_federation(self):
        """Returns None when not in federation."""
        briefing = {"diplomacy": {"federation": None}}
        assert _normalize_federation(briefing) is None

    def test_returns_string_federation_name(self):
        """Returns federation name when it's a string."""
        briefing = {"diplomacy": {"federation": "Galactic Union"}}
        assert _normalize_federation(briefing) == "Galactic Union"

    def test_extracts_name_from_dict(self):
        """Extracts name from federation dict."""
        briefing = {"diplomacy": {"federation": {"name": "Star Alliance"}}}
        assert _normalize_federation(briefing) == "Star Alliance"

    def test_handles_empty_briefing(self):
        """Handles empty briefing gracefully."""
        assert _normalize_federation({}) is None

    def test_handles_non_dict_briefing(self):
        """Handles non-dict briefing gracefully."""
        assert _normalize_federation(None) is None


class TestExtractWarNames:
    """Tests for _extract_war_names helper function."""

    def test_extracts_war_names(self):
        """Extracts set of war names."""
        briefing = {"history": {"wars": {"wars": ["War 1", "War 2"]}}}
        result = _extract_war_names(briefing)
        assert result == {"War 1", "War 2"}

    def test_handles_empty_wars(self):
        """Handles empty wars list."""
        briefing = {"history": {"wars": {"wars": []}}}
        assert _extract_war_names(briefing) == set()

    def test_handles_missing_wars(self):
        """Handles missing wars key."""
        assert _extract_war_names({}) == set()


class TestExtractPlayerLeaders:
    """Tests for _extract_player_leaders helper function."""

    def test_extracts_leaders_by_id(self):
        """Extracts leaders indexed by id."""
        briefing = {
            "history": {
                "leaders": {
                    "leaders": [
                        {"id": 1, "class": "admiral", "name": "Admiral X"},
                        {"id": 2, "class": "scientist", "name": "Dr. Y"},
                    ]
                }
            }
        }
        result = _extract_player_leaders(briefing)
        assert 1 in result
        assert 2 in result
        assert result[1]["class"] == "admiral"

    def test_handles_empty_leaders(self):
        """Handles empty leaders list."""
        briefing = {"history": {"leaders": {"leaders": []}}}
        assert _extract_player_leaders(briefing) == {}

    def test_handles_missing_leaders(self):
        """Handles missing leaders key."""
        assert _extract_player_leaders({}) == {}


class TestGetLeaderName:
    """Tests for _get_leader_name helper function."""

    def test_returns_name_if_present(self):
        """Returns name field if present."""
        leader = {"id": 1, "name": "Admiral Korath"}
        assert _get_leader_name(leader) == "Admiral Korath"

    def test_falls_back_to_name_key(self):
        """Falls back to name_key if name not present."""
        leader = {"id": 1, "name_key": "NAME_Admiral"}
        assert _get_leader_name(leader) == "Admiral"

    def test_handles_chr_pattern(self):
        """Handles _CHR_ pattern in name_key."""
        leader = {"id": 1, "name_key": "prefix_CHR_Zyx"}
        assert _get_leader_name(leader) == "Zyx"

    def test_falls_back_to_id(self):
        """Falls back to ID if no name available."""
        leader = {"id": 42}
        assert _get_leader_name(leader) == "#42"

    def test_returns_unknown_for_empty_leader(self):
        """Returns #unknown for completely empty leader."""
        assert _get_leader_name({}) == "#unknown"


class TestExtractEmpireNames:
    """Tests for _extract_empire_names helper function."""

    def test_extracts_empire_names(self):
        """Extracts empire_names mapping."""
        briefing = {
            "history": {"diplomacy": {"empire_names": {"1": "Galactic Empire", "2": "Republic"}}}
        }
        result = _extract_empire_names(briefing)
        assert result[1] == "Galactic Empire"
        assert result[2] == "Republic"

    def test_handles_empty_names(self):
        """Handles empty empire_names."""
        briefing = {"history": {"diplomacy": {"empire_names": {}}}}
        assert _extract_empire_names(briefing) == {}


class TestGetEmpireName:
    """Tests for _get_empire_name helper function."""

    def test_returns_name_if_known(self):
        """Returns empire name if in mapping."""
        empire_names = {1: "Galactic Empire", 2: "Republic"}
        assert _get_empire_name(1, empire_names) == "Galactic Empire"

    def test_falls_back_to_id(self):
        """Falls back to empire #ID if not in mapping."""
        assert _get_empire_name(99, {}) == "empire #99"


class TestExtractDiplomacySets:
    """Tests for _extract_diplomacy_sets helper function."""

    def test_extracts_allies_rivals_treaties(self):
        """Extracts allies, rivals, and treaties as sets."""
        briefing = {
            "history": {
                "diplomacy": {
                    "allies": [1, 2],
                    "rivals": [3],
                    "treaties": {"defensive_pact": [1], "commercial_pact": [2]},
                }
            }
        }
        allies, rivals, treaties = _extract_diplomacy_sets(briefing)
        assert allies == {1, 2}
        assert rivals == {3}
        assert treaties["defensive_pact"] == {1}

    def test_handles_empty_diplomacy(self):
        """Handles empty diplomacy data."""
        allies, rivals, treaties = _extract_diplomacy_sets({})
        assert allies == set()
        assert rivals == set()
        assert treaties == {}


class TestParseYear:
    """Tests for _parse_year helper function."""

    def test_parses_stellaris_date(self):
        """Parses Stellaris date format."""
        assert _parse_year("2250.01.01") == 2250

    def test_returns_none_for_invalid(self):
        """Returns None for invalid date."""
        assert _parse_year("abc") is None
        assert _parse_year(None) is None
        assert _parse_year("") is None


class TestExtractGalaxySettings:
    """Tests for _extract_galaxy_settings helper function."""

    def test_extracts_settings(self):
        """Extracts galaxy settings dict."""
        briefing = {"history": {"galaxy": {"mid_game_start": 50, "end_game_start": 150}}}
        result = _extract_galaxy_settings(briefing)
        assert result["mid_game_start"] == 50
        assert result["end_game_start"] == 150

    def test_handles_missing_settings(self):
        """Handles missing galaxy settings."""
        assert _extract_galaxy_settings({}) == {}


class TestExtractTechList:
    """Tests for _extract_tech_list helper function."""

    def test_extracts_tech_names(self):
        """Extracts set of tech names."""
        briefing = {"history": {"techs": {"techs": ["tech_lasers_1", "tech_shields_1"]}}}
        result = _extract_tech_list(briefing)
        assert result == {"tech_lasers_1", "tech_shields_1"}

    def test_handles_empty_techs(self):
        """Handles empty techs list."""
        briefing = {"history": {"techs": {"techs": []}}}
        assert _extract_tech_list(briefing) == set()


class TestExtractSystemCount:
    """Tests for _extract_system_count helper function."""

    def test_extracts_count(self):
        """Extracts system count."""
        briefing = {"history": {"systems": {"system_count": 42}}}
        assert _extract_system_count(briefing) == 42

    def test_handles_missing_count(self):
        """Handles missing system count."""
        assert _extract_system_count({}) is None


class TestExtractPolicies:
    """Tests for _extract_policies helper function."""

    def test_extracts_policies(self):
        """Extracts policy dict."""
        briefing = {"history": {"policies": {"policies": {"war_policy": "defensive"}}}}
        result = _extract_policies(briefing)
        assert result["war_policy"] == "defensive"

    def test_handles_empty_policies(self):
        """Handles empty policies."""
        assert _extract_policies({}) == {}


class TestExtractEdicts:
    """Tests for _extract_edicts helper function."""

    def test_extracts_edicts(self):
        """Extracts set of edict names."""
        briefing = {"history": {"edicts": {"edicts": ["edict_a", "edict_b"]}}}
        result = _extract_edicts(briefing)
        assert result == {"edict_a", "edict_b"}

    def test_handles_empty_edicts(self):
        """Handles empty edicts."""
        assert _extract_edicts({}) == set()


class TestExtractMegastructures:
    """Tests for _extract_megastructures helper function."""

    def test_extracts_megastructures_by_id(self):
        """Extracts megastructures indexed by ID."""
        briefing = {
            "history": {
                "megastructures": {
                    "megastructures": [
                        {"id": 0, "type": "dyson_sphere", "stage": 3},
                        {"id": 1, "type": "ring_world", "stage": 2},
                    ]
                }
            }
        }
        result = _extract_megastructures(briefing)
        assert 0 in result
        assert result[0]["type"] == "dyson_sphere"

    def test_handles_empty_megastructures(self):
        """Handles empty megastructures."""
        assert _extract_megastructures({}) == {}


class TestExtractCrisis:
    """Tests for _extract_crisis helper function."""

    def test_extracts_crisis(self):
        """Extracts crisis data."""
        briefing = {"history": {"crisis": {"active": True, "type": "prethoryn"}}}
        result = _extract_crisis(briefing)
        assert result["active"] is True
        assert result["type"] == "prethoryn"

    def test_returns_inactive_for_missing(self):
        """Returns inactive crisis for missing data."""
        result = _extract_crisis({})
        assert result["active"] is False


class TestExtractFallenEmpires:
    """Tests for _extract_fallen_empires helper function."""

    def test_extracts_fallen_empires_by_name(self):
        """Extracts fallen empires indexed by name."""
        briefing = {
            "history": {
                "fallen_empires": {
                    "fallen_empires": [
                        {"name": "Ancient Preservers", "status": "dormant"},
                        {"name": "Keepers", "status": "awakened"},
                    ]
                }
            }
        }
        result = _extract_fallen_empires(briefing)
        assert "Ancient Preservers" in result
        assert result["Ancient Preservers"]["status"] == "dormant"

    def test_handles_empty_fallen_empires(self):
        """Handles empty fallen empires."""
        assert _extract_fallen_empires({}) == {}


# --- Tests for compute_events ---


class TestComputeEvents:
    """Tests for the main compute_events function."""

    def test_returns_list(self, base_prev_snapshot, base_curr_snapshot):
        """compute_events returns a list."""
        result = compute_events(
            prev=base_prev_snapshot,
            curr=base_curr_snapshot,
            from_snapshot_id=1,
            to_snapshot_id=2,
        )
        assert isinstance(result, list)

    def test_returns_detected_event_instances(self, base_prev_snapshot, base_curr_snapshot):
        """Events in result are DetectedEvent instances."""
        result = compute_events(
            prev=base_prev_snapshot,
            curr=base_curr_snapshot,
            from_snapshot_id=1,
            to_snapshot_id=2,
        )
        for event in result:
            assert isinstance(event, DetectedEvent)

    def test_detects_military_power_change(self, base_prev_snapshot, base_curr_snapshot):
        """Detects significant military power changes."""
        # Modify to ensure significant change (>=15% AND >=2000, OR >=10000)
        base_prev_snapshot["military"]["military_power"] = 10000
        base_curr_snapshot["military"]["military_power"] = 20000  # +10000 absolute

        result = compute_events(
            prev=base_prev_snapshot,
            curr=base_curr_snapshot,
            from_snapshot_id=1,
            to_snapshot_id=2,
        )
        event_types = [e.event_type for e in result]
        assert "military_power_change" in event_types

    def test_detects_colony_change(self, base_prev_snapshot, base_curr_snapshot):
        """Detects colony count changes."""
        base_prev_snapshot["territory"]["colonies"]["total_count"] = 3
        base_curr_snapshot["territory"]["colonies"]["total_count"] = 5

        result = compute_events(
            prev=base_prev_snapshot,
            curr=base_curr_snapshot,
            from_snapshot_id=1,
            to_snapshot_id=2,
        )
        event_types = [e.event_type for e in result]
        assert "colony_count_change" in event_types

    def test_detects_tech_completed(self, base_prev_snapshot, base_curr_snapshot):
        """Detects technology completion."""
        base_prev_snapshot["technology"]["tech_count"] = 10
        base_curr_snapshot["technology"]["tech_count"] = 15

        result = compute_events(
            prev=base_prev_snapshot,
            curr=base_curr_snapshot,
            from_snapshot_id=1,
            to_snapshot_id=2,
        )
        event_types = [e.event_type for e in result]
        assert "tech_completed" in event_types

    def test_detects_federation_joined(self, base_prev_snapshot, base_curr_snapshot):
        """Detects joining a federation."""
        base_prev_snapshot["diplomacy"]["federation"] = None
        base_curr_snapshot["diplomacy"]["federation"] = "Galactic Union"

        result = compute_events(
            prev=base_prev_snapshot,
            curr=base_curr_snapshot,
            from_snapshot_id=1,
            to_snapshot_id=2,
        )
        event_types = [e.event_type for e in result]
        assert "federation_joined" in event_types

    def test_detects_federation_left(self, base_prev_snapshot, base_curr_snapshot):
        """Detects leaving a federation."""
        base_prev_snapshot["diplomacy"]["federation"] = "Galactic Union"
        base_curr_snapshot["diplomacy"]["federation"] = None

        result = compute_events(
            prev=base_prev_snapshot,
            curr=base_curr_snapshot,
            from_snapshot_id=1,
            to_snapshot_id=2,
        )
        event_types = [e.event_type for e in result]
        assert "federation_left" in event_types

    def test_detects_war_started(self, base_prev_snapshot, base_curr_snapshot):
        """Detects new wars starting."""
        base_prev_snapshot["history"]["wars"]["wars"] = []
        base_curr_snapshot["history"]["wars"]["wars"] = ["Conquest of Terra"]

        result = compute_events(
            prev=base_prev_snapshot,
            curr=base_curr_snapshot,
            from_snapshot_id=1,
            to_snapshot_id=2,
        )
        event_types = [e.event_type for e in result]
        assert "war_started" in event_types

    def test_detects_war_ended(self, base_prev_snapshot, base_curr_snapshot):
        """Detects wars ending."""
        base_prev_snapshot["history"]["wars"]["wars"] = ["Conquest of Terra"]
        base_curr_snapshot["history"]["wars"]["wars"] = []

        result = compute_events(
            prev=base_prev_snapshot,
            curr=base_curr_snapshot,
            from_snapshot_id=1,
            to_snapshot_id=2,
        )
        event_types = [e.event_type for e in result]
        assert "war_ended" in event_types

    def test_detects_leader_hired(self, base_prev_snapshot, base_curr_snapshot):
        """Detects new leaders being hired."""
        base_prev_snapshot["history"]["leaders"]["leaders"] = []
        base_curr_snapshot["history"]["leaders"]["leaders"] = [
            {"id": 1, "class": "admiral", "name": "Admiral Korath", "level": 3}
        ]

        result = compute_events(
            prev=base_prev_snapshot,
            curr=base_curr_snapshot,
            from_snapshot_id=1,
            to_snapshot_id=2,
        )
        event_types = [e.event_type for e in result]
        assert "leader_hired" in event_types

    def test_detects_leader_removed(self, base_prev_snapshot, base_curr_snapshot):
        """Detects leaders being removed."""
        base_prev_snapshot["history"]["leaders"]["leaders"] = [
            {"id": 1, "class": "admiral", "name": "Admiral Korath"}
        ]
        base_curr_snapshot["history"]["leaders"]["leaders"] = []

        result = compute_events(
            prev=base_prev_snapshot,
            curr=base_curr_snapshot,
            from_snapshot_id=1,
            to_snapshot_id=2,
        )
        event_types = [e.event_type for e in result]
        assert "leader_removed" in event_types

    def test_detects_leader_died(self, base_prev_snapshot, base_curr_snapshot):
        """Detects leader death (death_date appears)."""
        base_prev_snapshot["history"]["leaders"]["leaders"] = [
            {"id": 1, "class": "admiral", "name": "Admiral Korath", "death_date": None}
        ]
        base_curr_snapshot["history"]["leaders"]["leaders"] = [
            {"id": 1, "class": "admiral", "name": "Admiral Korath", "death_date": "2258.03.15"}
        ]

        result = compute_events(
            prev=base_prev_snapshot,
            curr=base_curr_snapshot,
            from_snapshot_id=1,
            to_snapshot_id=2,
        )
        event_types = [e.event_type for e in result]
        assert "leader_died" in event_types

    def test_detects_alliance_formed(self, base_prev_snapshot, base_curr_snapshot):
        """Detects new alliances forming."""
        base_prev_snapshot["history"]["diplomacy"]["allies"] = []
        base_curr_snapshot["history"]["diplomacy"]["allies"] = [1]
        base_curr_snapshot["history"]["diplomacy"]["empire_names"] = {1: "Friendly Empire"}

        result = compute_events(
            prev=base_prev_snapshot,
            curr=base_curr_snapshot,
            from_snapshot_id=1,
            to_snapshot_id=2,
        )
        event_types = [e.event_type for e in result]
        assert "alliance_formed" in event_types

    def test_detects_rivalry_declared(self, base_prev_snapshot, base_curr_snapshot):
        """Detects new rivalries."""
        base_prev_snapshot["history"]["diplomacy"]["rivals"] = []
        base_curr_snapshot["history"]["diplomacy"]["rivals"] = [2]

        result = compute_events(
            prev=base_prev_snapshot,
            curr=base_curr_snapshot,
            from_snapshot_id=1,
            to_snapshot_id=2,
        )
        event_types = [e.event_type for e in result]
        assert "rivalry_declared" in event_types

    def test_detects_treaty_signed(self, base_prev_snapshot, base_curr_snapshot):
        """Detects new treaties being signed."""
        base_prev_snapshot["history"]["diplomacy"]["treaties"] = {}
        base_curr_snapshot["history"]["diplomacy"]["treaties"] = {"defensive_pact": [1]}

        result = compute_events(
            prev=base_prev_snapshot,
            curr=base_curr_snapshot,
            from_snapshot_id=1,
            to_snapshot_id=2,
        )
        event_types = [e.event_type for e in result]
        assert "treaty_signed" in event_types

    def test_detects_midgame_milestone(self, base_prev_snapshot, base_curr_snapshot):
        """Detects entering midgame."""
        # Galaxy setting: mid_game_start = 50 (2200 + 50 = 2250)
        base_prev_snapshot["meta"]["date"] = "2249.01.01"
        base_curr_snapshot["meta"]["date"] = "2251.01.01"

        result = compute_events(
            prev=base_prev_snapshot,
            curr=base_curr_snapshot,
            from_snapshot_id=1,
            to_snapshot_id=2,
        )
        event_types = [e.event_type for e in result]
        assert "milestone_midgame" in event_types

    def test_detects_endgame_milestone(self, base_prev_snapshot, base_curr_snapshot):
        """Detects entering endgame."""
        # Galaxy setting: end_game_start = 150 (2200 + 150 = 2350)
        base_prev_snapshot["meta"]["date"] = "2349.01.01"
        base_curr_snapshot["meta"]["date"] = "2351.01.01"

        result = compute_events(
            prev=base_prev_snapshot,
            curr=base_curr_snapshot,
            from_snapshot_id=1,
            to_snapshot_id=2,
        )
        event_types = [e.event_type for e in result]
        assert "milestone_endgame" in event_types

    def test_detects_technology_researched(self, base_prev_snapshot, base_curr_snapshot):
        """Detects individual technologies being researched."""
        base_prev_snapshot["history"]["techs"]["techs"] = ["tech_lasers_1"]
        base_curr_snapshot["history"]["techs"]["techs"] = ["tech_lasers_1", "tech_lasers_2"]

        result = compute_events(
            prev=base_prev_snapshot,
            curr=base_curr_snapshot,
            from_snapshot_id=1,
            to_snapshot_id=2,
        )
        event_types = [e.event_type for e in result]
        assert "technology_researched" in event_types

    def test_detects_systems_gained(self, base_prev_snapshot, base_curr_snapshot):
        """Detects gaining systems."""
        base_prev_snapshot["history"]["systems"]["system_count"] = 10
        base_curr_snapshot["history"]["systems"]["system_count"] = 15

        result = compute_events(
            prev=base_prev_snapshot,
            curr=base_curr_snapshot,
            from_snapshot_id=1,
            to_snapshot_id=2,
        )
        event_types = [e.event_type for e in result]
        assert "systems_gained" in event_types

    def test_detects_systems_lost(self, base_prev_snapshot, base_curr_snapshot):
        """Detects losing systems."""
        base_prev_snapshot["history"]["systems"]["system_count"] = 15
        base_curr_snapshot["history"]["systems"]["system_count"] = 10

        result = compute_events(
            prev=base_prev_snapshot,
            curr=base_curr_snapshot,
            from_snapshot_id=1,
            to_snapshot_id=2,
        )
        event_types = [e.event_type for e in result]
        assert "systems_lost" in event_types

    def test_detects_policy_changed(self, base_prev_snapshot, base_curr_snapshot):
        """Detects policy changes."""
        base_prev_snapshot["history"]["policies"]["policies"] = {"war_policy": "defensive"}
        base_curr_snapshot["history"]["policies"]["policies"] = {"war_policy": "aggressive"}

        result = compute_events(
            prev=base_prev_snapshot,
            curr=base_curr_snapshot,
            from_snapshot_id=1,
            to_snapshot_id=2,
        )
        event_types = [e.event_type for e in result]
        assert "policy_changed" in event_types

    def test_detects_edict_activated(self, base_prev_snapshot, base_curr_snapshot):
        """Detects edicts being activated."""
        base_prev_snapshot["history"]["edicts"]["edicts"] = []
        base_curr_snapshot["history"]["edicts"]["edicts"] = ["edict_research_subsidies"]

        result = compute_events(
            prev=base_prev_snapshot,
            curr=base_curr_snapshot,
            from_snapshot_id=1,
            to_snapshot_id=2,
        )
        event_types = [e.event_type for e in result]
        assert "edict_activated" in event_types

    def test_detects_edict_expired(self, base_prev_snapshot, base_curr_snapshot):
        """Detects edicts expiring."""
        base_prev_snapshot["history"]["edicts"]["edicts"] = ["edict_research_subsidies"]
        base_curr_snapshot["history"]["edicts"]["edicts"] = []

        result = compute_events(
            prev=base_prev_snapshot,
            curr=base_curr_snapshot,
            from_snapshot_id=1,
            to_snapshot_id=2,
        )
        event_types = [e.event_type for e in result]
        assert "edict_expired" in event_types

    def test_detects_megastructure_started(self, base_prev_snapshot, base_curr_snapshot):
        """Detects new megastructures starting construction."""
        base_prev_snapshot["history"]["megastructures"]["megastructures"] = []
        base_curr_snapshot["history"]["megastructures"]["megastructures"] = [
            {"id": 0, "type": "dyson_sphere", "stage": 0}
        ]

        result = compute_events(
            prev=base_prev_snapshot,
            curr=base_curr_snapshot,
            from_snapshot_id=1,
            to_snapshot_id=2,
        )
        event_types = [e.event_type for e in result]
        assert "megastructure_started" in event_types

    def test_detects_megastructure_upgraded(self, base_prev_snapshot, base_curr_snapshot):
        """Detects megastructure stage upgrades."""
        base_prev_snapshot["history"]["megastructures"]["megastructures"] = [
            {"id": 0, "type": "dyson_sphere", "stage": 1}
        ]
        base_curr_snapshot["history"]["megastructures"]["megastructures"] = [
            {"id": 0, "type": "dyson_sphere", "stage": 2}
        ]

        result = compute_events(
            prev=base_prev_snapshot,
            curr=base_curr_snapshot,
            from_snapshot_id=1,
            to_snapshot_id=2,
        )
        event_types = [e.event_type for e in result]
        assert "megastructure_upgraded" in event_types

    def test_detects_crisis_started(self, base_prev_snapshot, base_curr_snapshot):
        """Detects crisis beginning."""
        base_prev_snapshot["history"]["crisis"] = {"active": False, "type": None}
        base_curr_snapshot["history"]["crisis"] = {"active": True, "type": "prethoryn"}

        result = compute_events(
            prev=base_prev_snapshot,
            curr=base_curr_snapshot,
            from_snapshot_id=1,
            to_snapshot_id=2,
        )
        event_types = [e.event_type for e in result]
        assert "crisis_started" in event_types

    def test_detects_crisis_defeated(self, base_prev_snapshot, base_curr_snapshot):
        """Detects crisis being defeated."""
        base_prev_snapshot["history"]["crisis"] = {"active": True, "type": "prethoryn"}
        base_curr_snapshot["history"]["crisis"] = {"active": False, "type": None}

        result = compute_events(
            prev=base_prev_snapshot,
            curr=base_curr_snapshot,
            from_snapshot_id=1,
            to_snapshot_id=2,
        )
        event_types = [e.event_type for e in result]
        assert "crisis_defeated" in event_types

    def test_detects_fallen_empire_awakened(self, base_prev_snapshot, base_curr_snapshot):
        """Detects fallen empire awakening."""
        base_prev_snapshot["history"]["fallen_empires"]["fallen_empires"] = [
            {"name": "Ancient Preservers", "status": "dormant", "archetype": "xenophile"}
        ]
        base_curr_snapshot["history"]["fallen_empires"]["fallen_empires"] = [
            {"name": "Ancient Preservers", "status": "awakened", "archetype": "xenophile"}
        ]

        result = compute_events(
            prev=base_prev_snapshot,
            curr=base_curr_snapshot,
            from_snapshot_id=1,
            to_snapshot_id=2,
        )
        event_types = [e.event_type for e in result]
        assert "fallen_empire_awakened" in event_types

    def test_detects_war_in_heaven_started(self, base_prev_snapshot, base_curr_snapshot):
        """Detects War in Heaven beginning."""
        base_prev_snapshot["history"]["fallen_empires"]["war_in_heaven"] = False
        base_curr_snapshot["history"]["fallen_empires"]["war_in_heaven"] = True

        result = compute_events(
            prev=base_prev_snapshot,
            curr=base_curr_snapshot,
            from_snapshot_id=1,
            to_snapshot_id=2,
        )
        event_types = [e.event_type for e in result]
        assert "war_in_heaven_started" in event_types

    def test_no_events_for_identical_snapshots(self, base_prev_snapshot):
        """Returns empty list for identical snapshots."""
        result = compute_events(
            prev=base_prev_snapshot,
            curr=base_prev_snapshot,
            from_snapshot_id=1,
            to_snapshot_id=2,
        )
        assert result == []

    def test_handles_empty_snapshots(self):
        """Handles empty snapshot dicts gracefully."""
        result = compute_events(
            prev={},
            curr={},
            from_snapshot_id=1,
            to_snapshot_id=2,
        )
        assert isinstance(result, list)

    def test_event_data_includes_snapshot_ids(self, base_prev_snapshot, base_curr_snapshot):
        """Event data includes from/to snapshot IDs."""
        base_prev_snapshot["territory"]["colonies"]["total_count"] = 3
        base_curr_snapshot["territory"]["colonies"]["total_count"] = 5

        result = compute_events(
            prev=base_prev_snapshot,
            curr=base_curr_snapshot,
            from_snapshot_id=42,
            to_snapshot_id=43,
        )
        # Find the colony_count_change event
        colony_event = next((e for e in result if e.event_type == "colony_count_change"), None)
        assert colony_event is not None
        assert colony_event.data["from_snapshot_id"] == 42
        assert colony_event.data["to_snapshot_id"] == 43


class TestDetectedEvent:
    """Tests for DetectedEvent dataclass."""

    def test_is_frozen(self):
        """DetectedEvent instances are immutable."""
        event = DetectedEvent(
            event_type="test_event",
            summary="Test summary",
            data={"key": "value"},
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            event.event_type = "modified"

    def test_has_required_fields(self):
        """DetectedEvent has event_type, summary, data fields."""
        event = DetectedEvent(
            event_type="test_event",
            summary="Test summary",
            data={"key": "value"},
        )
        assert event.event_type == "test_event"
        assert event.summary == "Test summary"
        assert event.data == {"key": "value"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
