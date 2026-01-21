from __future__ import annotations

import re
import zipfile
from datetime import datetime
from pathlib import Path

class PlanetsMixin:
    """Domain methods extracted from the original SaveExtractor."""

    def get_planets(self) -> dict:
        """Get the player's colonized planets.

        Returns:
            Dict with planet details including population and districts
        """
        result = {
            'planets': [],
            'count': 0,
            'total_pops': 0
        }

        player_id = self.get_player_empire_id()

        # Build population map from pop_groups section
        # pop_groups aggregates pops by type with size=N showing actual count
        pop_by_planet = self._get_population_by_planet()

        # Find the planets section
        planets_match = re.search(r'^planets=\s*\{\s*planet=\s*\{', self.gamestate, re.MULTILINE)
        if not planets_match:
            result['error'] = "Could not find planets section"
            return result

        start = planets_match.start()
        # Get a large chunk for planets (they're spread out)
        planets_chunk = self.gamestate[start:start + 20000000]  # 20MB - planets section is large

        planets_found = []

        # Find each planet block by looking for the pattern: \n\t\tID=\n\t\t{
        # Then check if it has owner=player_id
        planet_start_pattern = r'\n\t\t(\d+)=\s*\{'

        for match in re.finditer(planet_start_pattern, planets_chunk):
            planet_id = match.group(1)
            block_start = match.start() + 1  # Skip leading newline

            # Find the end of this planet block by counting braces
            brace_count = 0
            block_end = block_start
            started = False
            # Planet blocks can be very large (10k+ chars) due to pop data
            for i, char in enumerate(planets_chunk[block_start:block_start + 30000], block_start):
                if char == '{':
                    brace_count += 1
                    started = True
                elif char == '}':
                    brace_count -= 1
                    if started and brace_count == 0:
                        block_end = i + 1
                        break

            planet_block = planets_chunk[block_start:block_end]

            # Check if this planet is owned by player
            # Look for owner=0 (but not original_owner=0)
            owner_match = re.search(r'\n\s*owner=(\d+)', planet_block)
            if not owner_match:
                continue

            owner_id = int(owner_match.group(1))
            if owner_id != player_id:
                continue

            planet_info = {'id': planet_id}

            # Extract name
            name_match = re.search(r'name=\s*\{\s*key="([^"]+)"', planet_block)
            if name_match:
                planet_info['name'] = name_match.group(1).replace('NAME_', '')

            # Extract planet class
            class_match = re.search(r'planet_class="([^"]+)"', planet_block)
            if class_match:
                planet_info['type'] = class_match.group(1).replace('pc_', '')

            # Skip stars and other non-habitable types
            ptype = planet_info.get('type', '')
            if ptype.endswith('_star') or ptype in ['asteroid', 'barren', 'barren_cold', 'molten', 'toxic', 'frozen', 'gas_giant']:
                continue

            # Extract planet size
            size_match = re.search(r'planet_size=(\d+)', planet_block)
            if size_match:
                planet_info['size'] = int(size_match.group(1))

            # Get population from pop_groups (accurate count via size field)
            planet_id_int = int(planet_id)
            planet_info['population'] = pop_by_planet.get(planet_id_int, 0)
            result['total_pops'] += planet_info['population']

            # Extract stability
            stability_match = re.search(r'\n\s*stability=([\d.]+)', planet_block)
            if stability_match:
                planet_info['stability'] = float(stability_match.group(1))

            # Extract amenities
            amenities_match = re.search(r'\n\s*amenities=([\d.]+)', planet_block)
            if amenities_match:
                planet_info['amenities'] = float(amenities_match.group(1))

            # Extract free amenities (surplus/deficit)
            free_amenities_match = re.search(r'\n\s*free_amenities=([-\d.]+)', planet_block)
            if free_amenities_match:
                planet_info['free_amenities'] = float(free_amenities_match.group(1))

            # Extract crime
            crime_match = re.search(r'\n\s*crime=([\d.]+)', planet_block)
            if crime_match:
                planet_info['crime'] = round(float(crime_match.group(1)), 1)

            # Extract permanent planet modifier
            pm_match = re.search(r'planet_modifier="([^"]+)"', planet_block)
            if pm_match:
                planet_info['planet_modifier'] = pm_match.group(1).replace('pm_', '')

            # Extract timed modifiers (crime, events, buffs)
            timed_mods = self._extract_timed_modifiers(planet_block)
            if timed_mods:
                planet_info['modifiers'] = timed_mods

            # Extract buildings - resolve IDs to building type names
            # Planet format: buildings={ { buildings={ ID1 ID2 ... } } }
            # These IDs reference the global buildings section
            building_types = self._get_building_types()
            buildings_match = re.search(r'buildings=\s*\{[^}]*buildings=\s*\{([^}]+)\}', planet_block)
            if buildings_match:
                building_ids = re.findall(r'\d+', buildings_match.group(1))
                resolved_buildings = []
                for bid in building_ids:
                    if bid in building_types:
                        resolved_buildings.append(building_types[bid].replace('building_', ''))
                if resolved_buildings:
                    planet_info['buildings'] = resolved_buildings

            # Extract districts info
            # Format: districts={ 0 59 60 61 } (numeric indices)
            districts_match = re.search(r'districts=\s*\{([^}]+)\}', planet_block)
            if districts_match:
                districts_block = districts_match.group(1)
                district_ids = re.findall(r'\d+', districts_block)
                planet_info['district_count'] = len(district_ids)

            # Extract last building/district changed for context
            last_building = re.search(r'last_building_changed="([^"]+)"', planet_block)
            if last_building:
                planet_info['last_building'] = last_building.group(1)

            last_district = re.search(r'last_district_changed="([^"]+)"', planet_block)
            if last_district:
                planet_info['last_district'] = last_district.group(1)

            planets_found.append(planet_info)

        # Full list (no truncation); callers that need caps should slice.
        result['planets'] = planets_found
        result['count'] = len(planets_found)

        # Summary by type
        type_counts = {}
        for planet in planets_found:
            ptype = planet.get('type', 'unknown')
            if ptype not in type_counts:
                type_counts[ptype] = 0
            type_counts[ptype] += 1

        result['by_type'] = type_counts

        return result

    def get_archaeology(self, limit: int = 25) -> dict:
        """Get archaeological dig sites and progress (summary-first, capped)."""
        limit = max(1, min(int(limit or 25), 50))

        result = {
            'sites': [],
            'count': 0,
        }

        section = self._extract_section('archaeological_sites')
        if not section:
            result['error'] = 'Could not find archaeological_sites section'
            return result

        # Extract sites={ ... } block.
        sites_match = re.search(r'\bsites\s*=\s*\{', section)
        if not sites_match:
            return result

        sites_start = sites_match.start()
        brace_count = 0
        sites_end = None
        started = False
        for i, ch in enumerate(section[sites_start:], sites_start):
            if ch == '{':
                brace_count += 1
                started = True
            elif ch == '}':
                brace_count -= 1
                if started and brace_count == 0:
                    sites_end = i + 1
                    break
        if sites_end is None:
            return result

        sites_block = section[sites_start:sites_end]

        site_pattern = r'\n\t\t(\d+)=\n\t\t\{'
        sites_found: list[dict] = []

        def extract_key_block(text: str, key: str) -> str | None:
            m = re.search(rf'\b{re.escape(key)}\s*=\s*\{{', text)
            if not m:
                return None
            start = m.start()
            brace_count = 0
            started = False
            for i, ch in enumerate(text[start:], start):
                if ch == '{':
                    brace_count += 1
                    started = True
                elif ch == '}':
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
                if ch == '{':
                    brace_count += 1
                    started = True
                elif ch == '}':
                    brace_count -= 1
                    if started and brace_count == 0:
                        block_end = i + 1
                        break
            if block_end is None:
                continue

            site_block = sites_block[block_start:block_end]

            entry = {
                'site_id': site_id,
                'type': None,
                'location': None,
                'index': None,
                'clues': None,
                'difficulty': None,
                'days_left': None,
                'locked': None,
                'last_excavator_country': None,
                'excavator_fleet': None,
                'completed_count': 0,
                'last_completed_date': None,
                'events_count': 0,
                'active_events_count': 0,
            }

            type_match = re.search(r'\btype="([^"]+)"', site_block)
            if type_match:
                entry['type'] = type_match.group(1)

            location_match = re.search(r'\blocation\s*=\s*\{\s*type=(\d+)\s*id=(\d+)\s*\}', site_block)
            if location_match:
                entry['location'] = {'type': int(location_match.group(1)), 'id': int(location_match.group(2))}

            for key in ['index', 'clues', 'difficulty', 'days_left', 'last_excavator_country', 'excavator_fleet']:
                m = re.search(rf'\b{key}=([-\d]+)', site_block)
                if m:
                    entry[key] = int(m.group(1))

            locked_match = re.search(r'\blocked=(yes|no)\b', site_block)
            if locked_match:
                entry['locked'] = locked_match.group(1) == 'yes'

            completed_block = extract_key_block(site_block, 'completed') or ''
            if completed_block:
                entry['completed_count'] = len(re.findall(r'\bcountry=(\d+)', completed_block))
                dates = re.findall(r'\bdate=\s*"(\d+\.\d+\.\d+)"', completed_block)
                if dates:
                    entry['last_completed_date'] = dates[-1]

            events_block = extract_key_block(site_block, 'events') or ''
            if events_block:
                event_ids = re.findall(r'\bevent_id="([^"]+)"', events_block)
                entry['events_count'] = len(event_ids)
                entry['active_events_count'] = len(re.findall(r'\bexpired=no\b', events_block))

            sites_found.append(entry)
            if len(sites_found) >= limit:
                break

        result['sites'] = sites_found
        result['count'] = len(sites_found)
        return result

    def _extract_timed_modifiers(self, planet_block: str) -> list[dict]:
        """Extract timed modifiers from a planet block.

        Timed modifiers include crime events, prosperity buffs, etc.

        Returns:
            List of modifiers with name and days remaining
        """
        modifiers = []

        # Find timed_modifier block
        tm_match = re.search(r'timed_modifier\s*=\s*\{', planet_block)
        if not tm_match:
            return modifiers

        # Extract the timed_modifier block
        start = tm_match.start()
        brace_count = 0
        end = None
        for i, char in enumerate(planet_block[start:], start):
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    end = i + 1
                    break

        if end is None:
            return modifiers

        tm_block = planet_block[start:end]

        # Find items block
        items_match = re.search(r'items\s*=\s*\{', tm_block)
        if not items_match:
            return modifiers

        # Extract individual modifier entries
        # Format: { modifier="name" days=N }
        for match in re.finditer(r'\{\s*modifier="([^"]+)"\s*days=([-\d]+)\s*\}', tm_block):
            mod_name = match.group(1)
            days = int(match.group(2))

            # Clean up modifier name for display
            display_name = mod_name.replace('_', ' ').title()

            modifiers.append({
                'name': mod_name,
                'display_name': display_name,
                'days': days,  # -1 means permanent
                'permanent': days < 0,
            })

        return modifiers

    def get_problem_planets(self) -> dict:
        """Get planets with issues (high crime, low stability, amenity deficit).

        Returns:
            Dict with lists of planets grouped by problem type
        """
        planets_data = self.get_planets()
        planets = planets_data.get('planets', [])

        result = {
            'high_crime': [],      # Crime > 25%
            'low_stability': [],   # Stability < 50
            'amenity_deficit': [], # Free amenities < 0
            'problem_count': 0,
        }

        for planet in planets:
            problems = []

            crime = planet.get('crime', 0)
            if crime > 25:
                problems.append(f"crime {crime:.0f}%")
                result['high_crime'].append({
                    'name': planet.get('name', 'Unknown'),
                    'crime': crime,
                    'modifiers': planet.get('modifiers', []),
                })

            stability = planet.get('stability', 100)
            if stability < 50:
                problems.append(f"stability {stability:.0f}")
                result['low_stability'].append({
                    'name': planet.get('name', 'Unknown'),
                    'stability': stability,
                })

            free_amenities = planet.get('free_amenities', 0)
            if free_amenities < 0:
                problems.append(f"amenities {free_amenities:.0f}")
                result['amenity_deficit'].append({
                    'name': planet.get('name', 'Unknown'),
                    'deficit': free_amenities,
                })

        result['problem_count'] = (
            len(result['high_crime']) +
            len(result['low_stability']) +
            len(result['amenity_deficit'])
        )

        return result

    def _get_population_by_planet(self) -> dict[int, int]:
        """Build a mapping of planet_id -> total population from pop_groups.

        The pop_groups section aggregates pops by type (species, job category, ethics)
        with a 'size' field showing the actual number of pops in each group.
        This is the accurate way to count population, NOT pop_jobs which only
        lists job assignment IDs.

        Returns:
            Dict mapping planet_id (int) to total population (int)
        """
        pop_by_planet: dict[int, int] = {}

        # Find pop_groups section
        pop_groups_match = re.search(r'\npop_groups=\n\{', self.gamestate)
        if not pop_groups_match:
            # Try alternate format
            pop_groups_match = re.search(r'^pop_groups=\s*\{', self.gamestate, re.MULTILINE)
            if not pop_groups_match:
                return pop_by_planet

        pg_start = pop_groups_match.start()
        # Pop groups section can be very large in late game
        pg_chunk = self.gamestate[pg_start:pg_start + 100000000]  # Up to 100MB

        # Parse each pop_group entry: \n\tID=\n\t{ ... planet=X size=N ... }
        pop_pattern = r'\n\t(\d+)=\n\t\{'
        groups_processed = 0
        max_groups = 100000  # Safety limit

        for match in re.finditer(pop_pattern, pg_chunk):
            if groups_processed >= max_groups:
                break

            groups_processed += 1
            block_start = match.start() + 1

            # Get pop group block content (they're relatively small)
            chunk = pg_chunk[block_start:block_start + 2500]

            # Find end of this pop group's block
            brace_count = 0
            block_end = 0
            started = False
            for i, char in enumerate(chunk):
                if char == '{':
                    brace_count += 1
                    started = True
                elif char == '}':
                    brace_count -= 1
                    if started and brace_count == 0:
                        block_end = i + 1
                        break

            if block_end == 0:
                continue

            pop_block = chunk[:block_end]

            # Extract planet ID
            planet_match = re.search(r'\n\s*planet=(\d+)', pop_block)
            if not planet_match:
                continue

            planet_id = int(planet_match.group(1))

            # Extract size (actual number of pops in this group)
            size_match = re.search(r'\n\s*size=(\d+)', pop_block)
            if not size_match:
                continue

            pop_size = int(size_match.group(1))
            if pop_size > 0:
                pop_by_planet[planet_id] = pop_by_planet.get(planet_id, 0) + pop_size

        return pop_by_planet
