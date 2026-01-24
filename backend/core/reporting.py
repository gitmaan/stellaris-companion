"""
Session reporting utilities (Phase 3 Milestone 4).

Builds a deterministic end-of-session report from snapshots + events.
"""

from __future__ import annotations

import json
from typing import Any

from backend.core.database import GameDatabase


def _safe_int(value: Any) -> int | None:
    """Safely convert a value to int, returning None on failure.

    Args:
        value: Any value to convert to integer.

    Returns:
        The integer value, or None if conversion fails or value is None.
    """
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def _safe_float(value: Any) -> float | None:
    """Safely convert a value to float, returning None on failure.

    Args:
        value: Any value to convert to float.

    Returns:
        The float value, or None if conversion fails or value is None.
    """
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _fmt_delta(before: Any, after: Any) -> str:
    """Format a before/after delta for display in reports.

    Handles various cases: both None, one None, numeric deltas with +/- signs,
    and generic string conversion for other types.

    Args:
        before: The initial value (can be None, int, float, or any type).
        after: The final value (can be None, int, float, or any type).

    Returns:
        A formatted string showing the change, e.g., "100 → 150 (+50)".
    """
    if before is None and after is None:
        return "N/A"
    if before is None and after is not None:
        return f"None → {after}"
    if before is not None and after is None:
        return f"{before} → None"
    if isinstance(before, (int, float)) and isinstance(after, (int, float)):
        delta = after - before
        sign = "+" if delta > 0 else ""
        if isinstance(before, float) or isinstance(after, float):
            return f"{before:+.1f} → {after:+.1f} ({sign}{delta:+.1f})"
        return f"{before:,} → {after:,} ({sign}{delta:,})"
    return f"{before} → {after}"


def _extract_report_metrics(briefing: dict[str, Any]) -> dict[str, Any]:
    """Extract key metrics from a briefing dict for session reporting.

    Pulls out date, empire name, military stats, economy stats, territory,
    tech count, federation info, and active wars from the nested briefing
    structure.

    Args:
        briefing: A full briefing dictionary with meta, military, economy,
            territory, technology, diplomacy, and history sections.

    Returns:
        A flat dictionary with extracted metrics suitable for delta comparison.
    """
    meta = briefing.get("meta", {}) if isinstance(briefing, dict) else {}
    military = briefing.get("military", {}) if isinstance(briefing, dict) else {}
    economy = briefing.get("economy", {}) if isinstance(briefing, dict) else {}
    territory = briefing.get("territory", {}) if isinstance(briefing, dict) else {}
    tech = briefing.get("technology", {}) if isinstance(briefing, dict) else {}
    dip = briefing.get("diplomacy", {}) if isinstance(briefing, dict) else {}

    net = (
        economy.get("net_monthly", {})
        if isinstance(economy.get("net_monthly", {}), dict)
        else {}
    )
    colonies = (
        territory.get("colonies", {})
        if isinstance(territory.get("colonies", {}), dict)
        else {}
    )

    federation = dip.get("federation")
    federation_label = None
    if isinstance(federation, str) and federation.strip():
        federation_label = federation.strip()
    elif isinstance(federation, dict) and federation:
        federation_label = (
            federation.get("name") or federation.get("federation_name") or "Federation"
        )

    history = briefing.get("history", {}) if isinstance(briefing, dict) else {}
    wars = history.get("wars") if isinstance(history, dict) else None
    war_names: list[str] = []
    if isinstance(wars, dict):
        names = wars.get("wars") or wars.get("names") or []
        if isinstance(names, list):
            war_names = [str(n) for n in names if str(n).strip()]

    return {
        "date": meta.get("date"),
        "empire_name": meta.get("empire_name"),
        "military_power": _safe_int(military.get("military_power")),
        "fleet_count": _safe_int(military.get("fleet_count")),
        "colony_count": _safe_int(colonies.get("total_count")),
        "energy_net": _safe_float(net.get("energy")),
        "alloys_net": _safe_float(net.get("alloys")),
        "tech_count": _safe_int(tech.get("tech_count")),
        "federation": federation_label,
        "war_names": war_names,
    }


