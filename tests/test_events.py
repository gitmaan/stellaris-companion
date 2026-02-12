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
    _get_leader_name,
    _is_placeholder_recruitment_date,
    _normalize_federation,
    _pct_change,
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
            "technology": {"techs": []},
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
            "technology": {"techs": []},
            "policies": {"policies": {}},
            "edicts": {"edicts": []},
            "megastructures": {"megastructures": []},
            "crisis": {"active": False, "type": None},
            "fallen_empires": {"fallen_empires": [], "war_in_heaven": False},
            "systems": {"system_count": 12},
        },
    }


# --- Tests for helper functions ---


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


class TestRecruitmentDateFiltering:
    """Tests for leader recruitment pool placeholder detection."""

    def test_detects_placeholder_year_zero_date(self):
        """Treats year-0 recruitment dates as unrecruited pool entries."""
        assert _is_placeholder_recruitment_date("0.01.01") is True

    def test_ignores_real_recruitment_dates(self):
        """Real recruited leaders should not be filtered out."""
        assert _is_placeholder_recruitment_date("2200.01.01") is False
        assert _is_placeholder_recruitment_date("2391.11.12") is False
        assert _is_placeholder_recruitment_date(None) is False


# --- Tests for compute_events ---


class TestComputeEvents:
    """Tests for the main compute_events function."""

    def test_detects_military_power_change(self, base_prev_snapshot, base_curr_snapshot):
        """Detects significant military power changes."""
        base_prev_snapshot["military"]["military_power"] = 10000
        base_curr_snapshot["military"]["military_power"] = 20000

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

    def test_ignores_recruitment_pool_leader_churn(
        self, base_prev_snapshot, base_curr_snapshot
    ):
        """Pool rerolls should not appear as hired/removed roster events."""
        base_prev_snapshot["history"]["leaders"]["leaders"] = [
            {"id": 100, "class": "scientist", "name": "Pool A", "recruitment_date": "0.01.01"}
        ]
        base_curr_snapshot["history"]["leaders"]["leaders"] = [
            {"id": 101, "class": "scientist", "name": "Pool B", "recruitment_date": "0.01.01"}
        ]

        result = compute_events(
            prev=base_prev_snapshot,
            curr=base_curr_snapshot,
            from_snapshot_id=1,
            to_snapshot_id=2,
        )
        event_types = [e.event_type for e in result]
        assert "leader_hired" not in event_types
        assert "leader_removed" not in event_types

    def test_tracks_real_hire_while_ignoring_pool_reroll(
        self, base_prev_snapshot, base_curr_snapshot
    ):
        """A real recruited leader still emits hire even if pool rerolls too."""
        base_prev_snapshot["history"]["leaders"]["leaders"] = [
            {"id": 100, "class": "scientist", "name": "Pool A", "recruitment_date": "0.01.01"},
            {
                "id": 200,
                "class": "commander",
                "name": "Veteran",
                "recruitment_date": "2230.05.20",
            },
        ]
        base_curr_snapshot["history"]["leaders"]["leaders"] = [
            {"id": 101, "class": "scientist", "name": "Pool B", "recruitment_date": "0.01.01"},
            {
                "id": 200,
                "class": "commander",
                "name": "Veteran",
                "recruitment_date": "2230.05.20",
            },
            {
                "id": 201,
                "class": "scientist",
                "name": "Dr. Nova",
                "recruitment_date": "2260.01.01",
            },
        ]

        result = compute_events(
            prev=base_prev_snapshot,
            curr=base_curr_snapshot,
            from_snapshot_id=1,
            to_snapshot_id=2,
        )
        event_types = [e.event_type for e in result]
        assert "leader_hired" in event_types
        assert "leader_removed" not in event_types

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
        base_prev_snapshot["history"]["technology"]["techs"] = ["tech_lasers_1"]
        base_curr_snapshot["history"]["technology"]["techs"] = ["tech_lasers_1", "tech_lasers_2"]

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
        colony_event = next((e for e in result if e.event_type == "colony_count_change"), None)
        assert colony_event is not None
        assert colony_event.data["from_snapshot_id"] == 42
        assert colony_event.data["to_snapshot_id"] == 43


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
