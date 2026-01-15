from __future__ import annotations

import re
import zipfile
from datetime import datetime
from pathlib import Path

class SaveExtractorBase:
    """Base implementation: file I/O, caches, and shared parsing helpers."""

    def __init__(self, save_path: str):
        """Load and parse a Stellaris save file.

        Args:
            save_path: Path to the .sav file
        """
        self.save_path = Path(save_path)
        self.meta = None
        self.gamestate = None
        self._load_save()

        # Cache for parsed sections
        self._section_cache = {}
        self._building_types = None  # Lazy-loaded building ID→type map

    def _get_building_types(self) -> dict:
        """Parse the global buildings section to get ID→type mapping.

        Returns:
            Dict mapping building IDs (as strings) to building type names
        """
        if self._building_types is not None:
            return self._building_types

        self._building_types = {}

        # Find the top-level buildings section (near end of file)
        match = re.search(r'^buildings=\s*\{', self.gamestate, re.MULTILINE)
        if not match:
            return self._building_types

        start = match.start()
        # Parse entries like: 50331648={ type="building_ministry_production" position=0 }
        chunk = self.gamestate[start:start + 5000000]  # Buildings section can be large

        for m in re.finditer(r'(\d+)=\s*\{\s*type="([^"]+)"', chunk):
            building_id = m.group(1)
            building_type = m.group(2)
            self._building_types[building_id] = building_type

        return self._building_types

    def _load_save(self):
        """Extract gamestate and meta from the save file."""
        with zipfile.ZipFile(self.save_path, 'r') as z:
            self.gamestate = z.read('gamestate').decode('utf-8', errors='replace')
            self.meta = z.read('meta').decode('utf-8', errors='replace')

    def _find_section_bounds(self, section_name: str) -> tuple[int, int] | None:
        """Find the start and end positions of a top-level section.

        Args:
            section_name: Name of section (e.g., 'country', 'wars', 'fleets')

        Returns:
            Tuple of (start, end) positions, or None if not found
        """
        # Look for "section_name={" or "section_name ={" at start of line
        pattern = rf'^{section_name}\s*=\s*\{{'
        match = re.search(pattern, self.gamestate, re.MULTILINE)

        if not match:
            return None

        start = match.start()

        # Find matching closing brace
        brace_count = 0
        in_section = False

        for i, char in enumerate(self.gamestate[start:], start):
            if char == '{':
                brace_count += 1
                in_section = True
            elif char == '}':
                brace_count -= 1
                if in_section and brace_count == 0:
                    return (start, i + 1)

        return None

    def _extract_section(self, section_name: str) -> str | None:
        """Extract a complete top-level section.

        Args:
            section_name: Name of section to extract

        Returns:
            Section content as string, or None if not found
        """
        if section_name in self._section_cache:
            return self._section_cache[section_name]

        bounds = self._find_section_bounds(section_name)
        if bounds:
            content = self.gamestate[bounds[0]:bounds[1]]
            self._section_cache[section_name] = content
            return content
        return None

    def _extract_nested_block(self, content: str, key: str, value: str) -> str | None:
        """Extract a nested block where key=value.

        Args:
            content: Text to search in
            key: Key to match (e.g., 'name')
            value: Value to match (e.g., 'United Nations of Earth')

        Returns:
            The containing block, or None
        """
        # Find the value
        pattern = rf'{key}\s*=\s*"{re.escape(value)}"'
        match = re.search(pattern, content)

        if not match:
            return None

        # Walk backwards to find the opening brace of the containing block
        pos = match.start()
        brace_count = 0
        block_start = 0

        for i in range(pos, -1, -1):
            if content[i] == '}':
                brace_count += 1
            elif content[i] == '{':
                if brace_count == 0:
                    # Find the key before this brace
                    block_start = content.rfind('\n', 0, i) + 1
                    break
                brace_count -= 1

        # Now find the matching closing brace
        brace_count = 0
        for i in range(block_start, len(content)):
            if content[i] == '{':
                brace_count += 1
            elif content[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    return content[block_start:i + 1]

        return None

    def _find_country_section_start(self) -> int:
        """Find the start of the country={} block (not country=0 simple value).

        The gamestate has both:
        - country=0 (simple value near start, ~line 10)
        - country=\\n{\\n\\t0=... (actual countries block, deep in file)

        Returns:
            Position of 'country=' for the block, or -1 if not found
        """
        # Look for country= followed by newline and opening brace
        # This distinguishes from country=0 (simple value)
        match = re.search(r'\ncountry=\n\{', self.gamestate)
        if match:
            return match.start() + 1  # +1 to skip the leading \n
        return -1

    def _find_player_country_content(self, player_id: int = 0) -> str | None:
        """Get the content of the player's country block.

        Args:
            player_id: The player's country ID (usually 0)

        Returns:
            String content of the country block, or None if not found
        """
        section_start = self._find_country_section_start()
        if section_start == -1:
            return None

        # Get a large chunk starting from the country section
        chunk = self.gamestate[section_start:section_start + 1000000]

        # Find the player's country entry: \n\t{player_id}=\n\t{
        pattern = rf'\n\t{player_id}=\n\t\{{'
        match = re.search(pattern, chunk)
        if not match:
            return None

        start = match.start()

        # Find the next country entry to determine the end
        next_pattern = rf'\n\t(?:{player_id + 1}|\d+)=\n\t\{{'
        next_match = re.search(next_pattern, chunk[start + 10:])
        if next_match:
            end = start + 10 + next_match.start()
        else:
            end = min(start + 500000, len(chunk))

        return chunk[start:end]

    def _find_fleet_section_start(self) -> int:
        """Find the start of the fleet={} block.

        Returns:
            Position of 'fleet=' for the block, or -1 if not found
        """
        # Look for fleet= followed by newline and opening brace
        match = re.search(r'\nfleet=\n\{', self.gamestate)
        if match:
            return match.start() + 1
        return -1

    def _get_owned_fleet_ids(self, country_content: str) -> list[str]:
        """Extract fleet IDs from owned_fleets section.

        The country block has:
        - fleets={...} - fleets the player can SEE (has intel on)
        - owned_fleets={...} - fleets the player actually OWNS

        Args:
            country_content: Content of the player's country block

        Returns:
            List of fleet ID strings that the player owns
        """
        # Find owned_fleets section
        owned_match = re.search(r'owned_fleets=\s*\{', country_content)
        if not owned_match:
            return []

        # Get content after owned_fleets={
        content = country_content[owned_match.end():]

        # Extract all fleet=N values until we hit a section at lower indent
        # The structure is: owned_fleets=\n\t\t\t{\n\t\t\t\t{\n\t\t\t\t\tfleet=0\n\t\t\t\t}\n...
        fleet_ids = []
        for match in re.finditer(r'fleet=(\d+)', content[:15000]):
            fleet_ids.append(match.group(1))

        return fleet_ids

    def _get_ship_to_fleet_mapping(self) -> dict[str, str]:
        """Build a mapping of ship IDs to their fleet IDs.

        Returns:
            Dict mapping ship_id (str) -> fleet_id (str)
        """
        ships_match = re.search(r'^ships=\s*\{', self.gamestate, re.MULTILINE)
        if not ships_match:
            return {}

        ship_to_fleet = {}
        ships_chunk = self.gamestate[ships_match.start():ships_match.start() + 80000000]

        # Find each ship entry and extract its fleet ID
        # Ships may have auras={} or other blocks before fleet=
        ship_entries = list(re.finditer(r'\n\t(\d+)=\n\t\{', ships_chunk))

        for i, entry in enumerate(ship_entries):
            ship_id = entry.group(1)

            # Get content until next ship entry or 3000 chars
            start = entry.start() + 1
            if i + 1 < len(ship_entries):
                end = min(ship_entries[i + 1].start(), start + 3000)
            else:
                end = start + 3000

            content = ships_chunk[start:end]

            # Find fleet= anywhere in this ship's content
            fleet_m = re.search(r'\n\t\tfleet=(\d+)', content)
            if fleet_m:
                ship_to_fleet[ship_id] = fleet_m.group(1)

        return ship_to_fleet

    def _get_player_owned_fleet_ids(self) -> set[str]:
        """Get all fleet IDs owned by the player.

        Uses fleets_manager.owned_fleets from the player's country data.

        Returns:
            Set of fleet ID strings owned by the player
        """
        owned_fleet_ids = set()

        # Find country section
        country_match = re.search(r'\ncountry=\n\{', self.gamestate)
        if not country_match:
            return owned_fleet_ids

        country_start = country_match.start() + 1
        country_chunk = self.gamestate[country_start:country_start + 2000000]

        # Find player country (usually 0=)
        player_id = self.get_player_empire_id()
        player_pattern = rf'\n\t{player_id}=\n\t\{{'
        player_match = re.search(player_pattern, country_chunk)
        if not player_match:
            return owned_fleet_ids

        player_content = country_chunk[player_match.start():player_match.start() + 500000]

        # Find fleets_manager.owned_fleets
        fleets_mgr_match = re.search(r'fleets_manager=\s*\{', player_content)
        if not fleets_mgr_match:
            return owned_fleet_ids

        content = player_content[fleets_mgr_match.start():fleets_mgr_match.start() + 50000]
        for m in re.finditer(r'fleet=(\d+)', content):
            owned_fleet_ids.add(m.group(1))

        return owned_fleet_ids

    def _count_player_starbases(self, owned_fleet_ids: set[str] = None) -> dict:
        """Count player's starbases by level using ship→fleet ownership chain.

        Traces ownership: starbase.station (ship ID) → ship.fleet → player's owned_fleets

        Args:
            owned_fleet_ids: Optional pre-computed set of player fleet IDs

        Returns:
            Dict with starbase counts by level and totals
        """
        result = {
            'citadels': 0,
            'star_fortresses': 0,
            'starholds': 0,
            'starports': 0,
            'outposts': 0,
            'orbital_rings': 0,
            'total_upgraded': 0,  # Non-outpost, non-orbital starbases (count against capacity)
            'total_systems': 0,   # Systems owned (starbases excluding orbital rings)
            'total': 0,           # All starbases including orbital rings
        }

        # Get player's owned fleet IDs
        if owned_fleet_ids is None:
            owned_fleet_ids = self._get_player_owned_fleet_ids()

        if not owned_fleet_ids:
            return result

        # Build ship→fleet mapping
        ship_to_fleet = self._get_ship_to_fleet_mapping()
        if not ship_to_fleet:
            return result

        # Find starbase_mgr section
        starbase_match = re.search(r'^starbase_mgr=\s*\{', self.gamestate, re.MULTILINE)
        if not starbase_match:
            return result

        sb_chunk = self.gamestate[starbase_match.start():starbase_match.start() + 5000000]

        # Parse each starbase entry
        for m in re.finditer(r'\n\t\t(\d+)=\n\t\t\{', sb_chunk):
            sb_id = m.group(1)
            content = sb_chunk[m.start():m.start() + 2000]

            # Get level and station (ship ID)
            level_m = re.search(r'level="([^"]+)"', content)
            station_m = re.search(r'\n\t\t\tstation=(\d+)\n', content)

            if not station_m:
                continue

            ship_id = station_m.group(1)
            level = level_m.group(1) if level_m else 'unknown'

            # Trace ownership: ship → fleet → player?
            fleet_id = ship_to_fleet.get(ship_id)
            if not fleet_id or fleet_id not in owned_fleet_ids:
                continue

            # This starbase belongs to the player
            result['total'] += 1

            if 'citadel' in level:
                result['citadels'] += 1
                result['total_upgraded'] += 1
                result['total_systems'] += 1
            elif 'starfortress' in level:
                result['star_fortresses'] += 1
                result['total_upgraded'] += 1
                result['total_systems'] += 1
            elif 'starhold' in level:
                result['starholds'] += 1
                result['total_upgraded'] += 1
                result['total_systems'] += 1
            elif 'starport' in level:
                result['starports'] += 1
                result['total_upgraded'] += 1
                result['total_systems'] += 1
            elif 'orbital_ring' in level:
                result['orbital_rings'] += 1
                # Orbital rings don't count against starbase capacity or as systems
            elif 'outpost' in level:
                result['outposts'] += 1
                result['total_systems'] += 1

        return result

    def _get_country_names_map(self) -> dict:
        """Build a mapping of country ID -> country name for all empires.

        Returns:
            Dict mapping integer country IDs to their empire names
        """
        country_names = {}

        country_start = self._find_country_section_start()
        if country_start == -1:
            return country_names

        # Get a chunk of the country section
        country_chunk = self.gamestate[country_start:country_start + 10000000]

        # Find entries like \n\t0=\n\t{ ... name="United Nations of Earth" ... }
        # Parse each country block to extract ID and name
        country_entry_pattern = r'\n\t(\d+)=\n\t\{'
        entries = list(re.finditer(country_entry_pattern, country_chunk))

        for i, entry_match in enumerate(entries[:200]):  # Limit to first 200 countries for performance
            country_id = int(entry_match.group(1))
            entry_start = entry_match.start()

            # Determine block end
            if i + 1 < len(entries):
                entry_end = entries[i + 1].start()
            else:
                entry_end = min(entry_start + 50000, len(country_chunk))

            block = country_chunk[entry_start:entry_end]

            # Extract name - can be either:
            # 1. name="Direct Name" (simple string)
            # 2. name={ key="LOCALIZATION_KEY" } (localization reference)
            # First try direct string format
            name_match = re.search(r'\n\t\tname\s*=\s*"([^"]+)"', block)
            if name_match:
                country_names[country_id] = name_match.group(1)
            else:
                # Try localization key format: name={ key="..." }
                key_match = re.search(r'\n\t\tname\s*=\s*\{\s*key\s*=\s*"([^"]+)"', block)
                if key_match:
                    # Use the key as a fallback, cleaned up for readability
                    key = key_match.group(1)
                    # Convert EMPIRE_DESIGN_humans1 to "Humans 1" for readability
                    readable = key.replace('EMPIRE_DESIGN_', '').replace('_', ' ').title()
                    country_names[country_id] = readable

        return country_names

    def _analyze_player_fleets(self, fleet_ids: list[str], max_to_analyze: int = 1500) -> dict:
        """Analyze player's fleet IDs to categorize them properly.

        This distinguishes between:
        - Starbases (station=yes)
        - Military fleets (non-station, military_power > 0)
        - Civilian fleets (science ships, construction ships, transports)

        Args:
            fleet_ids: List of fleet ID strings from player's country block
            max_to_analyze: Max fleets to analyze in detail (for performance)

        Returns:
            Dict with categorized fleet counts and details
        """
        result = {
            'total_fleet_ids': len(fleet_ids),
            'starbase_count': 0,
            'military_fleet_count': 0,
            'civilian_fleet_count': 0,
            'military_ships': 0,
            'total_military_power': 0.0,
            'military_fleets': [],  # List of military fleet details
        }

        # Find the fleet section using robust detection
        fleet_section_start = self._find_fleet_section_start()
        if fleet_section_start == -1:
            return result

        fleet_section = self.gamestate[fleet_section_start:]

        # Analyze fleets (limit for performance in huge saves)
        analyzed = 0
        for fid in fleet_ids:
            if analyzed >= max_to_analyze:
                # Estimate remaining based on ratios
                ratio = len(fleet_ids) / max_to_analyze
                result['starbase_count'] = int(result['starbase_count'] * ratio)
                result['military_fleet_count'] = int(result['military_fleet_count'] * ratio)
                result['civilian_fleet_count'] = int(result['civilian_fleet_count'] * ratio)
                result['_note'] = f'Estimated from {max_to_analyze} of {len(fleet_ids)} fleet IDs'
                break

            # Pattern must match fleet ID at start of line with tab indent
            # This avoids matching ship IDs inside other fleet blocks
            pattern = rf'\n\t{fid}=\n\t\{{'
            match = re.search(pattern, fleet_section)
            if not match:
                continue

            # Extract full fleet block using brace matching for location data
            fleet_block = self._extract_fleet_block(fleet_section, match.start())
            fleet_data = fleet_block[:2500] if fleet_block else fleet_section[match.start():match.start() + 2500]
            analyzed += 1

            is_station = 'station=yes' in fleet_data
            is_civilian = 'civilian=yes' in fleet_data

            # Count ships
            ships_match = re.search(r'ships=\s*\{([^}]+)\}', fleet_data)
            ship_count = len(ships_match.group(1).split()) if ships_match else 0

            # Get military power
            mp_match = re.search(r'military_power=([\d.]+)', fleet_data)
            mp = float(mp_match.group(1)) if mp_match else 0.0

            if is_station:
                result['starbase_count'] += 1
            elif is_civilian:
                result['civilian_fleet_count'] += 1
            elif mp > 100:  # Threshold filters out space creatures with tiny mp
                result['military_fleet_count'] += 1
                result['military_ships'] += ship_count
                result['total_military_power'] += mp

                # Extract fleet name for military fleets
                name_match = re.search(r'key="([^"]+)"', fleet_data)
                fleet_name = name_match.group(1) if name_match else f"Fleet {fid}"
                # Clean up localization keys
                if fleet_name.startswith('shipclass_'):
                    fleet_name = fleet_name.replace('shipclass_', '').replace('_name', '').title()

                # Extract location data from movement_manager block
                location_data = self._extract_fleet_location(fleet_block) if fleet_block else {}

                if len(result['military_fleets']) < 20:  # Keep top 20
                    fleet_entry = {
                        'id': fid,
                        'name': fleet_name,
                        'ships': ship_count,
                        'military_power': round(mp, 0),
                    }
                    # Add location fields
                    fleet_entry['system_id'] = location_data.get('system_id')
                    fleet_entry['status'] = location_data.get('status', 'unknown')
                    fleet_entry['orbiting_planet_id'] = location_data.get('orbiting_planet_id')
                    fleet_entry['destination_system_id'] = location_data.get('destination_system_id')
                    result['military_fleets'].append(fleet_entry)
            else:
                result['civilian_fleet_count'] += 1

        return result

    def _extract_fleet_block(self, fleet_section: str, start_pos: int) -> str | None:
        """Extract complete fleet block using brace matching.

        Args:
            fleet_section: The fleet section content
            start_pos: Starting position of the fleet entry

        Returns:
            Complete fleet block string, or None if extraction fails
        """
        brace_count = 0
        started = False
        max_len = min(start_pos + 15000, len(fleet_section))  # Fleet blocks can be large

        for i in range(start_pos, max_len):
            char = fleet_section[i]
            if char == '{':
                brace_count += 1
                started = True
            elif char == '}':
                brace_count -= 1
                if started and brace_count == 0:
                    return fleet_section[start_pos:i + 1]

        return None

    def _extract_fleet_location(self, fleet_block: str) -> dict:
        """Extract location data from a fleet block's movement_manager.

        Args:
            fleet_block: Complete fleet block content

        Returns:
            Dict with:
              - system_id: Current system ID (from coordinate.origin)
              - status: 'idle', 'moving', 'in_combat', 'retreating', or 'unknown'
              - orbiting_planet_id: Planet ID if orbiting, None otherwise
              - destination_system_id: Target system if moving, None otherwise
        """
        result = {
            'system_id': None,
            'status': 'unknown',
            'orbiting_planet_id': None,
            'destination_system_id': None,
        }

        # Find movement_manager block
        mm_match = re.search(r'movement_manager=\s*\{', fleet_block)
        if not mm_match:
            return result

        # Extract movement_manager block using brace matching
        mm_start = mm_match.start()
        brace_count = 0
        started = False
        mm_end = mm_start

        for i in range(mm_start, min(mm_start + 5000, len(fleet_block))):
            char = fleet_block[i]
            if char == '{':
                brace_count += 1
                started = True
            elif char == '}':
                brace_count -= 1
                if started and brace_count == 0:
                    mm_end = i + 1
                    break

        mm_block = fleet_block[mm_start:mm_end]

        # Extract current system from coordinate.origin
        # Pattern: coordinate=\n\t\t\t{\n\t\t\t\tx=...\n\t\t\t\ty=...\n\t\t\t\torigin=SYSTEM_ID
        coord_match = re.search(r'coordinate=\s*\{[^}]*origin=(\d+)', mm_block)
        if coord_match:
            origin = int(coord_match.group(1))
            if origin != 4294967295:  # Not null
                result['system_id'] = origin

        # Extract state and map to simplified status
        state_match = re.search(r'\bstate=(move_\w+)', mm_block)
        if state_match:
            state = state_match.group(1)
            # Map Stellaris states to simplified status
            state_mapping = {
                'move_idle': 'idle',
                'move_system': 'moving',
                'move_galaxy': 'moving',
                'move_wind_up': 'moving',
                'move_jump_anim': 'moving',
                'move_to_system': 'moving',
                'move_to_planet': 'moving',
                'move_in_combat': 'in_combat',
                'move_retreat': 'retreating',
            }
            result['status'] = state_mapping.get(state, 'unknown')

        # Extract orbiting planet from orbit.orbitable.planet
        # Pattern: orbit=\n\t\t\t{\n\t\t\t\torbitable=\n\t\t\t\t{\n\t\t\t\t\tplanet=PLANET_ID
        orbit_match = re.search(r'orbit=\s*\{[^}]*orbitable=\s*\{[^}]*planet=(\d+)', mm_block)
        if orbit_match:
            planet_id = int(orbit_match.group(1))
            if planet_id != 4294967295:  # Not null
                result['orbiting_planet_id'] = planet_id

        # Extract destination system from target_coordinate.origin
        target_match = re.search(r'target_coordinate=\s*\{[^}]*origin=(\d+)', mm_block)
        if target_match:
            target_origin = int(target_match.group(1))
            if target_origin != 4294967295:  # Not null
                result['destination_system_id'] = target_origin

        return result

    def _get_species_names(self) -> dict:
        """Build a mapping of species IDs to their display names.

        Returns:
            Dict mapping species ID (as string) to species name
        """
        species_names = {}

        # Find the species_db section (near start of file)
        species_match = re.search(r'^species_db=\s*\{', self.gamestate, re.MULTILINE)
        if not species_match:
            # Fallback: try older format
            species_match = re.search(r'^species=\s*\{', self.gamestate, re.MULTILINE)
            if not species_match:
                return species_names

        start = species_match.start()
        # Species section is usually within first 2MB
        species_chunk = self.gamestate[start:start + 2000000]

        # Parse species entries: ID={ ... name="Species Name" ... }
        # Format: \n\tID=\n\t{ ... name="Name" ...
        species_pattern = r'\n\t(\d+)=\s*\{'
        for match in re.finditer(species_pattern, species_chunk):
            species_id = match.group(1)
            block_start = match.start()

            # Get a chunk for this species entry (they're typically < 1000 chars)
            block_chunk = species_chunk[block_start:block_start + 1500]

            # Extract name
            name_match = re.search(r'name="([^"]+)"', block_chunk)
            if name_match:
                species_names[species_id] = name_match.group(1)
            else:
                # Fallback: use species class as name
                class_match = re.search(r'class="([^"]+)"', block_chunk)
                if class_match:
                    species_names[species_id] = class_match.group(1)

        return species_names

    def _get_player_planet_ids(self) -> list[str]:
        """Get IDs of all planets owned by the player.

        Returns:
            List of planet ID strings
        """
        player_id = self.get_player_empire_id()
        planet_ids = []

        # Find the planets section
        planets_match = re.search(r'^planets=\s*\{\s*planet=\s*\{', self.gamestate, re.MULTILINE)
        if not planets_match:
            return planet_ids

        start = planets_match.start()
        planets_chunk = self.gamestate[start:start + 20000000]  # 20MB for planets

        # Find each planet and check ownership
        planet_start_pattern = r'\n\t\t(\d+)=\s*\{'
        for match in re.finditer(planet_start_pattern, planets_chunk):
            planet_id = match.group(1)
            block_start = match.start() + 1

            # Get first 3000 chars to find owner (owner is near start of block)
            block_chunk = planets_chunk[block_start:block_start + 3000]

            # Check if owned by player
            owner_match = re.search(r'\n\s*owner=(\d+)', block_chunk)
            if owner_match and int(owner_match.group(1)) == player_id:
                planet_ids.append(planet_id)

        return planet_ids

    def _get_pop_ids_for_planets(self, planet_ids: list[str]) -> list[str]:
        """Get all pop IDs from the specified planets.

        Args:
            planet_ids: List of planet ID strings to get pops from

        Returns:
            List of pop ID strings
        """
        pop_ids = []

        # Find the planets section
        planets_match = re.search(r'^planets=\s*\{\s*planet=\s*\{', self.gamestate, re.MULTILINE)
        if not planets_match:
            return pop_ids

        start = planets_match.start()
        planets_chunk = self.gamestate[start:start + 20000000]

        planet_id_set = set(planet_ids)

        # Find each planet block and extract pop_jobs
        planet_start_pattern = r'\n\t\t(\d+)=\s*\{'
        for match in re.finditer(planet_start_pattern, planets_chunk):
            planet_id = match.group(1)
            if planet_id not in planet_id_set:
                continue

            block_start = match.start() + 1

            # Find end of planet block (they can be large with pop data)
            brace_count = 0
            block_end = block_start
            started = False
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

            # Extract pop_jobs list
            pop_jobs_match = re.search(r'pop_jobs=\s*\{([^}]+)\}', planet_block)
            if pop_jobs_match:
                ids = re.findall(r'\d+', pop_jobs_match.group(1))
                pop_ids.extend(ids)

        return pop_ids

    def _strip_previews(self, data: dict) -> dict:
        """Remove raw_data_preview fields to reduce context size.

        Args:
            data: Dictionary that may contain preview fields

        Returns:
            Dictionary with preview fields removed
        """
        if not isinstance(data, dict):
            return data
        return {k: v for k, v in data.items() if 'preview' not in k.lower()}

