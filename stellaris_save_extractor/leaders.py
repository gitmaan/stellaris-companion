from __future__ import annotations

import logging

# Rust bridge for fast Clausewitz parsing (required - no fallback)
from rust_bridge import (
    ParserError,
    _get_active_session,
)

logger = logging.getLogger(__name__)


class LeadersMixin:
    """Domain methods extracted from the original SaveExtractor."""

    def get_leaders(self) -> dict:
        """Get the player's leader information.

        Requires Rust session mode for extraction.

        Returns:
            Dict with leader details including scientists, admirals, generals, governors

        Raises:
            ParserError: If no Rust session is active
        """
        return self._get_leaders_rust()

    def _get_leaders_rust(self) -> dict:
        """Rust-optimized leader extraction using session methods.

        Uses iter_section for leader iteration and batch_ops for traits.
        No self.gamestate access needed - all data from Rust session.

        Note: Uses two-phase approach because iter_section and get_duplicate_values
        cannot be interleaved (both use the same stdin/stdout pipe). Phase 2 uses
        batch_ops to fetch all traits in a single IPC call (P025).

        Returns:
            Dict with leader details

        Raises:
            ParserError: If no Rust session is active
        """
        session = _get_active_session()
        if not session:
            raise ParserError("Rust session required for get_leaders()")

        result = {"leaders": [], "count": 0, "by_class": {}}

        player_id = self.get_player_empire_id()
        class_counts = {}

        # Phase 1: Iterate and collect player leader data
        # (can't call get_duplicate_values during iter_section - same pipe)
        player_leaders_data = []
        for leader_id, leader_data in session.iter_section("leaders"):
            # P010: entry might be string "none" for deleted entries
            if not isinstance(leader_data, dict):
                continue

            # Check if this leader belongs to the player
            country_id = leader_data.get("country")
            if country_id is None or int(country_id) != player_id:
                continue

            # P011: Extract class using .get() with defaults
            leader_class = leader_data.get("class")
            if not leader_class:
                continue

            # Store leader data for phase 2
            player_leaders_data.append((str(leader_id), leader_data, leader_class))

        # Phase 2: Batch fetch all traits in one IPC call (P025: use batch_ops)
        # This avoids N round-trips and leverages section offset caching in Rust
        trait_ops = [
            {
                "op": "get_duplicate_values",
                "section": "leaders",
                "key": lid,
                "field": "traits",
            }
            for lid, _, _ in player_leaders_data
        ]
        trait_results = session.batch_ops(trait_ops) if trait_ops else []

        # Phase 3: Build leader info with traits
        leaders_found = []
        for i, (leader_id, leader_data, leader_class) in enumerate(player_leaders_data):
            leader_info = {
                "id": leader_id,
                "class": leader_class,
            }

            # Extract name from the name block
            name = self._extract_leader_name_rust(leader_data)
            if name:
                leader_info["name"] = name

            # P012: Extract level, handle type variations
            level = leader_data.get("level")
            if level is not None:
                leader_info["level"] = int(level)

            # Extract age
            age = leader_data.get("age")
            if age is not None:
                leader_info["age"] = int(age)

            # Get traits from batch result
            traits = (
                trait_results[i].get("values", []) if i < len(trait_results) else []
            )
            if traits:
                leader_info["traits"] = traits

            # Extract experience
            experience = leader_data.get("experience")
            if experience is not None:
                leader_info["experience"] = float(experience)

            # Extract date fields for history diffing (hire/death events)
            # death_date: When leader died (null for living leaders)
            death_date = leader_data.get("death_date")
            if death_date:
                leader_info["death_date"] = death_date

            # date_added: When leader was added to empire roster
            date_added = leader_data.get("date_added")
            if date_added:
                leader_info["date_added"] = date_added

            # recruitment_date: When leader was recruited
            # May be stored as recruitment_date, pre_ruler_date (for rulers), or date
            recruitment_date = leader_data.get("recruitment_date")
            if not recruitment_date:
                recruitment_date = leader_data.get("pre_ruler_date")
            if not recruitment_date:
                recruitment_date = leader_data.get("date")
            if recruitment_date:
                leader_info["recruitment_date"] = recruitment_date

            leaders_found.append(leader_info)

            # Count by class
            if leader_class not in class_counts:
                class_counts[leader_class] = 0
            class_counts[leader_class] += 1

        # Sort by leader ID to ensure consistent ordering
        leaders_found.sort(key=lambda x: int(x["id"]))

        result["leaders"] = leaders_found
        result["count"] = len(leaders_found)
        result["by_class"] = class_counts

        return result

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
