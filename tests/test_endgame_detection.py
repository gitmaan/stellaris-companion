"""Crises, the Great Khan, the War in Heaven, the L-Cluster, guardians and space
fauna are read from the names the game itself writes: country types and global flags.

The earlier detection searched the whole save for words. Several of those words do
not exist in the game, so the Prethoryn Scourge and the Contingency were never
reported, and others matched something else, so the Khan was reported dead after
his first defeat.
"""

from __future__ import annotations

import zipfile

import pytest

from stellaris_save_extractor import game_vocabulary


def _save(tmp_path, *, flags=(), countries=()):
    """A minimal save with the given global flags and (type, name key) countries."""
    lines = ['version="Cygnus v4.5.3"', 'date="2400.01.01"']
    lines += ["player=", "{", "\t", "\t{", '\t\tname="tester"', "\t\tcountry=0", "\t}", "}"]
    lines += ["flags=", "{"] + [f"\t{flag}=62808000" for flag in flags] + ["}"]
    lines += ["country=", "{", "\t0=", "\t{", '\t\ttype="default"', "\t\tcrisis_kills=12", "\t}"]
    for index, (country_type, name_key, *fleets) in enumerate(countries, start=1):
        lines += [f"\t{index}=", "\t{", f'\t\ttype="{country_type}"']
        lines += ["\t\tname=", "\t\t{", f'\t\t\tkey="{name_key}"', "\t\t}"]
        lines += ["\t\tfleets_manager=", "\t\t{", "\t\t\towned_fleets=", "\t\t\t{"]
        for fleet in range(fleets[0] if fleets else 0):
            lines += ["\t\t\t\t", "\t\t\t\t{", f"\t\t\t\t\tfleet={index * 100 + fleet}"]
            lines += ["\t\t\t\t}"]
        lines += ["\t\t\t}", "\t\t}", "\t}"]
    lines += ["}", ""]
    path = tmp_path / "endgame.sav"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("gamestate", "\n".join(lines).encode("utf-8"))
        archive.writestr("meta", b'version="Cygnus v4.5.3"\nname="tester"\n')
    return path


@pytest.fixture
def read(tmp_path):
    rust_bridge = pytest.importorskip("stellaris_companion.rust_bridge")
    from stellaris_save_extractor import SaveExtractor

    def _read(method, **save):
        path = _save(tmp_path, **save)
        with rust_bridge.session(path):
            return getattr(SaveExtractor(str(path)), method)()

    return _read


def test_the_prethoryn_scourge_is_a_crisis(read):
    crisis = read(
        "get_crisis_status",
        flags=["prethoryn_invasion_happened", "ongoing_prethoryn_invasion"],
        countries=[("swarm", "NAME_Prethoryn_Scourge"), ("tiyanki", "NAME_Placid_Leviathans")],
    )
    assert crisis["crisis_active"] is True
    assert crisis["crisis_type"] == "prethoryn"
    assert crisis["crisis_countries"] == [{"country_id": 1, "type": "prethoryn"}]
    assert crisis["player_crisis_kills"] == 12


def test_the_contingency_is_a_crisis(read):
    crisis = read(
        "get_crisis_status",
        flags=["ai_invasion_happened", "ai_invasion_ongoing"],
        countries=[("ai_empire", "NAME_Contingency")],
    )
    assert (crisis["crisis_active"], crisis["crisis_type"]) == (True, "contingency")


def test_a_crisis_announced_by_its_flag_counts_before_its_fleets_are_found(read):
    crisis = read("get_crisis_status", flags=["extradimensional_invasion_happened"])
    assert (crisis["crisis_active"], crisis["crisis_type"]) == (True, "unbidden")


def test_a_beaten_crisis_is_remembered_and_no_longer_in_progress(read):
    crisis = read(
        "get_crisis_status",
        flags=["prethoryn_invasion_happened", "prethoryn_invasion_defeated"],
        # Feral Prethoryn roam after the Scourge is beaten; they are not the crisis.
        countries=[("feral_prethoryn", "NAME_Feral_Prethoryn")],
    )
    assert crisis["crisis_active"] is False
    assert crisis["crisis_type"] is None
    assert crisis["crises_defeated"] == ["prethoryn"]


def test_space_fauna_and_ordinary_empires_are_not_a_crisis(read):
    crisis = read(
        "get_crisis_status",
        countries=[("amoeba", "NAME_Space_Amoeba"), ("default", "Swarm of Prethoryn Fans")],
    )
    assert crisis["crisis_active"] is False
    assert crisis["crisis_countries"] == []


