"""
Chronicle Generation Engine
============================

LLM-powered narrative generation for empire storytelling.
Produces dramatic chronicles from game events.

Supports incremental chapters - early chapters are permanent while new
chapters are added as the game progresses.

See docs/CHRONICLE_IMPLEMENTATION.md for original specification.
See docs/CHRONICLE_INCREMENTAL.md for incremental chapter design.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Literal

from google import genai
from pydantic import BaseModel, Field

from backend.core.advisor_providers import (
    ADVISOR_PROVIDER_GEMINI,
    AdvisorGenerationResult,
    AdvisorGenerator,
    AdvisorProviderConfig,
    AdvisorProviderError,
    create_advisor_generator,
)
from backend.core.chronicle_store import (
    ChronicleConflict,
    cached_chronicle_response,
    chapter_identity,
    chronicle_revision,
    compact_chronicle_context,
    events_between_dates,
    game_date_key,
    load_chapters_data,
    source_events,
)
from backend.core.database import GameDatabase
from backend.core.json_utils import json_dumps
from backend.core.language import build_language_policy, localized_text, normalize_language
from backend.core.model_briefing import build_model_briefing
from backend.core.model_routing import display_model_name, normalize_model_routing_mode
from backend.core.structured_output import (
    validate_structured_response as _validate_structured_response,
)
from stellaris_companion.game_knowledge import build_game_knowledge_prompt

logger = logging.getLogger(__name__)


# ============================================
# Pydantic models for structured LLM output
# ============================================


class NarrativeSection(BaseModel):
    """A single narrative block within a chapter."""

    type: Literal["prose", "quote", "declaration"]
    text: str
    attribution: str = ""


class ChapterOutput(BaseModel):
    """Structured output schema for chapter generation."""

    title: str = Field(
        description="A dramatic, thematic name for this chapter/era (e.g., 'The Cradle's Awakening', 'The Great Expansion')"
    )
    epigraph: str = Field(
        description="A short opening flavor line — a proverb, decree, or ominous statement that sets the chapter's tone (max 20 words)"
    )
    sections: list[NarrativeSection] = Field(
        description="Narrative blocks sized to the supplied evidence: prose, optional literary quotes, or occasional declarations"
    )
    summary: str = Field(
        description="2-3 sentences summarizing the key events for context in future chapters."
    )


class CurrentEraOutput(BaseModel):
    """Structured output schema for current era generation."""

    sections: list[NarrativeSection]


def _sections_to_text(sections: list[dict], epigraph: str = "") -> str:
    """Convert structured sections to a plain text narrative string."""
    parts: list[str] = []
    if epigraph:
        parts.append(f'"{epigraph}"')
        parts.append("")
    for section in sections:
        stype = section.get("type", "prose")
        text = section.get("text", "")
        if stype == "quote":
            attribution = section.get("attribution", "")
            parts.append(f'> "{text}"')
            if attribution:
                parts.append(f"> \u2014 {attribution}")
            parts.append("")
        elif stype == "declaration":
            parts.append(f"=== {text} ===")
            parts.append("")
        else:
            parts.append(text)
            parts.append("")
    return "\n".join(parts).strip()


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
CHAPTER_TIME_THRESHOLD = 30

# Chapter 1 should arrive quickly so players see something early.
# We still guard on "enough events" so the first chapter has substance.
FIRST_CHAPTER_TIME_THRESHOLD = 5
FIRST_CHAPTER_MIN_EVENTS_TIME = 8

# Milestone-based early Chapter 1 triggers (no need to wait 30 years).
# These are intentionally early/midgame-relevant events that tend to occur soon.
FIRST_CHAPTER_MILESTONE_EVENTS = {
    "first_contact",
    "war_started",
    "federation_joined",
    "colony_count_change",
    "ruler_changed",
    "subject_gained",
    "became_subject",
    "tradition_tree_completed",
    "lgate_opened",
}
FIRST_CHAPTER_MIN_YEARS_MILESTONE = 2
FIRST_CHAPTER_MIN_EVENTS_MILESTONE = 4

# Minimum years after era-ending event before finalizing
MIN_YEARS_AFTER_EVENT = 2

# Maximum chapters to finalize per request (prevent timeout)
MAX_CHAPTERS_PER_REQUEST = 2

# Hard caps to keep Gemini requests reasonably sized.
# These limits are deliberately conservative to avoid saturating the user's network.
MAX_EVENTS_PER_CHAPTER_PROMPT = 250
MAX_EVENTS_CURRENT_ERA_PROMPT = 200

NOTABLE_EVENT_TYPES = {
    # War and diplomacy
    "war_started",
    "war_ended",
    "federation_joined",
    "federation_left",
    "alliance_formed",
    "alliance_ended",
    # Crisis and endgame
    "crisis_started",
    "crisis_defeated",
    "fallen_empire_awakened",
    "war_in_heaven_started",
    # Chronicle enhancement events (CHR-001 to CHR-018)
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
    # Subjects / Vassals
    "subject_gained",
    "subject_lost",
    "became_subject",
    "freed_from_subject",
    # Geography
    "new_border_contact",
    # Milestones
    "colony_count_change",
    "military_power_change",
}

# A narrower subset of notable events should force immediate current-era refreshes.
# Colony and military power changes still matter for prompt selection and chapter
# context, but they are common enough that they should not rewrite the teaser
# on their own in balanced mode.
CURRENT_ERA_IMMEDIATE_REFRESH_EVENT_TYPES = NOTABLE_EVENT_TYPES - {
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

# Auto chapter-only scheduling (used by renderer background refresh loops).
AUTO_CHAPTER_IDLE_INTERVAL_SECONDS = 5 * 60
AUTO_CHAPTER_PENDING_INTERVAL_SECONDS = 30
# Refresh current-era teaser only after meaningful event growth.
CURRENT_ERA_REGEN_MIN_NEW_EVENTS = 3
ENHANCED_CURRENT_ERA_REGEN_MIN_NEW_EVENTS = 1
CHRONICLE_REFRESH_MODE_BALANCED = "balanced"
CHRONICLE_REFRESH_MODE_ENHANCED = "enhanced"
CHRONICLE_REFRESH_MODE_MANUAL = "manual"
DEFAULT_CHRONICLE_REFRESH_MODE = CHRONICLE_REFRESH_MODE_BALANCED
CHRONICLE_REFRESH_MODES = {
    CHRONICLE_REFRESH_MODE_BALANCED,
    CHRONICLE_REFRESH_MODE_ENHANCED,
    CHRONICLE_REFRESH_MODE_MANUAL,
}

CHRONICLE_EVIDENCE_RULES = """=== EVIDENCE RULES ===
- Treat each event and campaign-context line as an independent recorded fact.
- Dramatize tone, not campaign facts: do not add concrete motives, actions, causes,
  outcomes, relationships, or capabilities that are absent from the record.
- Events sharing a date establish coexistence, not cause and effect.
- Preserve the meaning of recorded metrics; do not turn counts into strength or net
  income into stockpiles, costs, or spending.
- If the record does not explain why something happened, leave the reason unknown.
- Quotes and declarations are literary framing, not new evidence, and must not introduce
  additional campaign facts.
