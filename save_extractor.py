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

        # Find the country section (it's deep in the file, ~21MB in)
        country_match = re.search(r'^country=\s*\{', self.gamestate, re.MULTILINE)

        if country_match:
            # Get a large chunk from country section to find player data
            start = country_match.start()
            country_chunk = self.gamestate[start:start + 500000]  # 500k chars

            # Extract metrics - these appear in order for country 0
            metrics = {
                'military_power': r'military_power\s*=\s*([\d.]+)',
                'economy_power': r'economy_power\s*=\s*([\d.]+)',
                'tech_power': r'tech_power\s*=\s*([\d.]+)',
                'victory_rank': r'victory_rank\s*=\s*(\d+)',
                'fleet_size': r'fleet_size\s*=\s*(\d+)',
            }

            for key, pattern in metrics.items():
                match = re.search(pattern, country_chunk)
                if match:
                    value = match.group(1)
                    result[key] = float(value) if '.' in value else int(value)

            # Find fleets list
            fleets_match = re.search(r'fleets\s*=\s*\{([^}]+)\}', country_chunk)
            if fleets_match:
                fleet_ids = re.findall(r'\d+', fleets_match.group(1))
                result['fleet_count'] = len(fleet_ids)

            # Find controlled planets (all celestial bodies in territory)
            controlled_match = re.search(r'controlled_planets\s*=\s*\{([^}]+)\}', country_chunk)
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
        """Get all active wars.

        Returns:
            Dict with war information including:
            - wars: List of war names (used by get_situation for at_war check)
            - count: Number of wars found
            - active_war_ids: IDs of active wars if found
        """
        result = {'wars': [], 'count': 0}

        # Search for war data in gamestate
        # Wars are usually near "active_wars" or in a "war" section
        war_pattern = r'war\s*=\s*\{[^}]*name\s*=\s*"([^"]+)"'
        war_matches = re.findall(war_pattern, self.gamestate)

        if war_matches:
            result['count'] = len(war_matches)
            # Populate 'wars' list (used by get_situation for at_war detection)
            result['wars'] = war_matches[:10]  # First 10

        # Try to find detailed war section
        # Look for active wars involving player
        player_id = self.get_player_empire_id()

        # Search for war entries
        war_section_match = re.search(r'active_wars\s*=\s*\{([^}]+)\}', self.gamestate)
        if war_section_match:
            war_ids = re.findall(r'\d+', war_section_match.group(1))
            result['active_war_ids'] = war_ids

        return result

    def get_fleets(self) -> dict:
        """Get player's fleet information.

        Returns:
            Dict with fleet details
        """
        result = {'fleets': [], 'count': 0}

        player_id = self.get_player_empire_id()

        # Find fleets owned by player
        fleet_pattern = rf'owner\s*=\s*{player_id}[^}}]*name\s*=\s*"([^"]+)"'

        # Search in chunks to avoid regex issues with huge strings
        chunk_size = 1000000
        fleet_names = []

        for i in range(0, len(self.gamestate), chunk_size):
            chunk = self.gamestate[i:i + chunk_size + 10000]  # Overlap
            matches = re.findall(fleet_pattern, chunk)
            fleet_names.extend(matches)

        # Deduplicate
        fleet_names = list(set(fleet_names))

        result['count'] = len(fleet_names)
        result['fleet_names'] = fleet_names[:20]  # First 20

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
            Dict with completed technologies and current research
        """
        result = {
            'completed_technologies': [],
            'current_research': {},
            'tech_count': 0
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

        # Extract tech_status block
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
        tech_pattern = r'technology="([^"]+)"'
        technologies = re.findall(tech_pattern, tech_block)
        result['completed_technologies'] = technologies
        result['tech_count'] = len(technologies)

        # Categorize technologies
        physics_techs = [t for t in technologies if any(x in t for x in ['physics', 'laser', 'shield', 'sensor', 'power', 'ftl', 'hyper'])]
        society_techs = [t for t in technologies if any(x in t for x in ['society', 'genome', 'gene', 'xeno', 'psi', 'health', 'food', 'colonization'])]
        engineering_techs = [t for t in technologies if any(x in t for x in ['engineering', 'mining', 'ship', 'armor', 'weapon', 'thruster', 'starbase', 'missile', 'torpedo'])]

        result['by_category'] = {
            'physics_related': len(physics_techs),
            'society_related': len(society_techs),
            'engineering_related': len(engineering_techs)
        }

        # Look for current research projects
        # Search for active research queues
        current_physics = re.search(r'physics\s*=\s*\{[^}]*technology="([^"]+)"', player_chunk)
        current_society = re.search(r'society\s*=\s*\{[^}]*technology="([^"]+)"', player_chunk)
        current_engineering = re.search(r'engineering\s*=\s*\{[^}]*technology="([^"]+)"', player_chunk)

        if current_physics:
            result['current_research']['physics'] = current_physics.group(1)
        if current_society:
            result['current_research']['society'] = current_society.group(1)
        if current_engineering:
            result['current_research']['engineering'] = current_engineering.group(1)

        # Get sample of recent/notable techs
        result['sample_technologies'] = technologies[-20:] if len(technologies) > 20 else technologies

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
        player_chunk = self.gamestate[player_start:player_start + 200000]

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

        # Extract income section
        income_match = re.search(r'income=\s*\{', budget_block)
        if income_match:
            # Find country_base income (the base resources)
            base_match = re.search(r'country_base=\s*\{([^}]+)\}', budget_block)
            if base_match:
                base_block = base_match.group(1)
                for resource in ['energy', 'minerals', 'food', 'consumer_goods', 'alloys',
                                'physics_research', 'society_research', 'engineering_research',
                                'influence', 'unity']:
                    res_match = re.search(rf'{resource}=([\d.]+)', base_block)
                    if res_match:
                        result['stockpiles'][resource] = float(res_match.group(1))

        # Extract total income from various sources
        income_resources = {}
        expenses_resources = {}

        # Parse income section more thoroughly
        income_section_match = re.search(r'income=\s*\{(.+?)\}\s*expenses=', budget_block, re.DOTALL)
        if income_section_match:
            income_section = income_section_match.group(1)
            # Sum up resources from all income sources
            for resource in ['energy', 'minerals', 'food', 'consumer_goods', 'alloys',
                            'physics_research', 'society_research', 'engineering_research',
                            'influence', 'unity', 'volatile_motes', 'exotic_gases', 'rare_crystals']:
                matches = re.findall(rf'{resource}=([\d.]+)', income_section)
                if matches:
                    income_resources[resource] = sum(float(m) for m in matches)

        result['monthly_income'] = income_resources

        # Parse expenses section
        expenses_match = re.search(r'expenses=\s*\{(.+?)\}\s*(?:balance|$)', budget_block, re.DOTALL)
        if expenses_match:
            expenses_section = expenses_match.group(1)
            for resource in ['energy', 'minerals', 'food', 'consumer_goods', 'alloys',
                            'physics_research', 'society_research', 'engineering_research',
                            'influence', 'unity', 'volatile_motes', 'exotic_gases', 'rare_crystals']:
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
                              result['net_monthly'].get('engineering_research', 0))
        }

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

    def search(self, query: str, max_results: int = 5, context_chars: int = 1000) -> dict:
        """Search the full gamestate for specific text.

        Args:
            query: Text to search for
            max_results: Maximum number of results to return
            context_chars: Characters of context around each match

        Returns:
            Dict with search results
        """
        result = {
            'query': query,
            'matches': [],
            'total_found': 0
        }

        query_lower = query.lower()
        gamestate_lower = self.gamestate.lower()

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

            result['matches'].append({
                'position': pos,
                'context': context
            })

            start = pos + 1

        # Count total matches
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
                'fleet_count': player_clean.get('fleet_count'),
                'fleet_size': player_clean.get('fleet_size'),
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
                'starbase_count': starbases.get('starbase_count'),
                'starbases_by_level': starbases.get('starbases_by_level', {}),
                'starbases': starbases.get('starbases', []),
            },
            'leadership': {
                'leader_count': leaders.get('leader_count'),
                'leaders_by_class': leaders.get('leaders_by_class', {}),
                'leaders': leaders.get('leaders', [])[:15],  # Top 15 leaders
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

        # Check war status
        wars = self.get_wars()
        war_list = wars.get('wars', [])
        result['war_count'] = len(war_list)
        result['at_war'] = len(war_list) > 0

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
