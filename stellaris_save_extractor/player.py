from __future__ import annotations

import contextlib
import logging
import re

# Rust bridge for Clausewitz parsing (required for session mode)
from stellaris_companion.rust_bridge import ParserError, _get_active_session

logger = logging.getLogger(__name__)


class PlayerMixin:
    """Domain methods extracted from the original SaveExtractor."""

    def _extract_braced_block(self, content: str, key: str) -> str | None:
        """Extract the full `key={...}` block from a larger text chunk."""
        match = re.search(rf"\b{re.escape(key)}\s*=\s*\{{", content)
        if not match:
            return None

        start = match.start()
        brace_count = 0
        started = False

        for i, char in enumerate(content[start:], start):
            if char == "{":
                brace_count += 1
                started = True
            elif char == "}":
                brace_count -= 1
                if started and brace_count == 0:
                    return content[start : i + 1]

        return None

    def _parse_simple_string_list_block(self, block: str, prefix: str | None = None) -> list[str]:
        """Parse a simple `{ "a" "b" }` or `{ a b }` block into a de-duped list."""
        if not block:
            return []

        open_brace = block.find("{")
        close_brace = block.rfind("}")
        if open_brace == -1 or close_brace == -1 or close_brace <= open_brace:
            return []

        inner = block[open_brace + 1 : close_brace]

        items = re.findall(r'"([^"]+)"', inner)
        if not items:
            if prefix:
                items = re.findall(rf"\b({re.escape(prefix)}[A-Za-z0-9_]+)\b", inner)
            else:
                items = re.findall(r"\b([A-Za-z0-9_]+)\b", inner)

        deduped: list[str] = []
        seen: set[str] = set()
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            deduped.append(item)

        return deduped

    def get_player_empire_id(self) -> int:
        """Get the player's country ID.

        Requires Rust session mode to be active.

        Returns:
            Player country ID (usually 0)

        Raises:
            ParserError: If no Rust session is active
        """
        session = _get_active_session()
        if not session:
            raise ParserError("Rust session required - use 'with session(save_path):' context")

        data = session.extract_sections(["player"])
        player_list = data.get("player", [])
        if player_list and isinstance(player_list, list) and len(player_list) > 0:
            country_id = player_list[0].get("country", "0")
            return int(country_id)
        return 0

    def get_player_status(self) -> dict:
        """Get the player's current empire status with clear, unambiguous metrics.

        Requires Rust session mode to be active.

        Returns:
            Dict with empire info, military, economy, and territory data.
            All field names are self-documenting to prevent LLM misinterpretation.

        Note:
            Results are cached per-instance since player status is expensive to compute
            and doesn't change within a single save file analysis.

        Raises:
            ParserError: If no Rust session is active
        """
        # Return cached result if available (expensive computation)
        if self._player_status_cache is not None:
            return self._player_status_cache

        # Rust session required
        session = _get_active_session()
        if not session:
            raise ParserError("Rust session required - use 'with session(save_path):' context")

        result = self._get_player_status_rust(session)

        # Cache the result for subsequent calls
        self._player_status_cache = result
        return result

    def _get_player_status_rust(self, session) -> dict:
        """Rust-optimized player status extraction using get_entry.

        Uses get_entry for fast single-entry lookup instead of scanning
        the entire country section with regex.
        """
        player_id = self.get_player_empire_id()

        result = {
            "player_id": player_id,
            "empire_name": self.get_metadata().get("name", "Unknown"),
            "date": self.get_metadata().get("date", "Unknown"),
        }

        # Get player country using cached method (0.004s vs 0.45s with regex)
        player_country = self._get_player_country_entry(player_id)

        if player_country and isinstance(player_country, dict):
            # Extract metrics directly from parsed dict
            metrics = [
                "military_power",
                "economy_power",
                "tech_power",
                "victory_rank",
                "fleet_size",
            ]
            for key in metrics:
                value = player_country.get(key)
                if value is not None:
                    # Values come as strings from jomini, convert to appropriate type
                    with contextlib.suppress(ValueError, TypeError):
                        result[key] = float(value) if "." in str(value) else int(value)

            # Get OWNED fleets from fleets_manager
            fleets_mgr = player_country.get("fleets_manager", {})
            owned_fleets_data = (
                fleets_mgr.get("owned_fleets", []) if isinstance(fleets_mgr, dict) else []
            )
            owned_fleet_ids = []
            for entry in owned_fleets_data:
                if isinstance(entry, dict):
                    fleet_id = entry.get("fleet")
                    if fleet_id is not None:
                        owned_fleet_ids.append(str(fleet_id))

            owned_set = set(owned_fleet_ids)

            if owned_fleet_ids:
                # Analyze the owned fleets (already uses Rust get_entries)
                fleet_analysis = self._analyze_player_fleets(owned_fleet_ids)
                result["military_fleet_count"] = fleet_analysis["military_fleet_count"]
                result["military_ships"] = fleet_analysis["military_ships"]
                # Keep fleet_count for backwards compatibility
                result["fleet_count"] = fleet_analysis["military_fleet_count"]

                # Get accurate starbase count from starbase_mgr
                starbase_info = self._count_player_starbases(owned_set)
                result["starbase_count"] = starbase_info["total_upgraded"]
                result["outpost_count"] = starbase_info["outposts"]
                result["starbases"] = starbase_info

            # Get controlled planets directly from parsed dict
            controlled_planets = player_country.get("controlled_planets", [])
            if isinstance(controlled_planets, list):
                result["celestial_bodies_in_territory"] = len(controlled_planets)

        # Get colonized planets data (already uses Rust when session active)
        planets_data = self.get_planets()
        colonies = planets_data.get("planets", [])
        total_pops = sum(p.get("population", 0) for p in colonies)

        # Separate habitats from planets (different pop capacities)
        habitats = [c for c in colonies if c.get("type", "").startswith("habitat")]
        regular_planets = [c for c in colonies if not c.get("type", "").startswith("habitat")]

        habitat_pops = sum(p.get("population", 0) for p in habitats)
        planet_pops = sum(p.get("population", 0) for p in regular_planets)

        result["colonies"] = {
            "total_count": len(colonies),
            "total_population": total_pops,
            "avg_pops_per_colony": (round(total_pops / len(colonies), 1) if colonies else 0),
            "_note": "These are colonized worlds with population, not all celestial bodies",
            # Breakdown by type for more accurate analysis
            "habitats": {
                "count": len(habitats),
                "population": habitat_pops,
                "avg_pops": round(habitat_pops / len(habitats), 1) if habitats else 0,
            },
            "planets": {
                "count": len(regular_planets),
                "population": planet_pops,
                "avg_pops": (
                    round(planet_pops / len(regular_planets), 1) if regular_planets else 0
                ),
            },
        }

        return result

    def get_empire_identity(self) -> dict:
        """Extract static empire identity for personality generation.

        This extracts ethics, government, civics, and species info from the
        player's country block. This data comes from empire creation and
        only changes via government reform or ethics shift events.

        Requires Rust session mode to be active.

        Returns:
            Dictionary with ethics, government, civics, species, and gestalt flags

        Raises:
            ParserError: If no Rust session is active
        """
        result = {
            "ethics": [],
            "government": None,
            "civics": [],
            "authority": None,
            "species_class": None,
            "species_name": None,
            "is_gestalt": False,
            "is_machine": False,
            "is_hive_mind": False,
            "empire_name": self.get_metadata().get("name", "Unknown"),
        }

        # Rust session required
        player_id = self.get_player_empire_id()
        country = self._get_player_country_entry(player_id)
        if not country or not isinstance(country, dict):
            return result

        # Extract ethics
        ethos = country.get("ethos", {})
        if isinstance(ethos, dict):
            ethic = ethos.get("ethic", [])
            if isinstance(ethic, str):
                ethic = [ethic]
            result["ethics"] = [e.replace("ethic_", "") for e in ethic if isinstance(e, str)]

        # Extract government info
        gov = country.get("government", {})
        if isinstance(gov, dict):
            gov_type = gov.get("type", "")
            if gov_type:
                result["government"] = gov_type.replace("gov_", "")

            authority = gov.get("authority", "")
            if authority:
                result["authority"] = authority.replace("auth_", "")

            civics = gov.get("civics", [])
            if isinstance(civics, list):
                result["civics"] = [c.replace("civic_", "") for c in civics if isinstance(c, str)]

        # Check for gestalt
        if "gestalt_consciousness" in result["ethics"]:
            result["is_gestalt"] = True
        if result["authority"] == "machine_intelligence":
            result["is_gestalt"] = True
            result["is_machine"] = True
        elif result["authority"] == "hive_mind":
            result["is_gestalt"] = True
            result["is_hive_mind"] = True

        # Extract founder species
        founder_ref = country.get("founder_species_ref")
        if founder_ref:
            species_names = self._get_species_names()
            result["species_name"] = species_names.get(str(founder_ref))

        return result

    def get_traditions(self) -> dict:
        """Extract picked traditions and summarize progress by tree.

        Requires Rust session mode to be active.

        Returns:
            Dict with:
              - traditions: list[str]
              - by_tree: dict[str, {picked: list[str], adopted: bool, finished: bool}]
              - count: int

        Raises:
            ParserError: If no Rust session is active
        """
        result = {
            "traditions": [],
            "by_tree": {},
            "count": 0,
        }

        # Rust session required (get_player_empire_id raises if no session)
        player_id = self.get_player_empire_id()
        country = self._get_player_country_entry(player_id)
        if not country or not isinstance(country, dict):
            return result

        traditions = country.get("traditions", [])
        if isinstance(traditions, list):
            result["traditions"] = traditions
            result["count"] = len(traditions)

            # Build by_tree summary
            by_tree: dict[str, dict] = {}
            for tradition_id in traditions:
                tree = "unknown"
                if tradition_id.startswith("tr_"):
                    remainder = tradition_id[3:]
                    parts = remainder.split("_", 1)
                    if parts and parts[0]:
                        tree = parts[0]

                entry = by_tree.setdefault(
                    tree, {"picked": [], "adopted": False, "finished": False}
                )
                entry["picked"].append(tradition_id)
                if tradition_id.endswith("_adopt"):
                    entry["adopted"] = True
                if tradition_id.endswith("_finish"):
                    entry["finished"] = True

            result["by_tree"] = by_tree

        return result

    def get_ascension_perks(self) -> dict:
        """Extract picked ascension perks.

        Requires Rust session mode to be active.

        Returns:
            Dict with:
              - ascension_perks: list[str]
              - count: int

        Raises:
            ParserError: If no Rust session is active
        """
        result = {
            "ascension_perks": [],
            "count": 0,
        }

        # Rust session required (get_player_empire_id raises if no session)
        player_id = self.get_player_empire_id()
        country = self._get_player_country_entry(player_id)
        if not country or not isinstance(country, dict):
            return result

        perks = country.get("ascension_perks", [])
        if isinstance(perks, list):
            result["ascension_perks"] = perks
            result["count"] = len(perks)

        return result

    def get_naval_capacity(self) -> dict:
        """Get the player's naval capacity usage.

        Note: Stellaris does not store max naval capacity directly in saves.
        It's calculated dynamically from starbases, techs, civics, etc.
        We provide the used capacity and fleet size.

        Requires Rust session mode to be active.

        Returns:
            Dict with:
              - used: Current naval capacity in use (from used_naval_capacity)
              - fleet_size: Total fleet size (ship count weighted by size)
              - starbase_capacity: Max starbases allowed
              - used_starbase_capacity: Current starbase count

        Raises:
            ParserError: If no Rust session is active
        """
        result = {
            "used": 0,
            "fleet_size": 0,
            "starbase_capacity": None,
            "used_starbase_capacity": None,
        }

        # Rust session required (get_player_empire_id raises if no session)
        player_id = self.get_player_empire_id()
        player_country = self._get_player_country_entry(player_id)

        if not player_country or not isinstance(player_country, dict):
            return result

        # Extract metrics directly from parsed dict
        used = player_country.get("used_naval_capacity")
        if used is not None:
            with contextlib.suppress(ValueError, TypeError):
                result["used"] = int(float(used))

        fleet_size = player_country.get("fleet_size")
        if fleet_size is not None:
            with contextlib.suppress(ValueError, TypeError):
                result["fleet_size"] = int(fleet_size)

        starbase_cap = player_country.get("starbase_capacity")
        if starbase_cap is not None:
            with contextlib.suppress(ValueError, TypeError):
                result["starbase_capacity"] = int(starbase_cap)

        used_starbase = player_country.get("used_starbase_capacity")
        if used_starbase is not None:
            with contextlib.suppress(ValueError, TypeError):
                result["used_starbase_capacity"] = int(used_starbase)

        return result

    def get_relics(self) -> dict:
        """Extract owned relics and activation cooldown (best-effort).

        Requires Rust session mode to be active.

        Returns:
            Dict with:
              - relics: list[str]
              - count: int
              - last_activated_relic: str|None
              - last_received_relic: str|None
              - activation_cooldown_days: int|None

        Raises:
            ParserError: If no Rust session is active
        """
        result = {
            "relics": [],
            "count": 0,
            "last_activated_relic": None,
            "last_received_relic": None,
            "activation_cooldown_days": None,
        }

        # Rust session required (get_player_empire_id raises if no session)
        player_id = self.get_player_empire_id()
        country = self._get_player_country_entry(player_id)
        if not country or not isinstance(country, dict):
            return result

        relics = country.get("relics", [])
        if isinstance(relics, list):
            result["relics"] = relics
            result["count"] = len(relics)

        # These fields may not be present in all saves
        result["last_activated_relic"] = country.get("last_activated_relic")
        result["last_received_relic"] = country.get("last_received_relic")

        return result
