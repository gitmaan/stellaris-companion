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
    assert parsed["model_context"]["schema_version"] == 1
