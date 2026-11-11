from __future__ import annotations

import json
from copy import deepcopy

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
    assert parsed["model_context"]["schema_version"] == 3


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


def test_model_briefing_preserves_source_and_recomputes_legacy_evidence() -> None:
    source = {
        "meta": {
            "version": "Cygnus v4.5.2",
            "required_dlcs": ["Overlord"],
            "missing_dlcs": ["Synthetic Dawn", "Utopia"],
        },
        "identity": {
            "authority": "machine_intelligence",
            "civics": ["machine_servitor", "machine_replication", "modded_civic"],
        },
        "model_context": {
            "schema_version": 2,
            "content_availability": {"unreported_dlc_status": "unavailable"},
        },
    }
    original = deepcopy(source)

    result = build_model_briefing(source)
    context = result["model_context"]

    assert source == original
    assert result["meta"] == {
        key: value for key, value in original["meta"].items() if key != "missing_dlcs"
    }
    assert result["identity"] == original["identity"]
    assert context["content_availability"]["reported_dlcs"] == ["Overlord"]
    assert "Synthetic Dawn" in context["content_availability"]["base_game_dlcs"]
    assert context["content_availability"]["unreported_dlc_status"] == "unknown"
    assert context["empire_identity"]["authority"]["kind"] == "authority"
    assert context["empire_identity"]["civics"][0] == {
        "id": "machine_servitor",
        "name": "Rogue Servitor",
        "kind": "civic",
        "source": "verified_catalog",
    }
    assert context["empire_identity"]["civics"][2]["source"] == "raw_identifier"
    assert build_model_briefing(result) == result


def test_model_briefing_does_not_invent_dlc_absence_from_old_stored_meta() -> None:
    result = build_model_briefing({"meta": {"version": "4.2.4"}, "identity": {}})
    evidence = result["model_context"]["content_availability"]
    assert evidence["dlc_evidence_status"] == "not_recorded"
    assert evidence["reported_dlcs"] == []
    assert evidence["base_game_dlcs"] == []
    assert evidence["unreported_dlc_status"] == "unknown"


def test_model_briefing_names_technologies_without_touching_the_source() -> None:
    source = {
        "meta": {"version": "Cygnus v4.5.3"},
        "technology": {
            "completed_count": 3,
            "researched_techs": ["tech_colonization_1", "tech_my_mod_reactor", "tech_lasers_1"],
            "in_progress": {
                "physics": {"tech": "tech_lasers_2", "progress": 12.0},
                "society": None,
                "engineering": None,
            },
            "available_techs": {
                "physics": ["tech_cryostasis_1", "tech_other_mod_thing"],
                "society": [],
                "engineering": [],
            },
        },
    }
    original = deepcopy(source)

    result = build_model_briefing(source)

    assert source == original
    technology = result["technology"]
    # Researched technologies are renamed in place; uncatalogued IDs stay visible.
    assert technology["researched_techs"] == [
        "New Worlds Protocol",
        "tech_my_mod_reactor",
        "Red Lasers",
    ]
    assert technology["completed_count"] == 3
    # Current research and options keep their IDs and are named alongside.
    assert technology["in_progress"] == original["technology"]["in_progress"]
    assert technology["available_techs"] == original["technology"]["available_techs"]
    naming = result["model_context"]["technology"]
    assert naming["names"] == {
        "tech_lasers_2": "Blue Lasers",
        "tech_cryostasis_1": "Automated Colony Ships",
    }
    assert naming["also_shown_as"] == {
        "tech_lasers_2": ["Blue Beam Projector"],
        "tech_cryostasis_1": ["Seedling Incubation"],
    }
    assert "treat both as the same" in naming["variant_rule"]
    assert "Cygnus v4.5.3" in naming["names_source"]
    assert "catalog_note" not in naming


def test_model_briefing_says_when_the_save_is_newer_than_the_name_catalog() -> None:
    technology = {"available_techs": {"physics": ["tech_administrative_ai"]}}

    newer = build_model_briefing({"meta": {"version": "Next v99.0.0"}, "technology": technology})
    unknown = build_model_briefing({"meta": {}, "technology": technology})

    assert (
        "Next v99.0.0, newer than the name catalog"
        in (newer["model_context"]["technology"]["catalog_note"])
    )
    assert "catalog_note" not in unknown["model_context"]["technology"]
    assert "also_shown_as" not in unknown["model_context"]["technology"]


def test_model_briefing_omits_technology_naming_without_technologies() -> None:
    for technology in (None, {}, {"researched_techs": []}, {"error": "x"}):
        result = build_model_briefing({"meta": {}, "technology": technology})
        assert "technology" not in result["model_context"]
