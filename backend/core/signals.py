"""
SnapshotSignals builder for unified history extraction.

Built once per snapshot in ingestion worker (where Rust session is active).
Provides normalized, resolved data for events and chronicle.

Part of Option D: Push Extraction Upstream.
See docs/OPTION_D_UNIFIED_HISTORY_EXTRACTION.md for architecture.
"""

from __future__ import annotations

import contextlib
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from stellaris_save_extractor import SaveExtractor

# Schema version for signals payload - increment when structure changes
SIGNALS_FORMAT_VERSION = 1


class _BriefingBackedExtractor:
    """Provide SaveExtractor-like accessors backed by a precomputed briefing.

    Goal: when ingestion already computed `briefing = extractor.get_complete_briefing()`,
    signals building should not re-run the same heavy Rust-backed extractor methods.

    This proxy reads from the briefing when the expected section is present and
    well-formed, and falls back to the real extractor otherwise.
    """

    def __init__(self, extractor: SaveExtractor, briefing: dict[str, Any]):
        self._extractor = extractor
        self._briefing = briefing if isinstance(briefing, dict) else {}

    def __getattr__(self, name: str) -> Any:
        # Forward all other attributes/methods (e.g., save_path, _get_player_country_entry).
        return getattr(self._extractor, name)

    @staticmethod
    def _as_dict(value: Any) -> dict[str, Any] | None:
        return value if isinstance(value, dict) else None

    def get_leaders(self) -> dict[str, Any]:
        return self._as_dict(self._briefing.get("leadership")) or self._extractor.get_leaders()

    def get_wars(self) -> dict[str, Any]:
        military = self._as_dict(self._briefing.get("military"))
        cached = self._as_dict(military.get("wars")) if military else None
        return cached or self._extractor.get_wars()

    def get_diplomacy(self) -> dict[str, Any]:
        return self._as_dict(self._briefing.get("diplomacy")) or self._extractor.get_diplomacy()

    def get_subjects(self) -> dict[str, Any]:
        diplomacy = self._as_dict(self._briefing.get("diplomacy"))
        cached = self._as_dict(diplomacy.get("subjects")) if diplomacy else None
        return cached or self._extractor.get_subjects()

    def get_technology(self) -> dict[str, Any]:
        return self._as_dict(self._briefing.get("technology")) or self._extractor.get_technology()

    def get_megastructures(self) -> dict[str, Any]:
        military = self._as_dict(self._briefing.get("military"))
        cached = self._as_dict(military.get("megastructures")) if military else None
        return cached or self._extractor.get_megastructures()

    def get_crisis_status(self) -> dict[str, Any]:
        endgame = self._as_dict(self._briefing.get("endgame"))
        cached = self._as_dict(endgame.get("crisis")) if endgame else None
        return cached or self._extractor.get_crisis_status()

    def get_fallen_empires(self) -> dict[str, Any]:
        return (
            self._as_dict(self._briefing.get("fallen_empires"))
            or self._extractor.get_fallen_empires()
        )

    def get_starbases(self) -> dict[str, Any]:
        return self._as_dict(self._briefing.get("defense")) or self._extractor.get_starbases()

    def get_ascension_perks(self) -> dict[str, Any]:
        progression = self._as_dict(self._briefing.get("progression"))
        cached = self._as_dict(progression.get("ascension_perks")) if progression else None
        return cached or self._extractor.get_ascension_perks()

    def get_lgate_status(self) -> dict[str, Any]:
        endgame = self._as_dict(self._briefing.get("endgame"))
        cached = self._as_dict(endgame.get("lgate")) if endgame else None
        return cached or self._extractor.get_lgate_status()

    def get_menace(self) -> dict[str, Any]:
        endgame = self._as_dict(self._briefing.get("endgame"))
        cached = self._as_dict(endgame.get("menace")) if endgame else None
        return cached or self._extractor.get_menace()

    def get_great_khan(self) -> dict[str, Any]:
        endgame = self._as_dict(self._briefing.get("endgame"))
        cached = self._as_dict(endgame.get("great_khan")) if endgame else None
        return cached or self._extractor.get_great_khan()

    def get_galactic_community(self) -> dict[str, Any]:
        progression = self._as_dict(self._briefing.get("progression"))
        cached = self._as_dict(progression.get("galactic_community")) if progression else None
        return cached or self._extractor.get_galactic_community()

    def get_traditions(self) -> dict[str, Any]:
        progression = self._as_dict(self._briefing.get("progression"))
        cached = self._as_dict(progression.get("traditions")) if progression else None
        return cached or self._extractor.get_traditions()

    def get_special_projects(self) -> dict[str, Any]:
        return (
            self._as_dict(self._briefing.get("projects")) or self._extractor.get_special_projects()
        )

    def get_strategic_geography(self) -> dict[str, Any]:
        cached = self._as_dict(self._briefing.get("strategic_geography"))
        return cached or self._extractor.get_strategic_geography()


def build_snapshot_signals(*, extractor: SaveExtractor, briefing: dict[str, Any]) -> dict[str, Any]:
    """Build normalized signals payload from SaveExtractor.

    This is called in the ingestion worker subprocess where the Rust session
    is active, ensuring all data comes from the fast Rust parser.

    Args:
        extractor: SaveExtractor instance (with active Rust session for best results)
        briefing: Complete briefing dict from extractor

    Returns:
        SnapshotSignals dict with format_version, generated_at, player_id, leaders, etc.
    """
    meta = briefing.get("meta", {}) if isinstance(briefing, dict) else {}

    # Prefer briefing-backed data where possible to avoid repeating expensive extraction
    # already done by get_complete_briefing(). Fall back to extractor if any briefing
    # section is missing or malformed.
    source: SaveExtractor = (
        _BriefingBackedExtractor(extractor, briefing)
        if isinstance(briefing, dict) and briefing
        else extractor
    )

    signals: dict[str, Any] = {
        "format_version": SIGNALS_FORMAT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "player_id": meta.get("player_id"),
    }

    # Extract leader signals with resolved names
    signals["leaders"] = _extract_leader_signals(source)

    # Extract war signals
    signals["wars"] = _extract_war_signals(source)

    # Extract diplomacy signals
    signals["diplomacy"] = _extract_diplomacy_signals(source)

    # Extract technology signals
    signals["technology"] = _extract_technology_signals(source)

    # Extract megastructures signals
    signals["megastructures"] = _extract_megastructures_signals(source)

    # Extract crisis signals
    signals["crisis"] = _extract_crisis_signals(source)

    # Extract fallen empires signals
    signals["fallen_empires"] = _extract_fallen_empires_signals(source)

    # Extract policies signals
    signals["policies"] = _extract_policies_signals(source)

    # Extract edicts signals
    signals["edicts"] = _extract_edicts_signals(source)

    # Extract galaxy settings (static per game but needed for milestone events)
    signals["galaxy_settings"] = _extract_galaxy_settings_signals(source)

    # Extract systems count (number of controlled systems via starbases)
    signals["systems"] = _extract_systems_signals(source)

    # Extract ascension perks for chronicle events
    signals["ascension_perks"] = _extract_ascension_perks_signals(source)

    # Extract L-Gate status for chronicle events (L-Gate opening is chapter-defining)
    signals["lgate"] = _extract_lgate_signals(source)

    # Extract menace/Become the Crisis status for chronicle events
    signals["menace"] = _extract_menace_signals(source)

    # Extract Great Khan / Marauder status for chronicle events
    signals["great_khan"] = _extract_great_khan_signals(source)

    # Extract Galactic Community status for chronicle events
    signals["galactic_community"] = _extract_galactic_community_signals(source)

    # Extract tradition tree completion status for chronicle events
    signals["traditions"] = _extract_traditions_signals(source)

    # Extract precursor discovery status for chronicle events
    signals["precursors"] = _extract_precursor_signals(source)

    # Extract subject/vassal relationships for chronicle events
    signals["subjects"] = _extract_subjects_signals(source)

    # Extract strategic geography (border neighbors, chokepoints)
    signals["geography"] = _extract_geography_signals(source)

    return signals


