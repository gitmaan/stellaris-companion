from __future__ import annotations

import re
import zipfile
from datetime import datetime
from pathlib import Path

class PlayerMixin:
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

    def _parse_simple_string_list_block(self, block: str, prefix: str | None = None) -> list[str]:
        """Parse a simple `{ "a" "b" }` or `{ a b }` block into a de-duped list."""
        if not block:
            return []

        open_brace = block.find('{')
        close_brace = block.rfind('}')
        if open_brace == -1 or close_brace == -1 or close_brace <= open_brace:
            return []

        inner = block[open_brace + 1 : close_brace]

        items = re.findall(r'"([^"]+)"', inner)
        if not items:
            if prefix:
                items = re.findall(rf'\b({re.escape(prefix)}[A-Za-z0-9_]+)\b', inner)
            else:
                items = re.findall(r'\b([A-Za-z0-9_]+)\b', inner)

        deduped: list[str] = []
        seen: set[str] = set()
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            deduped.append(item)

        return deduped

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

    def get_traditions(self) -> dict:
        """Extract picked traditions and summarize progress by tree.

        Returns:
            Dict with:
              - traditions: list[str]
              - by_tree: dict[str, {picked: list[str], adopted: bool, finished: bool}]
              - count: int
        """
        result = {
            "traditions": [],
            "by_tree": {},
            "count": 0,
        }

        player_id = self.get_player_empire_id()
        country_content = self._find_player_country_content(player_id)
        if not country_content:
            return result

        block = self._extract_braced_block(country_content, "traditions")
        traditions = self._parse_simple_string_list_block(block or "", prefix="tr_")

        by_tree: dict[str, dict] = {}
        for tradition_id in traditions:
            tree = "unknown"
            if tradition_id.startswith("tr_"):
                remainder = tradition_id[3:]
                parts = remainder.split("_", 1)
                if parts and parts[0]:
                    tree = parts[0]

            entry = by_tree.setdefault(tree, {"picked": [], "adopted": False, "finished": False})
            entry["picked"].append(tradition_id)
            if tradition_id.endswith("_adopt"):
                entry["adopted"] = True
            if tradition_id.endswith("_finish"):
                entry["finished"] = True

        result["traditions"] = traditions
        result["by_tree"] = by_tree
        result["count"] = len(traditions)
        return result

    def get_ascension_perks(self) -> dict:
        """Extract picked ascension perks.

        Returns:
            Dict with:
              - ascension_perks: list[str]
              - count: int
        """
        result = {
            "ascension_perks": [],
            "count": 0,
        }

        player_id = self.get_player_empire_id()
        country_content = self._find_player_country_content(player_id)
        if not country_content:
            return result

        block = self._extract_braced_block(country_content, "ascension_perks")
        perks = self._parse_simple_string_list_block(block or "", prefix="ap_")

        result["ascension_perks"] = perks
        result["count"] = len(perks)
        return result

    def get_naval_capacity(self) -> dict:
        """Get the player's naval capacity usage.

        Note: Stellaris does not store max naval capacity directly in saves.
        It's calculated dynamically from starbases, techs, civics, etc.
        We provide the used capacity and fleet size.

        Returns:
            Dict with:
              - used: Current naval capacity in use (from used_naval_capacity)
              - fleet_size: Total fleet size (ship count weighted by size)
              - starbase_capacity: Max starbases allowed
              - used_starbase_capacity: Current starbase count
        """
        result = {
            "used": 0,
            "fleet_size": 0,
            "starbase_capacity": None,
            "used_starbase_capacity": None,
        }

        player_id = self.get_player_empire_id()
        country_content = self._find_player_country_content(player_id)
        if not country_content:
            return result

        # Extract used_naval_capacity and fleet_size
        used_match = re.search(r'\bused_naval_capacity=([\d.]+)', country_content)
        fleet_match = re.search(r'\bfleet_size=(\d+)', country_content)
        starbase_cap_match = re.search(r'\bstarbase_capacity=(\d+)', country_content)
        used_starbase_match = re.search(r'\bused_starbase_capacity=(\d+)', country_content)

        if used_match:
            result["used"] = int(float(used_match.group(1)))
        if fleet_match:
            result["fleet_size"] = int(fleet_match.group(1))
        if starbase_cap_match:
            result["starbase_capacity"] = int(starbase_cap_match.group(1))
        if used_starbase_match:
            result["used_starbase_capacity"] = int(used_starbase_match.group(1))

        return result

    def get_relics(self) -> dict:
        """Extract owned relics and activation cooldown (best-effort).

        Returns:
            Dict with:
              - relics: list[str]
              - count: int
              - last_activated_relic: str|None
              - last_received_relic: str|None
              - activation_cooldown_days: int|None
        """
        result = {
            "relics": [],
            "count": 0,
            "last_activated_relic": None,
            "last_received_relic": None,
            "activation_cooldown_days": None,
        }

        player_id = self.get_player_empire_id()
        country_section = self._extract_section("country")
        if not country_section:
            return result

        entry_match = re.search(rf"\n\t{player_id}=\n\t\{{", country_section)
        if not entry_match:
            entry_match = re.search(rf"\n\t{player_id}\s*=\s*\{{", country_section)
        if not entry_match:
            return result

        start = entry_match.start() + 1
        brace_count = 0
        started = False
        end = None
        for i, ch in enumerate(country_section[start:], start):
            if ch == "{":
                brace_count += 1
                started = True
            elif ch == "}":
                brace_count -= 1
                if started and brace_count == 0:
                    end = i + 1
                    break
        if end is None:
            return result

        player_block = country_section[start:end]

        relics_block = self._extract_braced_block(player_block, "relics")
        relics = self._parse_simple_string_list_block(relics_block or "", prefix="r_")
        result["relics"] = relics
        result["count"] = len(relics)

        last_activated = re.search(r'\blast_activated_relic="([^"]+)"', player_block)
        if last_activated:
            result["last_activated_relic"] = last_activated.group(1)

        last_received = re.search(r'\blast_received_relic="([^"]+)"', player_block)
        if last_received:
            result["last_received_relic"] = last_received.group(1)

        cooldown = re.search(
            r'modifier="relic_activation_cooldown"[\s\S]{0,200}?\bdays=([-\d]+)',
            player_block,
        )
        if cooldown:
            try:
                result["activation_cooldown_days"] = int(cooldown.group(1))
            except ValueError:
                result["activation_cooldown_days"] = None

        return result
