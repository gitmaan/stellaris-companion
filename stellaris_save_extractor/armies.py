from __future__ import annotations

import logging

# Rust bridge for Clausewitz parsing (required for session mode)
from stellaris_companion.rust_bridge import ParserError, _get_active_session

logger = logging.getLogger(__name__)


class ArmiesMixin:
    """Army-related extraction methods."""

    def get_armies(self) -> dict:
        """Get all armies owned by the player empire.

        Parses the top-level `army={}` section and filters to player-owned armies.
        Armies can be stationed on planets (defense) or on transport ships (assault).

        Requires Rust session mode for extraction.

        Returns:
            Dict with:
              - armies: List of army dicts with type, health, max_health, morale,
                        location (planet_id or ship_id), leader_id
              - count: Total number of player armies
              - by_type: Dict mapping army type to count
              - total_strength: Sum of max_health for combat power estimate
        """
        session = _get_active_session()
        if not session:
            raise ParserError("Rust session required for get_armies")

        result = {
            "armies": [],
            "count": 0,
            "by_type": {},
            "total_strength": 0.0,
        }

        player_id = self.get_player_empire_id()
        armies_list = []
        by_type: dict[str, int] = {}
        total_strength = 0.0

        # Get name mappings for resolving IDs to names
        species_names = self._get_species_names()
        planet_names = self._get_planet_names_map()

        # Get owned_armies list from player country (avoids iterating all armies)
        player_country = self._get_player_country_entry(player_id)
        if not player_country or not isinstance(player_country, dict):
            return result

        owned_army_ids = player_country.get("owned_armies", [])
        if not owned_army_ids:
            return result

        # Batch fetch only player's armies (24x faster than iterating all)
        army_entries = session.get_entries("army", [str(aid) for aid in owned_army_ids])

        for entry in army_entries:
            army_id = entry.get("_key")
            army_data = entry.get("_value")

            if not isinstance(army_data, dict):
                continue

            # Extract army type
            army_type = army_data.get("type", "unknown")

            # Extract health values
            health = float(army_data.get("health", 0.0))
            max_health = float(army_data.get("max_health", 0.0))

            # Extract morale
            morale = army_data.get("morale")
            if morale is not None:
                morale = float(morale)

            # Determine location - planet or ship
            planet_id = army_data.get("planet")
            ship_id = army_data.get("ship")

            location_type = None
            location_id = None
            if planet_id is not None and str(planet_id) != "4294967295":
                location_type = "planet"
                location_id = str(planet_id)
            elif ship_id is not None and str(ship_id) != "4294967295":
                location_type = "ship"
                location_id = str(ship_id)

            # Extract leader if present
            leader_id = army_data.get("leader")

            # Extract experience
            experience = float(army_data.get("experience", 0.0))

            # Extract species if present
            species_id = army_data.get("species")

            # Build army info
            army_info = {
                "id": str(army_id),
                "type": army_type,
                "health": round(health, 1),
                "max_health": round(max_health, 1),
            }

            if morale is not None:
                army_info["morale"] = round(morale, 1)

            if location_type:
                army_info["location_type"] = location_type
                if location_type == "planet" and location_id:
                    army_info["location_name"] = planet_names.get(
                        location_id, f"Planet {location_id}"
                    )
                elif location_type == "ship":
                    army_info["location_name"] = "Transport Ship"

            if leader_id is not None and str(leader_id) != "4294967295":
                army_info["leader_id"] = str(leader_id)

            if experience > 0:
                army_info["experience"] = round(experience, 1)

            if species_id is not None and str(species_id) != "4294967295":
                species_id_str = str(species_id)
                army_info["species_name"] = species_names.get(
                    species_id_str, f"Species {species_id_str}"
                )

            armies_list.append(army_info)

            # Track by type
            by_type[army_type] = by_type.get(army_type, 0) + 1

            # Sum strength
            total_strength += max_health

        # Sort by army ID to ensure consistent ordering (Rust returns in numeric ID order)
        armies_list.sort(key=lambda x: int(x["id"]))

        result["armies"] = armies_list
        result["count"] = len(armies_list)
        result["by_type"] = by_type
        result["total_strength"] = round(total_strength, 1)

        return result

    def get_armies_summary(self) -> dict:
        """Get enriched army summary optimized for the advisor briefing.

        Instead of listing all 300+ individual armies (~17.5k tokens), returns
        aggregate counts and strengths by type and location (~300 tokens).

        The key distinction is transportable armies (on ships, available for
        invasion) vs garrisoned armies (on planets, for defense). This fixes
        the stress-test failure where the LLM conflated total garrison strength
        with available assault force.

        Returns:
            Dict with count, total_strength, by_type, by_location,
            transportable breakdown, and _note for LLM awareness.
        """
        session = _get_active_session()
        if not session:
            # Fall back to full armies if no session
            return self.get_armies()

        player_id = self.get_player_empire_id()
        player_country = self._get_player_country_entry(player_id)
        if not player_country or not isinstance(player_country, dict):
            return {
                "count": 0,
                "total_strength": 0.0,
                "by_type": {},
                "transportable": {"count": 0, "strength": 0.0},
                "garrisoned": {"count": 0, "strength": 0.0},
            }

        owned_army_ids = player_country.get("owned_armies", [])
        if not owned_army_ids:
            return {
                "count": 0,
                "total_strength": 0.0,
                "by_type": {},
                "transportable": {"count": 0, "strength": 0.0},
                "garrisoned": {"count": 0, "strength": 0.0},
            }

        army_entries = session.get_entries("army", [str(aid) for aid in owned_army_ids])

        by_type: dict[str, int] = {}
        total_strength = 0.0
        count = 0

        transport_count = 0
        transport_strength = 0.0
        garrison_count = 0
        garrison_strength = 0.0

        for entry in army_entries:
            army_data = entry.get("_value")
            if not isinstance(army_data, dict):
                continue

            army_type = army_data.get("type", "unknown")
            max_health = float(army_data.get("max_health", 0.0))

            count += 1
            total_strength += max_health
            by_type[army_type] = by_type.get(army_type, 0) + 1

            # Classify by location
            planet_id = army_data.get("planet")
            ship_id = army_data.get("ship")

            if ship_id is not None and str(ship_id) != "4294967295":
                transport_count += 1
                transport_strength += max_health
            elif planet_id is not None and str(planet_id) != "4294967295":
                garrison_count += 1
                garrison_strength += max_health

        return {
            "count": count,
            "total_strength": round(total_strength, 1),
            "by_type": by_type,
            "transportable": {
                "count": transport_count,
                "strength": round(transport_strength, 1),
                "note": "Armies on transport ships, available for planetary invasion",
            },
            "garrisoned": {
                "count": garrison_count,
                "strength": round(garrison_strength, 1),
                "note": "Armies stationed on planets for defense",
            },
            "_note": (
                "Army data is summarized by type and location. "
                "Per-planet garrison assignments are not included in this briefing."
            ),
        }