def build_session_report_text(
    *,
    db: GameDatabase,
    session_id: str,
    max_events: int = 20,
) -> str:
    """Build a deterministic end-of-session report from database snapshots.

    Retrieves the first and last snapshots for a session, computes deltas
    for key metrics (military power, fleet count, colonies, economy, tech),
    and appends recent notable events.

    Args:
        db: The GameDatabase instance to query.
        session_id: The session identifier to generate a report for.
        max_events: Maximum number of recent events to include (default 20).

    Returns:
        A formatted multi-line string report showing empire progress and events.
    """
    stats = db.get_session_snapshot_stats(session_id)
    snap_count = stats.get("snapshot_count", 0)
    first_date = stats.get("first_game_date")
    last_date = stats.get("last_game_date")

    first_row, last_row = db.get_first_last_snapshot_rows(session_id=session_id)
    first_metrics: dict[str, Any] = {}
    last_metrics: dict[str, Any] = {}

    # Baseline metrics: prefer the baseline full briefing JSON if available, else fall back to event_state_json.
    if first_row and isinstance(
        first_row.get("full_briefing_json") or first_row.get("event_state_json"), str
    ):
        try:
            first_payload = first_row.get("full_briefing_json") or first_row.get(
                "event_state_json"
            )
            first_metrics = _extract_report_metrics(json.loads(first_payload))
        except Exception:
            first_metrics = {}

    # Latest metrics: prefer the session-level latest briefing cache; fall back to snapshot JSON/state.
    latest_json = None
    try:
        latest_json = db.get_latest_session_briefing_json(session_id=session_id)
    except Exception:
        latest_json = None

    if isinstance(latest_json, str) and latest_json:
        try:
            last_metrics = _extract_report_metrics(json.loads(latest_json))
        except Exception:
            last_metrics = {}
    elif last_row and isinstance(
        last_row.get("full_briefing_json") or last_row.get("event_state_json"), str
    ):
        try:
            last_payload = last_row.get("full_briefing_json") or last_row.get(
                "event_state_json"
            )
            last_metrics = _extract_report_metrics(json.loads(last_payload))
        except Exception:
            last_metrics = {}

    empire = (
        last_metrics.get("empire_name")
        or first_metrics.get("empire_name")
        or "Unknown Empire"
    )
    header = f"Session report — {empire}"
    if first_date and last_date:
        header += f"\nIn-game: {first_date} → {last_date}"
    header += f"\nSnapshots: {snap_count}"

    lines: list[str] = [header, ""]

    # Baseline deltas (if we have both ends)
    def add_metric(label: str, key: str) -> None:
        before = first_metrics.get(key)
        after = last_metrics.get(key)
        if before is None and after is None:
            return
        lines.append(f"- {label}: {_fmt_delta(before, after)}")

    lines.append("Key deltas:")
    add_metric("Military power", "military_power")
    add_metric("Fleet count", "fleet_count")
    add_metric("Colonies", "colony_count")
    add_metric("Energy net", "energy_net")
    add_metric("Alloys net", "alloys_net")
    add_metric("Tech count", "tech_count")

    # Federation / wars state
    before_fed = first_metrics.get("federation")
    after_fed = last_metrics.get("federation")
    if before_fed != after_fed and (before_fed or after_fed):
        lines.append(f"- Federation: {_fmt_delta(before_fed, after_fed)}")

    after_wars = last_metrics.get("war_names") or []
    if after_wars:
        wars_preview = ", ".join(after_wars[:5])
        suffix = "…" if len(after_wars) > 5 else ""
        lines.append(f"- Active wars: {wars_preview}{suffix}")

    # Event feed
    events = db.get_recent_events(session_id=session_id, limit=max_events)
    if events:
        lines.append("")
        lines.append("Notable events:")
        # Show oldest-first for readability.
        for e in reversed(events):
            gd = e.get("game_date") or "Unknown date"
            summary = e.get("summary") or ""
            lines.append(f"- `{gd}` {summary}")

    return "\n".join(lines).strip()
