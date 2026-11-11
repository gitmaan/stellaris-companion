"""A small, slow, independent reader of Clausewitz text, used only to check the parser.

The Rust parser is what the app runs. This module shares no code with it: it reads
the same text with a few dozen lines of Python so that tests and
``scripts/check_local_saves.py`` can ask "is every key and value the save contains
present in what the parser returned?". It is deliberately simple rather than fast.

Shapes match the parser's JSON: a block of ``key=value`` pairs is a dict, a block
of bare values is a list, scalars are strings, and a key written more than once in
one block is a :class:`Repeated` list of its values in save order.
"""

from __future__ import annotations

import re
from typing import Any

_TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|[{}]|[<>!]=|[=<>]|[^\s{}=<>!"]+')
_OPERATORS = {"=", "<", ">", "<=", ">=", "!="}


class Repeated(list):
    """Values of a key that the save wrote several times in one block."""


def _atom(token: str) -> str:
    if token.startswith('"'):
        return re.sub(r"\\(.)", r"\1", token[1:-1])
    return token


def parse(text: str) -> dict[str, Any]:
    """Parse a whole document (the root is always key/value pairs)."""
    tokens = _TOKEN.findall(text)
    value, _ = _block(tokens, 0, root=True)
    return value if isinstance(value, dict) else {}


def _block(tokens: list[str], pos: int, *, root: bool = False) -> tuple[Any, int]:
    pairs: dict[str, Any] = {}
    seen_twice: set[str] = set()
    values: list[Any] = []
    while pos < len(tokens):
        token = tokens[pos]
        if token == "}":
            if root:  # a stray brace at the top level; the game writes none
                pos += 1
                continue
            pos += 1
            break
        if token == "{":
            value, pos = _block(tokens, pos + 1)
            values.append(value)
            continue
        if pos + 1 < len(tokens) and tokens[pos + 1] in _OPERATORS:
            key = _atom(token)
            pos += 2
            if pos < len(tokens) and tokens[pos] == "{":
                value, pos = _block(tokens, pos + 1)
            elif pos < len(tokens):
                value = _atom(tokens[pos])
                pos += 1
                # `color = hsv { ... }`: a tagged block; keep the block.
                if pos < len(tokens) and tokens[pos] == "{" and value in {"hsv", "rgb", "hsv360"}:
                    value, pos = _block(tokens, pos + 1)
            else:
                value = ""
            if key not in pairs:
                pairs[key] = value
            elif key in seen_twice:
                pairs[key].append(value)
            else:
                pairs[key] = Repeated([pairs[key], value])
                seen_twice.add(key)
            continue
        values.append(_atom(token))
        pos += 1
    if pairs and values:
        # Mixed blocks are rare and the two readers may order them differently.
        pairs["_mixed_values"] = values
        return pairs, pos
    return (pairs if pairs else values), pos


def differences(expected: Any, actual: Any, path: str = "", limit: int = 50) -> list[str]:
    """Where the parser's ``actual`` output loses or changes what the text holds."""
    found: list[str] = []

    def walk(want: Any, got: Any, where: str) -> None:
        if len(found) >= limit:
            return
        if isinstance(want, Repeated):
            if not isinstance(got, list) or len(got) != len(want):
                size = len(got) if isinstance(got, list) else type(got).__name__
                found.append(f"{where}: save repeats this key {len(want)} times, parser has {size}")
                return
            for index, (item, other) in enumerate(zip(want, got, strict=True)):
                walk(item, other, f"{where}[{index}]")
        elif isinstance(want, dict):
            if "_mixed_values" in want:
                return
            if not isinstance(got, dict):
                if not want and got in ([], None):
                    return
                found.append(f"{where}: save has a block of keys, parser has {type(got).__name__}")
                return
            for key, item in want.items():
                if key not in got:
                    found.append(f"{where}/{key}: missing from parser output")
                else:
                    walk(item, got[key], f"{where}/{key}")
        elif isinstance(want, list):
            if isinstance(got, list) and len(got) != len(want):
                # The parser drops empty blocks from a list: `{ { } { } }` reads as [].
                want = [item for item in want if item not in ([], {})]
            if not want and got in ({}, [], None):
                return
            if not isinstance(got, list) or len(got) != len(want):
                found.append(f"{where}: save has {len(want)} values, parser differs")
                return
            for index, (item, other) in enumerate(zip(want, got, strict=True)):
                walk(item, other, f"{where}[{index}]")
        elif str(got) != want.rstrip():  # the parser trims trailing whitespace in strings
            found.append(f"{where}: save has {want!r}, parser has {got!r}")

    walk(expected, actual, path)
    return found
