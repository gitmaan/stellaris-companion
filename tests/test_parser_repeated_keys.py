"""The parser must return everything the save text contains.

Clausewitz writes a list as the same key repeated in one block. A parser that keeps
one value per key reports an empire with two ethics as having one, twelve special
projects as one, and so on, and nothing downstream can tell. These tests read a
small save, written the way the game writes them, with the real parser and compare
the result with an independent reader of the same text.
"""

from __future__ import annotations

import zipfile

import pytest

from stellaris_save_extractor.clausewitz_reference import Repeated, differences, parse
from stellaris_save_extractor.fleet_classification import classify_owned_fleet
from stellaris_save_extractor.save_values import is_yes, repeated

GAMESTATE = """version="Cygnus v4.5.3"
date="2230.07.01"
player=
{
\t
\t{
\t\tname="tester"
\t\tcountry=0
\t}
}
species_db=
{
\t1=
\t{
\t\tname=
\t\t{
\t\t\tkey="Fédération 星海"
\t\t\tliteral=yes
\t\t}
\t\tclass="HUM"
\t\tportrait="human"
\t\ttraits=
\t\t{
\t\t\ttrait="trait_organic"
\t\t\ttrait="trait_adaptive"
\t\t\ttrait="trait_nomadic"
\t\t}
\t}
}
fleet=
{
\t7=
\t{
\t\tname=
\t\t{
\t\t\tkey="Sol Starbase"
\t\t}
\t\tstation=yes
\t\tships=
\t\t{
\t\t\t70 71
\t\t}
\t\tstation=yes
\t\tmilitary_power=2500
\t}
}
planets=
{
\tplanet=
\t{
\t\t3=
\t\t{
\t\t\tplanet_modifier="pm_weak_magnetic_field"
\t\t\tplanet_modifier="pm_mineral_rich"
\t\t\tempty_slots=
\t\t\t{
\t\t\t\t
\t\t\t\t{
\t\t\t\t}
\t\t\t\t{
\t\t\t\t}
\t\t\t}
\t\t}
\t}
}
country=
{
\t0=
\t{
\t\tname=
\t\t{
\t\t\tkey="Ilse Krüger's Commonwealth"
\t\t\tliteral=yes
\t\t}
\t\tethos=
\t\t{
\t\t\tethic="ethic_fanatic_egalitarian"
\t\t\tethic="ethic_xenophile"
\t\t}
\t\ttech_status=
\t\t{
\t\t\ttechnology="tech_lasers_1"
\t\t\tlevel=1
\t\t\ttechnology="tech_repeatable_lcluster_clue"
\t\t\tlevel=4
\t\t\tphysics_queue=
\t\t\t{
\t\t\t\t
\t\t\t\t{
\t\t\t\t\tprogress=12.5
\t\t\t\t\ttechnology="tech_lasers_2"
\t\t\t\t}
\t\t\t}
\t\t}
\t\tevents=
\t\t{
\t\t\tspecial_project=
\t\t\t{
\t\t\t\tid=50
\t\t\t\tdays_left=509
\t\t\t}
\t\t\tspecial_project=
\t\t\t{
\t\t\t\tid=61
\t\t\t\tdays_left=1149
\t\t\t}
\t\t\tcompleted_event_chain="first_chain"
\t\t\tcompleted_event_chain="second_chain"
\t\t}
\t\trelations_manager=
\t\t{
\t\t\trelation=
\t\t\t{
\t\t\t\towner=0
\t\t\t\tcountry=1
\t\t\t\trelation_current=-20
\t\t\t\tmodifier=
\t\t\t\t{
\t\t\t\t\tmodifier="opinion_first"
\t\t\t\t\tvalue=10
\t\t\t\t}
\t\t\t\tmodifier=
\t\t\t\t{
\t\t\t\t\tmodifier="opinion_second"
\t\t\t\t\tvalue=-30
\t\t\t\t}
\t\t\t}
\t\t\trelation=
\t\t\t{
\t\t\t\towner=0
\t\t\t\tcountry=2
\t\t\t\trelation_current=88
\t\t\t\tmigration_access=yes
\t\t\t}
\t\t}
\t}
\t1=
\t{
\t\ttype="fallen_empire"
\t\tname=
\t\t{
\t\t\tkey="Ancient Ones"
\t\t\tliteral=yes
\t\t}
\t\tethos=
\t\t{
\t\t\tethic="ethic_fanatic_xenophobe"
\t\t}
\t\tmilitary_power=90000
\t\trelations_manager=
\t\t{
\t\t\trelation=
\t\t\t{
\t\t\t\towner=1
\t\t\t\tcountry=5
\t\t\t\trelation_current=3
\t\t\t}
\t\t\trelation=
\t\t\t{
\t\t\t\towner=1
\t\t\t\tcountry=0
\t\t\t\trelation_current=-40
\t\t\t}
\t\t}
\t}
}
"""


@pytest.fixture(scope="module")
def save_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("save") / "repeated.sav"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("gamestate", GAMESTATE.encode("utf-8"))
        archive.writestr("meta", 'version="Cygnus v4.5.3"\nname="Krüger"\n'.encode())
    return path


@pytest.fixture(scope="module")
def parsed(save_path):
    rust_bridge = pytest.importorskip("stellaris_companion.rust_bridge")
    sections = list(parse(GAMESTATE))
    with rust_bridge.session(save_path) as active:
        result = active.extract_sections(sections)
        result["_iter_country"] = dict(active.iter_section("country"))
        result["_entry"] = active.get_entry("country", "0")
        result["_meta"] = active.extract_sections(["meta"]).get("meta")
    return result


