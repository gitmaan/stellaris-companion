"""
Chronicle Generation Engine
============================

LLM-powered narrative generation for empire storytelling.
Produces dramatic, Stellaris Invicta-style chronicles from game events.

Supports incremental chapters - early chapters are permanent while new
chapters are added as the game progresses.

See docs/CHRONICLE_IMPLEMENTATION.md for original specification.
See docs/CHRONICLE_INCREMENTAL.md for incremental chapter design.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

from google import genai
from pydantic import BaseModel, Field

from backend.core.database import GameDatabase

logger = logging.getLogger(__name__)


# ============================================
# Pydantic models for structured LLM output
# ============================================


class ChapterOutput(BaseModel):
    """Structured output schema for chapter generation."""

    title: str = Field(
        description="A dramatic, thematic name for this chapter/era (e.g., 'The Cradle's Awakening', 'The Great Expansion')"
    )
    narrative: str = Field(
        description="3-5 paragraphs of dramatic prose describing the events of this era (500-800 words). Write as a historian chronicling history, not as an advisor."
    )
    summary: str = Field(
        description="2-3 sentences summarizing the key events for context in future chapters."
    )


def _repair_json_string(text: str) -> str:
    """Repair JSON with unescaped newlines in string values.

    Gemini sometimes returns JSON with literal newlines inside strings,
    which is invalid JSON. This function escapes them properly.
    """
    # Strategy: Find string values and escape newlines within them
    # This regex finds content between quotes (handling escaped quotes)
    result = []
    in_string = False
    escape_next = False
    i = 0

    while i < len(text):
        char = text[i]

        if escape_next:
            result.append(char)
            escape_next = False
            i += 1
            continue

        if char == "\\":
            result.append(char)
            escape_next = True
            i += 1
            continue

        if char == '"':
            result.append(char)
            in_string = not in_string
            i += 1
            continue

        if in_string and char == "\n":
            # Escape the newline
            result.append("\\n")
            i += 1
            continue

        if in_string and char == "\r":
            # Skip carriage returns (will be part of \r\n -> \n)
            i += 1
            continue

        if in_string and char == "\t":
            # Escape tabs
            result.append("\\t")
            i += 1
            continue

        result.append(char)
        i += 1

    return "".join(result)


# Era-ending event types that trigger chapter finalization
ERA_ENDING_EVENTS = {
    "war_ended",
    "crisis_defeated",
    "fallen_empire_awakened",
    "war_in_heaven_started",
    "federation_joined",
    "federation_left",
}

# Years between chapters (if no era-ending event)
CHAPTER_TIME_THRESHOLD = 50

# Minimum years after era-ending event before finalizing
MIN_YEARS_AFTER_EVENT = 5

# Maximum chapters to finalize per request (prevent timeout)
MAX_CHAPTERS_PER_REQUEST = 2

# Hard caps to keep Gemini requests reasonably sized.
# These limits are deliberately conservative to avoid saturating the user's network.
MAX_EVENTS_PER_CHAPTER_PROMPT = 250
MAX_EVENTS_CURRENT_ERA_PROMPT = 200

NOTABLE_EVENT_TYPES = {
    "war_started",
    "war_ended",
    "crisis_started",
    "crisis_defeated",
    "fallen_empire_awakened",
    "war_in_heaven_started",
    "federation_joined",
    "federation_left",
    "alliance_formed",
    "alliance_ended",
    "colony_count_change",
    "military_power_change",
}

# Default chapters_json structure
DEFAULT_CHAPTERS_DATA = {
    "format_version": 1,
    "chapters": [],
    "current_era_start_date": None,
    "current_era_start_snapshot_id": None,
}


def parse_year(date_str: str | None) -> int | None:
    """Parse year from Stellaris date string (e.g., '2250.03.15')."""
    if not date_str or not isinstance(date_str, str):
        return None
    try:
        return int(date_str.split(".")[0])
    except (ValueError, IndexError):
        return None


class ChronicleGenerator:
    """Generate LLM-powered chronicles for empire sessions.

    Supports incremental chapters keyed by save_id for cross-session continuity.
    """

    # Staleness thresholds for legacy blob-based cache
    STALE_EVENT_THRESHOLD = 10
    STALE_SNAPSHOT_THRESHOLD = 5

    def __init__(self, db: GameDatabase, api_key: str | None = None):
        self.db = db
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY")
        self._client: genai.Client | None = None

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            if not self.api_key:
                raise ValueError("GOOGLE_API_KEY not configured")
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def generate_chronicle(
        self,
        session_id: str,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        """Generate an incremental chronicle for the session.

        Returns structured response with chapters and current era.
        Maintains backward compatibility with legacy 'chronicle' string field.
        """
        # Get save_id for cross-session continuity
        save_id = self.db.get_save_id_for_session(session_id)
        if not save_id:
            session = self.db.get_session_by_id(session_id)
            if not session:
                raise ValueError(f"Session not found: {session_id}")
            save_id = session.get("save_id")

        if not save_id:
            # Fallback to session-based chronicle (legacy)
            return self._generate_legacy_chronicle(
                session_id, force_refresh=force_refresh
            )

        # Load existing chapters data
        cached = self.db.get_chronicle_by_save_id(save_id)
        chapters_data = self._load_chapters_data(cached)

        # Get current state
        snapshot_range = self.db.get_snapshot_range_for_save(save_id)
        if not snapshot_range.get("snapshot_count"):
            return self._empty_chronicle_response()

        current_date = snapshot_range.get("last_game_date")
        current_snapshot_id = snapshot_range.get("last_snapshot_id")

        # Gather briefing for current session
        briefing_json = self.db.get_latest_session_briefing_json(session_id=session_id)
        briefing = json.loads(briefing_json) if briefing_json else {}

        # Check if we need to finalize any chapters
        chapters_finalized = 0
        pending_chapters = 0

        while chapters_finalized < MAX_CHAPTERS_PER_REQUEST:
            should_finalize, trigger = self._should_finalize_chapter(
                save_id=save_id,
                chapters_data=chapters_data,
                current_date=current_date,
                current_snapshot_id=current_snapshot_id,
            )
            if not should_finalize:
                break

            # Finalize the chapter
            self._finalize_chapter(
                save_id=save_id,
                chapters_data=chapters_data,
                briefing=briefing,
                trigger=trigger,
            )
            chapters_finalized += 1

        # Count remaining pending chapters
        pending_chapters = self._count_pending_chapters(
            save_id=save_id,
            chapters_data=chapters_data,
            current_date=current_date,
            current_snapshot_id=current_snapshot_id,
        )

        # Generate (or reuse cached) current era narrative.
        era_start_date, era_start_snapshot_id = self._get_current_era_start(
            save_id=save_id,
            chapters_data=chapters_data,
            snapshot_range=snapshot_range,
        )

        used_cached_current_era = False
        current_era_cache = chapters_data.get("current_era_cache")
        if (
            not force_refresh
            and isinstance(current_era_cache, dict)
            and current_snapshot_id is not None
            and current_era_cache.get("start_snapshot_id") == era_start_snapshot_id
            and current_era_cache.get("last_snapshot_id") == current_snapshot_id
            and isinstance(current_era_cache.get("current_era"), dict)
        ):
            used_cached_current_era = True
            current_era = current_era_cache["current_era"]
            logger.debug(
                "Chronicle current era cache hit (save_id=%s last_snapshot_id=%s)",
                save_id,
                current_snapshot_id,
            )
        else:
            if current_era_cache and not used_cached_current_era:
                chapters_data.pop("current_era_cache", None)

            current_era = self._generate_current_era(
                save_id=save_id,
                chapters_data=chapters_data,
                briefing=briefing,
                current_date=current_date,
            )

            if current_era and current_snapshot_id is not None:
                chapters_data["current_era_cache"] = {
                    "start_date": era_start_date,
                    "start_snapshot_id": era_start_snapshot_id,
                    "last_snapshot_id": current_snapshot_id,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "current_era": current_era,
                }
                logger.debug(
                    "Chronicle current era generated (save_id=%s last_snapshot_id=%s)",
                    save_id,
                    current_snapshot_id,
                )

        # Assemble full chronicle text for backward compatibility
        full_text = self._assemble_chronicle_text(chapters_data, current_era)

        # Calculate total event count
        all_events = self.db.get_all_events_by_save_id(save_id=save_id)
        event_count = len(all_events)
        snapshot_count = snapshot_range.get("snapshot_count", 0)

        # Save updated chapters
        self.db.upsert_chronicle_by_save_id(
            save_id=save_id,
            session_id=session_id,
            chronicle_text=full_text,
            chapters_json=json.dumps(chapters_data, ensure_ascii=False),
            event_count=event_count,
            snapshot_count=snapshot_count,
        )

        # Build response
        response_cached = (
            not force_refresh
            and chapters_finalized == 0
            and (used_cached_current_era or current_era is None)
        )
        return {
            # New structured format
            "chapters": [
                {
                    "number": ch["number"],
                    "title": ch["title"],
                    "start_date": ch["start_date"],
                    "end_date": ch["end_date"],
                    "narrative": ch["narrative"],
                    "summary": ch.get("summary", ""),
                    "is_finalized": ch.get("is_finalized", True),
                    "context_stale": ch.get("context_stale", False),
                    "can_regenerate": ch.get("is_finalized", True),
                }
                for ch in chapters_data.get("chapters", [])
            ],
            "current_era": current_era,
            "pending_chapters": pending_chapters,
            "message": (
                f"{pending_chapters} more chapters pending. Refresh to continue."
                if pending_chapters > 0
                else None
            ),
            # Backward compatible
            "chronicle": full_text,
            "cached": response_cached,
            "event_count": event_count,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _event_key(self, event: dict) -> tuple[Any, Any, Any]:
        return (event.get("game_date"), event.get("event_type"), event.get("summary"))

    def _select_events_for_prompt(
        self, events: list[dict], *, max_events: int
    ) -> tuple[list[dict], bool]:
        """Select a bounded subset of events for prompt size safety.

        Returns (selected_events, was_truncated).
        """
        if max_events <= 0:
            return [], bool(events)

        if len(events) <= max_events:
            return events, False

        # Deduplicate while preserving order.
        seen: set[tuple[Any, Any, Any]] = set()
        deduped: list[dict] = []
        for event in events:
            key = self._event_key(event)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(event)

        if len(deduped) <= max_events:
            return deduped, False

        notable: list[dict] = [
            e for e in deduped if e.get("event_type") in NOTABLE_EVENT_TYPES
        ]

        selected_keys: list[tuple[Any, Any, Any]]
        if len(notable) >= max_events:
            selected_keys = [self._event_key(e) for e in notable[-max_events:]]
        else:
            selected_set = {self._event_key(e) for e in notable}
            selected_keys = list(selected_set)
            for event in reversed(deduped):
                key = self._event_key(event)
                if key in selected_set:
                    continue
                selected_set.add(key)
                selected_keys.append(key)
                if len(selected_set) >= max_events:
                    break

        selected_set = set(selected_keys)
        selected: list[dict] = []
        included: set[tuple[Any, Any, Any]] = set()
        for event in deduped:
            key = self._event_key(event)
            if key in selected_set and key not in included:
                included.add(key)
                selected.append(event)

        return selected, True

    def _get_current_era_start(
        self,
        *,
        save_id: str,
        chapters_data: dict[str, Any],
        snapshot_range: dict[str, Any],
    ) -> tuple[str, int | None]:
        chapters = chapters_data.get("chapters", [])

        if chapters:
            return (
                chapters[-1].get("end_date"),
                chapters[-1].get("end_snapshot_id"),
            )

        era_start_date = chapters_data.get("current_era_start_date")
        era_start_snapshot_id = chapters_data.get("current_era_start_snapshot_id")
        if not era_start_date:
            era_start_date = snapshot_range.get("first_game_date", "2200.01.01")
            era_start_snapshot_id = snapshot_range.get("first_snapshot_id")

        return era_start_date, era_start_snapshot_id

    def regenerate_chapter(
        self,
        session_id: str,
        chapter_number: int,
        *,
        confirm: bool = False,
    ) -> dict[str, Any]:
        """Regenerate a specific finalized chapter.

        Returns error if confirm=False (requires explicit confirmation).
        Marks downstream chapters as context_stale.
        """
        if not confirm:
            return {"error": "Must confirm regeneration", "confirm_required": True}

        save_id = self.db.get_save_id_for_session(session_id)
        if not save_id:
            raise ValueError(f"No save_id for session: {session_id}")

        cached = self.db.get_chronicle_by_save_id(save_id)
        if not cached:
            raise ValueError(f"No chronicle found for save: {save_id}")

        chapters_data = self._load_chapters_data(cached)
        chapters = chapters_data.get("chapters", [])

        if chapter_number < 1 or chapter_number > len(chapters):
            raise ValueError(f"Invalid chapter number: {chapter_number}")

        chapter = chapters[chapter_number - 1]
        if not chapter.get("is_finalized"):
            raise ValueError(f"Chapter {chapter_number} is not finalized")

        # Get briefing for voice/context
        briefing_json = self.db.get_latest_session_briefing_json(session_id=session_id)
        briefing = json.loads(briefing_json) if briefing_json else {}

        # Get events for this chapter's time range
        events = self.db.get_events_in_snapshot_range(
            save_id=save_id,
            from_snapshot_id=chapter.get("start_snapshot_id"),
            to_snapshot_id=chapter.get("end_snapshot_id"),
        )

        # Get previous chapters for context
        previous_chapters = chapters[: chapter_number - 1]

        # Regenerate the chapter
        new_content = self._generate_chapter_content(
            chapter_number=chapter_number,
            events=events,
            briefing=briefing,
            previous_chapters=previous_chapters,
            start_date=chapter["start_date"],
            end_date=chapter["end_date"],
        )

        # Update the chapter
        chapter["title"] = new_content["title"]
        chapter["narrative"] = new_content["narrative"]
        chapter["summary"] = new_content["summary"]
        chapter["generated_at"] = datetime.now(timezone.utc).isoformat()
        chapter["context_stale"] = False

        # Mark downstream chapters as stale
        for i in range(chapter_number, len(chapters)):
            chapters[i]["context_stale"] = True

        # Save updated chapters
        full_text = self._assemble_chronicle_text(chapters_data, None)
        snapshot_range = self.db.get_snapshot_range_for_save(save_id)
        all_events = self.db.get_all_events_by_save_id(save_id=save_id)

        self.db.upsert_chronicle_by_save_id(
            save_id=save_id,
            session_id=session_id,
            chronicle_text=full_text,
            chapters_json=json.dumps(chapters_data, ensure_ascii=False),
            event_count=len(all_events),
            snapshot_count=snapshot_range.get("snapshot_count", 0),
        )

        return {
            "chapter": chapter,
            "regenerated": True,
            "stale_chapters": list(range(chapter_number + 1, len(chapters) + 1)),
        }

    def generate_recap(
        self,
        session_id: str,
        *,
        style: str = "summary",
        max_events: int = 30,
    ) -> dict[str, Any]:
        """Generate a recap for the session.

        Args:
            style: "summary" (deterministic) or "dramatic" (LLM-powered)
        """
        if style == "summary":
            from backend.core.reporting import build_session_report_text

            recap = build_session_report_text(db=self.db, session_id=session_id)
            return {"recap": recap, "style": "summary"}

        # Dramatic LLM-powered recap
        data = self._gather_session_data(session_id, max_events=max_events)

        if not data["events"]:
            return {
                "recap": "No events to recap. The story has yet to begin.",
                "style": "dramatic",
                "events_summarized": 0,
            }

        prompt = self._build_recap_prompt(data)

        response = self.client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt,
            config={"temperature": 1.0, "max_output_tokens": 2048},
        )

        return {
            "recap": response.text,
            "style": "dramatic",
            "events_summarized": len(data["events"]),
        }

    # --- Private Methods ---

    def _load_chapters_data(self, cached: dict[str, Any] | None) -> dict[str, Any]:
        """Load chapters_json or return default structure."""
        if not cached:
            return dict(DEFAULT_CHAPTERS_DATA)

        chapters_json = cached.get("chapters_json")
        if not chapters_json:
            return dict(DEFAULT_CHAPTERS_DATA)

        try:
            data = json.loads(chapters_json)
            if not isinstance(data, dict):
                return dict(DEFAULT_CHAPTERS_DATA)
            return data
        except json.JSONDecodeError:
            return dict(DEFAULT_CHAPTERS_DATA)

    def _should_finalize_chapter(
        self,
        save_id: str,
        chapters_data: dict[str, Any],
        current_date: str | None,
        current_snapshot_id: int | None,
    ) -> tuple[bool, str | None]:
        """Check if we should finalize a new chapter.

        Returns (should_finalize, trigger_reason).
        """
        if not current_date or not current_snapshot_id:
            return False, None

        chapters = chapters_data.get("chapters", [])
        current_year = parse_year(current_date)
        if current_year is None:
            return False, None

        # Determine the era start point
        if chapters:
            last_chapter = chapters[-1]
            era_start_date = last_chapter.get("end_date")
            era_start_snapshot_id = last_chapter.get("end_snapshot_id")
        else:
            era_start_date = chapters_data.get("current_era_start_date")
            era_start_snapshot_id = chapters_data.get("current_era_start_snapshot_id")
            if not era_start_date:
                # First chapter - get from snapshot range
                snapshot_range = self.db.get_snapshot_range_for_save(save_id)
                era_start_date = snapshot_range.get("first_game_date", "2200.01.01")
                era_start_snapshot_id = snapshot_range.get("first_snapshot_id")

        era_start_year = parse_year(era_start_date)
        if era_start_year is None:
            return False, None

        # Check time threshold (50+ years)
        years_elapsed = current_year - era_start_year
        if years_elapsed >= CHAPTER_TIME_THRESHOLD:
            return True, "time_threshold"

        # Check for era-ending events
        events = self.db.get_events_in_snapshot_range(
            save_id=save_id,
            from_snapshot_id=era_start_snapshot_id,
            to_snapshot_id=current_snapshot_id,
        )

        for event in events:
            if event.get("event_type") in ERA_ENDING_EVENTS:
                event_year = parse_year(event.get("game_date"))
                if event_year and (current_year - event_year) >= MIN_YEARS_AFTER_EVENT:
                    return True, event.get("event_type")

        return False, None

    def _count_pending_chapters(
        self,
        save_id: str,
        chapters_data: dict[str, Any],
        current_date: str | None,
        current_snapshot_id: int | None,
    ) -> int:
        """Count how many more chapters could be finalized."""
        count = 0
        temp_data = json.loads(json.dumps(chapters_data))  # Deep copy

        # Simulate finalization to count pending
        for _ in range(10):  # Max 10 to prevent infinite loop
            should_finalize, trigger = self._should_finalize_chapter(
                save_id=save_id,
                chapters_data=temp_data,
                current_date=current_date,
                current_snapshot_id=current_snapshot_id,
            )
            if not should_finalize:
                break

            # Simulate adding a chapter
            chapters = temp_data.get("chapters", [])
            if chapters:
                last_end = chapters[-1].get("end_date", "2200.01.01")
            else:
                snapshot_range = self.db.get_snapshot_range_for_save(save_id)
                last_end = snapshot_range.get("first_game_date", "2200.01.01")

            last_year = parse_year(last_end)
            new_end_year = (last_year or 2200) + CHAPTER_TIME_THRESHOLD
            new_end_date = f"{new_end_year}.01.01"

            temp_data["chapters"].append(
                {
                    "number": len(chapters) + 1,
                    "end_date": new_end_date,
                    "end_snapshot_id": current_snapshot_id,
                }
            )
            count += 1

        return count

    def _finalize_chapter(
        self,
        save_id: str,
        chapters_data: dict[str, Any],
        briefing: dict[str, Any],
        trigger: str | None,
    ) -> None:
        """Generate and finalize a new chapter."""
        chapters = chapters_data.get("chapters", [])
        chapter_number = len(chapters) + 1

        # Determine chapter date range
        if chapters:
            last_chapter = chapters[-1]
            start_date = last_chapter.get("end_date")
            start_snapshot_id = last_chapter.get("end_snapshot_id")
        else:
            snapshot_range = self.db.get_snapshot_range_for_save(save_id)
            start_date = snapshot_range.get("first_game_date", "2200.01.01")
            start_snapshot_id = snapshot_range.get("first_snapshot_id")

        # Find the end date based on trigger
        if trigger == "time_threshold":
            start_year = parse_year(start_date) or 2200
            end_year = start_year + CHAPTER_TIME_THRESHOLD
            end_date = f"{end_year}.01.01"
        else:
            # Use the triggering event's date as chapter end
            events = self.db.get_all_events_by_save_id(save_id=save_id)
            end_date = start_date
            for event in reversed(events):
                if event.get("event_type") == trigger:
                    end_date = event.get("game_date", end_date)
                    break

        # Get end snapshot ID (approximate - use events captured_at)
        snapshot_range = self.db.get_snapshot_range_for_save(save_id)
        end_snapshot_id = snapshot_range.get("last_snapshot_id")

        # Get events for this chapter
        chapter_events = self.db.get_events_in_snapshot_range(
            save_id=save_id,
            from_snapshot_id=start_snapshot_id,
            to_snapshot_id=end_snapshot_id,
        )

        # Filter events to chapter date range
        end_year = parse_year(end_date)
        chapter_events = [
            e
            for e in chapter_events
            if (parse_year(e.get("game_date")) or 0) <= (end_year or 9999)
        ]

        # Generate chapter content
        content = self._generate_chapter_content(
            chapter_number=chapter_number,
            events=chapter_events,
            briefing=briefing,
            previous_chapters=chapters,
            start_date=start_date,
            end_date=end_date,
        )

        # Add the new chapter
        chapters_data["chapters"].append(
            {
                "number": chapter_number,
                "title": content["title"],
                "start_date": start_date,
                "end_date": end_date,
                "start_snapshot_id": start_snapshot_id,
                "end_snapshot_id": end_snapshot_id,
                "narrative": content["narrative"],
                "summary": content["summary"],
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "is_finalized": True,
                "context_stale": False,
                "trigger": trigger,
                "event_count": len(chapter_events),
            }
        )

        # Update current era start
        chapters_data["current_era_start_date"] = end_date
        chapters_data["current_era_start_snapshot_id"] = end_snapshot_id

    def _generate_chapter_content(
        self,
        chapter_number: int,
        events: list[dict],
        briefing: dict[str, Any],
        previous_chapters: list[dict],
        start_date: str,
        end_date: str,
    ) -> dict[str, str]:
        """Generate chapter content using Gemini structured output."""
        identity = briefing.get("identity", {})
        empire_name = identity.get("empire_name", "Unknown Empire")
        ethics = ", ".join(identity.get("ethics", []))
        voice = self._get_voice_for_ethics(identity, ethics)

        # Build context from previous chapters
        context_lines = []
        for ch in previous_chapters:
            context_lines.append(
                f"- Chapter {ch['number']} \"{ch.get('title', 'Untitled')}\" "
                f"({ch.get('start_date', '?')} - {ch.get('end_date', '?')}): {ch.get('summary', '')}"
            )
        previous_context = (
            "\n".join(context_lines) if context_lines else "This is the first chapter."
        )

        selected_events, was_truncated = self._select_events_for_prompt(
            events, max_events=MAX_EVENTS_PER_CHAPTER_PROMPT
        )
        if was_truncated:
            logger.debug(
                "Chapter %s prompt events truncated (%s -> %s)",
                chapter_number,
                len(events),
                len(selected_events),
            )
        events_text = self._format_events(selected_events)
        truncation_note = ""
        if was_truncated:
            truncation_note = (
                f"NOTE: Event list truncated to {len(selected_events)} events to fit context. "
                "Focus on major arcs and turning points.\n"
            )

        prompt = f"""You are the Royal Chronicler of {empire_name}.