"""


def normalize_chronicle_refresh_mode(value: Any) -> str:
    """Normalize refresh mode from UI settings / API input."""
    if not isinstance(value, str):
        return DEFAULT_CHRONICLE_REFRESH_MODE
    normalized = value.strip().lower()
    if normalized in CHRONICLE_REFRESH_MODES:
        return normalized
    return DEFAULT_CHRONICLE_REFRESH_MODE


def get_current_era_regen_min_new_events(refresh_mode: Any) -> int:
    """Return the routine-event threshold for the selected refresh mode."""
    normalized = normalize_chronicle_refresh_mode(refresh_mode)
    if normalized == CHRONICLE_REFRESH_MODE_ENHANCED:
        return ENHANCED_CURRENT_ERA_REGEN_MIN_NEW_EVENTS
    return CURRENT_ERA_REGEN_MIN_NEW_EVENTS


def _chapter_narrative_scope(events: list[dict]) -> str:
    """Scale chapter length to the amount of consequential evidence available."""
    notable_facts = {
        (event.get("event_type"), event.get("summary"))
        for event in events
        if event.get("event_type") in NOTABLE_EVENT_TYPES
    }
    minor_notable_types = {
        "first_contact",
        "new_border_contact",
        "colony_count_change",
        "military_power_change",
    }
    has_major_turning_point = any(
        event.get("event_type") in NOTABLE_EVENT_TYPES
        and event.get("event_type") not in minor_notable_types
        for event in events
    )

    if has_major_turning_point or len(notable_facts) >= 3:
        return (
            "Use 3-5 sections and aim for 400-650 words. Give the recorded turning "
            "points room to breathe, but do not pad the chapter beyond its evidence."
        )
    return (
        "Use 2-3 prose sections and aim for 200-350 words. This is a lightly evidenced "
        "era, so keep it evocative and concise rather than filling gaps with story."
    )


def parse_year(date_str: str | None) -> int | None:
    """Parse year from Stellaris date string (e.g., '2250.03.15')."""
    if not date_str or not isinstance(date_str, str):
        return None
    try:
        return int(date_str.split(".")[0])
    except (ValueError, IndexError):
        return None


def _parse_iso_datetime(value: Any) -> datetime | None:
    """Parse ISO datetime string into timezone-aware datetime."""
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _chronicle_game_knowledge(briefing: dict[str, Any]) -> str:
    """Resolve the shared mechanics context from a model-facing briefing."""
    meta = briefing.get("meta") if isinstance(briefing.get("meta"), dict) else {}
    model_context = (
        briefing.get("model_context") if isinstance(briefing.get("model_context"), dict) else {}
    )
    version = str(meta.get("version") or model_context.get("game_version") or "unknown")
    return build_game_knowledge_prompt(
        version,
        purpose="chronicle",
        topics=json_dumps(briefing),
    )


class ChronicleGenerator:
    """Generate LLM-powered chronicles for empire sessions.

    Supports incremental chapters keyed by save_id for cross-session continuity.
    """

    # Staleness thresholds for legacy blob-based cache
    STALE_EVENT_THRESHOLD = 10
    STALE_SNAPSHOT_THRESHOLD = 5

    def __init__(
        self,
        db: GameDatabase,
        api_key: str | None = None,
        *,
        model_routing_mode: str | None = None,
        provider_config: AdvisorProviderConfig | None = None,
        provider_generator: AdvisorGenerator | None = None,
    ):
        self.db = db
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY")
        self.provider_config = (
            provider_config
            or getattr(provider_generator, "config", None)
            or AdvisorProviderConfig.from_environment(google_api_key=self.api_key)
        )
        self._client: genai.Client | None = None
        self._provider_generator = provider_generator
        self.model_routing_mode = normalize_model_routing_mode(
            model_routing_mode or os.environ.get("STELLARIS_MODEL_ROUTING_MODE")
        )
        self._model_route_events: list[dict[str, Any]] = []

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            if (
                self.provider_config.provider != ADVISOR_PROVIDER_GEMINI
                or not self.provider_config.api_key
            ):
                raise AdvisorProviderError(
                    f"{self.provider_config.display_name} is not configured for Chronicle",
                    code="CHRONICLE_PROVIDER_NOT_CONFIGURED",
                    status_code=400,
                )
            self._client = genai.Client(api_key=self.provider_config.api_key)
        return self._client

    @property
    def provider_generator(self) -> AdvisorGenerator:
        if self._provider_generator is None:
            if not self.provider_config.is_configured:
                raise AdvisorProviderError(
                    f"{self.provider_config.display_name} is not configured for Chronicle",
                    code="CHRONICLE_PROVIDER_NOT_CONFIGURED",
                    status_code=400,
                )
            gemini_client = (
                self.client if self.provider_config.provider == ADVISOR_PROVIDER_GEMINI else None
            )
            self._provider_generator = create_advisor_generator(
                config=self.provider_config,
                gemini_client=gemini_client,
            )
        if self._provider_generator is None:
            raise AdvisorProviderError(
                f"{self.provider_config.display_name} is not configured for Chronicle",
                code="CHRONICLE_PROVIDER_NOT_CONFIGURED",
                status_code=400,
            )
        return self._provider_generator

    def close(self) -> None:
        """Release provider connections created for this generation request."""
        close = getattr(self._provider_generator, "close", None)
        if callable(close):
            close()
        self._provider_generator = None
        self._client = None

    def generate_chronicle(
        self,
        session_id: str,
        *,
        force_refresh: bool = False,
        chapter_only: bool = False,
        refresh_mode: str = DEFAULT_CHRONICLE_REFRESH_MODE,
        model_routing_mode: str | None = None,
        language: str | None = None,
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
            # Fallback to session-based chronicle (legacy), with the same manual policy.
            if (
                normalize_chronicle_refresh_mode(refresh_mode) == CHRONICLE_REFRESH_MODE_MANUAL
                and not force_refresh
            ):
                return cached_chronicle_response(
                    self.db.get_cached_chronicle(session_id, language=normalize_language(language))
                )
            return self._generate_legacy_chronicle(session_id, force_refresh=force_refresh)

        self._model_route_events = []
        if model_routing_mode:
            self.model_routing_mode = normalize_model_routing_mode(model_routing_mode)
        output_language = normalize_language(language)
        refresh_mode = normalize_chronicle_refresh_mode(refresh_mode)

        # Load existing chapters data
        cached = self.db.get_chronicle_by_save_id(save_id, language=output_language)
        chapters_data = self._load_chapters_data(cached)
        expected_revision = chronicle_revision(chapters_data)
        if refresh_mode == CHRONICLE_REFRESH_MODE_MANUAL and not force_refresh:
            return cached_chronicle_response(cached)
        chapters_data["language"] = output_language

        # Load persistent custom instructions for this save
        custom_instructions = self.db.get_chronicle_custom_instructions(save_id)

        # Get current state
        snapshot_range = self.db.get_snapshot_range_for_save(save_id)
        if not snapshot_range.get("snapshot_count"):
            return self._empty_chronicle_response(language=output_language)

        current_date = snapshot_range.get("last_game_date")
        current_snapshot_id = snapshot_range.get("last_snapshot_id")
        source_date = game_date_key(current_date)
        archive_dates = [
            game_date_key(ch.get("end_date")) for ch in chapters_data.get("chapters", [])
        ]
        archive_dates.append(game_date_key(chapters_data.get("coverage_date")))
        coverage = max((date for date in archive_dates if date is not None), default=None)
        if cached and source_date is not None and coverage is not None and source_date < coverage:
            response = cached_chronicle_response(cached)
            response["message"] = (
                "This save predates the Chronicle's recorded coverage. The existing archive has been preserved."
            )
            return response

        # Freeze the dated source before any provider call. Later ingestion belongs
        # to the next refresh, even if it happens while the model is writing.
        briefing = self.db.get_historical_chronicle_briefing(save_id, current_snapshot_id)
        briefing = build_model_briefing(briefing) if isinstance(briefing, dict) else {}

        # Check if we need to finalize any chapters
        chapters_finalized = 0
        pending_chapters = 0
        deferred_chapter_only = False

        if chapter_only and not force_refresh:
            deferred_chapter_only, pending_chapters = self._chapter_only_cooldown_active(
                chapters_data=chapters_data
            )
            if deferred_chapter_only:
                logger.debug(
                    "Chronicle chapter-only run deferred by cooldown (save_id=%s pending=%s)",
                    save_id,
                    pending_chapters,
                )

        if not deferred_chapter_only:
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
                finalized = self._finalize_chapter(
                    save_id=save_id,
                    chapters_data=chapters_data,
                    briefing=briefing,
                    trigger=trigger,
                    snapshot_range=snapshot_range,
                    custom_instructions=custom_instructions,
                    language=output_language,
                )
                if not finalized:
                    break
                chapters_finalized += 1

            # Count remaining pending chapters
            pending_chapters = self._count_pending_chapters(
                save_id=save_id,
                chapters_data=chapters_data,
                current_date=current_date,
                current_snapshot_id=current_snapshot_id,
            )

            self._set_next_chapter_only_run(
                chapters_data=chapters_data,
                pending_chapters=pending_chapters,
            )

        # Generate (or reuse cached) current era narrative unless this request is
        # finalizing chapters only for background catch-up.
        #
        # Design intent:
        # - Current era is a teaser between chapters, not a live minute-by-minute feed.
        # - Generate at most once per era window (or on explicit force refresh).
        # - Do not spend teaser calls while chapters are still pending.
        era_start_date, era_start_snapshot_id = self._get_current_era_start(
            save_id=save_id,
            chapters_data=chapters_data,
            snapshot_range=snapshot_range,
        )

        used_cached_current_era = False
        current_era: dict[str, Any] | None = None
        current_era_cache = chapters_data.get("current_era_cache")

        cached_current_era = (
            current_era_cache.get("current_era")
            if isinstance(current_era_cache, dict)
            and isinstance(current_era_cache.get("current_era"), dict)
            else None
        )
        cache_matches_era = bool(
            isinstance(current_era_cache, dict)
            and current_era_cache.get("start_snapshot_id") == era_start_snapshot_id
            and cached_current_era is not None
        )

        regenerate_for_event_growth = False

        if cached_current_era and cached_current_era.get("manual_edit_locked"):
            # External/player prose remains protected even after a chapter boundary moves.
            used_cached_current_era = True
            current_era = cached_current_era
        elif chapter_only:
            if isinstance(current_era_cache, dict) and isinstance(
                current_era_cache.get("current_era"), dict
            ):
                # Keep existing current-era narrative text without invoking Gemini.
                # If finalized chapters moved the era boundary, the next visible
                # full refresh will detect the cache mismatch and regenerate.
                used_cached_current_era = True
                current_era = current_era_cache["current_era"]
        elif pending_chapters > 0:
            # Chapter generation is always higher priority than teaser freshness.
            # While there are still chapters to finalize, avoid spending extra
            # calls on current-era rewrites.
            if cache_matches_era:
                used_cached_current_era = True
                current_era = cached_current_era
            else:
                # Era boundary moved and no matching teaser exists yet.
                # Keep teaser empty until chapter queue clears.
                current_era = None
                if current_era_cache:
                    chapters_data.pop("current_era_cache", None)
        else:
            if cache_matches_era and not force_refresh:
                regenerate_for_event_growth = self._should_regenerate_current_era_for_event_growth(
                    save_id=save_id,
                    era_start_snapshot_id=era_start_snapshot_id,
                    cached_current_era=cached_current_era,
                    refresh_mode=refresh_mode,
                    current_snapshot_id=current_snapshot_id,
                    current_date=current_date,
                )
                if not regenerate_for_event_growth:
                    used_cached_current_era = True
                    current_era = cached_current_era
                    logger.debug(
                        "Chronicle current era cache hit (save_id=%s era_start_snapshot_id=%s)",
                        save_id,
                        era_start_snapshot_id,
                    )
                else:
                    logger.debug(
                        "Chronicle current era refresh due to event growth "
                        "(save_id=%s era_start_snapshot_id=%s)",
                        save_id,
                        era_start_snapshot_id,
                    )

            if force_refresh or not cache_matches_era or regenerate_for_event_growth:
                if current_era_cache and not used_cached_current_era:
                    chapters_data.pop("current_era_cache", None)

                current_era = self._generate_current_era(
                    save_id=save_id,
                    chapters_data=chapters_data,
                    briefing=briefing,
                    current_date=current_date,
                    current_snapshot_id=current_snapshot_id,
                    custom_instructions=custom_instructions,
                    language=output_language,
                )

                if current_era and current_snapshot_id is not None:
                    chapters_data["current_era_cache"] = {
                        "start_date": era_start_date,
                        "start_snapshot_id": era_start_snapshot_id,
                        "last_snapshot_id": current_snapshot_id,
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                        "language": output_language,
                        "coverage_date": current_date,
                        "current_era": current_era,
                    }
                    logger.debug(
                        "Chronicle current era generated (save_id=%s era_start_snapshot_id=%s)",
                        save_id,
                        era_start_snapshot_id,
                    )

        # Coverage advances only when prose was written from a frozen source, never
        # because a cache was viewed or background scheduling metadata was updated.
        if chapters_finalized or (current_era and not used_cached_current_era):
            dates = [ch.get("coverage_date") for ch in chapters_data.get("chapters", [])]
            if current_era:
                dates.append(current_era.get("coverage_date"))
            known_dates = [date for date in dates if isinstance(date, str) and date]
            chapters_data["coverage_date"] = max(known_dates, default=None)
            chapters_data["content_generated_at"] = datetime.now(timezone.utc).isoformat()
        elif cached:
            chapters_data.setdefault("content_generated_at", cached.get("generated_at"))

        all_events = self.db.get_events_in_snapshot_range(
            save_id=save_id,
            to_snapshot_id=current_snapshot_id,
        )
        event_count = len(all_events)
        content_changed = bool(chapters_finalized or (current_era and not used_cached_current_era))
        removed_era = bool(current_era_cache and "current_era_cache" not in chapters_data)
        if (
            cached
            and not content_changed
            and not removed_era
            and (not chapter_only or deferred_chapter_only)
        ):
            # Viewing existing prose keeps its revision, coverage and writing date.
            saved = cached
        else:
            saved = self.db.commit_chronicle(
                save_id=save_id,
                session_id=session_id,
                language=output_language,
                expected_revision=expected_revision,
                chapters_data=chapters_data,
                event_count=event_count,
                snapshot_count=snapshot_range.get("snapshot_count", 0),
            )
        response = cached_chronicle_response(saved)
        response.update(
            cached=bool(cached) and not content_changed and not removed_era,
            pending_chapters=pending_chapters,
            message=(
                f"{pending_chapters} more chapters pending. Refresh to continue."
                if pending_chapters > 0
                else None
            ),
            model_routing=self._model_routing_response(),
        )
        return response

    def _should_regenerate_current_era_for_event_growth(
        self,
        *,
        save_id: str,
        era_start_snapshot_id: int | None,
        cached_current_era: dict[str, Any] | None,
        refresh_mode: str = DEFAULT_CHRONICLE_REFRESH_MODE,
        current_snapshot_id: int | None = None,
        current_date: str | None = None,
    ) -> bool:
        """Refresh current era when enough new events accumulated for this era."""
        if era_start_snapshot_id is None:
            return False
        if not isinstance(cached_current_era, dict):
            return True

        cached_events_covered = cached_current_era.get("events_covered")
        if not isinstance(cached_events_covered, int) or cached_events_covered < 0:
            return True

        era_events = self.db.get_events_in_snapshot_range(
            save_id=save_id,
            from_snapshot_id=era_start_snapshot_id,
            to_snapshot_id=current_snapshot_id,
        )
        if current_date is not None:
            era_events = events_between_dates(
                era_events, cached_current_era.get("start_date"), current_date
            )
        current_era_event_count = len(era_events)
        new_events = max(0, current_era_event_count - cached_events_covered)
        if new_events <= 0:
            return False

        recent_events = era_events[-new_events:]
        if any(
            event.get("event_type") in CURRENT_ERA_IMMEDIATE_REFRESH_EVENT_TYPES
            for event in recent_events
        ):
            return True

        return new_events >= get_current_era_regen_min_new_events(refresh_mode)

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

        notable: list[dict] = [e for e in deduped if e.get("event_type") in NOTABLE_EVENT_TYPES]

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
        regeneration_instructions: str | None = None,
        expected_revision: str | None = None,
        model_routing_mode: str | None = None,
        language: str | None = None,
    ) -> dict[str, Any]:
        """Regenerate a specific finalized chapter.

        Returns error if confirm=False (requires explicit confirmation).
        Marks downstream chapters as context_stale.
        """
        if not confirm:
            return {"error": "Must confirm regeneration", "confirm_required": True}
        self._model_route_events = []
        if model_routing_mode:
            self.model_routing_mode = normalize_model_routing_mode(model_routing_mode)
        output_language = normalize_language(language)

        save_id = self.db.get_save_id_for_session(session_id)
        if not save_id:
            raise ValueError(f"No save_id for session: {session_id}")

        cached = self.db.get_chronicle_by_save_id(save_id, language=output_language)
        if not cached:
            raise ValueError(f"No chronicle found for save: {save_id}")

        chapters_data = self._load_chapters_data(cached)
        base_revision = chronicle_revision(chapters_data)
        if expected_revision is not None and expected_revision != base_revision:
            raise ChronicleConflict(
                "The Chronicle changed. Read the newer version before regenerating."
            )
        chapters = chapters_data.get("chapters", [])

        if chapter_number < 1 or chapter_number > len(chapters):
            raise ValueError(f"Invalid chapter number: {chapter_number}")

        chapter = chapters[chapter_number - 1]
        if not chapter.get("is_finalized"):
            raise ValueError(f"Chapter {chapter_number} is not finalized")

        # Load persistent custom instructions for this save
        custom_instructions = self.db.get_chronicle_custom_instructions(save_id)

        source = chapter.get("source_bundle")
        if isinstance(source, dict) and isinstance(source.get("events"), list):
            briefing = source.get("briefing") or {}
            events = source["events"]
        else:
            # Legacy archives do not have full historical snapshots. Use only
            # verified event records and compact context at the recorded boundary.
            historical = self.db.get_historical_chronicle_briefing(
                save_id, chapter.get("end_snapshot_id")
            )
            briefing = historical if isinstance(historical, dict) else {}
            events = self.db.get_events_in_snapshot_range(
                save_id=save_id,
                from_snapshot_id=chapter.get("start_snapshot_id"),
                to_snapshot_id=chapter.get("end_snapshot_id"),
            )
            start, end = chapter.get("start_date"), chapter.get("end_date")
            if not isinstance(start, str) or not isinstance(end, str) or not parse_year(end):
                raise ValueError("This legacy chapter has no verified date range to regenerate")
            events = events_between_dates(events, start, end)
            selected, partial = self._select_events_for_prompt(
                events, max_events=MAX_EVENTS_PER_CHAPTER_PROMPT
            )
            source = {
                "version": 1,
                "start_snapshot_id": chapter.get("start_snapshot_id"),
                "end_snapshot_id": chapter.get("end_snapshot_id"),
                "coverage_date": chapter.get("end_date"),
                "briefing": compact_chronicle_context(briefing),
                "events": source_events(selected),
                "source_event_count": len(events),
                "selected_event_count": len(selected),
                "partial_coverage": partial,
                "historical_context_limited": bool(briefing.get("historical_context_limited")),
            }
            events = source["events"]

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
            custom_instructions=custom_instructions,
            regeneration_instructions=regeneration_instructions,
            language=output_language,
        )

        # Update the chapter
        chapter["title"] = new_content["title"]
        chapter["epigraph"] = new_content.get("epigraph", "")
        chapter["sections"] = new_content.get("sections")
        chapter["narrative"] = new_content["narrative"]
        chapter["summary"] = new_content["summary"]
        chapter["provider"] = new_content.get("provider")
        chapter["model"] = new_content.get("model")
        chapter["generated_at"] = datetime.now(timezone.utc).isoformat()
        chapter["context_stale"] = False
        chapter["manual_edit_locked"] = False  # This explicitly requested replacement is undoable.
        chapter["source"] = "generated"
        chapter["source_bundle"] = source
        chapter["coverage_date"] = source.get("coverage_date")
        chapter["partial_coverage"] = source.get("partial_coverage", False)
        chapter["historical_context_limited"] = source.get("historical_context_limited", False)
        chapters_data["content_generated_at"] = chapter["generated_at"]

        # Mark downstream chapters as stale
        for i in range(chapter_number, len(chapters)):
            chapters[i]["context_stale"] = True

        saved = self.db.commit_chronicle(
            save_id=save_id,
            session_id=session_id,
            language=output_language,
            expected_revision=base_revision,
            chapters_data=chapters_data,
            event_count=int(cached.get("event_count") or 0),
            snapshot_count=int(cached.get("snapshot_count") or 0),
        )
        response = cached_chronicle_response(saved)
        rendered = next(ch for ch in response["chapters"] if ch["number"] == chapter_number)
        return {
            **response,
            "chapter": rendered,
            "regenerated": True,
            "stale_chapters": list(range(chapter_number + 1, len(chapters) + 1)),
            "model_routing": self._model_routing_response(),
        }

    def generate_recap(
        self,
        session_id: str,
        *,
        style: str = "summary",
        max_events: int = 30,
        model_routing_mode: str | None = None,
        language: str | None = None,
    ) -> dict[str, Any]:
        """Generate a recap for the session.

        Args:
            style: "summary" (deterministic) or "dramatic" (LLM-powered)
        """
        self._model_route_events = []
        if model_routing_mode:
            self.model_routing_mode = normalize_model_routing_mode(model_routing_mode)
        output_language = normalize_language(language)

        if style == "summary":
            from backend.core.reporting import build_session_report_text

            recap = build_session_report_text(db=self.db, session_id=session_id)
            return {"recap": recap, "style": "summary"}

        # Dramatic LLM-powered recap
        data = self._gather_session_data(session_id, max_events=max_events)

        if not data["events"]:
            return {
                "recap": localized_text("no_events_recap", output_language),
                "style": "dramatic",
                "events_summarized": 0,
            }

        prompt = self._build_recap_prompt(data, language=output_language)

        response = self._generate_content_with_routing(
            contents=prompt,
            config={"temperature": 1.0, "max_output_tokens": 2048},
            purpose_label="Chronicle recap",
            game_knowledge_context=_chronicle_game_knowledge(data["briefing"]),
        )

        return {
            "recap": response.text,
            "style": "dramatic",
            "events_summarized": len(data["events"]),
            "provider": response.provider,
            "model": response.model,
            "model_routing": self._model_routing_response(),
        }

    def _generate_content_with_routing(
        self,
        *,
        contents: str,
        config: dict[str, Any],
        purpose_label: str,
        game_knowledge_context: str | None = None,
    ) -> AdvisorGenerationResult:
        """Generate Chronicle content through the selected model provider."""
        response_schema = config.get("response_schema")
        system_prompt = (
            "Follow the Chronicle instructions precisely. Write as an in-universe "
            "historian, never as a strategic advisor. Treat the supplied events and "
            "campaign context as evidence: dramatize the voice, but do not invent "
            "motives, actions, causes, outcomes, or availability. Never turn events "
            "that share a date into a causal claim or use literary framing to add facts."
        )
        if game_knowledge_context:
            system_prompt = f"{system_prompt}\n\n{game_knowledge_context}"
        result = self.provider_generator.generate(
            system_prompt=system_prompt,
            user_prompt=contents,
            model_routing_mode=self.model_routing_mode,
            temperature=float(config.get("temperature", 1.0)),
            max_output_tokens=int(config.get("max_output_tokens", 4096)),
            purpose="chronicle",
            response_schema=(
                response_schema
                if isinstance(response_schema, type) and issubclass(response_schema, BaseModel)
                else None
            ),
            schema_name=purpose_label,
            allow_schema_fallback=bool(config.get("allow_schema_fallback", True)),
        )
        self._record_model_generation(result)
        return result

    def _generate_structured_content(
        self,
        *,
        contents: str,
        response_schema: type[BaseModel],
        temperature: float,
        max_output_tokens: int,
        purpose_label: str,
        game_knowledge_context: str | None = None,
    ) -> tuple[BaseModel, AdvisorGenerationResult]:
        """Generate and validate structured Chronicle output with one corrective retry."""
        validation_error: Exception | None = None
        prompt = contents

        # Native Gemini owns schema recovery and model fallback in one two-call loop.
        attempts = 1 if self.provider_config.provider == ADVISOR_PROVIDER_GEMINI else 2
        for attempt in range(attempts):
            try:
                result = self._generate_content_with_routing(
                    contents=prompt,
                    config={
                        "temperature": temperature,
                        "max_output_tokens": max_output_tokens,
                        "response_schema": response_schema,
                        "allow_schema_fallback": attempt == 0,
                    },
                    purpose_label=purpose_label,
                    game_knowledge_context=game_knowledge_context,
                )
            except AdvisorProviderError as exc:
                if attempt + 1 < attempts and exc.code == "PROVIDER_EMPTY_RESPONSE":
                    logger.warning("%s returned an empty response; retrying once", purpose_label)
                    prompt = (
                        f"{contents.rstrip()}\n\n"
                        "Return only a non-empty JSON object matching the requested schema."
                    )
                    continue
                raise
            try:
                return _validate_structured_response(result.text, response_schema), result
            except Exception as exc:
                validation_error = exc
                if attempt + 1 < attempts and not result.schema_fallback_used:
                    logger.warning(
                        "%s returned invalid structured output; retrying once: %s",
                        purpose_label,
                        exc,
                    )
                    prompt = (
                        f"{contents.rstrip()}\n\n"
                        "Your previous response could not be validated. Return only a JSON "
                        "object matching the requested schema. Do not include Markdown or "
                        f"commentary. Validation issue: {str(exc)[:500]}"
                    )
                else:
                    break

        raise AdvisorProviderError(
            f"{self.provider_config.display_name} could not produce valid structured "
            f"output for {purpose_label}",
            code="PROVIDER_INVALID_RESPONSE",
        ) from validation_error

    def _record_model_generation(self, result: AdvisorGenerationResult) -> None:
        event = dict(result.routing or {})
        event.setdefault("requested_model", result.requested_model)
        event.setdefault(
            "requested_model_display",
            display_model_name(result.requested_model),
        )
        event.setdefault("attempted_model", result.model)
        event.setdefault("attempted_model_display", display_model_name(result.model))
        event.setdefault("final_model", result.model)
        event.setdefault("final_model_display", display_model_name(result.model))
        event.setdefault("fallback", result.model != result.requested_model)
        event.setdefault("reason", None)
        event.setdefault("notice", None)
        event.setdefault("error", None)
        event["provider"] = result.provider
        event["diagnostics"] = result.diagnostics
        self._model_route_events.append(event)

    def _model_routing_response(self) -> dict[str, Any]:
        events = list(self._model_route_events)
        last_event = events[-1] if events else None
        fallback_events = [event for event in events if event.get("fallback")]
        last_fallback = fallback_events[-1] if fallback_events else None
        return {
            "mode": self.model_routing_mode,
            "provider": self.provider_config.provider,
            "provider_display": self.provider_config.display_name,
            "model": last_event.get("final_model") if last_event else None,
            "model_display": last_event.get("final_model_display") if last_event else None,
            "fallback": bool(fallback_events),
            "notice": last_fallback.get("notice") if last_fallback else None,
            "events": events,
        }

    # --- Private Methods ---

    def _load_chapters_data(self, cached: dict[str, Any] | None) -> dict[str, Any]:
        """Normalize stable chapter anchors consistently across every writer."""
        return load_chapters_data(cached)

    def _chapter_only_cooldown_active(
        self,
        *,
        chapters_data: dict[str, Any],
    ) -> tuple[bool, int]:
        """Return whether chapter-only auto generation is currently deferred."""
        auto_sync = chapters_data.get("auto_chapter_sync")
        if not isinstance(auto_sync, dict):
            return False, 0

        next_allowed_at = _parse_iso_datetime(auto_sync.get("next_allowed_at"))
        if next_allowed_at is None:
            return False, 0

        now = datetime.now(timezone.utc)
        if now >= next_allowed_at:
            return False, 0

        pending = auto_sync.get("pending_chapters")
        pending_count = pending if isinstance(pending, int) and pending >= 0 else 0
        return True, pending_count

    def _set_next_chapter_only_run(
        self,
        *,
        chapters_data: dict[str, Any],
        pending_chapters: int,
    ) -> None:
        """Persist next chapter-only auto sync window."""
        pending = max(0, int(pending_chapters))
        interval = (
            AUTO_CHAPTER_PENDING_INTERVAL_SECONDS
            if pending > 0
            else AUTO_CHAPTER_IDLE_INTERVAL_SECONDS
        )
        next_allowed = datetime.now(timezone.utc).timestamp() + interval
        chapters_data["auto_chapter_sync"] = {
            "pending_chapters": pending,
            "interval_seconds": interval,
            "next_allowed_at": datetime.fromtimestamp(next_allowed, timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

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

        # Do not finalize when no new snapshot has been recorded since era start.
        if era_start_snapshot_id is not None and int(current_snapshot_id) <= int(
            era_start_snapshot_id
        ):
            return False, None

        # Check time threshold (30+ years)
        years_elapsed = current_year - era_start_year
        # Pull events once; used for both chapter 1 special-cases and normal triggers.
        events = self.db.get_events_in_snapshot_range(
            save_id=save_id,
            from_snapshot_id=era_start_snapshot_id,
            to_snapshot_id=current_snapshot_id,
        )

        # Special-case: get Chapter 1 on the page quickly.
        # This also has the nice UX property of shrinking the "Current Era" window,
        # which reduces visible rewrites of "The Story Continues...".
        if not chapters:
            if (
                years_elapsed >= FIRST_CHAPTER_TIME_THRESHOLD
                and len(events) >= FIRST_CHAPTER_MIN_EVENTS_TIME
            ):
                return True, "time_threshold"

            if years_elapsed >= FIRST_CHAPTER_MIN_YEARS_MILESTONE and len(events) >= (
                FIRST_CHAPTER_MIN_EVENTS_MILESTONE
            ):
                # Use the first matching milestone event type as the chapter end trigger
                # (chapter end date becomes that event's date).
                for event in events:
                    et = event.get("event_type")
                    if et in FIRST_CHAPTER_MILESTONE_EVENTS:
                        return True, str(et)

        if years_elapsed >= CHAPTER_TIME_THRESHOLD:
            return True, "time_threshold"

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
        temp_data = json.loads(json_dumps(chapters_data))  # Deep copy

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
        custom_instructions: str | None = None,
        snapshot_range: dict[str, Any] | None = None,
        language: str = "en",
    ) -> bool:
        """Generate and finalize a new chapter.

        Returns True when a chapter was added; False when finalization is
        skipped (for example, no new snapshot range is available yet).
        """
        chapters = chapters_data.get("chapters", [])
        chapter_number = len(chapters) + 1
        snapshot_range = snapshot_range or self.db.get_snapshot_range_for_save(save_id)
        latest_snapshot_id = snapshot_range.get("last_snapshot_id")
        latest_game_date = snapshot_range.get("last_game_date")

        # Determine chapter date range
        if chapters:
            last_chapter = chapters[-1]
            start_date = last_chapter.get("end_date")
            start_snapshot_id = last_chapter.get("end_snapshot_id")
        else:
            start_date = snapshot_range.get("first_game_date", "2200.01.01")
            start_snapshot_id = snapshot_range.get("first_snapshot_id")

        # Find the end date based on trigger
        if trigger == "time_threshold":
            # Chapter 1 should appear early. Later chapters use the longer threshold.
            threshold_years = (
                FIRST_CHAPTER_TIME_THRESHOLD if chapter_number == 1 else CHAPTER_TIME_THRESHOLD
            )
            start_year = parse_year(start_date) or 2200
            target_end_year = start_year + threshold_years
            target_end_date = f"{target_end_year}.01.01"
            snapshot_at_or_before = self.db.get_latest_snapshot_at_or_before(
                save_id=save_id,
                game_date=target_end_date,
                upper_snapshot_id=latest_snapshot_id,
            )
            if snapshot_at_or_before:
                end_snapshot_id = snapshot_at_or_before.get("id")
                end_date = snapshot_at_or_before.get("game_date") or target_end_date
            else:
                # Sparse snapshots can leap across decades. In that case, close
                # at the latest available snapshot rather than emitting an empty chapter.
                end_snapshot_id = latest_snapshot_id
                end_date = latest_game_date or target_end_date
        else:
            # Use the triggering event's date as chapter end
            events = self.db.get_events_in_snapshot_range(
                save_id=save_id, to_snapshot_id=latest_snapshot_id
            )
            end_date = start_date
            for event in reversed(events):
                if event.get("event_type") == trigger:
                    end_date = event.get("game_date", end_date)
                    break
            snapshot_at_or_before = (
                self.db.get_latest_snapshot_at_or_before(
                    save_id=save_id,
                    game_date=end_date or (latest_game_date or "2200.01.01"),
                    upper_snapshot_id=latest_snapshot_id,
                )
                if end_date
                else None
            )
            end_snapshot_id = (
                snapshot_at_or_before.get("id") if snapshot_at_or_before else latest_snapshot_id
            )
            # Coverage is the dated source actually available, rather than an
            # event date for which no snapshot context has been captured.
            end_date = (
                snapshot_at_or_before.get("game_date")
                if snapshot_at_or_before
                else latest_game_date
            ) or end_date

        if end_snapshot_id is None:
            return False
        if start_snapshot_id is not None and int(end_snapshot_id) <= int(start_snapshot_id):
            return False

        # Get events for this chapter
        chapter_events = self.db.get_events_in_snapshot_range(
            save_id=save_id,
            from_snapshot_id=start_snapshot_id,
            to_snapshot_id=end_snapshot_id,
        )

        # Date and captured snapshot boundaries both apply after a save rollback.
        chapter_events = events_between_dates(chapter_events, start_date, end_date)

        # Historical chapters use facts captured at their end, never today's politics.
        historical = self.db.get_historical_chronicle_briefing(save_id, end_snapshot_id)
        briefing = historical if isinstance(historical, dict) else {}
        selected_events, partial = self._select_events_for_prompt(
            chapter_events, max_events=MAX_EVENTS_PER_CHAPTER_PROMPT
        )
        source_bundle = {
            "version": 1,
            "start_snapshot_id": start_snapshot_id,
            "end_snapshot_id": end_snapshot_id,
            "coverage_date": end_date,
            "briefing": compact_chronicle_context(briefing),
            "events": source_events(selected_events),
            "source_event_count": len(chapter_events),
            "selected_event_count": len(selected_events),
            "partial_coverage": partial,
            "historical_context_limited": bool(briefing.get("historical_context_limited")),
        }
        # Generate chapter content
        content = self._generate_chapter_content(
            chapter_number=chapter_number,
            events=chapter_events,
            briefing=briefing,
            previous_chapters=chapters,
            start_date=start_date,
            end_date=end_date,
            custom_instructions=custom_instructions,
            language=language,
        )

        # Add the new chapter
        chapters_data["chapters"].append(
            {
                "id": chapter_identity(
                    {
                        "number": chapter_number,
                        "start_snapshot_id": start_snapshot_id,
                        "end_snapshot_id": end_snapshot_id,
                        "start_date": start_date,
                        "end_date": end_date,
                    }
                ),
                "number": chapter_number,
                "title": content["title"],
                "start_date": start_date,
                "end_date": end_date,
                "start_snapshot_id": start_snapshot_id,
                "end_snapshot_id": end_snapshot_id,
                "epigraph": content.get("epigraph", ""),
                "sections": content.get("sections"),
                "narrative": content["narrative"],
                "summary": content["summary"],
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "is_finalized": True,
                "context_stale": False,
                "trigger": trigger,
                "event_count": len(chapter_events),
                "coverage_date": end_date,
                "source_bundle": source_bundle,
                "selected_event_count": len(selected_events),
                "partial_coverage": partial,
                "historical_context_limited": source_bundle["historical_context_limited"],
                "provider": content.get("provider"),
                "model": content.get("model"),
            }
        )

        # Update current era start
        chapters_data["current_era_start_date"] = end_date
        chapters_data["current_era_start_snapshot_id"] = end_snapshot_id
        return True

    def _generate_chapter_content(
        self,
        chapter_number: int,
        events: list[dict],
        briefing: dict[str, Any],
        previous_chapters: list[dict],
        start_date: str,
        end_date: str,
        custom_instructions: str | None = None,
        regeneration_instructions: str | None = None,
        language: str = "en",
    ) -> dict[str, Any]:
        """Generate and validate a structured Chronicle chapter."""
        identity = briefing.get("identity", {})
        empire_name = identity.get("empire_name", "Unknown Empire")
        ethics = ", ".join(identity.get("ethics", []))
        voice = self._get_voice_for_ethics(identity, ethics)

        # Build context from previous chapters
        context_lines = []
        for ch in previous_chapters[-8:]:
            context_lines.append(
                f'- Chapter {ch["number"]} "{ch.get("title", "Untitled")}" '
                f"({ch.get('start_date', '?')} - {ch.get('end_date', '?')}): {str(ch.get('summary', ''))[:2000]}"
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
        narrative_scope = _chapter_narrative_scope(selected_events)
        truncation_note = ""
        if was_truncated:
            truncation_note = (
                f"NOTE: Event list truncated to {len(selected_events)} events to fit context. "
                "Focus on major arcs and turning points.\n"
            )

        diplomatic_context = self._format_diplomatic_context(briefing)
        diplomatic_section = f"\n{diplomatic_context}\n" if diplomatic_context else ""
        geographic_context = self._format_geographic_context(briefing)
        geographic_section = f"\n{geographic_context}\n" if geographic_context else ""

        custom_section = ""
        if custom_instructions and custom_instructions.strip():
            custom_section = f"""
