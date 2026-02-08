"""Shared utility functions for the backend.core package."""

from __future__ import annotations

import hashlib
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
    """Compute a stable-ish hash for deduping snapshots."""
    if not isinstance(briefing, dict):
        return None
    meta = briefing.get("meta", {}) if isinstance(briefing.get("meta", {}), dict) else {}
    military = (
        briefing.get("military", {}) if isinstance(briefing.get("military", {}), dict) else {}
    )
    date = meta.get("date")
    empire_name = meta.get("empire_name") or meta.get("name")
    mil = military.get("military_power")
    if date is None and empire_name is None and mil is None:
        return None
    key_data = f"{date}|{mil}|{empire_name}"
    return hashlib.md5(key_data.encode("utf-8", errors="replace")).hexdigest()[:8]
