from __future__ import annotations

import re


class SpeciesMixin:
    """Species-related extraction methods."""

    def get_species_full(self) -> dict:
        """Get all species in the game with their traits.

        Returns:
            Dict with:
              - species: List of species with id, name, class, traits, home_planet
              - count: Total number of species
              - player_species_id: The player's founder species ID
        """
        result = {
            'species': [],
            'count': 0,
            'player_species_id': None,
        }

        # Find player's founder species
        player_id = self.get_player_empire_id()
        country_content = self._find_player_country_content(player_id)
        if country_content:
            founder_match = re.search(r'founder_species_ref=(\d+)', country_content)
            if founder_match:
                result['player_species_id'] = founder_match.group(1)

        # Find species_db section
        species_start = self.gamestate.find('\nspecies_db=')
        if species_start == -1:
            species_start = self.gamestate.find('species_db=')
        if species_start == -1:
            return result

        # Get the species section
        species_section = self.gamestate[species_start:species_start + 2000000]

        # Parse individual species entries
        entry_pattern = r'\n\t(\d+)=\s*\{'
        entries = list(re.finditer(entry_pattern, species_section))

        species_list = []

        for i, match in enumerate(entries[:200]):  # Cap at 200 species
            species_id = match.group(1)
            start_pos = match.end()

            # Find end of block using brace matching
            brace_count = 1
            pos = start_pos
            max_pos = min(start_pos + 5000, len(species_section))
            while brace_count > 0 and pos < max_pos:
                if species_section[pos] == '{':
                    brace_count += 1
                elif species_section[pos] == '}':
                    brace_count -= 1
                pos += 1

            block = species_section[start_pos:pos]

            # Skip empty species entries (id=0 is usually empty)
            if len(block.strip()) < 20:
                continue

            # Extract fields
            name_match = re.search(r'\bkey="([^"]+)"', block)
            if not name_match:
                # Try alternate name format
                name_match = re.search(r'name=\s*\{\s*key="([^"]+)"', block)

            class_match = re.search(r'\bclass="([^"]+)"', block)
            portrait_match = re.search(r'\bportrait="([^"]+)"', block)
            home_planet_match = re.search(r'\bhome_planet=(\d+)', block)

            # Extract traits
            traits = []
            traits_block = re.search(r'traits=\s*\{([^}]+)\}', block)
            if traits_block:
                trait_matches = re.findall(r'trait="([^"]+)"', traits_block.group(1))
                traits = trait_matches

            # Skip species with no meaningful data
            if not class_match and not traits:
                continue

            species_info = {
                'id': species_id,
                'name': name_match.group(1) if name_match else None,
                'class': class_match.group(1) if class_match else None,
                'portrait': portrait_match.group(1) if portrait_match else None,
                'traits': traits,
                'is_player_species': species_id == result['player_species_id'],
            }

            if home_planet_match:
                species_info['home_planet_id'] = home_planet_match.group(1)

            species_list.append(species_info)

        result['species'] = species_list
        result['count'] = len(species_list)

        return result

    def get_species_rights(self) -> dict:
        """Get species rights settings for the player empire.

        Returns:
            Dict with:
              - rights: List of species rights configurations
              - count: Number of species with custom rights
        """
        result = {
            'rights': [],
            'count': 0,
        }

        player_id = self.get_player_empire_id()
        country_content = self._find_player_country_content(player_id)
        if not country_content:
            return result

        # Find species_rights block
        rights_start = country_content.find('species_rights=')
        if rights_start == -1:
            return result

        # Get a chunk around species_rights
        rights_chunk = country_content[rights_start:rights_start + 50000]

        # Find the species_rights block
        brace_pos = rights_chunk.find('{')
        if brace_pos == -1:
            return result

        brace_count = 1
        pos = brace_pos + 1
        while brace_count > 0 and pos < len(rights_chunk):
            if rights_chunk[pos] == '{':
                brace_count += 1
            elif rights_chunk[pos] == '}':
                brace_count -= 1
            pos += 1

        rights_block = rights_chunk[brace_pos:pos]

        # Parse individual species rights entries
        # Each entry is: { species_index=X citizenship="Y" ... }
        entry_pattern = r'\{\s*species_index=(\d+)'
        entries = list(re.finditer(entry_pattern, rights_block))

        rights_list = []

        for match in entries[:50]:  # Cap at 50 species rights
            species_index = match.group(1)
            start_pos = match.start()

            # Find end of this entry
            entry_brace_count = 1
            epos = match.end()
            while entry_brace_count > 0 and epos < len(rights_block):
                if rights_block[epos] == '{':
                    entry_brace_count += 1
                elif rights_block[epos] == '}':
                    entry_brace_count -= 1
                epos += 1

            entry_block = rights_block[start_pos:epos]

            # Extract rights settings
            rights_info = {
                'species_index': species_index,
            }

            # Common rights fields
            rights_fields = [
                'citizenship', 'living_standard', 'military_service',
                'slavery', 'purge', 'population_control',
                'colonization_control', 'migration_control'
            ]

            for field in rights_fields:
                field_match = re.search(rf'{field}="([^"]+)"', entry_block)
                if field_match:
                    rights_info[field] = field_match.group(1)

            rights_list.append(rights_info)

        result['rights'] = rights_list
        result['count'] = len(rights_list)

        return result
