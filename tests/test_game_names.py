"""Names come from the player's installed game: their version, language and mods.

These tests build a small game folder the way the game lays one out and read it
with the real reader, then check that every place the app names an ID prefers the
installed game and still works without one.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.core.briefing_names import briefing_value_name
from backend.core.model_briefing import build_model_briefing
from backend.mcp.context import _display_identifier
from stellaris_companion import game_install, game_names
from stellaris_companion.campaign_evidence import english_identity_names, resolve_empire_identity
from stellaris_companion.game_install import GameInstall, find_game_install
from stellaris_companion.game_names import GameNames, read_localisation
from stellaris_companion.technology_names import (
    names_source,
    technology_display_name,
    technology_variant_names,
)

ENGLISH = """l_english:
 # A comment line
 tech_cryostasis_1:0 "Deep Sleep Pods"
 tech_cryostasis_1_wilderness: "Seedling Beds"
 building_factory_3:0 "Civilian Repli-Complexes"
 building_foundry_2:1 "Alloy Mega-Forges" # trailing comment
 foundry_2:0 "Something Else Entirely"
 sm_crew_quarters:0 "Crew Quarters"
 pc_arid:0 "Arid World"
 arid:0 "Dry"
 ethic_xenophile:0 "Xenophile"
 civic_technocracy:0 "Technocracy"
 auth_democratic:0 "Democratic"
 origin_default:0 "Prosperous Unification"
 war_goal_wg_independence:0 "Independence"
 tr_discovery_adopt:0 "$tradition_discovery$ Traditions"
 tradition_discovery:0 "Discovery"
 r_core:0 "§YIsolated§! £energy£ Core"
 quoted:0 "The \\"Old\\" Guard"
 NAME_Barnard's_Star:0 "Barnard's Star"
 dynamic_name:0 "[Root.GetName] Station"
 broken_reference:0 "$never_defined$ Works"
 loop_a:0 "$loop_b$"
 loop_b:0 "$loop_a$"
 tech_cryostasis_1_desc:0 "Colonists sleep through the journey, which lets a colony ship carry far more of them than it could ever feed awake."
 FUN:0 "Fungoid"
"""

GERMAN = """l_german:
 tech_cryostasis_1:0 "Kälteschlafkapseln"
 building_factory_3:0 "Ziviler Replikator-Komplex"
 civic_technocracy:0 "Technokratie"
"""


def make_game(root: Path, version: str = "Test v9.9.9") -> Path:
    game = root / "Stellaris"
    (game / "common").mkdir(parents=True)
    english = game / "localisation" / "english"
    english.mkdir(parents=True)
    (english / "main_l_english.yml").write_text(ENGLISH, encoding="utf-8-sig")
    german = game / "localisation" / "german"
    german.mkdir()
    (german / "main_l_german.yml").write_text(GERMAN, encoding="utf-8-sig")
    (game / "launcher-settings.json").write_text(json.dumps({"version": version}))
    return game


def make_user_dir(
    root: Path, language: str = "english", mods: dict[str, str] | None = None
) -> Path:
    """A player's settings folder; ``mods`` maps a mod name to its English text."""
    user = root / "user" / "Stellaris"
    (user / "save games").mkdir(parents=True)
    (user / "mod").mkdir()
    (user / "settings.txt").write_text(f'language="l_{language}"\nautosave="monthly"\n')
    enabled = []
    for name, text in (mods or {}).items():
        folder = root / "workshop" / name
        (folder / "localisation").mkdir(parents=True)
        (folder / "localisation" / f"{name}_l_english.yml").write_text(text, encoding="utf-8-sig")
        (user / "mod" / f"{name}.mod").write_text(f'name="{name}"\npath="{folder.as_posix()}"\n')
        enabled.append(f"mod/{name}.mod")
    (user / "dlc_load.json").write_text(json.dumps({"enabled_mods": enabled, "disabled_dlcs": []}))
    return user


@pytest.fixture
def machine(tmp_path, monkeypatch):
    """Point the search at a game and a settings folder under ``tmp_path``."""

    def setup(language: str = "english", mods: dict[str, str] | None = None) -> GameInstall:
        game = make_game(tmp_path)
        user = make_user_dir(tmp_path, language, mods)
        monkeypatch.setenv("STELLARIS_GAME_DIR", str(game))
        monkeypatch.setenv("STELLARIS_SAVE_DIR", str(user / "save games"))
        install = find_game_install()
        assert install is not None
        return install

    return setup


