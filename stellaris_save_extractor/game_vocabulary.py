"""Game identifiers the extractors look for, kept in one place so they can be checked.

A save records galaxy-wide facts under names the game's own scripts define: country
types in ``common/country_types`` and global flags set with ``set_global_flag``.
Reading those exact names is an answer; searching the save for a word that sounds
right is a guess, and a name the game never writes simply never matches.
:func:`missing_from_game` checks every name here against an installed game, and
``scripts/check_local_saves.py`` runs it before a release.
"""

from __future__ import annotations

import re
from pathlib import Path

# Country types the game defines with `end_game_crisis = yes`, by the crisis they
# belong to. The Sentinels and the Cybrex carry the same marker but fight the
# crisis, so they are not listed.
CRISIS_COUNTRY_TYPES = {
    "swarm": "prethoryn",
    "extradimensional": "unbidden",
    "extradimensional_2": "aberrant",
    "extradimensional_3": "vehement",
    "ai_empire": "contingency",
    "synth_queen": "cetana",
    "awakened_synth_queen": "cetana",
    "synth_queen_storm": "cetana",
    "the_reckoning": "the_reckoning",
}

# Global flags the crisis events set: (arrived, still running, defeated). The game
# removes the "still running" flag when the crisis ends; the Unbidden have none.
CRISIS_FLAGS: dict[str, tuple[str, str | None, str]] = {
    "prethoryn": (
        "prethoryn_invasion_happened",
        "ongoing_prethoryn_invasion",
        "prethoryn_invasion_defeated",
    ),
    "unbidden": (
        "extradimensional_invasion_happened",
        None,
        "extradimensional_invasion_defeated",
    ),
    "contingency": ("ai_invasion_happened", "ai_invasion_ongoing", "ai_invasion_defeated"),
    "cetana": ("synth_queen_happened", "synth_queen_ongoing", "synth_queen_defeated"),
}

# `awakened_marauders` is the Great Khan's horde, and also a placeholder the Heirs
# of the Khan origin creates, so the Khan's rise is read from the flags below.
MARAUDER_COUNTRY_TYPES = frozenset({"dormant_marauders", "marauder_raiders", "ruined_marauders"})
KHAN_COUNTRY_TYPE = "awakened_marauders"
# Set by the event every empire receives when the Khan rises.
KHAN_RISEN_FLAG = "great_khan_announcement"
# Set when the Khan dies for good; `great_khan_defeated_once` only marks a first defeat.
KHAN_DEAD_FLAG = "great_khan_dead"

# Held for as long as the War in Heaven lasts, then removed.
WAR_IN_HEAVEN_FLAG = "war_in_heaven_ongoing"
# Set when the first L-Gate is opened.
LGATE_OPENED_FLAG = "l_cluster_opened"


def country_types() -> set[str]:
    return {*CRISIS_COUNTRY_TYPES, *MARAUDER_COUNTRY_TYPES, KHAN_COUNTRY_TYPE}


def global_flags() -> set[str]:
    crisis = {flag for flags in CRISIS_FLAGS.values() for flag in flags if flag}
    return {*crisis, KHAN_RISEN_FLAG, KHAN_DEAD_FLAG, WAR_IN_HEAVEN_FLAG, LGATE_OPENED_FLAG}


def missing_from_game(game_dir: Path) -> list[str]:
    """Names above that the installed game's scripts never define or set."""
    defined_types: set[str] = set()
    for path in sorted((game_dir / "common" / "country_types").glob("*.txt")):
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        defined_types.update(re.findall(r"(?m)^([A-Za-z0-9_]+)\s*=\s*\{", text))

    set_flags: set[str] = set()
    for folder in ("events", "common"):
        for path in sorted((game_dir / folder).rglob("*.txt")):
            text = path.read_text(encoding="utf-8-sig", errors="replace")
            if "set_global_flag" in text:
                set_flags.update(re.findall(r"set_global_flag\s*=\s*([A-Za-z0-9_]+)", text))

    missing = [f"country type {name}" for name in sorted(country_types() - defined_types)]
    missing += [f"global flag {name}" for name in sorted(global_flags() - set_flags)]
    return missing