def _extract_leader_signals(extractor: SaveExtractor) -> dict[str, Any]:
    """Extract normalized leader data with resolved names.

    Uses extractor.get_leaders() which handles name resolution via
    _extract_leader_name_rust() when Rust session is active.

    Returns:
        Dict with count, leaders list, and ruler tracking:
        - count: int
        - leaders: list of leader dicts
        - ruler_id: int | None (ID of current ruler for change detection)
        - ruler_name: str | None (name of current ruler)

        Each leader has:
        - id: int
        - class: str (admiral, general, scientist, governor, official)
        - level: int | None
        - name: str | None (resolved human-readable name)
        - name_key: str | None (raw key for debugging/localization)
        - death_date: str | None
        - date_added: str | None
        - recruitment_date: str | None
        - is_ruler: bool (True if this leader is the current ruler)
    """
    raw = extractor.get_leaders()

    if not isinstance(raw, dict):
        return {"count": 0, "leaders": [], "ruler_id": None, "ruler_name": None}

    raw_leaders = raw.get("leaders", [])
    if not isinstance(raw_leaders, list):
        return {"count": 0, "leaders": [], "ruler_id": None, "ruler_name": None}

    # Get the actual ruler ID from the player country entry
    # The country.ruler field contains the leader ID of the current ruler
    actual_ruler_id: int | None = None
    try:
        player_id = extractor.get_player_empire_id()
        country = extractor._get_player_country_entry(player_id)
        if isinstance(country, dict):
            ruler_ref = country.get("ruler")
            if ruler_ref is not None:
                actual_ruler_id = int(ruler_ref)
    except Exception:
        pass

    normalized: list[dict[str, Any]] = []
    ruler_id: int | None = None
    ruler_name: str | None = None

    for leader in raw_leaders:
        if not isinstance(leader, dict):
            continue

        # Get leader ID
        leader_id = leader.get("id")
        try:
            leader_id_int = int(leader_id) if leader_id is not None else None
        except (ValueError, TypeError):
            continue

        if leader_id_int is None:
            continue

        # Check if this leader is the ruler
        # Primary: use the ruler field from country entry (exact match)
        # Fallback: class == "official" (for cases where country entry unavailable)
        leader_class = leader.get("class")
        if actual_ruler_id is not None:
            is_ruler = leader_id_int == actual_ruler_id
        else:
            is_ruler = leader_class == "official"

        # Build normalized leader entry
        entry: dict[str, Any] = {
            "id": leader_id_int,
            "class": leader_class,
            "level": leader.get("level"),
            "is_ruler": is_ruler,
        }

        # Name resolution: 'name' field from get_leaders() is already resolved
        # when Rust session is active (via _extract_leader_name_rust)
        resolved_name = leader.get("name")
        if resolved_name:
            entry["name"] = resolved_name

        # Track ruler at top level for easy diff detection
        if is_ruler:
            ruler_id = leader_id_int
            ruler_name = resolved_name

        # Keep name_key for debugging/localization (extract from raw data if available)
        # This would be the %LEADER_N% or NAME_* key before resolution
        name_key = leader.get("name_key")
        if name_key:
            entry["name_key"] = name_key

        # Date fields for history diffing (hire/death events)
        # These may be null/missing depending on leader state
        for date_field in ("death_date", "date_added", "recruitment_date"):
            date_val = leader.get(date_field)
            if date_val:
                entry[date_field] = date_val

        normalized.append(entry)

    return {
        "count": len(normalized),
        "leaders": normalized,
        "ruler_id": ruler_id,
        "ruler_name": ruler_name,
    }


def _clean_war_name_part(raw: str) -> str:
    """Clean a war name part by removing prefixes and formatting.

    Args:
        raw: Raw name string (e.g., "SPEC_Ubaric", "PRESCRIPTED_adjective_humans1")

    Returns:
        Cleaned, human-readable string
    """
    if not raw:
        return ""

    result = raw

    # Remove common prefixes
    for prefix in ("SPEC_", "ADJ_", "NAME_", "PRESCRIPTED_adjective_", "PRESCRIPTED_"):
        if result.startswith(prefix):
            result = result[len(prefix) :]
            break

    # Handle specific patterns like "humans1" -> "Human"
    # These are species prefixes followed by a number
    import re

    species_match = re.match(r"^([a-zA-Z]+)(\d+)$", result)
    if species_match:
        result = species_match.group(1).title()

    # Convert underscores to spaces
    result = result.replace("_", " ").strip()

    # Title case if all lowercase
    if result.islower():
        result = result.title()

    return result


def _extract_nested_value(value_block: dict[str, Any]) -> str:
    """Recursively extract a resolved value from a nested name block.

    War names can have deeply nested structures like:
    {key: "PRESCRIPTED_adjective_humans1", variables: [{key: "1", value: {key: "Secessionist_War"}}]}

    Args:
        value_block: Nested value dict with key and optional variables

    Returns:
        Best resolved value from the nested structure
    """
    if not isinstance(value_block, dict):
        return str(value_block) if value_block else ""

    key = value_block.get("key", "")
    variables = value_block.get("variables", [])

    # If this key starts with %, it needs resolution from variables
    if isinstance(key, str) and key.startswith("%") and key.endswith("%"):
        # Look for variable values
        if isinstance(variables, list):
            for var in variables:
                if isinstance(var, dict):
                    nested_value = var.get("value")
                    if isinstance(nested_value, dict):
                        return _extract_nested_value(nested_value)
                    elif nested_value:
                        return _clean_war_name_part(str(nested_value))
        return ""

    # Check for nested variables that might have the actual value
    if isinstance(variables, list) and variables:
        nested_parts: list[str] = []

        # Look for adjective variable (common in war names)
        for var in variables:
            if not isinstance(var, dict):
                continue
            var_key = var.get("key")
            nested_value = var.get("value")

            if var_key == "adjective" and isinstance(nested_value, dict):
                adj_key = nested_value.get("key", "")
                if adj_key:
                    return _clean_war_name_part(adj_key)

            # For numbered keys, extract values
            if isinstance(var_key, str) and var_key.isdigit():
                if isinstance(nested_value, dict):
                    extracted = _extract_nested_value(nested_value)
                    if extracted:
                        nested_parts.append(extracted)
                elif nested_value:
                    nested_parts.append(_clean_war_name_part(str(nested_value)))

        # If we found nested parts, return them combined
        if nested_parts:
            # Common pattern: adjective + war type -> "Human Secessionist War"
            cleaned_key = _clean_war_name_part(key)
            if cleaned_key and not cleaned_key.startswith("%"):
                return f"{cleaned_key} {' '.join(nested_parts)}"
            return " ".join(nested_parts)

    # Return the key itself, cleaned up
    return _clean_war_name_part(key)


