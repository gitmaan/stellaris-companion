"""Names the save stores as a key with variables, shown the way the game shows them.

A save does not hold the name of a planet, leader, empire or war as text. It holds
a key into the game's text, often with variables that are names themselves::

    name={ key="PRESCRIPTED_planet_name_glebsig" }                 -> Ladnah
    name={ key="PLANET_NAME_FORMAT"
           variables={ PARENT={ key="Bysh" } NUMERAL={ key="II" } } } -> Bysh II
    name={ key="%ADJ%" variables={ 1={ key="of_Technologists"
           variables={ 1={ key="Union" } } } } }                   -> Union of Technologists
    name={ key="%SEQ%" variables={ fmt={ key="HUMAN1_FLEET" } num={ key="3" } } } -> 3rd Fleet

The game builds the name from its text files. The rules for the special keys are
written in the game's own ``name_system`` text file (word order of adjectives,
turning a noun into an adjective, number formats), and this module follows them
with the text of the player's installed game, so the result is in the language
the player plays in. It gives no name when any part cannot be built exactly;
callers then fall back to a readable form of the key.
"""

from __future__ import annotations

import re
from typing import Any

from .game_names import (
    _COLOUR,
    _ICON,
    MAX_NAME_LENGTH,
    GameNames,
    default_form,
    installed_names,
)
from .game_names import _REFERENCE as _PLACEHOLDER

_SCRIPTED = re.compile(r"\[([^\[\]]+)\]")
# One position of a digit format: "100?:prefix(0 1 2 ...)suffix".
_DIGIT_POSITION = re.compile(r"^(\d+)(\??):([^()]*)\(([^()]*)\)(.*)$")
# One rule of a conditional format: "n100+10+(0-9)" is a multiple of 100, plus 10, plus 0 to 9.
_MULTIPLE_RULE = re.compile(r"^n(\d+)((?:\+\d+)*)(?:\+\((\d+)-(\d+)\))?$")
_MAX_DEPTH = 12
_NUMBER_FORMAT_ALIASES = {"O": "ORD", "CARD": "C"}


def stored_name(value: Any, names: GameNames | None = None) -> str | None:
    """The name the game shows for a stored name block or key; None when it cannot be built."""
    names = names or installed_names()
    if names is None:
        return None
    block = {"key": value} if isinstance(value, str) else value
    text = _Renderer(names).render(block, 0)
    if text is None:
        return None
    text = " ".join(_COLOUR.sub("", _ICON.sub("", text)).split())
    return text if text and len(text) <= MAX_NAME_LENGTH else None


def _variables(block: dict[str, Any]) -> dict[str, Any]:
    variables = block.get("variables")
    if not isinstance(variables, list):
        return {}
    return {
        str(item["key"]): item.get("value")
        for item in variables
        if isinstance(item, dict) and item.get("key") is not None
    }


