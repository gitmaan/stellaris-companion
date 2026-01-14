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

