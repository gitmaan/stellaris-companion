from __future__ import annotations

import re
import zipfile
from datetime import datetime
from pathlib import Path

class MilitaryMixin:
    """Domain methods extracted from the original SaveExtractor."""

    def _extract_braced_block(self, content: str, key: str) -> str | None:
        """Extract the full `key={...}` block from a larger text chunk."""
        match = re.search(rf'\b{re.escape(key)}\s*=\s*\{{', content)
        if not match:
            return None

        start = match.start()
        brace_count = 0
        started = False

        for i, char in enumerate(content[start:], start):
            if char == '{':
                brace_count += 1
                started = True
            elif char == '}':
                brace_count -= 1
                if started and brace_count == 0:
                    return content[start : i + 1]

        return None

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

            # Extract war name - can be either name="string" or name={key="string"...}
            war_name = None
            simple_name_match = re.search(r'\bname\s*=\s*"([^"]+)"', war_block[:2000])
            if simple_name_match:
                war_name = simple_name_match.group(1)
            else:
                # Try nested block format: name={...key="..."...}
                name_block = self._extract_braced_block(war_block[:5000], 'name')
                if name_block:
                    key_match = re.search(r'\bkey="([^"]+)"', name_block)
                    if key_match:
                        war_name = key_match.group(1)

            if not war_name:
                war_name = f"War #{entry_match.group(1)}"  # Fallback name

            # Extract start date
            start_date_match = re.search(r'start_date\s*=\s*"?([0-9.]+)"?', war_block)
            start_date = start_date_match.group(1) if start_date_match else None

            # Extract exhaustion values - use findall and take LAST match
            # The battles={} block contains per-battle exhaustion (usually 0 or small)
            # The war-level totals appear AFTER battles as top-level fields
            # Values are stored as 0-1 decimals, multiply by 100 for percentage
            attacker_exhaustion_matches = re.findall(r'attacker_war_exhaustion\s*=\s*([\d.]+)', war_block)
            defender_exhaustion_matches = re.findall(r'defender_war_exhaustion\s*=\s*([\d.]+)', war_block)
            attacker_exhaustion = float(attacker_exhaustion_matches[-1]) * 100 if attacker_exhaustion_matches else 0.0
            defender_exhaustion = float(defender_exhaustion_matches[-1]) * 100 if defender_exhaustion_matches else 0.0

            # Extract war goal
            war_goal_match = re.search(r'war_goal\s*=\s*\{[^}]*type\s*=\s*"?([^"\s}]+)"?', war_block, re.DOTALL)
            war_goal = war_goal_match.group(1) if war_goal_match else "unknown"

            # Extract attacker country IDs using proper brace matching
            attacker_ids = []
            attackers_block = self._extract_braced_block(war_block, 'attackers')
            if attackers_block:
                attacker_ids = re.findall(r'\bcountry\s*=\s*(\d+)', attackers_block)

            # Extract defender country IDs using proper brace matching
            defender_ids = []
            defenders_block = self._extract_braced_block(war_block, 'defenders')
            if defenders_block:
                defender_ids = re.findall(r'\bcountry\s*=\s*(\d+)', defenders_block)

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

    def get_fleet_composition(self, limit: int = 50) -> dict:
        """Get ship class composition across the player's fleets.

        Returns:
            Dict with:
              - fleets: list[{fleet_id, name, ship_classes, total_ships}]
              - by_class_total: dict[str,int]
              - fleet_count: int
        """
        result = {
            "fleets": [],
            "by_class_total": {},
            "fleet_count": 0,
        }

        player_id = self.get_player_empire_id()
        country_content = self._find_player_country_content(player_id)
        if not country_content:
            return result

        owned_fleet_ids = self._get_owned_fleet_ids(country_content)
        if not owned_fleet_ids:
            return result

        fleet_bounds = self._get_section_bounds("fleet")
        ships_bounds = self._get_section_bounds("ships")
        designs_bounds = self._get_section_bounds("ship_design")
        if not fleet_bounds or not ships_bounds or not designs_bounds:
            return result

        fleet_start, fleet_end = fleet_bounds
        ships_start, ships_end = ships_bounds
        designs_start, designs_end = designs_bounds

        design_to_size: dict[str, str] = {}
        design_entry_re = re.compile(r"(?m)^\t(\d+)\s*=\s*\{")
        for m in design_entry_re.finditer(self.gamestate, designs_start, designs_end):
            design_id = m.group(1)
            snippet = self.gamestate[m.start() : min(m.start() + 2500, designs_end)]
            size_m = re.search(r'\bship_size="([^"]+)"', snippet)
            if size_m:
                design_to_size[design_id] = size_m.group(1)

        ship_to_design: dict[str, str] = {}
        ship_entry_re = re.compile(r"(?m)^\t(\d+)\s*=\s*\{")
        for m in ship_entry_re.finditer(self.gamestate, ships_start, ships_end):
            ship_id = m.group(1)
            snippet = self.gamestate[m.start() : min(m.start() + 3000, ships_end)]
            impl_m = re.search(r'\bship_design_implementation\s*=\s*\{[^}]*\bdesign\s*=\s*(\d+)', snippet)
            if impl_m:
                ship_to_design[ship_id] = impl_m.group(1)
                continue

            design_m = re.search(r'\bship_design\s*=\s*(\d+)', snippet)
            if design_m:
                ship_to_design[ship_id] = design_m.group(1)

        owned_set = set(owned_fleet_ids)
        fleets: list[dict] = []
        by_class_total: dict[str, int] = {}

        fleet_entry_re = re.compile(r"(?m)^\t(\d+)\s*=\s*\{")
        for match in fleet_entry_re.finditer(self.gamestate, fleet_start, fleet_end):
            fleet_id = match.group(1)
            if fleet_id not in owned_set:
                continue

            start = match.start()
            brace_count = 0
            end = None
            for i in range(start, fleet_end):
                char = self.gamestate[i]
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end = i + 1
                        break
            if end is None:
                continue

            fleet_block = self.gamestate[start:end]
            header = fleet_block[:2500]

            if "station=yes" in header:
                continue
            if "civilian=yes" in header:
                continue

            mp_match = re.search(r'\bmilitary_power=([\d.]+)', header)
            military_power = float(mp_match.group(1)) if mp_match else 0.0
            if military_power <= 100:
                continue

            name_value = None
            name_block = self._extract_braced_block(fleet_block, "name")
            if name_block:
                key_match = re.search(r'\bkey="([^"]+)"', name_block)
                if key_match:
                    name_value = key_match.group(1)
            if not name_value:
                name_match = re.search(r'\bname="([^"]+)"', header)
                if name_match:
                    name_value = name_match.group(1)

            if name_value and name_value.startswith("shipclass_"):
                name_value = name_value.replace("shipclass_", "").replace("_name", "").title()

            ships_block = self._extract_braced_block(fleet_block, "ships")
            if not ships_block:
                continue

            open_brace = ships_block.find("{")
            close_brace = ships_block.rfind("}")
            if open_brace == -1 or close_brace == -1 or close_brace <= open_brace:
                continue

            ship_ids = re.findall(r"\d+", ships_block[open_brace + 1 : close_brace])
            ship_classes: dict[str, int] = {}

            for ship_id in ship_ids:
                design_id = ship_to_design.get(ship_id)
                ship_size = design_to_size.get(design_id or "", "") if design_id else ""
                ship_size = ship_size.strip() if ship_size else "unknown"

                ship_classes[ship_size] = ship_classes.get(ship_size, 0) + 1
                by_class_total[ship_size] = by_class_total.get(ship_size, 0) + 1

            total_ships = sum(ship_classes.values())
            fleets.append(
                {
                    "fleet_id": str(fleet_id),
                    "name": name_value,
                    "ship_classes": ship_classes,
                    "total_ships": total_ships,
                }
            )

        fleets.sort(key=lambda f: f.get("total_ships", 0), reverse=True)

        result["fleet_count"] = len(fleets)
        result["by_class_total"] = by_class_total
        result["fleets"] = fleets[: max(0, int(limit))]
        return result

    def get_starbases(self) -> dict:
        """Get the player's starbase information with defense breakdown.

        Returns:
            Dict with starbase locations, levels, modules, and defense analysis:
            - starbases: List of starbase objects with:
                - id, level, type, modules, buildings (existing)
                - defense_modules: list of defense module types (gun_battery, hangar_bay, missile_battery)
                - defense_buildings: list of defense-enhancing buildings
                - defense_platform_count: count of defense platforms
                - defense_score: calculated defense strength score
            - count: Total starbase count
            - by_level: Dict of level -> count
            - total_defense_score: Sum of all starbase defense_scores
        """
        result = {
            'starbases': [],
            'count': 0,
            'by_level': {},
            'total_defense_score': 0
        }

        player_id = self.get_player_empire_id()

        # Defense module types to track
        DEFENSE_MODULES = {'gun_battery', 'hangar_bay', 'missile_battery'}
        # Defense-enhancing building types
        DEFENSE_BUILDINGS = {'target_uplink_computer', 'defense_grid', 'command_center',
                             'communications_jammer', 'disruption_field', 'nebula_refinery'}
        # Level bonus for defense score
        LEVEL_BONUS = {
            'outpost': 0,
            'starport': 100,
            'starhold': 200,
            'starfortress': 400,
            'citadel': 800
        }

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
        total_defense_score = 0

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

            clean_level = level.replace('starbase_level_', '')
            starbase_info = {
                'id': sb_id,
                'level': clean_level
            }

            # Extract type if present
            type_match = re.search(r'type="([^"]+)"', sb_block)
            if type_match:
                starbase_info['type'] = type_match.group(1)

            # Extract modules
            modules = []
            modules_match = re.search(r'modules=\s*\{([^}]+)\}', sb_block)
            if modules_match:
                modules = re.findall(r'\d+=(\w+)', modules_match.group(1))
                starbase_info['modules'] = modules

            # Extract buildings
            buildings = []
            buildings_match = re.search(r'buildings=\s*\{([^}]+)\}', sb_block)
            if buildings_match:
                buildings = re.findall(r'\d+=(\w+)', buildings_match.group(1))
                starbase_info['buildings'] = buildings

            # Extract orbitals (defense platforms)
            defense_platform_count = 0
            orbitals_match = re.search(r'orbitals=\s*\{([^}]+)\}', sb_block)
            if orbitals_match:
                orbital_ids = re.findall(r'\d+=(\d+)', orbitals_match.group(1))
                # Count non-null orbitals (4294967295 = empty slot)
                defense_platform_count = sum(1 for oid in orbital_ids if oid != '4294967295')

            # Calculate defense-specific fields
            defense_modules = [m for m in modules if m in DEFENSE_MODULES]
            defense_buildings = [b for b in buildings if b in DEFENSE_BUILDINGS]

            # Calculate defense score
            gun_batteries = modules.count('gun_battery')
            hangar_bays = modules.count('hangar_bay')
            missile_batteries = modules.count('missile_battery')
            level_bonus = LEVEL_BONUS.get(clean_level, 0)

            defense_score = (
                (gun_batteries * 100) +
                (hangar_bays * 80) +
                (missile_batteries * 90) +
                (defense_platform_count * 50) +
                level_bonus
            )

            # Add defense fields to starbase info
            starbase_info['defense_modules'] = defense_modules
            starbase_info['defense_buildings'] = defense_buildings
            starbase_info['defense_platform_count'] = defense_platform_count
            starbase_info['defense_score'] = defense_score

            starbases_found.append(starbase_info)
            total_defense_score += defense_score

            # Count by level
            if clean_level not in level_counts:
                level_counts[clean_level] = 0
            level_counts[clean_level] += 1

        # Full list (no truncation); callers that need caps should slice.
        result['starbases'] = starbases_found
        result['count'] = len(starbases_found)
        result['by_level'] = level_counts
        result['starbase_ids'] = player_starbase_ids
        result['total_defense_score'] = total_defense_score

        return result

    def get_megastructures(self) -> dict:
        """Get the player's megastructures (gateways, dyson spheres, ringworlds, etc).

        Returns:
            Dict with:
              - megastructures: List of megastructure objects with type, status
              - count: Total count of player megastructures
              - by_type: Dict mapping type to count
              - ruined_available: List of ruined megastructures player could repair
        """
        result = {
            'megastructures': [],
            'count': 0,
            'by_type': {},
            'ruined_available': [],
        }

        player_id = self.get_player_empire_id()

        # Find megastructures section
        mega_start = self.gamestate.find('\nmegastructures=')
        if mega_start == -1:
            return result

        # Get a large chunk for megastructures
        mega_section = self.gamestate[mega_start:mega_start + 3000000]

        # Find all megastructure entries
        entry_pattern = r'\n\t(\d+)=\s*\{'
        entries = list(re.finditer(entry_pattern, mega_section))

        player_megas = []
        ruined_megas = []
        by_type: dict[str, int] = {}

        for i, match in enumerate(entries):
            mega_id = match.group(1)
            start_pos = match.end()

            # Find end of this block using brace matching
            brace_count = 1
            pos = start_pos
            max_pos = min(start_pos + 2000, len(mega_section))
            while brace_count > 0 and pos < max_pos:
                if mega_section[pos] == '{':
                    brace_count += 1
                elif mega_section[pos] == '}':
                    brace_count -= 1
                pos += 1

            block = mega_section[start_pos:pos]

            # Extract fields
            owner_match = re.search(r'\n\s*owner=(\d+)', block)
            type_match = re.search(r'\n\s*type="([^"]+)"', block)
            planet_match = re.search(r'\n\s*planet=(\d+)', block)

            if not type_match:
                continue

            mega_type = type_match.group(1)
            owner = int(owner_match.group(1)) if owner_match else None

            # Check if this is a ruined megastructure (could be repaired)
            is_ruined = 'ruined' in mega_type

            # Track ruined megastructures that could potentially be repaired
            if is_ruined:
                # These could be anywhere in the galaxy
                ruined_info = {
                    'id': mega_id,
                    'type': mega_type,
                    'owner': owner,
                }
                if planet_match and planet_match.group(1) != '4294967295':
                    ruined_info['planet_id'] = planet_match.group(1)
                ruined_megas.append(ruined_info)

            # Only count megastructures owned by player
            if owner != player_id:
                continue

            # Determine status from type name
            status = 'complete'
            if is_ruined:
                status = 'ruined'
            elif '_restored' in mega_type:
                status = 'restored'
            elif any(x in mega_type for x in ['_0', '_1', '_2', '_3', '_4', '_site']):
                status = 'under_construction'

            # Clean up type name for display
            display_type = mega_type
            # Remove stage suffixes for cleaner grouping
            for suffix in ['_ruined', '_restored', '_0', '_1', '_2', '_3', '_4', '_5', '_site']:
                if display_type.endswith(suffix):
                    display_type = display_type[:-len(suffix)]
                    break

            mega_info = {
                'id': mega_id,
                'type': mega_type,
                'display_type': display_type,
                'status': status,
            }

            if planet_match and planet_match.group(1) != '4294967295':
                mega_info['planet_id'] = planet_match.group(1)

            player_megas.append(mega_info)

            # Count by display type
            by_type[display_type] = by_type.get(display_type, 0) + 1

        result['megastructures'] = player_megas
        result['count'] = len(player_megas)
        result['by_type'] = by_type
        # Return all ruined megastructures - late-game galaxies can have many
        result['ruined_available'] = ruined_megas

        return result
