"""Shared utility functions for the backend.core package."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def compute_save_hash_from_briefing(briefing: dict[str, Any]) -> str | None:
    """Compute a stable hash for deduping snapshots.

    Uses a compact, canonical projection of high-signal briefing fields so
    same-date updates with meaningful state changes are less likely to collide.
    """
    if not isinstance(briefing, dict):
        return None

    meta = briefing.get("meta", {}) if isinstance(briefing.get("meta", {}), dict) else {}
    military = (
        briefing.get("military", {}) if isinstance(briefing.get("military", {}), dict) else {}
    )
    economy = briefing.get("economy", {}) if isinstance(briefing.get("economy", {}), dict) else {}
    territory = (
        briefing.get("territory", {}) if isinstance(briefing.get("territory", {}), dict) else {}
    )
    technology = (
        briefing.get("technology", {}) if isinstance(briefing.get("technology", {}), dict) else {}
    )

    colonies = (
        territory.get("colonies", {}) if isinstance(territory.get("colonies", {}), dict) else {}
    )
    net_monthly = (
        economy.get("net_monthly", {}) if isinstance(economy.get("net_monthly", {}), dict) else {}
    )

    signature = {
        "date": meta.get("date"),
        "campaign_id": meta.get("campaign_id"),
        "player_id": meta.get("player_id"),
        "empire_name": meta.get("empire_name") or meta.get("name"),
        "military_power": military.get("military_power"),
        "fleet_count": military.get("fleet_count"),
        "military_fleets": military.get("military_fleets"),
        "colony_count": colonies.get("total_count"),
        "tech_count": technology.get("tech_count"),
        "net_monthly": {
            "energy": net_monthly.get("energy"),
            "alloys": net_monthly.get("alloys"),
            "minerals": net_monthly.get("minerals"),
            "food": net_monthly.get("food"),
            "consumer_goods": net_monthly.get("consumer_goods"),
        },
    }

    has_signal = any(
        value is not None
        for value in (
            signature["date"],
            signature["campaign_id"],
            signature["player_id"],
            signature["empire_name"],
            signature["military_power"],
            signature["fleet_count"],
            signature["military_fleets"],
            signature["colony_count"],
            signature["tech_count"],
            *signature["net_monthly"].values(),
        )
    )
    if not has_signal:
        return None

    key_data = json.dumps(signature, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(key_data.encode("utf-8", errors="replace")).hexdigest()[:16]