def _resolve_war_name_from_block(name_block: Any) -> str | None:
    """Resolve a war name from its name block structure.

    War names in Stellaris saves can be:
    - Simple strings: "War Name"
    - Complex nested structures with localization keys and variables:
      {key="war_vs_adjectives", variables=[{key="1", value={key="%ADJECTIVE%", variables=[...]}}]}
      {key="%ADJ%", variables=[{key="1", value={key="PRESCRIPTED_adjective_humans1", variables=[...]}}]}

    Common patterns:
    - war_vs_adjectives: "{adj1}-{adj2} {suffix}" (e.g., "Ubaric-Ziiran War")
    - %ADJ%: Placeholder that needs resolution from nested variables

    Args:
        name_block: The name field from war data (dict or string)

    Returns:
        Human-readable war name or None if unresolvable
    """
    if name_block is None:
        return None

    if isinstance(name_block, str):
        return name_block.strip() if name_block.strip() else None

    if not isinstance(name_block, dict):
        return None

    key = name_block.get("key", "")
    variables = name_block.get("variables", [])

    # Extract resolved values from variables
    values: dict[str, str] = {}
    if isinstance(variables, list):
        for var in variables:
            if not isinstance(var, dict):
                continue
            var_key = var.get("key")
            if var_key is None:
                continue

            value_block = var.get("value")
            if isinstance(value_block, dict):
                # Recursively extract the resolved value
                resolved = _extract_nested_value(value_block)
                values[str(var_key)] = resolved
            elif value_block is not None:
                values[str(var_key)] = _clean_war_name_part(str(value_block))

    # Resolve based on known patterns
    if key == "war_vs_adjectives":
        # Pattern: "{1}-{2} {3}" where 1 and 2 are adjectives, 3 is suffix (usually "War")
        adj1 = values.get("1", "?")
        adj2 = values.get("2", "?")
        suffix = values.get("3", "War")
        return f"{adj1}-{adj2} {suffix}"

    # Check if key itself is a placeholder that needs resolution
    if key.startswith("%") and key.endswith("%"):
        # Try to resolve from variables
        # Common pattern: %ADJ% with variable 1 containing the value(s)
        if values.get("1"):
            return values["1"]
        # Return first available value
        for v in values.values():
            if v and isinstance(v, str) and v.strip():
                return v.strip()
        return None

    # Key might be a localization key we can't resolve but values provide context
    # Construct a readable name from available parts
    if values:
        # Try numbered keys in order
        parts = []
        for i in range(1, 10):
            val = values.get(str(i))
            if val and val.strip():
                parts.append(val.strip())
        if parts:
            return " ".join(parts)

    # Return the key itself if it looks like a real name (not a localization key)
    if key and not key.startswith("%") and "_" not in key[:4]:
        return key

    return None


def _extract_war_signals(extractor: SaveExtractor) -> dict[str, Any]:
    """Extract normalized war data for history diffing.

    Uses extractor.get_wars() which provides structured war data
    including participants, war goals, and exhaustion values.

    Also attempts to resolve war name placeholders like %ADJ% to produce
    human-readable names like "Ubaric-Ziiran War" for Chronicle.

    Returns:
        Dict with:
        - player_at_war: bool
        - count: int
        - wars: list of war names (for event detection diff)
    """
    raw = extractor.get_wars()

    if not isinstance(raw, dict):
        return {"player_at_war": False, "count": 0, "wars": []}

    player_at_war = bool(raw.get("player_at_war", False))
    raw_wars = raw.get("wars", [])

    if not isinstance(raw_wars, list):
        return {"player_at_war": player_at_war, "count": 0, "wars": []}

    # First get war names and battle locations from the extractor (already processed)
    war_names: list[str] = []
    battle_locations: dict[str, list[str]] = {}  # war_name -> top system names
    for war in raw_wars:
        if not isinstance(war, dict):
            continue
        name = war.get("name")
        if name and isinstance(name, str) and name.strip():
            clean_name = name.strip()
            war_names.append(clean_name)
            # Extract top battle system names for this war
            stats = war.get("battle_stats", {})
            if isinstance(stats, dict):
                locs = stats.get("battle_locations", [])
                if isinstance(locs, list):
                    sys_names = [
                        loc.get("system")
                        for loc in locs[:3]
                        if isinstance(loc, dict) and loc.get("system")
                    ]
                    if sys_names:
                        battle_locations[clean_name] = sys_names

    # Try to resolve placeholder names by accessing raw war data directly
    # This is done when Rust session is active
    try:
        from stellaris_companion.rust_bridge import _get_active_session

        session = _get_active_session()
        if session:
            resolved_names = _resolve_war_names_from_raw(extractor, session)
            if resolved_names:
                war_names = resolved_names
    except ImportError:
        pass

    return {
        "player_at_war": player_at_war,
        "count": len(war_names),
        "wars": war_names,
        "battle_locations": battle_locations,
    }


def _resolve_war_names_from_raw(extractor: SaveExtractor, session) -> list[str]:
    """Resolve war names from raw war data using Rust session.

    Accesses war section directly to get full name blocks with variables,
    allowing resolution of placeholders like %ADJ%.

    Args:
        extractor: SaveExtractor instance
        session: Active Rust session

    Returns:
        List of resolved war names for player wars
    """
    try:
        from stellaris_companion.rust_bridge import iter_section_entries

        player_id = extractor.get_player_empire_id()
        player_id_str = str(player_id)

        resolved_names: list[str] = []

        for war_id, war_data in iter_section_entries(extractor.save_path, "war"):
            if not isinstance(war_data, dict):
                continue

            # Check if player is involved in this war
            attacker_ids: list[str] = []
            attackers = war_data.get("attackers", [])
            if isinstance(attackers, list):
                for attacker in attackers:
                    if isinstance(attacker, dict):
                        country = attacker.get("country")
                        if country is not None:
                            attacker_ids.append(str(country))

            defender_ids: list[str] = []
            defenders = war_data.get("defenders", [])
            if isinstance(defenders, list):
                for defender in defenders:
                    if isinstance(defender, dict):
                        country = defender.get("country")
                        if country is not None:
                            defender_ids.append(str(country))

            if player_id_str not in attacker_ids and player_id_str not in defender_ids:
                continue

            # Resolve war name from name block
            name_block = war_data.get("name")
            resolved = _resolve_war_name_from_block(name_block)

            if resolved:
                resolved_names.append(resolved)
            else:
                # Fallback to war ID
                resolved_names.append(f"War #{war_id}")

        return resolved_names

    except Exception:
        return []


