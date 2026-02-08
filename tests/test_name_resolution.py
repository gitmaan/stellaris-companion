from __future__ import annotations

from stellaris_save_extractor.name_resolution import resolve_name


def test_resolve_localization_prefixes() -> None:
    assert resolve_name("NAME_Earth").display == "Earth"
    assert resolve_name("SPEC_Human").display == "Human"
    assert resolve_name("ADJ_Human").display == "Human"
    assert resolve_name("PRESCRIPTED_species_name_humans1").display == "Humans 1"


def test_resolve_special_empire_keys() -> None:
    assert resolve_name("FALLEN_EMPIRE_SPIRITUALIST").display == "Fallen Empire (Spiritualist)"
    assert resolve_name("AWAKENED_EMPIRE_1").display == "Awakened Empire 1"
    assert resolve_name("EMPIRE_DESIGN_humans1").display == "Humans 1"


def test_resolve_formatting_edge_cases() -> None:
    # Avoid 1St Fleet from naive .title()
    assert resolve_name("1ST_FLEET").display == "1st Fleet"
    assert resolve_name("Sol_III").display == "Sol III"
    assert resolve_name("ROBOT").display == "Robot"


def test_resolve_planet_templates() -> None:
    assert (
        resolve_name(
            {
                "key": "NEW_COLONY_NAME_1",
                "variables": [{"key": "NAME", "value": {"key": "NAME_Alpha_Centauri"}}],
            },
            context="planet",
        ).display
        == "Alpha Centauri 1"
    )

    assert (
        resolve_name(
            {
                "key": "PLANET_NAME_FORMAT",
                "variables": [
                    {"key": "PARENT", "value": {"key": "NAME_Seyyama"}},
                    {"key": "NUMERAL", "value": {"key": "I"}},
                ],
            },
            context="planet",
        ).display
        == "Seyyama I"
    )

    assert (
        resolve_name(
            {
                "key": "HABITAT_PLANET_NAME",
                "variables": [
                    {
                        "key": "FROM.from.solar_system.GetName",
                        "value": {"key": "Omicron_Persei"},
                    }
                ],
            },
            context="planet",
        ).display
        == "Omicron Persei Habitat"
    )
