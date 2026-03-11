"""Focused tests for military extraction helpers."""

import os
import sys

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
        }

    def _resolve_system_name(self, system_id: int) -> str:
        return self._systems.get(system_id, f"System {system_id}")


def test_extract_battle_stats_counts_only_player_battles():
    extractor = DummyMilitaryExtractor()
    battles = [
        {
            "attackers": ["16777220"],
            "defenders": ["15"],
            "attacker_victory": "no",
            "attacker_losses": "25",
            "defender_losses": "0",
            "system": "1",
            "type": "ships",
        },
        {
            "attackers": ["0"],
            "defenders": ["15"],
            "attacker_victory": "yes",
            "attacker_losses": "1",
            "defender_losses": "10",
            "system": "2",
            "type": "ships",
        },
        {
            "attackers": ["15"],
            "defenders": ["0"],
            "attacker_victory": "yes",
            "attacker_losses": "3",
            "defender_losses": "7",
            "system": "3",
            "type": "armies",
        },
    ]

    stats = extractor._extract_battle_stats(battles, player_id=0)

    assert stats["total_battles"] == 2
    assert stats["our_victories"] == 1
    assert stats["their_victories"] == 1
    assert stats["our_ship_losses"] == 1
    assert stats["their_ship_losses"] == 10
    assert stats["our_army_losses"] == 7
    assert stats["their_army_losses"] == 3
    assert {loc["system"] for loc in stats["battle_locations"]} == {
        "Player Victory System",
        "Player Defense System",
    }


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

    stats = extractor._extract_battle_stats(battles, player_id=0)

    assert stats["total_battles"] == 1
    assert stats["our_victories"] == 1
    assert stats["our_ship_losses"] == 2
    assert stats["their_ship_losses"] == 9


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

        expected = {"total_battles": 0, "our_victories": 0, "their_victories": 0}
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
                attacker_victory = battle.get("attacker_victory") == "yes"
                if (player_was_attacker and attacker_victory) or (
                    player_was_defender and not attacker_victory
                ):
                    expected["our_victories"] += 1
                else:
                    expected["their_victories"] += 1

        expected_by_war.append(expected)

    with rust_session(test_save_path):
        extractor = SaveExtractor(test_save_path)
        wars = extractor.get_wars()

    assert wars["player_at_war"] is True
    assert wars["active_war_count"] == len(expected_by_war)

    actual_by_war = [
        {
            "total_battles": war["battle_stats"]["total_battles"],
            "our_victories": war["battle_stats"]["our_victories"],
            "their_victories": war["battle_stats"]["their_victories"],
        }
        for war in wars["wars"]
    ]
    assert (
        actual_by_war
        == expected_by_war
        == [{"total_battles": 0, "our_victories": 0, "their_victories": 0}]
    )