def _extract_diplomacy_signals(extractor: SaveExtractor) -> dict[str, Any]:
    """Extract normalized diplomacy data for history diffing.

    Uses extractor.get_diplomacy() which provides comprehensive diplomatic data
    including allies, rivals, and various treaty types.

    Returns format compatible with events.py _extract_diplomacy_sets():
        Dict with:
        - player_id: int
        - allies: list of country IDs (sorted)
        - rivals: list of country IDs (sorted)
        - treaties: dict mapping treaty type to list of country IDs
        - empire_names: dict mapping country_id to empire name (for event summaries)
    """
    raw = extractor.get_diplomacy()

    if not isinstance(raw, dict):
        return {
            "player_id": None,
            "allies": [],
            "rivals": [],
            "treaties": {},
            "empire_names": {},
        }

    # Extract player ID from extractor
    try:
        player_id = extractor.get_player_empire_id()
    except Exception:
        player_id = None

    # Collect empire names from all diplomatic relations
    # get_diplomacy() returns {id, name} dicts for allies, rivals, etc.
    empire_names: dict[int, str] = {}

    def collect_empire_names(items: Any) -> None:
        """Collect empire names from list of {id, name} dicts."""
        if not isinstance(items, list):
            return
        for item in items:
            if isinstance(item, dict):
                cid = item.get("id")
                name = item.get("name")
                if cid is not None and name and isinstance(name, str):
                    try:
                        empire_names[int(cid)] = name
                    except (ValueError, TypeError):
                        continue

    # Collect names from all sources that have {id, name} format
    collect_empire_names(raw.get("allies", []))
    collect_empire_names(raw.get("rivals", []))
    collect_empire_names(raw.get("defensive_pacts", []))
    collect_empire_names(raw.get("non_aggression_pacts", []))
    collect_empire_names(raw.get("commercial_pacts", []))
    collect_empire_names(raw.get("migration_treaties", []))
    collect_empire_names(raw.get("sensor_links", []))
    collect_empire_names(raw.get("closed_borders", []))

    # Also collect from relations list which has more contacts
    relations = raw.get("relations", [])
    if isinstance(relations, list):
        for rel in relations:
            if isinstance(rel, dict):
                cid = rel.get("country_id")
                name = rel.get("empire_name")
                if cid is not None and name and isinstance(name, str):
                    try:
                        empire_names[int(cid)] = name
                    except (ValueError, TypeError):
                        continue

    # Helper to extract country IDs from list of {id, name} dicts
    def extract_ids(items: Any) -> list[int]:
        if not isinstance(items, list):
            return []
        ids: list[int] = []
        for item in items:
            if isinstance(item, dict):
                cid = item.get("id")
                if cid is not None:
                    try:
                        ids.append(int(cid))
                    except (ValueError, TypeError):
                        continue
            elif isinstance(item, (int, str)):
                try:
                    ids.append(int(item))
                except (ValueError, TypeError):
                    continue
        return sorted(ids)

    # Extract allies and rivals as sorted ID lists
    allies = extract_ids(raw.get("allies", []))
    rivals = extract_ids(raw.get("rivals", []))

    # Build treaties dict matching history.py format
    # Maps treaty type to list of country IDs
    treaties: dict[str, list[int]] = {}

    # Map from get_diplomacy() keys to treaty type names used in events.py
    treaty_mappings = [
        ("defensive_pacts", "defensive_pact"),
        ("non_aggression_pacts", "non_aggression_pact"),
        ("commercial_pacts", "commercial_pact"),
        ("migration_treaties", "migration_treaty"),
        ("sensor_links", "sensor_link"),
    ]

    for source_key, treaty_name in treaty_mappings:
        ids = extract_ids(raw.get(source_key, []))
        if ids:
            treaties[treaty_name] = ids

    # Also check treaties list for research_agreement and embassy
    # which may not have their own top-level keys
    raw_treaties = raw.get("treaties", [])
    if isinstance(raw_treaties, list):
        research_ids: list[int] = []
        embassy_ids: list[int] = []
        truce_ids: list[int] = []

        for t in raw_treaties:
            if not isinstance(t, dict):
                continue
            treaty_type = t.get("type")
            cid = t.get("country_id")
            if treaty_type and cid is not None:
                try:
                    cid_int = int(cid)
                    if treaty_type == "research_agreement":
                        research_ids.append(cid_int)
                    elif treaty_type == "embassy":
                        embassy_ids.append(cid_int)
                    elif treaty_type == "truce":
                        truce_ids.append(cid_int)
                except (ValueError, TypeError):
                    continue

        if research_ids:
            treaties["research_agreement"] = sorted(set(research_ids))
        if embassy_ids:
            treaties["embassy"] = sorted(set(embassy_ids))
        if truce_ids:
            treaties["truce"] = sorted(set(truce_ids))

    # Extract list of all known empire IDs for first contact detection
    # This includes all empires we have any relation entry with
    known_empire_ids: list[int] = sorted(empire_names.keys())

    # Convert int keys to strings for JSON serialization (orjson requires str keys)
    str_names = {str(k): v for k, v in empire_names.items()}

    return {
        "player_id": player_id,
        "allies": allies,
        "rivals": rivals,
        "treaties": treaties,
        "empire_names": str_names,
        "known_empire_ids": known_empire_ids,
    }


