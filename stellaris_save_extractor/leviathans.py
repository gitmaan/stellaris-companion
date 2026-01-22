from __future__ import annotations

import logging
import re

# Rust bridge for fast Clausewitz parsing
try:
    from rust_bridge import iter_section_entries, ParserError
    RUST_BRIDGE_AVAILABLE = True
except ImportError:
    RUST_BRIDGE_AVAILABLE = False
    ParserError = Exception  # Fallback type for type hints

logger = logging.getLogger(__name__)


class LeviathansMixin:
    """Extractors for Leviathans, Guardians, and space creatures."""

    # Known leviathan/guardian types with human-readable names and rewards
    LEVIATHAN_INFO = {
        'tiyanki': {
            'name': 'Tiyanki (Space Whales)',
            'reward': 'Tiyanki strategic resource, research',
            'threat': 'Low (passive unless attacked)',
        },
        'crystal': {
            'name': 'Crystalline Entities',
            'reward': 'Crystal armor technology',
            'threat': 'Medium (territorial)',
        },
        'amoeba': {
            'name': 'Space Amoeba',
            'reward': 'Amoeba flagella components',
            'threat': 'Low-Medium (can be pacified)',
        },
        'cloud': {
            'name': 'Void Cloud',
            'reward': 'Cloud lightning weapon',
            'threat': 'Medium',
        },
        'drone': {
            'name': 'Mining Drones',
            'reward': 'Drone components, minerals',
            'threat': 'Low-Medium',
        },
        'ether_drake': {
            'name': 'Ether Drake',
            'reward': 'Dragon armor, Dragon trophy',
            'threat': 'Very High (25k+ fleet power)',
        },
        'dimensional_horror': {
            'name': 'Dimensional Horror',
            'reward': 'Dark matter tech, jump drive insights',
            'threat': 'Very High',
        },
        'automated_dreadnought': {
            'name': 'Automated Dreadnought',
            'reward': 'Can be captured as flagship',
            'threat': 'Very High',
        },
        'stellarite': {
            'name': 'Stellarite Devourer',
            'reward': 'Stellar energy tech',
            'threat': 'Very High',
        },
        'enigmatic_fortress': {
            'name': 'Enigmatic Fortress',
            'reward': 'Rare tech (random)',
            'threat': 'High (puzzle encounter)',
        },
        'voidspawn': {
            'name': 'Voidspawn',
            'reward': 'Unique rewards',
            'threat': 'Very High',
        },
        'wraith': {
            'name': 'Spectral Wraith',
            'reward': 'Psionic tech',
            'threat': 'High',
        },
    }

    # Country type mappings for leviathan detection via Rust parser
    LEVIATHAN_COUNTRY_TYPES = {
        'tiyanki_country': 'tiyanki',
        'crystal_country': 'crystal',
        'amoeba_country': 'amoeba',
        'cloud_country': 'cloud',
        'mining_drone_country': 'drone',
        'drone_country': 'drone',
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
        # Try Rust bridge first for faster parsing
        if RUST_BRIDGE_AVAILABLE:
            try:
                return self._get_leviathans_rust()
            except ParserError as e:
                logger.warning(f"Rust parser failed for leviathans: {e}, falling back to regex")
            except Exception as e:
                logger.warning(f"Unexpected error from Rust parser: {e}, falling back to regex")

        # Fallback: regex-based parsing
        return self._get_leviathans_regex()

    def _get_leviathans_rust(self) -> dict:
        """Get leviathan status using Rust parser.

        Uses hybrid approach:
        - Rust parser for iterating over countries to find leviathan country types
        - Regex for gamestate-wide flag searches (guardians, defeat markers)

        Returns:
            Dict with leviathan status details
        """
        result = {
            'leviathans': [],
            'total_count': 0,
            'defeated_count': 0,
            'alive_count': 0,
        }

        detected_types = set()

        # First pass: detect leviathan countries via Rust parser iteration
        for country_id, country_data in iter_section_entries(self.gamestate_path, "country"):
            if not isinstance(country_data, dict):
                continue

            ctype = country_data.get("country_type") or country_data.get("type")
            if ctype and ctype in self.LEVIATHAN_COUNTRY_TYPES:
                detected_types.add(self.LEVIATHAN_COUNTRY_TYPES[ctype])

            # Also check country name for additional identification
            name_data = country_data.get("name", {})
            if isinstance(name_data, dict):
                name_key = name_data.get("key", "").lower()
                # Check for specific leviathan name keys
                if 'tiyanki' in name_key:
                    detected_types.add('tiyanki')
                elif 'crystal' in name_key or 'prism' in name_key:
                    detected_types.add('crystal')
                elif 'amoeba' in name_key or 'spaceborne_organic' in name_key:
                    detected_types.add('amoeba')
                elif 'cloud' in name_key:
                    detected_types.add('cloud')
                elif 'mining_drone' in name_key:
                    detected_types.add('drone')

        # Second pass: detect guardians via regex (they have specific flags/markers)
        # These are the major guardians that may not have dedicated country types
        guardian_patterns = {
            'ether_drake': [
                r'ether_drake',
                r'dragon_armor',
                r'NAME_Ether_Drake',
            ],
            'dimensional_horror': [
                r'dimensional_horror',
                r'NAME_Dimensional_Horror',
            ],
            'automated_dreadnought': [
                r'automated_dreadnought',
                r'NAME_Automated_Dreadnought',
            ],
            'stellarite': [
                r'stellarite',
                r'NAME_Stellarite',
            ],
            'enigmatic_fortress': [
                r'enigmatic_fortress',
                r'NAME_Enigmatic_Fortress',
            ],
            'voidspawn': [
                r'voidspawn',
                r'NAME_Voidspawn',
            ],
            'wraith': [
                r'spectral_wraith',
                r'NAME_Spectral_Wraith',
            ],
        }

        for lev_key, patterns in guardian_patterns.items():
            for pattern in patterns:
                if re.search(pattern, self.gamestate, re.IGNORECASE):
                    detected_types.add(lev_key)
                    break

        # Build result list with status
        detected = []
        for lev_key in detected_types:
            info = self.LEVIATHAN_INFO.get(lev_key, {})
            defeated = self._check_leviathan_defeated(lev_key)

            detected.append({
                'type': lev_key,
                'name': info.get('name', lev_key.replace('_', ' ').title()),
                'status': 'defeated' if defeated else 'alive',
                'reward': info.get('reward', 'Unknown'),
                'threat': info.get('threat', 'Unknown'),
            })

        result['leviathans'] = detected
        result['total_count'] = len(detected)
        result['defeated_count'] = sum(1 for l in detected if l['status'] == 'defeated')
        result['alive_count'] = sum(1 for l in detected if l['status'] == 'alive')

        return result

    def _get_leviathans_regex(self) -> dict:
        """Get leviathan status using regex parsing (fallback method).

        Returns:
            Dict with leviathan status details
        """
        result = {
            'leviathans': [],
            'total_count': 0,
            'defeated_count': 0,
            'alive_count': 0,
        }

        detected = []

        # Check for various leviathan types via country names, flags, and markers
        leviathan_patterns = {
            'tiyanki': [
                r'name="tiyanki_country"',
                r'tiyanki_spawn_system',
                r'NAME_Placid_Leviathans',
            ],
            'crystal': [
                r'name="crystal_country"',
                r'NAME_Prism',
                r'crystal_armor',
            ],
            'amoeba': [
                r'name="amoeba_country"',
                r'amoeba_home_system',
                r'NAME_Spaceborne_Organics',
            ],
            'cloud': [
                r'name="cloud_country"',
                r'NAME_Cloud_Entity',
                r'SPACE_CLOUD_LIGHTNING',
            ],
            'drone': [
                r'mining_drone.*country',
                r'NAME_Aggressive_Mining_Drone',
            ],
            'ether_drake': [
                r'ether_drake',
                r'dragon_armor',
                r'NAME_Ether_Drake',
                r'killed_ether_drake',
            ],
            'dimensional_horror': [
                r'dimensional_horror',
                r'NAME_Dimensional_Horror',
            ],
            'automated_dreadnought': [
                r'automated_dreadnought',
                r'NAME_Automated_Dreadnought',
            ],
            'stellarite': [
                r'stellarite',
                r'NAME_Stellarite',
            ],
            'enigmatic_fortress': [
                r'enigmatic_fortress',
                r'NAME_Enigmatic_Fortress',
            ],
            'voidspawn': [
                r'voidspawn',
                r'NAME_Voidspawn',
            ],
            'wraith': [
                r'spectral_wraith',
                r'NAME_Spectral_Wraith',
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

                detected.append({
                    'type': lev_key,
                    'name': info.get('name', lev_key.replace('_', ' ').title()),
                    'status': 'defeated' if defeated else 'alive',
                    'reward': info.get('reward', 'Unknown'),
                    'threat': info.get('threat', 'Unknown'),
                })

        result['leviathans'] = detected
        result['total_count'] = len(detected)
        result['defeated_count'] = sum(1 for l in detected if l['status'] == 'defeated')
        result['alive_count'] = sum(1 for l in detected if l['status'] == 'alive')

        return result

    def _check_leviathan_defeated(self, leviathan_type: str) -> bool:
        """Check if a specific leviathan has been defeated."""

        # Common defeat flag patterns
        defeat_patterns = [
            rf'killed_{leviathan_type}',
            rf'{leviathan_type}_defeated',
            rf'{leviathan_type}_dead',
            rf'defeated_{leviathan_type}',
        ]

        for pattern in defeat_patterns:
            if re.search(pattern, self.gamestate, re.IGNORECASE):
                return True

        # Special cases
        if leviathan_type == 'ether_drake':
            if re.search(r'killed_dragon|dragon_killed|ether_drake_killed', self.gamestate, re.IGNORECASE):
                return True
            # Check for dragon trophy (indicates defeat)
            if re.search(r'relic_dragon_trophy', self.gamestate):
                return True

        if leviathan_type == 'automated_dreadnought':
            # Can be captured instead of destroyed
            if re.search(r'dreadnought_captured|owns_dreadnought', self.gamestate, re.IGNORECASE):
                return True

        if leviathan_type == 'enigmatic_fortress':
            # Fortress is "solved" not defeated
            if re.search(r'fortress_solved|enigmatic_cache', self.gamestate, re.IGNORECASE):
                return True

        return False

    def get_guardians_summary(self) -> dict:
        """Get a quick summary of guardian status for briefings.

        Returns simplified view suitable for injection into advisor context.
        """
        full = self.get_leviathans()

        # Filter to just major guardians (high threat)
        major_guardians = [
            l for l in full['leviathans']
            if 'High' in l.get('threat', '') or 'Very High' in l.get('threat', '')
        ]

        alive_names = [l['name'] for l in major_guardians if l['status'] == 'alive']
        defeated_names = [l['name'] for l in major_guardians if l['status'] == 'defeated']

        return {
            'major_guardians_alive': alive_names,
            'major_guardians_defeated': defeated_names,
            'minor_creatures_present': full['alive_count'] - len(alive_names),
        }