@pytest.fixture
def installed(machine):
    """Answer name lookups from the test game, then go back to no install."""
    names = GameNames.from_install(machine())
    game_names.use_names(names)
    yield names
    game_names.use_names(None)


def test_the_install_is_found_with_its_version_language_and_mods(machine, tmp_path) -> None:
    install = machine("german", {"cool_mod": 'l_english:\n building_cool:0 "Cool Building"\n'})

    assert install.game_dir == tmp_path / "Stellaris"
    assert install.version == "Test v9.9.9"
    assert install.language == "german"
    assert install.mod_dirs == (tmp_path / "workshop" / "cool_mod",)


def test_a_steam_library_on_another_drive_is_searched(tmp_path, monkeypatch) -> None:
    steam = tmp_path / "Steam"
    library = tmp_path / "Games Drive" / "SteamLibrary"
    (steam / "steamapps").mkdir(parents=True)
    escaped = str(library).replace("\\", "\\\\")
    (steam / "steamapps" / "libraryfolders.vdf").write_text(
        f'"libraryfolders"\n{{\n\t"0"\n\t{{\n\t\t"path"\t\t"{escaped}"\n\t}}\n}}\n'
    )
    game = make_game(library / "steamapps" / "common")
    monkeypatch.delenv("STELLARIS_GAME_DIR", raising=False)
    monkeypatch.setattr(game_install, "_steam_roots", lambda: [steam])
    monkeypatch.setattr(game_install, "_save_dirs", lambda: [])

    assert find_game_install() == GameInstall(game_dir=game, version="Test v9.9.9")


def test_no_install_means_no_names_and_no_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("STELLARIS_GAME_DIR", "")
    assert find_game_install() is None
    monkeypatch.setenv("STELLARIS_GAME_DIR", str(tmp_path / "not-a-game"))
    assert find_game_install() is None


def test_a_file_is_read_for_the_language_its_name_and_first_line_say(tmp_path) -> None:
    game = make_game(tmp_path)
    folder = game / "localisation"
    # Right name, wrong header: the game ignores it, and so do we.
    (folder / "english" / "stray_l_english.yml").write_text('l_french:\n pc_arid:0 "Monde aride"\n')
    # A replace folder loads last and wins.
    (folder / "replace").mkdir()
    (folder / "replace" / "aaa_l_english.yml").write_text(
        'l_english:\n pc_arid:0 "Parched World"\n'
    )

    english = read_localisation(game, "english")
    german = read_localisation(game, "german")

    assert english["pc_arid"] == "Parched World"
    assert english["building_foundry_2"] == "Alloy Mega-Forges"
    assert english["NAME_Barnard's_Star"] == "Barnard's Star"
    assert "tech_cryostasis_1" in english and "A" not in english
    assert german == {
        "tech_cryostasis_1": "Kälteschlafkapseln",
        "building_factory_3": "Ziviler Replikator-Komplex",
        "civic_technocracy": "Technokratie",
    }


def test_names_are_resolved_and_cleaned_as_the_game_shows_them(installed) -> None:
    assert installed.name("tr_discovery_adopt") == "Discovery Traditions"
    assert installed.name("r_core") == "Isolated Core"
    assert installed.name("quoted") == 'The "Old" Guard'
    assert installed.source == "English text of the installed game, Test v9.9.9"


@pytest.mark.parametrize(
    "key",
    ["dynamic_name", "broken_reference", "loop_a", "tech_cryostasis_1_desc", "never_defined"],
)
def test_text_that_is_not_a_fixed_name_gives_no_name(installed, key) -> None:
    assert installed.name(key) is None


def test_an_enabled_mod_adds_and_renames(machine) -> None:
    install = machine(
        mods={
            "cool_mod": (
                'l_english:\n building_cool:0 "Cool Building"\n pc_arid:0 "Dustbowl"\n'
                ' tech_cool:0 "$building_cool$ Theory"\n'
            )
        }
    )
    names = GameNames.from_install(install)

    assert names.name("building_cool") == "Cool Building"
    assert names.name("tech_cool") == "Cool Building Theory"
    assert names.name("pc_arid") == "Dustbowl"
    assert names.name("building_factory_3") == "Civilian Repli-Complexes"