def _extract_subjects_signals(extractor: SaveExtractor) -> dict[str, Any]:
    """Extract normalized subject/vassal data for history diffing.

    Uses extractor.get_subjects() which provides Overlord DLC agreement data
    including subjects we control and overlords we serve.

    Returns format compatible with events.py get_subject_sets():
        Dict with:
        - as_overlord: sorted list of country IDs (our subjects)
        - as_subject: sorted list of country IDs (our overlords)
        - subject_details: dict mapping country_id to {preset, specialization}
        - empire_names: dict mapping country_id to empire name
    """
    with contextlib.suppress(Exception):
        raw = extractor.get_subjects()

        if not isinstance(raw, dict):
            return {"as_overlord": [], "as_subject": [], "subject_details": {}, "empire_names": {}}

        overlord_data = raw.get("as_overlord")
        subject_data = raw.get("as_subject")

        overlord_ids: list[int] = []
        subject_ids: list[int] = []
        details: dict[int, dict[str, Any]] = {}
        empire_names: dict[int, str] = {}

        # Extract IDs and details from agreements where we are overlord
        if isinstance(overlord_data, dict):
            subjects_list = overlord_data.get("subjects", [])
            if isinstance(subjects_list, list):
                for entry in subjects_list:
                    if not isinstance(entry, dict):
                        continue
                    target_id = entry.get("target_id")
                    if target_id is None:
                        continue
                    try:
                        cid = int(target_id)
                    except (ValueError, TypeError):
                        continue
                    overlord_ids.append(cid)
                    preset = entry.get("preset")
                    specialization = entry.get("specialization")
                    if preset or specialization:
                        detail: dict[str, Any] = {}
                        if preset and isinstance(preset, str):
                            detail["preset"] = preset
                        if specialization and isinstance(specialization, str):
                            detail["specialization"] = specialization
                        details[cid] = detail

        # Extract IDs from agreements where we are subject
        if isinstance(subject_data, dict):
            overlords_list = subject_data.get("overlords", [])
            if isinstance(overlords_list, list):
                for entry in overlords_list:
                    if not isinstance(entry, dict):
                        continue
                    owner_id = entry.get("owner_id")
                    if owner_id is None:
                        continue
                    try:
                        cid = int(owner_id)
                    except (ValueError, TypeError):
                        continue
                    subject_ids.append(cid)
                    preset = entry.get("preset")
                    if preset and isinstance(preset, str):
                        detail = {"preset": preset}
                        specialization = entry.get("specialization")
                        if specialization and isinstance(specialization, str):
                            detail["specialization"] = specialization
                        details[cid] = detail

        # Convert int keys to strings for JSON serialization (orjson requires str keys)
        str_details = {str(k): v for k, v in details.items()}
        str_names = {str(k): v for k, v in empire_names.items()}

        return {
            "as_overlord": sorted(overlord_ids),
            "as_subject": sorted(subject_ids),
            "subject_details": str_details,
            "empire_names": str_names,
        }

    return {"as_overlord": [], "as_subject": [], "subject_details": {}, "empire_names": {}}


def _extract_technology_signals(extractor: SaveExtractor) -> dict[str, Any]:
    """Extract normalized technology data for history diffing.

    Uses extractor.get_technology() which provides comprehensive tech data
    including researched techs, in-progress, and available.

    Returns format compatible with events.py _extract_tech_list():
        Dict with:
        - player_id: int | None
        - techs: sorted list of completed tech names
        - count: number of completed techs
        - in_progress: list of {id, category, progress} for current research
    """
    raw = extractor.get_technology()

    if not isinstance(raw, dict):
        return {
            "player_id": None,
            "techs": [],
            "count": 0,
            "in_progress": [],
        }

    # Extract player ID
    try:
        player_id = extractor.get_player_empire_id()
    except Exception:
        player_id = None

    # Get completed technologies
    researched = raw.get("researched_techs", [])
    if not isinstance(researched, list):
        researched = []

    # Ensure all are strings and sort
    techs = sorted([str(t) for t in researched if t])

    # Extract in-progress research
    in_progress_raw = raw.get("in_progress", {})
    in_progress: list[dict[str, Any]] = []

    if isinstance(in_progress_raw, dict):
        for category in ("physics", "society", "engineering"):
            current = in_progress_raw.get(category)
            if isinstance(current, dict) and current.get("tech"):
                in_progress.append(
                    {
                        "id": current.get("tech"),
                        "category": category,
                        "progress": current.get("progress", 0),
                    }
                )

    return {
        "player_id": player_id,
        "techs": techs,
        "count": len(techs),
        "in_progress": in_progress,
    }


def _extract_megastructures_signals(extractor: SaveExtractor) -> dict[str, Any]:
    """Extract normalized megastructures data for history diffing.

    Uses extractor.get_megastructures() which provides comprehensive megastructure data
    including type, status, and ownership.

    Returns format compatible with events.py _extract_megastructures():
        Dict with:
        - player_id: int | None
        - megastructures: list of dicts with id, type, stage
        - count: number of player megastructures
        - by_type: dict mapping type to count
    """
    raw = extractor.get_megastructures()

    if not isinstance(raw, dict):
        return {
            "player_id": None,
            "megastructures": [],
            "count": 0,
            "by_type": {},
        }

    # Extract player ID
    try:
        player_id = extractor.get_player_empire_id()
    except Exception:
        player_id = None

    raw_megas = raw.get("megastructures", [])
    if not isinstance(raw_megas, list):
        raw_megas = []

    # Normalize megastructures for events.py compatibility
    normalized: list[dict[str, Any]] = []

    for mega in raw_megas:
        if not isinstance(mega, dict):
            continue

        mega_id = mega.get("id")
        try:
            mega_id_int = int(mega_id) if mega_id is not None else None
        except (ValueError, TypeError):
            continue

        if mega_id_int is None:
            continue

        mega_type = mega.get("type", "")

        # Derive stage from type suffix (e.g., _0, _1, _2, _3, _4, _5)
        # Complete megastructures have no numeric suffix
        stage = 0
        if isinstance(mega_type, str):
            for i in range(6):
                if mega_type.endswith(f"_{i}"):
                    stage = i
                    break
            if "_site" in mega_type:
                stage = 0
            elif "_restored" in mega_type or "ruined" not in mega_type:
                # Check if it's a complete megastructure (no stage suffix)
                if not any(mega_type.endswith(f"_{i}") for i in range(6)):
                    if "_site" not in mega_type:
                        # Complete megastructure typically at stage 5
                        stage = 5

        entry: dict[str, Any] = {
            "id": mega_id_int,
            "type": mega_type,
            "stage": stage,
        }

        # Include display_type and status if available (useful for UI)
        if mega.get("display_type"):
            entry["display_type"] = mega.get("display_type")
        if mega.get("status"):
            entry["status"] = mega.get("status")
        if mega.get("planet_id"):
            entry["planet_id"] = mega.get("planet_id")

        normalized.append(entry)

    # Get by_type counts from raw data
    by_type = raw.get("by_type", {})
    if not isinstance(by_type, dict):
        by_type = {}

    return {
        "player_id": player_id,
        "megastructures": normalized,
        "count": len(normalized),
        "by_type": by_type,
    }


