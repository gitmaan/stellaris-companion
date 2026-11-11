"""Treaties are read from the keys the game writes in a relation block.

The save keys were read off real saves. Migration treaties were always empty
because the code looked for `migration_treaty`, while the game writes
`migration_access`, and federation allies were reported as defensive pacts.
"""

from __future__ import annotations

import zipfile

import pytest


def _relation(country: int, *keys: str, opinion: int = 0, trust: str = "0") -> str:
    lines = ["\t\t\trelation=", "\t\t\t{", "\t\t\t\towner=0", f"\t\t\t\tcountry={country}"]
    lines += [f"\t\t\t\ttrust={trust}", f"\t\t\t\trelation_current={opinion}"]
    # A nested block that repeats a treaty word must not be read as a treaty.
    lines += ["\t\t\t\tmodifier=", "\t\t\t\t{", '\t\t\t\t\tmodifier="opinion_defensive_pact"']
    lines += ["\t\t\t\t\tvalue=20", "\t\t\t\t}"]
    lines += [f"\t\t\t\t{key}" for key in keys]
    return "\n".join([*lines, "\t\t\t}"])


@pytest.fixture(scope="module")
def diplomacy(tmp_path_factory):
    rust_bridge = pytest.importorskip("stellaris_companion.rust_bridge")
    from stellaris_save_extractor import SaveExtractor

    relations = "\n".join(
        [
            _relation(1, "alliance=yes", "migration_access=yes", opinion=120, trust="24.99"),
            _relation(2, "defensive_pact=yes", "commercial_pact=yes", "research_agreement=yes"),
            _relation(3, "is_rival=yes", "closed_borders=yes", "truce=7", opinion=-300),
            _relation(4, "non_aggression_pact=yes", "embassy=yes", "communications=yes"),
            _relation(5),
        ]
    )
    countries = "\n".join(
        f'\t{cid}=\n\t{{\n\t\ttype="default"\n\t\tname=\n\t\t{{\n\t\t\tkey="Empire {cid}"\n'
        "\t\t\tliteral=yes\n\t\t}\n\t}"
        for cid in range(1, 6)
    )
    gamestate = (
        'version="Cygnus v4.5.3"\ndate="2300.01.01"\n'
        'player=\n{\n\t\n\t{\n\t\tname="tester"\n\t\tcountry=0\n\t}\n}\n'
        'country=\n{\n\t0=\n\t{\n\t\ttype="default"\n\t\trelations_manager=\n\t\t{\n'
        f"{relations}\n\t\t}}\n\t}}\n{countries}\n}}\n"
    )
    path = tmp_path_factory.mktemp("save") / "diplomacy.sav"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("gamestate", gamestate.encode("utf-8"))
        archive.writestr("meta", b'version="Cygnus v4.5.3"\nname="tester"\n')
    with rust_bridge.session(path):
        return SaveExtractor(str(path)).get_diplomacy()


def _ids(entries):
    return [entry["id"] for entry in entries]


def test_migration_treaties_are_read_from_migration_access(diplomacy):
    assert _ids(diplomacy["migration_treaties"]) == [1]


def test_an_ally_is_not_a_defensive_pact(diplomacy):
    assert _ids(diplomacy["allies"]) == [1]
    assert _ids(diplomacy["defensive_pacts"]) == [2]
    by_id = {relation["country_id"]: relation for relation in diplomacy["relations"]}
    assert by_id[1].get("alliance") is True
    assert "defensive_pact" not in by_id[1]


def test_the_other_treaties_and_stances(diplomacy):
    assert _ids(diplomacy["commercial_pacts"]) == [2]
    assert _ids(diplomacy["non_aggression_pacts"]) == [4]
    assert _ids(diplomacy["rivals"]) == [3]
    assert _ids(diplomacy["closed_borders"]) == [3]
    assert sorted((t["country_id"], t["type"]) for t in diplomacy["treaties"]) == [
        (1, "migration_treaty"),
        (2, "commercial_pact"),
        (2, "defensive_pact"),
        (2, "research_agreement"),
        (3, "closed_borders"),
        (3, "rival"),
        (4, "non_aggression_pact"),
    ]


def test_relation_details(diplomacy):
    by_id = {relation["country_id"]: relation for relation in diplomacy["relations"]}
    assert (by_id[1]["opinion"], by_id[1]["trust"]) == (120, 24)
    assert by_id[3]["opinion"] == -300
    assert by_id[3].get("has_truce") is True
    assert by_id[4].get("embassy") is True and by_id[4].get("has_contact") is True
    assert by_id[5] == {
        "country_id": 5,
        "empire_name": "Empire 5",
        "country_type": "default",
        "trust": 0,
        "opinion": 0,
    }
    assert diplomacy["relation_count"] == 5
