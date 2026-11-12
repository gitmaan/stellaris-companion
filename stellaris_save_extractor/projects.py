from __future__ import annotations

import logging

# Rust bridge for Clausewitz parsing (required for session mode)
from stellaris_companion.rust_bridge import ParserError, _get_active_session
from stellaris_save_extractor.save_values import repeated

logger = logging.getLogger(__name__)


class ProjectsMixin:
    """Extractors for special projects, event chains, and precursor progress."""

    # Known precursor chain identifiers
    PRECURSOR_CHAINS = {
        "yuht": "Yuhtaan (First Colonizers)",
        "first_league": "First League",
        "cybrex": "Cybrex (Ancient Machines)",
        "irassian": "Irassian Concordat",
        "vultaum": "Vultaum Star Assembly",
        "zroni": "Zroni (Psionic Precursors)",
    }

    # Notable event chains worth tracking
    NOTABLE_CHAINS = {
        "horizon_signal": "Horizon Signal (The Worm)",
        "ghost_signal": "Ghost Signal (Contingency warning)",
        "ai_crisis": "AI Crisis",
        "war_in_heaven": "War in Heaven",
        "prethoryn": "Prethoryn Scourge",
        "extradimensional": "Extradimensional Invaders",
        "gray": "Gray (L-Cluster)",
        "market_founding": "Galactic Market Founding",
        "wenkwort": "Wenkwort Artem",
        "shroud": "Shroud Events",
    }

    def get_special_projects(self) -> dict:
        """Get special projects, event chains, and precursor progress.

        Requires Rust session mode for extraction.

        Returns:
            Dict with:
              - active_projects: List of active special projects with days_left
              - active_count: Number of pending projects
              - soonest_completion: Days until next project completes
              - completed_chains: List of completed event chain names
              - notable_completed: Human-readable notable completions
              - precursor_progress: Dict of precursor chain status
        """
        session = _get_active_session()
        if not session:
            raise ParserError("Rust session required for get_special_projects")

        result = {
            "active_projects": [],
            "active_count": 0,
            "soonest_completion": None,
            "completed_chains": [],
            "notable_completed": [],
            "precursor_progress": {},
        }

        player_id = self.get_player_empire_id()

        # Use session.get_entry for O(1) lookup (P021)
        player_data = session.get_entry("country", str(player_id))

        if not player_data or not isinstance(player_data, dict):
            return result

        events = player_data.get("events")
        if not isinstance(events, dict):
            events = {}
        completed_chains = [str(chain) for chain in repeated(events.get("completed_event_chain"))]
        result["completed_chains"] = completed_chains

        # Identify notable completed chains
        notable = []
        for chain in completed_chains:
            chain_lower = chain.lower()
            for key, name in self.NOTABLE_CHAINS.items():
                if key in chain_lower:
                    notable.append(name)
                    break
        result["notable_completed"] = list(set(notable))

        active_projects = self._extract_active_projects_from_dict(events)
        result["active_projects"] = active_projects
        result["active_count"] = len(active_projects)

        if active_projects:
            days_list = [p["days_left"] for p in active_projects if p.get("days_left")]
            if days_list:
                result["soonest_completion"] = min(days_list)

        # Extract precursor progress from flags (Rust handles this well)
        # Pass completed chains to check for completed precursor homeworlds
        precursor_progress = self._extract_precursor_progress_from_flags(
            player_data.get("flags", {}), completed_chains
        )
        result["precursor_progress"] = precursor_progress

        return result

    def _extract_precursor_progress_from_flags(
        self, flags: dict, completed_chains: list[str]
    ) -> dict:
        """Extract precursor chain progress from country flags.

        Args:
            flags: Dict of country flags from Rust parser
            completed_chains: List of completed event chain names (for detecting completed precursors)

        Returns:
            Dict of precursor progress by precursor key
        """
        progress = {}

        for precursor_key, precursor_name in self.PRECURSOR_CHAINS.items():
            precursor_data = self._check_precursor_from_flags(
                flags, precursor_key, completed_chains
            )
            if precursor_data["found"]:
                progress[precursor_key] = {"name": precursor_name, **precursor_data}

        return progress

    def _check_precursor_from_flags(
        self, flags: dict, precursor: str, completed_chains: list[str]
    ) -> dict:
        """Check progress on a specific precursor chain using flags dict.

        Args:
            flags: Dict of country flags from Rust parser
            precursor: Precursor chain key (e.g., 'yuht', 'cybrex')
            completed_chains: List of completed event chain names

        Returns:
            Dict with precursor progress info
        """
        result = {
            "found": False,
            "stage": "not_started",
            "homeworld_found": False,
            "artifacts": 0,
        }

        # Check for intro flag (chain started)
        intro_key = f"{precursor}_intro"
        if intro_key in flags:
            result["found"] = True
            result["stage"] = "started"

        # Check for various stage markers
        stage_keys = [
            (f"{precursor}_world_found", "homeworld_found"),
            (f"{precursor}_homeworld", "homeworld_found"),
            (f"{precursor}_system", "system_located"),
        ]

        for flag_key, stage in stage_keys:
            if flag_key in flags:
                result["found"] = True
                result["stage"] = stage
                if "homeworld" in stage or "world" in stage:
                    result["homeworld_found"] = True

        # Count artifact-related entries (numbered stages like yuht_2, yuht_6)
        artifact_count = 0
        for flag_key in flags:
            # Match pattern: precursor_N where N is a digit
            if flag_key.startswith(f"{precursor}_") and flag_key[len(precursor) + 1 :].isdigit():
                artifact_count += 1

        if artifact_count > 0:
            result["found"] = True
            result["artifacts"] = artifact_count
            if result["stage"] == "not_started":
                result["stage"] = "collecting_artifacts"

        # Check for completed precursor homeworld chain
        # Look for chains like "yuht_homeworld_chain" in completed chains
        for chain in completed_chains:
            chain_lower = chain.lower()
            if precursor in chain_lower and "homeworld" in chain_lower:
                result["found"] = True
                result["stage"] = "completed"
                result["homeworld_found"] = True
                break

        return result

    def _extract_active_projects_from_dict(self, events: dict) -> list[dict]:
        """Extract active special projects from parsed events dict (fast path).

        Args:
            events: Parsed events dict from country entry

        Returns:
            List of active project dicts with id, days_left, debris_id
        """
        projects = []

        special_project = events.get("special_project")
        if not special_project:
            return projects

        # Handle single project (dict) or multiple projects (list)
        project_list = [special_project] if isinstance(special_project, dict) else special_project
        if not isinstance(project_list, list):
            return projects

        for sp in project_list:
            if not isinstance(sp, dict):
                continue

            project = {}

            # Extract project ID
            proj_id = sp.get("id")
            if proj_id is not None:
                try:
                    project["id"] = int(proj_id)
                except (ValueError, TypeError):
                    pass

            # Extract days left
            days_left = sp.get("days_left")
            if days_left is not None:
                try:
                    project["days_left"] = int(days_left)
                except (ValueError, TypeError):
                    pass

            # Extract debris reference
            debris = sp.get("debris")
            if debris is not None:
                try:
                    project["debris_id"] = int(debris)
                except (ValueError, TypeError):
                    pass

            if project:
                projects.append(project)

        return projects
