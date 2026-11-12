"""Names the save stores as a key with variables are shown as the game shows them.

The game text here is a small copy of the shapes the real game uses: plain names,
patterns with ``$VARIABLE$`` places, the adjective rules and the number formats of
its ``name_system`` file.
"""

from __future__ import annotations

import pytest

from stellaris_companion import game_names
from stellaris_companion.game_names import GameNames
from stellaris_companion.stored_names import stored_name
from stellaris_save_extractor.name_resolution import resolve_name

ENGLISH = {
    # Plain names
    "PRESCRIPTED_planet_name_glebsig": "Ladnah",
    "NAME_Alpha_Centauri": "Alpha Centauri",
    "SPEC_Xani": "Xani",
    "SPEC_Jhabbanid": "Jhabbanid",
    "SPEC_Hadadesh": "Hadadesh",
    "Union": "Union",
    "Academy": "Academy",
    "Centralized": "Centralized",
    "Hegemony": "Hegemony",
    "War": "War",
    "NAME": "Name",
    "X_CHR_Kofi": "Kofi",
    "X_CHR_Skhosana": "Skhosana",
    "X_CHR_Ivory": "Ivory",
    "X_CHR_Feti": "Feti",
    # Patterns with places for variables
    "PLANET_NAME_FORMAT": "$PARENT$ $NUMERAL$",
    "NEW_COLONY_NAME_1": "$NAME$ Prime",
    "STAR_NAME_1_OF_1": "$NAME$",
    "HABITAT_PLANET_NAME": "[prev.solar_system.GetName] Habitat Complex",
    "war_vs_adjectives": "$1$ - $2$ $3$",
    "AofB": "$1$ of $2$",
    "of_Technologists": "$1$ of Technologists",
    "PRESCRIPTED_species_adjective_humans1": "Human $1$",
    "X_CHR_Beak_of": "Beak of $1$",
    "X_CHR_son_of_Rakn": "$1$, son of Rakn",
    "TWO_NAMES_FORMAT": "$1$ $2$",
    "COLOURED": "§YGolden§! £energy£ Fleet",
    # Adjective rules
    "adj_format": "adj $1$",
    "adj_NNi": "*ian $1$",
    "adj_NNid": "*an $1$",
    # Number formats and names that use them
    "C": "(100?:(0 1 2 3 4 5 6 7 8 9); 10?:(0 1 2 3 4 5 6 7 8 9); 1:(0 1 2 3 4 5 6 7 8 9))",
    "R": (
        "(100?:(| C CC CCC CD D DC DCC DCCC CM); 10?:(| X XX XXX XL L LX LXX LXXX XC); "
        "1:(| I II III IV V VI VII VIII IX))"
    ),
    "ORD": "n100+10+(0-9):$C$th, n10+1:$C$st, n10+2:$C$nd, n10+3:$C$rd, def:$C$th",
    "X_FLEET": "$ORD$ Fleet",
    "X_HIVE": "Xenomorph Hive $R$",
    "X_REGIMENT": "$O$ Home Regiment",
    "X_FORCE": "$CARD$ Expeditionary Force",
}
NAMES = GameNames(ENGLISH)


def block(key: str, **variables) -> dict:
    """A name block as the parser returns it."""
    result: dict = {"key": key}
    if variables:
        result["variables"] = [
            {"key": name.replace("__", "."), "value": value} for name, value in variables.items()
        ]
    return result


def literal(text: str) -> dict:
    return {"key": text, "literal": "yes"}


def numbered(pattern: str, number: int) -> dict:
    return block("%SEQ%", fmt=block(pattern), num=block(str(number)))


def shown(value) -> str | None:
    return stored_name(value, NAMES)


def test_a_key_is_shown_by_the_games_text_and_a_typed_name_as_typed() -> None:
    assert shown(block("PRESCRIPTED_planet_name_glebsig")) == "Ladnah"
    assert shown("NAME_Alpha_Centauri") == "Alpha Centauri"
    assert shown(literal("PRESCRIPTED_planet_name_glebsig")) == "PRESCRIPTED_planet_name_glebsig"
    assert shown(block("COLOURED")) == "Golden Fleet"
    # No text for the key: no name, and the caller falls back.
    assert shown(block("MOD_planet_name_unknown")) is None
    assert shown({}) is None


