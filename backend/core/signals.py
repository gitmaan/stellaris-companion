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


def build_snapshot_signals(*, extractor: "SaveExtractor", briefing: dict[str, Any]) -> dict[str, Any]:
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
        resolved_name = leader.get('name')
        if resolved_name:
            entry['name'] = resolved_name

        # Keep name_key for debugging/localization (extract from raw data if available)
        # This would be the %LEADER_N% or NAME_* key before resolution
        name_key = leader.get('name_key')
        if name_key:
            entry['name_key'] = name_key

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


def _extract_war_signals(extractor: "SaveExtractor") -> dict[str, Any]:
    """Extract normalized war data for history diffing.

    Uses extractor.get_wars() which provides structured war data
    including participants, war goals, and exhaustion values.

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

    # Extract war names for event detection (war started/ended diffs)
    war_names: list[str] = []
    for war in raw_wars:
        if not isinstance(war, dict):
            continue
        name = war.get("name")
        if name and isinstance(name, str) and name.strip():
            war_names.append(name.strip())

    return {
        'player_at_war': player_at_war,
        'count': len(war_names),
        'wars': war_names,
    }