class _Renderer:
    def __init__(self, names: GameNames) -> None:
        self.names = names

    def text(self, key: str) -> str | None:
        """The game's text for ``key`` as written, placeholders and all."""
        text = self.names._entries.get(key)
        return None if text is None else default_form(text)

    def reference(self, key: str, depth: int) -> str | None:
        """Other game text a pattern refers to ("$tradition_discovery$")."""
        text = self.text(key)
        if text is None or depth > _MAX_DEPTH:
            return None
        return self.fill(text, {}, depth + 1)

    def pattern(self, block: dict[str, Any]) -> str | None:
        """The text a block's own key stands for, before its variables are filled in."""
        key = block["key"]
        # A key holding "$" is the pattern itself ("$base$ $affix$").
        return key if block.get("literal") == "yes" or "$" in key else self.text(key)

    def render(self, block: Any, depth: int) -> str | None:
        """Build the name of ``block``, or None when a part of it is unknown."""
        name = self.build(block, depth)
        # A part is joined to its neighbours by the pattern around it, not by its own spaces.
        return None if name is None else name.strip()

    def build(self, block: Any, depth: int) -> str | None:
        if depth > _MAX_DEPTH or not isinstance(block, dict):
            return None
        key = block.get("key")
        if not isinstance(key, str) or not key:
            return None
        if block.get("literal") == "yes":
            return key
        variables = _variables(block)

        if key == "%SEQ%":
            return self.numbered(variables, depth)
        if key == "%ADJ%":
            return self.render(variables.get("1"), depth + 1)
        if key == "%ADJECTIVE%":
            return self.adjective_from_noun(variables, depth)
        if key in ("%LEADER_1%", "%LEADER_2%"):
            if "2" not in variables:
                return self.render(variables.get("1"), depth + 1)
            return self.pair(variables.get("1"), variables["2"], depth, "TWO_NAMES_FORMAT")

        text = self.pattern(block)
        if text is None:
            # Part of a name that is not game text is shown as written ("II", "CR9-").
            return key if depth and not variables and "_" not in key else None
        if "1" in variables and "$1$" not in text:
            # A word and what it goes with: "Centralized" + "Hegemony".
            return self.pair(block, variables["1"], depth, "adj_format")
        return self.fill(text, variables, depth)

    def fill(
        self, text: str, variables: dict[str, Any], depth: int, other: str | None = None
    ) -> str | None:
        """Replace ``$NAME$`` and ``[Scope.GetName]`` in ``text`` with the block's variables.

        ``other`` is the name that takes the ``$1$`` place when the block is one of a pair.
        """
        failed = False
        used: set[str] = set()

        def value_of(name: str) -> str | None:
            if name == "1" and other is not None:
                return other
            if name in variables:
                used.add(name)
                return self.render(variables[name], depth + 1)
            if name == "1":
                # An adjective on its own: "Human $1$" is "Human".
                return ""
            return self.reference(name, depth)

        def placeholder(match: re.Match[str]) -> str:
            nonlocal failed
            value = value_of(match.group(1))
            failed = failed or value is None
            return value or ""

        text = _PLACEHOLDER.sub(placeholder, text)

        def scripted(match: re.Match[str]) -> str:
            nonlocal failed
            name = match.group(1)
            if name not in variables:
                # The text of another game version may name the scope differently;
                # one scripted name and one variable left can only mean each other.
                spare = [k for k in variables if k not in used and "." in k]
                if len(spare) != 1 or len(_SCRIPTED.findall(match.string)) != 1:
                    failed = True
                    return ""
                name = spare[0]
            used.add(name)
            value = self.render(variables[name], depth + 1)
            failed = failed or value is None
            return value or ""

        text = _SCRIPTED.sub(scripted, text)
        return None if failed else text

    def pair(self, first: Any, second: Any, depth: int, format_key: str) -> str | None:
        """Two parts of one name, joined the way the language joins them.

        Either part may hold the place for the other itself: "$1$ of Technologists"
        takes "Union" in front, "Beak of $1$" takes "Ivory" behind. When neither
        does, the game's format decides the order: ``adj_format`` ("adj $1$") for a
        word and what it describes, ``TWO_NAMES_FORMAT`` ("$1$ $2$") for a leader.
        """
        if not isinstance(first, dict) or not isinstance(first.get("key"), str):
            return None
        first_text = self.pattern(first)
        first_variables = {k: v for k, v in _variables(first).items() if v is not second}
        if first_text is not None and "$1$" in first_text:
            second_name = self.render(second, depth + 1)
            if second_name is None:
                return None
            return self.fill(first_text, first_variables, depth, second_name)

        if first_text is None or first["key"].startswith("%"):
            first_name = self.render(first, depth + 1)
        else:
            first_name = self.fill(first_text, first_variables, depth)
        if first_name is None:
            return None
        if isinstance(second, dict) and isinstance(second.get("key"), str):
            second_text = self.pattern(second)
            second_variables = _variables(second)
            if second_text is not None and "$1$" in second_text and "1" not in second_variables:
                return self.fill(second_text, second_variables, depth, first_name)
        second_name = self.render(second, depth + 1)
        if second_name is None:
            return None
        if format_key == "adj_format":
            pattern = self.text("adj_format") or "adj $1$"
            return pattern.replace("adj", first_name, 1).replace("$1$", second_name)
        pattern = self.text(format_key) or "$1$ $2$"
        return pattern.replace("$1$", first_name).replace("$2$", second_name)

    def adjective_from_noun(self, variables: dict[str, Any], depth: int) -> str | None:
        """Turn a noun into an adjective ("Jhabbanid" -> "Jhabbanan") and add what it describes."""
        noun = self.render(variables.get("adjective"), depth + 1)
        if not noun:
            return None
        described = ""
        if "1" in variables:
            rendered = self.render(variables["1"], depth + 1)
            if rendered is None:
                return None
            described = rendered
        for ending in (noun[-2:], noun[-1:], ""):
            pattern = self.text(f"adj_NN{ending}")
            if pattern is not None:
                stem = noun[: len(noun) - len(ending)] if ending else noun
                return pattern.replace("*", stem).replace("$1$", described)
        pattern = self.text("adj_format") or "adj $1$"
        return pattern.replace("adj", noun, 1).replace("$1$", described)

    def numbered(self, variables: dict[str, Any], depth: int) -> str | None:
        """A sequential name: the pattern's number formats filled with the number."""
        pattern_block, number_block = variables.get("fmt"), variables.get("num")
        if not isinstance(pattern_block, dict) or not isinstance(number_block, dict):
            return None
        try:
            number = int(number_block.get("key"))
        except (TypeError, ValueError):
            return None
        pattern = self.text(pattern_block.get("key", ""))
        if pattern is None:
            return None
        failed = False

        def placeholder(match: re.Match[str]) -> str:
            nonlocal failed
            value = self.number(match.group(1), number, depth + 1)
            if value is None:
                value = self.reference(match.group(1), depth)
            failed = failed or value is None
            return value or ""

        text = _PLACEHOLDER.sub(placeholder, pattern)
        return None if failed else text

    def number(self, format_key: str, number: int, depth: int) -> str | None:
        """``number`` written in one of the game's number formats (C, ORD, R, ...)."""
        definition = self.text(format_key)
        if definition is None:
            # Name lists also write "$O$" and "$CARD$"; the text file defines ORD and C.
            definition = self.text(_NUMBER_FORMAT_ALIASES.get(format_key, ""))
        if definition is None or depth > _MAX_DEPTH:
            return None
        definition = definition.strip()
        if definition.startswith("-1,"):
            number, definition = number - 1, definition[3:].strip()
        if definition.startswith("("):
            return _digits(definition, number)
        for rule in definition.split(","):
            condition, _, output = rule.strip().partition(":")
            if _rule_applies(condition.strip(), number):
                failed = False

                def placeholder(match: re.Match[str]) -> str:
                    nonlocal failed
                    value = self.number(match.group(1), number, depth + 1)
                    failed = failed or value is None
                    return value or ""

                text = _PLACEHOLDER.sub(placeholder, output.strip())
                return None if failed else text
        return None


def _rule_applies(condition: str, number: int) -> bool:
    if condition == "def":
        return True
    if condition.isdigit():
        return number == int(condition)
    match = _MULTIPLE_RULE.match(condition)
    if not match:
        return False
    remainder = number % int(match.group(1))
    base = sum(int(part) for part in match.group(2).split("+") if part)
    low, high = (int(match.group(3)), int(match.group(4))) if match.group(3) else (0, 0)
    return base + low <= remainder <= base + high


def _digits(definition: str, number: int) -> str | None:
    """Write ``number`` with a digit format such as the Roman numerals' ``R``."""
    if number < 0 or not definition.endswith(")"):
        return None
    out: list[str] = []
    remainder = number
    for position in definition[1:-1].split(";"):
        match = _DIGIT_POSITION.match(position.strip())
        if not match:
            return None
        base, optional, prefix, digits, suffix = match.groups()
        index, remainder = divmod(remainder, int(base))
        symbols = digits.split()
        if index >= len(symbols):
            return None
        if optional and index == 0 and not out:
            continue
        symbol = symbols[index]
        if symbol == "|":
            continue
        out.append(prefix + ("" if symbol == "||" else symbol) + suffix)
    return "".join(out)