=== CHRONICLER'S VOICE ===
{voice}

=== PREVIOUS CHAPTERS ===
{previous_context}

=== EVENTS FOR THIS CHAPTER ({start_date} to {end_date}) ===
{truncation_note}
{events_text}

=== YOUR TASK ===

Write Chapter {chapter_number} of the empire's chronicle.

Requirements:
- Title: A dramatic, thematic name for this era (e.g., "The Cradle's Awakening", "The Great Handshake")
- Narrative: 3-5 paragraphs of dramatic prose (500-800 words)
- Summary: 2-3 sentences summarizing key events for future chapter context

Do NOT give advice. You are a historian, not an advisor.
Do NOT fabricate events not in the event list.
"""

        try:
            response = self.client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=prompt,
                config={
                    "temperature": 1.0,
                    "max_output_tokens": 2048,
                    "response_mime_type": "application/json",
                    "response_schema": ChapterOutput,
                },
            )

            # Parse with Pydantic for validation
            chapter = ChapterOutput.model_validate_json(response.text)
            return {
                "title": chapter.title,
                "narrative": chapter.narrative,
                "summary": chapter.summary,
            }
        except Exception as e:
            # Fallback for errors - try JSON repair as last resort
            logger.warning(
                "Structured output failed for chapter %d: %s", chapter_number, e
            )
            try:
                # Attempt JSON repair if we got a response
                if hasattr(e, "__context__") and hasattr(e.__context__, "doc"):
                    raw_text = e.__context__.doc
                else:
                    raw_text = (
                        getattr(response, "text", "") if "response" in dir() else ""
                    )

                if raw_text:
                    repaired = _repair_json_string(raw_text)
                    result = json.loads(repaired)
                    logger.info("JSON repair succeeded for chapter %d", chapter_number)
                    return {
                        "title": result.get("title", f"Chapter {chapter_number}"),
                        "narrative": result.get("narrative", ""),
                        "summary": result.get("summary", ""),
                    }
            except Exception:
                pass

            return {
                "title": f"Chapter {chapter_number}",
                "narrative": f"[Generation error: {e}]",
                "summary": "",
            }

    def _generate_current_era(
        self,
        save_id: str,
        chapters_data: dict[str, Any],
        briefing: dict[str, Any],
        current_date: str | None,
    ) -> dict[str, Any] | None:
        """Generate the current era narrative (not finalized)."""
        chapters = chapters_data.get("chapters", [])

        # Determine era start
        if chapters:
            era_start_date = chapters[-1].get("end_date")
            era_start_snapshot_id = chapters[-1].get("end_snapshot_id")
        else:
            era_start_date = chapters_data.get("current_era_start_date")
            era_start_snapshot_id = chapters_data.get("current_era_start_snapshot_id")
            if not era_start_date:
                snapshot_range = self.db.get_snapshot_range_for_save(save_id)
                era_start_date = snapshot_range.get("first_game_date", "2200.01.01")
                era_start_snapshot_id = snapshot_range.get("first_snapshot_id")

        # Get events for current era
        events = self.db.get_events_in_snapshot_range(
            save_id=save_id,
            from_snapshot_id=era_start_snapshot_id,
            to_snapshot_id=None,  # Up to current
        )

        if not events:
            return None

        identity = briefing.get("identity", {})
        empire_name = identity.get("empire_name", "Unknown Empire")
        ethics = ", ".join(identity.get("ethics", []))
        voice = self._get_voice_for_ethics(identity, ethics)

        # Build previous chapters context
        context_lines = []
        for ch in chapters:
            context_lines.append(
                f"- Chapter {ch['number']} \"{ch.get('title', 'Untitled')}\": {ch.get('summary', '')}"
            )
        previous_context = (
            "\n".join(context_lines) if context_lines else "No previous chapters."
        )

        selected_events, was_truncated = self._select_events_for_prompt(
            events, max_events=MAX_EVENTS_CURRENT_ERA_PROMPT
        )
        if was_truncated:
            logger.debug(
                "Current era prompt events truncated (%s -> %s) (save_id=%s)",
                len(events),
                len(selected_events),
                save_id,
            )
        events_text = self._format_events(selected_events)
        truncation_note = ""
        if was_truncated:
            truncation_note = (
                f"NOTE: Event list truncated to {len(selected_events)} events to fit context. "
                "Focus on major arcs and the immediate stakes.\n"
            )

        prompt = f"""You are the Royal Chronicler of {empire_name}.

