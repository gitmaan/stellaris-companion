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

            # Count pops from pop_jobs list
            pop_jobs_match = re.search(r'pop_jobs=\s*\{([^}]+)\}', planet_block)
            if pop_jobs_match:
                pop_ids = re.findall(r'\d+', pop_jobs_match.group(1))
                planet_info['population'] = len(pop_ids)
                result['total_pops'] += len(pop_ids)
            else:
                planet_info['population'] = 0

            # Extract stability
            stability_match = re.search(r'\n\s*stability=([\d.]+)', planet_block)
            if stability_match:
                planet_info['stability'] = float(stability_match.group(1))

            # Extract amenities
            amenities_match = re.search(r'\n\s*amenities=([\d.]+)', planet_block)
            if amenities_match:
                planet_info['amenities'] = float(amenities_match.group(1))

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

        result['planets'] = planets_found[:50]  # Limit to 50 planets
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
