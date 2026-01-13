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


def extract_campaign_id_from_gamestate(gamestate: str) -> str | None:
    """Extract a stable campaign identifier from the gamestate text.

    Stellaris saves include a top-level `galaxy={ ... name=\"<uuid>\" ... }`.
    That UUID is a strong campaign discriminator across multiple runs.
    """
    if not gamestate:
        return None

    # Find the galaxy block (near the start of the file in practice).
    start = gamestate.find("\ngalaxy=")
    if start == -1:
        if gamestate.startswith("galaxy="):
            start = 0
        else:
            return None

    # Search a bounded window for the galaxy name UUID.
    window = gamestate[start : start + 20000]
    key = 'name="'
    pos = window.find(key)
    if pos == -1:
        return None
    end = window.find('"', pos + len(key))
    if end == -1:
        return None
    value = window[pos + len(key) : end].strip()
    return value or None


def extract_player_wars_from_gamestate(*, gamestate: str | None, player_id: int | None) -> dict[str, Any] | None:
    """Extract active wars involving the player from gamestate.

    This is a lightweight version of SaveExtractor.get_wars() so snapshot recording
    can capture wars without requiring additional tool calls.
    """
    if not gamestate:
        return None
    if player_id is None:
        return None

    pid = int(player_id)
    result: dict[str, Any] = {"player_at_war": False, "count": 0, "wars": []}

    # Check player's country block for active_wars IDs (fast, bounded window)
    country_start = gamestate.find("\ncountry=")
    if country_start != -1:
        window = gamestate[country_start : country_start + 120000]
        player_block_pos = window.find("\n\t0=")
        if player_block_pos != -1:
            player_window = window[player_block_pos : player_block_pos + 60000]
            aw_pos = player_window.find("active_wars")
            if aw_pos != -1:
                result["player_at_war"] = True

    # Extract war names involving player from war section (bounded)
    war_section_start = gamestate.find("\nwar=")
    if war_section_start == -1:
        if gamestate.startswith("war="):
            war_section_start = 0
        else:
            return result

    war_chunk = gamestate[war_section_start : war_section_start + 2500000]
    # Match blocks where attackers/defenders contain country=<player_id>
    # This is intentionally approximate but works well enough for delta events.
    import re

    pattern = r'name\s*=\s*"([^"]+)"[^}]*?(?:attackers|defenders)\s*=\s*\{[^}]*country=' + str(pid) + r'\b'
    names: list[str] = []
    for m in re.finditer(pattern, war_chunk, re.DOTALL):
        name = (m.group(1) or "").strip()
        if name and name not in names:
            names.append(name)

    result["wars"] = names[:25]
    result["count"] = len(names)
    if names:
        result["player_at_war"] = True

    return result


def compute_save_id(
    *,
    campaign_id: str | None,
    player_id: int | None,
    empire_name: str | None,
    save_path: Path | None,
) -> str:
    """Compute an identifier for a playthrough/save source.

    Priority:
    1) campaign_id (galaxy UUID) + player_id: robust across many campaigns in one folder.
    2) empire_name + save folder path: fallback when campaign_id is unavailable.
    """
    if campaign_id:
        pid = "" if player_id is None else str(int(player_id))
        raw = f"campaign:{campaign_id}|player:{pid}".encode("utf-8", errors="replace")
        return hashlib.sha1(raw).hexdigest()[:16]

    empire_part = (empire_name or "unknown").strip().lower()
    root = str(save_path.parent.resolve()) if save_path else "unknown"
    raw = f"empire:{empire_part}|root:{root}".encode("utf-8", errors="replace")
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
    campaign_id = meta.get("campaign_id")
    player_id = meta.get("player_id")

    net = economy.get("net_monthly", {}) if isinstance(economy.get("net_monthly", {}), dict) else {}
    colonies = territory.get("colonies", {}) if isinstance(territory.get("colonies", {}), dict) else {}

    return {
        "game_date": str(game_date) if game_date is not None else None,
        "empire_name": str(empire_name) if empire_name is not None else None,
        "campaign_id": str(campaign_id) if campaign_id is not None else None,
        "player_id": int(player_id) if isinstance(player_id, int) else None,
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
    gamestate: str | None = None,
    player_id: int | None = None,
    campaign_id: str | None = None,
    briefing: dict[str, Any],
) -> tuple[bool, int | None, str]:
    """Record a snapshot and create/reuse an active session.

    Returns:
        (inserted, snapshot_id, session_id)
    """
    metrics = extract_snapshot_metrics(briefing)
    resolved_campaign_id = (
        campaign_id
        or metrics.get("campaign_id")
        or (extract_campaign_id_from_gamestate(gamestate) if gamestate else None)
    )
    resolved_player_id = player_id if player_id is not None else metrics.get("player_id")

    wars = extract_player_wars_from_gamestate(gamestate=gamestate, player_id=resolved_player_id)

    # Avoid mutating the live snapshot object used by /ask; store extras in a copy.
    briefing_for_storage = dict(briefing)
    if wars:
        briefing_for_storage["history"] = {"wars": wars}

    session_id = db.get_or_create_active_session(
        save_id=compute_save_id(
            campaign_id=resolved_campaign_id,
            player_id=resolved_player_id,
            empire_name=metrics.get("empire_name"),
            save_path=save_path,
        ),
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
        wars_count=wars.get("count") if isinstance(wars, dict) else metrics.get("wars_count"),
        energy_net=metrics.get("energy_net"),
        alloys_net=metrics.get("alloys_net"),
        full_briefing_json=json.dumps(briefing_for_storage, ensure_ascii=False, separators=(",", ":")),
    )
    if inserted and snapshot_id is not None:
        try:
            db.record_events_for_new_snapshot(session_id=session_id, snapshot_id=snapshot_id, current_briefing=briefing_for_storage)
        except Exception:
            # Event generation should never break snapshot recording.
            pass

    return inserted, snapshot_id, session_id
