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
