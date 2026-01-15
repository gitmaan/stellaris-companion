from __future__ import annotations

import re


class EndgameMixin:
    """Extractors for endgame content: Crisis, L-Gates, Become the Crisis."""

    def get_crisis_status(self) -> dict:
        """Get current crisis status and player involvement.

        Detects active crisis factions (Prethoryn, Contingency, Unbidden) and
        tracks player's role in fighting or becoming the crisis.

        Returns:
            Dict with:
              - crisis_active: Whether a crisis has spawned
              - crisis_type: Type of crisis (prethoryn, contingency, unbidden, etc.)
              - crisis_countries: List of crisis faction country IDs
              - player_is_crisis_fighter: Whether player has crisis_fighter flag
              - player_crisis_kills: Number of crisis ships/armies killed
              - crisis_systems: Count of systems flagged as crisis-controlled
        """
        result = {
            'crisis_active': False,
            'crisis_type': None,
            'crisis_types_detected': [],
            'crisis_countries': [],
            'player_is_crisis_fighter': False,
            'player_crisis_kills': 0,
            'crisis_systems_count': 0,
        }

        # Crisis country type mappings
        CRISIS_TYPES = {
            'swarm': 'prethoryn',
            'extradimensional': 'unbidden',
            'extradimensional_2': 'aberrant',
            'extradimensional_3': 'vehement',
            'ai_empire_01': 'contingency',  # Contingency uses special country type
        }

        # Detect crisis countries by country_type
        crisis_countries = []
        crisis_types_found = set()

        # Search for crisis country types
        for crisis_type_key, crisis_name in CRISIS_TYPES.items():
            pattern = rf'country_type="{re.escape(crisis_type_key)}"'
            if re.search(pattern, self.gamestate):
                crisis_types_found.add(crisis_name)

        # Also check for swarm via type="swarm" (alternate format)
        if re.search(r'\btype="swarm"', self.gamestate):
            crisis_types_found.add('prethoryn')

        # Check for contingency via contingency_bot species or contingency data
        if re.search(r'contingency_bot|data="contingency_', self.gamestate):
            crisis_types_found.add('contingency')

        # Check for extradimensional via related tech/species
        if re.search(r'extradimensional_weapon|type="extradimensional"', self.gamestate):
            crisis_types_found.add('unbidden')

        # Find crisis country IDs
        country_section_start = self._find_country_section_start()
        if country_section_start != -1:
            country_chunk = self.gamestate[country_section_start:country_section_start + 50000000]

            # Find countries with crisis types
            for match in re.finditer(r'\n\t(\d+)=\n\t\{', country_chunk):
                country_id = int(match.group(1))
                start = match.start()

                # Get a reasonable chunk of this country
                end = start + 50000
                block = country_chunk[start:end]

                # Check if this is a crisis country
                type_match = re.search(r'\btype="([^"]+)"', block[:5000])
                if type_match:
                    ctype = type_match.group(1)
                    if ctype in CRISIS_TYPES or ctype in ['swarm', 'extradimensional']:
                        crisis_countries.append({
                            'country_id': country_id,
                            'type': CRISIS_TYPES.get(ctype, ctype),
                        })

        result['crisis_countries'] = crisis_countries
        result['crisis_types_detected'] = list(crisis_types_found)
        result['crisis_active'] = len(crisis_types_found) > 0
        if crisis_types_found:
            # Primary crisis type (prioritize main ones)
            for primary in ['prethoryn', 'contingency', 'unbidden']:
                if primary in crisis_types_found:
                    result['crisis_type'] = primary
                    break
            if not result['crisis_type']:
                result['crisis_type'] = list(crisis_types_found)[0]

        # Check player's crisis involvement
        player_id = self.get_player_empire_id()
        player_chunk = self._find_player_country_content(player_id)
        if player_chunk:
            # Check for crisis_fighter flag
            if 'crisis_fighter=yes' in player_chunk:
                result['player_is_crisis_fighter'] = True

            # Check for crisis_kills count
            kills_match = re.search(r'\bcrisis_kills=(\d+)', player_chunk)
            if kills_match:
                result['player_crisis_kills'] = int(kills_match.group(1))

        # Count crisis-controlled systems via flags
        crisis_system_flags = [
            'lost_swarm_system',
            'hostile_system',
            'contingency_system',
        ]
        total_crisis_systems = 0
        for flag in crisis_system_flags:
            total_crisis_systems += len(re.findall(rf'\b{flag}=', self.gamestate))

        result['crisis_systems_count'] = total_crisis_systems

        return result

    def get_lgate_status(self) -> dict:
        """Get L-Gate and L-Cluster status.

        Tracks L-Gate insights collected and whether the L-Cluster has been opened.

        Returns:
            Dict with:
              - lgate_enabled: Whether L-Gates exist in this galaxy
              - insights_collected: Number of L-Gate insights (from tech_repeatable_lcluster_clue)
              - insights_required: Usually 7 to open
              - lgate_opened: Whether L-Cluster has been accessed
              - player_activation_progress: Tech progress toward activation (0-100)
        """
        result = {
            'lgate_enabled': False,
            'insights_collected': 0,
            'insights_required': 7,  # Standard requirement
            'lgate_opened': False,
            'player_activation_progress': 0,
        }

        # Check if L-Gates are enabled in galaxy settings
        if 'lgate_enabled=yes' in self.gamestate:
            result['lgate_enabled'] = True
        elif 'lgate_enabled=no' in self.gamestate:
            result['lgate_enabled'] = False
            return result  # No point checking further

        # Get player's L-Gate insights from tech_repeatable_lcluster_clue
        player_id = self.get_player_empire_id()
        player_chunk = self._find_player_country_content(player_id)

        if player_chunk:
            # Look for tech_repeatable_lcluster_clue in technology section
            tech_block = self._extract_braced_block(player_chunk, 'tech_status')
            if tech_block:
                # Find the repeatable tech entry
                clue_match = re.search(
                    r'technology="tech_repeatable_lcluster_clue"[^}]*level=(\d+)',
                    tech_block
                )
                if clue_match:
                    result['insights_collected'] = int(clue_match.group(1))

            # Check for activation tech progress
            # This appears in potential={} section as "tech_lgate_activation"="XX"
            potential_match = re.search(
                r'"tech_lgate_activation"="(\d+)"',
                player_chunk
            )
            if potential_match:
                result['player_activation_progress'] = int(potential_match.group(1))

        # Check if L-Gate has been opened (look for L-Cluster access)
        # When opened, there will be bypass connections to the L-Cluster
        # Or we can check for gray_tempest/lcluster related flags
        if re.search(r'lcluster_|l_cluster_opened|gray_tempest_country', self.gamestate):
            result['lgate_opened'] = True

        # Also check if player has the activation tech completed
        if player_chunk:
            if 'tech_lgate_activation' in player_chunk:
                tech_section = self._extract_braced_block(player_chunk, 'technology')
                if tech_section and '"tech_lgate_activation"' in tech_section:
                    # Check if it's in completed techs (not just potential)
                    completed_block = self._extract_braced_block(tech_section, 'completed')
                    if completed_block and 'tech_lgate_activation' in completed_block:
                        result['lgate_opened'] = True

        return result

    def get_menace(self) -> dict:
        """Get Become the Crisis status for the player.

        Tracks menace level and crisis ascension progress if player has
        the ap_become_the_crisis ascension perk.

        Returns:
            Dict with:
              - has_crisis_perk: Whether player has Become the Crisis perk
              - menace_level: Current menace accumulated
              - crisis_level: Crisis ascension tier (0-5)
        """
        result = {
            'has_crisis_perk': False,
            'menace_level': 0,
            'crisis_level': 0,
        }

        player_id = self.get_player_empire_id()
        player_chunk = self._find_player_country_content(player_id)

        if not player_chunk:
            return result

        # Check for Become the Crisis ascension perk
        ascension_block = self._extract_braced_block(player_chunk, 'ascension_perks')
        if ascension_block:
            if 'ap_become_the_crisis' in ascension_block:
                result['has_crisis_perk'] = True

        # If they have the perk, look for menace tracking
        if result['has_crisis_perk']:
            # Menace is stored in the country block
            menace_match = re.search(r'\bmenace=(\d+)', player_chunk)
            if menace_match:
                result['menace_level'] = int(menace_match.group(1))

            # Crisis level/tier
            crisis_level_match = re.search(r'\bcrisis_level=(\d+)', player_chunk)
            if crisis_level_match:
                result['crisis_level'] = int(crisis_level_match.group(1))

        return result

    def get_great_khan(self) -> dict:
        """Get Great Khan / Marauder status.

        The Great Khan is a mid-game crisis where marauder clans unify under
        a single leader and begin conquering the galaxy.

        Returns:
            Dict with:
              - marauders_present: Whether marauder empires exist
              - marauder_count: Number of marauder factions
              - khan_risen: Whether the Great Khan has spawned
              - khan_status: Current state (active, defeated, etc.)
              - khan_country_id: Country ID of the Khan's empire if active
        """
        result = {
            'marauders_present': False,
            'marauder_count': 0,
            'khan_risen': False,
            'khan_status': None,
            'khan_country_id': None,
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
                result['marauders_present'] = True
                marauder_count += len(matches)

        # Dedupe - NAME_Marauder appears multiple times per empire
        # Estimate actual marauder empires (usually 1-3)
        if marauder_count > 0:
            result['marauder_count'] = min(marauder_count, 3)  # Cap at realistic number

        # Check for Great Khan rising
        # The Khan has specific country type and event flags
        khan_patterns = [
            (r'type="awakened_marauders"', 'active'),
            (r'type="marauder_empire"', 'active'),
            (r'great_khan_risen', 'active'),
            (r'great_khan=yes', 'active'),
            (r'khan_country', 'active'),
        ]

        for pattern, status in khan_patterns:
            if re.search(pattern, self.gamestate):
                result['khan_risen'] = True
                result['khan_status'] = status
                break

        # Check for Khan defeated
        khan_defeated_patterns = [
            r'great_khan_dead',
            r'great_khan_defeated',
            r'khan_successor',  # Khan died, successors fighting
        ]

        for pattern in khan_defeated_patterns:
            if re.search(pattern, self.gamestate):
                result['khan_risen'] = True  # Was risen at some point
                result['khan_status'] = 'defeated'
                break

        # Try to find Khan's country ID if active
        if result['khan_risen'] and result['khan_status'] == 'active':
            # Look for awakened_marauders country
            country_section_start = self._find_country_section_start()
            if country_section_start != -1:
                country_chunk = self.gamestate[country_section_start:country_section_start + 10000000]

                for match in re.finditer(r'\n\t(\d+)=\n\t\{', country_chunk):
                    country_id = int(match.group(1))
                    start = match.start()
                    block = country_chunk[start:start + 5000]

                    if 'type="awakened_marauders"' in block or 'type="marauder_empire"' in block:
                        result['khan_country_id'] = country_id
                        break

        return result