def _extract_crisis_signals(extractor: SaveExtractor) -> dict[str, Any]:
    """Extract normalized crisis status for history diffing.

    Uses extractor.get_crisis_status() which provides comprehensive crisis data
    including crisis type, active factions, and player involvement.

    Returns format compatible with events.py _extract_crisis():
        Dict with:
        - active: bool (whether a crisis has spawned)
        - type: str | None (prethoryn, contingency, unbidden, etc.)
        - progress: int | None (crisis systems count as a proxy for progress)
        - player_is_crisis_fighter: bool
        - player_crisis_kills: int
        - crisis_countries: list of {country_id, type}
    """
    raw = extractor.get_crisis_status()

    if not isinstance(raw, dict):
        return {
            "active": False,
            "type": None,
            "progress": None,
        }

    # Normalize to format expected by events.py
    # events.py checks: crisis.get("active") and crisis.get("type")
    active = bool(raw.get("crisis_active", False))
    crisis_type = raw.get("crisis_type")

    result: dict[str, Any] = {
        "active": active,
        "type": crisis_type,
    }

    # Include crisis systems count as progress indicator
    crisis_systems = raw.get("crisis_systems_count")
    if crisis_systems is not None:
        try:
            result["progress"] = int(crisis_systems)
        except (ValueError, TypeError):
            result["progress"] = None

    # Include additional details useful for narrative/reporting
    if raw.get("player_is_crisis_fighter"):
        result["player_is_crisis_fighter"] = True

    player_kills = raw.get("player_crisis_kills")
    if player_kills:
        with contextlib.suppress(ValueError, TypeError):
            result["player_crisis_kills"] = int(player_kills)

    # Include crisis country info for detailed reporting
    crisis_countries = raw.get("crisis_countries", [])
    if isinstance(crisis_countries, list) and crisis_countries:
        result["crisis_countries"] = crisis_countries

    # Include all detected crisis types if multiple (e.g., aberrant + vehement)
    crisis_types = raw.get("crisis_types_detected", [])
    if isinstance(crisis_types, list) and len(crisis_types) > 1:
        result["crisis_types_detected"] = crisis_types

    return result


def _extract_fallen_empires_signals(extractor: SaveExtractor) -> dict[str, Any]:
    """Extract normalized fallen empires data for history diffing.

    Uses extractor.get_fallen_empires() which provides comprehensive data
    about dormant and awakened fallen empires in the galaxy.

    Returns format compatible with events.py _extract_fallen_empires():
        Dict with:
        - fallen_empires: list of dicts with name, status, ethics, military_power, archetype
        - dormant_count: int
        - awakened_count: int
        - war_in_heaven: bool
    """
    raw = extractor.get_fallen_empires()

    if not isinstance(raw, dict):
        return {
            "fallen_empires": [],
            "dormant_count": 0,
            "awakened_count": 0,
            "war_in_heaven": False,
        }

    # Extract fallen empires list
    raw_fe_list = raw.get("fallen_empires", [])
    if not isinstance(raw_fe_list, list):
        raw_fe_list = []

    # Normalize to format expected by events.py _extract_fallen_empires()
    # events.py keys by name and checks: status, archetype, military_power, ethics
    normalized: list[dict[str, Any]] = []

    for fe in raw_fe_list:
        if not isinstance(fe, dict):
            continue

        # Get name - required field for events.py keying
        name = fe.get("name")
        if not name:
            continue

        entry: dict[str, Any] = {
            "name": name,
            "status": fe.get("status", "dormant"),
            "archetype": fe.get("archetype", "Unknown"),
        }

        # Include military power if available
        mil_power = fe.get("military_power")
        if mil_power is not None:
            with contextlib.suppress(ValueError, TypeError):
                entry["military_power"] = float(mil_power)

        # Include ethics if available
        ethics = fe.get("ethics")
        if ethics is not None:
            # May be a string or list depending on source
            if isinstance(ethics, list):
                entry["ethics"] = ethics
            elif isinstance(ethics, str):
                entry["ethics"] = [ethics]

        # Include country_id for detailed tracking (useful for events/narrative)
        cid = fe.get("country_id")
        if cid is not None:
            with contextlib.suppress(ValueError, TypeError):
                entry["country_id"] = int(cid)

        normalized.append(entry)

    # Get counts from raw data or compute from normalized list
    dormant_count = raw.get("dormant_count")
    if dormant_count is None:
        dormant_count = sum(1 for fe in normalized if fe.get("status") == "dormant")
    else:
        try:
            dormant_count = int(dormant_count)
        except (ValueError, TypeError):
            dormant_count = 0

    awakened_count = raw.get("awakened_count")
    if awakened_count is None:
        awakened_count = sum(1 for fe in normalized if fe.get("status") == "awakened")
    else:
        try:
            awakened_count = int(awakened_count)
        except (ValueError, TypeError):
            awakened_count = 0

    # War in Heaven detection
    war_in_heaven = bool(raw.get("war_in_heaven", False))

    return {
        "fallen_empires": normalized,
        "dormant_count": dormant_count,
        "awakened_count": awakened_count,
        "war_in_heaven": war_in_heaven,
    }


def _extract_policies_signals(extractor: SaveExtractor) -> dict[str, Any]:
    """Extract normalized policies data for history diffing.

    Uses Rust-parsed player country entry which contains active_policies
    as a list of {policy, selected} dicts.

    Returns format compatible with events.py _extract_policies():
        Dict with:
        - player_id: int | None
        - policies: dict mapping policy name to selected value
        - count: int
    """
    # Get player ID
    try:
        player_id = extractor.get_player_empire_id()
    except Exception:
        player_id = None

    # Get player country entry from Rust session
    country = extractor._get_player_country_entry(player_id or 0)
    if not isinstance(country, dict):
        return {
            "player_id": player_id,
            "policies": {},
            "count": 0,
        }

    # Extract active_policies list
    active_policies = country.get("active_policies", [])
    if not isinstance(active_policies, list):
        return {
            "player_id": player_id,
            "policies": {},
            "count": 0,
        }

    # Convert to {policy_name: selected_value} format matching history.py
    policies: dict[str, str] = {}
    for p in active_policies:
        if not isinstance(p, dict):
            continue
        policy_name = p.get("policy")
        selected = p.get("selected")
        if policy_name and selected and isinstance(policy_name, str) and isinstance(selected, str):
            policies[policy_name] = selected

    return {
        "player_id": player_id,
        "policies": policies,
        "count": len(policies),
    }


def _extract_edicts_signals(extractor: SaveExtractor) -> dict[str, Any]:
    """Extract normalized edicts data for history diffing.

    Uses Rust-parsed player country entry which contains edicts
    as a list of {edict, date, perpetual, start_date} dicts.

    Returns format compatible with events.py _extract_edicts():
        Dict with:
        - player_id: int | None
        - edicts: sorted list of active edict names
        - count: int
    """
    # Get player ID
    try:
        player_id = extractor.get_player_empire_id()
    except Exception:
        player_id = None

    # Get player country entry from Rust session
    country = extractor._get_player_country_entry(player_id or 0)
    if not isinstance(country, dict):
        return {
            "player_id": player_id,
            "edicts": [],
            "count": 0,
        }

    # Extract edicts list
    raw_edicts = country.get("edicts", [])
    if not isinstance(raw_edicts, list):
        return {
            "player_id": player_id,
            "edicts": [],
            "count": 0,
        }

    # Extract edict names
    edict_names: list[str] = []
    for ed in raw_edicts:
        if not isinstance(ed, dict):
            continue
        edict_name = ed.get("edict")
        if edict_name and isinstance(edict_name, str):
            edict_names.append(edict_name)

    # Sort and dedupe
    unique_edicts = sorted(set(edict_names))

    return {
        "player_id": player_id,
        "edicts": unique_edicts,
        "count": len(unique_edicts),
    }


