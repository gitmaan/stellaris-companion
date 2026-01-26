"""
History context builder for /ask (Phase 3 Milestone 5).

Only used when the user explicitly asks about changes/trends over time.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from backend.core.database import GameDatabase
from backend.core.history import compute_save_id, extract_snapshot_metrics

_HISTORY_KEYWORDS = re.compile(
    r"\b("
    r"since|recent|recently|last\s+(save|autosave|session|turn)|"
    r"what\s+changed|change(s)?|delta|diff|"
    r"trend|trending|over\s+time|over\s+the\s+last|"
    r"compared\s+to|vs\.?|versus|"
    r"progress|how\s+have\s+we\s+been"
    r")\b",
    re.IGNORECASE,
)


def should_include_history(question: str) -> bool:
    if not question:
        return False
    return _HISTORY_KEYWORDS.search(question) is not None


def _fmt(val: Any) -> str:
    if val is None:
        return "n/a"
    if isinstance(val, float):
        return f"{val:+.1f}"
    if isinstance(val, int):
        return f"{val:,}"
    return str(val)


def build_history_context(
    *,
    db: GameDatabase,
    campaign_id: str | None,
    player_id: int | None,
    empire_name: str | None,
    save_path: Path | None,
    max_events: int = 10,
    max_points: int = 8,
) -> str | None:
    """Build a compact history context block for the current campaign/session."""
    save_id = compute_save_id(
        campaign_id=campaign_id,
        player_id=player_id,
        empire_name=empire_name,
        save_path=save_path,
    )

    session_id = db.get_active_or_latest_session_id(save_id=save_id)
    if not session_id:
        return None

    stats = db.get_session_snapshot_stats(session_id)
    events = db.get_recent_events(session_id=session_id, limit=max_events)
    points = db.get_recent_snapshot_points(session_id=session_id, limit=max_points)

    lines: list[str] = []
    lines.append("HISTORY (current campaign/session):")
    lines.append(f"- session_id: {session_id}")
    if stats.get("first_game_date") and stats.get("last_game_date"):
        lines.append(f"- date_range: {stats['first_game_date']} → {stats['last_game_date']}")
    lines.append(f"- snapshots: {stats.get('snapshot_count', 0)}")

    if events:
        lines.append("- recent_events:")
        # oldest-first
        for e in reversed(events):
            gd = e.get("game_date") or "Unknown"
            summary = e.get("summary") or ""
            lines.append(f"  - {gd}: {summary}")

    if points:
        lines.append("- recent_timeline_points:")
        for p in reversed(points):  # oldest-first
            gd = p.get("game_date") or "Unknown"
            lines.append(
                "  - "
                f"{gd}: "
                f"mil={_fmt(p.get('military_power'))}, "
                f"colonies={_fmt(p.get('colony_count'))}, "
                f"energy_net={_fmt(p.get('energy_net'))}, "
                f"alloys_net={_fmt(p.get('alloys_net'))}, "
                f"wars={_fmt(p.get('wars_count'))}"
            )

    text = "\n".join(lines).strip()
    # Cap size to protect /ask latency and token cost.
    return text[:3500]


def build_history_context_for_companion(
    *,
    db: GameDatabase,
    companion,
    max_events: int = 10,
    max_points: int = 8,
) -> str | None:
    """Convenience wrapper using the live Companion instance."""
    if not getattr(companion, "is_loaded", False):
        return None

    briefing = getattr(companion, "_current_snapshot", None) or {}
    metrics = extract_snapshot_metrics(briefing) if isinstance(briefing, dict) else {}

    # Prefer campaign_id from the snapshot meta to avoid loading the full gamestate in hot paths.
    campaign_id = metrics.get("campaign_id") if isinstance(metrics, dict) else None

    return build_history_context(
        db=db,
        campaign_id=campaign_id,
        player_id=(
            companion.extractor.get_player_empire_id()
            if getattr(companion, "extractor", None)
            else None
        ),
        empire_name=metrics.get("empire_name") if isinstance(metrics, dict) else None,
        save_path=getattr(companion, "save_path", None),
        max_events=max_events,
        max_points=max_points,
    )