=== CHRONICLE STYLE CUSTOMIZATION (player-provided) ===
{custom_instructions.strip()}
"""

        regen_section = ""
        if regeneration_instructions and regeneration_instructions.strip():
            regen_section = f"""
=== REGENERATION GUIDANCE (player-provided, one-time) ===
The player has specifically requested these changes for this regeneration:
{regeneration_instructions.strip()}
Incorporate this guidance while maintaining narrative consistency.
"""

        language_policy = build_language_policy(
            language,
            structured_json=True,
            user_visible_fields=("title", "epigraph", "sections.text", "attribution", "summary"),
        )

        prompt = f"""You are the Royal Chronicler of {empire_name}.

=== CHRONICLER'S VOICE ===
{voice}
{custom_section}
{language_policy}

=== PREVIOUS CHAPTERS (literary continuity, not additional evidence) ===
{previous_context}
Historical context is limited to the recorded facts supplied below. Missing politics or motives remain unknown.
{diplomatic_section}{geographic_section}
=== EVENTS FOR THIS CHAPTER ({start_date} to {end_date}) ===
{truncation_note}
{events_text}

{CHRONICLE_EVIDENCE_RULES}

=== YOUR TASK ===

Write Chapter {chapter_number} of the empire's chronicle.

Requirements:
- title: A dramatic, thematic name for this era
- epigraph: A short, evocative opening line — a proverb, decree, or ominous statement that sets the chapter's tone (max 20 words)
- sections: A narrative array sized to the evidence, with:
  - type "prose": Standard dramatic paragraphs (most sections should be this)
  - type "quote": Optional in-universe literary framing with an attribution
  - type "declaration": An optional short proclamation, used sparingly
