from __future__ import annotations

import contextlib
import logging
import re

# Rust bridge for Clausewitz parsing (required for session mode)
from stellaris_companion.rust_bridge import ParserError, _get_active_session

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

        player_id = self.get_player_empire_id()

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

        # Use session extract_sections for planets (reuses parsed data, no spawn)
        # The planets section has nested structure: planets.planet.{id: {...}}
        data = session.extract_sections(["planets"])
        planets_data = data.get("planets", {}).get("planet", {})

        planets_found = []

        for planet_id, planet in planets_data.items():
            if not isinstance(planet, dict):
                continue

            # Check if this planet is owned by the player
            owner = planet.get("owner")
            if owner is None or int(owner) != player_id:
                continue

            # Get planet class and skip non-habitable
            planet_class = planet.get("planet_class", "")
            ptype = planet_class.replace("pc_", "") if planet_class else ""

            # Skip stars and non-habitable types
            if ptype.endswith("_star") or ptype in non_habitable:
                continue

            planet_info = {"id": str(planet_id)}

            # Extract name
            name_data = planet.get("name")
            if name_data:
                planet_info["name"] = self._extract_planet_name(name_data)

            # Extract type
            if ptype:
                planet_info["type"] = ptype

            # Extract planet size
            size = planet.get("planet_size")
            if size is not None:
                planet_info["size"] = int(size)

            # Get population from pop_groups
            planet_id_int = int(planet_id)
            planet_info["population"] = pop_by_planet.get(planet_id_int, 0)
            result["total_pops"] += planet_info["population"]

            # Extract stability
            stability = planet.get("stability")
            if stability is not None:
                planet_info["stability"] = float(stability)

            # Extract amenities
            amenities = planet.get("amenities")
            if amenities is not None:
                planet_info["amenities"] = float(amenities)

            # Extract free amenities (surplus/deficit)
            free_amenities = planet.get("free_amenities")
            if free_amenities is not None:
                planet_info["free_amenities"] = float(free_amenities)

            # Extract crime
            crime = planet.get("crime")
            if crime is not None:
                planet_info["crime"] = round(float(crime), 1)

            # Extract permanent planet modifier
            pm = planet.get("planet_modifier")
            if pm:
                planet_info["planet_modifier"] = pm.replace("pm_", "")

            # Extract timed modifiers
            timed_mods = self._extract_timed_modifiers_rust(planet.get("timed_modifier"))
            if timed_mods:
                planet_info["modifiers"] = timed_mods

            # Extract player's own buildings from buildings_cache
            player_buildings = planet.get("buildings_cache", [])
            if player_buildings and isinstance(player_buildings, list):
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
            ext_buildings = planet.get("externally_owned_buildings", [])
            if ext_buildings and isinstance(ext_buildings, list):
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
            districts = planet.get("districts", [])
            if isinstance(districts, list):
                planet_info["district_count"] = len(districts)

            # Extract last building/district changed for context
            last_building = planet.get("last_building_changed")
            if last_building:
                planet_info["last_building"] = last_building

            last_district = planet.get("last_district_changed")
            if last_district:
                planet_info["last_district"] = last_district

            planets_found.append(planet_info)

        # Sort by planet ID for consistent ordering
        planets_found.sort(key=lambda x: int(x["id"]))

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

    def get_archaeology(self, limit: int = 25) -> dict:
        """Get archaeological dig sites and progress (summary-first, capped).

        Uses Rust session when active for fast extraction, falls back to regex.
        """
        # Dispatch to Rust version when session is active
        session = _get_active_session()
        if session:
            return self._get_archaeology_rust(limit)
        return self._get_archaeology_regex(limit)

    def _get_archaeology_rust(self, limit: int = 25) -> dict:
        """Rust-optimized archaeology extraction using session mode.

        Uses extract_sections for fast parsed dict access without regex.
        Enriches each site with:
        - player_visible: whether the player can see/interact with this site
        - player_completed: whether the player has excavated it
        - system_name: resolved from planet coordinate.origin -> galactic_object

        Args:
            limit: Maximum number of sites to return (1-50)

        Returns:
            Dict with archaeological site details
        """
        session = _get_active_session()
        if not session:
            return self._get_archaeology_regex(limit)

        limit = max(1, min(int(limit or 25), 50))

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
            if len(sites_found) >= limit:
                break

        result["sites"] = sites_found
        result["count"] = len(sites_found)
        return result

    def _get_archaeology_regex(self, limit: int = 25) -> dict:
        """Get archaeological dig sites using regex (fallback method)."""
        limit = max(1, min(int(limit or 25), 50))

        result = {
            "sites": [],
            "count": 0,
        }

        section = self._extract_section("archaeological_sites")
        if not section:
            result["error"] = "Could not find archaeological_sites section"
            return result

        # Extract sites={ ... } block.
        sites_match = re.search(r"\bsites\s*=\s*\{", section)
        if not sites_match:
            return result

        sites_start = sites_match.start()
        brace_count = 0
        sites_end = None
        started = False
        for i, ch in enumerate(section[sites_start:], sites_start):
            if ch == "{":
                brace_count += 1
                started = True
            elif ch == "}":
                brace_count -= 1
                if started and brace_count == 0:
                    sites_end = i + 1
                    break
        if sites_end is None:
            return result

        sites_block = section[sites_start:sites_end]

        site_pattern = r"\n\t\t(\d+)=\n\t\t\{"
        sites_found: list[dict] = []

        def extract_key_block(text: str, key: str) -> str | None:
            m = re.search(rf"\b{re.escape(key)}\s*=\s*\{{", text)
            if not m:
                return None
            start = m.start()
            brace_count = 0
            started = False
            for i, ch in enumerate(text[start:], start):
                if ch == "{":
                    brace_count += 1
                    started = True
                elif ch == "}":
                    brace_count -= 1
                    if started and brace_count == 0:
                        return text[start : i + 1]
            return None

        for match in re.finditer(site_pattern, sites_block):
            site_id = match.group(1)
            block_start = match.start() + 1

            brace_count = 0
            block_end = None
            started = False
            for i, ch in enumerate(sites_block[block_start:], block_start):
                if ch == "{":
                    brace_count += 1
                    started = True
                elif ch == "}":
                    brace_count -= 1
                    if started and brace_count == 0:
                        block_end = i + 1
                        break
            if block_end is None:
                continue

            site_block = sites_block[block_start:block_end]

            entry = {
                "site_id": site_id,
                "type": None,
                "location": None,
                "index": None,
                "clues": None,
                "difficulty": None,
                "days_left": None,
                "locked": None,
                "last_excavator_country": None,
                "excavator_fleet": None,
                "completed_count": 0,
                "last_completed_date": None,
                "events_count": 0,
                "active_events_count": 0,
            }

            type_match = re.search(r'\btype="([^"]+)"', site_block)
            if type_match:
                entry["type"] = type_match.group(1)

            location_match = re.search(
                r"\blocation\s*=\s*\{\s*type=(\d+)\s*id=(\d+)\s*\}", site_block
            )
            if location_match:
                entry["location"] = {
                    "type": int(location_match.group(1)),
                    "id": int(location_match.group(2)),
                }

            for key in [
                "index",
                "clues",
                "difficulty",
                "days_left",
                "last_excavator_country",
                "excavator_fleet",
            ]:
                m = re.search(rf"\b{key}=([-\d]+)", site_block)
                if m:
                    entry[key] = int(m.group(1))

            locked_match = re.search(r"\blocked=(yes|no)\b", site_block)
            if locked_match:
                entry["locked"] = locked_match.group(1) == "yes"

            completed_block = extract_key_block(site_block, "completed") or ""
            if completed_block:
                entry["completed_count"] = len(re.findall(r"\bcountry=(\d+)", completed_block))
                dates = re.findall(r'\bdate=\s*"(\d+\.\d+\.\d+)"', completed_block)
                if dates:
                    entry["last_completed_date"] = dates[-1]

            events_block = extract_key_block(site_block, "events") or ""
            if events_block:
                event_ids = re.findall(r'\bevent_id="([^"]+)"', events_block)
                entry["events_count"] = len(event_ids)
                entry["active_events_count"] = len(re.findall(r"\bexpired=no\b", events_block))

            sites_found.append(entry)
            if len(sites_found) >= limit:
                break

        result["sites"] = sites_found
        result["count"] = len(sites_found)
        return result
