from __future__ import annotations

import logging
from collections import Counter

from rust_bridge import ParserError, _get_active_session

logger = logging.getLogger(__name__)


class TechnologyMixin:
    """Domain methods extracted from the original SaveExtractor."""

    def get_technology(self) -> dict:
        """Get the player's technology research status.

        Requires active Rust session for parsed dict access.

        Returns:
            Dict with detailed technology tracking including:
            - completed_count: Number of researched technologies
            - researched_techs: List of completed tech names
            - in_progress: Current research for each category with progress details
            - research_speed: Monthly research income by category
            - available_techs: Technologies available for research by category

        Raises:
            ParserError: If no Rust session is active
        """
        return self._get_technology_rust()

    def _get_technology_rust(self) -> dict:
        """Get technology using Rust session.

        Uses get_duplicate_values for researched techs (handles duplicate keys)
        and parsed dict access for queues, alternatives, and budget.

        Returns:
            Dict with technology status

        Raises:
            ParserError: If no Rust session is active
        """
        session = _get_active_session()
        if not session:
            raise ParserError("Rust session required for get_technology")

        result = {
            "completed_count": 0,
            "researched_techs": [],
            "in_progress": {"physics": None, "society": None, "engineering": None},
            "research_speed": {"physics": 0, "society": 0, "engineering": 0},
            "available_techs": {"physics": [], "society": [], "engineering": []},
            "repeatables": {},
            "repeatables_total_levels": 0,
        }

        player_id = self.get_player_empire_id()

        # Use cached player country entry for fast lookup
        player_data = self._get_player_country_entry(player_id)

        if not player_data or not isinstance(player_data, dict):
            result["error"] = "Could not find player country"
            return result

        tech_status = player_data.get("tech_status")
        if not tech_status:
            result["error"] = "Could not find tech_status section"
            return result

        # Extract researched techs using get_duplicate_values (handles duplicate keys correctly)
        technologies = session.get_duplicate_values("country", str(player_id), "technology")
        result["researched_techs"] = sorted(list(set(technologies)))
        result["completed_count"] = len(result["researched_techs"])

        # Extract current research from queue structures (Rust handles these correctly)
        for category in ["physics", "society", "engineering"]:
            queue_key = f"{category}_queue"
            queue = tech_status.get(queue_key, [])
            if isinstance(queue, list) and len(queue) > 0:
                current = queue[0]  # First item in queue is current research
                if isinstance(current, dict):
                    tech_name = current.get("technology")
                    progress_str = current.get("progress", "0")
                    try:
                        progress = float(progress_str)
                    except (ValueError, TypeError):
                        progress = 0.0

                    result["in_progress"][category] = {
                        "tech": tech_name,
                        "progress": progress,
                        "cost": None,  # Would need tech definitions to get actual cost
                        "percent_complete": None,  # Can't calculate without cost
                        "leader_id": None,
                    }

        # Extract available techs from alternatives structure
        alternatives = tech_status.get("alternatives", {})
        if isinstance(alternatives, dict):
            for category in ["physics", "society", "engineering"]:
                alt_list = alternatives.get(category, [])
                if isinstance(alt_list, list):
                    result["available_techs"][category] = sorted(alt_list)

        # Extract research speed from budget
        budget = player_data.get("budget", {})
        current_month = budget.get("current_month", {})
        income = current_month.get("income", {})

        if isinstance(income, dict):
            # Sum up research income from all sources
            research_totals = {"physics": 0.0, "society": 0.0, "engineering": 0.0}

            for source, resources in income.items():
                if isinstance(resources, dict):
                    for resource, value_str in resources.items():
                        try:
                            value = float(value_str)
                        except (ValueError, TypeError):
                            continue

                        if resource == "physics_research":
                            research_totals["physics"] += value
                        elif resource == "society_research":
                            research_totals["society"] += value
                        elif resource == "engineering_research":
                            research_totals["engineering"] += value

            result["research_speed"] = {cat: round(val, 2) for cat, val in research_totals.items()}

        # Extract repeatable technologies and their levels
        repeatable_techs = [t for t in technologies if t.startswith("tech_repeatable_")]
        repeatable_counts = Counter(repeatable_techs)

        # Clean up the names and organize by type
        repeatables = {}
        for tech, level in repeatable_counts.items():
            clean_name = tech.replace("tech_repeatable_", "")
            repeatables[clean_name] = level

        result["repeatables"] = repeatables
        result["repeatables_total_levels"] = sum(repeatable_counts.values())

        return result