=== CHRONICLER'S VOICE ===
{voice}

=== PREVIOUS CHAPTERS ===
{previous_context}

=== CURRENT ERA EVENTS ({era_start_date} to present) ===
{truncation_note}
{events_text}

=== YOUR TASK ===

Write a brief narrative for "The Current Era" - the unfolding present.
This is NOT a finalized chapter - it's a 1-2 paragraph teaser about current events.
End with "The story continues..." to indicate this era is still being written.

Do NOT give advice. You are a historian, not an advisor.
"""

        try:
            response = self.client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=prompt,
                config={"temperature": 1.0, "max_output_tokens": 1024},
            )

            return {
                "start_date": era_start_date,
                "narrative": response.text,
                "events_covered": len(events),
            }
        except Exception:
            return {
                "start_date": era_start_date,
                "narrative": "The current era unfolds...\n\nThe story continues...",
                "events_covered": len(events),
            }

    def _assemble_chronicle_text(
        self,
        chapters_data: dict[str, Any],
        current_era: dict[str, Any] | None,
    ) -> str:
        """Assemble full chronicle text from chapters and current era."""
        lines = []

        chapters = chapters_data.get("chapters", [])
        for ch in chapters:
            lines.append(
                f"### CHAPTER {ch['number']}: {ch.get('title', 'Untitled').upper()}"
            )
            lines.append(
                f"**{ch.get('start_date', '?')} – {ch.get('end_date', '?')}**\n"
            )
            lines.append(ch.get("narrative", ""))
            lines.append("")

        if current_era:
            lines.append("### THE CURRENT ERA")
            lines.append(f"**{current_era.get('start_date', '?')} – Present**\n")
            lines.append(current_era.get("narrative", ""))

        return "\n".join(lines)

    def _empty_chronicle_response(self) -> dict[str, Any]:
        """Return empty chronicle response."""
        return {
            "chapters": [],
            "current_era": None,
            "pending_chapters": 0,
            "message": None,
            "chronicle": "No events recorded yet. The chronicle awaits the first chapters of history.",
            "cached": False,
            "event_count": 0,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # --- Legacy Support ---

    def _generate_legacy_chronicle(
        self,
        session_id: str,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        """Generate chronicle using legacy blob-based approach (for backward compatibility)."""
        # Check cache (unless force refresh)
        if not force_refresh:
            cached = self._get_cached_if_valid(session_id)
            if cached:
                return cached

        # Gather data
        data = self._gather_session_data(session_id)

        if not data["events"]:
            return {
                "chronicle": "No events recorded yet. The chronicle awaits the first chapters of history.",
                "cached": False,
                "event_count": 0,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        # Build prompt
        prompt = self._build_chronicler_prompt(data)

        # Call Gemini
        response = self.client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt,
            config={"temperature": 1.0, "max_output_tokens": 4096},
        )

        chronicle_text = response.text
        event_count = len(data["events"])
        snapshot_count = self.db.get_snapshot_count(session_id)

        # Cache result
        self.db.upsert_cached_chronicle(
            session_id=session_id,
            chronicle_text=chronicle_text,
            event_count=event_count,
            snapshot_count=snapshot_count,
        )

        return {
            "chronicle": chronicle_text,
            "cached": False,
            "event_count": event_count,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _get_cached_if_valid(self, session_id: str) -> dict[str, Any] | None:
        """Get cached chronicle if still valid (not stale)."""
        cached = self.db.get_cached_chronicle(session_id)
        if not cached:
            return None

        current_events = self.db.get_event_count(session_id)
        current_snapshots = self.db.get_snapshot_count(session_id)

        event_delta = current_events - cached["event_count"]
        snapshot_delta = current_snapshots - cached["snapshot_count"]

        if event_delta >= self.STALE_EVENT_THRESHOLD:
            return None
        if snapshot_delta >= self.STALE_SNAPSHOT_THRESHOLD:
            return None

        return {
            "chronicle": cached["chronicle_text"],
            "cached": True,
            "event_count": cached["event_count"],
            "generated_at": cached["generated_at"],
        }

    def _gather_session_data(
        self, session_id: str, max_events: int | None = None
    ) -> dict[str, Any]:
        """Gather all data needed for chronicle/recap generation."""
        session = self.db.get_session_by_id(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        if max_events is None:
            events = self.db.get_all_events(session_id=session_id)
        else:
            events = self.db.get_recent_events(session_id=session_id, limit=max_events)

        briefing_json = self.db.get_latest_session_briefing_json(session_id=session_id)
        briefing = json.loads(briefing_json) if briefing_json else {}

        stats = self.db.get_session_snapshot_stats(session_id)

        return {
            "session": dict(session),
            "events": events,
            "briefing": briefing,
            "first_date": stats.get("first_game_date"),
            "last_date": stats.get("last_game_date"),
        }

    def _build_chronicler_prompt(self, data: dict[str, Any]) -> str:
        """Build the full chronicler prompt with ethics-based voice."""
        briefing = data["briefing"]
        identity = briefing.get("identity", {})

        empire_name = identity.get("empire_name", "Unknown Empire")
        ethics = ", ".join(identity.get("ethics", []))
        authority = identity.get("authority", "unknown")
        civics = ", ".join(identity.get("civics", []))

        voice = self._get_voice_for_ethics(identity, ethics)
        events_text = self._format_events(data["events"])
        state_text = self._summarize_state(briefing)

        return f"""You are the Royal Chronicler of {empire_name}. Your task is to write the official historical chronicle of this empire.