def test_the_khan_is_still_active_after_his_first_defeat(read):
    khan = read(
        "get_great_khan",
        flags=["great_khan_announcement", "great_khan_defeated_once"],
        countries=[("awakened_marauders", "NAME_Great_Khanate")],
    )
    assert khan["khan_risen"] is True
    assert khan["khan_status"] == "active"
    assert khan["khan_country_id"] == 1


def test_the_khan_is_defeated_once_the_game_says_he_is_dead(read):
    khan = read(
        "get_great_khan",
        flags=["great_khan_announcement", "great_khan_defeated_once", "great_khan_dead"],
        countries=[("ruined_marauders", "NAME_Broken_Horde")],
    )
    assert (khan["khan_risen"], khan["khan_status"]) == (True, "defeated")
    assert khan["khan_country_id"] is None


def test_dormant_marauders_are_present_without_a_khan(read):
    khan = read(
        "get_great_khan",
        countries=[("dormant_marauders", "NAME_Horde_1"), ("dormant_marauders", "NAME_Horde_2")],
    )
    assert khan["marauders_present"] is True
    assert khan["marauder_count"] == 2
    assert (khan["khan_risen"], khan["khan_status"]) == (False, None)


def test_the_heirs_of_the_khan_placeholder_is_not_a_risen_khan(read):
    khan = read("get_great_khan", countries=[("awakened_marauders", "NAME_Heirs_Host")])
    assert (khan["khan_risen"], khan["khan_status"]) == (False, None)


def test_a_war_in_heaven_is_read_from_its_flag(read):
    assert read("get_fallen_empires", flags=["no_war_in_heaven"])["war_in_heaven"] is False
    ongoing = read("get_fallen_empires", flags=["war_in_heaven_started", "war_in_heaven_ongoing"])
    assert ongoing["war_in_heaven"] is True


def test_the_l_cluster_is_open_once_its_flag_is_set(read):
    assert read("get_lgate_status")["lgate_opened"] is False
    assert read("get_lgate_status", flags=["l_cluster_opened"])["lgate_opened"] is True


def test_guardians_and_fauna_are_read_from_their_country_types(read):
    found = read(
        "get_leviathans",
        countries=[
            ("guardian_dragon", "NAME_Grand_Dragon", 1),
            ("tiyanki", "NAME_Placid_Leviathans", 8),
            ("amoeba", "NAME_Spaceborne_Organics", 0),
            ("amoeba_borderless", "NAME_Spaceborne_Organics", 0),
            # Script helpers and look-alike names are not the creatures.
            ("tiyanki_garrison", "NAME_Placid_Leviathans", 18),
            ("drone_faction", "NAME_Mining_Drone_Expansion_Initiative", 3),
            ("default", "Crystal Cloud Concord", 4),
        ],
    )
    assert [(item["type"], item["status"], item["fleets"]) for item in found["leviathans"]] == [
        ("amoeba", "defeated", 0),
        ("ether_drake", "alive", 1),
        ("tiyanki", "alive", 8),
    ]
    assert (found["total_count"], found["alive_count"], found["defeated_count"]) == (3, 2, 1)
    assert found["leviathans"][1]["name"] == "Ether Drake"


def test_no_guardian_is_reported_when_none_exists(read):
    # `tech_dragon_armor` in research data used to be read as a living Ether Drake.
    found = read("get_leviathans", flags=["tech_dragon_armor_unlocked"])
    assert found == {"leviathans": [], "total_count": 0, "defeated_count": 0, "alive_count": 0}


def test_every_name_looked_for_is_checked_against_the_installed_game(tmp_path):
    (tmp_path / "common" / "country_types").mkdir(parents=True)
    (tmp_path / "events").mkdir()
    types = sorted(game_vocabulary.country_types() - {"swarm"})
    (tmp_path / "common" / "country_types" / "00.txt").write_text(
        "".join(f"{name} = {{\n}}\n" for name in types)
    )
    flags = sorted(game_vocabulary.global_flags() - {"great_khan_dead"})
    (tmp_path / "events" / "crisis.txt").write_text(
        "".join(f"\tset_global_flag = {name}\n" for name in flags)
    )

    assert game_vocabulary.missing_from_game(tmp_path) == [
        "country type swarm",
        "global flag great_khan_dead",
    ]
