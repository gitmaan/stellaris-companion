from __future__ import annotations

import contextlib
import logging

# Rust bridge for Clausewitz parsing (required for session mode)
from stellaris_companion.rust_bridge import ParserError, _get_active_session

from .game_vocabulary import (
    CRISIS_COUNTRY_TYPES,
    CRISIS_FLAGS,
    KHAN_COUNTRY_TYPE,
    KHAN_DEAD_FLAG,
    KHAN_RISEN_FLAG,
    LGATE_OPENED_FLAG,
    MARAUDER_COUNTRY_TYPES,
)

logger = logging.getLogger(__name__)


class EndgameMixin:
    """Extractors for endgame content: Crisis, L-Gates, Become the Crisis."""

    def get_crisis_status(self) -> dict:
        """Get the end-game crisis in progress, and the crises already beaten.

        Returns:
            Dict with:
              - crisis_active: Whether a crisis is in progress
              - crisis_type: The crisis (prethoryn, contingency, unbidden, cetana, ...)
              - crisis_types_detected: Every crisis in progress
              - crisis_countries: Crisis faction country IDs
              - crises_defeated: Crises the galaxy has already beaten
              - player_crisis_kills: Crisis ships and armies the player has killed
        """
        return self._get_crisis_status_rust()

    def _get_crisis_status_rust(self) -> dict:
        """Read the crisis from crisis country types and the game's crisis flags."""
        if not _get_active_session():
            raise ParserError("Rust session required for get_crisis_status")

        flags = self._get_global_flags()
        crisis_countries = []
        active = set()
        for country_id, country_data in self._get_countries_cached().items():
            crisis_name = CRISIS_COUNTRY_TYPES.get(
                country_data.get("country_type") or country_data.get("type")
            )
            if crisis_name:
                crisis_countries.append({"country_id": int(country_id), "type": crisis_name})
                active.add(crisis_name)

        defeated = []
        for crisis_name, (arrived, running, beaten) in CRISIS_FLAGS.items():
            if beaten in flags:
                defeated.append(crisis_name)
                # Leftover fleets of a beaten crisis are not a crisis in progress.
                active.discard(crisis_name)
            elif arrived in flags or (running and running in flags):
                active.add(crisis_name)
        crisis_countries = [c for c in crisis_countries if c["type"] in active]

        result = {
            "crisis_active": bool(active),
            "crisis_type": next(
                (name for name in ("prethoryn", "contingency", "unbidden") if name in active),
                min(active) if active else None,
            ),
            "crisis_types_detected": sorted(active),
            "crisis_countries": crisis_countries,
            "crises_defeated": defeated,
            "player_crisis_kills": 0,
        }

        player_data = self._get_player_country_entry(self.get_player_empire_id())
        if isinstance(player_data, dict) and player_data.get("crisis_kills") is not None:
            with contextlib.suppress(ValueError, TypeError):
                result["player_crisis_kills"] = int(player_data["crisis_kills"])

        return result

    def get_lgate_status(self) -> dict:
        """Get L-Gate and L-Cluster status.

        Tracks L-Gate insights collected and whether the L-Cluster has been opened.

        Requires Rust session mode for extraction.

        Returns:
            Dict with:
              - lgate_enabled: Whether L-Gates exist in this galaxy
              - insights_collected: Number of L-Gate insights (from tech_repeatable_lcluster_clue)
              - insights_required: Usually 7 to open
              - lgate_opened: Whether L-Cluster has been accessed
              - player_activation_progress: Tech progress toward activation (0-100)
        """
        session = _get_active_session()
        if not session:
            raise ParserError("Rust session required for get_lgate_status")

        result = {
            "lgate_enabled": False,
            "insights_collected": 0,
            "insights_required": 7,  # Standard requirement
            "lgate_opened": False,
            "player_activation_progress": 0,
        }

        # Check if L-Gates are enabled using contains_kv (1.8x faster than contains_tokens)
        # contains_kv traverses the parsed tree instead of scanning raw bytes
        lgate_kv = session.contains_kv([("lgate_enabled", "yes"), ("lgate_enabled", "no")])
        matches = lgate_kv.get("matches", {})
        if matches.get("lgate_enabled=yes"):
            result["lgate_enabled"] = True
        elif matches.get("lgate_enabled=no"):
            result["lgate_enabled"] = False
            return result  # No point checking further

        # Get player's L-Gate insights from cached player country entry
        player_id = self.get_player_empire_id()
        country_data = self._get_player_country_entry(player_id)

        # Insights are levels of a repeatable technology, stored with the other
        # researched technologies as technology/level pairs.
        result["insights_collected"] = self._get_researched_technology_levels(player_id).get(
            "tech_repeatable_lcluster_clue", 0
        )

        if isinstance(country_data, dict):
            tech_status = country_data.get("tech_status", {})
            if isinstance(tech_status, dict):
                # Check for activation tech progress in tech_status.potential block
                potential = tech_status.get("potential", {})
                if isinstance(potential, dict):
                    activation_progress = potential.get("tech_lgate_activation")
                    if activation_progress is not None:
                        with contextlib.suppress(ValueError, TypeError):
                            result["player_activation_progress"] = int(activation_progress)

        result["lgate_opened"] = LGATE_OPENED_FLAG in self._get_global_flags()

        return result

    def get_menace(self) -> dict:
        """Get Become the Crisis status for the player.

        Tracks menace level and crisis ascension progress if player has
        the ap_become_the_crisis ascension perk.

        Requires Rust session mode for extraction.

        Returns:
            Dict with:
              - has_crisis_perk: Whether player has Become the Crisis perk
              - menace_level: Current menace accumulated
              - crisis_level: Crisis ascension tier (0-5)
        """
        session = _get_active_session()
        if not session:
            raise ParserError("Rust session required for get_menace")

        result = {
            "has_crisis_perk": False,
            "menace_level": 0,
            "crisis_level": 0,
        }

        player_id = self.get_player_empire_id()
        country_data = self._get_player_country_entry(player_id)

        if not isinstance(country_data, dict):
            return result

        # Check for Become the Crisis ascension perk
        ascension_perks = country_data.get("ascension_perks", [])
        if isinstance(ascension_perks, list):
            if "ap_become_the_crisis" in ascension_perks:
                result["has_crisis_perk"] = True
        elif isinstance(ascension_perks, str):
            # Single perk case
            if ascension_perks == "ap_become_the_crisis":
                result["has_crisis_perk"] = True

        # If they have the perk, look for menace tracking
        if result["has_crisis_perk"]:
            # Menace is stored in the country block
            menace = country_data.get("menace")
            if menace is not None:
                with contextlib.suppress(ValueError, TypeError):
                    result["menace_level"] = int(menace)

            # Crisis level/tier
            crisis_level = country_data.get("crisis_level")
            if crisis_level is not None:
                with contextlib.suppress(ValueError, TypeError):
                    result["crisis_level"] = int(crisis_level)

        return result

    def get_great_khan(self) -> dict:
        """Get Great Khan / Marauder status.

        The Great Khan is a mid-game crisis where marauder clans unify under
        a single leader and begin conquering the galaxy.

        Requires Rust session mode for extraction.

        Returns:
            Dict with:
              - marauders_present: Whether marauder empires exist
              - marauder_count: Number of marauder factions
              - khan_risen: Whether the Great Khan has spawned
              - khan_status: Current state (active, defeated, etc.)
              - khan_country_id: Country ID of the Khan's empire if active
        """
        return self._get_great_khan_rust()

    def _get_great_khan_rust(self) -> dict:
        """Read the Great Khan's state from marauder country types and the Khan's flags."""
        if not _get_active_session():
            raise ParserError("Rust session required for get_great_khan")

        flags = self._get_global_flags()
        marauder_count = 0
        horde_id = None
        for country_id, country_data in self._get_countries_cached().items():
            ctype = country_data.get("country_type") or country_data.get("type")
            if ctype in MARAUDER_COUNTRY_TYPES:
                marauder_count += 1
            elif ctype == KHAN_COUNTRY_TYPE:
                horde_id = int(country_id)

        dead = KHAN_DEAD_FLAG in flags
        risen = dead or KHAN_RISEN_FLAG in flags
        result = {
            "marauders_present": marauder_count > 0 or (risen and horde_id is not None),
            "marauder_count": marauder_count,
            "khan_risen": risen,
            "khan_status": "defeated" if dead else ("active" if risen else None),
            "khan_country_id": None,
            "khan_empire_name": None,
        }
        if risen and not dead and horde_id is not None:
            result["khan_country_id"] = horde_id
            result["khan_empire_name"] = self._get_country_names_map().get(
                horde_id, f"Khan Empire {horde_id}"
            )
        return result
