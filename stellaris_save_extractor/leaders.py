from __future__ import annotations

import re
import zipfile
from datetime import datetime
from pathlib import Path

class LeadersMixin:
    """Domain methods extracted from the original SaveExtractor."""

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

        # Full list (no truncation); callers that need caps should slice.
        result['leaders'] = leaders_found
        result['count'] = len(leaders_found)
        result['by_class'] = class_counts

        return result
