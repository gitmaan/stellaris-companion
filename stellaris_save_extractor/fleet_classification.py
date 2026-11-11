"""Classify a player's owned fleets as military, starbase, or civilian.

Stellaris 4.x ("Pegasus") tags every fleet with a ``ship_class`` (e.g.
``shipclass_military``, ``shipclass_starbase``, ``shipclass_science_ship``) and
no longer marks starbases with ``station=yes``. The old heuristic
(``station``/``civilian`` flags plus a military-power threshold) therefore
counted every starbase as a military fleet. Prefer the explicit ``ship_class``
when present; fall back to the legacy heuristic for older saves that lack it.
"""

from __future__ import annotations

from .save_values import is_yes

MILITARY_SHIP_CLASS = "shipclass_military"
STARBASE_SHIP_CLASS = "shipclass_starbase"

# Non-combat owned fleets in 4.x saves (science/construction/orbital stations).
CIVILIAN_SHIP_CLASSES = frozenset(
    {
        "shipclass_science_ship",
        "shipclass_constructor",
        "shipclass_colonizer",
        "shipclass_transport",
        "shipclass_mining_station",
        "shipclass_research_station",
        "shipclass_observation_station",
    }
)


def classify_owned_fleet(fleet_data: dict, *, military_power_threshold: float = 100.0) -> str:
    """Return ``"military"``, ``"starbase"``, or ``"civilian"`` for one fleet.

    Args:
        fleet_data: A parsed fleet entry from the gamestate ``fleet`` section.
        military_power_threshold: Legacy-only cutoff used when a fleet has no
            ``ship_class`` and no ``station``/``civilian`` markers (filters out
            tiny space-fauna fleets).
    """
    ship_class = fleet_data.get("ship_class")
    if ship_class == STARBASE_SHIP_CLASS:
        return "starbase"
    if ship_class == MILITARY_SHIP_CLASS:
        return "military"
    if ship_class in CIVILIAN_SHIP_CLASSES:
        return "civilian"

    # Legacy saves (or unrecognized ship_class): fall back to the old heuristic.
    if is_yes(fleet_data.get("station")):
        return "starbase"
    if is_yes(fleet_data.get("civilian")):
        return "civilian"

    try:
        military_power = float(fleet_data.get("military_power", "0") or 0)
    except (ValueError, TypeError):
        military_power = 0.0
    return "military" if military_power > military_power_threshold else "civilian"
