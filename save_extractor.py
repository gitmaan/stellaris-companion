"""
Save Extractor for Stellaris Save Files
========================================

Extracts specific sections from Clausewitz format gamestate files.
Used by both native SDK and ADK tool implementations.
"""

import zipfile
import re
from pathlib import Path
from datetime import datetime


class SaveExtractor:
    """Extract and query sections from a Stellaris save file."""

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

    def get_metadata(self) -> dict:
        """Get basic save metadata.

        Returns:
            Dict with empire name, date, version, etc.
        """
        result = {
            'file_path': str(self.save_path),
            'file_size_mb': self.save_path.stat().st_size / (1024 * 1024),
            'gamestate_chars': len(self.gamestate),
            'modified': datetime.fromtimestamp(self.save_path.stat().st_mtime).isoformat(),
        }

        # Parse meta file
        for line in self.meta.split('\n'):
            if '=' in line and 'flag' not in line.lower():
                key, _, value = line.partition('=')
                key = key.strip()
                value = value.strip().strip('"')
                if key in ['version', 'name', 'date']:
                    result[key] = value

        return result

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

    def get_player_empire_id(self) -> int:
        """Get the player's country ID.

        Returns:
            Player country ID (usually 0)
        """
        # Look for player={ section
        match = re.search(r'player\s*=\s*\{[^}]*country\s*=\s*(\d+)', self.gamestate[:5000])
        if match:
            return int(match.group(1))
        return 0  # Default to 0

    def get_player_status(self) -> dict:
        """Get the player's current empire status with clear, unambiguous metrics.

        Returns:
            Dict with empire info, military, economy, and territory data.
            All field names are self-documenting to prevent LLM misinterpretation.
        """
        player_id = self.get_player_empire_id()

        result = {
            'player_id': player_id,
            'empire_name': self.get_metadata().get('name', 'Unknown'),
            'date': self.get_metadata().get('date', 'Unknown'),
        }

        # Get the player's country block using proper section detection
        country_content = self._find_player_country_content(player_id)

        if country_content:
            # Extract metrics from the player's country block
            metrics = {
                'military_power': r'military_power\s*=\s*([\d.]+)',
                'economy_power': r'economy_power\s*=\s*([\d.]+)',
                'tech_power': r'tech_power\s*=\s*([\d.]+)',
                'victory_rank': r'victory_rank\s*=\s*(\d+)',
                'fleet_size': r'fleet_size\s*=\s*(\d+)',
            }

            for key, pattern in metrics.items():
                match = re.search(pattern, country_content)
                if match:
                    value = match.group(1)
                    result[key] = float(value) if '.' in value else int(value)

            # Get OWNED fleets (not just visible fleets)
            owned_fleet_ids = self._get_owned_fleet_ids(country_content)
            owned_set = set(owned_fleet_ids)

            if owned_fleet_ids:
                # Analyze the owned fleets
                fleet_analysis = self._analyze_player_fleets(owned_fleet_ids)
                result['military_fleet_count'] = fleet_analysis['military_fleet_count']
                result['military_ships'] = fleet_analysis['military_ships']
                # Keep fleet_count for backwards compatibility
                result['fleet_count'] = fleet_analysis['military_fleet_count']

                # Get accurate starbase count from starbase_mgr
                starbase_info = self._count_player_starbases(owned_set)
                result['starbase_count'] = starbase_info['total_upgraded']
                result['outpost_count'] = starbase_info['outposts']
                result['starbases'] = starbase_info

            # Find controlled planets (all celestial bodies in territory)
            controlled_match = re.search(r'controlled_planets\s*=\s*\{([^}]+)\}', country_content)
            if controlled_match:
                planet_ids = re.findall(r'\d+', controlled_match.group(1))
                result['celestial_bodies_in_territory'] = len(planet_ids)

        # Get colonized planets data (actual colonies with population)
        # This is the TRUE planet count that matters for empire management
        planets_data = self.get_planets()
        colonies = planets_data.get('planets', [])
        total_pops = sum(p.get('population', 0) for p in colonies)

        # Separate habitats from planets (different pop capacities)
        habitats = [c for c in colonies if c.get('type', '').startswith('habitat')]
        regular_planets = [c for c in colonies if not c.get('type', '').startswith('habitat')]

        habitat_pops = sum(p.get('population', 0) for p in habitats)
        planet_pops = sum(p.get('population', 0) for p in regular_planets)

        result['colonies'] = {
            'total_count': len(colonies),
            'total_population': total_pops,
            'avg_pops_per_colony': round(total_pops / len(colonies), 1) if colonies else 0,
            '_note': 'These are colonized worlds with population, not all celestial bodies',
            # Breakdown by type for more accurate analysis
            'habitats': {
                'count': len(habitats),
                'population': habitat_pops,
                'avg_pops': round(habitat_pops / len(habitats), 1) if habitats else 0,
            },
            'planets': {
                'count': len(regular_planets),
                'population': planet_pops,
                'avg_pops': round(planet_pops / len(regular_planets), 1) if regular_planets else 0,
            },
        }

        return result

    def get_empire(self, name: str) -> dict:
        """Get detailed information about a specific empire.

        Args:
            name: Empire name to search for

        Returns:
            Dict with empire details
        """
        result = {'name': name, 'found': False}

        country_section = self._extract_section('country')
        if not country_section:
            result['error'] = "Could not find country section"
            return result

        # Search for empire by name
        pattern = rf'name\s*=\s*"{re.escape(name)}"'
        match = re.search(pattern, country_section)

        if not match:
            # Try partial match
            pattern = rf'name\s*=\s*"[^"]*{re.escape(name)}[^"]*"'
            match = re.search(pattern, country_section, re.IGNORECASE)

        if match:
            result['found'] = True

            # Extract surrounding context (the country block)
            # Go back to find the country ID
            pos = match.start()
            block_start = country_section.rfind('\n\t', 0, pos)

            # Find the end of this block
            brace_count = 0
            started = False
            empire_data = ""

            for i, char in enumerate(country_section[block_start:], block_start):
                empire_data += char
                if char == '{':
                    brace_count += 1
                    started = True
                elif char == '}':
                    brace_count -= 1
                    if started and brace_count == 0:
                        break

            result['raw_data_preview'] = empire_data[:8000] + "..." if len(empire_data) > 8000 else empire_data

            # Extract key info
            military_match = re.search(r'military_power\s*=\s*([\d.]+)', empire_data)
            if military_match:
                result['military_power'] = float(military_match.group(1))

            economy_match = re.search(r'economy_power\s*=\s*([\d.]+)', empire_data)
            if economy_match:
                result['economy_power'] = float(economy_match.group(1))

            # Relation to player
            opinion_match = re.search(r'opinion\s*=\s*\{[^}]*base\s*=\s*([-\d.]+)', empire_data)
            if opinion_match:
                result['opinion'] = float(opinion_match.group(1))

        return result

    def get_wars(self) -> dict:
        """Get all active wars involving the player with detailed information.

        Returns:
            Dict with detailed war information including:
            - wars: List of detailed war objects with name, dates, exhaustion, participants
            - player_at_war: Boolean indicating if player is at war
            - active_war_count: Number of wars the player is in
        """
        from date_utils import days_between

        result = {'wars': [], 'player_at_war': False, 'active_war_count': 0}

        player_id = self.get_player_empire_id()
        current_date = self.get_metadata().get('date', '')

        # Build a country ID -> name mapping for lookups
        country_names = self._get_country_names_map()

        # Find war section
        war_section_match = re.search(r'\nwar=\n\{', self.gamestate)
        if not war_section_match:
            return result

        war_start = war_section_match.start() + 1
        war_chunk = self.gamestate[war_start:war_start + 5000000]  # Wars can be large

        # Parse individual war blocks
        # Each war entry starts with a pattern like \n\t0=\n\t{
        war_entry_pattern = r'\n\t(\d+)=\n\t\{'
        war_entries = list(re.finditer(war_entry_pattern, war_chunk))

        for i, entry_match in enumerate(war_entries):
            # Determine the end of this war block
            entry_start = entry_match.start()
            if i + 1 < len(war_entries):
                entry_end = war_entries[i + 1].start()
            else:
                # Find closing brace for last entry
                entry_end = min(entry_start + 100000, len(war_chunk))

            war_block = war_chunk[entry_start:entry_end]

            # Extract war name
            name_match = re.search(r'name\s*=\s*"([^"]+)"', war_block)
            if not name_match:
                continue
            war_name = name_match.group(1)

            # Extract start date
            start_date_match = re.search(r'start_date\s*=\s*"?([0-9.]+)"?', war_block)
            start_date = start_date_match.group(1) if start_date_match else None

            # Extract exhaustion values
            attacker_exhaustion_match = re.search(r'attacker_war_exhaustion\s*=\s*([\d.]+)', war_block)
            defender_exhaustion_match = re.search(r'defender_war_exhaustion\s*=\s*([\d.]+)', war_block)
            attacker_exhaustion = float(attacker_exhaustion_match.group(1)) if attacker_exhaustion_match else 0.0
            defender_exhaustion = float(defender_exhaustion_match.group(1)) if defender_exhaustion_match else 0.0

            # Extract war goal
            war_goal_match = re.search(r'war_goal\s*=\s*\{[^}]*type\s*=\s*"?([^"\s}]+)"?', war_block, re.DOTALL)
            war_goal = war_goal_match.group(1) if war_goal_match else "unknown"

            # Extract attacker country IDs
            attacker_ids = []
            attackers_match = re.search(r'attackers\s*=\s*\{(.*?)\n\t\}', war_block, re.DOTALL)
            if attackers_match:
                attacker_ids = re.findall(r'country\s*=\s*(\d+)', attackers_match.group(1))

            # Extract defender country IDs
            defender_ids = []
            defenders_match = re.search(r'defenders\s*=\s*\{(.*?)\n\t\}', war_block, re.DOTALL)
            if defenders_match:
                defender_ids = re.findall(r'country\s*=\s*(\d+)', defenders_match.group(1))

            # Check if player is involved and determine side
            player_id_str = str(player_id)
            player_is_attacker = player_id_str in attacker_ids
            player_is_defender = player_id_str in defender_ids

            if not player_is_attacker and not player_is_defender:
                continue  # Player not involved in this war

            # Build war info
            our_side = "attacker" if player_is_attacker else "defender"
            our_exhaustion = attacker_exhaustion if player_is_attacker else defender_exhaustion
            their_exhaustion = defender_exhaustion if player_is_attacker else attacker_exhaustion

            # Resolve country names
            attacker_names = [country_names.get(int(cid), f"Empire {cid}") for cid in attacker_ids]
            defender_names = [country_names.get(int(cid), f"Empire {cid}") for cid in defender_ids]

            # Calculate duration
            duration_days = None
            if start_date and current_date:
                duration_days = days_between(start_date, current_date)

            war_info = {
                'name': war_name,
                'start_date': start_date,
                'duration_days': duration_days,
                'our_side': our_side,
                'our_exhaustion': round(our_exhaustion, 1),
                'their_exhaustion': round(their_exhaustion, 1),
                'participants': {
                    'attackers': attacker_names,
                    'defenders': defender_names
                },
                'war_goal': war_goal,
                'status': 'in_progress'  # All wars in the war section are active
            }

            result['wars'].append(war_info)

        result['active_war_count'] = len(result['wars'])
        result['count'] = len(result['wars'])  # Backward compatibility
        result['player_at_war'] = len(result['wars']) > 0

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

            fleet_data = fleet_section[match.start():match.start() + 2500]
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

                if len(result['military_fleets']) < 20:  # Keep top 20
                    result['military_fleets'].append({
                        'id': fid,
                        'name': fleet_name,
                        'ships': ship_count,
                        'military_power': round(mp, 0),
                    })
            else:
                result['civilian_fleet_count'] += 1

        return result

    def get_fleets(self) -> dict:
        """Get player's fleet information with proper categorization.

        Returns:
            Dict with military fleets, starbases, and civilian fleet counts.
            The 'fleets' list contains actual military combat fleets, not starbases
            or civilian ships (science, construction, transport).
        """
        result = {
            'fleets': [],
            'count': 0,
            'military_fleet_count': 0,
            'starbase_count': 0,
            'civilian_fleet_count': 0,
            'military_ships': 0,
            'total_military_power': 0.0,
        }

        # Get the player's country block using proper section detection
        player_id = self.get_player_empire_id()
        country_content = self._find_player_country_content(player_id)
        if not country_content:
            return result

        # Get OWNED fleets (not just visible fleets)
        owned_fleet_ids = self._get_owned_fleet_ids(country_content)
        if not owned_fleet_ids:
            return result

        # Analyze the owned fleets
        analysis = self._analyze_player_fleets(owned_fleet_ids)

        result['count'] = analysis['military_fleet_count']
        result['military_fleet_count'] = analysis['military_fleet_count']
        result['civilian_fleet_count'] = analysis['civilian_fleet_count']
        result['military_ships'] = analysis['military_ships']
        result['total_military_power'] = analysis['total_military_power']
        result['fleets'] = analysis['military_fleets']
        result['fleet_names'] = [f['name'] for f in analysis['military_fleets']]

        # Get accurate starbase count from starbase_mgr
        owned_set = set(owned_fleet_ids)
        starbase_info = self._count_player_starbases(owned_set)
        result['starbase_count'] = starbase_info['total_upgraded']
        result['starbases'] = starbase_info

        return result

    def get_leaders(self) -> dict:
        """Get the player's leader information.

        Returns:
            Dict with leader details including scientists, admirals, generals, governors
        """
        result = {
            'leaders': [],
            'count': 0,
            'by_class': {}
        }

        player_id = self.get_player_empire_id()

        # Find the leaders section (top-level)
        leaders_match = re.search(r'^leaders=\s*\{', self.gamestate, re.MULTILINE)
        if not leaders_match:
            result['error'] = "Could not find leaders section"
            return result

        # Extract a large chunk from the leaders section
        start = leaders_match.start()
        leaders_chunk = self.gamestate[start:start + 3000000]  # 3MB chunk

        leaders_found = []
        class_counts = {}

        # Find each leader block by looking for ID={ pattern at the start
        # Use a simpler approach: find all leader blocks and filter by country
        leader_start_pattern = r'\n\t(\d+)=\s*\{\s*\n\t\tname='

        for match in re.finditer(leader_start_pattern, leaders_chunk):
            leader_id = match.group(1)
            block_start = match.start() + 1  # Skip the leading newline

            # Find the end of this leader block by counting braces
            brace_count = 0
            block_end = block_start
            started = False
            for i, char in enumerate(leaders_chunk[block_start:block_start + 5000], block_start):
                if char == '{':
                    brace_count += 1
                    started = True
                elif char == '}':
                    brace_count -= 1
                    if started and brace_count == 0:
                        block_end = i + 1
                        break

            leader_block = leaders_chunk[block_start:block_end]

            # Check if this leader belongs to the player
            country_match = re.search(r'\n\s*country=(\d+)', leader_block)
            if not country_match:
                continue

            country_id = int(country_match.group(1))
            if country_id != player_id:
                continue

            # Extract class
            class_match = re.search(r'class="([^"]+)"', leader_block)
            if not class_match:
                continue

            leader_class = class_match.group(1)

            # Extract leader details
            leader_info = {
                'id': leader_id,
                'class': leader_class,
            }

            # Extract name - try different patterns
            # Pattern 1: full_names={ key="XXX_CHR_Name" }
            name_match = re.search(r'key="([^"]+_CHR_[^"]+)"', leader_block)
            if name_match:
                raw_name = name_match.group(1)
                leader_info['name'] = raw_name.split('_CHR_')[-1]
            else:
                # Pattern 2: key="%LEADER_2%" with variables
                name_match = re.search(r'key="(%[^"]+%)"', leader_block)
                if name_match:
                    # Try to find a more readable name in variables
                    var_name = re.search(r'value=\s*\{\s*key="([^"]+_CHR_[^"]+)"', leader_block)
                    if var_name:
                        leader_info['name'] = var_name.group(1).split('_CHR_')[-1]
                    else:
                        leader_info['name'] = name_match.group(1)

            # Extract level
            level_match = re.search(r'\n\s*level=(\d+)', leader_block)
            if level_match:
                leader_info['level'] = int(level_match.group(1))

            # Extract age
            age_match = re.search(r'\n\s*age=(\d+)', leader_block)
            if age_match:
                leader_info['age'] = int(age_match.group(1))

            # Extract traits
            traits = re.findall(r'traits="([^"]+)"', leader_block)
            if traits:
                leader_info['traits'] = traits

            # Extract experience if available
            exp_match = re.search(r'experience=([\d.]+)', leader_block)
            if exp_match:
                leader_info['experience'] = float(exp_match.group(1))

            leaders_found.append(leader_info)

            # Count by class
            if leader_class not in class_counts:
                class_counts[leader_class] = 0
            class_counts[leader_class] += 1

        result['leaders'] = leaders_found[:30]  # Limit to 30 leaders
        result['count'] = len(leaders_found)
        result['by_class'] = class_counts

        return result

    def get_technology(self) -> dict:
        """Get the player's technology research status.

        Returns:
            Dict with detailed technology tracking including:
            - completed_count: Number of researched technologies
            - researched_techs: List of completed tech names
            - in_progress: Current research for each category with progress details
            - research_speed: Monthly research income by category
            - available_techs: Technologies available for research by category
        """
        result = {
            'completed_count': 0,
            'researched_techs': [],
            'in_progress': {
                'physics': None,
                'society': None,
                'engineering': None
            },
            'research_speed': {
                'physics': 0,
                'society': 0,
                'engineering': 0
            },
            'available_techs': {
                'physics': [],
                'society': [],
                'engineering': []
            }
        }

        player_id = self.get_player_empire_id()

        # Find the country section and player's tech_status
        country_match = re.search(r'^country=\s*\{', self.gamestate, re.MULTILINE)
        if not country_match:
            result['error'] = "Could not find country section"
            return result

        start = country_match.start()
        # Find player country (0=)
        player_match = re.search(r'\n\t0=\s*\{', self.gamestate[start:start + 1000000])
        if not player_match:
            result['error'] = "Could not find player country"
            return result

        player_start = start + player_match.start()
        player_chunk = self.gamestate[player_start:player_start + 500000]

        # Find tech_status section
        tech_match = re.search(r'tech_status=\s*\{', player_chunk)
        if not tech_match:
            result['error'] = "Could not find tech_status section"
            return result

        # Extract tech_status block using brace matching
        tech_start = tech_match.start()
        brace_count = 0
        tech_end = tech_start
        for i, char in enumerate(player_chunk[tech_start:], tech_start):
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    tech_end = i + 1
                    break

        tech_block = player_chunk[tech_start:tech_end]

        # Extract completed technologies
        # Format: technology="tech_name" level=1 (repeated for each tech)
        # The techs are listed as individual technology="..." entries, not in a { } block
        tech_pattern = r'technology="([^"]+)"'
        technologies = re.findall(tech_pattern, tech_block)
        result['researched_techs'] = sorted(list(set(technologies)))
        result['completed_count'] = len(result['researched_techs'])

        # Extract current research for each category
        # Format in tech_status:
        # physics={ level=5 progress=1234.5 tech=tech_name leader=5 }
        for category in ['physics', 'society', 'engineering']:
            # Match the category block within tech_status
            cat_match = re.search(rf'\b{category}=\s*\{{([^}}]+)\}}', tech_block)
            if cat_match:
                cat_content = cat_match.group(1)

                # Extract tech name (can be quoted or bare)
                tech_name_match = re.search(r'tech=(?:"([^"]+)"|(\w+))', cat_content)
                progress_match = re.search(r'progress=([\d.]+)', cat_content)
                leader_match = re.search(r'leader=(\d+)', cat_content)

                if tech_name_match:
                    tech_name = tech_name_match.group(1) or tech_name_match.group(2)
                    progress = float(progress_match.group(1)) if progress_match else 0.0
                    leader_id = int(leader_match.group(1)) if leader_match else None

                    # Try to get tech cost - this would require additional lookup
                    # For now, we'll estimate or leave as None
                    # Cost data isn't directly in tech_status, would need tech definitions
                    result['in_progress'][category] = {
                        'tech': tech_name,
                        'progress': progress,
                        'cost': None,  # Would need tech definitions to get actual cost
                        'percent_complete': None,  # Can't calculate without cost
                        'leader_id': leader_id
                    }

        # Also check the queue format for current research (alternative location)
        # Format: physics_queue={ { progress=X technology="tech_name" date="Y" } }
        for category in ['physics', 'society', 'engineering']:
            if result['in_progress'][category] is None:
                queue_match = re.search(
                    rf'{category}_queue=\s*\{{[^}}]*progress=([\d.]+)[^}}]*technology="([^"]+)"',
                    player_chunk
                )
                if queue_match:
                    result['in_progress'][category] = {
                        'tech': queue_match.group(2),
                        'progress': float(queue_match.group(1)),
                        'cost': None,
                        'percent_complete': None,
                        'leader_id': None
                    }

        # Extract available techs by category
        # There are two possible locations:
        # 1. A section with physics={ "tech_a" "tech_b" } society={...} engineering={...}
        #    (contains the tech options for current research choices)
        # 2. potential={ "tech_name"="weight" ... } (weighted tech pool)
        #
        # Look for the category blocks that contain quoted tech names (research options)
        for category in ['physics', 'society', 'engineering']:
            # Match category={ "tech_..." "tech_..." } pattern
            # Use a pattern that matches a block containing only quoted tech names
            cat_match = re.search(rf'{category}=\s*\{{\s*("[^"]+"\s*)+\}}', tech_block)
            if cat_match:
                cat_content = cat_match.group(0)
                # Extract quoted tech names from the block
                quoted = re.findall(r'"(tech_[^"]+)"', cat_content)
                result['available_techs'][category] = sorted(list(set(quoted)))

        # Get research speed from monthly income
        # This requires extracting from the budget section
        budget_match = re.search(r'budget=\s*\{', player_chunk)
        if budget_match:
            budget_start = budget_match.start()
            # Extract budget block
            brace_count = 0
            budget_end = budget_start
            for i, char in enumerate(player_chunk[budget_start:budget_start + 100000], budget_start):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        budget_end = i + 1
                        break

            budget_block = player_chunk[budget_start:budget_end]

            # Parse income section for research resources
            income_section_match = re.search(r'income=\s*\{(.+?)\}\s*expenses=', budget_block, re.DOTALL)
            if income_section_match:
                income_section = income_section_match.group(1)

                # Sum up research income from all sources
                for category, resource in [
                    ('physics', 'physics_research'),
                    ('society', 'society_research'),
                    ('engineering', 'engineering_research')
                ]:
                    matches = re.findall(rf'{resource}=([\d.]+)', income_section)
                    if matches:
                        result['research_speed'][category] = round(sum(float(m) for m in matches), 2)

        # Calculate percent_complete for in-progress research if we have research speed
        # Using a rough estimate: typical tech cost = 1000-10000 depending on tier
        # This is an approximation since actual cost requires tech definitions
        for category in ['physics', 'society', 'engineering']:
            if result['in_progress'][category] and result['research_speed'][category] > 0:
                progress = result['in_progress'][category]['progress']
                speed = result['research_speed'][category]
                # Rough estimate: if we know progress and speed, we can estimate months remaining
                # but without cost, we can't calculate percentage
                # Leave as None unless we have actual cost data

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

    def get_pop_statistics(self) -> dict:
        """Get detailed population statistics for the player's empire.

        Aggregates pop data across all player-owned planets including:
        - Total pop count
        - Breakdown by species
        - Breakdown by job category (ruler/specialist/worker)
        - Breakdown by stratum
        - Average happiness
        - Employment statistics

        Returns:
            Dict with population statistics:
            {
                "total_pops": 1250,
                "by_species": {"Human": 800, "Blorg": 300, ...},
                "by_job_category": {"ruler": 50, "specialist": 400, ...},
                "by_stratum": {"ruler": 50, "specialist": 400, ...},
                "happiness_avg": 68.5,
                "employed_pops": 1050,
                "unemployed_pops": 200
            }
        """
        result = {
            'total_pops': 0,
            'by_species': {},
            'by_job_category': {},
            'by_stratum': {},
            'happiness_avg': 0.0,
            'employed_pops': 0,
            'unemployed_pops': 0,
        }

        # Step 1: Get player's planet IDs (as integers for comparison)
        planet_ids = self._get_player_planet_ids()
        if not planet_ids:
            return result

        player_planet_set = set(int(pid) for pid in planet_ids)

        # Step 2: Build species ID to name mapping
        species_names = self._get_species_names()

        # Step 3: Find pop_groups section (this is where actual pop data lives)
        # Structure: pop_groups=\n{\n\tID=\n\t{ key={ species=X category="Y" } planet=Z size=N happiness=H ... }
        pop_groups_match = re.search(r'\npop_groups=\n\{', self.gamestate)
        if not pop_groups_match:
            # Fallback: try alternate format
            pop_groups_match = re.search(r'^pop_groups=\s*\{', self.gamestate, re.MULTILINE)
            if not pop_groups_match:
                result['error'] = "Could not find pop_groups section"
                return result

        pop_start = pop_groups_match.start()
        # Pop groups section can be large in late game
        pop_chunk = self.gamestate[pop_start:pop_start + 50000000]  # Up to 50MB

        # Tracking for statistics
        species_counts = {}
        job_category_counts = {}
        stratum_counts = {}
        happiness_values = []
        total_pops = 0

        # Parse pop groups - each group represents multiple pops of same type
        # Format: \n\tID=\n\t{ ... key={ species=X category="Y" } ... planet=Z size=N ...
        pop_pattern = r'\n\t(\d+)=\n\t\{'
        groups_processed = 0
        max_groups = 50000  # Safety limit

        for match in re.finditer(pop_pattern, pop_chunk):
            if groups_processed >= max_groups:
                result['_note'] = f'Processed {max_groups} pop groups (limit reached)'
                break

            groups_processed += 1
            block_start = match.start() + 1

            # Get pop group block content
            block_chunk = pop_chunk[block_start:block_start + 2500]

            # Find end of this pop group's block
            brace_count = 0
            block_end = 0
            started = False
            for i, char in enumerate(block_chunk):
                if char == '{':
                    brace_count += 1
                    started = True
                elif char == '}':
                    brace_count -= 1
                    if started and brace_count == 0:
                        block_end = i + 1
                        break

            pop_block = block_chunk[:block_end] if block_end > 0 else block_chunk

            # Check if this pop group is on a player-owned planet
            planet_match = re.search(r'\n\s*planet=(\d+)', pop_block)
            if not planet_match:
                continue

            planet_id = int(planet_match.group(1))
            if planet_id not in player_planet_set:
                continue

            # Get the size of this pop group (number of pops)
            size_match = re.search(r'\n\s*size=(\d+)', pop_block)
            if not size_match:
                continue

            pop_size = int(size_match.group(1))
            if pop_size == 0:
                continue

            total_pops += pop_size

            # Extract species from key={ species=X ... } block
            # Species is inside the nested key block
            key_match = re.search(r'key=\s*\{([^}]+)\}', pop_block)
            if key_match:
                key_block = key_match.group(1)

                # Extract species ID
                species_match = re.search(r'species=(\d+)', key_block)
                if species_match:
                    species_id = species_match.group(1)
                    species_name = species_names.get(species_id, f"Species_{species_id}")
                    species_counts[species_name] = species_counts.get(species_name, 0) + pop_size

                # Extract category (job category: ruler, specialist, worker, slave, etc.)
                category_match = re.search(r'category="([^"]+)"', key_block)
                if category_match:
                    category = category_match.group(1)
                    job_category_counts[category] = job_category_counts.get(category, 0) + pop_size
                    # Use category as stratum (they're equivalent in Stellaris)
                    stratum_counts[category] = stratum_counts.get(category, 0) + pop_size

            # Extract happiness (0.0 to 1.0 scale in save, convert to percentage)
            # Weight by pop size for accurate average
            happiness_match = re.search(r'\n\s*happiness=([\d.]+)', pop_block)
            if happiness_match:
                happiness = float(happiness_match.group(1))
                # Add each pop's happiness (weighted by size)
                happiness_values.extend([happiness * 100] * pop_size)

        # Finalize results
        result['total_pops'] = total_pops
        result['by_species'] = species_counts
        result['by_job_category'] = job_category_counts
        result['by_stratum'] = stratum_counts

        # Employed pops = total minus unemployed category
        unemployed = job_category_counts.get('unemployed', 0)
        result['employed_pops'] = total_pops - unemployed
        result['unemployed_pops'] = unemployed

        # Calculate average happiness
        if happiness_values:
            result['happiness_avg'] = round(sum(happiness_values) / len(happiness_values), 1)

        return result

    def get_resources(self) -> dict:
        """Get the player's resource/economy snapshot.

        Returns:
            Dict with resource stockpiles and monthly income/expenses
        """
        result = {
            'stockpiles': {},
            'monthly_income': {},
            'monthly_expenses': {},
            'net_monthly': {}
        }

        player_id = self.get_player_empire_id()

        # Find the country section and player's budget
        country_match = re.search(r'^country=\s*\{', self.gamestate, re.MULTILINE)
        if not country_match:
            result['error'] = "Could not find country section"
            return result

        start = country_match.start()
        player_match = re.search(r'\n\t0=\s*\{', self.gamestate[start:start + 1000000])
        if not player_match:
            result['error'] = "Could not find player country"
            return result

        player_start = start + player_match.start()
        # Need larger chunk to reach standard_economy_module (around offset 300k+)
        player_chunk = self.gamestate[player_start:player_start + 400000]

        # Find budget section
        budget_match = re.search(r'budget=\s*\{', player_chunk)
        if not budget_match:
            result['error'] = "Could not find budget section"
            return result

        budget_start = budget_match.start()
        # Extract budget block (it's large, ~50k chars)
        brace_count = 0
        budget_end = budget_start
        for i, char in enumerate(player_chunk[budget_start:budget_start + 100000], budget_start):
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    budget_end = i + 1
                    break

        budget_block = player_chunk[budget_start:budget_end]

        # All tracked resources including strategic resources
        STOCKPILE_RESOURCES = [
            'energy', 'minerals', 'food', 'consumer_goods', 'alloys',
            'physics_research', 'society_research', 'engineering_research',
            'influence', 'unity', 'volatile_motes', 'exotic_gases', 'rare_crystals',
            'sr_living_metal', 'sr_zro', 'sr_dark_matter', 'minor_artifacts', 'astral_threads'
        ]

        # Extract ACTUAL stockpiles from standard_economy_module.resources
        # This is where Stellaris stores the current accumulated resource values
        econ_module_match = re.search(r'standard_economy_module=\s*\{', player_chunk)
        if econ_module_match:
            econ_start = econ_module_match.start()
            econ_chunk = player_chunk[econ_start:econ_start + 3000]
            resources_match = re.search(r'resources=\s*\{([^}]+)\}', econ_chunk)
            if resources_match:
                resources_block = resources_match.group(1)
                for resource in STOCKPILE_RESOURCES:
                    res_match = re.search(rf'{resource}=([\d.-]+)', resources_block)
                    if res_match:
                        result['stockpiles'][resource] = float(res_match.group(1))

        # Extract total income from various sources
        income_resources = {}
        expenses_resources = {}

        # All tracked resources including strategic resources
        ALL_RESOURCES = [
            # Basic resources
            'energy', 'minerals', 'food', 'consumer_goods', 'alloys',
            # Research
            'physics_research', 'society_research', 'engineering_research',
            # Influence/Unity
            'influence', 'unity',
            # Exotic resources
            'volatile_motes', 'exotic_gases', 'rare_crystals',
            # Strategic resources (late-game)
            'sr_living_metal', 'sr_zro', 'sr_dark_matter',
            # Special resources (DLC-dependent)
            'minor_artifacts', 'astral_threads'
        ]

        # Parse income section more thoroughly
        income_section_match = re.search(r'income=\s*\{(.+?)\}\s*expenses=', budget_block, re.DOTALL)
        if income_section_match:
            income_section = income_section_match.group(1)
            # Sum up resources from all income sources
            for resource in ALL_RESOURCES:
                matches = re.findall(rf'{resource}=([\d.]+)', income_section)
                if matches:
                    income_resources[resource] = sum(float(m) for m in matches)

        result['monthly_income'] = income_resources

        # Parse expenses section
        expenses_match = re.search(r'expenses=\s*\{(.+?)\}\s*(?:balance|$)', budget_block, re.DOTALL)
        if expenses_match:
            expenses_section = expenses_match.group(1)
            for resource in ALL_RESOURCES:
                matches = re.findall(rf'{resource}=([\d.]+)', expenses_section)
                if matches:
                    expenses_resources[resource] = sum(float(m) for m in matches)

        result['monthly_expenses'] = expenses_resources

        # Calculate net
        for resource in set(list(income_resources.keys()) + list(expenses_resources.keys())):
            income = income_resources.get(resource, 0)
            expense = expenses_resources.get(resource, 0)
            result['net_monthly'][resource] = round(income - expense, 2)

        # Add a summary of key resources
        result['summary'] = {
            'energy_net': result['net_monthly'].get('energy', 0),
            'minerals_net': result['net_monthly'].get('minerals', 0),
            'food_net': result['net_monthly'].get('food', 0),
            'alloys_net': result['net_monthly'].get('alloys', 0),
            'consumer_goods_net': result['net_monthly'].get('consumer_goods', 0),
            'research_total': (result['net_monthly'].get('physics_research', 0) +
                              result['net_monthly'].get('society_research', 0) +
                              result['net_monthly'].get('engineering_research', 0)),
            # Exotic resources (mid-game)
            'volatile_motes_net': result['net_monthly'].get('volatile_motes', 0),
            'exotic_gases_net': result['net_monthly'].get('exotic_gases', 0),
            'rare_crystals_net': result['net_monthly'].get('rare_crystals', 0),
            # Strategic resources (late-game) - only include if non-zero
            'living_metal_net': result['net_monthly'].get('sr_living_metal', 0),
            'zro_net': result['net_monthly'].get('sr_zro', 0),
            'dark_matter_net': result['net_monthly'].get('sr_dark_matter', 0),
            # Special resources
            'minor_artifacts': result['stockpiles'].get('minor_artifacts', 0),
        }

        # Add strategic resource stockpiles (only if present)
        strategic = {}
        for res in ['sr_living_metal', 'sr_zro', 'sr_dark_matter']:
            if res in result['stockpiles'] and result['stockpiles'][res] > 0:
                strategic[res.replace('sr_', '')] = result['stockpiles'][res]
        if strategic:
            result['strategic_stockpiles'] = strategic

        return result

    def get_diplomacy(self) -> dict:
        """Get the player's diplomatic relations.

        Returns:
            Dict with relations, treaties, and diplomatic status with other empires
        """
        result = {
            'relations': [],
            'treaties': [],
            'allies': [],
            'rivals': [],
            'federation': None
        }

        player_id = self.get_player_empire_id()

        # Find the country section and player's relations_manager
        country_match = re.search(r'^country=\s*\{', self.gamestate, re.MULTILINE)
        if not country_match:
            result['error'] = "Could not find country section"
            return result

        start = country_match.start()
        player_match = re.search(r'\n\t0=\s*\{', self.gamestate[start:start + 1000000])
        if not player_match:
            result['error'] = "Could not find player country"
            return result

        player_start = start + player_match.start()
        player_chunk = self.gamestate[player_start:player_start + 500000]

        # Find relations_manager section
        rel_match = re.search(r'relations_manager=\s*\{', player_chunk)
        if not rel_match:
            result['error'] = "Could not find relations_manager section"
            return result

        rel_start = rel_match.start()
        # Extract relations_manager block
        brace_count = 0
        rel_end = rel_start
        for i, char in enumerate(player_chunk[rel_start:rel_start + 100000], rel_start):
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    rel_end = i + 1
                    break

        rel_block = player_chunk[rel_start:rel_end]

        # Parse individual relations
        # Pattern: relation={owner=<player_id> country=X ...}
        relation_pattern = r'relation=\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}'

        relations_found = []
        allies = []
        rivals = []

        for match in re.finditer(relation_pattern, rel_block):
            rel_content = match.group(1)

            # Only process relations where owner=player_id (not hardcoded 0)
            if not re.search(rf'owner={player_id}\b', rel_content):
                continue

            relation_info = {}

            # Extract country ID
            country_match = re.search(r'country=(\d+)', rel_content)
            if country_match:
                relation_info['country_id'] = int(country_match.group(1))

            # Extract trust
            trust_match = re.search(r'trust=(\d+)', rel_content)
            if trust_match:
                relation_info['trust'] = int(trust_match.group(1))

            # Extract relation score
            rel_current = re.search(r'relation_current=([-\d]+)', rel_content)
            if rel_current:
                relation_info['opinion'] = int(rel_current.group(1))

            # Check for treaties/agreements
            if 'alliance=yes' in rel_content:
                relation_info['alliance'] = True
                allies.append(relation_info.get('country_id'))
            if 'research_agreement=yes' in rel_content:
                relation_info['research_agreement'] = True
            if 'embassy=yes' in rel_content:
                relation_info['embassy'] = True
            if 'truce=' in rel_content and 'truce' not in rel_content.split('=')[0]:
                relation_info['has_truce'] = True

            # Check for communications
            if 'communications=yes' in rel_content:
                relation_info['has_contact'] = True

            relations_found.append(relation_info)

        result['relations'] = relations_found[:30]  # Limit to 30
        result['allies'] = allies
        result['relation_count'] = len(relations_found)

        # Check for federation membership
        fed_match = re.search(r'federation=(\d+)', player_chunk[:5000])
        if fed_match and fed_match.group(1) != '4294967295':  # Not null
            result['federation'] = int(fed_match.group(1))

        # Summarize by opinion
        positive_relations = len([r for r in relations_found if r.get('opinion', 0) > 0])
        negative_relations = len([r for r in relations_found if r.get('opinion', 0) < 0])
        neutral_relations = len([r for r in relations_found if r.get('opinion', 0) == 0])

        result['summary'] = {
            'positive': positive_relations,
            'negative': negative_relations,
            'neutral': neutral_relations,
            'total_contacts': len(relations_found)
        }

        return result

    def get_fallen_empires(self) -> dict:
        """Get information about all Fallen Empires in the galaxy (both dormant and awakened).

        Fallen Empires are ancient, powerful civilizations. They start dormant but can
        awaken in the late game, becoming major threats or allies.

        Returns:
            Dict with:
                - fallen_empires: List of all FEs with status
                - dormant_count: Number still dormant
                - awakened_count: Number that have awakened
                - war_in_heaven: Whether War in Heaven is active
        """
        result = {
            'fallen_empires': [],
            'dormant_count': 0,
            'awakened_count': 0,
            'total_count': 0,
            'war_in_heaven': False,
        }

        # Get player military power for comparison
        player_status = self.get_player_status()
        player_military = player_status.get('military_power', 0)

        # Find country section and build country position index
        country_start = self._find_country_section_start()
        if country_start == -1:
            return result

        country_chunk = self.gamestate[country_start:]
        country_entries = [(int(m.group(1)), country_start + m.start())
                          for m in re.finditer(r'\n\t(\d+)=\n\t\{', country_chunk)]

        # Find all fallen empire types (both dormant and awakened)
        fe_positions = [(m.start(), 'dormant') for m in re.finditer(r'type="fallen_empire"', self.gamestate)]
        fe_positions += [(m.start(), 'awakened') for m in re.finditer(r'type="awakened_fallen_empire"', self.gamestate)]

        if not fe_positions:
            return result

        # Check for War in Heaven
        if 'war_in_heaven' in self.gamestate.lower():
            if re.search(r'(?<!no_)war_in_heaven\s*=\s*yes', self.gamestate):
                result['war_in_heaven'] = True

        # FE archetype mapping
        FE_ARCHETYPES = {
            'xenophile': ('Benevolent Interventionists', 'May awaken to "guide" younger races'),
            'xenophobe': ('Militant Isolationists', 'Hostile if you colonize near them'),
            'materialist': ('Ancient Caretakers', 'Protect galaxy from synthetic threats'),
            'spiritualist': ('Holy Guardians', 'Protect holy worlds, hate tomb worlds'),
        }

        # Process each fallen empire
        for fe_pos, status in fe_positions:
            # Find which country this belongs to
            country_id = None
            country_pos = None
            for cid, cpos in country_entries:
                if cpos < fe_pos:
                    country_id = cid
                    country_pos = cpos
                else:
                    break

            if country_id is None:
                continue

            # Get next country position for boundary
            next_pos = None
            for cid, cpos in country_entries:
                if cpos > country_pos:
                    next_pos = cpos
                    break

            block = self.gamestate[country_pos:next_pos] if next_pos else self.gamestate[country_pos:country_pos + 200000]

            # Extract empire details
            empire_info = {
                'country_id': country_id,
                'name': 'Unknown Fallen Empire',
                'status': status,  # 'dormant' or 'awakened'
                'archetype': 'Unknown',
                'archetype_behavior': '',
                'military_power': 0,
                'power_ratio': 0.0,
                'ethics': None,
            }

            # Get name
            name_m = re.search(r'name=\n\t*\{[^}]*key="([^"]+)"', block)
            if name_m:
                raw_name = name_m.group(1)
                empire_info['name'] = raw_name.replace('SPEC_', '').replace('_', ' ').title()

            # Get ethics (determines FE archetype)
            ethos_m = re.search(r'ethos=\s*\{([^}]+)\}', block[:200000])
            if ethos_m:
                ethos_block = ethos_m.group(1)
                ethics_list = re.findall(r'ethic="(ethic_[^"]+)"', ethos_block)
                if ethics_list:
                    # Use the fanatic ethic if present
                    ethic = None
                    for e in ethics_list:
                        if 'fanatic' in e:
                            ethic = e
                            break
                    if not ethic:
                        ethic = ethics_list[0]

                    empire_info['ethics'] = ethic

                    # Map to FE archetype
                    for key, (archetype, behavior) in FE_ARCHETYPES.items():
                        if key in ethic:
                            empire_info['archetype'] = archetype
                            empire_info['archetype_behavior'] = behavior
                            break

            # Get military power
            mil_m = re.search(r'military_power=([\d.]+)', block)
            if mil_m:
                empire_info['military_power'] = float(mil_m.group(1))
                if player_military > 0:
                    empire_info['power_ratio'] = round(empire_info['military_power'] / player_military, 1)

            # Get their opinion of player
            opinion_m = re.search(r'relations_manager=.*?country=0[^}]*opinion=([-\d]+)', block[:80000], re.DOTALL)
            if opinion_m:
                empire_info['opinion_of_player'] = int(opinion_m.group(1))

            result['fallen_empires'].append(empire_info)

        # Count by status
        result['dormant_count'] = sum(1 for fe in result['fallen_empires'] if fe['status'] == 'dormant')
        result['awakened_count'] = sum(1 for fe in result['fallen_empires'] if fe['status'] == 'awakened')
        result['total_count'] = len(result['fallen_empires'])

        return result

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

    def get_starbases(self) -> dict:
        """Get the player's starbase information.

        Returns:
            Dict with starbase locations, levels, and modules
        """
        result = {
            'starbases': [],
            'count': 0,
            'by_level': {}
        }

        player_id = self.get_player_empire_id()

        # Find which starbases belong to player by looking at galactic_object section
        # Each system has a starbases={...} list and inhibitor_owners={...} containing owner IDs
        galactic_match = re.search(r'^galactic_object=\s*\{', self.gamestate, re.MULTILINE)
        if not galactic_match:
            result['error'] = "Could not find galactic_object section"
            return result

        go_start = galactic_match.start()
        go_chunk = self.gamestate[go_start:go_start + 5000000]  # 5MB for systems

        # Find systems where inhibitor_owners contains player_id
        # Pattern: starbases={ ID } ... inhibitor_owners={ player_id }
        player_starbase_ids = []

        # Match system blocks that have starbases and are owned by player
        # Use player_id instead of hardcoded 0
        system_pattern = rf'starbases=\s*\{{\s*(\d+)\s*\}}[^}}]*?inhibitor_owners=\s*\{{[^}}]*\b{player_id}\b'
        for match in re.finditer(system_pattern, go_chunk):
            sb_id = match.group(1)
            if sb_id != '4294967295':  # Not null
                player_starbase_ids.append(sb_id)

        # Now find the starbase_mgr section and get details for player starbases
        starbase_match = re.search(r'^starbase_mgr=\s*\{', self.gamestate, re.MULTILINE)
        if not starbase_match:
            result['error'] = "Could not find starbase_mgr section"
            return result

        sb_start = starbase_match.start()
        starbase_chunk = self.gamestate[sb_start:sb_start + 2000000]

        # Parse individual starbases from starbase_mgr
        starbase_pattern = r'\n\t\t(\d+)=\s*\{\s*\n\t\t\tlevel="([^"]+)"'

        starbases_found = []
        level_counts = {}

        for match in re.finditer(starbase_pattern, starbase_chunk):
            sb_id = match.group(1)
            level = match.group(2)

            # Only include player starbases
            if sb_id not in player_starbase_ids:
                continue

            block_start = match.start() + 1

            # Find the end of this starbase block
            brace_count = 0
            block_end = block_start
            started = False
            for i, char in enumerate(starbase_chunk[block_start:block_start + 3000], block_start):
                if char == '{':
                    brace_count += 1
                    started = True
                elif char == '}':
                    brace_count -= 1
                    if started and brace_count == 0:
                        block_end = i + 1
                        break

            sb_block = starbase_chunk[block_start:block_end]

            starbase_info = {
                'id': sb_id,
                'level': level.replace('starbase_level_', '')
            }

            # Extract type if present
            type_match = re.search(r'type="([^"]+)"', sb_block)
            if type_match:
                starbase_info['type'] = type_match.group(1)

            # Extract modules
            modules_match = re.search(r'modules=\s*\{([^}]+)\}', sb_block)
            if modules_match:
                modules = re.findall(r'\d+=(\w+)', modules_match.group(1))
                starbase_info['modules'] = modules

            # Extract buildings
            buildings_match = re.search(r'buildings=\s*\{([^}]+)\}', sb_block)
            if buildings_match:
                buildings = re.findall(r'\d+=(\w+)', buildings_match.group(1))
                starbase_info['buildings'] = buildings

            starbases_found.append(starbase_info)

            # Count by level
            clean_level = starbase_info['level']
            if clean_level not in level_counts:
                level_counts[clean_level] = 0
            level_counts[clean_level] += 1

        result['starbases'] = starbases_found[:50]  # Limit to 50
        result['count'] = len(starbases_found)
        result['by_level'] = level_counts
        result['starbase_ids'] = player_starbase_ids[:100]

        return result

    def search(self, query: str, max_results: int = 5, context_chars: int = 500) -> dict:
        """Search the full gamestate for specific text.

        Args:
            query: Text to search for
            max_results: Maximum number of results to return (capped at 10)
            context_chars: Characters of context around each match (capped at 500)

        Returns:
            Dict with search results (total output capped at ~4000 chars)
        """
        # Cap parameters to prevent context overflow
        max_results = min(max_results, 10)
        context_chars = min(context_chars, 500)
        MAX_TOTAL_OUTPUT = 4000  # Hard limit on total context returned

        result = {
            'query': query,
            'matches': [],
            'total_found': 0
        }

        # Sanitize query - remove any potential injection characters
        # Allow only alphanumeric, spaces, underscores, and common punctuation
        sanitized_query = ''.join(
            c for c in query
            if c.isalnum() or c in ' _-.,\'"'
        )
        if not sanitized_query:
            result['error'] = 'Query contains no valid search characters'
            return result

        query_lower = sanitized_query.lower()
        gamestate_lower = self.gamestate.lower()

        total_context_size = 0
        start = 0

        while len(result['matches']) < max_results:
            pos = gamestate_lower.find(query_lower, start)
            if pos == -1:
                break

            result['total_found'] += 1

            # Get context
            context_start = max(0, pos - context_chars // 2)
            context_end = min(len(self.gamestate), pos + len(query) + context_chars // 2)

            context = self.gamestate[context_start:context_end]

            # Sanitize context output - escape special characters that could
            # be interpreted as instructions
            context = context.replace('{{', '{ {').replace('}}', '} }')

            # Check if adding this context would exceed our limit
            if total_context_size + len(context) > MAX_TOTAL_OUTPUT:
                result['truncated'] = True
                break

            total_context_size += len(context)

            result['matches'].append({
                'position': pos,
                'context': context
            })

            start = pos + 1

        # Count total matches (without retrieving context)
        while True:
            pos = gamestate_lower.find(query_lower, start)
            if pos == -1:
                break
            result['total_found'] += 1
            start = pos + 1

        return result

    def get_summary(self) -> str:
        """Get a brief text summary of the save for context.

        Returns:
            Short summary string
        """
        meta = self.get_metadata()
        player = self.get_player_status()
        colonies = player.get('colonies', {})

        summary = f"""Save File Summary:
- Empire: {meta.get('name', 'Unknown')}
- Date: {meta.get('date', 'Unknown')}
- Version: {meta.get('version', 'Unknown')}
- Colonies: {colonies.get('total_count', 'Unknown')} ({colonies.get('total_population', 0)} pops)
- Fleets: {player.get('fleet_count', 'Unknown')}
- Military Power: {player.get('military_power', 'Unknown')}
- Economy Power: {player.get('economy_power', 'Unknown')}
- Tech Power: {player.get('tech_power', 'Unknown')}
"""
        return summary

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

    def get_full_briefing(self) -> dict:
        """Get comprehensive empire overview for strategic briefings.

        This aggregates data from all major tools into a single response,
        reducing API round-trips from 6+ to 1 for broad questions.

        Returns:
            Dictionary with player status, resources, diplomacy, planets,
            starbases, and leaders (~4k tokens, optimized for context efficiency)
        """
        # Get all data
        player = self.get_player_status()
        resources = self.get_resources()
        diplomacy = self.get_diplomacy()
        planets = self.get_planets()
        starbases = self.get_starbases()
        leaders = self.get_leaders()
        technology = self.get_technology()

        # Strip raw_data_preview fields to reduce context size
        player_clean = self._strip_previews(player)

        # Build optimized briefing
        return {
            'meta': {
                'empire_name': player_clean.get('empire_name'),
                'date': player_clean.get('date'),
                'player_id': player_clean.get('player_id'),
            },
            'military': {
                'military_power': player_clean.get('military_power'),
                'military_fleets': player_clean.get('military_fleet_count'),
                'military_ships': player_clean.get('military_ships'),
                'starbases': player_clean.get('starbase_count'),
            },
            'economy': {
                'economy_power': player_clean.get('economy_power'),
                'tech_power': player_clean.get('tech_power'),
                # Use 'net_monthly' (correct key) and 'summary' for pre-computed values
                'net_monthly': resources.get('net_monthly', {}),
                'key_resources': {
                    # net_monthly uses bare keys like 'energy', not 'energy_net'
                    'energy': resources.get('net_monthly', {}).get('energy'),
                    'minerals': resources.get('net_monthly', {}).get('minerals'),
                    'alloys': resources.get('net_monthly', {}).get('alloys'),
                    'consumer_goods': resources.get('net_monthly', {}).get('consumer_goods'),
                    'research_total': resources.get('summary', {}).get('research_total'),
                },
            },
            'territory': {
                'celestial_bodies_in_territory': player_clean.get('celestial_bodies_in_territory'),
                'colonies': player_clean.get('colonies', {}),  # Breakdown by habitats vs planets
                'planets_by_type': planets.get('by_type', {}),
                'top_colonies': planets.get('planets', [])[:10],  # Top 10 colonies with details
            },
            'diplomacy': {
                'relation_count': diplomacy.get('relation_count'),
                'allies': diplomacy.get('allies', []),
                'rivals': diplomacy.get('rivals', []),
                'federation': diplomacy.get('federation'),
                'summary': diplomacy.get('summary', {}),
            },
            'defense': {
                'count': starbases.get('count'),
                'by_level': starbases.get('by_level', {}),
                'starbases': starbases.get('starbases', []),
            },
            'leadership': {
                'count': leaders.get('count'),
                'by_class': leaders.get('by_class', {}),
                'leaders': leaders.get('leaders', [])[:15],  # Top 15 leaders
            },
            'technology': {
                'current_research': technology.get('current_research', {}),
                'tech_count': technology.get('tech_count', 0),
                'by_category': technology.get('by_category', {}),
            },
        }

    def get_slim_briefing(self) -> dict:
        """Get slim empire snapshot with NO truncated lists.

        Unlike get_full_briefing(), this only includes COMPLETE data:
        - Summary counts (leaders, planets, starbases)
        - Key numbers (military power, economy)
        - Headlines (capital planet, ruler, current research)
        - NO truncated lists that could cause hallucination

        This forces the model to call get_details() for specific information
        about leaders, planets, diplomacy, etc.

        Returns:
            Dictionary with ~1.5KB of complete summary data
        """
        player = self.get_player_status()
        resources = self.get_resources()
        diplomacy = self.get_diplomacy()
        planets = self.get_planets()
        starbases = self.get_starbases()
        leaders = self.get_leaders()
        technology = self.get_technology()

        # Find capital planet (first planet, usually homeworld)
        all_planets = planets.get('planets', [])
        capital = all_planets[0] if all_planets else {}

        # Find ruler (official class leader, or first leader)
        all_leaders = leaders.get('leaders', [])
        ruler = next(
            (l for l in all_leaders if l.get('class') == 'official'),
            all_leaders[0] if all_leaders else {}
        )

        return {
            'meta': {
                'empire_name': player.get('empire_name'),
                'date': player.get('date'),
            },
            'military': {
                'power': player.get('military_power'),
                'military_fleets': player.get('military_fleet_count'),
                'military_ships': player.get('military_ships'),
                'starbases': player.get('starbase_count'),
            },
            'economy': {
                'power': player.get('economy_power'),
                'tech_power': player.get('tech_power'),
                'net_monthly': resources.get('net_monthly', {}),
            },
            'territory': {
                'total_colonies': player.get('colonies', {}).get('total', 0),
                'habitats': player.get('colonies', {}).get('habitats', 0),
                'by_type': planets.get('by_type', {}),
                # HEADLINE: Capital only (not all planets)
                'capital': {
                    'name': capital.get('name'),
                    'type': capital.get('type'),
                    'population': capital.get('population'),
                    'stability': capital.get('stability'),
                } if capital else None,
            },
            'leadership': {
                'total_count': leaders.get('count'),
                'by_class': leaders.get('by_class', {}),
                # HEADLINE: Ruler only (not all leaders)
                'ruler': {
                    'name': ruler.get('name'),
                    'class': ruler.get('class'),
                    'level': ruler.get('level'),
                    'traits': ruler.get('traits', []),
                } if ruler else None,
                # NO leaders list - forces tool use for details
            },
            'diplomacy': {
                'contact_count': diplomacy.get('relation_count'),
                'ally_count': len(diplomacy.get('allies', [])),
                'rival_count': len(diplomacy.get('rivals', [])),
                'federation': diplomacy.get('federation'),
                # NO relations list - forces tool use for details
            },
            'defense': {
                'starbase_count': starbases.get('count'),
                'by_level': starbases.get('by_level', {}),
                # NO starbases list - forces tool use for details
            },
            'technology': {
                'current_research': technology.get('current_research', {}),
                'tech_count': technology.get('tech_count', 0),
                'by_category': technology.get('by_category', {}),
            },
        }

    def get_empire_identity(self) -> dict:
        """Extract static empire identity for personality generation.

        This extracts ethics, government, civics, and species info from the
        player's country block. This data comes from empire creation and
        only changes via government reform or ethics shift events.

        Returns:
            Dictionary with ethics, government, civics, species, and gestalt flags
        """
        result = {
            'ethics': [],
            'government': None,
            'civics': [],
            'authority': None,
            'species_class': None,
            'species_name': None,
            'is_gestalt': False,
            'is_machine': False,
            'is_hive_mind': False,
            'empire_name': self.get_metadata().get('name', 'Unknown'),
        }

        player_id = self.get_player_empire_id()

        # Find the country section and player's data
        country_match = re.search(r'^country=\s*\{', self.gamestate, re.MULTILINE)
        if not country_match:
            result['error'] = "Could not find country section"
            return result

        start = country_match.start()
        player_match = re.search(r'\n\t0=\s*\{', self.gamestate[start:start + 1000000])
        if not player_match:
            result['error'] = "Could not find player country"
            return result

        player_start = start + player_match.start()
        # Need larger chunk - government block can be far into the country data
        player_chunk = self.gamestate[player_start:player_start + 500000]

        # Extract ethics from ethos={} block
        # Format: ethos={ ethic="ethic_fanatic_egalitarian" ethic="ethic_xenophile" }
        ethos_match = re.search(r'ethos=\s*\{([^}]+)\}', player_chunk)
        if ethos_match:
            ethos_block = ethos_match.group(1)
            ethics_matches = re.findall(r'ethic="ethic_([^"]+)"', ethos_block)
            result['ethics'] = ethics_matches

        # Check for gestalt consciousness
        if 'gestalt_consciousness' in str(result['ethics']):
            result['is_gestalt'] = True
            # Determine if machine or hive mind from authority
            if 'auth_machine_intelligence' in player_chunk:
                result['is_machine'] = True
            elif 'auth_hive_mind' in player_chunk:
                result['is_hive_mind'] = True

        # Extract government block
        # Format: government={ type="gov_representative_democracy" authority="auth_democratic" civics={...} }
        gov_block_match = re.search(r'government=\s*\{', player_chunk)
        if gov_block_match:
            gov_start = gov_block_match.start()
            # Extract a chunk for the government block
            gov_chunk = player_chunk[gov_start:gov_start + 2000]

            # Extract government type
            type_match = re.search(r'type="([^"]+)"', gov_chunk)
            if type_match:
                result['government'] = type_match.group(1).replace('gov_', '')

            # Extract authority
            auth_match = re.search(r'authority="([^"]+)"', gov_chunk)
            if auth_match:
                result['authority'] = auth_match.group(1).replace('auth_', '')

            # Extract civics
            civics_match = re.search(r'civics=\s*\{([^}]+)\}', gov_chunk)
            if civics_match:
                civics_block = civics_match.group(1)
                civics = re.findall(r'"civic_([^"]+)"', civics_block)
                result['civics'] = civics

        # Update gestalt flags based on authority
        if result['authority'] == 'machine_intelligence':
            result['is_gestalt'] = True
            result['is_machine'] = True
        elif result['authority'] == 'hive_mind':
            result['is_gestalt'] = True
            result['is_hive_mind'] = True

        # Extract founder species info
        founder_match = re.search(r'founder_species_ref=(\d+)', player_chunk)
        if founder_match:
            species_id = founder_match.group(1)
            # Look up species in species_db (first 2MB of file)
            species_chunk = self.gamestate[:2000000]
            species_pattern = rf'\b{species_id}=\s*\{{[^}}]*?class="([^"]+)"'
            species_match = re.search(species_pattern, species_chunk, re.DOTALL)
            if species_match:
                result['species_class'] = species_match.group(1)

            # Get species name
            species_name_pattern = rf'\b{species_id}=\s*\{{[^}}]*?name="([^"]+)"'
            name_match = re.search(species_name_pattern, species_chunk, re.DOTALL)
            if name_match:
                result['species_name'] = name_match.group(1)

        return result

    def get_details(self, categories: list[str], limit: int = 10) -> dict:
        """Get detailed information for one or more categories.

        This is a unified drill-down tool that replaces multiple narrow tools.
        Use get_full_briefing() first to get the overview, then use this tool
        for additional details on specific categories.

        This function supports batching: request multiple categories in one call
        to reduce LLM tool round-trips.

        Args:
            categories: List of categories to return. Each item must be one of:
                - "leaders"
                - "planets"
                - "starbases"
                - "technology"
                - "wars"
                - "fleets"
                - "resources"
                - "diplomacy"
            limit: Max items to return for list-like fields (default 10, capped at 50)

        Returns:
            Dictionary mapping each category to its detailed data.
            If any categories are invalid, an "errors" field is included.
        """
        valid_categories = {
            "leaders", "planets", "starbases", "technology",
            "wars", "fleets", "resources", "diplomacy",
        }

        if not isinstance(categories, list) or not categories:
            return {"error": "categories must be a non-empty list of strings"}

        # Cap limit to prevent excessive output
        limit = min(max(1, limit), 50)

        results: dict[str, dict] = {}
        errors: dict[str, str] = {}

        for category in categories:
            if category not in valid_categories:
                errors[category] = f"Invalid category. Must be one of: {', '.join(sorted(valid_categories))}"
                continue

            if category == "leaders":
                data = self.get_leaders()
                if 'leaders' in data:
                    data['leaders'] = data['leaders'][:limit]
                results[category] = data
                continue

            if category == "planets":
                data = self.get_planets()
                if 'planets' in data:
                    data['planets'] = data['planets'][:limit]
                results[category] = data
                continue

            if category == "starbases":
                data = self.get_starbases()
                if 'starbases' in data:
                    data['starbases'] = data['starbases'][:limit]
                results[category] = data
                continue

            if category == "technology":
                data = self.get_technology()
                if 'sample_technologies' in data:
                    data['sample_technologies'] = data['sample_technologies'][:limit]
                if 'completed_technologies' in data:
                    data['completed_technologies'] = data['completed_technologies'][:limit]
                results[category] = data
                continue

            if category == "wars":
                data = self.get_wars()
                if 'wars' in data:
                    data['wars'] = data['wars'][:limit]
                results[category] = data
                continue

            if category == "fleets":
                data = self.get_fleets()
                if 'fleet_names' in data:
                    data['fleet_names'] = data['fleet_names'][:limit]
                results[category] = data
                continue

            if category == "resources":
                results[category] = self.get_resources()
                continue

            if category == "diplomacy":
                data = self.get_diplomacy()
                if 'relations' in data:
                    data['relations'] = data['relations'][:limit]
                results[category] = data
                continue

        out: dict = {"results": results, "limit": limit}
        if errors:
            out["errors"] = errors
        return out

    def get_situation(self) -> dict:
        """Analyze current game situation for personality tone modifiers.

        This analyzes the current game state to determine appropriate
        tone adjustments for the advisor personality.

        Returns:
            Dictionary with game phase, war status, economy state, and diplomatic situation
        """
        result = {
            'game_phase': 'early',
            'year': 2200,
            'at_war': False,
            'war_count': 0,
            'contacts_made': False,
            'contact_count': 0,
            'rivals': [],
            'allies': [],
            'crisis_active': False,
        }

        # Get game date and calculate year
        meta = self.get_metadata()
        date_str = meta.get('date', '2200.01.01')
        try:
            year = int(date_str.split('.')[0])
            result['year'] = year

            # Determine game phase
            if year < 2230:
                result['game_phase'] = 'early'
            elif year < 2300:
                result['game_phase'] = 'mid_early'
            elif year < 2350:
                result['game_phase'] = 'mid_late'
            elif year < 2400:
                result['game_phase'] = 'late'
            else:
                result['game_phase'] = 'endgame'
        except (ValueError, IndexError):
            pass

        # Check war status - use the improved player-specific war detection
        wars = self.get_wars()
        result['war_count'] = wars.get('count', 0)
        result['at_war'] = wars.get('player_at_war', False)
        result['wars'] = wars.get('wars', [])

        # Check diplomatic situation
        diplomacy = self.get_diplomacy()
        result['contact_count'] = diplomacy.get('relation_count', 0)
        result['contacts_made'] = result['contact_count'] > 0
        result['allies'] = diplomacy.get('allies', [])
        result['rivals'] = diplomacy.get('rivals', [])

        # Get economy data - provide raw values, let the model interpret
        # based on context (empire size, game phase, stockpiles)
        resources = self.get_resources()
        net_monthly = resources.get('net_monthly', {})

        # Provide key resource net values for the model to interpret
        result['economy'] = {
            'energy_net': net_monthly.get('energy', 0),
            'minerals_net': net_monthly.get('minerals', 0),
            'alloys_net': net_monthly.get('alloys', 0),
            'consumer_goods_net': net_monthly.get('consumer_goods', 0),
            'research_net': (
                net_monthly.get('physics_research', 0) +
                net_monthly.get('society_research', 0) +
                net_monthly.get('engineering_research', 0)
            ),
            '_note': 'Raw monthly net values - interpret based on empire size and game phase'
        }

        # Count negative resources as a simple indicator
        negative_resources = sum(1 for v in [
            net_monthly.get('energy', 0),
            net_monthly.get('minerals', 0),
            net_monthly.get('food', 0),
            net_monthly.get('consumer_goods', 0),
            net_monthly.get('alloys', 0),
        ] if v < 0)

        result['economy']['resources_in_deficit'] = negative_resources

        # Check for crisis (search for crisis-related content)
        crisis_keywords = ['prethoryn', 'contingency', 'unbidden', 'crisis_faction']
        for keyword in crisis_keywords:
            if keyword in self.gamestate.lower():
                # Further check if crisis is actually active
                if re.search(rf'{keyword}.*country_type="(swarm|crisis|extradimensional)"',
                           self.gamestate.lower()):
                    result['crisis_active'] = True
                    break

        # Check for Fallen Empires (both dormant and awakened)
        fallen = self.get_fallen_empires()
        if fallen.get('total_count', 0) > 0:
            result['fallen_empires'] = {
                'total_count': fallen['total_count'],
                'dormant_count': fallen['dormant_count'],
                'awakened_count': fallen['awakened_count'],
                'war_in_heaven': fallen['war_in_heaven'],
                'empires': [
                    {
                        'name': e['name'],
                        'status': e['status'],
                        'archetype': e['archetype'],
                        'power_ratio': e['power_ratio'],
                    }
                    for e in fallen['fallen_empires']
                ]
            }

        return result


# Standalone functions for tool use (stateless, take extractor as param)

def get_player_status(extractor: SaveExtractor) -> dict:
    """Get the player's current empire status including resources and fleet power.

    Args:
        extractor: SaveExtractor instance

    Returns:
        Dict with player empire status
    """
    return extractor.get_player_status()


def get_empire(extractor: SaveExtractor, name: str) -> dict:
    """Get detailed information about a specific empire by name.

    Args:
        extractor: SaveExtractor instance
        name: Name of the empire to look up

    Returns:
        Dict with empire details
    """
    return extractor.get_empire(name)


def get_wars(extractor: SaveExtractor) -> dict:
    """Get information about active wars.

    Args:
        extractor: SaveExtractor instance

    Returns:
        Dict with war information
    """
    return extractor.get_wars()


def get_fleets(extractor: SaveExtractor) -> dict:
    """Get the player's fleet information.

    Args:
        extractor: SaveExtractor instance

    Returns:
        Dict with fleet details
    """
    return extractor.get_fleets()


def search_save(extractor: SaveExtractor, query: str) -> dict:
    """Search the full save file for specific text.

    Args:
        extractor: SaveExtractor instance
        query: Text to search for

    Returns:
        Dict with search results and context
    """
    return extractor.search(query)


def get_leaders(extractor: SaveExtractor) -> dict:
    """Get the player's leader information.

    Args:
        extractor: SaveExtractor instance

    Returns:
        Dict with leader details
    """
    return extractor.get_leaders()


def get_technology(extractor: SaveExtractor) -> dict:
    """Get the player's technology research status.

    Args:
        extractor: SaveExtractor instance

    Returns:
        Dict with technology details
    """
    return extractor.get_technology()


def get_resources(extractor: SaveExtractor) -> dict:
    """Get the player's resource/economy snapshot.

    Args:
        extractor: SaveExtractor instance

    Returns:
        Dict with resource details
    """
    return extractor.get_resources()


def get_diplomacy(extractor: SaveExtractor) -> dict:
    """Get the player's diplomatic relations.

    Args:
        extractor: SaveExtractor instance

    Returns:
        Dict with diplomacy details
    """
    return extractor.get_diplomacy()


def get_planets(extractor: SaveExtractor) -> dict:
    """Get the player's colonized planets.

    Args:
        extractor: SaveExtractor instance

    Returns:
        Dict with planet details
    """
    return extractor.get_planets()


def get_starbases(extractor: SaveExtractor) -> dict:
    """Get the player's starbase information.

    Args:
        extractor: SaveExtractor instance

    Returns:
        Dict with starbase details
    """
    return extractor.get_starbases()


def get_pop_statistics(extractor: SaveExtractor) -> dict:
    """Get detailed population statistics for the player's empire.

    Aggregates pop data across all player-owned planets including
    breakdowns by species, job category, stratum, and employment.

    Args:
        extractor: SaveExtractor instance

    Returns:
        Dict with population statistics including by_species, by_job_category,
        by_stratum, happiness_avg, employed_pops, unemployed_pops
    """
    return extractor.get_pop_statistics()


if __name__ == "__main__":
    # Test the extractor
    import sys

    if len(sys.argv) < 2:
        print("Usage: python save_extractor.py <save_file.sav>")
        sys.exit(1)

    extractor = SaveExtractor(sys.argv[1])

    print("=== Metadata ===")
    print(extractor.get_metadata())

    print("\n=== Player Status ===")
    print(extractor.get_player_status())

    print("\n=== Summary ===")
    print(extractor.get_summary())
