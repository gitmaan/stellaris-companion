from __future__ import annotations

import logging

# Rust bridge for fast Clausewitz parsing (required - no fallback)
from stellaris_companion.rust_bridge import (
    ParserError,
    _get_active_session,
)
from stellaris_companion.stored_names import stored_name
from stellaris_save_extractor.save_values import repeated

logger = logging.getLogger(__name__)

# Envoys are stored as leaders in the save, but the game shows them in the
# diplomacy panel (assigned to the galactic community, federations, spy networks,
# improving/harming relations) — NOT in the Leaders screen. So the leader roster
# count excludes them and they are reported separately.
ENVOY_CLASS = "envoy"


def _partition_envoys(leaders: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split a leader list into (roster, envoys) by class."""
    roster = [leader for leader in leaders if leader.get("class") != ENVOY_CLASS]
    envoys = [leader for leader in leaders if leader.get("class") == ENVOY_CLASS]
    return roster, envoys


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
        """Read the player's leaders from the parsed ``leaders`` section.

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

        # Authoritative hired-leader roster. In 4.x the leaders section also holds
        # unrecruited recruitment-pool candidates tagged with the player's country,
        # so we filter to owned_leaders (matches the in-game Leaders screen). Falls
        # back to the legacy country scan when the field is absent (older saves).
        owned_leader_ids = self._get_player_owned_leader_ids()

        player_leaders_data = []
        for leader_id, leader_data in session.iter_section("leaders"):
            # P010: entry might be string "none" for deleted entries
            if not isinstance(leader_data, dict):
                continue

            # Check if this leader belongs to the player
            if owned_leader_ids is not None:
                if str(leader_id) not in owned_leader_ids:
                    continue
            else:
                country_id = leader_data.get("country")
                if country_id is None or int(country_id) != player_id:
                    continue

            # P011: Extract class using .get() with defaults
            leader_class = leader_data.get("class")
            if not leader_class:
                continue

            player_leaders_data.append((str(leader_id), leader_data, leader_class))

        leaders_found = []
        for leader_id, leader_data, leader_class in player_leaders_data:
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

            traits = [str(trait) for trait in repeated(leader_data.get("traits"))]
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

        # Envoys are diplomatic units shown separately from the Leaders screen, so
        # the roster count excludes them (matches the in-game count).
        roster, envoys = _partition_envoys(leaders_found)
        result["leaders"] = roster
        result["envoys"] = envoys
        result["count"] = len(roster)
        result["envoy_count"] = len(envoys)
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

        # The name as the installed game shows it; below are guesses from the key.
        shown = stored_name(full_names)
        if shown:
            return shown

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
