"""
History helpers for Phase 3 snapshot recording.

Milestone 1: record a snapshot on save detection without re-parsing.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from backend.core.database import GameDatabase


def compute_save_id(*, empire_name: str | None, save_path: Path | None) -> str:
    """Compute a stable-ish identifier for a playthrough/save source.

    We intentionally avoid using a per-autosave filename as the identifier.
    This is a heuristic for Phase 3 and can be improved later.
    """
    empire_part = (empire_name or "unknown").strip().lower()
    root = str(save_path.parent.resolve()) if save_path else "unknown"
    raw = f"{empire_part}|{root}".encode("utf-8", errors="replace")
    return hashlib.sha1(raw).hexdigest()[:16]


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def extract_snapshot_metrics(briefing: dict[str, Any]) -> dict[str, Any]:
    meta = briefing.get("meta", {}) if isinstance(briefing, dict) else {}
    military = briefing.get("military", {}) if isinstance(briefing, dict) else {}
    economy = briefing.get("economy", {}) if isinstance(briefing, dict) else {}
    territory = briefing.get("territory", {}) if isinstance(briefing, dict) else {}

    game_date = meta.get("date")
    empire_name = meta.get("empire_name")

    net = economy.get("net_monthly", {}) if isinstance(economy.get("net_monthly", {}), dict) else {}
    colonies = territory.get("colonies", {}) if isinstance(territory.get("colonies", {}), dict) else {}

    return {
        "game_date": str(game_date) if game_date is not None else None,
        "empire_name": str(empire_name) if empire_name is not None else None,
        "military_power": _safe_int(military.get("military_power")),
        "colony_count": _safe_int(colonies.get("total_count")),
        # wars_count not in get_full_briefing() yet (fill in later milestones)
        "wars_count": None,
        "energy_net": _safe_float(net.get("energy")),
        "alloys_net": _safe_float(net.get("alloys")),
    }


def record_snapshot_from_companion(
    *,
    db: GameDatabase,
    save_path: Path | None,
    save_hash: str | None,
    briefing: dict[str, Any],
) -> tuple[bool, int | None, str]:
    """Record a snapshot and create/reuse an active session.

    Returns:
        (inserted, snapshot_id, session_id)
    """
    metrics = extract_snapshot_metrics(briefing)
    session_id = db.get_or_create_active_session(
        save_id=compute_save_id(empire_name=metrics.get("empire_name"), save_path=save_path),
        save_path=str(save_path) if save_path else None,
        empire_name=metrics.get("empire_name"),
        last_game_date=metrics.get("game_date"),
    )

    inserted, snapshot_id = db.insert_snapshot_if_new(
        session_id=session_id,
        game_date=metrics.get("game_date"),
        save_hash=save_hash,
        military_power=metrics.get("military_power"),
        colony_count=metrics.get("colony_count"),
        wars_count=metrics.get("wars_count"),
        energy_net=metrics.get("energy_net"),
        alloys_net=metrics.get("alloys_net"),
        full_briefing_json=json.dumps(briefing, ensure_ascii=False, separators=(",", ":")),
    )
    return inserted, snapshot_id, session_id

