from __future__ import annotations

import contextlib
import logging
import re

# Rust bridge for Clausewitz parsing (required for session mode)
from rust_bridge import ParserError, _get_active_session

logger = logging.getLogger(__name__)


class PlanetsMixin:
    """Domain methods extracted from the original SaveExtractor."""

    def get_planets(self) -> dict:
        """Get the player's colonized planets.

        Requires Rust session mode for extraction.

        Returns:
            Dict with planet details including population and districts
        """
        return self._get_planets_rust()

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
        if not isinstance(name_data, dict):
            return str(name_data) if name_data else "Unknown"

        key = name_data.get("key", "Unknown")
        variables = name_data.get("variables", [])

        def clean_name(raw_name: str) -> str:
            """Clean up a raw name value (strip NAME_ prefix, replace underscores)."""
            if raw_name.startswith("NAME_"):
                raw_name = raw_name[5:]
            return raw_name.replace("_", " ")

        # Handle NEW_COLONY_NAME_X with variables
        # e.g., NEW_COLONY_NAME_1 with NAME=Alpha_Centauri -> "Alpha Centauri 1"
        if key.startswith("NEW_COLONY_NAME_"):
            colony_num = key.replace("NEW_COLONY_NAME_", "")
            for var in variables:
                if var.get("key") == "NAME":
                    value = var.get("value", {})
                    if isinstance(value, dict):
                        system_name = clean_name(value.get("key", ""))
                        if system_name:
                            return f"{system_name} {colony_num}"
            # Fallback if no variable found
            return f"Colony {colony_num}"

        # Handle HABITAT_PLANET_NAME with variables
        # e.g., HABITAT_PLANET_NAME with FROM.from.solar_system.GetName=Omicron_Persei -> "Omicron Persei Habitat"
        if key == "HABITAT_PLANET_NAME":
            for var in variables:
                if "solar_system" in var.get("key", "") or var.get("key") == "NAME":
                    value = var.get("value", {})
                    if isinstance(value, dict):
                        system_name = clean_name(value.get("key", ""))
                        if system_name:
                            return f"{system_name} Habitat"
            # Fallback if no variable found
            return "Habitat"

        # Check for direct NAME_ pattern (e.g., "NAME_Earth" -> "Earth")
        if key.startswith("NAME_"):
            return clean_name(key)

        # Check for HUMAN2_PLANET_ or similar _PLANET_ patterns (e.g., "HUMAN2_PLANET_StCaspar" -> "StCaspar")
        if "_PLANET_" in key:
            return key.split("_PLANET_")[-1].replace("_", " ")

        return key

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

            # Extract buildings - resolve IDs to building type names
            # The baseline extracts from externally_owned_buildings (megacorp branch offices, etc.)
            # This matches what the regex pattern `buildings=\s*\{[^}]*buildings=\s*\{([^}]+)\}` finds
            ext_buildings = planet.get("externally_owned_buildings", [])
            if ext_buildings and isinstance(ext_buildings, list):
                resolved_buildings = []
                for ext_entry in ext_buildings:
                    if isinstance(ext_entry, dict):
                        building_ids = ext_entry.get("buildings", [])
                        for bid in building_ids:
                            bid_str = str(bid)
                            if bid_str in building_types:
                                resolved_buildings.append(
                                    building_types[bid_str].replace("building_", "")
                                )
                if resolved_buildings:
                    planet_info["buildings"] = resolved_buildings

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

        for key, pop_group in session.iter_section("pop_groups"):
            # P010: entry might be string "none" for deleted entries
            if not isinstance(pop_group, dict):
                continue

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

        sites_found = []

        for site_id, site in sites_data.items():
            # P010: entry might be string "none" for deleted entries
            if not isinstance(site, dict):
                continue

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

            # P011: use .get() with defaults
            site_type = site.get("type")
            if site_type:
                entry["type"] = site_type

            # Extract location
            location = site.get("location")
            if isinstance(location, dict):
                loc_type = location.get("type")
                loc_id = location.get("id")
                if loc_type is not None and loc_id is not None:
                    entry["location"] = {
                        "type": int(loc_type),
                        "id": int(loc_id),
                    }

            # Extract numeric fields
            for key in [
                "index",
                "clues",
                "difficulty",
                "days_left",
                "last_excavator_country",
                "excavator_fleet",
            ]:
                value = site.get(key)
                if value is not None:
                    with contextlib.suppress(ValueError, TypeError):
                        entry[key] = int(value)

            # Extract locked boolean
            locked = site.get("locked")
            if locked is not None:
                entry["locked"] = locked == "yes"

            # Extract completed info
            completed = site.get("completed")
            if isinstance(completed, list):
                entry["completed_count"] = len(completed)
                # Get last completed date
                for comp in completed:
                    if isinstance(comp, dict):
                        date = comp.get("date")
                        if date:
                            entry["last_completed_date"] = date

            # Extract events info
            events = site.get("events")
            if isinstance(events, list):
                entry["events_count"] = len(events)
                # Count active (non-expired) events
                active_count = 0
                for evt in events:
                    if isinstance(evt, dict):
                        expired = evt.get("expired")
                        if expired == "no":
                            active_count += 1
                entry["active_events_count"] = active_count

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

    def get_problem_planets(self) -> dict:
        """Get planets with issues (high crime, low stability, amenity deficit).

        Returns:
            Dict with lists of planets grouped by problem type
        """
        planets_data = self.get_planets()
        planets = planets_data.get("planets", [])

        result = {
            "high_crime": [],  # Crime > 25%
            "low_stability": [],  # Stability < 50
            "amenity_deficit": [],  # Free amenities < 0
            "problem_count": 0,
        }

        for planet in planets:
            problems = []

            crime = planet.get("crime", 0)
            if crime > 25:
                problems.append(f"crime {crime:.0f}%")
                result["high_crime"].append(
                    {
                        "name": planet.get("name", "Unknown"),
                        "crime": crime,
                        "modifiers": planet.get("modifiers", []),
                    }
                )

            stability = planet.get("stability", 100)
            if stability < 50:
                problems.append(f"stability {stability:.0f}")
                result["low_stability"].append(
                    {
                        "name": planet.get("name", "Unknown"),
                        "stability": stability,
                    }
                )

            free_amenities = planet.get("free_amenities", 0)
            if free_amenities < 0:
                problems.append(f"amenities {free_amenities:.0f}")
                result["amenity_deficit"].append(
                    {
                        "name": planet.get("name", "Unknown"),
                        "deficit": free_amenities,
                    }
                )

        result["problem_count"] = (
            len(result["high_crime"])
            + len(result["low_stability"])
            + len(result["amenity_deficit"])
        )

        return result
