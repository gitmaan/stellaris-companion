"""
History helpers for Phase 3 snapshot recording.

Milestone 1: record a snapshot on save detection without re-parsing.
"""

from __future__ import annotations

import contextlib
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


def extract_galaxy_settings_from_gamestate(
    gamestate: str | None,
) -> dict[str, Any] | None:
    """Extract a few stable galaxy/game settings used for milestone events."""
    if not gamestate:
        return None

    start = gamestate.find("\ngalaxy=")
    if start == -1:
        if gamestate.startswith("galaxy="):
            start = 0
        else:
            return None

    window = gamestate[start : start + 25000]

    def _find_int(key: str) -> int | None:
        import re

        m = re.search(rf"\b{key}\s*=\s*(\d+)\b", window)
        return int(m.group(1)) if m else None

    def _find_str(key: str) -> str | None:
        import re

        m = re.search(rf'\b{key}\s*=\s*"([^"]+)"', window)
        return m.group(1).strip() if m and m.group(1).strip() else None

    return {
        "galaxy_name": _find_str("name"),
        "mid_game_start": _find_int("mid_game_start"),
        "end_game_start": _find_int("end_game_start"),
        "victory_year": _find_int("victory_year"),
        "ironman": _find_str("ironman"),
        "difficulty": _find_str("difficulty"),
        "crisis_type": _find_str("crisis_type"),
    }


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
    colonies = (
        territory.get("colonies", {}) if isinstance(territory.get("colonies", {}), dict) else {}
    )

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


def build_event_state_from_briefing(briefing: dict[str, Any]) -> dict[str, Any]:
    """Build a compact state snapshot used for event detection and reporting.

    This intentionally excludes large, low-signal lists (planets, ship breakdowns, etc.)
    while preserving the keys consumed by `backend.core.events.compute_events()` and
    `backend.core.reporting`.
    """
    if not isinstance(briefing, dict):
        return {}

    meta = briefing.get("meta") if isinstance(briefing.get("meta"), dict) else {}
    military = briefing.get("military") if isinstance(briefing.get("military"), dict) else {}
    economy = briefing.get("economy") if isinstance(briefing.get("economy"), dict) else {}
    territory = briefing.get("territory") if isinstance(briefing.get("territory"), dict) else {}
    technology = briefing.get("technology") if isinstance(briefing.get("technology"), dict) else {}
    diplomacy = briefing.get("diplomacy") if isinstance(briefing.get("diplomacy"), dict) else {}

    net_monthly = economy.get("net_monthly") if isinstance(economy.get("net_monthly"), dict) else {}
    colonies = territory.get("colonies") if isinstance(territory.get("colonies"), dict) else {}

    # Keep only economy nets used by event detection (plus a few high-signal ones).
    economy_state = {
        "net_monthly": {
            k: net_monthly.get(k)
            for k in ("energy", "alloys", "consumer_goods", "food", "minerals")
            if k in net_monthly
        }
    }

    territory_state = (
        {"colonies": {"total_count": colonies.get("total_count")}} if colonies else {"colonies": {}}
    )

    # Military keys used by event detection/reporting.
    military_state = {
        k: military.get(k)
        for k in ("military_power", "military_fleets", "fleet_count")
        if k in military
    }

    technology_state = {k: technology.get(k) for k in ("tech_count",) if k in technology}
    diplomacy_state = {}
    if "federation" in diplomacy:
        diplomacy_state["federation"] = diplomacy.get("federation")

    # History payload is already “small by design” (built by history enrichment helpers).
    history = briefing.get("history") if isinstance(briefing.get("history"), dict) else {}

    event_state: dict[str, Any] = {
        "meta": {
            k: meta.get(k) for k in ("date", "empire_name", "campaign_id", "player_id") if k in meta
        },
        "military": military_state,
        "economy": economy_state,
        "territory": territory_state,
        "technology": technology_state,
        "diplomacy": diplomacy_state,
    }
    if history:
        event_state["history"] = history

    return event_state


