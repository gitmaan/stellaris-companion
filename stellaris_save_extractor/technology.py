from __future__ import annotations

import logging

from stellaris_companion.rust_bridge import ParserError, _get_active_session

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
            - in_progress: Head of each research queue with progress details;
              ``special_project`` when that is a project, and ``queued_techs``
              for technologies waiting behind it
            - research_speed: Monthly research income by category
            - available_techs: Technologies available for research by category

        Raises:
            ParserError: If no Rust session is active
        """
        return self._get_technology_rust()

    def _get_technology_rust(self) -> dict:
        """Get technology using Rust session.

        Researched technologies and their levels are the direct children of the
        country's ``tech_status`` block; queues, alternatives and budget sit beside them.

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

        # Finished technologies only: the research queues below also hold
        # ``technology=`` keys, for technologies that are still being researched.
        researched_levels = self._get_researched_technology_levels(player_id)
        result["researched_techs"] = sorted(researched_levels)
        result["completed_count"] = len(result["researched_techs"])

        # The head of each queue is what the field is working on. It can be a
        # special project, with technologies waiting behind it.
        for category in ["physics", "society", "engineering"]:
            queue = tech_status.get(f"{category}_queue", [])
            items = (
                [item for item in queue if isinstance(item, dict)]
                if isinstance(queue, list)
                else []
            )
            if not items:
                continue
            current = items[0]
            try:
                progress = float(current.get("progress", "0"))
            except (ValueError, TypeError):
                progress = 0.0
            entry = {
                "tech": current.get("technology"),
                "progress": progress,
                "cost": None,  # Would need tech definitions to get actual cost
                "percent_complete": None,  # Can't calculate without cost
                "leader_id": None,
            }
            if not entry["tech"] and "special_project" in current:
                entry["special_project"] = True
            queued = [
                item["technology"]
                for item in items[1:]
                if isinstance(item.get("technology"), str) and item["technology"]
            ]
            if queued:
                entry["queued_techs"] = queued
            result["in_progress"][category] = entry

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

        # Repeatable technologies and the level each has reached
        repeatables = {
            tech.replace("tech_repeatable_", ""): level
            for tech, level in researched_levels.items()
            if tech.startswith("tech_repeatable_")
        }
        result["repeatables"] = repeatables
        result["repeatables_total_levels"] = sum(repeatables.values())

        return result
