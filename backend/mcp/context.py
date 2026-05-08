"""Context helpers for the local Stellaris Companion MCP server."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.core.database import GameDatabase
from backend.core.language import language_name, normalize_language

DEFAULT_EVENT_LIMIT = 25
MAX_EVENT_LIMIT = 120
MAX_CHRONICLE_EVENTS = 250
MAX_CHRONICLE_WRITEBACK_CHARS = 20_000
MAX_CHRONICLE_SUMMARY_CHARS = 2_000
MAX_CHRONICLE_EDIT_HISTORY_ITEMS = 10
MAX_TEXT_LENGTH = 1600
MAX_LIST_ITEMS_COMPACT = 12
MAX_ADVISOR_BRIEFING_CHARS = 60_000

DEFAULT_CHAPTERS_DATA = {
    "format_version": 1,
    "chapters": [],
    "current_era_start_date": None,
    "current_era_start_snapshot_id": None,
}

NOTABLE_EVENT_TYPES = {
    "war_started",
    "war_ended",
    "federation_joined",
    "federation_left",
    "alliance_formed",
    "alliance_ended",
    "crisis_started",
    "crisis_defeated",
    "fallen_empire_awakened",
    "war_in_heaven_started",
    "ascension_perk_selected",
    "lgate_opened",
    "crisis_level_increased",
    "megastructure_construction_completed",
    "megastructure_restored",
    "megastructure_ruined",
    "ruler_changed",
    "first_contact",
    "great_khan_spawned",
    "great_khan_died",
    "galactic_community_joined",
    "galactic_community_left",
    "galactic_community_council_joined",
    "tradition_tree_completed",
    "precursor_homeworld_discovered",
    "subject_gained",
    "subject_lost",
    "became_subject",
    "freed_from_subject",
    "new_border_contact",
    "colony_count_change",
    "military_power_change",
}

FOCUS_SECTIONS = {
    "economy": ["economy", "situation", "territory", "strategic_geography"],
    "military": ["military", "defense", "technology", "situation", "strategic_geography"],
    "diplomacy": ["diplomacy", "federation_details", "fallen_empires", "situation"],
    "technology": ["technology", "projects", "progression", "economy"],
    "territory": ["territory", "strategic_geography", "defense", "economy"],
    "chronicle": ["situation", "identity", "diplomacy", "military", "territory", "endgame"],
    "crisis": ["endgame", "military", "diplomacy", "fallen_empires", "defense"],
    "general": [
        "situation",
        "economy",
        "military",
        "diplomacy",
        "territory",
        "technology",
        "endgame",
    ],
}

ADVISOR_BRIEFING_SECTIONS = [
    "situation",
    "economy",
    "military",
    "diplomacy",
    "territory",
    "technology",
    "defense",
    "strategic_geography",
    "progression",
    "projects",
    "leadership",
    "species",
    "federation_details",
    "fallen_empires",
    "leviathans",
    "endgame",
    "history",
]

ROMAN_NUMERALS = {
    "1": "I",
    "2": "II",
    "3": "III",
    "4": "IV",
    "5": "V",
    "6": "VI",
}

DISPLAY_NAME_OVERRIDES = {
    "tech_doctrine_fleet_size_1": "Fleet Doctrines",
    "tech_automated_exploration": "Automated Exploration Protocols",
    "tech_mass_drivers_1": "Mass Drivers",
    "tech_mass_drivers_2": "Coilguns",
    "tech_mass_drivers_3": "Railguns",
    "tech_mass_drivers_4": "Advanced Railguns",
    "tech_mass_drivers_5": "Gauss Cannons",
    "war_started": "War Started",
    "war_ended": "War Ended",
    "colony_count_change": "Colony Count Change",
    "military_power_change": "Military Power Change",
}

DISPLAY_ID_PREFIXES = (
    "tech_",
    "ethic_",
    "civic_",
    "authority_",
    "auth_",
    "origin_",
    "tradition_",
    "tr_",
    "ap_",
    "trait_",
    "leader_trait_",
    "edict_",
    "policy_",
    "building_",
    "district_",
    "job_",
    "deposit_",
    "pc_",
    "starbase_",
    "component_",
    "weapon_",
    "ship_",
    "shipclass_",
    "bombardment_",
    "casus_belli_",
    "war_goal_",
    "federation_",
    "resolution_",
    "crisis_",
    "relic_",
)

DISPLAY_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$")


class McpContextError(RuntimeError):
    """Raised when the local MCP context cannot satisfy a request."""


class StellarisMcpContext:
    """Facade over the local Stellaris Companion history database."""

    def __init__(
        self,
        *,
        db_path: str | Path | None = None,
        db: GameDatabase | None = None,
        language: str = "en",
    ) -> None:
        self._owns_db = db is None
        self.db = db if db is not None else GameDatabase(db_path=db_path)
        self.language = normalize_language(language)

    def close(self) -> None:
        if self._owns_db:
            self.db.close()

    def get_active_campaign(self) -> dict[str, Any]:
        session = self._get_current_session()
        if not session:
            return {
                "save_loaded": False,
                "message": "No campaign session is available in the local Stellaris Companion history database.",
            }

        save_id = str(session.get("save_id") or "")
        snapshot_range = self.db.get_snapshot_range_for_save(save_id) if save_id else {}
        briefing = self._load_briefing(str(session["id"]))
        meta = briefing.get("meta") if isinstance(briefing.get("meta"), dict) else {}
        identity = briefing.get("identity") if isinstance(briefing.get("identity"), dict) else {}

        return {
            "save_loaded": True,
            "save_id": save_id,
            "active_session_id": session.get("id"),
            "empire_name": session.get("empire_name")
            or identity.get("name")
            or meta.get("empire_name")
            or meta.get("name"),
            "game_date": session.get("last_game_date")
            or session.get("last_game_date_computed")
            or meta.get("date"),
            "first_game_date": session.get("first_game_date")
            or snapshot_range.get("first_game_date"),
            "snapshot_count": session.get("snapshot_count")
            or snapshot_range.get("snapshot_count")
            or 0,
            "started_at": session.get("started_at"),
            "ended_at": session.get("ended_at"),
            "is_active": session.get("ended_at") is None,
            "version": meta.get("version"),
            "language": self.language,
        }

    def get_strategy_context(
        self,
        *,
        question: str = "",
        focus: str = "auto",
        event_limit: int = 15,
    ) -> dict[str, Any]:
        session = self._require_current_session()
        save_id = str(session.get("save_id") or "")
        session_id = str(session["id"])
        briefing = self._load_briefing(session_id)
        resolved_focus = self._resolve_focus(question=question, focus=focus)

        payload = {
            "campaign": self.get_active_campaign(),
            "question": question,
            "focus": resolved_focus,
            "advisor_mode": "External client should reason from this context. No in-app LLM call was made.",
            "briefing_mode": "rich",
            "briefing": self._build_advisor_briefing(briefing, resolved_focus),
            "recent_events": self.get_recent_events(limit=event_limit, notable_only=False).get(
                "events", []
            ),
            "advisor_custom_instructions": self._get_advisor_custom(session_id),
            "advisor_memory": self.db.get_advisor_memory_summary(save_id, language=self.language)
            if save_id
            else None,
            "response_guidance": self._advisor_response_guidance(briefing),
            "privacy": {
                "raw_save_file_included": False,
                "write_back_enabled": False,
                "remote_sync_enabled": False,
            },
        }
        briefing_size = len(json.dumps(payload["briefing"], ensure_ascii=False))
        if briefing_size > MAX_ADVISOR_BRIEFING_CHARS:
            payload["briefing_mode"] = "focused_fallback"
            payload["briefing"] = self._select_briefing_sections(briefing, resolved_focus)
            payload["briefing_note"] = (
                "The rich Advisor Briefing exceeded the local payload ceiling, so this "
                "response includes a focused section fallback. Use get_empire_briefing "
                "for follow-up detail if needed."
            )
        payload["briefing_size_chars"] = len(json.dumps(payload["briefing"], ensure_ascii=False))
        return _drop_empty(payload)

    def get_empire_briefing(
        self,
        *,
        sections: list[str] | None = None,
        max_detail: str = "compact",
    ) -> dict[str, Any]:
        session = self._require_current_session()
        briefing = self._load_briefing(str(session["id"]))
        selected_sections = [str(s) for s in sections or FOCUS_SECTIONS["general"]]
        detail = "full" if str(max_detail).lower() == "full" else "compact"
        return {
            "campaign": self.get_active_campaign(),
            "sections": {
                key: _compact_value(
                    briefing.get(key),
                    max_depth=5 if detail == "full" else 3,
                    max_list_items=25 if detail == "full" else MAX_LIST_ITEMS_COMPACT,
                )
                for key in selected_sections
                if key in briefing
            },
            "detail": detail,
        }

    def get_recent_events(
        self,
        *,
        limit: int = DEFAULT_EVENT_LIMIT,
        notable_only: bool = False,
    ) -> dict[str, Any]:
        session = self._require_current_session()
        lim = _clamp_int(limit, default=DEFAULT_EVENT_LIMIT, minimum=1, maximum=MAX_EVENT_LIMIT)
        rows = self.db.get_recent_events(session_id=str(session["id"]), limit=lim)
        events = [_event_payload(row) for row in rows]
        if notable_only:
            events = [event for event in events if event.get("event_type") in NOTABLE_EVENT_TYPES]
        return {
            "campaign": self.get_active_campaign(),
            "limit": lim,
            "notable_only": notable_only,
            "events": events,
        }

    def get_cached_chronicle(self) -> dict[str, Any]:
        session = self._require_current_session()
        save_id = str(session.get("save_id") or "")
        cached = (
            self.db.get_chronicle_by_save_id(save_id, language=self.language) if save_id else None
        )
        if not cached:
            cached = self.db.get_cached_chronicle(str(session["id"]), language=self.language)

        if not cached:
            return {
                "campaign": self.get_active_campaign(),
                "cached": False,
                "chapters": [],
                "current_era": None,
                "chronicle": "",
                "message": "No cached Chronicle is available yet. Open/generate Chronicle in the Electron app first, or use source material to write in the MCP client.",
                "archive_guidance": self._chronicle_archive_guidance(cached=False),
                "save_affordance": self._chronicle_save_affordance(),
            }

        chapters_data = _parse_json_object(cached.get("chapters_json"))
        current_era_cache = chapters_data.get("current_era_cache")
        current_era = (
            current_era_cache.get("current_era")
            if isinstance(current_era_cache, dict)
            and isinstance(current_era_cache.get("current_era"), dict)
            else None
        )
        chapters = (
            chapters_data.get("chapters") if isinstance(chapters_data.get("chapters"), list) else []
        )

        return {
            "campaign": self.get_active_campaign(),
            "cached": True,
            "save_id": cached.get("save_id") or save_id,
            "session_id": cached.get("session_id") or session.get("id"),
            "language": cached.get("language") or self.language,
            "generated_at": cached.get("generated_at"),
            "event_count": cached.get("event_count"),
            "snapshot_count": cached.get("snapshot_count"),
            "chapters": [_chapter_payload(ch) for ch in chapters],
            "current_era": _current_era_payload(current_era),
            "chronicle": cached.get("chronicle_text") or "",
            "chronicle_custom_instructions": cached.get("chronicle_custom_instructions"),
            "archive_guidance": self._chronicle_archive_guidance(cached=True),
            "save_affordance": self._chronicle_save_affordance(),
        }

    def get_chronicle_source_material(
        self,
        *,
        scope: str = "current_era",
        chapter_number: int | None = None,
        max_events: int = 80,
    ) -> dict[str, Any]:
        session = self._require_current_session()
        save_id = str(session.get("save_id") or "")
        if not save_id:
            raise McpContextError("Current session has no save_id.")

        lim = _clamp_int(max_events, default=80, minimum=1, maximum=MAX_CHRONICLE_EVENTS)
        cached = self.db.get_chronicle_by_save_id(save_id, language=self.language)
        chapters_data = _parse_json_object(cached.get("chapters_json")) if cached else {}
        normalized_scope = str(scope or "current_era").strip().lower()
        if normalized_scope.startswith("chapter:") and chapter_number is None:
            with contextlib_suppress_value_error():
                chapter_number = int(normalized_scope.split(":", 1)[1])
            normalized_scope = "chapter"

        events: list[dict[str, Any]]
        event_range: dict[str, Any] = {}

        if normalized_scope == "chapter" or chapter_number is not None:
            chapter = self._find_chapter(chapters_data, chapter_number)
            if not chapter:
                raise McpContextError(f"Chapter {chapter_number} is not available in the cache.")
            events = self.db.get_events_in_snapshot_range(
                save_id=save_id,
                from_snapshot_id=chapter.get("start_snapshot_id"),
                to_snapshot_id=chapter.get("end_snapshot_id"),
            )
            event_range = {
                "scope": "chapter",
                "chapter_number": chapter.get("number"),
                "start_date": chapter.get("start_date"),
                "end_date": chapter.get("end_date"),
                "start_snapshot_id": chapter.get("start_snapshot_id"),
                "end_snapshot_id": chapter.get("end_snapshot_id"),
            }
        elif normalized_scope == "latest_session":
            events = list(
                reversed(self.db.get_recent_events(session_id=str(session["id"]), limit=lim))
            )
            event_range = {"scope": "latest_session"}
        elif normalized_scope == "full_summary":
            events = self.db.get_all_events_by_save_id(save_id=save_id)
            event_range = {"scope": "full_summary"}
        else:
            start_snapshot_id = self._current_era_start_snapshot_id(chapters_data)
            events = self.db.get_events_in_snapshot_range(
                save_id=save_id,
                from_snapshot_id=start_snapshot_id,
                to_snapshot_id=None,
            )
            event_range = {
                "scope": "current_era",
                "start_snapshot_id": start_snapshot_id,
                "start_date": chapters_data.get("current_era_start_date"),
            }

        truncated = len(events) > lim
        if truncated:
            events = events[-lim:]

        briefing = self._load_briefing(str(session["id"]))
        return {
            "campaign": self.get_active_campaign(),
            "event_range": event_range,
            "events": [_event_payload(row) for row in events],
            "truncated": truncated,
            "briefing": self._select_briefing_sections(briefing, "chronicle"),
            "chronicle_custom_instructions": self.db.get_chronicle_custom_instructions(save_id),
            "chronicle_guidance": self._chronicle_source_guidance(briefing, event_range),
            "save_affordance": self._chronicle_save_affordance(),
            "write_back_enabled": True,
        }

    def save_chronicle_current_era(
        self,
        *,
        narrative: str,
        title: str | None = None,
        start_date: str | None = None,
        events_covered: int | None = None,
    ) -> dict[str, Any]:
        """Persist externally written current-era Chronicle prose to the local cache."""
        cleaned_narrative = str(narrative or "").strip()
        self._validate_chronicle_text(cleaned_narrative, field_name="narrative")

        state = self._load_chronicle_state()
        session = state["session"]
        save_id = state["save_id"]
        chapters_data = state["chapters_data"]
        snapshot_range = state["snapshot_range"]
        before = _json_clone(chapters_data)
        era_start_date = (
            start_date
            or chapters_data.get("current_era_start_date")
            or snapshot_range.get("first_game_date")
            or session.get("first_game_date")
            or session.get("last_game_date")
            or "2200.01.01"
        )
        era_start_snapshot_id = chapters_data.get("current_era_start_snapshot_id")
        if era_start_snapshot_id is None:
            era_start_snapshot_id = snapshot_range.get("first_snapshot_id")

        latest_snapshot_id = snapshot_range.get("last_snapshot_id")
        era_events = self.db.get_events_in_snapshot_range(
            save_id=save_id,
            from_snapshot_id=era_start_snapshot_id,
            to_snapshot_id=None,
        )
        resolved_events_covered = (
            int(events_covered)
            if isinstance(events_covered, int) and events_covered >= 0
            else len(era_events)
        )

        generated_at = datetime.now(timezone.utc).isoformat()
        current_era = {
            "title": (title or "External Chronicle Draft").strip(),
            "start_date": str(era_start_date),
            "narrative": cleaned_narrative,
            "sections": [{"type": "prose", "text": cleaned_narrative, "attribution": ""}],
            "events_covered": resolved_events_covered,
            "source": "mcp_writeback",
            "external_edit": {
                "operation": "save_current_era",
                "source": "external_ai",
                "updated_at": generated_at,
            },
        }
        chapters_data["current_era_start_date"] = str(era_start_date)
        chapters_data["current_era_start_snapshot_id"] = era_start_snapshot_id
        chapters_data["current_era_cache"] = {
            "start_date": str(era_start_date),
            "start_snapshot_id": era_start_snapshot_id,
            "last_snapshot_id": latest_snapshot_id,
            "generated_at": generated_at,
            "language": self.language,
            "source": "mcp_writeback",
            "current_era": current_era,
        }
        self._record_external_edit(
            chapters_data,
            before=before,
            operation="save_current_era",
            target="chronicle.current_era",
            updated_at=generated_at,
        )

        self._persist_chronicle_state(
            session=session,
            save_id=save_id,
            chapters_data=chapters_data,
            snapshot_range=snapshot_range,
        )

        return {
            "campaign": self.get_active_campaign(),
            "saved": True,
            "write_back_enabled": True,
            "message": (
                f'Saved current-era Chronicle draft "{current_era["title"]}" '
                "to Stellaris Companion."
            ),
            "saved_item": _chronicle_item_payload("current_era", current_era),
            "narrative_chars": len(cleaned_narrative),
            "saved_at": generated_at,
            "current_era": _current_era_payload(current_era),
            "app_visibility": (
                "The Chronicle page will show this cached current-era draft after it refreshes."
            ),
        }

    def update_chronicle_chapter(
        self,
        *,
        chapter_number: int,
        narrative: str,
        title: str | None = None,
        summary: str | None = None,
        epigraph: str | None = None,
        sections: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Persist an externally revised finalized Chronicle chapter."""
        cleaned_narrative = str(narrative or "").strip()
        self._validate_chronicle_text(cleaned_narrative, field_name="narrative")
        if summary is not None and len(str(summary)) > MAX_CHRONICLE_SUMMARY_CHARS:
            raise McpContextError(
                f"Chronicle summary is too long ({len(str(summary))} > {MAX_CHRONICLE_SUMMARY_CHARS} chars)."
            )

        state = self._load_chronicle_state(require_cached=True)
        session = state["session"]
        save_id = state["save_id"]
        chapters_data = state["chapters_data"]
        chapter = self._find_chapter(chapters_data, int(chapter_number))
        if not chapter:
            raise McpContextError(f"Chapter {chapter_number} is not available in the cache.")

        before = _json_clone(chapters_data)
        updated_at = datetime.now(timezone.utc).isoformat()
        chapter["narrative"] = cleaned_narrative
        chapter["sections"] = self._normalize_sections(sections, fallback_text=cleaned_narrative)
        if title is not None and str(title).strip():
            chapter["title"] = str(title).strip()
        if summary is not None:
            chapter["summary"] = str(summary).strip()
        if epigraph is not None:
            chapter["epigraph"] = str(epigraph).strip()
        chapter["source"] = "mcp_writeback"
        chapter["external_edit"] = {
            "operation": "update_chapter",
            "source": "external_ai",
            "updated_at": updated_at,
        }
        chapter["manual_edit_locked"] = True

        self._record_external_edit(
            chapters_data,
            before=before,
            operation="update_chapter",
            target=f"chronicle.chapter.{chapter_number}",
            updated_at=updated_at,
        )
        self._persist_chronicle_state(
            session=session,
            save_id=save_id,
            chapters_data=chapters_data,
            snapshot_range=state["snapshot_range"],
        )

        return {
            "campaign": self.get_active_campaign(),
            "saved": True,
            "message": (
                f"Saved Chapter {chapter.get('number') or chapter_number}, "
                f'"{chapter.get("title") or "Untitled"}", to Stellaris Companion.'
            ),
            "saved_item": _chronicle_item_payload("chapter", chapter),
            "chapter": _chapter_payload(chapter),
            "narrative_chars": len(cleaned_narrative),
            "saved_at": updated_at,
            "app_visibility": (
                "The Chronicle page will show this revised chapter after it refreshes."
            ),
        }

    def create_chronicle_chapter(
        self,
        *,
        narrative: str,
        title: str,
        summary: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        start_snapshot_id: int | None = None,
        end_snapshot_id: int | None = None,
        epigraph: str | None = None,
        sections: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Append an externally written Chronicle chapter to the local archive."""
        cleaned_narrative = str(narrative or "").strip()
        self._validate_chronicle_text(cleaned_narrative, field_name="narrative")
        cleaned_title = str(title or "").strip()
        if not cleaned_title:
            raise McpContextError("Chapter title is required.")
        if summary is not None and len(str(summary)) > MAX_CHRONICLE_SUMMARY_CHARS:
            raise McpContextError(
                f"Chronicle summary is too long ({len(str(summary))} > {MAX_CHRONICLE_SUMMARY_CHARS} chars)."
            )

        state = self._load_chronicle_state()
        session = state["session"]
        save_id = state["save_id"]
        chapters_data = state["chapters_data"]
        chapters = self._ensure_chapters(chapters_data)
        before = _json_clone(chapters_data)
        snapshot_range = state["snapshot_range"]
        previous_chapter = chapters[-1] if chapters else None
        next_number = (
            max(
                (_safe_int(ch.get("number")) or 0 for ch in chapters if isinstance(ch, dict)),
                default=0,
            )
            + 1
        )
        resolved_start_date = (
            start_date
            or (previous_chapter.get("end_date") if isinstance(previous_chapter, dict) else None)
            or chapters_data.get("current_era_start_date")
            or snapshot_range.get("first_game_date")
            or session.get("first_game_date")
            or "2200.01.01"
        )
        resolved_end_date = (
            end_date
            or session.get("last_game_date")
            or session.get("last_game_date_computed")
            or snapshot_range.get("last_game_date")
            or resolved_start_date
        )
        resolved_start_snapshot_id = (
            start_snapshot_id
            if start_snapshot_id is not None
            else (
                previous_chapter.get("end_snapshot_id")
                if isinstance(previous_chapter, dict)
                else chapters_data.get("current_era_start_snapshot_id")
            )
        )
        if resolved_start_snapshot_id is None:
            resolved_start_snapshot_id = snapshot_range.get("first_snapshot_id")
        resolved_end_snapshot_id = (
            end_snapshot_id
            if end_snapshot_id is not None
            else snapshot_range.get("last_snapshot_id")
        )

        updated_at = datetime.now(timezone.utc).isoformat()
        chapter = {
            "number": next_number,
            "title": cleaned_title,
            "start_date": str(resolved_start_date),
            "end_date": str(resolved_end_date),
            "start_snapshot_id": resolved_start_snapshot_id,
            "end_snapshot_id": resolved_end_snapshot_id,
            "summary": str(summary or "").strip(),
            "narrative": cleaned_narrative,
            "sections": self._normalize_sections(sections, fallback_text=cleaned_narrative),
            "epigraph": str(epigraph or "").strip(),
            "is_finalized": True,
            "context_stale": False,
            "source": "mcp_writeback",
            "external_edit": {
                "operation": "create_chapter",
                "source": "external_ai",
                "updated_at": updated_at,
            },
            "manual_edit_locked": True,
        }
        chapters.append(_drop_empty(chapter))
        chapters_data["current_era_start_date"] = str(resolved_end_date)
        chapters_data["current_era_start_snapshot_id"] = resolved_end_snapshot_id
        chapters_data.pop("current_era_cache", None)

        self._record_external_edit(
            chapters_data,
            before=before,
            operation="create_chapter",
            target=f"chronicle.chapter.{next_number}",
            updated_at=updated_at,
        )
        self._persist_chronicle_state(
            session=session,
            save_id=save_id,
            chapters_data=chapters_data,
            snapshot_range=snapshot_range,
        )

        return {
            "campaign": self.get_active_campaign(),
            "saved": True,
            "message": (
                f'Saved Chapter {next_number}, "{chapter.get("title") or "Untitled"}", '
                "to Stellaris Companion."
            ),
            "saved_item": _chronicle_item_payload("chapter", chapter),
            "chapter": _chapter_payload(chapter),
            "narrative_chars": len(cleaned_narrative),
            "saved_at": updated_at,
            "app_visibility": ("The Chronicle page will show this new chapter after it refreshes."),
        }

    def undo_chronicle_edit(self) -> dict[str, Any]:
        """Undo the last external MCP Chronicle edit."""
        state = self._load_chronicle_state(require_cached=True)
        session = state["session"]
        save_id = state["save_id"]
        chapters_data = state["chapters_data"]
        history = self._external_edit_history(chapters_data)
        if not history:
            raise McpContextError("There is no external Chronicle edit to undo.")

        last_edit = history[-1]
        previous = last_edit.get("previous_chapters_data")
        if not isinstance(previous, dict):
            raise McpContextError(
                "The last Chronicle edit cannot be undone because its backup is missing."
            )

        restored = _json_clone(previous)
        restored["external_edit_history"] = history[:-1]
        restored["external_edit_last_updated_at"] = datetime.now(timezone.utc).isoformat()
        self._persist_chronicle_state(
            session=session,
            save_id=save_id,
            chapters_data=restored,
            snapshot_range=state["snapshot_range"],
        )

        return {
            "campaign": self.get_active_campaign(),
            "undone": True,
            "message": f"Undid the most recent Chronicle edit{_undo_target_phrase(last_edit)}.",
            "remaining_undo_count": len(history) - 1,
            "app_visibility": (
                "The Chronicle page will show the restored Chronicle after it refreshes."
            ),
        }

    def _load_chronicle_state(self, *, require_cached: bool = False) -> dict[str, Any]:
        session = self._require_current_session()
        save_id = str(session.get("save_id") or "")
        if not save_id:
            raise McpContextError("Current session has no save_id.")

        cached = self.db.get_chronicle_by_save_id(save_id, language=self.language)
        if not cached:
            cached = self.db.get_cached_chronicle(str(session["id"]), language=self.language)
        if require_cached and not cached:
            raise McpContextError("No cached Chronicle is available to edit.")

        chapters_data = _parse_json_object(cached.get("chapters_json")) if cached else {}
        if not chapters_data:
            chapters_data = _json_clone(DEFAULT_CHAPTERS_DATA)
        self._ensure_chapters(chapters_data)
        snapshot_range = self.db.get_snapshot_range_for_save(save_id)
        return {
            "session": session,
            "save_id": save_id,
            "cached": cached,
            "chapters_data": chapters_data,
            "snapshot_range": snapshot_range,
        }

    def _persist_chronicle_state(
        self,
        *,
        session: dict[str, Any],
        save_id: str,
        chapters_data: dict[str, Any],
        snapshot_range: dict[str, Any],
    ) -> None:
        current_era_cache = chapters_data.get("current_era_cache")
        current_era = (
            current_era_cache.get("current_era")
            if isinstance(current_era_cache, dict)
            and isinstance(current_era_cache.get("current_era"), dict)
            else None
        )
        chronicle_text = _assemble_chronicle_text(chapters_data, current_era)
        event_count = len(self.db.get_all_events_by_save_id(save_id=save_id))
        snapshot_count = int(
            snapshot_range.get("snapshot_count") or session.get("snapshot_count") or 0
        )
        self.db.upsert_chronicle_by_save_id(
            save_id=save_id,
            session_id=str(session["id"]),
            chronicle_text=chronicle_text,
            chapters_json=json.dumps(chapters_data, ensure_ascii=False),
            event_count=event_count,
            snapshot_count=snapshot_count,
            language=self.language,
        )

    def _validate_chronicle_text(self, value: str, *, field_name: str) -> None:
        if not value:
            raise McpContextError(f"Chronicle {field_name} is required.")
        if len(value) > MAX_CHRONICLE_WRITEBACK_CHARS:
            raise McpContextError(
                f"Chronicle {field_name} is too long for MCP write-back "
                f"({len(value)} > {MAX_CHRONICLE_WRITEBACK_CHARS} chars)."
            )

    def _ensure_chapters(self, chapters_data: dict[str, Any]) -> list[dict[str, Any]]:
        chapters = chapters_data.get("chapters")
        if not isinstance(chapters, list):
            chapters = []
            chapters_data["chapters"] = chapters
        return chapters

    def _normalize_sections(
        self,
        sections: list[dict[str, Any]] | None,
        *,
        fallback_text: str,
    ) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        if isinstance(sections, list):
            for section in sections[:12]:
                if not isinstance(section, dict):
                    continue
                text = str(section.get("text") or "").strip()
                if not text:
                    continue
                raw_type = str(section.get("type") or "prose").strip().lower()
                section_type = (
                    raw_type if raw_type in {"prose", "quote", "declaration"} else "prose"
                )
                normalized.append(
                    _drop_empty(
                        {
                            "type": section_type,
                            "text": text,
                            "attribution": str(section.get("attribution") or "").strip(),
                        }
                    )
                )
        if normalized:
            return normalized
        return [{"type": "prose", "text": fallback_text, "attribution": ""}]

    def _record_external_edit(
        self,
        chapters_data: dict[str, Any],
        *,
        before: dict[str, Any],
        operation: str,
        target: str,
        updated_at: str,
    ) -> None:
        history = self._external_edit_history(chapters_data)
        history.append(
            {
                "operation": operation,
                "target": target,
                "updated_at": updated_at,
                "source": "external_ai",
                "previous_chapters_data": _visible_chapters_snapshot(before),
            }
        )
        chapters_data["external_edit_history"] = history[-MAX_CHRONICLE_EDIT_HISTORY_ITEMS:]
        chapters_data["external_edit_last_updated_at"] = updated_at

    def _external_edit_history(self, chapters_data: dict[str, Any]) -> list[dict[str, Any]]:
        raw = chapters_data.get("external_edit_history")
        if not isinstance(raw, list):
            return []
        return [item for item in raw if isinstance(item, dict)]

    def _get_current_session(self) -> dict[str, Any] | None:
        row = self.db.execute(
            """
            SELECT
                s.id,
                s.save_id,
                s.save_path,
                s.empire_name,
                s.started_at,
                s.ended_at,
                s.last_game_date,
                s.last_updated_at,
                COUNT(snap.id) AS snapshot_count,
                MIN(snap.game_date) AS first_game_date,
                MAX(snap.game_date) AS last_game_date_computed
            FROM sessions s
            LEFT JOIN snapshots snap ON snap.session_id = s.id
            GROUP BY s.id
            ORDER BY (s.ended_at IS NULL) DESC, COALESCE(s.last_updated_at, s.started_at) DESC
            LIMIT 1;
            """
        ).fetchone()
        return dict(row) if row else None

    def _require_current_session(self) -> dict[str, Any]:
        session = self._get_current_session()
        if not session:
            raise McpContextError(
                "No campaign session is available in Stellaris Companion history."
            )
        return session

    def _load_briefing(self, session_id: str) -> dict[str, Any]:
        raw = self.db.get_latest_session_briefing_json(session_id=session_id)
        if not raw:
            raw = self.db.get_latest_snapshot_full_briefing_json(session_id=session_id)
        parsed = _parse_json_object(raw)
        return parsed

    def _get_advisor_custom(self, session_id: str) -> str | None:
        return self.db.get_session_advisor_custom(session_id=session_id)

    def _resolve_focus(self, *, question: str, focus: str) -> str:
        raw_focus = str(focus or "auto").strip().lower()
        if raw_focus in FOCUS_SECTIONS:
            return raw_focus

        text = question.lower()
        rules = [
            ("economy", ("economy", "energy", "minerals", "alloys", "consumer", "deficit")),
            ("military", ("fleet", "war", "naval", "ship", "army", "starbase", "power")),
            ("diplomacy", ("diplomacy", "federation", "ally", "rival", "subject", "vassal")),
            ("technology", ("tech", "research", "tradition", "ascension", "project")),
            ("territory", ("planet", "colony", "system", "sector", "claim", "border")),
            ("crisis", ("crisis", "khan", "fallen empire", "war in heaven", "endgame")),
            ("chronicle", ("chronicle", "chapter", "history", "story", "narrative")),
        ]
        for name, tokens in rules:
            if any(token in text for token in tokens):
                return name
        return "general"

    def _select_briefing_sections(self, briefing: dict[str, Any], focus: str) -> dict[str, Any]:
        sections = ["meta", "identity", *FOCUS_SECTIONS.get(focus, FOCUS_SECTIONS["general"])]
        selected: dict[str, Any] = {}
        for section in dict.fromkeys(sections):
            if section in briefing:
                selected[section] = _compact_value(briefing.get(section))
        return _drop_empty(selected)

    def _build_advisor_briefing(self, briefing: dict[str, Any], focus: str) -> dict[str, Any]:
        prioritized_sections = [
            "meta",
            "identity",
            *FOCUS_SECTIONS.get(focus, []),
            *ADVISOR_BRIEFING_SECTIONS,
            *briefing.keys(),
        ]
        selected: dict[str, Any] = {}
        for section in dict.fromkeys(prioritized_sections):
            if section in briefing:
                selected[section] = _compact_value(briefing.get(section))
        return _drop_empty(selected)

    def _advisor_response_guidance(self, briefing: dict[str, Any]) -> dict[str, Any]:
        return {
            "role": "strategic_advisor",
            "advisor_voice": self._advisor_voice_guidance(briefing),
            "answer_style": (
                "Answer as Stellaris Companion's in-universe strategic advisor. "
                "Interpret the campaign state, prioritize problems, and recommend concrete next actions."
            ),
            "recommended_shape": [
                "brief diagnosis",
                "campaign evidence using exact provided values",
                "top next actions",
                "trade-offs, risks, or what to check in-game",
            ],
            "presentation_contract": self._presentation_contract(kind="advisor"),
            "facts_policy": {
                "use_only_provided_context": True,
                "exact_numbers_only": True,
                "missing_values": "Say unknown or not available rather than estimating.",
                "distinguish_advice_from_facts": True,
                "respect_game_version_and_dlc": True,
            },
            "language_policy": self._language_guidance(),
            "advisor_memory_policy": (
                "Use advisor_memory as prior player intent or preference, not as evidence about "
                "the current campaign state."
            ),
            "custom_instructions_policy": (
                "Apply advisor_custom_instructions as player-provided style or priority guidance "
                "when present, without overriding factual accuracy."
            ),
            "naval_capacity_policy": self._naval_capacity_guidance(briefing),
            "tool_use_policy": {
                "main_tool": "Advisor Briefing is the preferred context for strategy questions.",
                "section_tool": "Use Empire Briefing only for follow-up detail or context-budget constraints.",
                "write_back_enabled": False,
                "in_app_llm_called": False,
            },
        }

    def _advisor_voice_guidance(self, briefing: dict[str, Any]) -> dict[str, Any]:
        identity = briefing.get("identity") if isinstance(briefing.get("identity"), dict) else {}
        situation = briefing.get("situation") if isinstance(briefing.get("situation"), dict) else {}
        empire_name = (
            identity.get("empire_name")
            or identity.get("name")
            or briefing.get("empire_name")
            or "the empire"
        )
        ethics = identity.get("ethics") if isinstance(identity.get("ethics"), list) else []
        civics = identity.get("civics") if isinstance(identity.get("civics"), list) else []

        if identity.get("is_machine"):
            voice = "Use precise, analytical machine-intelligence language while still giving direct strategic advice."
        elif identity.get("is_hive_mind"):
            voice = "Use collective hive-consciousness language and frame advice around the survival and growth of the whole."
        else:
            voice = (
                "Use colorful but concise roleplay language that reflects the empire's ethics, "
                "authority, civics, current danger level, and the player's custom advisor instructions."
            )

        return _drop_empty(
            {
                "persona": f"Strategic advisor to {empire_name}",
                "voice": voice,
                "empire_identity": {
                    "name": empire_name,
                    "ethics": [_display_identifier(str(item)) for item in ethics],
                    "civics": [_display_identifier(str(item)) for item in civics],
                    "at_war": situation.get("at_war"),
                    "game_phase": _display_identifier(str(situation.get("game_phase")))
                    if situation.get("game_phase")
                    else None,
                },
                "customization": (
                    "The advisor_custom_instructions field is player-authored persona and priority guidance. "
                    "Apply it unless it conflicts with factual accuracy."
                ),
            }
        )

    def _presentation_contract(self, *, kind: str) -> dict[str, Any]:
        base_rules = [
            "Do not expose tool names, operation names, database targets, source tags, schema fields, or implementation details unless the user asks for debugging.",
            "Use player-facing names and labels rather than raw game identifiers.",
            "Do not present raw JSON, tables of internal fields, or client/tool status as the answer.",
            "When exact evidence is useful, quote only user-facing campaign values such as dates, resource totals, fleet power, empire names, and chapter titles.",
        ]
        if kind == "chronicle":
            base_rules.append(
                "After a draft or revision, mention the save-back option in natural language without naming the underlying save tool."
            )
        return {
            "surface": "natural_chat",
            "rules": base_rules,
        }

    def _chronicle_archive_guidance(self, *, cached: bool) -> dict[str, Any]:
        if not cached:
            task = (
                "Tell the user no cached Chronicle is available yet. If they want new prose in "
                "chat, use Chronicle Source Material rather than inventing an archive."
            )
        else:
            task = (
                "Display, summarize, or discuss the existing cached Chronicle. Do not invent "
                "missing chapters or claim to regenerate the archive."
            )
        return {
            "role": "archive_reader",
            "task": task,
            "source_of_truth": "Use only the cached Chronicle chapters/current era returned by this tool.",
            "not_an_advisor": True,
            "do_not_fabricate_missing_chapters": True,
            "presentation_contract": self._presentation_contract(kind="chronicle"),
            "language_policy": self._language_guidance(),
            "write_back_enabled": True,
        }

    def _chronicle_source_guidance(
        self,
        briefing: dict[str, Any],
        event_range: dict[str, Any],
    ) -> dict[str, Any]:
        scope = str(event_range.get("scope") or "current_era")
        if scope == "current_era":
            output_shape = (
                "Write a brief, unresolved current-era passage, usually 1-3 sections. "
                "End by leaving the story open."
            )
        elif scope == "chapter":
            output_shape = (
                "Write a chapter-style passage with a title, optional epigraph, prose or quote "
                "sections, and a concise summary if the user asks for a full chapter."
            )
        else:
            output_shape = "Write a recap or narrative summary appropriate to the requested scope."

        return {
            "role": "royal_chronicler",
            "not_an_advisor": True,
            "source_of_truth": (
                "Use the returned events, event_range, briefing, cached chapter context, and "
                "Chronicle custom instructions as source material."
            ),
            "do_not_fabricate_events": True,
            "voice_guidance": self._chronicle_voice_guidance(briefing),
            "presentation_contract": self._presentation_contract(kind="chronicle"),
            "style_rules": [
                "Write as an in-universe historical chronicle, not a strategy answer.",
                "Use specific dates, leaders, systems, wars, and empire names when provided.",
                "When leader names are missing or placeholders, use titles instead.",
                "Preserve continuity with existing Chronicle chapter summaries when present.",
                "Do not claim the passage was saved into Stellaris Companion unless the user explicitly asks to save and a save tool succeeds.",
                "After presenting a draft or revision, briefly tell the user they can ask to save it back to Stellaris Companion when ready.",
            ],
            "output_shape": output_shape,
            "language_policy": self._language_guidance(),
            "custom_instructions_policy": (
                "Apply chronicle_custom_instructions as player-provided style guidance when present."
            ),
            "write_back_enabled": True,
            "save_policy": self._chronicle_save_affordance(),
        }

    def _chronicle_save_affordance(self) -> dict[str, Any]:
        return {
            "available": True,
            "offer_after_draft": True,
            "do_not_save_without_explicit_request": True,
            "save_intent_phrases": [
                "save this",
                "apply this",
                "send this to Stellaris Companion",
                "write this back",
                "save it back to the app",
            ],
            "suggested_phrase": (
                'When you are happy with this version, say "save this to Stellaris Companion" '
                "and I will send it back to the app."
            ),
        }

    def _language_guidance(self) -> dict[str, str]:
        return {
            "language": self.language,
            "name": language_name(self.language),
            "rule": (
                "Respond in this language. Preserve empire names, leader names, planet names, "
                "system names, ship names, and numeric values exactly as provided. Render raw "
                "game identifiers as readable player-facing labels."
            ),
        }

    def _naval_capacity_guidance(self, briefing: dict[str, Any]) -> dict[str, Any]:
        military = briefing.get("military") if isinstance(briefing.get("military"), dict) else {}
        naval_capacity = (
            military.get("naval_capacity")
            if isinstance(military.get("naval_capacity"), dict)
            else {}
        )
        analysis = (
            naval_capacity.get("analysis")
            if isinstance(naval_capacity.get("analysis"), dict)
            else {}
        )
        return {
            "current_usage_path": "briefing.military.naval_capacity.used",
            "safe_limit_path": "briefing.military.naval_capacity.analysis.limit",
            "exact_rule": (
                "Treat naval_capacity.used as current usage, not the cap ceiling. Only claim "
                "over/under/at naval cap when the briefing explicitly marks that claim as safe."
            ),
            "safe_to_claim_over_cap": bool(analysis.get("safe_to_claim_over_cap", False)),
            "safe_to_claim_limit": bool(analysis.get("safe_to_claim_limit", False)),
            "safe_to_claim_penalty": bool(analysis.get("safe_to_claim_penalty", False)),
        }

    def _chronicle_voice_guidance(self, briefing: dict[str, Any]) -> str:
        identity = briefing.get("identity") if isinstance(briefing.get("identity"), dict) else {}
        raw_ethics = identity.get("ethics", [])
        ethics = (
            " ".join(str(item).lower() for item in raw_ethics)
            if isinstance(raw_ethics, list)
            else str(raw_ethics).lower()
        )
        if identity.get("is_machine"):
            return "Use cold, logical precision and frame history as a data log for future processing units."
        if identity.get("is_hive_mind"):
            return (
                "Write as collective memory, using 'we' and framing history as growth of the whole."
            )
        if "authoritarian" in ethics:
            return "Use imperial grandeur, emphasizing the state, hierarchy, order, and command."
        if "egalitarian" in ethics:
            return "Celebrate collective achievement, the people, and democratic ideals."
        if "militarist" in ethics:
            return "Use martial pride, emphasizing battles, preparedness, conquests, and honor."
        if "spiritualist" in ethics:
            return "Use religious reverence and frame history as providence or sacred destiny."
        if "pacifist" in ethics:
            return "Value peace and diplomacy, framing conflict as tragedy and peace as triumph."
        if "materialist" in ethics:
            return "Celebrate scientific progress, reason, and the march of knowledge."
        return "Use epic gravitas befitting a galactic chronicle."

    def _find_chapter(
        self,
        chapters_data: dict[str, Any],
        chapter_number: int | None,
    ) -> dict[str, Any] | None:
        if chapter_number is None:
            return None
        chapters = chapters_data.get("chapters")
        if not isinstance(chapters, list):
            return None
        for chapter in chapters:
            if isinstance(chapter, dict) and chapter.get("number") == chapter_number:
                return chapter
        return None

    def _current_era_start_snapshot_id(self, chapters_data: dict[str, Any]) -> int | None:
        chapters = chapters_data.get("chapters")
        if isinstance(chapters, list) and chapters:
            last = chapters[-1]
            if isinstance(last, dict) and last.get("end_snapshot_id") is not None:
                return _safe_int(last.get("end_snapshot_id"))
        return _safe_int(chapters_data.get("current_era_start_snapshot_id"))


class contextlib_suppress_value_error:
    """Tiny local context manager to avoid importing contextlib for one narrow parse."""

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return exc_type is ValueError


def _parse_json_object(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_clone(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def _visible_chapters_snapshot(chapters_data: dict[str, Any]) -> dict[str, Any]:
    snapshot = _json_clone(chapters_data)
    if isinstance(snapshot, dict):
        snapshot.pop("external_edit_history", None)
    return snapshot if isinstance(snapshot, dict) else {}


def _event_payload(row: dict[str, Any]) -> dict[str, Any]:
    data = _parse_json_object(row.get("data_json"))
    return _drop_empty(
        {
            "id": row.get("id"),
            "captured_at": row.get("captured_at"),
            "game_date": row.get("game_date"),
            "event_type": _display_identifier(str(row.get("event_type") or "")),
            "summary": row.get("summary"),
            "data": _compact_value(data, max_depth=3, max_list_items=8),
        }
    )


def _chapter_payload(chapter: Any) -> dict[str, Any]:
    if not isinstance(chapter, dict):
        return {}
    return _drop_empty(
        {
            "number": chapter.get("number"),
            "title": chapter.get("title"),
            "start_date": chapter.get("start_date"),
            "end_date": chapter.get("end_date"),
            "summary": chapter.get("summary"),
            "narrative": chapter.get("narrative"),
            "epigraph": chapter.get("epigraph"),
            "sections": chapter.get("sections"),
            "is_finalized": chapter.get("is_finalized", True),
            "context_stale": chapter.get("context_stale", False),
            "start_snapshot_id": chapter.get("start_snapshot_id"),
            "end_snapshot_id": chapter.get("end_snapshot_id"),
        }
    )


def _current_era_payload(current_era: Any) -> dict[str, Any]:
    if not isinstance(current_era, dict):
        return {}
    return _drop_empty(
        {
            "title": current_era.get("title"),
            "start_date": current_era.get("start_date"),
            "narrative": current_era.get("narrative"),
            "sections": current_era.get("sections"),
            "events_covered": current_era.get("events_covered"),
        }
    )


def _chronicle_item_payload(kind: str, item: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "kind": kind,
        "title": item.get("title"),
        "start_date": item.get("start_date"),
    }
    if kind == "chapter":
        payload["chapter_number"] = item.get("number")
        payload["end_date"] = item.get("end_date")
    return _drop_empty(payload)


def _undo_target_phrase(edit: dict[str, Any]) -> str:
    target = str(edit.get("target") or "")
    if target == "chronicle.current_era":
        return " for the current-era draft"
    if target.startswith("chronicle.chapter."):
        chapter_number = target.rsplit(".", 1)[-1]
        if chapter_number.isdigit():
            return f" for Chapter {chapter_number}"
    return ""


def _assemble_chronicle_text(
    chapters_data: dict[str, Any],
    current_era: dict[str, Any] | None,
) -> str:
    lines: list[str] = []

    chapters = chapters_data.get("chapters")
    if isinstance(chapters, list):
        for chapter in chapters:
            if not isinstance(chapter, dict):
                continue
            number = chapter.get("number", "?")
            title = str(chapter.get("title") or "Untitled").upper()
            lines.append(f"### CHAPTER {number}: {title}")
            lines.append(f"**{chapter.get('start_date', '?')} – {chapter.get('end_date', '?')}**\n")
            lines.append(str(chapter.get("narrative") or ""))
            lines.append("")

    if current_era:
        lines.append("### THE CURRENT ERA")
        lines.append(f"**{current_era.get('start_date', '?')} – Present**\n")
        lines.append(str(current_era.get("narrative") or ""))

    return "\n".join(lines)


def _compact_value(
    value: Any,
    *,
    max_depth: int = 4,
    max_list_items: int = MAX_LIST_ITEMS_COMPACT,
    max_text_length: int = MAX_TEXT_LENGTH,
) -> Any:
    if max_depth <= 0:
        if isinstance(value, dict):
            return {"_truncated": f"{len(value)} keys"}
        if isinstance(value, list):
            return {"_truncated": f"{len(value)} items"}
        return value

    if isinstance(value, str):
        value = _display_identifier(value)
        if len(value) <= max_text_length:
            return value
        return f"{value[:max_text_length].rstrip()}... [truncated {len(value) - max_text_length} chars]"
    if isinstance(value, int | float | bool) or value is None:
        return value
    if isinstance(value, list):
        items = [
            _compact_value(
                item,
                max_depth=max_depth - 1,
                max_list_items=max_list_items,
                max_text_length=max_text_length,
            )
            for item in value[:max_list_items]
        ]
        if len(value) > max_list_items:
            items.append({"_truncated_items": len(value) - max_list_items})
        return items
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.startswith("_") and key_text not in {"_note"}:
                continue
            result[key_text] = _compact_value(
                item,
                max_depth=max_depth - 1,
                max_list_items=max_list_items,
                max_text_length=max_text_length,
            )
        return _drop_empty(result)
    return str(value)


def _display_identifier(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return text
    if text in DISPLAY_NAME_OVERRIDES:
        return DISPLAY_NAME_OVERRIDES[text]
    if not _looks_like_display_identifier(text):
        return value

    stem = text
    for prefix in sorted(DISPLAY_ID_PREFIXES, key=len, reverse=True):
        if stem.startswith(prefix):
            stem = stem[len(prefix) :]
            break

    parts = [part for part in stem.split("_") if part]
    suffix = ""
    if len(parts) > 1 and parts[-1] in ROMAN_NUMERALS:
        suffix = f" {ROMAN_NUMERALS[parts.pop()]}"
    label = " ".join(_title_part(part) for part in parts).strip()
    return f"{label}{suffix}".strip() or value


def _looks_like_display_identifier(value: str) -> bool:
    if value in DISPLAY_NAME_OVERRIDES:
        return True
    return bool(DISPLAY_ID_PATTERN.match(value))


def _title_part(part: str) -> str:
    if part.upper() in {"FTL", "AI", "DNA"}:
        return part.upper()
    return part.capitalize()


def _drop_empty(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in value.items()
        if item is not None and item != {} and item != [] and item != ""
    }


def _clamp_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
