"""Nomad empires read as settled empires (#79)."""

from __future__ import annotations

from ._synthetic import advisor_request, country, ingest_synthetic_save, synthetic_meta, system


def nomad_sections() -> dict:
    """A Voidfarer empire: one Arkship, one Waystation and one Logistic Ship.

    Layouts follow real 4.4 saves (colony carriers, situations, starbase_mgr,
    owned fleets, ship designs); Nomad keys follow the game's definitions.
    """
    return {
        "player": [{"name": "Reporter", "country": "0"}],
        "country": {
            "0": country(
                "Barcalan Collective",
                controlled_colonies=[7],
                fleets_manager={"owned_fleets": [{"fleet": "10"}, {"fleet": "11"}]},
                modules={
                    "standard_economy_module": {"resources": {"energy": "40", "minerals": "0"}}
                },
                # As reported: Mineral upkeep with no Mineral production entry.
                budget={
                    "current_month": {
                        "income": {"country_base": {"energy": "12"}},
                        "expenses": {"ship_upkeep": {"minerals": "35", "energy": "20"}},
                    }
                },
            )
        },
        "colony": {"7": {"carrier": {"type": "ship", "reference": 900}, "planet_class": "pc_ark"}},
        "planets": {"planet": {}},
        "fleet": {"10": {"ships": [900, 902]}, "11": {"ships": [901]}},
        "ships": {
            "900": {
                "name": {"key": "Wandering Hearth", "literal": "yes"},
                "fleet": "10",
                "coordinate": {"origin": "5"},
                "ship_design_implementation": {"design": "50"},
            },
            "901": {
                "fleet": "11",
                "coordinate": {"origin": "6"},
                "ship_design_implementation": {"design": "51"},
                "resources": {"minerals": "420", "energy": "130.5"},
            },
            "902": {
                "fleet": "10",
                "coordinate": {"origin": "4294967295"},
                "ship_design_implementation": {"design": "52"},
                "resources": [["minerals", "300"]],
            },
        },
        "ship_design": {
            "50": {"growth_stages": [{"ship_size": "civilian_arkship_tier_2"}]},
            "51": {"growth_stages": [{"ship_size": "starbase_waystation_1"}]},
            "52": {"growth_stages": [{"ship_size": "nomads_constructor"}]},
        },
        "starbase_mgr": {
            "starbases": {"30": {"level": "starbase_level_waystation_1", "station": "901"}}
        },
        "situations": {
            "situations": {
                "0": {
                    "type": "situation_nomad_economy",
                    "country": "0",
                    "progress": "8450.5",
                    "last_month_progress": "-62.25",
                    "approach": "situation_nomad_economy_smooth_spending",
                    "stage": "2",
                }
            }
        },
        "galactic_object": {"5": system("Tau Ceti"), "6": system("Kepler")},
    }


def test_issue_79_nomad_economy_is_read_as_operational_reserves(monkeypatch, tmp_path):
    """https://github.com/gitmaan/stellaris-companion/issues/79

    A Nomad empire showed negative Minerals with no production entry. The
    Advisor treated it as a failing settled mining economy because nothing
    marked the empire as Nomadic or described reserves and the stockpile chain.
    """
    payload = ingest_synthetic_save(
        monkeypatch,
        tmp_path,
        nomad_sections(),
        meta=synthetic_meta(name="Barcalan Collective", date="2310.01.01", version="Cygnus v4.5.2"),
    )
    _, system_prompt, briefing = advisor_request(
        monkeypatch, payload, "Should I worry about my mineral income?"
    )

    assert briefing["identity"]["is_nomadic"] is True
    nomad = briefing["nomad"]
    assert nomad["detected_by"] == ["arkship_colony", "operational_reserves_situation"]
    assert nomad["operational_reserves"] == {
        "current": 8450.5,
        "monthly_change": -62.25,
        "stage": "medium",
        "approach": "balance",
    }
    assert nomad["arkships"] == [
        {"name": "Wandering Hearth", "role": "civilian", "tier": 2, "system": "Tau Ceti"}
    ]
    assert nomad["waystations"]["count"] == 1
    assert nomad["waystations"]["stockpile_total"] == {"minerals": 420.0, "energy": 130.5}
    assert nomad["waystations"]["stations"][0]["system"] == "Kepler"
    assert nomad["logistic_ships"] == {"count": 1, "cargo_total": {"minerals": 300.0}}

    rules = briefing["model_context"]["nomad_economy"]
    assert "one point equals one Mineral or one Energy Credit" in rules["operational_reserves"]
    assert "never diagnose failing mining" in rules["monthly_lines"]
    # The question never says "Nomad", yet the maintained Nomad economy mechanics
    # are retrieved alongside the always-on briefing rules.
    assert "### Operational Reserves and Arkship Economy" in system_prompt


def test_settled_empires_get_no_nomad_rules(monkeypatch, tmp_path):
    sections = nomad_sections()
    sections["colony"] = {"7": {"carrier": {"type": "planet", "reference": 24}}}
    sections["planets"] = {"planet": {"24": {"name": "Barcal", "planet_class": "pc_ocean"}}}
    sections["situations"] = {"situations": {}}
    payload = ingest_synthetic_save(monkeypatch, tmp_path, sections)
    _, _, briefing = advisor_request(monkeypatch, payload, "How is my mineral income?")

    assert briefing["identity"]["is_nomadic"] is False
    assert "nomad" not in briefing
    assert "nomad_economy" not in briefing["model_context"]
