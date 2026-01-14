from __future__ import annotations

import re
import zipfile
from datetime import datetime
from pathlib import Path

class MilitaryMixin:
    """Domain methods extracted from the original SaveExtractor."""

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

