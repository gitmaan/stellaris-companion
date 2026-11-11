"""English in-game names for technology IDs found in saves.

A save lists technologies by internal ID, and many IDs say nothing about the name
the player sees: ``tech_cryostasis_1`` is "Automated Colony Ships". The names
here are generated from shipped game files by
``scripts/generate_identity_catalog.py``; the JSON records its source game version.

This is a name catalog, not a rules catalog: it says what an ID is called in the
English UI, not whether the technology is available to this empire. Modded or
newer-than-catalog IDs have no entry, and callers keep the ID visible for them.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from pathlib import Path

logger = logging.getLogger(__name__)

TECHNOLOGY_CATALOG_PATH = Path(__file__).with_name("technology_catalog.json")


def _load_technology_catalog(
    path: Path = TECHNOLOGY_CATALOG_PATH,
) -> tuple[str | None, dict[str, str], dict[str, tuple[str, ...]]]:
    """Load ``{id: name}`` and ``{id: other names}``, or nothing if unreadable."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        names = {
            str(identifier): name
            for identifier, name in data["technology"].items()
            if isinstance(name, str) and name
        }
        variants = {
            str(identifier): tuple(name for name in other if isinstance(name, str) and name)
            for identifier, other in (data.get("variants") or {}).items()
            if isinstance(other, list)
        }
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        logger.exception("Technology name catalog unavailable at %s", path)
        return None, {}, {}
    version = data.get("game_version")
    return (version if isinstance(version, str) else None), names, variants


TECHNOLOGY_CATALOG_GAME_VERSION, _TECHNOLOGY_NAMES, _TECHNOLOGY_VARIANTS = (
    _load_technology_catalog()
)
_VERSION = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")


def _version_tuple(version: object) -> tuple[int, int, int] | None:
    match = _VERSION.search(version) if isinstance(version, str) else None
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)


def catalog_covers_game_version(
    game_version: object, catalog_version: object = TECHNOLOGY_CATALOG_GAME_VERSION
) -> bool | None:
    """Whether the catalog is at least as new as ``game_version``; None if unknown.

    A newer game can add or rename technologies the catalog has never seen, and a
    patch release is enough for that, so patch versions are compared too.
    """
    game, catalog = _version_tuple(game_version), _version_tuple(catalog_version)
    if game is None or catalog is None:
        return None
    return catalog >= game


def technology_display_name(identifier: object) -> str | None:
    """Return the English in-game name for a save technology ID, if catalogued."""
    if not isinstance(identifier, str):
        return None
    return _TECHNOLOGY_NAMES.get(identifier.strip())


def technology_label(identifier: object) -> str:
    """Return the in-game name, or a readable form of an uncatalogued ID."""
    name = technology_display_name(identifier)
    if name:
        return name
    text = str(identifier or "").strip()
    return text.removeprefix("tech_").replace("_", " ").title()


def technology_names_for(identifiers: Iterable[object]) -> dict[str, str]:
    """Map each catalogued ID in ``identifiers`` to its name, in first-seen order."""
    names: dict[str, str] = {}
    for identifier in identifiers:
        name = technology_display_name(identifier)
        if name and identifier not in names:
            names[str(identifier).strip()] = name
    return names


def technology_variant_names(identifier: object) -> tuple[str, ...]:
    """Other names the game can show for this technology, depending on the empire."""
    if not isinstance(identifier, str):
        return ()
    return _TECHNOLOGY_VARIANTS.get(identifier.strip(), ())
