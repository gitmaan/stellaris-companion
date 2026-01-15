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

        fleet_section = self._extract_section("fleet")
        ships_section = self._extract_section("ships")
        designs_section = self._extract_section("ship_design")
        if not fleet_section or not ships_section or not designs_section:
            return result

        design_to_size: dict[str, str] = {}
        for m in re.finditer(r'\n\t(\d+)=\n\t\{', designs_section):
            design_id = m.group(1)
            snippet = designs_section[m.start() : m.start() + 2500]
            size_m = re.search(r'\bship_size="([^"]+)"', snippet)
            if size_m:
                design_to_size[design_id] = size_m.group(1)

        ship_to_design: dict[str, str] = {}
        for m in re.finditer(r'\n\t(\d+)=\n\t\{', ships_section):
            ship_id = m.group(1)
            snippet = ships_section[m.start() : m.start() + 3000]
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

        for match in re.finditer(r'\n\t(\d+)=\n\t\{', fleet_section):
            fleet_id = match.group(1)
            if fleet_id not in owned_set:
                continue

            start = match.start()
            brace_count = 0
            end = None
            for i, char in enumerate(fleet_section[start:], start):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end = i + 1
                        break
            if end is None:
                continue

            fleet_block = fleet_section[start:end]
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
        result['ruined_available'] = ruined_megas[:20]  # Cap ruined list

        return result

    def get_ship_designs(self) -> dict:
        """Get the player's unique ship designs/templates with weapon and defense loadouts.

        Returns:
            Dict with:
              - designs: List of unique ship designs used by player with:
                  - design_id: The design template ID
                  - ship_class: Ship class (corvette/destroyer/cruiser/battleship etc)
                  - weapons: List of weapon component names
                  - defenses: List of armor/shield component names
                  - sample_ship_id: ID of a ship using this design
              - by_class: Dict mapping ship class to count of designs
              - count: Total unique designs
        """
        result = {
            'designs': [],
            'by_class': {},
            'count': 0,
        }

        player_id = self.get_player_empire_id()
        country_content = self._find_player_country_content(player_id)
        if not country_content:
            return result

        owned_fleet_ids = self._get_owned_fleet_ids(country_content)
        if not owned_fleet_ids:
            return result

        fleet_section = self._extract_section("fleet")
        ships_section = self._extract_section("ships")
        designs_section = self._extract_section("ship_design")
        if not fleet_section or not ships_section or not designs_section:
            return result

        owned_set = set(owned_fleet_ids)

        # Step 1: Build a mapping from design_id to ship_size and extract components from designs
        # The ship_design section has the full component loadout including utility slots (shields/armor)
        design_to_size: dict[str, str] = {}
        design_to_components: dict[str, dict] = {}  # design_id -> {weapons: [], defenses: []}

        for m in re.finditer(r'\n\t(\d+)=\n\t\{', designs_section):
            design_id = m.group(1)

            # Find the end of this design block
            design_start = m.start()
            brace_count = 0
            design_end = design_start
            started = False
            for i, char in enumerate(designs_section[design_start:design_start + 15000], design_start):
                if char == '{':
                    brace_count += 1
                    started = True
                elif char == '}':
                    brace_count -= 1
                    if started and brace_count == 0:
                        design_end = i + 1
                        break

            design_block = designs_section[design_start:design_end]

            # Extract ship_size
            size_m = re.search(r'\bship_size="([^"]+)"', design_block)
            if size_m:
                design_to_size[design_id] = size_m.group(1)

            # Extract all component templates from the design
            # Pattern: component={ slot="..." template="COMPONENT_NAME" }
            weapons = []
            defenses = []
            for comp_m in re.finditer(r'component\s*=\s*\{[^}]*slot="([^"]+)"[^}]*template="([^"]+)"', design_block):
                slot = comp_m.group(1)
                template = comp_m.group(2)
                # Categorize by slot type
                if 'UTILITY' in slot.upper():
                    # Utility slots contain shields, armor, reactors, etc.
                    if any(x in template.upper() for x in ['ARMOR', 'SHIELD', 'HULL', 'DEFLECTOR', 'CRYSTAL_ARMOR', 'DRAGON_ARMOR']):
                        if template not in defenses:
                            defenses.append(template)
                elif 'GUN' in slot.upper() or 'TORPEDO' in slot.upper() or 'MISSILE' in slot.upper() or 'HANGAR' in slot.upper() or 'WEAPON' in slot.upper():
                    # Weapon slots
                    if template not in weapons:
                        weapons.append(template)

            design_to_components[design_id] = {'weapons': weapons, 'defenses': defenses}

        # Step 2: Collect player's ship IDs from owned fleets
        player_ship_ids: set[str] = set()
        for match in re.finditer(r'\n\t(\d+)=\n\t\{', fleet_section):
            fleet_id = match.group(1)
            if fleet_id not in owned_set:
                continue

            # Get fleet block to extract ships
            start = match.start()
            brace_count = 0
            end = None
            for i, char in enumerate(fleet_section[start:], start):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end = i + 1
                        break
            if end is None:
                continue

            fleet_block = fleet_section[start:end]
            ships_block = self._extract_braced_block(fleet_block, "ships")
            if ships_block:
                open_brace = ships_block.find("{")
                close_brace = ships_block.rfind("}")
                if open_brace != -1 and close_brace > open_brace:
                    ship_ids = re.findall(r"\d+", ships_block[open_brace + 1 : close_brace])
                    player_ship_ids.update(ship_ids)

        if not player_ship_ids:
            return result

        # Step 3: Parse ships to get design_id and link to a sample ship
        # Track unique designs used by player (components come from design_to_components)
        design_info: dict[str, dict] = {}  # design_id -> {sample_ship_id}

        for m in re.finditer(r'\n\t(\d+)=\n\t\{', ships_section):
            ship_id = m.group(1)
            if ship_id not in player_ship_ids:
                continue

            # Get a chunk to find design ID
            ship_start = m.start()
            ship_block = ships_section[ship_start:ship_start + 3000]

            # Extract design ID from ship_design_implementation
            impl_m = re.search(r'\bship_design_implementation\s*=\s*\{[^}]*\bdesign\s*=\s*(\d+)', ship_block)
            if impl_m:
                design_id = impl_m.group(1)
            else:
                # Fallback to ship_design field
                design_m = re.search(r'\bship_design\s*=\s*(\d+)', ship_block)
                if design_m:
                    design_id = design_m.group(1)
                else:
                    continue

            # Record this design if we haven't seen it
            if design_id not in design_info:
                design_info[design_id] = {
                    'sample_ship_id': ship_id,
                }

        # Step 4: Build the result with ship class information
        by_class: dict[str, int] = {}
        designs_list = []

        for design_id, info in design_info.items():
            ship_class = design_to_size.get(design_id, "unknown")

            # Get components from the design template
            components = design_to_components.get(design_id, {'weapons': [], 'defenses': []})

            design_entry = {
                'design_id': design_id,
                'ship_class': ship_class,
                'weapons': components['weapons'],
                'defenses': components['defenses'],
                'sample_ship_id': info['sample_ship_id'],
            }
            designs_list.append(design_entry)

            # Count by class
            by_class[ship_class] = by_class.get(ship_class, 0) + 1

        # Sort by ship class for readability
        class_order = ['corvette', 'frigate', 'destroyer', 'cruiser', 'battlecruiser', 'battleship', 'titan', 'colossus', 'juggernaut']
        def class_sort_key(d):
            ship_class = d['ship_class'].lower()
            for i, c in enumerate(class_order):
                if c in ship_class:
                    return (i, ship_class)
            return (len(class_order), ship_class)

        designs_list.sort(key=class_sort_key)

        result['designs'] = designs_list
        result['by_class'] = by_class
        result['count'] = len(designs_list)

        return result
