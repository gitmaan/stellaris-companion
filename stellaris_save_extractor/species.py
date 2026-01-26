from __future__ import annotations

import logging
import re

# Rust bridge for Clausewitz parsing (required for session mode)
from rust_bridge import iter_section_entries

logger = logging.getLogger(__name__)


class SpeciesMixin:
    """Species-related extraction methods."""

    def get_species_full(self) -> dict:
        """Get all species in the game with their traits.

        Uses Rust parser for iteration and structured data, with regex
        for traits extraction (due to duplicate key issue in Clausewitz format).

        Returns:
            Dict with:
              - species: List of species with id, name, class, traits, home_planet
              - count: Total number of species
              - player_species_id: The player's founder species ID
        """
        return self._get_species_full_rust()

    def _get_species_full_rust(self) -> dict:
        """Get species using Rust parser.

        Uses hybrid approach: Rust parser for iteration and structured data
        (name, class, portrait, home_planet), but regex for traits extraction
        because the Clausewitz format has duplicate keys (trait="x" repeated)
        which the Rust parser doesn't handle correctly (only keeps last value).

        Returns:
            Dict with species data
        """
        result = {
            "species": [],
            "count": 0,
            "player_species_id": None,
        }

        # Find player's founder species using cached player country entry
        player_id = self.get_player_empire_id()
        country_data = self._get_player_country_entry(player_id)
        if country_data and isinstance(country_data, dict):
            founder_ref = country_data.get("founder_species_ref")
            if founder_ref is not None:
                result["player_species_id"] = str(founder_ref)

        # Build a map of species_id -> traits using regex
        # (Rust parser only keeps last trait due to duplicate keys)
        species_traits = self._extract_species_traits_regex()

        species_list = []

        # Iterate species using Rust parser
        for species_id, species_data in iter_section_entries(self.save_path, "species_db"):
            # Skip empty species entries
            if not species_data or len(species_data) < 2:
                continue

            # Skip species without class (usually empty entries)
            species_class = species_data.get("class")
            if not species_class:
                continue

            # Extract name from name block
            name = None
            name_block = species_data.get("name")
            if isinstance(name_block, dict):
                name = name_block.get("key")
            elif isinstance(name_block, str):
                name = name_block

            # Get portrait
            portrait = species_data.get("portrait")

            # Get home planet
            home_planet = species_data.get("home_planet")

            # Get traits from regex extraction (more complete than Rust)
            traits = species_traits.get(str(species_id), [])

            species_info = {
                "id": str(species_id),
                "name": name,
                "class": species_class,
                "portrait": portrait,
                "traits": traits,
                "is_player_species": str(species_id) == result["player_species_id"],
            }

            if home_planet is not None:
                species_info["home_planet_id"] = str(home_planet)

            species_list.append(species_info)

        result["species"] = species_list
        result["count"] = len(species_list)

        return result

    def _find_species_db_section(self) -> str:
        """Find and extract the species_db section with proper boundaries.

        Returns:
            The species_db section content, or empty string if not found
        """
        # Find species_db section
        species_start = self.gamestate.find("\nspecies_db=")
        if species_start == -1:
            species_start = self.gamestate.find("species_db=")
        if species_start == -1:
            return ""

        # Find the end of species_db section using brace matching
        chunk = self.gamestate[species_start:]
        brace_count = 0
        started = False
        end_pos = 0
        for i, char in enumerate(chunk):
            if char == "{":
                brace_count += 1
                started = True
            elif char == "}":
                brace_count -= 1
                if started and brace_count == 0:
                    end_pos = i + 1
                    break

        return self.gamestate[species_start : species_start + end_pos]

    def _extract_species_traits_regex(self) -> dict:
        """Extract traits for all species using regex.

        The Rust parser can't handle duplicate keys (trait="x" repeated),
        so we extract traits with regex from the species_db section.

        Returns:
            Dict mapping species ID to list of trait names
        """
        species_traits = {}

        # Get properly bounded species_db section
        species_section = self._find_species_db_section()
        if not species_section:
            return species_traits

        # Parse individual species entries
        entry_pattern = r"\n\t(\d+)=\s*\{"
        entries = list(re.finditer(entry_pattern, species_section))

        for i, match in enumerate(entries):
            species_id = match.group(1)
            start_pos = match.end()

            # Find end of block using brace matching
            brace_count = 1
            pos = start_pos
            max_pos = min(start_pos + 5000, len(species_section))
            while brace_count > 0 and pos < max_pos:
                if species_section[pos] == "{":
                    brace_count += 1
                elif species_section[pos] == "}":
                    brace_count -= 1
                pos += 1

            block = species_section[start_pos:pos]

            # Extract traits
            traits = []
            traits_block = re.search(r"traits=\s*\{([^}]+)\}", block)
            if traits_block:
                trait_matches = re.findall(r'trait="([^"]+)"', traits_block.group(1))
                traits = trait_matches

            if traits:
                species_traits[species_id] = traits

        return species_traits

    def _get_species_full_regex(self) -> dict:
        """Get species using regex parsing (fallback method).

        Returns:
            Dict with species data
        """
        result = {
            "species": [],
            "count": 0,
            "player_species_id": None,
        }

        # Find player's founder species
        player_id = self.get_player_empire_id()
        country_content = self._find_player_country_content(player_id)
        if country_content:
            founder_match = re.search(r"founder_species_ref=(\d+)", country_content)
            if founder_match:
                result["player_species_id"] = founder_match.group(1)

        # Get properly bounded species_db section
        species_section = self._find_species_db_section()
        if not species_section:
            return result

        # Parse individual species entries
        entry_pattern = r"\n\t(\d+)=\s*\{"
        entries = list(re.finditer(entry_pattern, species_section))

        species_list = []

        # Process all species - modded games can have 500+ species types
        for i, match in enumerate(entries):
            species_id = match.group(1)
            start_pos = match.end()

            # Find end of block using brace matching
            brace_count = 1
            pos = start_pos
            max_pos = min(start_pos + 5000, len(species_section))
            while brace_count > 0 and pos < max_pos:
                if species_section[pos] == "{":
                    brace_count += 1
                elif species_section[pos] == "}":
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
            home_planet_match = re.search(r"\bhome_planet=(\d+)", block)

            # Extract traits
            traits = []
            traits_block = re.search(r"traits=\s*\{([^}]+)\}", block)
            if traits_block:
                trait_matches = re.findall(r'trait="([^"]+)"', traits_block.group(1))
                traits = trait_matches

            # Skip species with no meaningful data
            if not class_match and not traits:
                continue

            species_info = {
                "id": species_id,
                "name": name_match.group(1) if name_match else None,
                "class": class_match.group(1) if class_match else None,
                "portrait": portrait_match.group(1) if portrait_match else None,
                "traits": traits,
                "is_player_species": species_id == result["player_species_id"],
            }

            if home_planet_match:
                species_info["home_planet_id"] = home_planet_match.group(1)

            species_list.append(species_info)

        result["species"] = species_list
        result["count"] = len(species_list)

        return result

    def get_species_rights(self) -> dict:
        """Get species rights settings for the player empire.

        Returns:
            Dict with:
              - rights: List of species rights configurations
              - count: Number of species with custom rights
        """
        result = {
            "rights": [],
            "count": 0,
        }

        player_id = self.get_player_empire_id()
        country_content = self._find_player_country_content(player_id)
        if not country_content:
            return result

        # Find species_rights block
        rights_start = country_content.find("species_rights=")
        if rights_start == -1:
            return result

        # Get a chunk around species_rights
        rights_chunk = country_content[rights_start : rights_start + 50000]

        # Find the species_rights block
        brace_pos = rights_chunk.find("{")
        if brace_pos == -1:
            return result

        brace_count = 1
        pos = brace_pos + 1
        while brace_count > 0 and pos < len(rights_chunk):
            if rights_chunk[pos] == "{":
                brace_count += 1
            elif rights_chunk[pos] == "}":
                brace_count -= 1
            pos += 1

        rights_block = rights_chunk[brace_pos:pos]

        # Parse individual species rights entries
        # Each entry is: { species_index=X citizenship="Y" ... }
        entry_pattern = r"\{\s*species_index=(\d+)"
        entries = list(re.finditer(entry_pattern, rights_block))

        rights_list = []

        # Process all species rights - empires with many subspecies/templates can exceed 50
        for match in entries:
            species_index = match.group(1)
            start_pos = match.start()

            # Find end of this entry
            entry_brace_count = 1
            epos = match.end()
            while entry_brace_count > 0 and epos < len(rights_block):
                if rights_block[epos] == "{":
                    entry_brace_count += 1
                elif rights_block[epos] == "}":
                    entry_brace_count -= 1
                epos += 1

            entry_block = rights_block[start_pos:epos]

            # Extract rights settings
            rights_info = {
                "species_index": species_index,
            }

            # Common rights fields
            rights_fields = [
                "citizenship",
                "living_standard",
                "military_service",
                "slavery",
                "purge",
                "population_control",
                "colonization_control",
                "migration_control",
            ]

            for field in rights_fields:
                field_match = re.search(rf'{field}="([^"]+)"', entry_block)
                if field_match:
                    rights_info[field] = field_match.group(1)

            rights_list.append(rights_info)

        result["rights"] = rights_list
        result["count"] = len(rights_list)

        return result