def test_a_pattern_is_filled_with_the_blocks_own_variables() -> None:
    colony = block("NEW_COLONY_NAME_1", NAME=block("NAME_Alpha_Centauri"))
    assert shown(colony) == "Alpha Centauri Prime"
    # A variable is a name block too, and a part that is not game text is shown as written.
    moon = block("PLANET_NAME_FORMAT", PARENT=colony, NUMERAL=block("II"))
    assert shown(moon) == "Alpha Centauri Prime II"
    # The variable wins over game text that happens to have the same key ("NAME").
    assert shown(block("STAR_NAME_1_OF_1", NAME=block("SPEC_Xani"))) == "Xani"
    # A place with nothing to fill it leaves the name unknown.
    assert shown(block("PLANET_NAME_FORMAT", PARENT=colony)) is None
    assert shown(block("NEW_COLONY_NAME_1", NAME=block("MOD_unknown_key"))) is None


def test_a_name_the_running_game_fills_in_takes_the_variable_the_save_recorded() -> None:
    # The save was written by a version that named the scope differently.
    habitat = block("HABITAT_PLANET_NAME", FROM__from__solar_system__GetName=block("SPEC_Xani"))
    assert shown(habitat) == "Xani Habitat Complex"
    assert shown(block("HABITAT_PLANET_NAME")) is None


def test_a_war_is_named_from_both_sides() -> None:
    war = block(
        "war_vs_adjectives",
        **{
            "1": block("%ADJECTIVE%", adjective=block("SPEC_Xani")),
            "2": block("%ADJECTIVE%", adjective=block("SPEC_Jhabbanid")),
            "3": block("War"),
        },
    )
    assert shown(war) == "Xanian - Jhabbanan War"


def test_an_adjective_goes_beside_what_it_describes() -> None:
    # The language's word order ("adj $1$") when neither part places the other.
    centralized = block("Centralized", **{"1": block("Hegemony")})
    assert shown(block("%ADJ%", **{"1": centralized})) == "Centralized Hegemony"
    # A part with a "$1$" place takes the other part there, whichever of the two it is.
    union = block("of_Technologists", **{"1": block("Union")})
    assert shown(block("%ADJ%", **{"1": union})) == "Union of Technologists"
    academy = block("Academy", **{"1": block("of_Technologists")})
    assert shown(block("%ADJ%", **{"1": academy})) == "Academy of Technologists"
    # Nested adjectives.
    nested = block("%ADJ%", **{"1": block("Centralized", **{"1": block("%ADJ%", **{"1": union})})})
    assert shown(nested) == "Centralized Union of Technologists"
    # An adjective on its own.
    assert shown(block("PRESCRIPTED_species_adjective_humans1")) == "Human"
    assert shown(block("AofB", **{"1": block("Union"), "2": block("SPEC_Xani")})) == "Union of Xani"


def test_a_noun_becomes_an_adjective_by_its_ending() -> None:
    def adjective(species: str, *described: dict) -> str | None:
        variables = {"adjective": block(species)}
        if described:
            variables["1"] = described[0]
        return shown(block("%ADJECTIVE%", **variables))

    assert adjective("SPEC_Xani") == "Xanian"
    # Two letters are tried before one: "id" -> "an", not "d".
    assert adjective("SPEC_Jhabbanid", block("Hegemony")) == "Jhabbanan Hegemony"
    # No rule for the ending: the noun is used as it is, in the language's word order.
    assert adjective("SPEC_Hadadesh", block("Union")) == "Hadadesh Union"
    assert adjective("MOD_unknown_species") is None


def test_a_leader_has_both_names() -> None:
    def leader(first: str, second: str) -> str | None:
        return shown(block("%LEADER_2%", **{"1": block(first), "2": block(second)}))

    assert leader("X_CHR_Kofi", "X_CHR_Skhosana") == "Kofi Skhosana"
    assert leader("X_CHR_Beak_of", "X_CHR_Ivory") == "Beak of Ivory"
    assert leader("X_CHR_Feti", "X_CHR_son_of_Rakn") == "Feti, son of Rakn"
    assert shown(block("%LEADER_1%", **{"1": block("X_CHR_Kofi")})) == "Kofi"
    assert leader("X_CHR_Kofi", "MOD_CHR_unknown") is None


