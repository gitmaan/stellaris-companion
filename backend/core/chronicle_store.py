"""Shared Chronicle revision, source metadata, and read-only presentation helpers."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any


class ChronicleConflict(ValueError):
    """A source archive changed or disappeared while work was being prepared."""


def game_date_key(value: Any) -> tuple[int, int, int] | None:
    if not isinstance(value, str):
        return None
    try:
        parts = tuple(int(part) for part in value.strip().split("."))
    except ValueError:
        return None
    if len(parts) != 3 or parts[0] < 0 or not 1 <= parts[1] <= 12 or not 1 <= parts[2] <= 31:
        return None
    return parts


def events_between_dates(
    events: list[dict[str, Any]], start: Any, end: Any
) -> list[dict[str, Any]]:
    lower, upper = game_date_key(start), game_date_key(end)
    if upper is None:
        return []
    return [
        event
        for event in events
        if (date := game_date_key(event.get("game_date"))) is not None
        and (lower is None or date >= lower)
        and date <= upper
    ]


def load_chapters_data(cached: dict[str, Any] | None) -> dict[str, Any]:
    raw = (cached or {}).get("chapters_json")
    data = json.loads(raw) if isinstance(raw, str) and raw else {}
    if not isinstance(data, dict):
        raise ValueError("Stored Chronicle chapter data is not an object")
    data = deepcopy(data)
    data.setdefault("format_version", 1)
    data.setdefault("chapters", [])
    if not isinstance(data["chapters"], list):
        raise ValueError("Stored Chronicle chapters are not a list")
    data.setdefault("current_era_start_date", None)
    data.setdefault("current_era_start_snapshot_id", None)
    for chapter in data["chapters"]:
        if isinstance(chapter, dict):
            chapter.setdefault("id", chapter_identity(chapter))
    return data


def compact_chronicle_context(briefing: dict[str, Any]) -> dict[str, Any]:
    """Retain only bounded, dated facts used by the Chronicle's context formatter.

    This lives with the lightweight snapshot state rather than retaining every
    full briefing. Unknown historical facts remain absent.
    """

    def fields(value: Any, names: tuple[str, ...]) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        result = {}
        for name in names:
            item = value.get(name)
            if isinstance(item, (str, int, float, bool)):
                result[name] = item[:400] if isinstance(item, str) else item
            elif isinstance(item, list):
                result[name] = [v[:400] for v in item[:8] if isinstance(v, str)]
        return result

    identity = fields(
        briefing.get("identity"),
        ("empire_name", "ethics", "authority", "civics", "origin", "is_machine", "is_hive_mind"),
    )
    meta = fields(briefing.get("meta"), ("date", "version", "empire_name"))
    if not identity.get("empire_name") and meta.get("empire_name"):
        identity["empire_name"] = meta["empire_name"]
    diplomacy = briefing.get("diplomacy") or {}
    geography = briefing.get("strategic_geography") or {}
    relation_fields = (
        "empire_name",
        "country_type",
        "ethics",
        "authority",
        "opinion",
        "rival",
        "defensive_pact",
        "non_aggression_pact",
        "commercial_pact",
        "research_agreement",
        "closed_borders",
        "has_truce",
    )
    return {
        "meta": meta,
        "identity": identity,
        "diplomacy": {
            "relations": [
                fields(v, relation_fields) for v in (diplomacy.get("relations") or [])[:40]
            ],
            "federation": fields(diplomacy.get("federation"), ("name",)),
        },
        "strategic_geography": {
            "border_neighbors": [
                fields(v, ("empire_name", "direction"))
                for v in (geography.get("border_neighbors") or [])[:5]
            ],
            "chokepoints": [
                fields(v, ("system_name", "enemy_neighbors"))
                for v in (geography.get("chokepoints") or [])[:3]
            ],
        },
    }


def source_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep precisely the bounded facts formatted into the provider prompt."""
    return [
        {
            "id": event.get("id"),
            "game_date": event.get("game_date"),
            "event_type": event.get("event_type"),
            "summary": str(event.get("summary") or event.get("event_type") or "Unknown event")[
                :1000
            ],
        }
        for event in events
    ]