- summary: 2-3 sentences summarizing key events for future chapter context

{narrative_scope}
Quotes and declarations are optional, never quotas, and cannot add campaign facts.

Do NOT give advice. You are a historian, not an advisor.
Do NOT fabricate events not in the event list.
You may dramatize language, but not facts. The epigraph must be atmospheric rather
than a factual claim. When a reason is not present in the event list, leave it unexplained.
{regen_section}"""

        parsed, response = self._generate_structured_content(
            contents=prompt,
            response_schema=ChapterOutput,
            temperature=0.7,
            max_output_tokens=4096,
            purpose_label=f"Chronicle chapter {chapter_number}",
            game_knowledge_context=_chronicle_game_knowledge(briefing),
        )
        chapter = ChapterOutput.model_validate(parsed)
        sections = [section.model_dump() for section in chapter.sections]
        return {
            "title": chapter.title,
            "epigraph": chapter.epigraph,
            "sections": sections,
            "narrative": _sections_to_text(sections, chapter.epigraph),
            "summary": chapter.summary,
            "provider": response.provider,
            "model": response.model,
        }

    def _generate_current_era(
        self,
        save_id: str,
        chapters_data: dict[str, Any],
        briefing: dict[str, Any],
        current_date: str | None,
        custom_instructions: str | None = None,
        current_snapshot_id: int | None = None,
        language: str = "en",
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
            to_snapshot_id=current_snapshot_id,  # Frozen request boundary
        )

        events = events_between_dates(events, era_start_date, current_date)
        if not events:
            return None

        identity = briefing.get("identity", {})
        empire_name = identity.get("empire_name", "Unknown Empire")
        ethics = ", ".join(identity.get("ethics", []))
        voice = self._get_voice_for_ethics(identity, ethics)

        # Build previous chapters context
        context_lines = []
        for ch in chapters[-8:]:
            context_lines.append(
                f'- Chapter {ch["number"]} "{ch.get("title", "Untitled")}": {ch.get("summary", "")}'
            )
        previous_context = "\n".join(context_lines) if context_lines else "No previous chapters."

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

        diplomatic_context = self._format_diplomatic_context(briefing)
        diplomatic_section = f"\n{diplomatic_context}\n" if diplomatic_context else ""
        geographic_context = self._format_geographic_context(briefing)
        geographic_section = f"\n{geographic_context}\n" if geographic_context else ""

        era_custom_section = ""
        if custom_instructions and custom_instructions.strip():
            era_custom_section = f"""
