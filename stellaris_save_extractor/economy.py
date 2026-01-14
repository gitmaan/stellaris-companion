from __future__ import annotations

import re
import zipfile
from datetime import datetime
from pathlib import Path

class EconomyMixin:
    """Domain methods extracted from the original SaveExtractor."""

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