def chapter_identity(chapter: dict[str, Any]) -> str:
    """Legacy chapters retain their anchor when their title/prose is rewritten."""
    source = [
        chapter.get(k)
        for k in ("number", "start_snapshot_id", "end_snapshot_id", "start_date", "end_date")
    ]
    return "chapter_" + hashlib.sha256(json.dumps(source).encode()).hexdigest()[:24]


def chronicle_revision(data: dict[str, Any]) -> str:
    visible = deepcopy(data)
    for key in ("external_edit_history", "external_edit_last_updated_at", "chapter_undo"):
        visible.pop(key, None)
    encoded = json.dumps(
        visible, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return "chronicle_" + hashlib.sha256(encoded).hexdigest()[:24]


def assemble_chronicle(data: dict[str, Any]) -> str:
    parts = []
    for chapter in data.get("chapters", []):
        parts.extend(
            [
                f"## Chapter {chapter.get('number')}: {chapter.get('title', '')}",
                f"**{chapter.get('start_date', '?')} – {chapter.get('end_date', '?')}**",
                str(chapter.get("narrative") or ""),
            ]
        )
    era = (data.get("current_era_cache") or {}).get("current_era")
    if isinstance(era, dict):
        parts.extend(["## Current Era", str(era.get("narrative") or "")])
    return "\n\n".join(parts).strip()


def cached_chronicle_response(cached: dict[str, Any] | None) -> dict[str, Any]:
    """Read existing prose without advancing its writing time or source coverage."""
    warning = None
    try:
        data = load_chapters_data(cached)
    except (ValueError, TypeError):
        data = load_chapters_data(None)
        warning = "Stored chapter data could not be parsed; legacy prose was preserved."
    undo = data.get("chapter_undo") or {}
    chapters = []
    for index, raw in enumerate(data.get("chapters", []), start=1):
        if not isinstance(raw, dict):
            continue
        # Source bundles and revision backups stay local, outside the renderer payload.
        chapter = {k: deepcopy(v) for k, v in raw.items() if k != "source_bundle"}
        chapter.setdefault("number", index)
        chapter.setdefault("title", f"Chapter {index}")
        chapter.setdefault("narrative", "")
        chapter.setdefault("start_date", "")
        chapter.setdefault("end_date", "")
        chapter.setdefault("summary", "")
        chapter.setdefault("is_finalized", True)
        chapter.setdefault("context_stale", False)
        chapter["can_regenerate"] = bool(chapter["is_finalized"])
        chapter["can_undo"] = bool(undo.get(str(chapter.get("id"))))
        chapter["manual_edit_locked"] = bool(chapter.get("manual_edit_locked"))
        chapter.setdefault("coverage_date", None)
        chapters.append(chapter)
    era_cache = data.get("current_era_cache") or {}
    era = deepcopy(era_cache.get("current_era")) if isinstance(era_cache, dict) else None
    if isinstance(era, dict):
        era.pop("source_bundle", None)
        era.setdefault("coverage_date", era_cache.get("coverage_date"))
        era.setdefault("generated_at", era_cache.get("generated_at"))
    response = {
        "chapters": chapters,
        "current_era": era,
        "pending_chapters": 0,
        "message": None,
        "chronicle": (cached or {}).get("chronicle_text") or "",
        "cached": bool(cached),
        "event_count": int((cached or {}).get("event_count") or 0),
        "generated_at": ""
        if data.get("reset_tombstone")
        else (data.get("content_generated_at") or (cached or {}).get("generated_at") or ""),
        "coverage_date": data.get("coverage_date"),
        "model_routing": None,
        "language": (cached or {}).get("language") or data.get("language") or "en",
        "chronicle_revision": chronicle_revision(data),
    }
    if warning:
        response["cache_warning"] = warning
    return response
