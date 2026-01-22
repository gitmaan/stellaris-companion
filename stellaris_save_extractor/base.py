from __future__ import annotations

import io
import logging
import re
import zipfile
from datetime import datetime
from pathlib import Path

# Rust bridge for fast Clausewitz parsing
try:
    from rust_bridge import extract_sections, iter_section_entries, ParserError
    RUST_BRIDGE_AVAILABLE = True
except ImportError:
    RUST_BRIDGE_AVAILABLE = False
    ParserError = Exception  # Fallback type for type hints

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
        This is an alias for save_path for compatibility with rust_bridge.py.
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

        # Try Rust bridge first for faster parsing
        if RUST_BRIDGE_AVAILABLE:
            try:
                sections = extract_sections(self.gamestate_path, ["buildings"])
                buildings = sections.get("buildings", {})
                self._building_types = {
                    bid: data.get("type")
                    for bid, data in buildings.items()
                    if isinstance(data, dict) and "type" in data
                }
                return self._building_types
            except ParserError as e:
                logger.warning(f"Rust parser failed for buildings: {e}, falling back to regex")
            except Exception as e:
                logger.warning(f"Unexpected error from Rust parser: {e}, falling back to regex")

        # Fallback: regex-based parsing
        return self._get_building_types_regex()

    def _get_building_types_regex(self) -> dict:
        """Parse buildings section using regex (fallback method).

        Returns:
            Dict mapping building IDs (as strings) to building type names
        """
        # Find the top-level buildings section (near end of file)
        match = re.search(r'^buildings=\s*\{', self.gamestate, re.MULTILINE)
        if not match:
            return self._building_types

        start = match.start()
        # Parse entries like: 50331648={ type="building_ministry_production" position=0 }
        chunk = self.gamestate[start:start + 5000000]  # Buildings section can be large

        for m in re.finditer(r'(\d+)=\s*\{\s*type="([^"]+)"', chunk):
            building_id = m.group(1)
            building_type = m.group(2)
            self._building_types[building_id] = building_type

        return self._building_types

    def _load_meta(self) -> None:
        """Extract meta from the save file (cheap, used for Tier 0 status)."""
        with zipfile.ZipFile(self.save_path, 'r') as z:
            with z.open("meta") as raw:
                with io.TextIOWrapper(raw, encoding="utf-8", errors="replace") as text:
                    self._meta = text.read()

    def _load_gamestate(self) -> None:
        """Extract the full gamestate from the save file (expensive)."""
        with zipfile.ZipFile(self.save_path, 'r') as z:
            with z.open("gamestate") as raw:
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
        pattern = rf'^{re.escape(section_name)}\s*=\s*\{{'
        match = re.search(pattern, self.gamestate, re.MULTILINE)

        if not match:
            return None

        start = match.start()

        # Find matching closing brace
        brace_count = 0
        in_section = False

        for i, char in enumerate(self.gamestate[start:], start):
            if char == '{':
                brace_count += 1
                in_section = True
            elif char == '}':
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
            if content[i] == '}':
                brace_count += 1
            elif content[i] == '{':
                if brace_count == 0:
                    # Find the key before this brace
                    block_start = content.rfind('\n', 0, i) + 1
                    break
                brace_count -= 1

        # Now find the matching closing brace
        brace_count = 0
        for i in range(block_start, len(content)):
            if content[i] == '{':
                brace_count += 1
            elif content[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    return content[block_start:i + 1]

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

        Args:
            player_id: The player's country ID (usually 0)

        Returns:
            String content of the country block, or None if not found
        """
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
                    return self.gamestate[start : i + 1]

        return None

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
        owned_match = re.search(r'owned_fleets=\s*\{', country_content)
        if not owned_match:
            return []

        # Get content after owned_fleets={
        content = country_content[owned_match.end():]

        # Extract all fleet=N values until we hit a section at lower indent
        # The structure is: owned_fleets=\n\t\t\t{\n\t\t\t\t{\n\t\t\t\t\tfleet=0\n\t\t\t\t}\n...
        # Use 100KB window - late-game empires can have 200+ fleets, each entry ~50 bytes
        fleet_ids = []
        for match in re.finditer(r'fleet=(\d+)', content[:100000]):
            fleet_ids.append(match.group(1))

        return fleet_ids

    def _get_ship_to_fleet_mapping(self) -> dict[str, str]:
        """Build a mapping of ship IDs to their fleet IDs.

        Returns:
            Dict mapping ship_id (str) -> fleet_id (str)
        """
        bounds = self._get_section_bounds("ships")
        if not bounds:
            return {}

        ship_to_fleet = {}
        ships_start, ships_end = bounds
        entry_re = re.compile(r'(?m)^\t(\d+)\s*=\s*\{')

        for entry in entry_re.finditer(self.gamestate, ships_start, ships_end):
            ship_id = entry.group(1)
            start = entry.start()
            snippet = self.gamestate[start : min(start + 3000, ships_end)]

            fleet_m = re.search(r'\bfleet=(\d+)\b', snippet)
            if fleet_m:
                ship_to_fleet[ship_id] = fleet_m.group(1)

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
        fleets_mgr_match = re.search(r'fleets_manager=\s*\{', player_content)
        if not fleets_mgr_match:
            return owned_fleet_ids

        content = player_content[fleets_mgr_match.start():fleets_mgr_match.start() + 50000]
        for m in re.finditer(r'fleet=(\d+)', content):
            owned_fleet_ids.add(m.group(1))

        return owned_fleet_ids

    def _count_player_starbases(self, owned_fleet_ids: set[str] = None) -> dict:
        """Count player's starbases by level using ship→fleet ownership chain.

        Traces ownership: starbase.station (ship ID) → ship.fleet → player's owned_fleets

        Args:
            owned_fleet_ids: Optional pre-computed set of player fleet IDs

        Returns:
            Dict with starbase counts by level and totals
        """
        result = {
            'citadels': 0,
            'star_fortresses': 0,
            'starholds': 0,
            'starports': 0,
            'outposts': 0,
            'orbital_rings': 0,
            'total_upgraded': 0,  # Non-outpost, non-orbital starbases (count against capacity)
            'total_systems': 0,   # Systems owned (starbases excluding orbital rings)
            'total': 0,           # All starbases including orbital rings
        }

        # Get player's owned fleet IDs
        if owned_fleet_ids is None:
            owned_fleet_ids = self._get_player_owned_fleet_ids()

        if not owned_fleet_ids:
            return result

        # Build ship→fleet mapping
        ship_to_fleet = self._get_ship_to_fleet_mapping()
        if not ship_to_fleet:
            return result

        # Find starbase_mgr section
        starbase_match = re.search(r'^starbase_mgr=\s*\{', self.gamestate, re.MULTILINE)
        if not starbase_match:
            return result

        sb_chunk = self.gamestate[starbase_match.start():starbase_match.start() + 5000000]

        # Parse each starbase entry
        for m in re.finditer(r'\n\t\t(\d+)=\n\t\t\{', sb_chunk):
            sb_id = m.group(1)
            content = sb_chunk[m.start():m.start() + 2000]

            # Get level and station (ship ID)
            level_m = re.search(r'level="([^"]+)"', content)
            station_m = re.search(r'\n\t\t\tstation=(\d+)\n', content)

            if not station_m:
                continue

            ship_id = station_m.group(1)
            level = level_m.group(1) if level_m else 'unknown'

            # Trace ownership: ship → fleet → player?
            fleet_id = ship_to_fleet.get(ship_id)
            if not fleet_id or fleet_id not in owned_fleet_ids:
                continue

            # This starbase belongs to the player
            result['total'] += 1

            if 'citadel' in level:
                result['citadels'] += 1
                result['total_upgraded'] += 1
                result['total_systems'] += 1
            elif 'starfortress' in level:
                result['star_fortresses'] += 1
                result['total_upgraded'] += 1
                result['total_systems'] += 1
            elif 'starhold' in level:
                result['starholds'] += 1
                result['total_upgraded'] += 1
                result['total_systems'] += 1
            elif 'starport' in level:
                result['starports'] += 1
                result['total_upgraded'] += 1
                result['total_systems'] += 1
            elif 'orbital_ring' in level:
                result['orbital_rings'] += 1
                # Orbital rings don't count against starbase capacity or as systems
            elif 'outpost' in level:
                result['outposts'] += 1
                result['total_systems'] += 1

        return result

    def _get_country_names_map(self) -> dict:
        """Build a mapping of country ID -> country name for all empires.

        This method is cached - the expensive parsing is only done once per
        extraction session. Late-game saves can have 300+ countries including
        primitives, pirates, marauders, caravaneers, fallen/awakened empires, etc.

        Returns:
            Dict mapping integer country IDs to their empire names
        """
        # Return cached result if available
        if self._country_names is not None:
            return self._country_names

        country_names = {}

        bounds = self._get_section_bounds("country")
        if not bounds:
            self._country_names = country_names
            return country_names
        country_start, country_end = bounds

        # Find entries like: <tab>0={ ... name="United Nations of Earth" ... }
        entry_re = re.compile(r'(?m)^\t(\d+)\s*=\s*\{')
        entries = list(entry_re.finditer(self.gamestate, country_start, country_end))

        # Process all country entries - no artificial limit
        # Late-game saves can have 300+ countries (fallen empires, primitives,
        # marauders, caravaneers, etc.) and we need to resolve all of them
        for i, entry_match in enumerate(entries):
            country_id = int(entry_match.group(1))
            entry_start = entry_match.start()

            # Determine block end - only need first part of block for name
            # Using min of 5000 chars or next entry to optimize performance
            if i + 1 < len(entries):
                entry_end = min(entry_start + 5000, entries[i + 1].start())
            else:
                entry_end = entry_start + 5000

            block = self.gamestate[entry_start : min(entry_end, country_end)]

            # Extract name - can be either:
            # 1. name="Direct Name" (simple string)
            # 2. name={ key="LOCALIZATION_KEY" } (localization reference)
            # 3. name={ key="%ADJECTIVE%" variables={...} } (template with variables)
            # First try direct string format
            name_match = re.search(r'(?m)^\t\tname\s*=\s*"([^"]+)"', block)
            if name_match:
                country_names[country_id] = name_match.group(1)
            else:
                # Try localization key format: name={ key="..." }
                key_match = re.search(r'(?m)^\t\tname\s*=\s*\{\s*key\s*=\s*"([^"]+)"', block)
                if key_match:
                    key = key_match.group(1)
                    # Check if name block has variables (look specifically in name={...} block)
                    # Extract name block first to check for variables
                    name_block_match = re.search(r'(?m)^\t\tname\s*=\s*\{', block)
                    has_name_vars = False
                    if name_block_match:
                        # Find extent of name block
                        ns = name_block_match.end()
                        bc = 1
                        ne = ns
                        while bc > 0 and ne < len(block):
                            if block[ne] == '{': bc += 1
                            elif block[ne] == '}': bc -= 1
                            ne += 1
                        name_section = block[name_block_match.start():ne]
                        has_name_vars = 'variables=' in name_section

                    if has_name_vars:
                        # Extract variable values to build readable name
                        readable = self._resolve_template_name(block, key)
                    else:
                        readable = self._localization_key_to_readable_name(key)
                    country_names[country_id] = readable

        # Cache the result for subsequent calls
        self._country_names = country_names
        return country_names

    def _localization_key_to_readable_name(self, key: str) -> str:
        """Convert a localization key to a human-readable name.

        Handles various patterns including:
        - EMPIRE_DESIGN_* (standard empires)
        - FALLEN_EMPIRE_* (fallen empires with optional type suffix)
        - AWAKENED_EMPIRE_* (awakened empires)
        - NAME_* (named entities like Enigmatic Observers)

        Args:
            key: The localization key (e.g., "FALLEN_EMPIRE_SPIRITUALIST")

        Returns:
            Human-readable name (e.g., "Fallen Empire (Spiritualist)")
        """
        # Handle AWAKENED_EMPIRE_* patterns (check before FALLEN to handle awakened first)
        # Examples: AWAKENED_EMPIRE_SPIRITUALIST, AWAKENED_EMPIRE_1
        if key.startswith('AWAKENED_EMPIRE_'):
            suffix = key[len('AWAKENED_EMPIRE_'):]
            if suffix.isdigit():
                return f"Awakened Empire {suffix}"
            else:
                # Convert suffix like SPIRITUALIST to (Spiritualist)
                type_name = suffix.replace('_', ' ').title()
                return f"Awakened Empire ({type_name})"

        # Handle FALLEN_EMPIRE_* patterns
        # Examples: FALLEN_EMPIRE_1, FALLEN_EMPIRE_SPIRITUALIST, FALLEN_EMPIRE_MATERIALIST
        if key.startswith('FALLEN_EMPIRE_'):
            suffix = key[len('FALLEN_EMPIRE_'):]
            if suffix.isdigit():
                return f"Fallen Empire {suffix}"
            else:
                # Convert suffix like SPIRITUALIST to (Spiritualist)
                type_name = suffix.replace('_', ' ').title()
                return f"Fallen Empire ({type_name})"

        # Handle NAME_* patterns (specific named entities)
        # Examples: NAME_Enigmatic_Observers, NAME_Keepers_of_Knowledge
        if key.startswith('NAME_'):
            name_part = key[len('NAME_'):]
            # Replace underscores with spaces, preserve existing capitalization
            return name_part.replace('_', ' ')

        # Handle standard EMPIRE_DESIGN_* patterns
        # Examples: EMPIRE_DESIGN_humans1, EMPIRE_DESIGN_commonwealth
        if key.startswith('EMPIRE_DESIGN_'):
            name_part = key[len('EMPIRE_DESIGN_'):]
            # Insert space before trailing numbers (humans1 -> humans 1)
            name_part = re.sub(r'(\D)(\d+)$', r'\1 \2', name_part)
            return name_part.replace('_', ' ').title()

        # Fallback: general cleanup for any other patterns
        # Remove common prefixes and clean up
        result = key
        for prefix in ['EMPIRE_', 'COUNTRY_', 'CIV_']:
            if result.startswith(prefix):
                result = result[len(prefix):]
                break

        return result.replace('_', ' ').title()

    def _resolve_template_name(self, block: str, template_key: str) -> str:
        """Resolve a template name like %ADJECTIVE% using its variables block.

        Stellaris uses templates like:
            name={
                key="%ADJECTIVE%"
                variables={
                    { key="adjective" value={ key="SPEC_Khessam" } }
                    { key="1" value={ key="State" } }
                }
            }
        This should resolve to "Khessam State".

        Args:
            block: The country block containing the name and variables
            template_key: The template key (e.g., "%ADJECTIVE%")

        Returns:
            Resolved name or a cleaned-up fallback
        """
        # First, extract just the name={...} block to avoid matching adjective={...}
        name_block_match = re.search(r'\n\t\tname\s*=\s*\{', block)
        if name_block_match:
            # Find matching closing brace for name block
            start = name_block_match.end()
            brace_count = 1
            end = start
            while brace_count > 0 and end < len(block):
                if block[end] == '{':
                    brace_count += 1
                elif block[end] == '}':
                    brace_count -= 1
                end += 1
            name_block = block[name_block_match.start():end]
        else:
            name_block = block[:1000]  # Fallback to first part

        # Recursively extract all literal value keys from nested variables
        # This handles nested templates like %ADJ% containing more templates
        # Pattern: value={ key="SOMETHING" } where SOMETHING doesn't start with %
        all_values = re.findall(r'value\s*=\s*\{\s*key\s*=\s*"([^"%][^"]*)"', name_block)

        if not all_values:
            # Try simpler value="string" format
            all_values = re.findall(r'value\s*=\s*"([^"%][^"]*)"', name_block)

        if all_values:
            # Clean up each value and combine
            parts = []
            for vk in all_values:
                # Remove common prefixes like SPEC_, ADJ_, etc.
                clean = vk
                for prefix in ['SPEC_', 'ADJ_', 'NAME_', 'SUFFIX_']:
                    if clean.startswith(prefix):
                        clean = clean[len(prefix):]
                        break
                # Convert underscores to spaces
                clean = clean.replace('_', ' ').strip()
                if clean:
                    parts.append(clean)

            if parts:
                return ' '.join(parts)

        # Fallback: return a generic label
        return "Unknown Empire"

    def _analyze_player_fleets(self, fleet_ids: list[str], max_to_analyze: int = 1500) -> dict:
        """Analyze player's fleet IDs to categorize them properly.

        This distinguishes between:
        - Starbases (station=yes)
        - Military fleets (non-station, military_power > 0)
        - Civilian fleets (science ships, construction ships, transports)

        Args:
            fleet_ids: List of fleet ID strings from player's country block
            max_to_analyze: Max fleets to analyze in detail (for performance)

        Returns:
            Dict with categorized fleet counts and details
        """
        result = {
            'total_fleet_ids': len(fleet_ids),
            'starbase_count': 0,
            'military_fleet_count': 0,
            'civilian_fleet_count': 0,
            'military_ships': 0,
            'total_military_power': 0.0,
            'military_fleets': [],  # List of military fleet details
        }

        # Find the fleet section using robust detection
        fleet_section_start = self._find_fleet_section_start()
        if fleet_section_start == -1:
            return result

        fleet_section = self.gamestate[fleet_section_start:]

        # Analyze fleets (limit for performance in huge saves)
        analyzed = 0
        for fid in fleet_ids:
            if analyzed >= max_to_analyze:
                # Estimate remaining based on ratios
                ratio = len(fleet_ids) / max_to_analyze
                result['starbase_count'] = int(result['starbase_count'] * ratio)
                result['military_fleet_count'] = int(result['military_fleet_count'] * ratio)
                result['civilian_fleet_count'] = int(result['civilian_fleet_count'] * ratio)
                result['_note'] = f'Estimated from {max_to_analyze} of {len(fleet_ids)} fleet IDs'
                break

            # Pattern must match fleet ID at start of line with tab indent
            # This avoids matching ship IDs inside other fleet blocks
            pattern = rf'\n\t{fid}=\n\t\{{'
            match = re.search(pattern, fleet_section)
            if not match:
                continue

            # Get fleet data - find boundary at next fleet entry to handle
            # arbitrarily large fleets (hundreds of ships, combat history, etc.)
            fleet_start = match.start()

            # Find next fleet entry: \n\t{digits}=\n\t{ pattern
            # Search within reasonable window (100KB handles extreme cases)
            search_window = fleet_section[fleet_start + 10:fleet_start + 100000]
            next_fleet = re.search(r'\n\t\d+=\n\t\{', search_window)
            if next_fleet:
                block_end = next_fleet.start() + 10  # +10 accounts for offset
            else:
                block_end = 100000  # Last fleet in section

            fleet_data = fleet_section[fleet_start:fleet_start + block_end]
            analyzed += 1

            # Check for station/civilian at fleet's top level (two tabs indentation)
            is_station = re.search(r'\n\t\tstation=yes', fleet_data) is not None
            is_civilian = re.search(r'\n\t\tcivilian=yes', fleet_data) is not None

            # Count ships
            ships_match = re.search(r'ships=\s*\{([^}]+)\}', fleet_data)
            ship_count = len(ships_match.group(1).split()) if ships_match else 0

            # Get military power
            mp_match = re.search(r'military_power=([\d.]+)', fleet_data)
            mp = float(mp_match.group(1)) if mp_match else 0.0

            if is_station:
                result['starbase_count'] += 1
            elif is_civilian:
                result['civilian_fleet_count'] += 1
            elif mp > 100:  # Threshold filters out space creatures with tiny mp
                result['military_fleet_count'] += 1
                result['military_ships'] += ship_count
                result['total_military_power'] += mp

                # Extract fleet name for military fleets
                name_match = re.search(r'key="([^"]+)"', fleet_data)
                fleet_name = name_match.group(1) if name_match else f"Fleet {fid}"

                # Handle %SEQ% format strings - extract num variable for fleet number
                if fleet_name == '%SEQ%':
                    num_match = re.search(r'key="num"[^}]*key="(\d+)"', fleet_data)
                    if num_match:
                        fleet_num = int(num_match.group(1))
                        fleet_name = f"Fleet #{fleet_num}"
                    else:
                        fleet_name = f"Fleet {fid}"

                # Clean up localization keys
                if fleet_name.startswith('shipclass_'):
                    fleet_name = fleet_name.replace('shipclass_', '').replace('_name', '').title()
                elif fleet_name.startswith('NAME_'):
                    fleet_name = fleet_name.replace('NAME_', '').replace('_', ' ')
                elif fleet_name.startswith('TRANS_'):
                    fleet_name = 'Transport Fleet'
                elif fleet_name.endswith('_FLEET'):
                    # e.g., HUMAN1_FLEET -> extract just the type
                    fleet_name = fleet_name.replace('_FLEET', '').replace('_', ' ').title() + ' Fleet'

                # Store all military fleets (no truncation - callers can slice if needed)
                result['military_fleets'].append({
                    'id': fid,
                    'name': fleet_name,
                    'ships': ship_count,
                    'military_power': round(mp, 0),
                })
            else:
                result['civilian_fleet_count'] += 1

        return result

    def _get_species_names(self) -> dict:
        """Build a mapping of species IDs to their display names.

        Uses Rust bridge for fast parsing when available, falls back to regex.

        Returns:
            Dict mapping species ID (as string) to species name
        """
        # Try Rust bridge first for faster parsing
        if RUST_BRIDGE_AVAILABLE:
            try:
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
                            species_names[species_id] = name
                        elif data.get("class"):
                            # Fallback to class name
                            species_names[species_id] = data["class"]
                return species_names
            except ParserError as e:
                logger.warning(f"Rust parser failed for species_db: {e}, falling back to regex")
            except Exception as e:
                logger.warning(f"Unexpected error from Rust parser: {e}, falling back to regex")

        # Fallback: regex-based parsing
        return self._get_species_names_regex()

    def _get_species_names_regex(self) -> dict:
        """Build species ID to name mapping using regex (fallback method).

        Returns:
            Dict mapping species ID (as string) to species name
        """
        species_names = {}

        # Find the species_db section (near start of file)
        species_match = re.search(r'^species_db=\s*\{', self.gamestate, re.MULTILINE)
        if not species_match:
            # Fallback: try older format
            species_match = re.search(r'^species=\s*\{', self.gamestate, re.MULTILINE)
            if not species_match:
                return species_names

        start = species_match.start()
        # Species section is usually within first 2MB
        species_chunk = self.gamestate[start:start + 2000000]

        # Parse species entries: ID={ ... name="Species Name" ... }
        # Format: \n\tID=\n\t{ ... name="Name" ...
        species_pattern = r'\n\t(\d+)=\s*\{'
        for match in re.finditer(species_pattern, species_chunk):
            species_id = match.group(1)
            block_start = match.start()

            # Get a chunk for this species entry (they're typically < 1000 chars)
            block_chunk = species_chunk[block_start:block_start + 1500]

            # Extract name
            name_match = re.search(r'name="([^"]+)"', block_chunk)
            if name_match:
                species_names[species_id] = name_match.group(1)
            else:
                # Fallback: use species class as name
                class_match = re.search(r'class="([^"]+)"', block_chunk)
                if class_match:
                    species_names[species_id] = class_match.group(1)

        return species_names

    def _get_player_planet_ids(self) -> list[str]:
        """Get IDs of all planets owned by the player.

        Returns:
            List of planet ID strings
        """
        player_id = self.get_player_empire_id()
        planet_ids = []

        # Find the planets section
        planets_match = re.search(r'^planets=\s*\{\s*planet=\s*\{', self.gamestate, re.MULTILINE)
        if not planets_match:
            return planet_ids

        start = planets_match.start()
        planets_chunk = self.gamestate[start:start + 20000000]  # 20MB for planets

        # Find each planet and check ownership
        planet_start_pattern = r'\n\t\t(\d+)=\s*\{'
        for match in re.finditer(planet_start_pattern, planets_chunk):
            planet_id = match.group(1)
            block_start = match.start() + 1

            # Get first 3000 chars to find owner (owner is near start of block)
            block_chunk = planets_chunk[block_start:block_start + 3000]

            # Check if owned by player
            owner_match = re.search(r'\n\s*owner=(\d+)', block_chunk)
            if owner_match and int(owner_match.group(1)) == player_id:
                planet_ids.append(planet_id)

        return planet_ids

    def _get_pop_ids_for_planets(self, planet_ids: list[str]) -> list[str]:
        """Get all pop IDs from the specified planets.

        Args:
            planet_ids: List of planet ID strings to get pops from

        Returns:
            List of pop ID strings
        """
        pop_ids = []

        # Find the planets section
        planets_match = re.search(r'^planets=\s*\{\s*planet=\s*\{', self.gamestate, re.MULTILINE)
        if not planets_match:
            return pop_ids

        start = planets_match.start()
        planets_chunk = self.gamestate[start:start + 20000000]

        planet_id_set = set(planet_ids)

        # Find each planet block and extract pop_jobs
        planet_start_pattern = r'\n\t\t(\d+)=\s*\{'
        for match in re.finditer(planet_start_pattern, planets_chunk):
            planet_id = match.group(1)
            if planet_id not in planet_id_set:
                continue

            block_start = match.start() + 1

            # Find end of planet block (they can be large with pop data)
            brace_count = 0
            block_end = block_start
            started = False
            for i, char in enumerate(planets_chunk[block_start:block_start + 30000], block_start):
                if char == '{':
                    brace_count += 1
                    started = True
                elif char == '}':
                    brace_count -= 1
                    if started and brace_count == 0:
                        block_end = i + 1
                        break

            planet_block = planets_chunk[block_start:block_end]

            # Extract pop_jobs list
            pop_jobs_match = re.search(r'pop_jobs=\s*\{([^}]+)\}', planet_block)
            if pop_jobs_match:
                ids = re.findall(r'\d+', pop_jobs_match.group(1))
                pop_ids.extend(ids)

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
        return {k: v for k, v in data.items() if 'preview' not in k.lower()}
