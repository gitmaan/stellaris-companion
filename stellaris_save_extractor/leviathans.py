from __future__ import annotations

import logging

# Rust bridge for Clausewitz parsing (required for session mode)
from stellaris_companion.rust_bridge import ParserError, _get_active_session

from .game_vocabulary import LEVIATHAN_COUNTRY_TYPES
from .save_values import text

logger = logging.getLogger(__name__)


class LeviathansMixin:
    """Extractors for Leviathans, Guardians, and space creatures."""

    # Known leviathan/guardian types with human-readable names and rewards
    LEVIATHAN_INFO = {
        "tiyanki": {
            "name": "Tiyanki (Space Whales)",
            "reward": "Tiyanki strategic resource, research",
            "threat": "Low (passive unless attacked)",
        },
        "crystal": {
            "name": "Crystalline Entities",
            "reward": "Crystal armor technology",
            "threat": "Medium (territorial)",
        },
        "amoeba": {
            "name": "Space Amoeba",
            "reward": "Amoeba flagella components",
            "threat": "Low-Medium (can be pacified)",
        },
        "cloud": {
            "name": "Void Cloud",
            "reward": "Cloud lightning weapon",
            "threat": "Medium",
        },
        "drone": {
            "name": "Mining Drones",
            "reward": "Drone components, minerals",
            "threat": "Low-Medium",
        },
        "ether_drake": {
            "name": "Ether Drake",
            "reward": "Dragon armor, Dragon trophy",
            "threat": "Very High (25k+ fleet power)",
        },
        "dimensional_horror": {
            "name": "Dimensional Horror",
            "reward": "Dark matter tech, jump drive insights",
            "threat": "Very High",
        },
        "automated_dreadnought": {
            "name": "Automated Dreadnought",
            "reward": "Can be captured as flagship",
            "threat": "Very High",
        },
        "stellarite": {
            "name": "Stellarite Devourer",
            "reward": "Stellar energy tech",
            "threat": "Very High",
        },
        "enigmatic_fortress": {
            "name": "Enigmatic Fortress",
            "reward": "Rare tech (random)",
            "threat": "High (puzzle encounter)",
        },
        "voidspawn": {
            "name": "Voidspawn",
            "reward": "Unique rewards",
            "threat": "Very High",
        },
        "wraith": {
            "name": "Spectral Wraith",
            "reward": "Psionic tech",
            "threat": "High",
        },
        "asteroid_hive": {"name": "Asteroid Hive"},
        "infinity_machine": {"name": "Infinity Machine"},
        "scavenger_bot": {"name": "Scavenger Bot"},
        "tiyanki_matriarch": {"name": "Tiyanki Matriarch"},
        "toxic_god": {"name": "Toxic God"},
        "voidworms": {"name": "Voidworms"},
        "cutholoids": {"name": "Cutholoids"},
    }

    def get_leviathans(self) -> dict:
        """Get the guardians and space fauna that exist in the galaxy.

        Each kind has its own country type in the game. One that still has fleets
        is alive; one whose country remains with no fleets has been wiped out, by
        whichever empire did it. A kind that never spawned is not listed.

        Returns:
            Dict with:
              - leviathans: One entry per kind, with status and fleet count
              - total_count: Number of kinds present
              - defeated_count: Kinds with no fleets left
              - alive_count: Kinds that still have fleets
        """
        if not _get_active_session():
            raise ParserError("Rust session required for get_leviathans")

        fleets: dict[str, int] = {}
        for country in self._get_countries_cached().values():
            kind = LEVIATHAN_COUNTRY_TYPES.get(
                text(country.get("country_type")) or text(country.get("type"))
            )
            if kind:
                fleets[kind] = fleets.get(kind, 0) + len(
                    self._get_owned_fleet_ids_from_entry(country)
                )

        detected = []
        for kind in sorted(fleets):
            info = self.LEVIATHAN_INFO.get(kind, {})
            entry = {
                "type": kind,
                "name": info.get("name", kind.replace("_", " ").title()),
                "status": "alive" if fleets[kind] else "defeated",
                "fleets": fleets[kind],
            }
            entry.update({key: info[key] for key in ("reward", "threat") if key in info})
            detected.append(entry)

        return {
            "leviathans": detected,
            "total_count": len(detected),
            "defeated_count": sum(1 for item in detected if item["status"] == "defeated"),
            "alive_count": sum(1 for item in detected if item["status"] == "alive"),
        }