=== CHRONICLE STYLE CUSTOMIZATION (player-provided) ===
{custom_instructions.strip()}
"""

        language_policy = build_language_policy(
            language,
            structured_json=True,
            user_visible_fields=("sections.text", "attribution"),
        )

        prompt = f"""You are the Royal Chronicler of {empire_name}.

=== CHRONICLER'S VOICE ===
{voice}
{era_custom_section}
{language_policy}

=== PREVIOUS CHAPTERS (literary continuity, not additional evidence) ===
{previous_context}
Historical context is limited to the recorded facts supplied below. Missing politics or motives remain unknown.
{diplomatic_section}{geographic_section}
=== CURRENT ERA EVENTS ({era_start_date} to {current_date or "unknown date"}) ===
{truncation_note}
{events_text}

{CHRONICLE_EVIDENCE_RULES}

=== YOUR TASK ===

Write a brief narrative for "The Current Era" - the unfolding present.
This is NOT a finalized chapter - it's a 1-2 paragraph teaser about current events.

Return structured sections:
- sections: 1-3 blocks, each with type ("prose" or optional literary "quote") and text.
  A quote must not add campaign facts absent from the evidence.
End the final prose section with "The story continues..."

Do NOT give advice. You are a historian, not an advisor.
"""

        parsed, response = self._generate_structured_content(
            contents=prompt,
            response_schema=CurrentEraOutput,
            temperature=1.0,
            # Thinking models share this budget with the final structured response.
            max_output_tokens=4096,
            purpose_label="Chronicle current era",
            game_knowledge_context=_chronicle_game_knowledge(briefing),
        )
        era_output = CurrentEraOutput.model_validate(parsed)
        sections = [section.model_dump() for section in era_output.sections]
        return {
            "start_date": era_start_date,
            "sections": sections,
            "narrative": _sections_to_text(sections),
            "events_covered": len(events),
            "selected_event_count": len(selected_events),
            "partial_coverage": was_truncated,
            "coverage_date": current_date,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "provider": response.provider,
            "model": response.model,
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
            lines.append(f"### CHAPTER {ch['number']}: {ch.get('title', 'Untitled').upper()}")
            lines.append(f"**{ch.get('start_date', '?')} – {ch.get('end_date', '?')}**\n")
            lines.append(ch.get("narrative", ""))
            lines.append("")

        if current_era:
            lines.append("### THE CURRENT ERA")
            lines.append(f"**{current_era.get('start_date', '?')} – Present**\n")
            lines.append(current_era.get("narrative", ""))

        return "\n".join(lines)

    def _empty_chronicle_response(self, *, language: str = "en") -> dict[str, Any]:
        """Return empty chronicle response."""
        return {
            **cached_chronicle_response(None),
            "chapters": [],
            "current_era": None,
            "pending_chapters": 0,
            "message": None,
            "chronicle": localized_text("no_events_chronicle", language),
            "cached": False,
            "event_count": 0,
            "generated_at": "",
            "language": language,
            "model_routing": self._model_routing_response(),
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

        # Capture the source revision and counts before provider work.
        base = self.db.get_cached_chronicle(session_id)
        expected_revision = chronicle_revision(load_chapters_data(base))
        snapshot_count = self.db.get_snapshot_count(session_id)
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

        # Generate through the selected provider.
        response = self._generate_content_with_routing(
            contents=prompt,
            config={"temperature": 1.0, "max_output_tokens": 4096},
            purpose_label="Chronicle legacy",
            game_knowledge_context=_chronicle_game_knowledge(data["briefing"]),
        )

        chronicle_text = response.text
        event_count = len(data["events"])
        saved = self.db.commit_legacy_chronicle(
            session_id=session_id,
            expected_revision=expected_revision,
            chronicle_text=chronicle_text,
            event_count=event_count,
            snapshot_count=snapshot_count,
            coverage_date=data.get("last_date"),
        )

        return {
            **cached_chronicle_response(saved),
            "chronicle": chronicle_text,
            "cached": False,
            "event_count": event_count,
            "generated_at": cached_chronicle_response(saved)["generated_at"],
            "provider": response.provider,
            "model": response.model,
            "model_routing": self._model_routing_response(),
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
        briefing = build_model_briefing(json.loads(briefing_json)) if briefing_json else {}

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
(From {data["first_date"]} to {data["last_date"]})
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
                "Use cold, logical precision and technical language, as a historical data "
                "log for future processing units."
            )
        elif identity.get("is_hive_mind"):
            return "Write as a solemn collective memory using 'we' and 'the swarm'."
        elif "fanatic_authoritarian" in ethics or "authoritarian" in ethics:
            return "Use formal imperial grandeur and a stately, ceremonial cadence."
        elif "fanatic_egalitarian" in ethics or "egalitarian" in ethics:
            return "Use a civic, people-centered tone with democratic imagery."
        elif "fanatic_militarist" in ethics or "militarist" in ethics:
            return "Use a disciplined martial cadence and the vocabulary of military history."
        elif "fanatic_spiritualist" in ethics or "spiritualist" in ethics:
            return "Use solemn, reverent language and spiritual imagery."
        elif "fanatic_pacifist" in ethics or "pacifist" in ethics:
            return "Use a reflective, diplomatic tone and measured language."
        elif "fanatic_materialist" in ethics or "materialist" in ethics:
            return "Use precise, intellectually curious language with scientific imagery."
        else:
            return "Write with epic gravitas befitting a galactic chronicle."

    def _build_recap_prompt(self, data: dict[str, Any], *, language: str = "en") -> str:
        """Build a shorter recap prompt for recent events."""
        briefing = data["briefing"]
        identity = briefing.get("identity", {})
        empire_name = identity.get("empire_name", "Unknown Empire")

        events_text = self._format_events(data["events"])
        state_text = self._summarize_state(briefing)

        language_policy = build_language_policy(language)

        return f"""You are the Royal Chronicler of {empire_name}. Write a dramatic "Previously on..." recap.