def _extract_galaxy_settings_signals(extractor: SaveExtractor) -> dict[str, Any]:
    """Extract galaxy settings for milestone events and game phase detection.

    Uses Rust session extract_sections(['galaxy']) for fast parsed lookup.
    These are static per game (set at galaxy generation) but needed for:
    - Midgame/endgame milestone events
    - Victory year detection
    - Difficulty and ironman mode indicators

    Returns format compatible with history.py extract_galaxy_settings_from_gamestate():
        Dict with:
        - galaxy_name: str | None (galaxy UUID used for campaign identification)
        - mid_game_start: int | None (years after 2200 when midgame starts)
        - end_game_start: int | None (years after 2200 when endgame starts)
        - victory_year: int | None (year when victory is calculated)
        - ironman: str | None ('yes' or None)
        - difficulty: str | None (difficulty setting name)
        - crisis_type: str | None (pre-selected crisis if any)
    """
    # Try to use Rust session for fast parsed lookup
    try:
        from stellaris_companion.rust_bridge import _get_active_session

        session = _get_active_session()
        if session:
            return _extract_galaxy_settings_rust(session)
    except ImportError:
        pass

    # No session available - return empty (gamestate fallback in history.py)
    return {}


def _extract_galaxy_settings_rust(session) -> dict[str, Any]:
    """Extract galaxy settings using Rust session's extract_sections.

    Args:
        session: Active RustSession instance

    Returns:
        Galaxy settings dict
    """
    try:
        sections = session.extract_sections(["galaxy"])
        galaxy = sections.get("galaxy", {})

        if not isinstance(galaxy, dict):
            return {}

        # Helper to safely get int value
        def _safe_int(val: Any) -> int | None:
            if val is None:
                return None
            try:
                return int(val)
            except (ValueError, TypeError):
                return None

        # Helper to safely get str value
        def _safe_str(val: Any) -> str | None:
            if val is None:
                return None
            if isinstance(val, str) and val.strip():
                return val.strip()
            return None

        return {
            "galaxy_name": _safe_str(galaxy.get("name")),
            "mid_game_start": _safe_int(galaxy.get("mid_game_start")),
            "end_game_start": _safe_int(galaxy.get("end_game_start")),
            "victory_year": _safe_int(galaxy.get("victory_year")),
            "ironman": _safe_str(galaxy.get("ironman")),
            "difficulty": _safe_str(galaxy.get("difficulty")),
            "crisis_type": _safe_str(galaxy.get("crisis_type")),
        }
    except Exception:
        # On any error, return empty dict (gamestate fallback in history.py)
        return {}


def _extract_systems_signals(extractor: SaveExtractor) -> dict[str, Any]:
    """Extract systems count for the player empire.

    Uses extractor.get_starbases() which is already Rust-backed.
    Each starbase represents a controlled system, so the starbase count
    gives us the player's system count.

    Returns format compatible with events.py _extract_system_count():
        Dict with:
        - player_id: int | None
        - count: int (number of controlled systems)
        - by_level: dict mapping starbase level to count
    """
    # Get player ID
    try:
        player_id = extractor.get_player_empire_id()
    except Exception:
        player_id = None

    # Get starbases data - each starbase represents a controlled system
    raw = extractor.get_starbases()

    if not isinstance(raw, dict):
        return {
            "player_id": player_id,
            "count": 0,
            "by_level": {},
        }

    # Get count from starbases data
    count = raw.get("count", 0)
    try:
        count = int(count)
    except (ValueError, TypeError):
        count = 0

    # Get breakdown by starbase level (useful for expansion milestones)
    by_level = raw.get("by_level", {})
    if not isinstance(by_level, dict):
        by_level = {}

    return {
        "player_id": player_id,
        "count": count,
        "by_level": by_level,
    }


def _extract_ascension_perks_signals(extractor: SaveExtractor) -> dict[str, Any]:
    """Extract ascension perks for chronicle events.

    Uses extractor.get_ascension_perks() which provides the list of
    selected ascension perks for the player empire.

    Returns:
        Dict with:
        - perks: list of ascension perk IDs (e.g., ['ap_synthetic_evolution', ...])
        - count: number of perks selected
    """
    try:
        raw = extractor.get_ascension_perks()
        if not isinstance(raw, dict):
            return {"perks": [], "count": 0}

        # Note: extractor returns 'ascension_perks', we normalize to 'perks'
        perks = raw.get("ascension_perks", [])
        if not isinstance(perks, list):
            perks = []

        return {
            "perks": perks,
            "count": len(perks),
        }
    except Exception:
        return {"perks": [], "count": 0}


def _extract_lgate_signals(extractor: SaveExtractor) -> dict[str, Any]:
    """Extract L-Gate status for chronicle events.

    Uses extractor.get_lgate_status() which provides L-Gate and L-Cluster
    information including whether the L-Gate has been opened.

    Returns:
        Dict with:
        - enabled: whether L-Gates exist in the galaxy
        - opened: whether L-Gate has been opened (major event)
        - insights_collected: number of L-Gate insights found
        - insights_required: usually 7
    """
    try:
        raw = extractor.get_lgate_status()
        if not isinstance(raw, dict):
            return {
                "enabled": False,
                "opened": False,
                "insights_collected": 0,
                "insights_required": 7,
            }

        return {
            "enabled": bool(raw.get("lgate_enabled", False)),
            "opened": bool(raw.get("lgate_opened", False)),
            "insights_collected": raw.get("insights_collected", 0),
            "insights_required": raw.get("insights_required", 7),
        }
    except Exception:
        return {"enabled": False, "opened": False, "insights_collected": 0, "insights_required": 7}


def _extract_menace_signals(extractor: SaveExtractor) -> dict[str, Any]:
    """Extract menace/Become the Crisis status for chronicle events.

    Uses extractor.get_menace() which provides crisis perk status and
    menace level for empires pursuing the Become the Crisis path.

    Returns:
        Dict with:
        - has_crisis_perk: whether player has Become the Crisis perk
        - menace_level: current menace accumulated (0 if no perk)
        - crisis_level: crisis ascension tier 0-5 (0 if no perk)
    """
    try:
        raw = extractor.get_menace()
        if not isinstance(raw, dict):
            return {"has_crisis_perk": False, "menace_level": 0, "crisis_level": 0}

        return {
            "has_crisis_perk": bool(raw.get("has_crisis_perk", False)),
            "menace_level": raw.get("menace_level", 0),
            "crisis_level": raw.get("crisis_level", 0),
        }
    except Exception:
        return {"has_crisis_perk": False, "menace_level": 0, "crisis_level": 0}