=== EMPIRE IDENTITY ===
Name: {empire_name}
Ethics: {ethics}
Authority: {authority}
Civics: {civics}

=== CHRONICLER'S VOICE ===
{voice}

You are NOT an advisor. You do NOT give recommendations or strategic advice. You are a HISTORIAN writing for future generations.

=== STYLE GUIDE ===
- Write as an epic galactic chronicle: dramatic, cinematic, larger-than-life
- Each chapter should read like the opening crawl of a space opera
- Use vivid, evocative language: "The stars themselves trembled" not "There was a big war"
- Employ narrative techniques: foreshadowing, dramatic irony, rising tension
- Name specific dates when dramatic (e.g., "On the first day of 2350, the sky burned")
- When leader names are missing or show as placeholders, use titles instead
- DO NOT fabricate events - only reference what appears in the event log
- DO NOT give advice or recommendations - you are a chronicler, not an advisor

{state_text}

=== COMPLETE EVENT HISTORY ===
(From {data['first_date']} to {data['last_date']})
{events_text}

=== YOUR TASK ===

Write a chronicle divided into 4-6 chapters. For each chapter:
1. **Chapter Title**: A dramatic, thematic name
2. **Date Range**: The years this chapter covers (use actual dates from events)
3. **Narrative**: 2-4 paragraphs of dramatic prose

