"""The player's dig sites are reported however many sites the galaxy has.

Sites were read in save order and reading stopped at the fiftieth, before the
ones the player cannot see were left out. In a galaxy with more than fifty sites
a player's own sites past that point were missing from the briefing.
"""

from __future__ import annotations

import zipfile

import pytest

PLAYER = 0
OTHER_EMPIRES = "1 16777220"


def _site(site_id: int, visible_to: str | None, completed_by: tuple[int, ...] = ()) -> str:
    lines = [f"\t\t{site_id}=", "\t\t{", "\t\t\texcavator_fleet=4294967295"]
    lines += [f'\t\t\ttype="site_{site_id}"']
    if completed_by:
        lines += ["\t\t\tcompleted=", "\t\t\t{"]
        for country in completed_by:
            lines += ["\t\t\t\t", "\t\t\t\t{", f"\t\t\t\t\tcountry={country}"]
            lines += ['\t\t\t\t\tdate=\t\t\t\t\t"2242.01.24"', "\t\t\t\t}"]
        lines += ["\t\t\t}"]
    lines += ["\t\t\tclues=2", "\t\t\tdays_left=90", "\t\t\tdifficulty=3", "\t\t\tlocked=no"]
    if visible_to is not None:
        lines += ["\t\t\tvisible_to=", "\t\t\t{", f"\t\t\t\t{visible_to} ", "\t\t\t}"]
    return "\n".join([*lines, "\t\t}"])


@pytest.fixture(scope="module")
def extractor(tmp_path_factory):
    rust_bridge = pytest.importorskip("stellaris_companion.rust_bridge")
    from stellaris_save_extractor import SaveExtractor

    # Fifty-five sites belong to other empires or to no one yet; the player's five come last.
    sites = [_site(n, OTHER_EMPIRES if n % 2 else None, (1, 1)) for n in range(55)]
    sites += [
        _site(55, f"{PLAYER} 1"),
        _site(56, f"{PLAYER}"),
        _site(57, f"1 {PLAYER} 16777220", (PLAYER, PLAYER, PLAYER)),
        _site(58, f"{PLAYER} 16777220", (1,)),
        _site(59, f"{PLAYER}"),
    ]
    gamestate = (
        'version="Cygnus v4.5.3"\ndate="2300.01.01"\n'
        'player=\n{\n\t\n\t{\n\t\tname="tester"\n\t\tcountry=0\n\t}\n}\n'
        'country=\n{\n\t0=\n\t{\n\t\ttype="default"\n\t}\n}\n'
        "archaeological_sites=\n{\n\tsites=\n\t{\n" + "\n".join(sites) + "\n\t}\n}\n"
    )
    path = tmp_path_factory.mktemp("save") / "archaeology.sav"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("gamestate", gamestate.encode("utf-8"))
        archive.writestr("meta", b'version="Cygnus v4.5.3"\nname="tester"\n')
    with rust_bridge.session(path):
        yield SaveExtractor(str(path))


def _player_sites(result: dict) -> list[str]:
    return [site["site_id"] for site in result["sites"] if site["player_visible"]]


def test_every_site_is_read_when_no_limit_is_given(extractor):
    result = extractor.get_archaeology(limit=None)

    assert result["count"] == 60
    assert _player_sites(result) == ["55", "56", "57", "58", "59"]


def test_a_limit_keeps_the_players_sites_ahead_of_the_rest(extractor):
    assert _player_sites(extractor.get_archaeology()) == ["55", "56", "57", "58", "59"]

    first_three = extractor.get_archaeology(limit=3)
    assert [site["site_id"] for site in first_three["sites"]] == ["55", "56", "57"]


def test_a_site_says_who_can_see_it_and_who_dug_it(extractor):
    sites = {site["site_id"]: site for site in extractor.get_archaeology(limit=None)["sites"]}

    # One viewer, written as a block holding a single number.
    assert sites["56"]["player_visible"] is True
    assert sites["57"]["player_completed"] is True
    assert sites["57"]["completed_count"] == 3
    # Another empire finished a chapter of a site the player can see.
    assert sites["58"]["player_completed"] is False
    assert sites["58"]["completed_count"] == 1
    assert sites["1"]["player_visible"] is False
    assert sites["0"]["player_visible"] is False
