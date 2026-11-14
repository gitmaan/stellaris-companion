from __future__ import annotations

import contextlib
import logging

# Rust bridge for Clausewitz parsing (required for session mode)
from stellaris_companion.rust_bridge import ParserError, _get_active_session

from .save_values import repeated, text

logger = logging.getLogger(__name__)


class PlanetsMixin:
    """Domain methods extracted from the original SaveExtractor."""

    def get_planets(self) -> dict:
        """Get the player's colonized planets.

        Requires Rust session mode for extraction.
        Results are cached per-instance (called by both get_player_status
        and get_complete_briefing).

        Returns:
            Dict with planet details including population and districts
        """
        if self._planets_cache is not None:
            return self._planets_cache
        self._planets_cache = self._get_planets_rust()
        return self._planets_cache

    def _extract_planet_name(self, name_data) -> str:
        """Extract readable planet name from Rust-parsed name data.

        Handles formats:
        - {"key": "NAME_Earth"} -> "Earth"
        - {"key": "NEW_COLONY_NAME_1", "variables": [{"key": "NAME", "value": {"key": "NAME_Alpha_Centauri"}}]} -> "Alpha Centauri 1"
        - {"key": "HABITAT_PLANET_NAME", "variables": [{"key": "FROM.from.solar_system.GetName", "value": {"key": "Omicron_Persei"}}]} -> "Omicron Persei Habitat"
        - {"key": "HUMAN2_PLANET_StCaspar"} -> "StCaspar"

        Args:
            name_data: Dict with key and optional variables

        Returns:
            Human-readable planet name
        """
        return self.resolve_name(name_data, default="Unknown Planet", context="planet").display

    def _get_planets_rust(self) -> dict:
        """Rust-optimized planets extraction using session mode.

        Uses iter_section for fast planet iteration without regex.
        Fixes truncation bugs in regex version (20MB limit).

        Returns:
            Dict with planet details including population and districts

        Raises:
            ParserError: If no active Rust session
        """
        session = _get_active_session()
        if not session:
            raise ParserError("Rust session required for get_planets")

        result = {"planets": [], "count": 0, "total_pops": 0}

        # Build population map from pop_groups section (using session)
        pop_by_planet = self._get_population_by_planet_rust()

        # Get building types mapping
        building_types = self._get_building_types()

        # Get country names for resolving branch office owners
        country_names = self._get_country_names_map()

        # Non-habitable planet types to skip
        non_habitable = {
            "asteroid",
            "barren",
            "barren_cold",
            "molten",
            "toxic",
            "frozen",
            "gas_giant",
        }

        resolution = self._get_player_colony_resolution()
        planets_found = []

        def colony_value(colony: dict, carrier: dict, key: str, default=None):
            value = colony.get(key)
            return carrier.get(key, default) if value is None else value

        def list_values(value) -> list:
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                return list(value.values())
            return []

        for ref in resolution.refs:
            colony = ref.colony
            carrier = ref.carrier

            # Get planet class and skip non-habitable
            planet_class = text(colony_value(colony, carrier, "planet_class", ""))
            ptype = planet_class.replace("pc_", "") if planet_class else ""
            if ref.carrier_type == "ship" and not ptype:
                ship_type = carrier.get("ship_size") or carrier.get("ship_class")
                if isinstance(ship_type, str):
                    ptype = ship_type.removeprefix("shipclass_")
                else:
                    ptype = "ship_colony"

            # The authoritative 4.4 colony list may use ship carriers. Only
            # apply the old physical-world filter to legacy planet records.
            if ref.schema == "legacy_planet" and (
                ptype.endswith("_star") or ptype in non_habitable
            ):
                continue

            display_id = ref.carrier_id or ref.colony_id
            planet_info = {"id": str(display_id)}
            if ref.schema == "colony_carrier":
                planet_info.update(
                    {
                        "colony_id": ref.colony_id,
                        "carrier_type": ref.carrier_type,
                        "carrier_id": ref.carrier_id,
                    }
                )

            # Extract name
            name_data = carrier.get("name") or colony.get("name")
            if name_data:
                planet_info["name"] = self._extract_planet_name(name_data)

            # Extract type
            if ptype:
                planet_info["type"] = ptype

            # Extract planet size
            size = colony_value(colony, carrier, "planet_size")
            if size is not None:
                with contextlib.suppress(ValueError, TypeError):
                    planet_info["size"] = int(size)

            # Pop groups retain the legacy field name ``planet`` but reference
            # the Colony ID in 4.4+, not the carrier's planet/ship ID.
            try:
                population = pop_by_planet.get(int(ref.colony_id), 0)
            except (ValueError, TypeError):
                population = 0
            planet_info["population"] = population
            result["total_pops"] += planet_info["population"]

            # Extract stability
            stability = colony_value(colony, carrier, "stability")
            if stability is not None:
                with contextlib.suppress(ValueError, TypeError):
                    planet_info["stability"] = float(stability)

            # Extract amenities
            amenities = colony_value(colony, carrier, "amenities")
            if amenities is not None:
                with contextlib.suppress(ValueError, TypeError):
                    planet_info["amenities"] = float(amenities)

            # Extract free amenities (surplus/deficit)
            free_amenities = colony_value(colony, carrier, "free_amenities")
            if free_amenities is not None:
                with contextlib.suppress(ValueError, TypeError):
                    planet_info["free_amenities"] = float(free_amenities)

            # Extract crime
            crime = colony_value(colony, carrier, "crime")
            if crime is not None:
                with contextlib.suppress(ValueError, TypeError):
                    planet_info["crime"] = round(float(crime), 1)

            # Extract permanent planet modifier
            planet_modifiers = [
                pm.replace("pm_", "")
                for pm in repeated(colony_value(colony, carrier, "planet_modifier"))
                if isinstance(pm, str) and pm
            ]
            if planet_modifiers:
                # The single-value field predates planets with several modifiers.
                planet_info["planet_modifier"] = planet_modifiers[-1]
            if len(planet_modifiers) > 1:
                planet_info["planet_modifiers"] = planet_modifiers

            # Extract timed modifiers
            timed_mods = self._extract_timed_modifiers_rust(
                colony_value(colony, carrier, "timed_modifier")
            )
            if timed_mods:
                planet_info["modifiers"] = timed_mods

            # Extract player's own buildings from buildings_cache
            player_buildings = list_values(colony_value(colony, carrier, "buildings_cache", []))
            if player_buildings:
                resolved_player_buildings = []
                for bid in player_buildings:
                    bid_str = str(bid)
                    if bid_str in building_types:
                        resolved_player_buildings.append(
                            building_types[bid_str].replace("building_", "")
                        )
                if resolved_player_buildings:
                    planet_info["buildings"] = resolved_player_buildings

            # Extract branch offices (megacorp buildings on our planets)
            # These are NOT the player's buildings - they're owned by other empires
            ext_buildings = list_values(
                colony_value(colony, carrier, "externally_owned_buildings", [])
            )
            if ext_buildings:
                branch_offices = []
                for ext_entry in ext_buildings:
                    if isinstance(ext_entry, dict):
                        owner_id = ext_entry.get("building_owner")
                        owner_type = ext_entry.get("owner_type", "")
                        building_ids = ext_entry.get("buildings", [])
                        resolved_buildings = []
                        for bid in building_ids:
                            bid_str = str(bid)
                            if bid_str in building_types:
                                resolved_buildings.append(
                                    building_types[bid_str].replace("building_", "")
                                )
                        if resolved_buildings and owner_id:
                            # Country names map uses int keys
                            owner_id_int = int(owner_id) if isinstance(owner_id, str) else owner_id
                            owner_name = country_names.get(owner_id_int, f"Empire #{owner_id}")
                            branch_offices.append(
                                {
                                    "owner_id": str(owner_id),
                                    "owner_name": owner_name,
                                    "owner_type": owner_type,
                                    "buildings": resolved_buildings,
                                }
                            )
                if branch_offices:
                    planet_info["branch_offices"] = branch_offices

            # Extract districts count
            raw_districts = colony_value(colony, carrier, "districts", [])
            if isinstance(raw_districts, (list, dict)):
                planet_info["district_count"] = len(list_values(raw_districts))

            # Extract last building/district changed for context
            last_building = colony_value(colony, carrier, "last_building_changed")
            if last_building:
                planet_info["last_building"] = last_building

            last_district = colony_value(colony, carrier, "last_district_changed")
            if last_district:
                planet_info["last_district"] = last_district

            planets_found.append(planet_info)

        # Sort numeric IDs first while remaining safe for modded string IDs.
        def sort_key(item: dict) -> tuple[int, int | str]:
            try:
                return 0, int(item["id"])
            except (ValueError, TypeError):
                return 1, str(item["id"])

        planets_found.sort(key=sort_key)

        result["planets"] = planets_found
        result["count"] = len(planets_found)

        # Summary by type
        type_counts = {}
        for planet in planets_found:
            ptype = planet.get("type", "unknown")
            if ptype not in type_counts:
                type_counts[ptype] = 0
            type_counts[ptype] += 1

        result["by_type"] = type_counts

        if resolution.schema == "colony_carrier":
            result["schema"] = resolution.schema
            result["planet_colonies"] = sum(
                1 for planet in planets_found if planet.get("carrier_type") == "planet"
            )
            result["ship_colonies"] = sum(
                1 for planet in planets_found if planet.get("carrier_type") == "ship"
            )
            if resolution.warnings:
                result["_warnings"] = list(resolution.warnings)

        return result

    def _extract_timed_modifiers_rust(self, timed_modifier_data) -> list[dict]:
        """Extract timed modifiers from Rust-parsed data.

        Args:
            timed_modifier_data: Dict with items list, e.g., {"items": [{"modifier": "...", "days": N}]}

        Returns:
            List of modifier dicts with name, display_name, days, permanent
        """
        modifiers = []

        if not isinstance(timed_modifier_data, dict):
            return modifiers

        items = timed_modifier_data.get("items", [])
        if not isinstance(items, list):
            return modifiers

        for item in items:
            if not isinstance(item, dict):
                continue

            mod_name = item.get("modifier")
            days_str = item.get("days")

            if not mod_name:
                continue

            try:
                days = int(days_str) if days_str is not None else 0
            except (ValueError, TypeError):
                days = 0

            display_name = mod_name.replace("_", " ").title()

            modifiers.append(
                {
                    "name": mod_name,
                    "display_name": display_name,
                    "days": days,
                    "permanent": days < 0,
                }
            )

        return modifiers

    def _get_population_by_planet_rust(self) -> dict[int, int]:
        """Build a mapping of planet_id -> total population using Rust session.

        Uses session iter_section for fast iteration without spawning.

        Returns:
            Dict mapping planet_id (int) to total population (int)

        Raises:
            ParserError: If no active Rust session or parser fails
        """
        session = _get_active_session()
        if not session:
            raise ParserError("Rust session required for population extraction")

        pop_by_planet: dict[int, int] = {}

        # Uses cached pop_groups section to avoid redundant Rust IPC
        for key, pop_group in self._get_pop_groups_cached().items():
            # P011: use .get() with defaults
            planet_id = pop_group.get("planet")
            size = pop_group.get("size")

            if planet_id is None or size is None:
                continue

            try:
                planet_id_int = int(planet_id)
                pop_size = int(size)
                if pop_size > 0:
                    pop_by_planet[planet_id_int] = pop_by_planet.get(planet_id_int, 0) + pop_size
            except (ValueError, TypeError):
                continue

        return pop_by_planet

    def get_archaeology(self, limit: int | None = 25) -> dict:
        """Archaeological sites and their progress, the player's own first.

        Each site says whether the player can see it (``player_visible``), whether
        the player finished one of its chapters (``player_completed``), how many
        chapters are done (``completed_count``) and which system it is in.

        Args:
            limit: The most sites to return; None for every site. Sites the player
                can see are returned before the rest, so a limit never drops one
                of them in favour of a site elsewhere in the galaxy.
        """
        session = _get_active_session()
        if not session:
            raise ParserError("Rust session required for get_archaeology")

        result = {
            "sites": [],
            "count": 0,
        }

        # Use session extract_sections for archaeological_sites
        data = session.extract_sections(["archaeological_sites"])
        arch_data = data.get("archaeological_sites", {})
        sites_data = arch_data.get("sites", {})

        if not isinstance(sites_data, dict):
            return result

        player_id = self.get_player_empire_id()
        player_id_str = str(player_id)

        # Lazy-load caches for system name resolution
        # These are already warm during briefing (get_planets, get_strategic_geography)
        planets_section = None
        galactic_objects = None

        sites_found = []

        for site_id, site in sites_data.items():
            # P010: entry might be string "none" for deleted entries
            if not isinstance(site, dict):
                continue

            entry = {
                "site_id": site_id,
                "type": None,
                "clues": None,
                "difficulty": None,
                "days_left": None,
                "locked": None,
                "player_visible": False,
                "player_completed": False,
                "completed_count": 0,
                "active_excavation": False,
                "system_name": None,
            }

            # P011: use .get() with defaults
            site_type = site.get("type")
            if site_type:
                entry["type"] = site_type

            # Check player visibility
            visible_to = site.get("visible_to", [])
            if isinstance(visible_to, list):
                entry["player_visible"] = player_id_str in [str(v) for v in visible_to]

            # Extract numeric fields
            for key in ["clues", "difficulty", "days_left"]:
                value = site.get(key)
                if value is not None:
                    with contextlib.suppress(ValueError, TypeError):
                        entry[key] = int(value)

            # Extract locked boolean
            locked = site.get("locked")
            if locked is not None:
                entry["locked"] = locked == "yes"

            # Active excavation check
            excavator_fleet = site.get("excavator_fleet")
            if excavator_fleet is not None:
                with contextlib.suppress(ValueError, TypeError):
                    entry["active_excavation"] = int(excavator_fleet) != 4294967295

            # Extract completed info + check player involvement
            completed = site.get("completed")
            if isinstance(completed, list):
                entry["completed_count"] = len(completed)
                for comp in completed:
                    if isinstance(comp, dict):
                        if str(comp.get("country")) == player_id_str:
                            entry["player_completed"] = True
                            break

            # Resolve system name: location.id -> planet coordinate.origin -> galactic_object name
            location = site.get("location")
            if isinstance(location, dict):
                planet_id = str(location.get("id", ""))
                if planet_id:
                    # Lazy-load planet data (cached from get_planets)
                    if planets_section is None:
                        planets_section = (
                            session.extract_sections(["planets"])
                            .get("planets", {})
                            .get("planet", {})
                        )
                    planet = planets_section.get(planet_id, {})
                    if isinstance(planet, dict):
                        coord = planet.get("coordinate", {})
                        if isinstance(coord, dict):
                            system_id = str(coord.get("origin", ""))
                            if system_id:
                                # Lazy-load galactic objects (cached from briefing)
                                if galactic_objects is None:
                                    galactic_objects = self._get_galactic_objects_cached()
                                sys_data = galactic_objects.get(system_id, {})
                                if isinstance(sys_data, dict):
                                    name_block = sys_data.get("name")
                                    if name_block is not None:
                                        entry["system_name"] = self.resolve_name(
                                            name_block,
                                            default=None,
                                            context="system",
                                        ).display

            sites_found.append(entry)

        sites_found.sort(key=lambda site: not site["player_visible"])
        if limit is not None:
            sites_found = sites_found[: max(1, int(limit))]
        result["sites"] = sites_found
        result["count"] = len(sites_found)
        return result