End with "The Story Continues..." about the current situation.
"""

    def _get_voice_for_ethics(self, identity: dict, ethics: str) -> str:
        """Determine narrative voice based on ethics/identity."""
        if identity.get("is_machine"):
            return (
                "Write with cold, logical precision. No emotion, only analysis of "
                "historical patterns. Use technical terminology. Frame the chronicle "
                "as a data log for future processing units."
            )
        elif identity.get("is_hive_mind"):
            return (
                "Write as the collective memory. Use 'we' and 'the swarm'. "
                "Frame history as the growth of the whole."
            )
        elif "fanatic_authoritarian" in ethics or "authoritarian" in ethics:
            return (
                "Write with imperial grandeur. Emphasize the glory of the state, "
                "the wisdom of the throne, and the order that hierarchy brings."
            )
        elif "fanatic_egalitarian" in ethics or "egalitarian" in ethics:
            return (
                "Write celebrating the triumph of the people. "
                "Emphasize collective achievement and democratic ideals."
            )
        elif "fanatic_militarist" in ethics or "militarist" in ethics:
            return "Write with martial pride. Emphasize battles, conquests, and military honor."
        elif "fanatic_spiritualist" in ethics or "spiritualist" in ethics:
            return "Write with religious reverence. Frame history as divine providence."
        elif "fanatic_pacifist" in ethics or "pacifist" in ethics:
            return (
                "Write valuing peace and diplomacy. Frame conflicts as tragedies, "
                "peace as triumph."
            )
        elif "fanatic_materialist" in ethics or "materialist" in ethics:
            return (
                "Write celebrating scientific progress. Frame history as the march "
                "of knowledge and reason."
            )
        else:
            return "Write with epic gravitas befitting a galactic chronicle."

    def _build_recap_prompt(self, data: dict[str, Any]) -> str:
        """Build a shorter recap prompt for recent events."""
        briefing = data["briefing"]
        identity = briefing.get("identity", {})
        empire_name = identity.get("empire_name", "Unknown Empire")

        events_text = self._format_events(data["events"])
        state_text = self._summarize_state(briefing)

        return f"""You are the Royal Chronicler of {empire_name}. Write a dramatic "Previously on..." recap.

