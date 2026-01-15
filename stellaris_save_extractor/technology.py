from __future__ import annotations

import re
import zipfile
from datetime import datetime
from pathlib import Path

class TechnologyMixin:
    """Domain methods extracted from the original SaveExtractor."""

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
            },
            'repeatables': {},
            'repeatables_total_levels': 0,
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

        # Extract repeatable technologies and their levels
        # Repeatables appear as: technology="tech_repeatable_X" multiple times
        # The count of occurrences = the level
        from collections import Counter
        repeatable_techs = [t for t in technologies if t.startswith('tech_repeatable_')]
        repeatable_counts = Counter(repeatable_techs)

        # Clean up the names and organize by type
        repeatables = {}
        for tech, level in repeatable_counts.items():
            # Remove tech_repeatable_ prefix for cleaner names
            clean_name = tech.replace('tech_repeatable_', '')
            repeatables[clean_name] = level

        result['repeatables'] = repeatables
        result['repeatables_total_levels'] = sum(repeatable_counts.values())

        return result

