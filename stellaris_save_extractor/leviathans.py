from __future__ import annotations

import logging
import re

# Rust bridge for Clausewitz parsing (required for session mode)
from rust_bridge import _get_active_session

logger = logging.getLogger(__name__)


class LeviathansMixin:
    """Extractors for Leviathans, Guardians, and space creatures."""

    # Known leviathan/guardian types with human-readable names and rewards
    LEVIATHAN_INFO = {
        "tiyanki": {
            "name": "Tiyanki (Space Whales)",
            "reward": "Tiyanki strategic resource, research",
            "threat": "Low (passive unless attacked)",
        },
        "crystal": {
            "name": "Crystalline Entities",
            "reward": "Crystal armor technology",
            "threat": "Medium (territorial)",
        },
        "amoeba": {
            "name": "Space Amoeba",
            "reward": "Amoeba flagella components",
            "threat": "Low-Medium (can be pacified)",
        },
        "cloud": {
            "name": "Void Cloud",
            "reward": "Cloud lightning weapon",
            "threat": "Medium",
        },
        "drone": {
            "name": "Mining Drones",
            "reward": "Drone components, minerals",
            "threat": "Low-Medium",
        },
        "ether_drake": {
            "name": "Ether Drake",
            "reward": "Dragon armor, Dragon trophy",
            "threat": "Very High (25k+ fleet power)",
        },
        "dimensional_horror": {
            "name": "Dimensional Horror",
            "reward": "Dark matter tech, jump drive insights",
            "threat": "Very High",
        },
        "automated_dreadnought": {
            "name": "Automated Dreadnought",
            "reward": "Can be captured as flagship",
            "threat": "Very High",
        },
        "stellarite": {
            "name": "Stellarite Devourer",
            "reward": "Stellar energy tech",
            "threat": "Very High",
        },
        "enigmatic_fortress": {
            "name": "Enigmatic Fortress",
            "reward": "Rare tech (random)",
            "threat": "High (puzzle encounter)",
        },
        "voidspawn": {
            "name": "Voidspawn",
            "reward": "Unique rewards",
            "threat": "Very High",
        },
        "wraith": {
            "name": "Spectral Wraith",
            "reward": "Psionic tech",
            "threat": "High",
        },
    }

    # Country type mappings for leviathan detection via Rust parser
    LEVIATHAN_COUNTRY_TYPES = {
        "tiyanki_country": "tiyanki",
        "crystal_country": "crystal",
        "amoeba_country": "amoeba",
        "cloud_country": "cloud",
        "mining_drone_country": "drone",
        "drone_country": "drone",
    }

    def get_leviathans(self) -> dict:
        """Get status of Leviathans and Guardians in the galaxy.

        Uses Rust parser for fast extraction when available, falls back to regex.

        Returns:
            Dict with:
              - leviathans: List of detected leviathans with status
              - total_count: Number of leviathan types detected
              - defeated_count: Number defeated by player
              - alive_count: Number still active
        """
        # Dispatch to Rust version when session is active (P030)
        session = _get_active_session()
        if session:
            return self._get_leviathans_rust()
        return self._get_leviathans_regex()

    def _get_leviathans_rust(self) -> dict:
        """Get leviathan status using Rust parser.

        Uses session mode for fast data access:
        - session.iter_section() for countries to find leviathan country types (P031)
        - session.contains_tokens() for fast guardian detection and defeat markers

        Returns:
            Dict with leviathan status details
        """
        # Check for active session first (P030)
        session = _get_active_session()
        if not session:
            return self._get_leviathans_regex()

        result = {
            "leviathans": [],
            "total_count": 0,
            "defeated_count": 0,
            "alive_count": 0,
        }

        detected_types = set()

        # First pass: detect leviathan countries via session.iter_section (P031)
        for country_id, country_data in session.iter_section("country"):
            if not isinstance(country_data, dict):  # P010: handle "none" strings
                continue

            ctype = country_data.get("country_type") or country_data.get("type")
            if ctype and ctype in self.LEVIATHAN_COUNTRY_TYPES:
                detected_types.add(self.LEVIATHAN_COUNTRY_TYPES[ctype])

            # Also check country name for additional identification
            name_data = country_data.get("name", {})
            if isinstance(name_data, dict):
                name_key = name_data.get("key", "").lower()
                # Check for specific leviathan name keys
                if "tiyanki" in name_key:
                    detected_types.add("tiyanki")
                elif "crystal" in name_key or "prism" in name_key:
                    detected_types.add("crystal")
                elif "amoeba" in name_key or "spaceborne_organic" in name_key:
                    detected_types.add("amoeba")
                elif "cloud" in name_key:
                    detected_types.add("cloud")
                elif "mining_drone" in name_key:
                    detected_types.add("drone")

        # Second pass: detect guardians via contains_tokens (fast Aho-Corasick scan)
        # These are the major guardians that may not have dedicated country types
        guardian_tokens = {
            "ether_drake": [
                "ether_drake",
                "dragon_armor",
                "NAME_Ether_Drake",
            ],
            "dimensional_horror": [
                "dimensional_horror",
                "NAME_Dimensional_Horror",
            ],
            "automated_dreadnought": [
                "automated_dreadnought",
                "NAME_Automated_Dreadnought",
            ],
            "stellarite": [
                "stellarite",
                "NAME_Stellarite",
            ],
            "enigmatic_fortress": [
                "enigmatic_fortress",
                "NAME_Enigmatic_Fortress",
            ],
            "voidspawn": [
                "voidspawn",
                "NAME_Voidspawn",
            ],
            "wraith": [
                "spectral_wraith",
                "NAME_Spectral_Wraith",
            ],
        }

        # Collect all tokens for a single Aho-Corasick scan
        all_tokens = []
        token_to_guardian = {}
        for lev_key, tokens in guardian_tokens.items():
            for token in tokens:
                all_tokens.append(token)
                token_to_guardian[token] = lev_key

        result_data = session.contains_tokens(all_tokens)
        matches = result_data.get("matches", {})
        for token, found in matches.items():
            if found and token in token_to_guardian:
                detected_types.add(token_to_guardian[token])

        # Build result list with status
        # Pre-compute defeat status for all detected types using contains_tokens
        defeat_status = self._check_leviathans_defeated_rust(detected_types, session)

        detected = []
        for lev_key in detected_types:
            info = self.LEVIATHAN_INFO.get(lev_key, {})
            defeated = defeat_status.get(lev_key, False)

            detected.append(
                {
                    "type": lev_key,
                    "name": info.get("name", lev_key.replace("_", " ").title()),
                    "status": "defeated" if defeated else "alive",
                    "reward": info.get("reward", "Unknown"),
                    "threat": info.get("threat", "Unknown"),
                }
            )

        result["leviathans"] = detected
        result["total_count"] = len(detected)
        result["defeated_count"] = sum(1 for l in detected if l["status"] == "defeated")
        result["alive_count"] = sum(1 for l in detected if l["status"] == "alive")

        return result

    def _get_leviathans_regex(self) -> dict:
        """Get leviathan status using regex parsing (fallback method).

        Returns:
            Dict with leviathan status details
        """
        result = {
            "leviathans": [],
            "total_count": 0,
            "defeated_count": 0,
            "alive_count": 0,
        }

        detected = []

        # Check for various leviathan types via country names, flags, and markers
        leviathan_patterns = {
            "tiyanki": [
                r'name="tiyanki_country"',
                r"tiyanki_spawn_system",
                r"NAME_Placid_Leviathans",
            ],
            "crystal": [
                r'name="crystal_country"',
                r"NAME_Prism",
                r"crystal_armor",
            ],
            "amoeba": [
                r'name="amoeba_country"',
                r"amoeba_home_system",
                r"NAME_Spaceborne_Organics",
            ],
            "cloud": [
                r'name="cloud_country"',
                r"NAME_Cloud_Entity",
                r"SPACE_CLOUD_LIGHTNING",
            ],
            "drone": [
                r"mining_drone.*country",
                r"NAME_Aggressive_Mining_Drone",
            ],
            "ether_drake": [
                r"ether_drake",
                r"dragon_armor",
                r"NAME_Ether_Drake",
                r"killed_ether_drake",
            ],
            "dimensional_horror": [
                r"dimensional_horror",
                r"NAME_Dimensional_Horror",
            ],
            "automated_dreadnought": [
                r"automated_dreadnought",
                r"NAME_Automated_Dreadnought",
            ],
            "stellarite": [
                r"stellarite",
                r"NAME_Stellarite",
            ],
            "enigmatic_fortress": [
                r"enigmatic_fortress",
                r"NAME_Enigmatic_Fortress",
            ],
            "voidspawn": [
                r"voidspawn",
                r"NAME_Voidspawn",
            ],
            "wraith": [
                r"spectral_wraith",
                r"NAME_Spectral_Wraith",
            ],
        }

        # Check for each leviathan type
        for lev_key, patterns in leviathan_patterns.items():
            found = False
            for pattern in patterns:
                if re.search(pattern, self.gamestate, re.IGNORECASE):
                    found = True
                    break

            if found:
                info = self.LEVIATHAN_INFO.get(lev_key, {})

                # Check if defeated
                defeated = self._check_leviathan_defeated(lev_key)

                detected.append(
                    {
                        "type": lev_key,
                        "name": info.get("name", lev_key.replace("_", " ").title()),
                        "status": "defeated" if defeated else "alive",
                        "reward": info.get("reward", "Unknown"),
                        "threat": info.get("threat", "Unknown"),
                    }
                )

        result["leviathans"] = detected
        result["total_count"] = len(detected)
        result["defeated_count"] = sum(1 for l in detected if l["status"] == "defeated")
        result["alive_count"] = sum(1 for l in detected if l["status"] == "alive")

        return result

    def _check_leviathan_defeated(self, leviathan_type: str) -> bool:
        """Check if a specific leviathan has been defeated."""

        # Common defeat flag patterns
        defeat_patterns = [
            rf"killed_{leviathan_type}",
            rf"{leviathan_type}_defeated",
            rf"{leviathan_type}_dead",
            rf"defeated_{leviathan_type}",
        ]

        for pattern in defeat_patterns:
            if re.search(pattern, self.gamestate, re.IGNORECASE):
                return True

        # Special cases
        if leviathan_type == "ether_drake":
            if re.search(
                r"killed_dragon|dragon_killed|ether_drake_killed",
                self.gamestate,
                re.IGNORECASE,
            ):
                return True
            # Check for dragon trophy (indicates defeat)
            if re.search(r"relic_dragon_trophy", self.gamestate):
                return True

        if leviathan_type == "automated_dreadnought":
            # Can be captured instead of destroyed
            if re.search(r"dreadnought_captured|owns_dreadnought", self.gamestate, re.IGNORECASE):
                return True

        if leviathan_type == "enigmatic_fortress":
            # Fortress is "solved" not defeated
            if re.search(r"fortress_solved|enigmatic_cache", self.gamestate, re.IGNORECASE):
                return True

        return False

    def _check_leviathans_defeated_rust(self, leviathan_types: set, session) -> dict:
        """Check defeat status for multiple leviathans using contains_tokens.

        This is faster than calling _check_leviathan_defeated() for each type
        because it batches all token checks into a single Aho-Corasick scan.

        Args:
            leviathan_types: Set of leviathan type keys to check
            session: Active RustSession instance

        Returns:
            Dict mapping leviathan_type -> bool (True if defeated)
        """
        if not session or not leviathan_types:
            return {}

        # Build all defeat tokens for all leviathan types
        all_tokens = []
        token_to_leviathan = {}

        for lev_type in leviathan_types:
            # Common defeat patterns
            defeat_tokens = [
                f"killed_{lev_type}",
                f"{lev_type}_defeated",
                f"{lev_type}_dead",
                f"defeated_{lev_type}",
            ]

            # Special cases
            if lev_type == "ether_drake":
                defeat_tokens.extend(
                    [
                        "killed_dragon",
                        "dragon_killed",
                        "ether_drake_killed",
                        "relic_dragon_trophy",
                    ]
                )
            elif lev_type == "automated_dreadnought":
                defeat_tokens.extend(
                    [
                        "dreadnought_captured",
                        "owns_dreadnought",
                    ]
                )
            elif lev_type == "enigmatic_fortress":
                defeat_tokens.extend(
                    [
                        "fortress_solved",
                        "enigmatic_cache",
                    ]
                )

            for token in defeat_tokens:
                all_tokens.append(token)
                # Map token back to leviathan type (many-to-one)
                if token not in token_to_leviathan:
                    token_to_leviathan[token] = lev_type

        # Single Aho-Corasick scan for all defeat tokens
        result_data = session.contains_tokens(all_tokens)
        matches = result_data.get("matches", {})

        # Build defeat status dict
        defeat_status = {lev_type: False for lev_type in leviathan_types}
        for token, found in matches.items():
            if found and token in token_to_leviathan:
                defeat_status[token_to_leviathan[token]] = True

        return defeat_status

    def get_guardians_summary(self) -> dict:
        """Get a quick summary of guardian status for briefings.

        Returns simplified view suitable for injection into advisor context.
        """
        full = self.get_leviathans()

        # Filter to just major guardians (high threat)
        major_guardians = [
            l
            for l in full["leviathans"]
            if "High" in l.get("threat", "") or "Very High" in l.get("threat", "")
        ]

        alive_names = [l["name"] for l in major_guardians if l["status"] == "alive"]
        defeated_names = [l["name"] for l in major_guardians if l["status"] == "defeated"]

        return {
            "major_guardians_alive": alive_names,
            "major_guardians_defeated": defeated_names,
            "minor_creatures_present": full["alive_count"] - len(alive_names),
        }
