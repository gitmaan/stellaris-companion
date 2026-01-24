from __future__ import annotations

import logging
import re

# Rust bridge for fast Clausewitz parsing
try:
    from rust_bridge import iter_section_entries, ParserError, _get_active_session

    RUST_BRIDGE_AVAILABLE = True
except ImportError:
    RUST_BRIDGE_AVAILABLE = False
    ParserError = Exception  # Fallback type for type hints
    _get_active_session = lambda: None  # Fallback for type hints

logger = logging.getLogger(__name__)


class EndgameMixin:
    """Extractors for endgame content: Crisis, L-Gates, Become the Crisis."""

    # Crisis country type mappings
    # NOTE: 'swarm' alone is space fauna (Tiyanki, Amoebas, etc.)
    # Prethoryn uses 'swarm_species' and has names containing 'Prethoryn'
    CRISIS_TYPES = {
        "swarm_species": "prethoryn",  # Actual Prethoryn Scourge
        "extradimensional": "unbidden",
        "extradimensional_2": "aberrant",
        "extradimensional_3": "vehement",
        "ai_empire_01": "contingency",  # Contingency machine worlds
        "contingency_machine_empire": "contingency",
    }

    # Space fauna types to EXCLUDE (these are NOT crisis)
    SPACE_FAUNA_TYPES = {
        "swarm",  # Generic space creatures (Tiyanki, Amoebas)
        "amoeba",
        "tiyanki",
        "crystal",
        "drone",
        "cloud",
    }

    def get_crisis_status(self) -> dict:
        """Get current crisis status and player involvement.

        Detects active crisis factions (Prethoryn, Contingency, Unbidden) and
        tracks player's role in fighting or becoming the crisis.

        Uses Rust parser for fast extraction when available, falls back to regex.

        Returns:
            Dict with:
              - crisis_active: Whether a crisis has spawned
              - crisis_type: Type of crisis (prethoryn, contingency, unbidden, etc.)
              - crisis_countries: List of crisis faction country IDs
              - player_is_crisis_fighter: Whether player has crisis_fighter flag
              - player_crisis_kills: Number of crisis ships/armies killed
              - crisis_systems: Count of systems flagged as crisis-controlled
        """
        # Try Rust bridge first for faster parsing
        if RUST_BRIDGE_AVAILABLE:
            try:
                return self._get_crisis_status_rust()
            except ParserError as e:
                logger.warning(
                    f"Rust parser failed for crisis status: {e}, falling back to regex"
                )
            except Exception as e:
                logger.warning(
                    f"Unexpected error from Rust parser: {e}, falling back to regex"
                )

        # Fallback: regex-based parsing
        return self._get_crisis_status_regex()

    def _get_crisis_status_rust(self) -> dict:
        """Get crisis status using Rust parser.

        Returns:
            Dict with crisis status details
        """
        # Check for active session at start - delegate to regex if not available
        session = _get_active_session()
        if not session:
            return self._get_crisis_status_regex()

        result = {
            "crisis_active": False,
            "crisis_type": None,
            "crisis_types_detected": [],
            "crisis_countries": [],
            "player_is_crisis_fighter": False,
            "player_crisis_kills": 0,
            "crisis_systems_count": 0,
        }

        # Detect crisis countries by iterating over country section
        crisis_countries = []
        crisis_types_found = set()

        for country_id, country_data in session.iter_section("country"):
            if not isinstance(country_data, dict):
                continue

            # Check country type
            ctype = country_data.get("country_type") or country_data.get("type")
            if not ctype:
                continue

            # Skip space fauna
            if ctype in self.SPACE_FAUNA_TYPES:
                continue

            # Check for known crisis types
            if ctype in self.CRISIS_TYPES:
                crisis_name = self.CRISIS_TYPES[ctype]
                crisis_countries.append(
                    {
                        "country_id": int(country_id),
                        "type": crisis_name,
                    }
                )
                crisis_types_found.add(crisis_name)
                continue

            # Also check for Prethoryn by name (backup detection)
            name_data = country_data.get("name", {})
            if isinstance(name_data, dict):
                name_key = name_data.get("key", "")
                if name_key and "prethoryn" in name_key.lower():
                    crisis_countries.append(
                        {
                            "country_id": int(country_id),
                            "type": "prethoryn",
                        }
                    )
                    crisis_types_found.add("prethoryn")

        result["crisis_countries"] = crisis_countries
        result["crisis_types_detected"] = list(crisis_types_found)
        result["crisis_active"] = len(crisis_types_found) > 0
        if crisis_types_found:
            # Primary crisis type (prioritize main ones)
            for primary in ["prethoryn", "contingency", "unbidden"]:
                if primary in crisis_types_found:
                    result["crisis_type"] = primary
                    break
            if not result["crisis_type"]:
                result["crisis_type"] = list(crisis_types_found)[0]

        # Check player's crisis involvement from cached player country entry
        player_id = self.get_player_empire_id()
        player_data = self._get_player_country_entry(player_id)
        if player_data and isinstance(player_data, dict):
            # Check for crisis_fighter flag
            flags = player_data.get("flags", {})
            if isinstance(flags, dict) and "crisis_fighter" in flags:
                result["player_is_crisis_fighter"] = True

            # Check for crisis_kills count
            crisis_kills = player_data.get("crisis_kills")
            if crisis_kills is not None:
                try:
                    result["player_crisis_kills"] = int(crisis_kills)
                except (ValueError, TypeError):
                    pass

        # Count crisis-controlled systems via count_keys (tree traversal)
        # This is faster than regex since we traverse the already-parsed JSON tree
        crisis_system_flags = [
            "prethoryn_system",  # Prethoryn infested systems
            "prethoryn_invasion_system",  # Prethoryn invasion target
            "contingency_system",  # Contingency sterilization hubs
            "contingency_world",  # Contingency machine world
            "unbidden_portal_system",  # Unbidden dimensional anchor
            "extradimensional_system",  # Generic extradimensional flag
        ]

        # Use count_keys operation (session guaranteed to be active from start check)
        counts_result = session.count_keys(crisis_system_flags)
        counts = counts_result.get("counts", {})
        result["crisis_systems_count"] = sum(counts.values())

        return result

    def _get_crisis_status_regex(self) -> dict:
        """Get crisis status using regex parsing (fallback method).

        Returns:
            Dict with crisis status details
        """
        result = {
            "crisis_active": False,
            "crisis_type": None,
            "crisis_types_detected": [],
            "crisis_countries": [],
            "player_is_crisis_fighter": False,
            "player_crisis_kills": 0,
            "crisis_systems_count": 0,
        }

        # Detect crisis countries by country_type
        crisis_countries = []
        crisis_types_found = set()

        # Find crisis country IDs by scanning the country section
        country_section_start = self._find_country_section_start()
        if country_section_start != -1:
            country_chunk = self.gamestate[
                country_section_start : country_section_start + 50000000
            ]

            # Find countries with crisis types
            for match in re.finditer(r"\n\t(\d+)=\n\t\{", country_chunk):
                country_id = int(match.group(1))
                start = match.start()

                # Get a reasonable chunk of this country
                end = start + 50000
                block = country_chunk[start:end]

                # Check if this is a crisis country by looking for country_type
                ctype = None
                ctype_match = re.search(r'\bcountry_type="([^"]+)"', block[:5000])
                if ctype_match:
                    ctype = ctype_match.group(1)

                # Skip space fauna
                if ctype and ctype in self.SPACE_FAUNA_TYPES:
                    continue

                # Check for known crisis types
                if ctype and ctype in self.CRISIS_TYPES:
                    crisis_name = self.CRISIS_TYPES[ctype]
                    crisis_countries.append(
                        {
                            "country_id": country_id,
                            "type": crisis_name,
                        }
                    )
                    crisis_types_found.add(crisis_name)
                    continue

                # Also check for Prethoryn by name (backup detection)
                name_match = re.search(r'key="([^"]*[Pp]rethoryn[^"]*)"', block[:5000])
                if name_match:
                    crisis_countries.append(
                        {
                            "country_id": country_id,
                            "type": "prethoryn",
                        }
                    )
                    crisis_types_found.add("prethoryn")

        result["crisis_countries"] = crisis_countries
        result["crisis_types_detected"] = list(crisis_types_found)
        result["crisis_active"] = len(crisis_types_found) > 0
        if crisis_types_found:
            # Primary crisis type (prioritize main ones)
            for primary in ["prethoryn", "contingency", "unbidden"]:
                if primary in crisis_types_found:
                    result["crisis_type"] = primary
                    break
            if not result["crisis_type"]:
                result["crisis_type"] = list(crisis_types_found)[0]

        # Check player's crisis involvement
        player_id = self.get_player_empire_id()
        player_chunk = self._find_player_country_content(player_id)
        if player_chunk:
            # Check for crisis_fighter flag
            if "crisis_fighter=yes" in player_chunk:
                result["player_is_crisis_fighter"] = True

            # Check for crisis_kills count
            kills_match = re.search(r"\bcrisis_kills=(\d+)", player_chunk)
            if kills_match:
                result["player_crisis_kills"] = int(kills_match.group(1))

        # Count crisis-controlled systems via flags
        # NOTE: 'hostile_system' is for space creatures (amoebas, drones, etc.), NOT crisis
        # NOTE: 'lost_swarm_system' is for the Lost Swarm space creature event, NOT Prethoryn
        crisis_system_flags = [
            "prethoryn_system",  # Prethoryn infested systems
            "prethoryn_invasion_system",  # Prethoryn invasion target
            "contingency_system",  # Contingency sterilization hubs
            "contingency_world",  # Contingency machine world
            "unbidden_portal_system",  # Unbidden dimensional anchor
            "extradimensional_system",  # Generic extradimensional flag
        ]
        total_crisis_systems = 0
        for flag in crisis_system_flags:
            total_crisis_systems += len(re.findall(rf"\b{flag}=", self.gamestate))

        result["crisis_systems_count"] = total_crisis_systems

        return result

    def get_lgate_status(self) -> dict:
        """Get L-Gate and L-Cluster status.

        Tracks L-Gate insights collected and whether the L-Cluster has been opened.

        Uses Rust parser for fast extraction when available, falls back to regex.

        Returns:
            Dict with:
              - lgate_enabled: Whether L-Gates exist in this galaxy
              - insights_collected: Number of L-Gate insights (from tech_repeatable_lcluster_clue)
              - insights_required: Usually 7 to open
              - lgate_opened: Whether L-Cluster has been accessed
              - player_activation_progress: Tech progress toward activation (0-100)
        """
        # Try Rust bridge first for faster parsing
        if RUST_BRIDGE_AVAILABLE:
            try:
                return self._get_lgate_status_rust()
            except ParserError as e:
                logger.warning(
                    f"Rust parser failed for L-Gate status: {e}, falling back to regex"
                )
            except Exception as e:
                logger.warning(
                    f"Unexpected error from Rust parser: {e}, falling back to regex"
                )

        # Fallback: regex-based parsing
        return self._get_lgate_status_regex()

    def _get_lgate_status_rust(self) -> dict:
        """Get L-Gate status using Rust parser.

        Returns:
            Dict with L-Gate status details
        """
        # Check for active session at start - delegate to regex if not available
        session = _get_active_session()
        if not session:
            return self._get_lgate_status_regex()

        result = {
            "lgate_enabled": False,
            "insights_collected": 0,
            "insights_required": 7,  # Standard requirement
            "lgate_opened": False,
            "player_activation_progress": 0,
        }

        # Check if L-Gates are enabled using contains_tokens
        lgate_tokens = session.contains_tokens(["lgate_enabled=yes", "lgate_enabled=no"])
        matches = lgate_tokens.get("matches", {})
        if matches.get("lgate_enabled=yes"):
            result["lgate_enabled"] = True
        elif matches.get("lgate_enabled=no"):
            result["lgate_enabled"] = False
            return result  # No point checking further

        # Get player's L-Gate insights from cached player country entry
        player_id = self.get_player_empire_id()
        country_data = self._get_player_country_entry(player_id)

        if isinstance(country_data, dict):
            tech_status = country_data.get("tech_status", {})
            if isinstance(tech_status, dict):
                # Look for tech_repeatable_lcluster_clue in technology list
                # Note: Due to duplicate key issues, we may need to check multiple formats
                # Try the level field for repeatables
                repeatables = tech_status.get("repeatables", {})
                if isinstance(repeatables, dict):
                    clue_level = repeatables.get("tech_repeatable_lcluster_clue")
                    if clue_level is not None:
                        try:
                            result["insights_collected"] = int(clue_level)
                        except (ValueError, TypeError):
                            pass

                # Check for activation tech progress in tech_status.potential block
                potential = tech_status.get("potential", {})
                if isinstance(potential, dict):
                    activation_progress = potential.get("tech_lgate_activation")
                    if activation_progress is not None:
                        try:
                            result["player_activation_progress"] = int(activation_progress)
                        except (ValueError, TypeError):
                            pass

        # Check if L-Gate has been opened using contains_tokens
        lcluster_tokens = session.contains_tokens([
            "lcluster_",
            "l_cluster_opened",
            "gray_tempest_country"
        ])
        lcluster_matches = lcluster_tokens.get("matches", {})
        if any(lcluster_matches.values()):
            result["lgate_opened"] = True

        return result

    def _get_lgate_status_regex(self) -> dict:
        """Get L-Gate status using regex parsing (fallback method).

        Returns:
            Dict with L-Gate status details
        """
        result = {
            "lgate_enabled": False,
            "insights_collected": 0,
            "insights_required": 7,  # Standard requirement
            "lgate_opened": False,
            "player_activation_progress": 0,
        }

        # Check if L-Gates are enabled in galaxy settings
        if "lgate_enabled=yes" in self.gamestate:
            result["lgate_enabled"] = True
        elif "lgate_enabled=no" in self.gamestate:
            result["lgate_enabled"] = False
            return result  # No point checking further

        # Get player's L-Gate insights from tech_repeatable_lcluster_clue
        player_id = self.get_player_empire_id()
        player_chunk = self._find_player_country_content(player_id)

        if player_chunk:
            # Look for tech_repeatable_lcluster_clue in technology section
            tech_block = self._extract_braced_block(player_chunk, "tech_status")
            if tech_block:
                # Find the repeatable tech entry
                clue_match = re.search(
                    r'technology="tech_repeatable_lcluster_clue"[^}]*level=(\d+)',
                    tech_block,
                )
                if clue_match:
                    result["insights_collected"] = int(clue_match.group(1))

            # Check for activation tech progress
            # This appears in potential={} section as "tech_lgate_activation"="XX"
            potential_match = re.search(
                r'"tech_lgate_activation"="(\d+)"', player_chunk
            )
            if potential_match:
                result["player_activation_progress"] = int(potential_match.group(1))

        # Check if L-Gate has been opened (look for L-Cluster access)
        # When opened, there will be bypass connections to the L-Cluster
        # Or we can check for gray_tempest/lcluster related flags
        if re.search(
            r"lcluster_|l_cluster_opened|gray_tempest_country", self.gamestate
        ):
            result["lgate_opened"] = True

        # Also check if player has the activation tech completed
        if player_chunk:
            if "tech_lgate_activation" in player_chunk:
                tech_section = self._extract_braced_block(player_chunk, "technology")
                if tech_section and '"tech_lgate_activation"' in tech_section:
                    # Check if it's in completed techs (not just potential)
                    completed_block = self._extract_braced_block(
                        tech_section, "completed"
                    )
                    if completed_block and "tech_lgate_activation" in completed_block:
                        result["lgate_opened"] = True

        return result

    def get_menace(self) -> dict:
        """Get Become the Crisis status for the player.

        Tracks menace level and crisis ascension progress if player has
        the ap_become_the_crisis ascension perk.

        Uses Rust parser for fast extraction when available, falls back to regex.

        Returns:
            Dict with:
              - has_crisis_perk: Whether player has Become the Crisis perk
              - menace_level: Current menace accumulated
              - crisis_level: Crisis ascension tier (0-5)
        """
        # Try Rust bridge first for faster parsing
        if RUST_BRIDGE_AVAILABLE:
            try:
                return self._get_menace_rust()
            except ParserError as e:
                logger.warning(
                    f"Rust parser failed for menace: {e}, falling back to regex"
                )
            except Exception as e:
                logger.warning(
                    f"Unexpected error from Rust parser: {e}, falling back to regex"
                )

        # Fallback: regex-based parsing
        return self._get_menace_regex()

    def _get_menace_rust(self) -> dict:
        """Get menace status using Rust parser.

        Returns:
            Dict with menace status details
        """
        # Check for active session at start - delegate to regex if not available
        session = _get_active_session()
        if not session:
            return self._get_menace_regex()

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
        # Note: ascension_perks may have duplicate keys, so use regex fallback for reliability
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
                try:
                    result["menace_level"] = int(menace)
                except (ValueError, TypeError):
                    pass

            # Crisis level/tier
            crisis_level = country_data.get("crisis_level")
            if crisis_level is not None:
                try:
                    result["crisis_level"] = int(crisis_level)
                except (ValueError, TypeError):
                    pass

        return result

    def _get_menace_regex(self) -> dict:
        """Get menace status using regex parsing (fallback method).

        Returns:
            Dict with menace status details
        """
        result = {
            "has_crisis_perk": False,
            "menace_level": 0,
            "crisis_level": 0,
        }

        player_id = self.get_player_empire_id()
        player_chunk = self._find_player_country_content(player_id)

        if not player_chunk:
            return result

        # Check for Become the Crisis ascension perk
        ascension_block = self._extract_braced_block(player_chunk, "ascension_perks")
        if ascension_block:
            if "ap_become_the_crisis" in ascension_block:
                result["has_crisis_perk"] = True

        # If they have the perk, look for menace tracking
        if result["has_crisis_perk"]:
            # Menace is stored in the country block
            menace_match = re.search(r"\bmenace=(\d+)", player_chunk)
            if menace_match:
                result["menace_level"] = int(menace_match.group(1))

            # Crisis level/tier
            crisis_level_match = re.search(r"\bcrisis_level=(\d+)", player_chunk)
            if crisis_level_match:
                result["crisis_level"] = int(crisis_level_match.group(1))

        return result

    def get_great_khan(self) -> dict:
        """Get Great Khan / Marauder status.

        The Great Khan is a mid-game crisis where marauder clans unify under
        a single leader and begin conquering the galaxy.

        Uses Rust parser for fast extraction when available, falls back to regex.

        Returns:
            Dict with:
              - marauders_present: Whether marauder empires exist
              - marauder_count: Number of marauder factions
              - khan_risen: Whether the Great Khan has spawned
              - khan_status: Current state (active, defeated, etc.)
              - khan_country_id: Country ID of the Khan's empire if active
        """
        # Try Rust bridge first for faster parsing
        if RUST_BRIDGE_AVAILABLE:
            try:
                return self._get_great_khan_rust()
            except ParserError as e:
                logger.warning(
                    f"Rust parser failed for Great Khan: {e}, falling back to regex"
                )
            except Exception as e:
                logger.warning(
                    f"Unexpected error from Rust parser: {e}, falling back to regex"
                )

        # Fallback: regex-based parsing
        return self._get_great_khan_regex()

    def _get_great_khan_rust(self) -> dict:
        """Get Great Khan status using Rust parser.

        Returns:
            Dict with Great Khan status details
        """
        # Check for active session at start - delegate to regex if not available
        session = _get_active_session()
        if not session:
            return self._get_great_khan_regex()

        result = {
            "marauders_present": False,
            "marauder_count": 0,
            "khan_risen": False,
            "khan_status": None,
            "khan_country_id": None,
        }

        marauder_count = 0
        khan_country_id = None

        for country_id, country_data in session.iter_section("country"):
            if not isinstance(country_data, dict):
                continue

            ctype = country_data.get("country_type") or country_data.get("type")
            if not ctype:
                continue

            # Check for marauder types
            if ctype in ("dormant_marauders", "marauder", "marauder_raiders"):
                result["marauders_present"] = True
                marauder_count += 1

            # Check for awakened marauders (Great Khan)
            if ctype in ("awakened_marauders", "marauder_empire"):
                result["khan_risen"] = True
                result["khan_status"] = "active"
                khan_country_id = int(country_id)

            # Also check country name for marauder identification
            name_data = country_data.get("name", {})
            if isinstance(name_data, dict):
                name_key = name_data.get("key", "")
                if name_key and "marauder" in name_key.lower():
                    result["marauders_present"] = True
                    if not marauder_count:  # Don't double count
                        marauder_count += 1

        # Cap marauder count at realistic number
        if marauder_count > 0:
            result["marauder_count"] = min(marauder_count, 3)

        if khan_country_id is not None:
            result["khan_country_id"] = khan_country_id

        # Check for Khan defeated via flag search using contains_tokens
        khan_defeated_tokens = [
            "great_khan_dead",
            "great_khan_defeated",
            "khan_successor",  # Khan died, successors fighting
        ]
        defeated_result = session.contains_tokens(khan_defeated_tokens)
        defeated_matches = defeated_result.get("matches", {})

        if any(defeated_matches.values()):
            result["khan_risen"] = True  # Was risen at some point
            result["khan_status"] = "defeated"

        # Check for Khan rising via flags if not detected by country type
        if not result["khan_risen"]:
            khan_risen_tokens = [
                "great_khan_risen",
                "great_khan=yes",
                "khan_country",
            ]
            risen_result = session.contains_tokens(khan_risen_tokens)
            risen_matches = risen_result.get("matches", {})

            if any(risen_matches.values()):
                result["khan_risen"] = True
                result["khan_status"] = "active"

        return result

    def _get_great_khan_regex(self) -> dict:
        """Get Great Khan status using regex parsing (fallback method).

        Returns:
            Dict with Great Khan status details
        """
        result = {
            "marauders_present": False,
            "marauder_count": 0,
            "khan_risen": False,
            "khan_status": None,
            "khan_country_id": None,
        }

        # Check for marauder countries
        # Marauders have type="dormant_marauders" or similar
        marauder_patterns = [
            r'type="dormant_marauders"',
            r'type="marauder"',
            r'type="marauder_raiders"',
            r'key="NAME_Marauder"',
        ]

        marauder_count = 0
        for pattern in marauder_patterns:
            matches = re.findall(pattern, self.gamestate)
            if matches:
                result["marauders_present"] = True
                marauder_count += len(matches)

        # Dedupe - NAME_Marauder appears multiple times per empire
        # Estimate actual marauder empires (usually 1-3)
        if marauder_count > 0:
            result["marauder_count"] = min(marauder_count, 3)  # Cap at realistic number

        # Check for Great Khan rising
        # The Khan has specific country type and event flags
        khan_patterns = [
            (r'type="awakened_marauders"', "active"),
            (r'type="marauder_empire"', "active"),
            (r"great_khan_risen", "active"),
            (r"great_khan=yes", "active"),
            (r"khan_country", "active"),
        ]

        for pattern, status in khan_patterns:
            if re.search(pattern, self.gamestate):
                result["khan_risen"] = True
                result["khan_status"] = status
                break

        # Check for Khan defeated
        khan_defeated_patterns = [
            r"great_khan_dead",
            r"great_khan_defeated",
            r"khan_successor",  # Khan died, successors fighting
        ]

        for pattern in khan_defeated_patterns:
            if re.search(pattern, self.gamestate):
                result["khan_risen"] = True  # Was risen at some point
                result["khan_status"] = "defeated"
                break

        # Try to find Khan's country ID if active
        if result["khan_risen"] and result["khan_status"] == "active":
            # Look for awakened_marauders country
            country_section_start = self._find_country_section_start()
            if country_section_start != -1:
                country_chunk = self.gamestate[
                    country_section_start : country_section_start + 10000000
                ]

                for match in re.finditer(r"\n\t(\d+)=\n\t\{", country_chunk):
                    country_id = int(match.group(1))
                    start = match.start()
                    block = country_chunk[start : start + 5000]

                    if (
                        'type="awakened_marauders"' in block
                        or 'type="marauder_empire"' in block
                    ):
                        result["khan_country_id"] = country_id
                        break

        return result
