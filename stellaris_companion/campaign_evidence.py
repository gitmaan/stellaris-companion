"""Shared interpretation of campaign evidence, without changing extracted values.

The save's DLC list reports requirements, not a complete feature or entitlement
inventory. Identity identifiers are observations; names only explain those IDs.
These functions perform no I/O (the bundled name catalog loads once at import)
and can also interpret older stored briefings.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Paradox's 4.3.6 release (2026-05-11) integrated all three packs into the base game.
# https://store.steampowered.com/news/posts/?appids=281990&enddate=1778509430&feed=steam_community_announcements
BASE_GAME_DLC_INTEGRATIONS = {
    "Utopia": (4, 3, 6),
    "Synthetic Dawn": (4, 3, 6),
    "Humanoids": (4, 3, 6),
}

_VERSION_PATTERN = re.compile(r"(?<![\w.])v?(\d+)\.(\d+)(?:\.(\d+))?(?![.\d])", re.I)
_DLC_STATUS_VALUES = frozenset({"reported", "not_recorded", "invalid"})

# Display names generated from shipped game files by
# scripts/generate_identity_catalog.py; the JSON records its source game version.
# This is a name catalog, not a rules catalog: it says what an ID is called in the
# English UI, not whether it is playable, compatible, or still exists in the game.
# Unknown, modded, or newer-than-catalog identifiers deliberately keep their
# identifier as the display.
IDENTITY_CATALOG_PATH = Path(__file__).with_name("identity_catalog.json")
_IDENTITY_KINDS = ("authority", "civic", "ethic", "origin")


def _load_identity_catalog(path: Path = IDENTITY_CATALOG_PATH) -> tuple[str | None, dict]:
    """Load ``kind -> {id: name}`` maps, degrading to raw identifiers if unreadable."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        names = {
            kind: {
                str(identifier): name
                for identifier, name in data[kind].items()
                if isinstance(name, str) and name
            }
            for kind in _IDENTITY_KINDS
        }
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        logger.exception("Identity name catalog unavailable at %s", path)
        return None, {kind: {} for kind in _IDENTITY_KINDS}
    version = data.get("game_version")
    return (version if isinstance(version, str) else None), names


IDENTITY_CATALOG_GAME_VERSION, _IDENTITY_NAMES = _load_identity_catalog()
_IDENTITY_PREFIXES = {
    "authority": "auth_",
    "civic": "civic_",
    "ethic": "ethic_",
    "origin": "origin_",
}


def resolve_content_availability(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Describe positive content evidence without inventing negative availability.

    Reported packs indicate save requirements; integrated packs indicate base-game
    content. Neither establishes current player unlocks or achievement eligibility.
    Legacy ``missing_dlcs`` is a derived guess and is intentionally never trusted.
    """
    meta = metadata if isinstance(metadata, dict) else {}
    version = meta.get("version")
    version = version.strip() if isinstance(version, str) else ""
    match = _VERSION_PATTERN.search(version)
    parsed_version = tuple(int(part or 0) for part in match.groups()) if match else None

    reported = meta.get("required_dlcs")
    valid_list = isinstance(reported, list) and all(
        isinstance(item, str) and bool(item.strip()) for item in reported
    )
    explicit_status = meta.get("required_dlcs_status")
    if isinstance(explicit_status, str) and explicit_status in _DLC_STATUS_VALUES:
        status = explicit_status
        if status == "reported" and not valid_list:
            status = "invalid"
    elif "required_dlcs_status" in meta:
        status = "invalid"
    elif "required_dlcs" not in meta or (valid_list and not reported):
        # The old extractor used [] for both absent and explicitly empty blocks.
        status = "not_recorded"
    else:
        status = "reported" if valid_list else "invalid"

    return {
        "game_version": version or None,
        "version_status": "parsed" if parsed_version is not None else "unknown",
        "dlc_evidence_status": status,
        "reported_dlcs": list(reported) if status == "reported" else [],
        "base_game_dlcs": sorted(
            name
            for name, integrated_since in BASE_GAME_DLC_INTEGRATIONS.items()
            if parsed_version is not None and parsed_version >= integrated_since
        ),
        "unreported_dlc_status": "unknown",
    }


def resolve_empire_identity(identity: dict[str, Any] | None) -> dict[str, Any]:
    """Add names and explicit kinds to observed IDs, preserving unknown identifiers.

    A civic remains a civic even when its name describes an empire archetype. The
    caller's raw fields are never changed. Both save keys and legacy prefix-stripped
    IDs resolve to the same canonical ID for each kind. Names come from a name
    catalog generated from one game version's files, not a rules catalog; IDs it
    does not know (mods, newer releases) keep their identifier as the name.
    """
    raw = identity if isinstance(identity, dict) else {}

    def entry(value: Any, kind: str) -> dict[str, str] | None:
        if not isinstance(value, str) or not value.strip():
            return None
        identifier = value.strip().removeprefix(_IDENTITY_PREFIXES[kind])
        if not identifier:
            return None
        name = _IDENTITY_NAMES[kind].get(identifier)
        return {
            "id": identifier,
            "name": name or identifier,
            "kind": kind,
            "source": "verified_catalog" if name else "raw_identifier",
        }

    def entries(value: Any, kind: str) -> list[dict[str, str]]:
        if not isinstance(value, list):
            return []
        return [resolved for item in value if (resolved := entry(item, kind)) is not None]

    return {
        "authority": entry(raw.get("authority"), "authority"),
        "civics": entries(raw.get("civics"), "civic"),
        "ethics": entries(raw.get("ethics"), "ethic"),
        "origin": entry(raw.get("origin"), "origin"),
    }