{state_text}

=== RECENT EVENTS ===
{events_text}

Write a 2-3 paragraph dramatic recap of recent events, ending with the current stakes.
Do NOT give advice. Write as a historian, not an advisor.
"""

    def _format_events(self, events: list[dict]) -> str:
        """Format events for the LLM prompt."""
        # Deduplicate events
        seen: set[tuple] = set()
        deduped = []
        for e in events:
            key = (e.get("game_date"), e.get("event_type"), e.get("summary"))
            if key not in seen:
                seen.add(key)
                deduped.append(e)

        # Group by year
        by_year: dict[str, list[dict]] = {}
        for e in deduped:
            year = e.get("game_date", "")[:4] or "Unknown"
            if year not in by_year:
                by_year[year] = []
            by_year[year].append(e)

        lines = []
        for year in sorted(by_year.keys()):
            year_events = by_year[year]
            lines.append(f"\n=== {year} ===")

            if len(year_events) > 15:
                notable = [
                    e for e in year_events if e.get("event_type") in NOTABLE_EVENT_TYPES
                ]
                for e in notable:
                    lines.append(
                        f"  * {e.get('summary', e.get('event_type', 'Unknown event'))}"
                    )
                lines.append(f"  (+ {len(year_events) - len(notable)} other events)")
            else:
                for e in year_events:
                    lines.append(
                        f"  * {e.get('summary', e.get('event_type', 'Unknown event'))}"
                    )

        return "\n".join(lines)

    def _summarize_state(self, briefing: dict) -> str:
        """Summarize current empire state for context."""
        identity = briefing.get("identity", {})
        situation = briefing.get("situation", {})
        military = briefing.get("military", {})
        territory = briefing.get("territory", {})
        endgame = briefing.get("endgame", {})

        lines = [
            "=== CURRENT STATE ===",
            f"Empire: {identity.get('empire_name', 'Unknown')}",
            f"Year: {situation.get('year', '?')}",
            f"Military Power: {military.get('military_power', 0):,.0f}",
            f"Colonies: {territory.get('colonies', {}).get('total_count', 0)}",
        ]

        crisis = endgame.get("crisis", {})
        if crisis.get("crisis_active"):
            lines.append(
                f"CRISIS: {crisis.get('crisis_type', 'Unknown').title()} "
                f"({crisis.get('crisis_systems_count', 0)} systems)"
            )

        fe = situation.get("fallen_empires", {})
        if fe.get("awakened_count", 0) > 0:
            lines.append(f"Awakened Empires: {fe.get('awakened_count', 0)}")

        if fe.get("war_in_heaven"):
            lines.append("WAR IN HEAVEN: Active")

        return "\n".join(lines)
