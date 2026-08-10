from __future__ import annotations

import json

from backend.core.model_briefing import build_model_briefing, build_model_briefing_json


def test_model_briefing_preserves_stellaris_4_population_values_with_semantics() -> None:
    source = {
        "meta": {"version": "Pegasus v4.4.6"},
        "economy": {"pop_statistics": {"total_pops": 5436}},
    }

    result = build_model_briefing(source)

    assert result["economy"]["pop_statistics"]["total_pops"] == 5436
    assert "measured in the thousands" in result["model_context"]["population"]["scale"]
    assert "100 workforce" in result["model_context"]["population"]["workforce_rule"]
    assert "model_context" not in source


def test_model_briefing_explains_special_diplomatic_contacts() -> None:
    result = build_model_briefing(
        {
            "meta": {"version": "Pegasus v4.4.6"},
            "diplomacy": {
                "empire_count": 0,
                "relation_count": 1,
                "relations": [{"empire_name": "Privateers", "country_type": "pirate"}],
            },
        }
    )

    diplomacy = result["model_context"]["diplomacy"]
    assert diplomacy["ordinary_empire_country_type"] == "default"
    assert "pirates" in diplomacy["instruction"]


def test_model_briefing_json_falls_back_for_invalid_json() -> None:
    assert build_model_briefing_json("not-json") == "not-json"

    parsed = json.loads(build_model_briefing_json('{"meta":{"version":"Corvus v4.2.4"}}'))
    assert parsed["model_context"]["schema_version"] == 2


def test_model_briefing_adds_explicit_war_side_semantics_and_aliases() -> None:
    source = {
        "meta": {"version": "Pegasus v4.4.6"},
        "military": {
            "wars": {
                "wars": [
                    {
                        "our_side": "attacker",
                        "battle_stats": {
                            "total_battles": 35,
                            "our_victories": 25,
                            "their_victories": 10,
                            "unknown_outcomes": 0,
                            "our_ship_losses": 69,
                            "their_ship_losses": 258,
                        },
                    }
                ]
            }
        },
    }

    result = build_model_briefing(source)
    stats = result["military"]["wars"]["wars"][0]["battle_stats"]

    assert stats["player_involved_battles"] == 35
    assert stats["our_side_victories"] == 25
    assert stats["opposing_side_victories"] == 10
    assert stats["our_side_ship_losses"] == 69
    assert stats["opposing_side_ship_losses"] == 258
    assert (
        "not a complete measure" in result["model_context"]["military"]["wars"]["assessment_rule"]
    )
    assert "player_involved_battles" not in source["military"]["wars"]["wars"][0]["battle_stats"]