@pytest.mark.parametrize(
    ("pattern", "number", "name"),
    [
        ("X_FLEET", 1, "1st Fleet"),
        ("X_FLEET", 2, "2nd Fleet"),
        ("X_FLEET", 3, "3rd Fleet"),
        ("X_FLEET", 11, "11th Fleet"),
        ("X_FLEET", 21, "21st Fleet"),
        ("X_FLEET", 112, "112th Fleet"),
        ("X_HIVE", 4, "Xenomorph Hive IV"),
        ("X_HIVE", 14, "Xenomorph Hive XIV"),
        ("X_HIVE", 102, "Xenomorph Hive CII"),
        # Name lists also write the ordinal as $O$ and the plain number as $CARD$.
        ("X_REGIMENT", 3, "3rd Home Regiment"),
        ("X_FORCE", 7, "7 Expeditionary Force"),
    ],
)
def test_a_numbered_name_uses_the_games_number_formats(pattern, number, name) -> None:
    assert shown(numbered(pattern, number)) == name


def test_a_number_the_format_cannot_write_gives_no_name() -> None:
    assert shown(numbered("X_HIVE", 1000)) is None
    assert shown(numbered("MOD_unknown_pattern", 1)) is None
    assert shown(block("%SEQ%", fmt=block("X_FLEET"), num=block("first"))) is None


def test_another_language_uses_its_own_word_order_and_numbers() -> None:
    german = GameNames(
        {
            **ENGLISH,
            "adj_format": "adj-$1$",
            "ORD": "def:$C$.",
            "X_FLEET": "$ORD$ Flotte",
            "Centralized": "Zentral",
            "Hegemony": "Hegemonie",
        },
        language="german",
    )
    centralized = block("%ADJ%", **{"1": block("Centralized", **{"1": block("Hegemony")})})

    assert stored_name(centralized, german) == "Zentral-Hegemonie"
    assert stored_name(numbered("X_FLEET", 3), german) == "3. Flotte"


def test_a_text_with_a_form_per_gender_or_case_is_shown_in_its_plain_form() -> None:
    """The game makes words agree; this app uses each word's first, plain form."""
    russian = GameNames(
        {
            "NAME_Earth": "Земля|||gen:Земли",
            "Union": "Союз&!masc|||gen:Союза&!masc",
            "AofB": "$1$ $2&gen$&!1",
            "adj_NNi": "$1$ *iana|||masc:$1$ *iano",
            "SPEC_Xani": "Xani",
        },
        language="russian",
    )
    union_of_earth = block("AofB", **{"1": block("Union"), "2": block("NAME_Earth")})

    assert stored_name(block("NAME_Earth"), russian) == "Земля"
    assert stored_name(union_of_earth, russian) == "Союз Земля"
    assert stored_name(block("%ADJECTIVE%", adjective=block("SPEC_Xani")), russian) == "Xaniana"
    # Names of buildings and the rest are read the same way.
    assert russian.name("NAME_Earth") == "Земля"
    assert russian.name("Union") == "Союз"


def test_a_format_this_app_does_not_know_gives_no_name() -> None:
    prefix = block("%ACRONYM%", base=block("Union"))
    assert shown(prefix) is None
    assert shown(block("AofB", **{"1": prefix, "2": block("Union")})) is None


def test_the_extractors_use_the_games_name_and_guess_only_without_it() -> None:
    capital = block("PRESCRIPTED_planet_name_glebsig")
    game_names.use_names(NAMES)
    try:
        resolved = resolve_name(capital, context="planet")
        assert (resolved.display, resolved.source, resolved.confidence) == (
            "Ladnah",
            "game_text",
            1.0,
        )
        assert resolve_name("NAME_Alpha_Centauri").display == "Alpha Centauri"
        # A bare word may be a name the player typed; it is not looked up as a key.
        assert resolve_name("War").source == "literal"
        assert resolve_name("C").display == "C"
        # No game text for it: the readable guess, as before.
        assert resolve_name(block("MOD_planet_name_ixidar"), context="planet").source != "game_text"
    finally:
        game_names.use_names(None)

    guessed = resolve_name(capital, context="planet")
    assert guessed.source != "game_text"
    assert guessed.display == "Planet Name Glebsig"
