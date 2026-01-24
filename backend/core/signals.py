"""
SnapshotSignals builder for unified history extraction.

Built once per snapshot in ingestion worker (where Rust session is active).
Provides normalized, resolved data for events and chronicle.

Part of Option D: Push Extraction Upstream.
See docs/OPTION_D_UNIFIED_HISTORY_EXTRACTION.md for architecture.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from save_extractor import SaveExtractor

# Schema version for signals payload - increment when structure changes
SIGNALS_FORMAT_VERSION = 1


def build_snapshot_signals(
    *, extractor: "SaveExtractor", briefing: dict[str, Any]
) -> dict[str, Any]:
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

    signals: dict[str, Any] = {
        "format_version": SIGNALS_FORMAT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "player_id": meta.get("player_id"),
    }

    # Extract leader signals with resolved names
    signals["leaders"] = _extract_leader_signals(extractor)

    # Extract war signals
    signals["wars"] = _extract_war_signals(extractor)

    # Extract diplomacy signals
    signals["diplomacy"] = _extract_diplomacy_signals(extractor)

    # Extract technology signals
    signals["technology"] = _extract_technology_signals(extractor)

    # Extract megastructures signals
    signals["megastructures"] = _extract_megastructures_signals(extractor)

    # Extract crisis signals
    signals["crisis"] = _extract_crisis_signals(extractor)

    # Extract fallen empires signals
    signals["fallen_empires"] = _extract_fallen_empires_signals(extractor)

    # Extract policies signals
    signals["policies"] = _extract_policies_signals(extractor)

    # Extract edicts signals
    signals["edicts"] = _extract_edicts_signals(extractor)

    # Extract galaxy settings (static per game but needed for milestone events)
    signals["galaxy_settings"] = _extract_galaxy_settings_signals(extractor)

    # Extract systems count (number of controlled systems via starbases)
    signals["systems"] = _extract_systems_signals(extractor)

    return signals


def _extract_leader_signals(extractor: "SaveExtractor") -> dict[str, Any]:
    """Extract normalized leader data with resolved names.

    Uses extractor.get_leaders() which handles name resolution via
    _extract_leader_name_rust() when Rust session is active.

    Returns:
        Dict with count and leaders list, each leader having:
        - id: int
        - class: str (admiral, general, scientist, governor, ruler)
        - level: int | None
        - name: str | None (resolved human-readable name)
        - name_key: str | None (raw key for debugging/localization)
        - death_date: str | None
        - date_added: str | None
        - recruitment_date: str | None
    """
    raw = extractor.get_leaders()

    if not isinstance(raw, dict):
        return {"count": 0, "leaders": []}

    raw_leaders = raw.get("leaders", [])
    if not isinstance(raw_leaders, list):
        return {"count": 0, "leaders": []}

    normalized: list[dict[str, Any]] = []

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

        # Build normalized leader entry
        entry: dict[str, Any] = {
            "id": leader_id_int,
            "class": leader.get("class"),
            "level": leader.get("level"),
        }

        # Name resolution: 'name' field from get_leaders() is already resolved
        # when Rust session is active (via _extract_leader_name_rust)
        resolved_name = leader.get("name")
        if resolved_name:
            entry["name"] = resolved_name

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
    if key and not key.startswith("%") and not "_" in key[:4]:
        return key

    return None


def _extract_war_signals(extractor: "SaveExtractor") -> dict[str, Any]:
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

    # First get war names from the extractor (already processed)
    war_names: list[str] = []
    for war in raw_wars:
        if not isinstance(war, dict):
            continue
        name = war.get("name")
        if name and isinstance(name, str) and name.strip():
            war_names.append(name.strip())

    # Try to resolve placeholder names by accessing raw war data directly
    # This is done when Rust session is active
    try:
        from rust_bridge import _get_active_session, iter_section_entries

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
    }


def _resolve_war_names_from_raw(extractor: "SaveExtractor", session) -> list[str]:
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
        from rust_bridge import iter_section_entries

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


def _extract_diplomacy_signals(extractor: "SaveExtractor") -> dict[str, Any]:
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

    return {
        "player_id": player_id,
        "allies": allies,
        "rivals": rivals,
        "treaties": treaties,
        "empire_names": empire_names,
    }


def _extract_technology_signals(extractor: "SaveExtractor") -> dict[str, Any]:
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


def _extract_megastructures_signals(extractor: "SaveExtractor") -> dict[str, Any]:
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


def _extract_crisis_signals(extractor: "SaveExtractor") -> dict[str, Any]:
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
        try:
            result["player_crisis_kills"] = int(player_kills)
        except (ValueError, TypeError):
            pass

    # Include crisis country info for detailed reporting
    crisis_countries = raw.get("crisis_countries", [])
    if isinstance(crisis_countries, list) and crisis_countries:
        result["crisis_countries"] = crisis_countries

    # Include all detected crisis types if multiple (e.g., aberrant + vehement)
    crisis_types = raw.get("crisis_types_detected", [])
    if isinstance(crisis_types, list) and len(crisis_types) > 1:
        result["crisis_types_detected"] = crisis_types

    return result


def _extract_fallen_empires_signals(extractor: "SaveExtractor") -> dict[str, Any]:
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
            try:
                entry["military_power"] = float(mil_power)
            except (ValueError, TypeError):
                pass

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
            try:
                entry["country_id"] = int(cid)
            except (ValueError, TypeError):
                pass

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


def _extract_policies_signals(extractor: "SaveExtractor") -> dict[str, Any]:
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
        if (
            policy_name
            and selected
            and isinstance(policy_name, str)
            and isinstance(selected, str)
        ):
            policies[policy_name] = selected

    return {
        "player_id": player_id,
        "policies": policies,
        "count": len(policies),
    }


def _extract_edicts_signals(extractor: "SaveExtractor") -> dict[str, Any]:
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


def _extract_galaxy_settings_signals(extractor: "SaveExtractor") -> dict[str, Any]:
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
        from rust_bridge import _get_active_session

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


def _extract_systems_signals(extractor: "SaveExtractor") -> dict[str, Any]:
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