def test_technologies_are_named_by_the_installed_game_then_the_catalog(installed) -> None:
    # The installed game wins; the shipped catalog calls this Automated Colony Ships.
    assert technology_display_name("tech_cryostasis_1") == "Deep Sleep Pods"
    assert technology_variant_names("tech_cryostasis_1") == ("Seedling Beds",)
    # Not in this game's text: the catalog still knows it.
    assert technology_display_name("tech_lasers_1") == "Red Lasers"
    assert technology_display_name("tech_my_mod_reactor") is None
    assert names_source() == "English text of the installed game, Test v9.9.9"


def test_without_an_install_the_catalogs_name_everything_they_did_before() -> None:
    assert technology_display_name("tech_cryostasis_1") == "Automated Colony Ships"
    assert technology_variant_names("tech_cryostasis_1") == ("Seedling Incubation",)
    assert names_source().startswith("English game text, ")
    assert briefing_value_name("building_factory_3") is None
    assert _display_identifier("building_factory_3") == "Factory III"


def test_empire_identity_uses_the_players_language_and_keeps_english_for_knowledge(machine) -> None:
    game_names.use_names(GameNames.from_install(machine("german")))
    try:
        identity = {"civics": ["technocracy", "meritocracy"], "ethics": ["xenophile"]}
        typed = resolve_empire_identity(identity)
        english = english_identity_names(identity)
    finally:
        game_names.use_names(None)

    assert typed["civics"] == [
        {"id": "technocracy", "name": "Technokratie", "kind": "civic", "source": "installed_game"},
        {"id": "meritocracy", "name": "Meritocracy", "kind": "civic", "source": "verified_catalog"},
    ]
    assert english == ["Technocracy", "Meritocracy", "Xenophile"]


@pytest.mark.parametrize(
    ("section", "field", "value", "name"),
    [
        # The save's own ID is the game's text key.
        ("territory", "last_building", "building_factory_3", "Civilian Repli-Complexes"),
        ("progression", "traditions", "tr_discovery_adopt", "Discovery Traditions"),
        # A planet's buildings list drops "building_": looked up as a building, not as
        # whatever else is called foundry_2.
        ("territory", "buildings", "foundry_2", "Alloy Mega-Forges"),
        ("defense", "buildings", "crew_quarters", "Crew Quarters"),
        ("territory", "type", "arid", "Arid World"),
        ("diplomacy", "ethics", "xenophile", "Xenophile"),
        ("situation", "war_goal", "wg_independence", "Independence"),
        ("species", "class", "FUN", "Fungoid"),
    ],
)
def test_a_briefing_value_is_named_as_the_kind_of_thing_it_is(
    installed, section, field, value, name
) -> None:
    assert briefing_value_name(value, section, field) == name
    assert _display_identifier(value, section, field) == name


def test_ordinary_words_and_the_apps_own_terms_are_left_alone(installed) -> None:
    # "arid" is game text ("Dry"), but one bare word outside a listed field is not an ID.
    assert briefing_value_name("arid", "situation", "summary") is None
    assert _display_identifier("arid", "situation", "summary") == "arid"
    assert _display_identifier("FUN", "leadership", "name") == "FUN"
    # No game name: shown in readable words, as before.
    assert _display_identifier("under_construction", "military", "status") == "Under Construction"
    assert _display_identifier("war_started") == "War Started"


def test_the_advisor_is_told_the_names_are_the_players_own(installed) -> None:
    briefing = build_model_briefing(
        {
            "meta": {"version": "Test v9.9.9"},
            "technology": {
                "researched_techs": ["tech_cryostasis_1"],
                "available_techs": {"physics": ["tech_cryostasis_1"]},
            },
        }
    )
    naming = briefing["model_context"]["technology"]

    assert briefing["technology"]["researched_techs"] == ["Deep Sleep Pods"]
    assert naming["names"] == {"tech_cryostasis_1": "Deep Sleep Pods"}
    assert naming["names_source"] == "English text of the installed game, Test v9.9.9"
    assert "exactly as written" in naming["instruction"]
    assert "catalog_note" not in naming


def test_changing_the_games_language_is_picked_up_while_the_app_runs(
    machine, tmp_path, monkeypatch
) -> None:
    machine("english")
    monkeypatch.setattr(game_names, "RECHECK_SECONDS", 0.0)
    game_names.use_installed_game()
    try:
        assert game_names.game_name("building_factory_3") == "Civilian Repli-Complexes"
        settings = tmp_path / "user" / "Stellaris" / "settings.txt"
        settings.write_text('language="l_german"\n')
        assert game_names.game_name("building_factory_3") == "Ziviler Replikator-Komplex"
    finally:
        game_names.use_names(None)
