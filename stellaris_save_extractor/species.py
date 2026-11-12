from __future__ import annotations

import logging

# Rust bridge for fast Clausewitz parsing (required - no fallback)
from stellaris_companion.rust_bridge import (
    ParserError,
    _get_active_session,
)
from stellaris_save_extractor.save_values import repeated

logger = logging.getLogger(__name__)


def _trait_ids(species_data: dict) -> list[str]:
    """A species' trait IDs: the ``trait`` keys of its ``traits`` block, in save order."""
    traits = species_data.get("traits")
    if not isinstance(traits, dict):
        return []
    return [str(trait) for trait in repeated(traits.get("trait"))]


class SpeciesMixin:
    """Species-related extraction methods."""

    def get_species_full(self) -> dict:
        """Get all species in the game with their traits.

        Returns:
            Dict with:
              - species: List of species with id, name, class, traits, home_planet
              - count: Total number of species
              - player_species_id: The player's founder species ID

        Raises:
            ParserError: If no Rust session is active
        """
        session = _get_active_session()
        if not session:
            raise ParserError("Rust session required for get_species_full()")

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

        species_list = []
        for species_id, species_data in session.iter_section("species_db"):
            # P010: entry might be string "none" for deleted entries
            if not isinstance(species_data, dict):
                continue

            # Skip species without class (usually empty entries)
            species_class = species_data.get("class")
            if not species_class:
                continue

            # Extract name from name block
            name_block = species_data.get("name")
            raw_name_key: str | None = None
            if isinstance(name_block, dict):
                raw_name_key = name_block.get("key")
            elif isinstance(name_block, str):
                raw_name_key = name_block

            resolved = self.resolve_name(
                name_block if name_block is not None else "",
                default="",
                context="species",
            )
            # Fallback: keep class value as-is (often short codes like MAM/REP/AVI)
            display_name = resolved.display.strip() or str(species_class)

            species_info = {
                "id": str(species_id),
                "name": display_name,
                "name_key": raw_name_key,
                "name_source": resolved.source,
                "name_confidence": resolved.confidence,
                "class": species_class,
                "portrait": species_data.get("portrait"),
                "traits": _trait_ids(species_data),
                "is_player_species": str(species_id) == result["player_species_id"],
            }

            home_planet = species_data.get("home_planet")
            if home_planet is not None:
                species_info["home_planet_id"] = str(home_planet)

            species_list.append(species_info)

        result["species"] = species_list
        result["count"] = len(species_list)

        return result

    def get_species_for_briefing(self, contacted_country_ids: set[int] | None = None) -> dict:
        """Get trimmed species data optimized for the advisor briefing.

        Instead of dumping all 600+ species (55k tokens), returns:
        - Player species in full detail
        - Founder species of each contacted empire (name + class + traits)
        - Galaxy-wide summary (total count + class breakdown)

        This covers all reasonable advisor queries at ~2-4k tokens instead of 55k.

        Args:
            contacted_country_ids: Set of country IDs the player has diplomatic
                contact with. If None, only player species + galaxy summary.

        Returns:
            Dict with player_species, known_empire_species, galaxy_summary,
            and _note for LLM data-availability awareness.
        """
        session = _get_active_session()
        if not session:
            raise ParserError("Rust session required for get_species_for_briefing()")

        # 1. Find player's founder species ID
        player_id = self.get_player_empire_id()
        country_data = self._get_player_country_entry(player_id)
        player_species_id: str | None = None
        if country_data and isinstance(country_data, dict):
            ref = country_data.get("founder_species_ref")
            if ref is not None:
                player_species_id = str(ref)

        # 2. Find contacted empires' founder species IDs
        countries = self._get_countries_cached()
        country_names = self._get_country_names_map()

        # Map: species_id -> empire_name (for labeling)
        needed_species: dict[str, str] = {}
        if player_species_id:
            needed_species[player_species_id] = country_names.get(player_id, "Player Empire")

        if contacted_country_ids:
            for cid in contacted_country_ids:
                country = countries.get(str(cid))
                if not country or not isinstance(country, dict):
                    continue
                founder_ref = country.get("founder_species_ref")
                if founder_ref is not None:
                    sid = str(founder_ref)
                    if sid not in needed_species:
                        needed_species[sid] = country_names.get(cid, f"Empire {cid}")

        # 3. Single pass of species_db: build galaxy summary + collect needed species
        species_data_list: list[dict] = []
        galaxy_class_counts: dict[str, int] = {}
        total_count = 0

        for species_id, species_data in session.iter_section("species_db"):
            if not isinstance(species_data, dict):
                continue
            species_class = species_data.get("class")
            if not species_class:
                continue

            total_count += 1
            galaxy_class_counts[species_class] = galaxy_class_counts.get(species_class, 0) + 1

            # Only store detail for needed species
            sid = str(species_id)
            if sid in needed_species:
                name_block = species_data.get("name")
                resolved = self.resolve_name(
                    name_block if name_block is not None else "",
                    default="",
                    context="species",
                )
                display_name = resolved.display.strip() or str(species_class)

                species_data_list.append(
                    {
                        "id": sid,
                        "name": display_name,
                        "class": species_class,
                        "empire": needed_species[sid],
                        "is_player_species": sid == player_species_id,
                        "traits": _trait_ids(species_data),
                    }
                )

        # 4. Build result
        player_species = None
        known_empire_species = []
        for sp in species_data_list:
            # Strip internal fields for cleaner output
            entry = {
                "name": sp["name"],
                "class": sp["class"],
                "traits": sp["traits"],
                "empire": sp["empire"],
            }
            if sp["is_player_species"]:
                player_species = entry
            else:
                known_empire_species.append(entry)

        contacted_count = len(known_empire_species)
        return {
            "player_species": player_species,
            "known_empire_species": known_empire_species,
            "galaxy_summary": {
                "total_species_in_galaxy": total_count,
                "by_class": galaxy_class_counts,
            },
            "_note": (
                f"Species data covers your empire and {contacted_count} "
                f"diplomatically contacted empires in detail. "
                f"The galaxy has {total_count} total species across "
                f"{len(galaxy_class_counts)} classes — individual traits for "
                f"uncontacted or gene-modded subspecies are not included."
            ),
        }

    def get_species_rights(self) -> dict:
        """Get species rights settings for the player empire.

        Uses fast path via _get_player_country_entry() for parsed data access.

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
        country_entry = self._get_player_country_entry(player_id)
        if not country_entry or not isinstance(country_entry, dict):
            return result

        # Extract species_rights from parsed dict
        species_rights = country_entry.get("species_rights")
        if not species_rights:
            return result

        # Handle both list and single dict
        rights_entries = species_rights if isinstance(species_rights, list) else [species_rights]

        rights_list = []

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

        for entry in rights_entries:
            if not isinstance(entry, dict):
                continue

            species_index = entry.get("species_index")
            if species_index is None:
                continue

            rights_info = {
                "species_index": str(species_index),
            }

            # Extract all rights fields from parsed entry
            for field in rights_fields:
                value = entry.get(field)
                if value is not None:
                    rights_info[field] = str(value)

            rights_list.append(rights_info)

        result["rights"] = rights_list
        result["count"] = len(rights_list)

        return result