def _extract_great_khan_signals(extractor: SaveExtractor) -> dict[str, Any]:
    """Extract Great Khan / Marauder status for chronicle events.

    Uses extractor.get_great_khan() which provides Great Khan status
    including whether the Khan has spawned and their current state.

    Returns:
        Dict with:
        - marauders_present: whether marauder empires exist in the galaxy
        - marauder_count: number of marauder factions (0-3)
        - khan_risen: whether the Great Khan has spawned (at any point)
        - khan_status: current state ('active', 'defeated', or None)
        - khan_country_id: country ID of the Khan's empire if active
    """
    try:
        raw = extractor.get_great_khan()
        if not isinstance(raw, dict):
            return {
                "marauders_present": False,
                "marauder_count": 0,
                "khan_risen": False,
                "khan_status": None,
                "khan_country_id": None,
            }

        return {
            "marauders_present": bool(raw.get("marauders_present", False)),
            "marauder_count": raw.get("marauder_count", 0),
            "khan_risen": bool(raw.get("khan_risen", False)),
            "khan_status": raw.get("khan_status"),
            "khan_country_id": raw.get("khan_country_id"),
        }
    except Exception:
        return {
            "marauders_present": False,
            "marauder_count": 0,
            "khan_risen": False,
            "khan_status": None,
            "khan_country_id": None,
        }


def _extract_galactic_community_signals(extractor: SaveExtractor) -> dict[str, Any]:
    """Extract Galactic Community status for chronicle events.

    Uses extractor.get_galactic_community() which provides Galactic Community
    membership and council status for the player empire.

    Returns:
        Dict with:
        - exists: whether Galactic Community has been formed
        - member: whether player is a member
        - council_member: whether player is on the council
        - members_count: total number of GC members
    """
    try:
        raw = extractor.get_galactic_community()
        if not isinstance(raw, dict):
            return {
                "exists": False,
                "member": False,
                "council_member": False,
                "members_count": 0,
            }

        # Check if GC exists (community_formed field is set when GC is formed)
        exists = bool(raw.get("community_formed"))

        # Player membership status
        member = bool(raw.get("player_is_member", False))

        # Check if player is on the council
        council_member = False
        council_members = raw.get("council_members", [])
        if isinstance(council_members, list):
            player_id = None
            try:
                player_id = extractor.get_player_empire_id()
            except Exception:
                pass
            if player_id is not None:
                council_member = player_id in council_members

        return {
            "exists": exists,
            "member": member,
            "council_member": council_member,
            "members_count": raw.get("members_count", 0),
        }
    except Exception:
        return {
            "exists": False,
            "member": False,
            "council_member": False,
            "members_count": 0,
        }


def _extract_traditions_signals(extractor: SaveExtractor) -> dict[str, Any]:
    """Extract tradition tree completion status for chronicle events.

    Uses extractor.get_traditions() which provides tradition progress
    by tree including finished status.

    Returns:
        Dict with:
        - finished_trees: list of tree names that are fully completed
        - by_tree: dict mapping tree name to {finished: bool}
        - total_traditions: int (total individual traditions picked)
    """
    try:
        raw = extractor.get_traditions()
        if not isinstance(raw, dict):
            return {"finished_trees": [], "by_tree": {}, "total_traditions": 0}

        by_tree_raw = raw.get("by_tree", {})
        if not isinstance(by_tree_raw, dict):
            return {"finished_trees": [], "by_tree": {}, "total_traditions": 0}

        # Extract just the finished status for each tree (we only care about tree completion)
        finished_trees: list[str] = []
        by_tree: dict[str, dict[str, bool]] = {}

        for tree_name, tree_data in by_tree_raw.items():
            if not isinstance(tree_data, dict):
                continue
            is_finished = bool(tree_data.get("finished", False))
            by_tree[tree_name] = {"finished": is_finished}
            if is_finished:
                finished_trees.append(tree_name)

        return {
            "finished_trees": sorted(finished_trees),
            "by_tree": by_tree,
            "total_traditions": raw.get("count", 0),
        }
    except Exception:
        return {"finished_trees": [], "by_tree": {}, "total_traditions": 0}


def _extract_precursor_signals(extractor: SaveExtractor) -> dict[str, Any]:
    """Extract precursor discovery status for chronicle events.

    Uses extractor.get_special_projects() which provides precursor chain
    progress including homeworld discovery status.

    Returns:
        Dict with:
        - discovered_homeworlds: list of precursor keys where homeworld was found
        - precursor_progress: dict mapping precursor key to {name, stage, homeworld_found}
    """
    try:
        raw = extractor.get_special_projects()
        if not isinstance(raw, dict):
            return {"discovered_homeworlds": [], "precursor_progress": {}}

        precursor_progress_raw = raw.get("precursor_progress", {})
        if not isinstance(precursor_progress_raw, dict):
            return {"discovered_homeworlds": [], "precursor_progress": {}}

        # Extract discovered homeworlds and simplified progress
        discovered_homeworlds: list[str] = []
        precursor_progress: dict[str, dict[str, Any]] = {}

        for precursor_key, progress_data in precursor_progress_raw.items():
            if not isinstance(progress_data, dict):
                continue

            homeworld_found = bool(progress_data.get("homeworld_found", False))
            stage = progress_data.get("stage", "not_started")
            name = progress_data.get("name", precursor_key)

            precursor_progress[precursor_key] = {
                "name": name,
                "stage": stage,
                "homeworld_found": homeworld_found,
            }

            if homeworld_found:
                discovered_homeworlds.append(precursor_key)

        return {
            "discovered_homeworlds": sorted(discovered_homeworlds),
            "precursor_progress": precursor_progress,
        }
    except Exception:
        return {"discovered_homeworlds": [], "precursor_progress": {}}


def _extract_geography_signals(extractor: SaveExtractor) -> dict[str, Any]:
    """Extract strategic geography data (border neighbors, chokepoints).

    Uses extractor.get_strategic_geography() which computes spatial
    intelligence from galactic_object data.

    Returns:
        Dict with:
        - border_neighbors: list of {empire_name, empire_id, direction, shared_border_systems}
        - chokepoints: list of {system_name, system_id, friendly_connections, enemy_neighbors}
        - empire_centroid: {x, y} or None
        - total_player_systems: int
    """
    try:
        raw = extractor.get_strategic_geography()
        if not isinstance(raw, dict):
            return {
                "border_neighbors": [],
                "chokepoints": [],
                "empire_centroid": None,
                "total_player_systems": 0,
            }
        return raw
    except Exception:
        return {
            "border_neighbors": [],
            "chokepoints": [],
            "empire_centroid": None,
            "total_player_systems": 0,
        }
