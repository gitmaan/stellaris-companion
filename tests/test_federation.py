"""The player's federation is read with its name, its members and its president.

The briefing had the federation's ID and its members' IDs and no names, so the
Advisor could not say what the federation is called or who leads it, and history
recorded "Joined a federation: Federation".
"""

from __future__ import annotations

import zipfile

import pytest

from stellaris_companion import game_names
from stellaris_companion.game_names import GameNames

# A federation's name as the save stores it: a key into the game's text with variables.
FEDERATION_NAME = (
    '\t\tname=\n\t\t{\n\t\t\tkey="%ADJ%"\n\t\t\tvariables=\n\t\t\t{\n\t\t\t\t\n\t\t\t\t{\n'
    '\t\t\t\t\tkey="1"\n\t\t\t\t\tvalue=\n\t\t\t\t\t{\n\t\t\t\t\t\tkey="Star"\n'
    "\t\t\t\t\t\tvariables=\n\t\t\t\t\t\t{\n\t\t\t\t\t\t\t\n\t\t\t\t\t\t\t{\n"
    '\t\t\t\t\t\t\t\tkey="1"\n\t\t\t\t\t\t\t\tvalue=\n\t\t\t\t\t\t\t\t{\n'
    '\t\t\t\t\t\t\t\t\tkey="Compact"\n\t\t\t\t\t\t\t\t}\n\t\t\t\t\t\t\t}\n'
    "\t\t\t\t\t\t}\n\t\t\t\t\t}\n\t\t\t\t}\n\t\t\t}\n\t\t}\n"
)


def _country(country_id: int, name: str, federation: int | None) -> str:
    member = f"\t\tfederation={federation}\n" if federation is not None else ""
    # Every empire has relations from the first day; an ally is a fellow member.
    member += (
        "\t\trelations_manager=\n\t\t{\n\t\t\trelation=\n\t\t\t{\n"
        f"\t\t\t\towner={country_id}\n\t\t\t\tcountry=7\n\t\t\t\talliance=yes\n"
        "\t\t\t}\n\t\t}\n"
    )
    return (
        f'\t{country_id}=\n\t{{\n\t\ttype="default"\n\t\tname=\n\t\t{{\n'
        f'\t\t\tkey="{name}"\n\t\t\tliteral=yes\n\t\t}}\n{member}\t}}'
    )


@pytest.fixture(scope="module")
def federation(tmp_path_factory):
    rust_bridge = pytest.importorskip("stellaris_companion.rust_bridge")
    from stellaris_save_extractor import SaveExtractor

    countries = "\n".join(
        [
            _country(0, "Kilik Cooperative", 0),
            _country(1, "Tebrid Homolog", None),
            _country(7, "Ymorz Commerce League", 0),
            _country(16777221, "Ess'Jaggon Order", 0),
        ]
    )
    # The first federation formed in a galaxy has ID 0.
    federations = (
        "federation=\n{\n\t0=\n\t{\n" + FEDERATION_NAME + "\t\tfederation_progression=\n\t\t{\n"
        '\t\t\tfederation_type="trade_federation"\n\t\t\texperience=1200\n\t\t\tlevels=2\n\t\t}\n'
        "\t\tmembers=\n\t\t{\n\t\t\t16777221 0 7 \n\t\t}\n\t\tleader=7\n\t}\n}\n"
    )
    gamestate = (
        'version="Cygnus v4.5.3"\ndate="2300.01.01"\n'
        'player=\n{\n\t\n\t{\n\t\tname="tester"\n\t\tcountry=0\n\t}\n}\n'
        f"country=\n{{\n{countries}\n}}\n{federations}"
    )
    path = tmp_path_factory.mktemp("save") / "federation.sav"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("gamestate", gamestate.encode("utf-8"))
        archive.writestr("meta", b'version="Cygnus v4.5.3"\nname="tester"\n')
    game_names.use_names(GameNames({"Star": "Star $1$", "Compact": "Compact"}))
    try:
        with rust_bridge.session(path):
            extractor = SaveExtractor(str(path))
            yield extractor.get_federation_details(), extractor.get_diplomacy()
    finally:
        game_names.use_names(None)


def test_the_federation_has_the_name_the_game_shows(federation):
    details, diplomacy = federation

    assert details["federation_id"] == 0
    assert diplomacy["federation"] == 0
    assert details["name"] == "Star Compact"
    assert details["type"] == "trade_federation"
    assert details["level"] == 2


def test_members_and_president_are_named(federation):
    details, _ = federation

    assert details["members"] == [16777221, 0, 7]
    assert details["member_names"] == [
        "Ess'Jaggon Order",
        "Kilik Cooperative",
        "Ymorz Commerce League",
    ]
    assert details["president"] == 7
    assert details["president_name"] == "Ymorz Commerce League"
