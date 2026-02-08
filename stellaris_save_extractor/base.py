from __future__ import annotations

import io
import logging
import re
import zipfile
from pathlib import Path

# Rust bridge for Clausewitz parsing (required for session mode)
from stellaris_companion.rust_bridge import (
    ParserError,
    _get_active_session,
    extract_sections,
    iter_section_entries,
)

from .name_resolution import ResolvedName
from .name_resolution import resolve_name as _resolve_name

logger = logging.getLogger(__name__)


class SaveExtractorBase:
    """Base implementation: file I/O, caches, and shared parsing helpers."""

    _MAX_CACHED_SECTION_CHARS = 2_000_000

    def __init__(self, save_path: str):
        """Load and parse a Stellaris save file.

        Args:
            save_path: Path to the .sav file
        """
        self.save_path = Path(save_path)
        self._meta: str | None = None
        self._gamestate: str | None = None
        self._load_meta()

        # Cache for parsed sections
        self._section_cache: dict[str, str | None] = {}
        self._section_bounds_cache: dict[str, tuple[int, int] | None] = {}
        self._building_types = None  # Lazy-loaded building ID→type map
        self._country_names = None  # Lazy-loaded country ID→name map
        self._country_authorities = None  # Lazy-loaded country ID→authority map
        self._country_ethics = None  # Lazy-loaded country ID→ethics list map
        self._countries_cache = None  # Lazy-loaded full country section cache
        self._galactic_objects_cache = None  # Lazy-loaded galactic_object section cache
        self._fleets_cache = None  # Lazy-loaded fleet section cache
        self._pop_groups_cache = None  # Lazy-loaded pop_groups section cache
        self._planet_names = None  # Lazy-loaded planet ID→name map
        self._planets_cache = None  # Lazy-loaded get_planets() result
        self._system_owner_map_cache = None  # Lazy-loaded system_id->owner country_id map
        self._player_status_cache = None  # Cached player status (expensive to compute)
        self._player_country_entry_cache = None  # Cached player country from Rust get_entry
        self._player_country_content_cache = None  # Cached player country string content

    def close(self) -> None:
        """Release large in-memory state (best-effort)."""
        self.release_gamestate()

    def release_gamestate(self) -> None:
        """Free the extracted gamestate and any dependent caches."""
        self._gamestate = None
        self._section_cache.clear()
        self._section_bounds_cache.clear()
        self._building_types = None
        self._country_names = None
        self._country_authorities = None
        self._country_ethics = None
        self._countries_cache = None
        self._galactic_objects_cache = None
        self._fleets_cache = None
        self._pop_groups_cache = None
        self._planet_names = None
        self._planets_cache = None
        self._system_owner_map_cache = None
        self._player_status_cache = None
        self._player_country_entry_cache = None
        self._player_country_content_cache = None

    def __enter__(self) -> SaveExtractorBase:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @property
    def meta(self) -> str:
        if self._meta is None:
            self._load_meta()
        return self._meta or ""

    @meta.setter
    def meta(self, value: str | None) -> None:
        self._meta = value

    @property
    def gamestate(self) -> str:
        if self._gamestate is None:
            self._load_gamestate()
        return self._gamestate or ""

    @gamestate.setter
    def gamestate(self, value: str | None) -> None:
        self._gamestate = value

    @property
    def gamestate_path(self) -> Path:
        """Path to the save file for Rust bridge integration.

        The Rust parser expects .sav file paths to extract sections directly.
        This is an alias for save_path for compatibility with the rust_bridge module API.
        """
        return self.save_path

    def _get_building_types(self) -> dict:
        """Parse the global buildings section to get ID→type mapping.

        Uses Rust bridge for fast parsing when available, falls back to regex.

        Returns:
            Dict mapping building IDs (as strings) to building type names
        """
        if self._building_types is not None:
            return self._building_types

        self._building_types = {}

        # Use Rust bridge for parsing (session mode required)
        sections = extract_sections(self.gamestate_path, ["buildings"])
        buildings = sections.get("buildings", {})
        self._building_types = {
            bid: data.get("type")
            for bid, data in buildings.items()
            if isinstance(data, dict) and "type" in data
        }
        return self._building_types

    def _load_meta(self) -> None:
        """Extract meta from the save file (cheap, used for Tier 0 status)."""
        with zipfile.ZipFile(self.save_path, "r") as z, z.open("meta") as raw:
            with io.TextIOWrapper(raw, encoding="utf-8", errors="replace") as text:
                self._meta = text.read()

    def _load_gamestate(self) -> None:
        """Extract the full gamestate from the save file (expensive)."""
        with zipfile.ZipFile(self.save_path, "r") as z, z.open("gamestate") as raw:
            with io.TextIOWrapper(raw, encoding="utf-8", errors="replace") as text:
                self._gamestate = text.read()

    def _get_section_bounds(self, section_name: str) -> tuple[int, int] | None:
        """Get cached (start, end) bounds for a top-level section."""
        if section_name in self._section_bounds_cache:
            return self._section_bounds_cache[section_name]
        bounds = self._find_section_bounds(section_name)
        self._section_bounds_cache[section_name] = bounds
        return bounds

    def _find_section_bounds(self, section_name: str) -> tuple[int, int] | None:
        """Find the start and end positions of a top-level section.

        Args:
            section_name: Name of section (e.g., 'country', 'wars', 'fleets')

        Returns:
            Tuple of (start, end) positions, or None if not found
        """
        # Look for "section_name={" or "section_name ={" at start of line
        pattern = rf"^{re.escape(section_name)}\s*=\s*\{{"
        match = re.search(pattern, self.gamestate, re.MULTILINE)

        if not match:
            return None

        start = match.start()

        # Find matching closing brace
        brace_count = 0
        in_section = False

        for i, char in enumerate(self.gamestate[start:], start):
            if char == "{":
                brace_count += 1
                in_section = True
            elif char == "}":
                brace_count -= 1
                if in_section and brace_count == 0:
                    return (start, i + 1)

        return None

    def _extract_section(self, section_name: str) -> str | None:
        """Extract a complete top-level section.

        Args:
            section_name: Name of section to extract

        Returns:
            Section content as string, or None if not found
        """
        if section_name in self._section_cache:
            return self._section_cache[section_name]

        bounds = self._get_section_bounds(section_name)
        if bounds:
            content = self.gamestate[bounds[0] : bounds[1]]
            if len(content) <= self._MAX_CACHED_SECTION_CHARS:
                self._section_cache[section_name] = content
            return content
        return None

    def _extract_nested_block(self, content: str, key: str, value: str) -> str | None:
        """Extract a nested block where key=value.

        Args:
            content: Text to search in
            key: Key to match (e.g., 'name')
            value: Value to match (e.g., 'United Nations of Earth')

        Returns:
            The containing block, or None
        """
        # Find the value
        pattern = rf'{key}\s*=\s*"{re.escape(value)}"'
        match = re.search(pattern, content)

        if not match:
            return None

        # Walk backwards to find the opening brace of the containing block
        pos = match.start()
        brace_count = 0
        block_start = 0

        for i in range(pos, -1, -1):
            if content[i] == "}":
                brace_count += 1
            elif content[i] == "{":
                if brace_count == 0:
                    # Find the key before this brace
                    block_start = content.rfind("\n", 0, i) + 1
                    break
                brace_count -= 1

        # Now find the matching closing brace
        brace_count = 0
        for i in range(block_start, len(content)):
            if content[i] == "{":
                brace_count += 1
            elif content[i] == "}":
                brace_count -= 1
                if brace_count == 0:
                    return content[block_start : i + 1]

        return None

    def _find_country_section_start(self) -> int:
        """Find the start of the country={} block (not country=0 simple value).

        The gamestate has both:
        - country=0 (simple value near start, ~line 10)
        - country=\\n{\\n\\t0=... (actual countries block, deep in file)

        Returns:
            Position of 'country=' for the block, or -1 if not found
        """
        bounds = self._get_section_bounds("country")
        if not bounds:
            return -1
        return bounds[0]

    def _find_player_country_content(self, player_id: int = 0) -> str | None:
        """Get the content of the player's country block.

        Results are cached since this is an expensive operation and the
        player country content doesn't change within a single analysis.

        Args:
            player_id: The player's country ID (usually 0)

        Returns:
            String content of the country block, or None if not found
        """
        # Return cached result if available
        if self._player_country_content_cache is not None:
            return self._player_country_content_cache

        bounds = self._get_section_bounds("country")
        if not bounds:
            return None

        country_start, country_end = bounds

        # Search near the start of the country section (player entries are early).
        search_end = min(country_end, country_start + 10_000_000)
        entry_re = re.compile(rf"(?m)^\t{player_id}\s*=\s*\{{")
        match = entry_re.search(self.gamestate, country_start, search_end)
        if not match:
            return None

        start = match.start()
        brace_count = 0
        started = False

        for i, ch in enumerate(self.gamestate[start:country_end], start):
            if ch == "{":
                brace_count += 1
                started = True
            elif ch == "}":
                brace_count -= 1
                if started and brace_count == 0:
                    result = self.gamestate[start : i + 1]
                    self._player_country_content_cache = result
                    return result

        return None

    def _get_player_country_entry(self, player_id: int = 0) -> dict | None:
        """Get the player's country entry as a parsed dict using Rust get_entry.

        This is much faster than _find_player_country_content (0.004s vs 0.45s)
        when a Rust session is active. Results are cached.

        Args:
            player_id: The player's country ID (usually 0)

        Returns:
            Parsed country dict if found, None otherwise.
            Note: Returns None if no active session (use _find_player_country_content instead).
        """
        # Return cached result if available
        if self._player_country_entry_cache is not None:
            return self._player_country_entry_cache

        session = _get_active_session()
        if not session:
            return None

        entry = session.get_entry("country", str(player_id))
        if entry and isinstance(entry, dict):
            self._player_country_entry_cache = entry
            return entry

        return None

    def _get_owned_fleet_ids_from_entry(self, country_entry: dict) -> list[str]:
        """Extract owned fleet IDs from a parsed country dict.

        This is the fast path (works with Rust get_entry output).
        Use this instead of _get_owned_fleet_ids() when you have the parsed dict.

        Args:
            country_entry: Parsed country dict from session.get_entry()

        Returns:
            List of fleet ID strings that the country owns
        """
        if not isinstance(country_entry, dict):
            return []

        fleets_mgr = country_entry.get("fleets_manager", {})
        if not isinstance(fleets_mgr, dict):
            return []

        owned_fleets_data = fleets_mgr.get("owned_fleets", [])
        if not isinstance(owned_fleets_data, list):
            return []

        fleet_ids = []
        for entry in owned_fleets_data:
            if isinstance(entry, dict):
                fleet_id = entry.get("fleet")
                if fleet_id is not None:
                    fleet_ids.append(str(fleet_id))

        return fleet_ids

    def _find_fleet_section_start(self) -> int:
        """Find the start of the fleet={} block.

        Returns:
            Position of 'fleet=' for the block, or -1 if not found
        """
        bounds = self._get_section_bounds("fleet")
        if not bounds:
            return -1
        return bounds[0]

    def _get_owned_fleet_ids(self, country_content: str) -> list[str]:
        """Extract fleet IDs from owned_fleets section.

        The country block has:
        - fleets={...} - fleets the player can SEE (has intel on)
        - owned_fleets={...} - fleets the player actually OWNS

        Args:
            country_content: Content of the player's country block

        Returns:
            List of fleet ID strings that the player owns
        """
        # Find owned_fleets section
        owned_match = re.search(r"owned_fleets=\s*\{", country_content)
        if not owned_match:
            return []

        # Get content after owned_fleets={
        content = country_content[owned_match.end() :]

        # Extract all fleet=N values until we hit a section at lower indent
        # The structure is: owned_fleets=\n\t\t\t{\n\t\t\t\t{\n\t\t\t\t\tfleet=0\n\t\t\t\t}\n...
        # Use 100KB window - late-game empires can have 200+ fleets, each entry ~50 bytes
        fleet_ids = []
        for match in re.finditer(r"fleet=(\d+)", content[:100000]):
            fleet_ids.append(match.group(1))

        return fleet_ids

    def _get_ship_to_fleet_mapping(self) -> dict[str, str]:
        """Build a mapping of ship IDs to their fleet IDs.

        Uses Rust iter_section_entries for parsing (session mode required).

        Returns:
            Dict mapping ship_id (str) -> fleet_id (str)
        """
        ship_to_fleet = {}

        for ship_id, ship_data in iter_section_entries(self.save_path, "ships"):
            if isinstance(ship_data, dict):
                fleet_id = ship_data.get("fleet")
                if fleet_id:
                    ship_to_fleet[ship_id] = str(fleet_id)

        return ship_to_fleet

    def _get_player_owned_fleet_ids(self) -> set[str]:
        """Get all fleet IDs owned by the player.

        Uses fleets_manager.owned_fleets from the player's country data.

        Returns:
            Set of fleet ID strings owned by the player
        """
        owned_fleet_ids = set()

        player_id = self.get_player_empire_id()
        player_content = self._find_player_country_content(player_id)
        if not player_content:
            return owned_fleet_ids

        # Find fleets_manager.owned_fleets
        fleets_mgr_match = re.search(r"fleets_manager=\s*\{", player_content)
        if not fleets_mgr_match:
            return owned_fleet_ids

        content = player_content[fleets_mgr_match.start() : fleets_mgr_match.start() + 50000]
        for m in re.finditer(r"fleet=(\d+)", content):
            owned_fleet_ids.add(m.group(1))

        return owned_fleet_ids

    def _count_player_starbases(self, owned_fleet_ids: set[str] = None) -> dict:
        """Count player's starbases by level.

        Optimized approach: batch-fetch player's fleets via get_entries, extract
        their ship IDs, then check which starbases have stations matching those ships.
        This avoids iterating the entire ships section (10K+ entries).

        Args:
            owned_fleet_ids: Optional pre-computed set of player fleet IDs

        Returns:
            Dict with starbase counts by level and totals
        """
        result = {
            "citadels": 0,
            "star_fortresses": 0,
            "starholds": 0,
            "starports": 0,
            "outposts": 0,
            "orbital_rings": 0,
            "total_upgraded": 0,  # Non-outpost, non-orbital starbases (count against capacity)
            "total_systems": 0,  # Systems owned (starbases excluding orbital rings)
            "total": 0,  # All starbases including orbital rings
        }

        # Get player's owned fleet IDs
        if owned_fleet_ids is None:
            owned_fleet_ids = self._get_player_owned_fleet_ids()

        if not owned_fleet_ids:
            return result

        # Batch-fetch only player's fleets and extract their ship IDs
        # This is 17x faster than iterating all 10K+ ships
        session = _get_active_session()
        if not session:
            return result

        fleet_entries = session.get_entries("fleet", list(owned_fleet_ids))

        player_ship_ids = set()
        for entry in fleet_entries:
            fleet_data = entry.get("_value")
            if not isinstance(fleet_data, dict):
                continue
            ships = fleet_data.get("ships", [])
            if isinstance(ships, dict):
                # ships might be dict like {"0": ship_id, "1": ship_id, ...}
                for ship_id in ships.values():
                    player_ship_ids.add(str(ship_id))
            elif isinstance(ships, list):
                for ship_id in ships:
                    player_ship_ids.add(str(ship_id))

        if not player_ship_ids:
            return result

        # Get starbases and check if station is a player ship
        data = extract_sections(self.save_path, ["starbase_mgr"])
        starbases = data.get("starbase_mgr", {}).get("starbases", {})

        for sb_id, sb_data in starbases.items():
            if not isinstance(sb_data, dict):
                continue

            station = sb_data.get("station")
            level = sb_data.get("level", "unknown")

            if station is None:
                continue

            # Check if station ship belongs to player
            if str(station) not in player_ship_ids:
                continue

            # This starbase belongs to the player
            result["total"] += 1

            if "citadel" in level:
                result["citadels"] += 1
                result["total_upgraded"] += 1
                result["total_systems"] += 1
            elif "starfortress" in level:
                result["star_fortresses"] += 1
                result["total_upgraded"] += 1
                result["total_systems"] += 1
            elif "starhold" in level:
                result["starholds"] += 1
                result["total_upgraded"] += 1
                result["total_systems"] += 1
            elif "starport" in level:
                result["starports"] += 1
                result["total_upgraded"] += 1
                result["total_systems"] += 1
            elif "orbital_ring" in level:
                result["orbital_rings"] += 1
                # Orbital rings don't count against starbase capacity or as systems
            elif "outpost" in level:
                result["outposts"] += 1
                result["total_systems"] += 1

        return result

    def _get_countries_cached(self) -> dict[str, dict]:
        """Iterate countries section once and cache for reuse across extractors.

        Many extractors need to iterate the country section (diplomacy, fallen
        empires, crisis detection, khan detection, leviathans). This method
        ensures we only do the expensive Rust IPC iteration once per extraction.

        Returns:
            Dict mapping country ID (string) to country data dict
        """
        if self._countries_cache is not None:
            return self._countries_cache

        from stellaris_companion.rust_bridge import _get_active_session

        session = _get_active_session()
        if not session:
            return {}

        self._countries_cache = {}
        for country_id, country_data in session.iter_section("country"):
            if isinstance(country_data, dict):
                self._countries_cache[country_id] = country_data

        return self._countries_cache

    def _get_galactic_objects_cached(self) -> dict[str, dict]:
        """Iterate galactic_object section once and cache for reuse.

        Used by diplomacy (claims/systems) and military (starbases).

        Returns:
            Dict mapping system ID (string) to system data dict
        """
        if self._galactic_objects_cache is not None:
            return self._galactic_objects_cache

        from stellaris_companion.rust_bridge import _get_active_session

        session = _get_active_session()
        if not session:
            return {}

        self._galactic_objects_cache = {}
        for system_id, system_data in session.iter_section("galactic_object"):
            if isinstance(system_data, dict):
                self._galactic_objects_cache[system_id] = system_data

        return self._galactic_objects_cache

    def _get_fleets_cached(self) -> dict[str, dict]:
        """Iterate fleet section once and cache for reuse.

        Used by military (get_fleets, get_starbases).

        Returns:
            Dict mapping fleet ID (string) to fleet data dict
        """
        if self._fleets_cache is not None:
            return self._fleets_cache

        from stellaris_companion.rust_bridge import _get_active_session

        session = _get_active_session()
        if not session:
            return {}

        self._fleets_cache = {}
        for fleet_id, fleet_data in session.iter_section("fleet"):
            if isinstance(fleet_data, dict):
                self._fleets_cache[fleet_id] = fleet_data

        return self._fleets_cache

    def _get_pop_groups_cached(self) -> dict[str, dict]:
        """Iterate pop_groups section once and cache for reuse.

        Used by economy (pop statistics) and planets (species distribution).

        Returns:
            Dict mapping pop_group ID (string) to pop_group data dict
        """
        if self._pop_groups_cache is not None:
            return self._pop_groups_cache

        from stellaris_companion.rust_bridge import _get_active_session

        session = _get_active_session()
        if not session:
            return {}

        self._pop_groups_cache = {}
        for group_id, group_data in session.iter_section("pop_groups"):
            if isinstance(group_data, dict):
                self._pop_groups_cache[group_id] = group_data

        return self._pop_groups_cache

    def _get_country_names_map(self) -> dict:
        """Build a mapping of country ID -> country name for all empires.

        This method is cached - the expensive parsing is only done once per
        extraction session. Late-game saves can have 300+ countries including
        primitives, pirates, marauders, caravaneers, fallen/awakened empires, etc.

        Uses cached country section data for efficiency.

        Returns:
            Dict mapping integer country IDs to their empire names
        """
        # Return cached result if available
        if self._country_names is not None:
            return self._country_names

        country_names = {}

        for country_id_str, country_data in self._get_countries_cached().items():
            country_id = int(country_id_str)
            name_block = country_data.get("name")

            if name_block is None:
                continue

            country_names[country_id] = self.resolve_name(
                name_block, default="Unknown Empire", context="country"
            ).display

        self._country_names = country_names
        return self._country_names

    def _get_country_authorities_map(self) -> dict:
        """Build a mapping of country ID -> government authority for all empires.

        This method is cached - the expensive parsing is only done once per
        extraction session. Authority values indicate government type:
        - "auth_corporate" = Megacorp
        - "auth_machine_intelligence" = Machine Intelligence
        - "auth_hive_mind" = Hive Mind
        - "auth_democratic", "auth_oligarchic", "auth_dictatorial", "auth_imperial" = Standard empires

        Uses cached country section data for efficiency.

        Returns:
            Dict mapping integer country IDs to their government authority string
        """
        # Return cached result if available
        if self._country_authorities is not None:
            return self._country_authorities

        country_authorities = {}

        for country_id_str, country_data in self._get_countries_cached().items():
            country_id = int(country_id_str)

            # Authority is nested under government.authority
            government = country_data.get("government")
            if not isinstance(government, dict):
                continue

            authority = government.get("authority")
            if authority and isinstance(authority, str):
                country_authorities[country_id] = authority

        self._country_authorities = country_authorities
        return self._country_authorities

    def _get_country_ethics_map(self) -> dict:
        """Build a mapping of country ID -> ethics list for all empires.

        This method is cached - the expensive parsing is only done once per
        extraction session. Ethics values are cleaned (``ethic_`` prefix stripped)
        to match the format used by the player identity extractor.

        Uses cached country section data for efficiency.

        Returns:
            Dict mapping integer country IDs to a list of ethic strings,
            e.g. ``{0: ["fanatic_xenophile", "militarist"]}``
        """
        if self._country_ethics is not None:
            return self._country_ethics

        country_ethics: dict[int, list[str]] = {}

        for country_id_str, country_data in self._get_countries_cached().items():
            country_id = int(country_id_str)

            ethos = country_data.get("ethos")
            if not isinstance(ethos, dict):
                continue

            ethic = ethos.get("ethic", [])
            if isinstance(ethic, str):
                ethic = [ethic]
            if isinstance(ethic, list):
                cleaned = [e.replace("ethic_", "") for e in ethic if isinstance(e, str)]
                if cleaned:
                    country_ethics[country_id] = cleaned

        self._country_ethics = country_ethics
        return self._country_ethics

    def _clean_localization_key(self, key: str) -> str:
        """Clean up a localization key to a readable name.

        Handles common prefixes like NAME_, SPEC_, PRESCRIPTED_, etc.

        Args:
            key: Raw localization key (e.g., "NAME_Sol", "SPEC_Human")

        Returns:
            Cleaned up readable name (e.g., "Sol", "Human")
        """
        return self.resolve_name(key, default=key, context="generic").display

    def resolve_name(
        self,
        value: object,
        *,
        default: str = "Unknown",
        context: str = "generic",
    ) -> ResolvedName:
        """Resolve a display name from a raw key / name block / literal.

        This is the single entrypoint for name resolution across extractors.
        """
        # Narrow context to supported literals at runtime (avoid importing typing in hot paths)
        ctx = (
            context
            if context in {"generic", "planet", "country", "species", "fleet"}
            else "generic"
        )
        return _resolve_name(value, default=default, context=ctx)  # type: ignore[arg-type]

    def _get_planet_names_map(self) -> dict:
        """Build a mapping of planet ID -> planet name for all planets.

        This method is cached - the expensive parsing is only done once per
        extraction session.

        Uses Rust extract_sections for parsing (session mode required).

        Returns:
            Dict mapping planet ID (as string) to planet name
        """
        # Return cached result if available
        if self._planet_names is not None:
            return self._planet_names

        planet_names = {}

        # Use Rust extract_sections for planet parsing
        data = extract_sections(self.save_path, ["planets"])
        planets = data.get("planets", {}).get("planet", {})

        for planet_id, planet_data in planets.items():
            if not isinstance(planet_data, dict):
                continue

            name_block = planet_data.get("name")
            if name_block is None:
                continue

            # Handle different name formats
            if isinstance(name_block, (str, dict)):
                planet_names[planet_id] = self.resolve_name(
                    name_block, default="Unknown Planet", context="planet"
                ).display

        self._planet_names = planet_names
        return self._planet_names

    def _resolve_template_name_from_rust(self, name_block: dict) -> str:
        """Resolve a template name from Rust-parsed name block.

        Args:
            name_block: Dict with 'key' and 'variables' fields

        Returns:
            Resolved human-readable name
        """
        return self.resolve_name(name_block, default="Unknown Empire", context="country").display

    def _analyze_player_fleets(self, fleet_ids: list[str], max_to_analyze: int = 1500) -> dict:
        """Analyze player's fleet IDs using Rust session get_entries.

        This distinguishes between:
        - Starbases (station=yes)
        - Military fleets (non-station, military_power > 0)
        - Civilian fleets (science ships, construction ships, transports)

        Uses direct batch lookup instead of iterating all fleets. Benefits:
        - Fetches only owned fleets (200 IDs) instead of iterating 10K+ fleets
        - No 100KB block size limits (complete fleet data)
        - No regex parsing errors on nested structures
        - Much faster via direct Rust session get_entries call

        Args:
            fleet_ids: List of fleet ID strings from player's country block
            max_to_analyze: Max fleets to analyze in detail (for performance)

        Returns:
            Dict with categorized fleet counts and details

        Raises:
            ParserError: If no active Rust session
        """
        session = _get_active_session()
        if not session:
            raise ParserError("No active Rust session - session mode required")

        result = {
            "total_fleet_ids": len(fleet_ids),
            "starbase_count": 0,
            "military_fleet_count": 0,
            "civilian_fleet_count": 0,
            "military_ships": 0,
            "total_military_power": 0.0,
            "military_fleets": [],
        }

        # Use get_entries to fetch only owned fleets directly (not all 10K+ fleets)
        # Limit to max_to_analyze for performance in huge saves
        ids_to_fetch = [str(fid) for fid in fleet_ids[:max_to_analyze]]
        entries = session.get_entries("fleet", ids_to_fetch)

        for entry in entries:
            fid = entry.get("_key", "")
            fleet = entry.get("_value")

            # P010: entry might be string "none" for deleted entries
            if not isinstance(fleet, dict):
                continue

            # Direct dict access - no regex needed
            is_station = fleet.get("station") == "yes"
            is_civilian = fleet.get("civilian") == "yes"

            # Get ship count from ships list/dict
            ships = fleet.get("ships", [])
            if isinstance(ships, (list, dict)):
                ship_count = len(ships)
            else:
                ship_count = 0

            # Get military power
            mp = fleet.get("military_power")
            mp = float(mp) if mp is not None else 0.0

            if is_station:
                result["starbase_count"] += 1
            elif is_civilian:
                result["civilian_fleet_count"] += 1
            elif mp > 100:  # Threshold filters out space creatures with tiny mp
                result["military_fleet_count"] += 1
                result["military_ships"] += ship_count
                result["total_military_power"] += mp

                # Extract fleet name
                fleet_name = self._extract_fleet_name_from_data(fleet, fid)

                result["military_fleets"].append(
                    {
                        "id": fid,
                        "name": fleet_name,
                        "ships": ship_count,
                        "military_power": round(mp, 0),
                    }
                )
            else:
                result["civilian_fleet_count"] += 1

        # Add estimation note if we limited the analysis
        if len(fleet_ids) > max_to_analyze:
            ratio = len(fleet_ids) / max_to_analyze
            result["starbase_count"] = int(result["starbase_count"] * ratio)
            result["military_fleet_count"] = int(result["military_fleet_count"] * ratio)
            result["civilian_fleet_count"] = int(result["civilian_fleet_count"] * ratio)
            result["_note"] = f"Estimated from {max_to_analyze} of {len(fleet_ids)} fleet IDs"

        return result

    def _extract_fleet_name_from_data(self, fleet: dict, fid: str) -> str:
        """Extract fleet name from parsed fleet data structure."""
        name_data = fleet.get("name")

        if not name_data:
            return f"Fleet {fid}"

        return self.resolve_name(name_data, default=f"Fleet {fid}", context="fleet").display

    def _get_species_names(self) -> dict:
        """Build a mapping of species IDs to their display names.

        Uses Rust extract_sections for parsing (session mode required).

        Returns:
            Dict mapping species ID (as string) to species name
        """
        sections = extract_sections(self.gamestate_path, ["species_db"])
        species_db = sections.get("species_db", {})
        species_names = {}
        for species_id, data in species_db.items():
            if isinstance(data, dict):
                # Name can be a string or a dict with key field
                name = data.get("name")
                if isinstance(name, dict):
                    name = name.get("key")
                if name:
                    species_names[species_id] = self.resolve_name(
                        name, default=f"Species {species_id}", context="species"
                    ).display
                elif data.get("class"):
                    # Fallback to class name
                    species_names[species_id] = self.resolve_name(
                        data["class"], default=f"Species {species_id}", context="species"
                    ).display
        return species_names

    def _get_player_planet_ids(self) -> list[str]:
        """Get IDs of all planets owned by the player.

        Uses Rust extract_sections for parsing (session mode required).

        Returns:
            List of planet ID strings
        """
        player_id = self.get_player_empire_id()
        player_id_str = str(player_id)
        planet_ids = []

        # Extract planets section
        data = extract_sections(self.save_path, ["planets"])
        planets = data.get("planets", {}).get("planet", {})

        for planet_id, planet_data in planets.items():
            if isinstance(planet_data, dict):
                owner = planet_data.get("owner")
                if owner == player_id_str:
                    planet_ids.append(planet_id)

        return planet_ids

    def _get_pop_ids_for_planets(self, planet_ids: list[str]) -> list[str]:
        """Get all pop IDs from the specified planets.

        Uses Rust extract_sections for parsing (session mode required).

        Args:
            planet_ids: List of planet ID strings to get pops from

        Returns:
            List of pop ID strings
        """
        pop_ids = []
        planet_id_set = set(planet_ids)

        # Extract planets section
        data = extract_sections(self.save_path, ["planets"])
        planets = data.get("planets", {}).get("planet", {})

        for planet_id, planet_data in planets.items():
            if planet_id not in planet_id_set:
                continue

            if isinstance(planet_data, dict):
                pop_jobs = planet_data.get("pop_jobs", [])
                if isinstance(pop_jobs, list):
                    pop_ids.extend(pop_jobs)

        return pop_ids

    def _strip_previews(self, data: dict) -> dict:
        """Remove raw_data_preview fields to reduce context size.

        Args:
            data: Dictionary that may contain preview fields

        Returns:
            Dictionary with preview fields removed
        """
        if not isinstance(data, dict):
            return data
        return {k: v for k, v in data.items() if "preview" not in k.lower()}
