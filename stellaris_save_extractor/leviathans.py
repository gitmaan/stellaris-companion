from __future__ import annotations

import re


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

    def get_leviathans(self) -> dict:
        """Get status of Leviathans and Guardians in the galaxy.

        Returns:
            Dict with:
              - leviathans: List of detected leviathans with status
              - total_count: Number of leviathan types detected
              - defeated_count: Number defeated by player
              - alive_count: Number still active
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