def test_the_parser_returns_everything_the_save_text_contains(parsed):
    expected = parse(GAMESTATE)
    problems = [
        line
        for section, value in expected.items()
        for line in differences(value, parsed.get(section), section)
    ]
    assert problems == []


def test_a_repeated_key_is_a_list_in_save_order(parsed):
    country = parsed["country"]["0"]
    assert country["ethos"]["ethic"] == ["ethic_fanatic_egalitarian", "ethic_xenophile"]
    assert [p["days_left"] for p in country["events"]["special_project"]] == ["509", "1149"]
    relations = country["relations_manager"]["relation"]
    assert [r["country"] for r in relations] == ["1", "2"]
    assert [m["modifier"] for m in relations[0]["modifier"]] == ["opinion_first", "opinion_second"]
    assert parsed["planets"]["planet"]["3"]["planet_modifier"] == [
        "pm_weak_magnetic_field",
        "pm_mineral_rich",
    ]


def test_a_key_written_once_keeps_its_value(parsed):
    assert parsed["country"]["1"]["ethos"]["ethic"] == "ethic_fanatic_xenophobe"
    assert parsed["fleet"]["7"]["ships"] == ["70", "71"]
    assert parsed["country"]["0"]["relations_manager"]["relation"][1]["migration_access"] == "yes"


def test_every_way_of_reading_an_entry_agrees(parsed):
    assert parsed["_entry"] == parsed["country"]["0"]
    assert parsed["_iter_country"]["0"] == parsed["country"]["0"]


def test_names_are_read_as_utf8(parsed):
    assert parsed["country"]["0"]["name"]["key"] == "Ilse Krüger's Commonwealth"
    assert parsed["species_db"]["1"]["name"]["key"] == "Fédération 星海"
    assert parsed["_meta"]["name"] == "Krüger"


def test_a_species_portrait_is_not_one_of_its_traits(save_path):
    rust_bridge = pytest.importorskip("stellaris_companion.rust_bridge")
    with rust_bridge.session(save_path) as active:
        scoped = active.get_duplicate_values("species_db", "1", "trait", within="traits")
    assert scoped == ["trait_organic", "trait_adaptive", "trait_nomadic"]


@pytest.fixture(scope="module")
def extractor(save_path):
    rust_bridge = pytest.importorskip("stellaris_companion.rust_bridge")
    from stellaris_save_extractor import SaveExtractor

    with rust_bridge.session(save_path):
        yield SaveExtractor(str(save_path))


def test_an_empire_keeps_all_its_ethics(extractor):
    assert extractor.get_empire_identity()["ethics"] == ["fanatic_egalitarian", "xenophile"]
    assert extractor._get_country_ethics_map() == {
        0: ["fanatic_egalitarian", "xenophile"],
        1: ["fanatic_xenophobe"],
    }


def test_every_active_special_project_is_counted(extractor):
    projects = extractor.get_special_projects()
    assert projects["active_count"] == 2
    assert projects["soonest_completion"] == 509
    assert projects["completed_chains"] == ["first_chain", "second_chain"]


def test_a_fallen_empires_opinion_of_the_player_is_read(extractor):
    (fallen,) = extractor.get_fallen_empires()["fallen_empires"]
    assert fallen["opinion_of_player"] == -40


def test_lgate_insights_come_from_the_repeatable_technology_level(extractor):
    assert extractor.get_lgate_status()["insights_collected"] == 4


def test_species_traits_do_not_include_the_portrait(extractor):
    (species,) = extractor.get_species_full()["species"]
    assert species["traits"] == ["trait_organic", "trait_adaptive", "trait_nomadic"]
    assert species["name"] == "Fédération 星海"


def test_a_flag_the_game_writes_twice_is_still_set(parsed):
    fleet = parsed["fleet"]["7"]
    assert fleet["station"] == ["yes", "yes"]
    assert is_yes(fleet["station"])
    assert classify_owned_fleet(fleet) == "starbase"


def test_repeated_and_is_yes_accept_either_shape():
    assert repeated(None) == []
    assert repeated("one") == ["one"]
    assert repeated(["one", "two"]) == ["one", "two"]
    assert is_yes("yes") and is_yes(["no", "yes"])
    assert not is_yes(None) and not is_yes("no") and not is_yes(["no"])


def test_the_reference_reader_marks_repeated_keys():
    tree = parse('a={ k="x" k="y" once=1 list={ 1 2 } } b={ c>=3 }')
    assert isinstance(tree["a"]["k"], Repeated)
    assert tree["a"]["k"] == ["x", "y"]
    assert tree["a"]["once"] == "1"
    assert tree["a"]["list"] == ["1", "2"]
    assert tree["b"]["c"] == "3"


def test_the_reference_reader_reports_a_dropped_value():
    tree = parse('a={ k="x" k="y" name="Krüger" }')
    assert differences(tree, {"a": {"k": ["x", "y"], "name": "Krüger"}}) == []
    assert differences(tree, {"a": {"k": "y", "name": "Krüger"}}) == [
        "/a/k: save repeats this key 2 times, parser has str"
    ]
    assert differences(tree, {"a": {"k": ["x", "y"], "name": "KrÃ¼ger"}}) == [
        "/a/name: save has 'Krüger', parser has 'KrÃ¼ger'"
    ]
