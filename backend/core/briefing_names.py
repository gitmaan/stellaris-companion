"""The in-game name of a value in a briefing, from the player's installed game.

Most briefing values are the save's own IDs, and the game keys its text by the
same ID: ``tr_discovery_adopt`` is "Discovery Traditions". For a few fields the
text key is the ID with its kind in front: a starbase's ``crew_quarters`` is named
under ``sm_crew_quarters``, and a planet's buildings list holds ``foundry_2`` for
``building_foundry_2``. ``NAME_KEY_PREFIXES`` records that per field, so a value is
looked up as the kind of thing it is and never as something else with a similar ID.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from stellaris_companion.game_names import game_name

# (briefing section, field) -> what the game puts in front of the value in its text keys.
NAME_KEY_PREFIXES: dict[tuple[str, str], tuple[str, ...]] = {
    ("territory", "buildings"): ("building_",),
    ("territory", "type"): ("pc_",),
    ("defense", "level"): ("starbase_",),
    ("defense", "buildings"): ("sm_",),
    ("defense", "defense_buildings"): ("sm_",),
    ("defense", "modules"): ("sm_",),
    ("defense", "defense_modules"): ("sm_",),
    ("diplomacy", "ethics"): ("ethic_",),
    ("situation", "war_goal"): ("war_goal_",),
    ("military", "war_goal"): ("war_goal_",),
    ("species", "class"): ("",),
}

# (briefing section, field) -> the dict under that field is keyed by save IDs, and what
# the game puts in front of them in its text keys. Every other dict key is the app's own
# word for a field and is never looked up: ``found`` and ``federation`` have game text too.
KEY_NAME_PREFIXES: dict[tuple[str, str], tuple[str, ...]] = {
    ("progression", "by_tree"): ("tradition_",),
    ("defense", "by_level"): ("starbase_", ""),
    ("military", "ship_classes"): ("",),
    ("federation_details", "laws"): ("",),
    # Resources: ``sr_zro`` is "Zro", ``integrity`` is "Valor", and a mod's are its own.
    ("economy", "stockpiles"): ("",),
    ("economy", "monthly_income"): ("",),
    ("economy", "monthly_expenses"): ("",),
    ("economy", "net_monthly"): ("",),
    ("economy", "strategic_stockpiles"): ("sr_",),
}

# A save ID: lowercase words joined by underscores. One bare word is too easily
# an ordinary word, so it is only looked up in a field listed above.
ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$")

# A leader trait's second and third tier. The game's text names a few of them, always
# as the first tier's name and the tier ("$leader_trait_resilient$ II"), and leaves
# most without text of their own; those are named here the same way.
TIERED_TRAIT = re.compile(r"^((?:leader_)?trait_[a-z0-9_]+)_([23])$")
TIER_NUMERALS = {"2": "II", "3": "III"}


def briefing_value_name(value: str, section: str = "", field: str = "") -> str | None:
    """What the installed game calls ``value``; None when it has no name for it."""
    prefixes = NAME_KEY_PREFIXES.get((section, field), ())
    name = game_name(*(prefix + value for prefix in prefixes))
    if name is None and ID_PATTERN.match(value):
        name = game_name(value) or _tiered_trait_name(value)
    return name


def _tiered_trait_name(value: str) -> str | None:
    tiered = TIERED_TRAIT.match(value)
    first_tier = game_name(tiered.group(1)) if tiered else None
    return f"{first_tier} {TIER_NUMERALS[tiered.group(2)]}" if first_tier else None


def briefing_key_names(keys: Iterable[str], section: str, field: str) -> dict[str, str]:
    """The in-game name of each key of a dict that is keyed by save IDs.

    A tradition tree is ``unyielding`` in the save and "Fortification" on screen.
    Empty when the field is not keyed by IDs, and when two keys share a name,
    because one entry would then replace the other.
    """
    prefixes = KEY_NAME_PREFIXES.get((section, field))
    if not prefixes:
        return {}
    keys = list(keys)
    names = {key: game_name(*(prefix + key for prefix in prefixes)) for key in keys}
    shown = [names[key] or key for key in keys]
    if len(set(shown)) != len(shown):
        return {}
    return {key: name for key, name in names.items() if name and name != key}
