"""Read keys that a save may write once or several times in one block.

Clausewitz has no list syntax for keyed values: a list is the same key written
again (``ethic="a" ethic="b"``). The parser returns such a key as a list of its
values in save order, and a key written once as the bare value. These helpers
keep readers from depending on which of the two a particular save happened to
contain.
"""

from __future__ import annotations

from typing import Any


def repeated(value: Any) -> list[Any]:
    """Every value of a key that may be repeated; ``[]`` when the key is absent."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def is_yes(value: Any) -> bool:
    """Whether a yes/no key is set. The game writes some flags more than once."""
    return any(item == "yes" for item in repeated(value))


def one(value: Any) -> Any:
    """The value of a key a reader expects once: the first when the save repeats it."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


def text(value: Any, default: str = "") -> str:
    """A key's value as text; ``default`` when it is absent or holds a block."""
    value = one(value)
    return value if isinstance(value, str) else default


def block(value: Any) -> dict[str, Any]:
    """A key's block; ``{}`` when it is absent or holds a bare value such as ``none``."""
    value = one(value)
    return value if isinstance(value, dict) else {}
