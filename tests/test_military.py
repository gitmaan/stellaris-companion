"""Focused tests for military extraction helpers."""

import json
import os
import sys
from pathlib import Path

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stellaris_save_extractor.military import MilitaryMixin


class DummyMilitaryExtractor(MilitaryMixin):
    """Minimal test double for MilitaryMixin helpers."""

    def __init__(self):
        self._systems = {
            1: "Ignored System",
            2: "Player Victory System",
            3: "Player Defense System",
            4: "Unknown Outcome System",
        }

    def _resolve_system_name(self, system_id: int) -> str:
        return self._systems.get(system_id, f"System {system_id}")


def test_extract_battle_stats_uses_parent_war_side_fixture():
    extractor = DummyMilitaryExtractor()
    fixture_path = Path(__file__).parent / "fixtures" / "player_war_attacker_battles.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    stats = extractor._extract_battle_stats(
        fixture["battles"],
        player_id=fixture["player_id"],
        player_is_war_attacker=fixture["player_is_war_attacker"],
    )

    for key, expected in fixture["expected"].items():
        assert stats[key] == expected
    assert {loc["system"] for loc in stats["battle_locations"]} == {
        "Unknown Outcome System",
        "Player Defense System",
        "Player Victory System",
    }


@pytest.mark.parametrize(
    (
        "player_is_war_attacker",
        "local_player_side",
        "attacker_victory",
        "expected_our_victories",
        "expected_their_victories",
        "expected_our_losses",
        "expected_their_losses",
    ),
    [
        (True, "defenders", "yes", 1, 0, 2, 9),
        (True, "attackers", "no", 0, 1, 2, 9),
        (False, "attackers", "yes", 0, 1, 9, 2),
        (False, "defenders", "no", 1, 0, 9, 2),
    ],
)
def test_extract_battle_stats_outcome_matrix_uses_parent_war_side(
    player_is_war_attacker,
    local_player_side,
    attacker_victory,
    expected_our_victories,
    expected_their_victories,
    expected_our_losses,
    expected_their_losses,
):
    extractor = DummyMilitaryExtractor()
    battle = {
        "attackers": ["0"] if local_player_side == "attackers" else ["15"],
        "defenders": ["0"] if local_player_side == "defenders" else ["15"],
        "attacker_victory": attacker_victory,
        "attacker_losses": "2",
        "defender_losses": "9",
        "system": "2",
        "type": "ships",
    }

    stats = extractor._extract_battle_stats(
        [battle],
        player_id=0,
        player_is_war_attacker=player_is_war_attacker,
    )

    assert stats["total_battles"] == 1
    assert stats["our_victories"] == expected_our_victories
    assert stats["their_victories"] == expected_their_victories
    assert stats["unknown_outcomes"] == 0
    assert stats["our_ship_losses"] == expected_our_losses
    assert stats["their_ship_losses"] == expected_their_losses


def test_extract_battle_stats_accepts_dict_participants():
    extractor = DummyMilitaryExtractor()
    battles = [
        {
            "attackers": [{"country": "0"}],
            "defenders": [{"country": "15"}],
            "attacker_victory": "yes",
            "attacker_losses": "2",
            "defender_losses": "9",
            "system": "2",
            "type": "ships",
        },
    ]

    stats = extractor._extract_battle_stats(
        battles,
        player_id=0,
        player_is_war_attacker=True,
    )

    assert stats["total_battles"] == 1
    assert stats["our_victories"] == 1
    assert stats["our_ship_losses"] == 2
    assert stats["their_ship_losses"] == 9


def test_summarize_war_control_includes_capital_and_system_evidence():
    summary = DummyMilitaryExtractor._summarize_war_control(
        lost_control_records=[
            {
                "owner_id": "15",
                "controller_id": "0",
                "fleet_id": "100",
                "system_id": "9",
                "system_name": "Enemy Prime",
            },
            {
                "owner_id": "16",
                "controller_id": "1",
                "fleet_id": "101",
                "system_id": "10",
                "system_name": "Allied Advance",
            },
            {
                "owner_id": "0",
                "controller_id": "15",
                "fleet_id": "102",
                "system_id": "12",
                "system_name": "Sol",
            },
        ],
        capital_control={
            "0": {"controller_id": "0", "system_id": "12", "capital_name": "Earth"},
            "15": {"controller_id": "0", "system_id": "9", "capital_name": "Enemy Prime"},
            "16": {"controller_id": "16", "system_id": "10", "capital_name": "Second Prime"},
        },
        our_side_ids={"0", "1"},
        opposing_side_ids={"15", "16"},
        player_id="0",
        country_names={0: "Player", 1: "Ally", 15: "Enemy", 16: "Second Enemy"},
    )

    assert summary["enemy_starbase_assets_controlled_by_our_side"] == 2
    assert summary["enemy_assets_controlled_by_player"] == 1
    assert {entry["system_id"] for entry in summary["enemy_systems_controlled_by_our_side"]} == {
        "9",
        "10",
    }
    assert [
        entry["empire"] for entry in summary["enemy_capital_colonies_occupied_by_our_side"]
    ] == ["Enemy"]
    assert {
        entry["empire"] for entry in summary["enemy_capital_systems_controlled_by_our_side"]
    } == {"Enemy", "Second Enemy"}
    assert summary["our_starbase_assets_controlled_by_enemy_side"] == 1
    assert summary["player_capital_colony_occupied_by_enemy_side"] is False
    assert summary["player_capital_system_controlled_by_enemy_side"] is True


