from __future__ import annotations

import logging
import re
import zipfile
from datetime import datetime
from pathlib import Path

# Rust bridge for fast Clausewitz parsing
try:
    from rust_bridge import extract_sections, iter_section_entries, ParserError
    RUST_BRIDGE_AVAILABLE = True
except ImportError:
    RUST_BRIDGE_AVAILABLE = False
    ParserError = Exception  # Fallback type for type hints

logger = logging.getLogger(__name__)


class LeadersMixin:
    """Domain methods extracted from the original SaveExtractor."""

    def get_leaders(self) -> dict:
        """Get the player's leader information.

        Uses Rust parser for fast extraction when available, falls back to regex.

        Returns:
            Dict with leader details including scientists, admirals, generals, governors
        """
        # Try Rust bridge first for faster parsing
        if RUST_BRIDGE_AVAILABLE:
            try:
                return self._get_leaders_rust()
            except ParserError as e:
                logger.warning(f"Rust parser failed for leaders: {e}, falling back to regex")
            except Exception as e:
                logger.warning(f"Unexpected error from Rust parser: {e}, falling back to regex")

        # Fallback: regex-based parsing
        return self._get_leaders_regex()

    def _get_leaders_rust(self) -> dict:
        """Get leaders using Rust parser.

        Note: Uses hybrid approach - Rust for main iteration, but extracts traits
        using regex because the Clausewitz format has duplicate keys for traits
        which the JSON-style Rust parser doesn't handle correctly.

        Returns:
            Dict with leader details
        """
        result = {
            'leaders': [],
            'count': 0,
            'by_class': {}
        }

        player_id = self.get_player_empire_id()
        leaders_found = []
        class_counts = {}

        # Get leader blocks from gamestate for traits extraction (Rust parser
        # only returns last trait because of duplicate keys)
        leader_blocks = self._get_leader_blocks_for_traits()

        # Iterate over leaders section using Rust parser
        for leader_id, leader_data in iter_section_entries(self.gamestate_path, "leaders"):
            if not isinstance(leader_data, dict):
                continue

            # Check if this leader belongs to the player
            country_id = leader_data.get("country")
            if country_id is None or int(country_id) != player_id:
                continue

            # Extract class
            leader_class = leader_data.get("class")
            if not leader_class:
                continue

            leader_info = {
                'id': str(leader_id),
                'class': leader_class,
            }

            # Extract name from the name block
            name = self._extract_leader_name_rust(leader_data)
            if name:
                leader_info['name'] = name

            # Extract level
            level = leader_data.get("level")
            if level is not None:
                leader_info['level'] = int(level)

            # Extract age
            age = leader_data.get("age")
            if age is not None:
                leader_info['age'] = int(age)

            # Extract traits using regex from raw blocks (Rust parser only keeps last value for duplicate keys)
            traits = self._extract_leader_traits_from_block(leader_blocks.get(str(leader_id), ""))
            if traits:
                leader_info['traits'] = traits

            # Extract experience
            experience = leader_data.get("experience")
            if experience is not None:
                leader_info['experience'] = float(experience)

            leaders_found.append(leader_info)

            # Count by class
            if leader_class not in class_counts:
                class_counts[leader_class] = 0
            class_counts[leader_class] += 1

        # Sort by leader ID to ensure consistent ordering
        leaders_found.sort(key=lambda x: int(x['id']))

        result['leaders'] = leaders_found
        result['count'] = len(leaders_found)
        result['by_class'] = class_counts

        return result

    def _get_leader_blocks_for_traits(self) -> dict[str, str]:
        """Extract raw leader blocks from gamestate for trait extraction.

        The Rust parser can't handle duplicate keys (traits="x" repeated multiple times),
        so we extract raw blocks and parse traits with regex.

        Returns:
            Dict mapping leader_id (str) to raw block text
        """
        blocks = {}

        # Find the leaders section
        leaders_match = re.search(r'^leaders=\s*\{', self.gamestate, re.MULTILINE)
        if not leaders_match:
            return blocks

        start = leaders_match.start()
        leaders_chunk = self.gamestate[start:start + 3000000]

        # Find each leader block
        leader_start_pattern = r'\n\t(\d+)=\s*\{(?:\s*\n|\s*$)'

        for match in re.finditer(leader_start_pattern, leaders_chunk):
            leader_id = match.group(1)
            block_start = match.start() + 1

            # Find the end of this block by counting braces
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

            blocks[leader_id] = leaders_chunk[block_start:block_end]

        return blocks

    def _extract_leader_traits_from_block(self, block: str) -> list[str]:
        """Extract all traits from a raw leader block using regex.

        Args:
            block: Raw text of leader block

        Returns:
            List of trait strings
        """
        if not block:
            return []
        return re.findall(r'traits="([^"]+)"', block)

    def _extract_leader_name_rust(self, leader_data: dict) -> str | None:
        """Extract leader name from Rust-parsed leader data.

        Handles various name formats:
        - name={ full_names={ key="XXX_CHR_Name" } }
        - name={ full_names={ key="%LEADER_2%" variables=[...] } }
        - NAME_* format for special characters

        Args:
            leader_data: Dict of parsed leader data

        Returns:
            Human-readable name or None
        """
        name_block = leader_data.get("name")
        if not isinstance(name_block, dict):
            return None

        # Names are under full_names
        full_names = name_block.get("full_names")
        if not isinstance(full_names, dict):
            return None

        key = full_names.get("key", "")

        # Check for direct _CHR_ pattern (e.g., "HUMAN1_CHR_Miriam")
        if "_CHR_" in key:
            return key.split("_CHR_")[-1]

        # Check for NAME_ pattern (special characters like NAME_Skrand_Sharpbeak)
        if key.startswith("NAME_"):
            # Remove NAME_ prefix and convert underscores to spaces
            return key[5:].replace("_", " ")

        # Check variables for the actual name (template format like %LEADER_2%)
        variables = full_names.get("variables", [])
        if isinstance(variables, list):
            # Look for the first name variable (usually key="1")
            for var in variables:
                if isinstance(var, dict):
                    var_key = var.get("key")
                    if var_key == "1":  # First name is usually key="1"
                        value = var.get("value", {})
                        if isinstance(value, dict):
                            val_key = value.get("key", "")
                            if "_CHR_" in val_key:
                                return val_key.split("_CHR_")[-1]

        return None

    def _get_leaders_regex(self) -> dict:
        """Get leaders using regex parsing (fallback method).

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
