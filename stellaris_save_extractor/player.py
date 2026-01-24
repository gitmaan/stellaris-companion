from __future__ import annotations

import logging
import re
import zipfile
from datetime import datetime
from pathlib import Path

# Rust bridge for fast Clausewitz parsing
try:
    from rust_bridge import (
        extract_sections,
        iter_section_entries,
        ParserError,
        _get_active_session,
    )

    RUST_BRIDGE_AVAILABLE = True
except ImportError:
    RUST_BRIDGE_AVAILABLE = False
    ParserError = Exception  # Fallback type
    _get_active_session = lambda: None

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

    def _parse_simple_string_list_block(
        self, block: str, prefix: str | None = None
    ) -> list[str]:
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

        Returns:
            Player country ID (usually 0)
        """
        # Try Rust parser first
        if RUST_BRIDGE_AVAILABLE:
            try:
                data = extract_sections(self.save_path, ["player"])
                player_list = data.get("player", [])
                if (
                    player_list
                    and isinstance(player_list, list)
                    and len(player_list) > 0
                ):
                    country_id = player_list[0].get("country", "0")
                    return int(country_id)
            except ParserError as e:
                logger.warning(
                    f"Rust parser failed for player: {e}, falling back to regex"
                )
            except Exception as e:
                logger.warning(
                    f"Unexpected error from Rust parser: {e}, falling back to regex"
                )

        # Fallback to regex
        return self._get_player_empire_id_regex()

    def _get_player_empire_id_regex(self) -> int:
        """Get player empire ID using regex (fallback method)."""
        match = re.search(
            r"player\s*=\s*\{[^}]*country\s*=\s*(\d+)", self.gamestate[:5000]
        )
        if match:
            return int(match.group(1))
        return 0

    def get_player_status(self) -> dict:
        """Get the player's current empire status with clear, unambiguous metrics.

        Uses Rust session when active for fast extraction, falls back to regex.

        Returns:
            Dict with empire info, military, economy, and territory data.
            All field names are self-documenting to prevent LLM misinterpretation.

        Note:
            Results are cached per-instance since player status is expensive to compute
            and doesn't change within a single save file analysis.
        """
        # Return cached result if available (expensive computation)
        if self._player_status_cache is not None:
            return self._player_status_cache

        # Dispatch to Rust version when session is active
        session = _get_active_session()
        if session:
            result = self._get_player_status_rust(session)
        else:
            result = self._get_player_status_regex()

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
                    try:
                        result[key] = float(value) if "." in str(value) else int(value)
                    except (ValueError, TypeError):
                        pass

            # Get OWNED fleets from fleets_manager
            fleets_mgr = player_country.get("fleets_manager", {})
            owned_fleets_data = (
                fleets_mgr.get("owned_fleets", [])
                if isinstance(fleets_mgr, dict)
                else []
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
        regular_planets = [
            c for c in colonies if not c.get("type", "").startswith("habitat")
        ]

        habitat_pops = sum(p.get("population", 0) for p in habitats)
        planet_pops = sum(p.get("population", 0) for p in regular_planets)

        result["colonies"] = {
            "total_count": len(colonies),
            "total_population": total_pops,
            "avg_pops_per_colony": (
                round(total_pops / len(colonies), 1) if colonies else 0
            ),
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
                    round(planet_pops / len(regular_planets), 1)
                    if regular_planets
                    else 0
                ),
            },
        }

        return result

    def _get_player_status_regex(self) -> dict:
        """Original regex-based player status extraction (fallback)."""
        player_id = self.get_player_empire_id()

        result = {
            "player_id": player_id,
            "empire_name": self.get_metadata().get("name", "Unknown"),
            "date": self.get_metadata().get("date", "Unknown"),
        }

        # Get the player's country block using proper section detection
        country_content = self._find_player_country_content(player_id)

        if country_content:
            # Extract metrics from the player's country block
            metrics = {
                "military_power": r"military_power\s*=\s*([\d.]+)",
                "economy_power": r"economy_power\s*=\s*([\d.]+)",
                "tech_power": r"tech_power\s*=\s*([\d.]+)",
                "victory_rank": r"victory_rank\s*=\s*(\d+)",
                "fleet_size": r"fleet_size\s*=\s*(\d+)",
            }

            for key, pattern in metrics.items():
                match = re.search(pattern, country_content)
                if match:
                    value = match.group(1)
                    result[key] = float(value) if "." in value else int(value)

            # Get OWNED fleets (not just visible fleets)
            owned_fleet_ids = self._get_owned_fleet_ids(country_content)
            owned_set = set(owned_fleet_ids)

            if owned_fleet_ids:
                # Analyze the owned fleets
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

            # Find controlled planets (all celestial bodies in territory)
            controlled_match = re.search(
                r"controlled_planets\s*=\s*\{([^}]+)\}", country_content
            )
            if controlled_match:
                planet_ids = re.findall(r"\d+", controlled_match.group(1))
                result["celestial_bodies_in_territory"] = len(planet_ids)

        # Get colonized planets data (actual colonies with population)
        # This is the TRUE planet count that matters for empire management
        planets_data = self.get_planets()
        colonies = planets_data.get("planets", [])
        total_pops = sum(p.get("population", 0) for p in colonies)

        # Separate habitats from planets (different pop capacities)
        habitats = [c for c in colonies if c.get("type", "").startswith("habitat")]
        regular_planets = [
            c for c in colonies if not c.get("type", "").startswith("habitat")
        ]

        habitat_pops = sum(p.get("population", 0) for p in habitats)
        planet_pops = sum(p.get("population", 0) for p in regular_planets)

        result["colonies"] = {
            "total_count": len(colonies),
            "total_population": total_pops,
            "avg_pops_per_colony": (
                round(total_pops / len(colonies), 1) if colonies else 0
            ),
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
                    round(planet_pops / len(regular_planets), 1)
                    if regular_planets
                    else 0
                ),
            },
        }

        return result

    def get_empire(self, name: str) -> dict:
        """Get detailed information about a specific empire.

        Args:
            name: Empire name to search for

        Returns:
            Dict with empire details
        """
        result = {"name": name, "found": False}

        country_section = self._extract_section("country")
        if not country_section:
            result["error"] = "Could not find country section"
            return result

        # Search for empire by name
        pattern = rf'name\s*=\s*"{re.escape(name)}"'
        match = re.search(pattern, country_section)

        if not match:
            # Try partial match
            pattern = rf'name\s*=\s*"[^"]*{re.escape(name)}[^"]*"'
            match = re.search(pattern, country_section, re.IGNORECASE)

        if match:
            result["found"] = True

            # Extract surrounding context (the country block)
            # Go back to find the country ID
            pos = match.start()
            block_start = country_section.rfind("\n\t", 0, pos)

            # Find the end of this block
            brace_count = 0
            started = False
            empire_data = ""

            for i, char in enumerate(country_section[block_start:], block_start):
                empire_data += char
                if char == "{":
                    brace_count += 1
                    started = True
                elif char == "}":
                    brace_count -= 1
                    if started and brace_count == 0:
                        break

            result["raw_data_preview"] = (
                empire_data[:8000] + "..." if len(empire_data) > 8000 else empire_data
            )

            # Extract key info
            military_match = re.search(r"military_power\s*=\s*([\d.]+)", empire_data)
            if military_match:
                result["military_power"] = float(military_match.group(1))

            economy_match = re.search(r"economy_power\s*=\s*([\d.]+)", empire_data)
            if economy_match:
                result["economy_power"] = float(economy_match.group(1))

            # Relation to player
            opinion_match = re.search(
                r"opinion\s*=\s*\{[^}]*base\s*=\s*([-\d.]+)", empire_data
            )
            if opinion_match:
                result["opinion"] = float(opinion_match.group(1))

        return result

    def get_empire_identity(self) -> dict:
        """Extract static empire identity for personality generation.

        This extracts ethics, government, civics, and species info from the
        player's country block. This data comes from empire creation and
        only changes via government reform or ethics shift events.

        Returns:
            Dictionary with ethics, government, civics, species, and gestalt flags
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

        # Try Rust session with cached player country entry
        player_id = self.get_player_empire_id()
        country = self._get_player_country_entry(player_id)
        if country and isinstance(country, dict):
            try:
                # Extract ethics
                ethos = country.get("ethos", {})
                if isinstance(ethos, dict):
                    ethic = ethos.get("ethic", [])
                    if isinstance(ethic, str):
                        ethic = [ethic]
                    result["ethics"] = [
                        e.replace("ethic_", "") for e in ethic if isinstance(e, str)
                    ]

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
                        result["civics"] = [
                            c.replace("civic_", "")
                            for c in civics
                            if isinstance(c, str)
                        ]

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
            except Exception as e:
                logger.warning(
                    f"Error extracting empire identity from Rust: {e}, falling back to regex"
                )

        # Fallback to regex
        return self._get_empire_identity_regex()

    def _get_empire_identity_regex(self) -> dict:
        """Extract empire identity using regex (fallback method)."""
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

        player_id = self.get_player_empire_id()

        country_match = re.search(r"^country=\s*\{", self.gamestate, re.MULTILINE)
        if not country_match:
            result["error"] = "Could not find country section"
            return result

        start = country_match.start()
        player_match = re.search(
            r"\n\t0=\s*\{", self.gamestate[start : start + 1000000]
        )
        if not player_match:
            result["error"] = "Could not find player country"
            return result

        player_start = start + player_match.start()
        player_chunk = self.gamestate[player_start : player_start + 500000]

        ethos_match = re.search(r"ethos=\s*\{([^}]+)\}", player_chunk)
        if ethos_match:
            ethos_block = ethos_match.group(1)
            ethics_matches = re.findall(r'ethic="ethic_([^"]+)"', ethos_block)
            result["ethics"] = ethics_matches

        if "gestalt_consciousness" in str(result["ethics"]):
            result["is_gestalt"] = True
            if "auth_machine_intelligence" in player_chunk:
                result["is_machine"] = True
            elif "auth_hive_mind" in player_chunk:
                result["is_hive_mind"] = True

        gov_block_match = re.search(r"government=\s*\{", player_chunk)
        if gov_block_match:
            gov_start = gov_block_match.start()
            gov_chunk = player_chunk[gov_start : gov_start + 2000]

            type_match = re.search(r'type="([^"]+)"', gov_chunk)
            if type_match:
                result["government"] = type_match.group(1).replace("gov_", "")

            auth_match = re.search(r'authority="([^"]+)"', gov_chunk)
            if auth_match:
                result["authority"] = auth_match.group(1).replace("auth_", "")

            civics_match = re.search(r"civics=\s*\{([^}]+)\}", gov_chunk)
            if civics_match:
                civics_block = civics_match.group(1)
                civics = re.findall(r'"civic_([^"]+)"', civics_block)
                result["civics"] = civics

        if result["authority"] == "machine_intelligence":
            result["is_gestalt"] = True
            result["is_machine"] = True
        elif result["authority"] == "hive_mind":
            result["is_gestalt"] = True
            result["is_hive_mind"] = True

        founder_match = re.search(r"founder_species_ref=(\d+)", player_chunk)
        if founder_match:
            species_id = founder_match.group(1)
            species_chunk = self.gamestate[:2000000]
            species_pattern = rf'\b{species_id}=\s*\{{[^}}]*?class="([^"]+)"'
            species_match = re.search(species_pattern, species_chunk, re.DOTALL)
            if species_match:
                result["species_class"] = species_match.group(1)

            species_name_pattern = rf'\b{species_id}=\s*\{{[^}}]*?name="([^"]+)"'
            name_match = re.search(species_name_pattern, species_chunk, re.DOTALL)
            if name_match:
                result["species_name"] = name_match.group(1)

        return result

    def get_traditions(self) -> dict:
        """Extract picked traditions and summarize progress by tree.

        Returns:
            Dict with:
              - traditions: list[str]
              - by_tree: dict[str, {picked: list[str], adopted: bool, finished: bool}]
              - count: int
        """
        result = {
            "traditions": [],
            "by_tree": {},
            "count": 0,
        }

        # Try Rust session with cached player country entry
        player_id = self.get_player_empire_id()
        country = self._get_player_country_entry(player_id)
        if country and isinstance(country, dict):
            try:
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
            except Exception as e:
                logger.warning(
                    f"Error extracting traditions from Rust: {e}, falling back to regex"
                )

        # Fallback to regex
        return self._get_traditions_regex()

    def _get_traditions_regex(self) -> dict:
        """Extract traditions using regex (fallback method)."""
        result = {
            "traditions": [],
            "by_tree": {},
            "count": 0,
        }

        player_id = self.get_player_empire_id()
        country_content = self._find_player_country_content(player_id)
        if not country_content:
            return result

        block = self._extract_braced_block(country_content, "traditions")
        traditions = self._parse_simple_string_list_block(block or "", prefix="tr_")

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

        result["traditions"] = traditions
        result["by_tree"] = by_tree
        result["count"] = len(traditions)
        return result

    def get_ascension_perks(self) -> dict:
        """Extract picked ascension perks.

        Returns:
            Dict with:
              - ascension_perks: list[str]
              - count: int
        """
        result = {
            "ascension_perks": [],
            "count": 0,
        }

        # Try Rust session with cached player country entry
        player_id = self.get_player_empire_id()
        country = self._get_player_country_entry(player_id)
        if country and isinstance(country, dict):
            try:
                perks = country.get("ascension_perks", [])
                if isinstance(perks, list):
                    result["ascension_perks"] = perks
                    result["count"] = len(perks)
                return result
            except Exception as e:
                logger.warning(
                    f"Error extracting ascension_perks from Rust: {e}, falling back to regex"
                )

        # Fallback to regex
        return self._get_ascension_perks_regex()

    def _get_ascension_perks_regex(self) -> dict:
        """Extract ascension perks using regex (fallback method)."""
        result = {
            "ascension_perks": [],
            "count": 0,
        }

        player_id = self.get_player_empire_id()
        country_content = self._find_player_country_content(player_id)
        if not country_content:
            return result

        block = self._extract_braced_block(country_content, "ascension_perks")
        perks = self._parse_simple_string_list_block(block or "", prefix="ap_")

        result["ascension_perks"] = perks
        result["count"] = len(perks)
        return result

    def get_naval_capacity(self) -> dict:
        """Get the player's naval capacity usage.

        Note: Stellaris does not store max naval capacity directly in saves.
        It's calculated dynamically from starbases, techs, civics, etc.
        We provide the used capacity and fleet size.

        Returns:
            Dict with:
              - used: Current naval capacity in use (from used_naval_capacity)
              - fleet_size: Total fleet size (ship count weighted by size)
              - starbase_capacity: Max starbases allowed
              - used_starbase_capacity: Current starbase count
        """
        result = {
            "used": 0,
            "fleet_size": 0,
            "starbase_capacity": None,
            "used_starbase_capacity": None,
        }

        player_id = self.get_player_empire_id()
        country_content = self._find_player_country_content(player_id)
        if not country_content:
            return result

        # Extract used_naval_capacity and fleet_size
        used_match = re.search(r"\bused_naval_capacity=([\d.]+)", country_content)
        fleet_match = re.search(r"\bfleet_size=(\d+)", country_content)
        starbase_cap_match = re.search(r"\bstarbase_capacity=(\d+)", country_content)
        used_starbase_match = re.search(
            r"\bused_starbase_capacity=(\d+)", country_content
        )

        if used_match:
            result["used"] = int(float(used_match.group(1)))
        if fleet_match:
            result["fleet_size"] = int(fleet_match.group(1))
        if starbase_cap_match:
            result["starbase_capacity"] = int(starbase_cap_match.group(1))
        if used_starbase_match:
            result["used_starbase_capacity"] = int(used_starbase_match.group(1))

        return result

    def get_relics(self) -> dict:
        """Extract owned relics and activation cooldown (best-effort).

        Returns:
            Dict with:
              - relics: list[str]
              - count: int
              - last_activated_relic: str|None
              - last_received_relic: str|None
              - activation_cooldown_days: int|None
        """
        result = {
            "relics": [],
            "count": 0,
            "last_activated_relic": None,
            "last_received_relic": None,
            "activation_cooldown_days": None,
        }

        # Try Rust session with cached player country entry
        player_id = self.get_player_empire_id()
        country = self._get_player_country_entry(player_id)
        if country and isinstance(country, dict):
            try:
                relics = country.get("relics", [])
                if isinstance(relics, list):
                    result["relics"] = relics
                    result["count"] = len(relics)

                # These fields may not be in Rust output, try to get them
                result["last_activated_relic"] = country.get("last_activated_relic")
                result["last_received_relic"] = country.get("last_received_relic")
                return result
            except Exception as e:
                logger.warning(
                    f"Error extracting relics from Rust: {e}, falling back to regex"
                )

        # Fallback to regex
        return self._get_relics_regex()

    def _get_relics_regex(self) -> dict:
        """Extract relics using regex (fallback method)."""
        result = {
            "relics": [],
            "count": 0,
            "last_activated_relic": None,
            "last_received_relic": None,
            "activation_cooldown_days": None,
        }

        player_id = self.get_player_empire_id()
        player_block = self._find_player_country_content(player_id)
        if not player_block:
            return result

        relics_block = self._extract_braced_block(player_block, "relics")
        relics = self._parse_simple_string_list_block(relics_block or "", prefix="r_")
        result["relics"] = relics
        result["count"] = len(relics)

        last_activated = re.search(r'\blast_activated_relic="([^"]+)"', player_block)
        if last_activated:
            result["last_activated_relic"] = last_activated.group(1)

        last_received = re.search(r'\blast_received_relic="([^"]+)"', player_block)
        if last_received:
            result["last_received_relic"] = last_received.group(1)

        cooldown = re.search(
            r'modifier="relic_activation_cooldown"[\s\S]{0,200}?\bdays=([-\d]+)',
            player_block,
        )
        if cooldown:
            try:
                result["activation_cooldown_days"] = int(cooldown.group(1))
            except ValueError:
                result["activation_cooldown_days"] = None

        return result