def test_battle_diagnostic_record_exposes_raw_and_parent_side_calculation():
    extractor = DummyMilitaryExtractor()
    battle = {
        "attackers": ["15"],
        "defenders": ["0"],
        "attacker_victory": "yes",
        "attacker_losses": "1",
        "defender_losses": "15",
        "system": "2",
        "type": "ships",
    }

    diagnostic = extractor._build_battle_diagnostic_record(
        battle,
        local_attackers={"15"},
        local_defenders={"0"},
        player_is_war_attacker=True,
    )

    assert diagnostic == {
        "local_attacker_country_ids": ["15"],
        "local_defender_country_ids": ["0"],
        "raw_attacker_victory": "yes",
        "raw_attacker_losses": 1,
        "raw_defender_losses": 15,
        "battle_type": "ships",
        "system_id": "2",
        "computed_result": "our_side_victory",
        "computed_our_side_losses": 1,
        "computed_opposing_side_losses": 15,
    }


def test_classify_megastructure_status_uses_live_state_not_stage_suffix():
    extractor = DummyMilitaryExtractor()

    assert (
        extractor._classify_megastructure_status(
            {"build_queue": "4294967295"},
            "grand_archive_0",
        )
        == "complete"
    )
    assert (
        extractor._classify_megastructure_status(
            {"build_queue": "4294967295"},
            "strategic_coordination_center_1",
        )
        == "complete"
    )
    assert (
        extractor._classify_megastructure_status(
            {"build_queue": "17753"},
            "mega_shipyard_3",
        )
        == "under_construction"
    )
    assert (
        extractor._classify_megastructure_status(
            {
                "build_queue": "4294967295",
                "upgrade": {
                    "halted": "0",
                    "indefinitely_halted": "no",
                    "progress": "488",
                    "upgrade_to": "interstellar_assembly_4",
                },
            },
            "interstellar_assembly_3",
        )
        == "under_construction"
    )
    assert extractor._normalize_megastructure_display_type("grand_archive_0") == "grand_archive"


def test_completed_dyson_swarm_final_stage_is_complete():
    extractor = DummyMilitaryExtractor()

    assert (
        extractor._classify_megastructure_status(
            {"build_queue": "4294967295"},
            "dyson_swarm_3",
        )
        == "complete"
    )


def test_dyson_swarm_upgrading_to_sphere_is_under_construction():
    extractor = DummyMilitaryExtractor()

    assert (
        extractor._classify_megastructure_status(
            {
                "build_queue": "4294967295",
                "upgrade": {
                    "halted": "0",
                    "indefinitely_halted": "no",
                    "progress": "488",
                    "upgrade_to": "dyson_sphere_2",
                },
            },
            "dyson_swarm_3",
        )
        == "under_construction"
    )


@pytest.mark.integration
def test_real_save_battle_stats_match_raw_player_participation(test_save_path):
    from stellaris_companion.rust_bridge import (
        extract_sections,
        iter_section_entries,
    )
    from stellaris_companion.rust_bridge import (
        session as rust_session,
    )
    from stellaris_save_extractor import SaveExtractor

    player_id = str(extract_sections(test_save_path, ["player"])["player"][0]["country"])
    expected_by_war: list[dict[str, int]] = []

    for _, war in iter_section_entries(test_save_path, "war"):
        if not isinstance(war, dict):
            continue

        attackers = {
            str(a.get("country"))
            for a in war.get("attackers", [])
            if isinstance(a, dict) and a.get("country") is not None
        }
        defenders = {
            str(d.get("country"))
            for d in war.get("defenders", [])
            if isinstance(d, dict) and d.get("country") is not None
        }
        if player_id not in attackers and player_id not in defenders:
            continue

        player_is_war_attacker = player_id in attackers
        expected = {
            "total_battles": 0,
            "our_victories": 0,
            "their_victories": 0,
            "unknown_outcomes": 0,
        }
        battles = war.get("battles", [])
        if isinstance(battles, list):
            for battle in battles:
                if not isinstance(battle, dict):
                    continue

                battle_attackers = {str(x) for x in battle.get("attackers", []) if x is not None}
                battle_defenders = {str(x) for x in battle.get("defenders", []) if x is not None}
                player_was_attacker = player_id in battle_attackers
                player_was_defender = player_id in battle_defenders

                if not player_was_attacker and not player_was_defender:
                    continue

                expected["total_battles"] += 1
                attacker_victory = battle.get("attacker_victory")
                if attacker_victory not in {"yes", "no"}:
                    expected["unknown_outcomes"] += 1
                elif (attacker_victory == "yes") == player_is_war_attacker:
                    expected["our_victories"] += 1
                else:
                    expected["their_victories"] += 1

        expected_by_war.append(expected)

    with rust_session(test_save_path):
        extractor = SaveExtractor(test_save_path)
        wars = extractor.get_wars()
        diagnostics = extractor.get_war_diagnostics()

    assert wars["player_at_war"] is True
    assert wars["active_war_count"] == len(expected_by_war)
    assert diagnostics["schema_version"] == 2
    assert diagnostics["result_orientation"] == "parent_war_side"
    assert diagnostics["included_battles"] == 0
    assert diagnostics["wars"][0]["direct_battle_count"] == 0

    actual_by_war = [
        {
            "total_battles": war["battle_stats"]["total_battles"],
            "our_victories": war["battle_stats"]["our_victories"],
            "their_victories": war["battle_stats"]["their_victories"],
            "unknown_outcomes": war["battle_stats"]["unknown_outcomes"],
        }
        for war in wars["wars"]
    ]
    assert (
        actual_by_war
        == expected_by_war
        == [
            {
                "total_battles": 0,
                "our_victories": 0,
                "their_victories": 0,
                "unknown_outcomes": 0,
            }
        ]
    )
