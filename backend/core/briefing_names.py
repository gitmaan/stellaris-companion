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

from stellaris_companion.game_names import game_name

# (briefing section, field) -> what the game puts in front of the value in its text keys.
NAME_KEY_PREFIXES: dict[tuple[str, str], tuple[str, ...]] = {
    ("territory", "buildings"): ("building_",),
    ("territory", "type"): ("pc_",),
    ("defense", "buildings"): ("sm_",),
    ("defense", "defense_buildings"): ("sm_",),
    ("defense", "modules"): ("sm_",),
    ("defense", "defense_modules"): ("sm_",),
    ("diplomacy", "ethics"): ("ethic_",),
    ("situation", "war_goal"): ("war_goal_",),
    ("military", "war_goal"): ("war_goal_",),
    ("species", "class"): ("",),
}

# A save ID: lowercase words joined by underscores. One bare word is too easily
# an ordinary word, so it is only looked up in a field listed above.
ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$")


def briefing_value_name(value: str, section: str = "", field: str = "") -> str | None:
    """What the installed game calls ``value``; None when it has no name for it."""
    prefixes = NAME_KEY_PREFIXES.get((section, field), ())
    name = game_name(*(prefix + value for prefix in prefixes))
    if name is None and ID_PATTERN.match(value):
        name = game_name(value)
    return name