def build_history_enrichment(
    *,
    gamestate: str | None,
    player_id: int | None,
    precomputed_signals: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the optional `history` payload stored with a snapshot.

    This is intentionally best-effort and returns an empty dict when inputs are missing.

    Args:
        gamestate: Raw gamestate string for regex-based extraction (legacy path).
        player_id: The player's empire ID.
        precomputed_signals: Optional SnapshotSignals dict from build_snapshot_signals().
            When provided, uses signals data for leaders, wars, diplomacy, technology,
            megastructures, crisis, fallen_empires, policies, edicts instead of parsing
            gamestate. This provides resolved names and better performance.

    Returns:
        History enrichment dict for storage with snapshot.
    """
    # Start with precomputed signals if available
    signals = precomputed_signals if isinstance(precomputed_signals, dict) else {}

    # If no gamestate and no signals, return empty
    if not gamestate and not signals:
        return {}

    int(player_id) if isinstance(player_id, int) else None

    # All history data now comes from precomputed signals
    # Signals are built in ingestion_worker with active Rust session for fast, resolved data
    # Legacy gamestate extraction functions have been removed (UHE-023)
    leaders = signals.get("leaders")
    wars = signals.get("wars")
    diplomacy = signals.get("diplomacy")
    techs = signals.get("technology")
    policies = signals.get("policies")
    edicts = signals.get("edicts")
    megastructures = signals.get("megastructures")
    crisis = signals.get("crisis")
    fallen_empires = signals.get("fallen_empires")

    # Galaxy settings from signals (added in UHE-020)
    galaxy = signals.get("galaxy_settings")

    # Systems count from signals (added in UHE-021)
    systems = signals.get("systems")

    history: dict[str, Any] = {}
    if wars:
        history["wars"] = wars
    if leaders:
        history["leaders"] = leaders
    if diplomacy:
        history["diplomacy"] = diplomacy
    if galaxy:
        history["galaxy"] = galaxy
    if techs:
        history["techs"] = techs
    if policies:
        history["policies"] = policies
    if edicts:
        history["edicts"] = edicts
    if megastructures:
        history["megastructures"] = megastructures
    if crisis:
        history["crisis"] = crisis
    if systems:
        history["systems"] = systems
    if fallen_empires:
        history["fallen_empires"] = fallen_empires

    return history


def record_snapshot_from_briefing(
    *,
    db: GameDatabase,
    save_path: Path | None,
    save_hash: str | None,
    briefing: dict[str, Any],
    briefing_json: str | None = None,
) -> tuple[bool, int | None, str]:
    """Record a snapshot when you already have a full briefing dict.

    This avoids re-parsing gamestate in the main process (useful when ingestion happens
    in a separate worker process). If the briefing already contains a `history` key,
    it will be persisted as-is.
    """
    metrics = extract_snapshot_metrics(briefing)
    resolved_campaign_id = metrics.get("campaign_id")
    resolved_player_id = metrics.get("player_id")

    history = briefing.get("history") if isinstance(briefing.get("history"), dict) else None
    wars = history.get("wars") if isinstance(history, dict) else None

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

    full_json = (
        briefing_json
        if isinstance(briefing_json, str) and briefing_json
        else json.dumps(briefing, ensure_ascii=False, separators=(",", ":"))
    )
    inserted, snapshot_id = db.insert_snapshot_if_new(
        session_id=session_id,
        game_date=metrics.get("game_date"),
        save_hash=save_hash,
        military_power=metrics.get("military_power"),
        colony_count=metrics.get("colony_count"),
        wars_count=(wars.get("count") if isinstance(wars, dict) else metrics.get("wars_count")),
        energy_net=metrics.get("energy_net"),
        alloys_net=metrics.get("alloys_net"),
        # Full briefings are stored on the session row (latest) and only kept per-snapshot for the baseline.
        full_briefing_json=full_json,
        event_state_json=json.dumps(
            build_event_state_from_briefing(briefing),
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    )
    if inserted and snapshot_id is not None:
        try:
            # Persist the latest full briefing once per session (overwrite), not per snapshot row.
            db.update_session_latest_briefing(
                session_id=session_id,
                latest_briefing_json=full_json,
                last_game_date=metrics.get("game_date"),
            )
        except Exception:
            pass
        with contextlib.suppress(Exception):
            db.record_events_for_new_snapshot(
                session_id=session_id,
                snapshot_id=snapshot_id,
                current_briefing=briefing,
            )
        with contextlib.suppress(Exception):
            db.enforce_full_briefing_retention(session_id=session_id)
        with contextlib.suppress(Exception):
            db.maybe_checkpoint_wal()

    return inserted, snapshot_id, session_id


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

    Note: This is a legacy path. History extraction now requires signals
    built in ingestion_worker where Rust session is active. This function
    will use any history already present in the briefing, but won't extract
    new history data. For full history support, use ingestion_worker +
    record_snapshot_from_briefing.

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

    # Use history from briefing if already present (from ingestion_worker)
    # Legacy gamestate extraction has been removed (UHE-023)
    briefing_for_storage = dict(briefing)
    history = briefing.get("history") if isinstance(briefing.get("history"), dict) else {}
    wars = history.get("wars") if isinstance(history, dict) else None

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

    full_json = json.dumps(briefing_for_storage, ensure_ascii=False, separators=(",", ":"))
    inserted, snapshot_id = db.insert_snapshot_if_new(
        session_id=session_id,
        game_date=metrics.get("game_date"),
        save_hash=save_hash,
        military_power=metrics.get("military_power"),
        colony_count=metrics.get("colony_count"),
        wars_count=(wars.get("count") if isinstance(wars, dict) else metrics.get("wars_count")),
        energy_net=metrics.get("energy_net"),
        alloys_net=metrics.get("alloys_net"),
        full_briefing_json=full_json,
        event_state_json=json.dumps(
            build_event_state_from_briefing(briefing_for_storage),
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    )
    if inserted and snapshot_id is not None:
        with contextlib.suppress(Exception):
            db.update_session_latest_briefing(
                session_id=session_id,
                latest_briefing_json=full_json,
                last_game_date=metrics.get("game_date"),
            )
        try:
            db.record_events_for_new_snapshot(
                session_id=session_id,
                snapshot_id=snapshot_id,
                current_briefing=briefing_for_storage,
            )
        except Exception:
            # Event generation should never break snapshot recording.
            pass
        with contextlib.suppress(Exception):
            db.enforce_full_briefing_retention(session_id=session_id)
        with contextlib.suppress(Exception):
            db.maybe_checkpoint_wal()

    return inserted, snapshot_id, session_id