{language_policy}

{state_text}

=== RECENT EVENTS ===
{events_text}

{CHRONICLE_EVIDENCE_RULES}

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

            for event in source_events(year_events):
                date = event.get("game_date") or "Unknown date"
                lines.append(f"  * {date}: {event['summary']}")

        return "\n".join(lines)

    def _format_diplomatic_context(self, briefing: dict) -> str:
        """Format diplomatic relations for the LLM prompt.

        Summarises known empires, their ethics, and the player's relationship
        with them so the chronicler can reference neighbours by name and
        disposition rather than inventing details.

        Returns an empty string when no diplomacy data is available (the prompt
        section is simply omitted).
        """
        diplomacy = briefing.get("diplomacy")
        if not isinstance(diplomacy, dict):
            return ""

        relations = diplomacy.get("relations", [])
        if not relations:
            return ""

        empire_lines: list[str] = []
        special_lines: list[str] = []

        for rel in relations:
            name = rel.get("empire_name")
            if not name:
                continue

            country_type = str(rel.get("country_type") or "default")
            if country_type != "default":
                special_lines.append(f"- {name} | type: {country_type} | special contact")
                continue

            parts = [name]

            # Ethics (e.g. "fanatic_xenophobe, militarist")
            ethics = rel.get("ethics")
            if ethics and isinstance(ethics, list):
                parts.append(f"ethics: {', '.join(ethics)}")

            # Authority (e.g. "auth_imperial")
            authority = rel.get("authority")
            if authority:
                parts.append(authority.replace("auth_", ""))

            # Opinion
            opinion = rel.get("opinion")
            if opinion is not None:
                parts.append(f"opinion {opinion:+d}")

            # Key diplomatic statuses
            statuses = []
            if rel.get("rival"):
                statuses.append("rival")
            if rel.get("defensive_pact"):
                statuses.append("defensive pact")
            if rel.get("non_aggression_pact"):
                statuses.append("NAP")
            if rel.get("commercial_pact"):
                statuses.append("commercial pact")
            if rel.get("research_agreement"):
                statuses.append("research agreement")
            if rel.get("closed_borders"):
                statuses.append("closed borders")
            if rel.get("has_truce"):
                statuses.append("truce")
            if statuses:
                parts.append(", ".join(statuses))

            empire_lines.append(f"- {' | '.join(parts)}")

        lines: list[str] = []
        if empire_lines:
            lines.append("=== KNOWN EMPIRES ===")
            lines.extend(empire_lines)
        if special_lines:
            if lines:
                lines.append("")
            lines.append("=== SPECIAL CONTACTS (NOT ORDINARY EMPIRES) ===")
            lines.extend(special_lines)

        # Federation
        federation = diplomacy.get("federation")
        if federation and isinstance(federation, dict):
            fed_name = federation.get("name", "Unknown Federation")
            if lines:
                lines.append("")
            lines.append(f"Federation: {fed_name}")

        return "\n".join(lines)

    def _format_geographic_context(self, briefing: dict) -> str:
        """Format strategic geography for the LLM prompt.

        Provides border neighbors with compass directions and key chokepoints
        so the chronicler can reference spatial relationships and named
        systems rather than inventing locations.

        Returns an empty string when no geography data is available.
        """
        geography = briefing.get("strategic_geography")
        if not isinstance(geography, dict):
            return ""

        lines: list[str] = []

        # Border neighbors: top 5, name + direction
        neighbors = geography.get("border_neighbors", [])
        if isinstance(neighbors, list) and neighbors:
            parts: list[str] = []
            for n in neighbors[:5]:
                if not isinstance(n, dict):
                    continue
                name = n.get("empire_name")
                if not name:
                    continue
                direction = n.get("direction", "")
                parts.append(f"{name} ({direction})" if direction else name)
            if parts:
                lines.append(f"Border neighbors: {', '.join(parts)}")

        # Chokepoints: top 3, system name + enemy
        chokepoints = geography.get("chokepoints", [])
        if isinstance(chokepoints, list) and chokepoints:
            choke_parts: list[str] = []
            for c in chokepoints[:3]:
                if not isinstance(c, dict):
                    continue
                sys_name = c.get("system_name")
                if not sys_name:
                    continue
                enemies = c.get("enemy_neighbors", [])
                if enemies:
                    choke_parts.append(f"{sys_name} (borders {', '.join(enemies[:2])})")
                else:
                    choke_parts.append(sys_name)
            if choke_parts:
                lines.append(f"Chokepoints: {'; '.join(choke_parts)}")

        if not lines:
            return ""

        return "=== STRATEGIC BORDERS ===\n" + "\n".join(lines)

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
