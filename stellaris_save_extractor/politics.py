from __future__ import annotations

import contextlib
import logging

# Rust bridge for Clausewitz parsing (required for session mode)
from stellaris_companion.rust_bridge import ParserError, _get_active_session

logger = logging.getLogger(__name__)


class PoliticsMixin:
    """Internal politics extractors (factions, elections, agendas, etc.)."""

    def get_factions(self, limit: int = 10) -> dict:
        """Get a compact summary of the player's political factions.

        Requires Rust session mode for extraction.

        Notes:
        - Returns an empty list for gestalt empires.
        - Does not return raw pop IDs (members are summarized as a count).
        """
        session = _get_active_session()
        if not session:
            raise ParserError("Rust session required for get_factions")

        identity = self.get_empire_identity()
        is_gestalt = bool(identity.get("is_gestalt", False))

        result = {
            "is_gestalt": is_gestalt,
            "factions": [],
            "count": 0,
        }

        if is_gestalt:
            return result

        player_id = self.get_player_empire_id()
        factions: list[dict] = []

        # P031: Use session.iter_section() directly
        for faction_id, faction_data in session.iter_section("pop_factions"):
            # P010: Entry might be string "none" - always check isinstance
            if not isinstance(faction_data, dict):
                continue

            # P011: Use .get() with defaults
            # Check country - only include player's factions
            country = faction_data.get("country")
            if country is None:
                continue
            try:
                if int(country) != player_id:
                    continue
            except (ValueError, TypeError):
                continue

            # Extract faction type
            faction_type = faction_data.get("type", "unknown")

            name = self.resolve_name(faction_data.get("name")).display

            # Extract support values - P012: fields can be str, int, float
            support_percent = 0.0
            support_power = 0.0
            approval = 0.0

            sp = faction_data.get("support_percent")
            if sp is not None:
                with contextlib.suppress(ValueError, TypeError):
                    support_percent = float(sp)

            spow = faction_data.get("support_power")
            if spow is not None:
                with contextlib.suppress(ValueError, TypeError):
                    support_power = float(spow)

            appr = faction_data.get("faction_approval")
            if appr is not None:
                with contextlib.suppress(ValueError, TypeError):
                    approval = float(appr)

            # Count members
            members = faction_data.get("members", [])
            members_count = len(members) if isinstance(members, list) else 0

            factions.append(
                {
                    "id": str(faction_id),  # P013: Entry IDs are strings
                    "country_id": player_id,
                    "type": faction_type,
                    "name": name,
                    "support_percent": support_percent,
                    "support_power": support_power,
                    "approval": approval,
                    "members_count": members_count,
                }
            )

        # Sort by support percent descending
        factions.sort(key=lambda f: f.get("support_percent", 0.0), reverse=True)

        result["count"] = len(factions)
        result["factions"] = factions[: max(0, min(int(limit), 25))]
        return result
