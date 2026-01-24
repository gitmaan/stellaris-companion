"""
Chronicle Generation Engine
============================

LLM-powered narrative generation for empire storytelling.
Produces dramatic, Stellaris Invicta-style chronicles from game events.

See docs/CHRONICLE_IMPLEMENTATION.md for full specification.
See docs/CHRONICLE_TESTING.md for prompt validation results.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from google import genai

from backend.core.database import GameDatabase


class ChronicleGenerator:
    """Generate LLM-powered chronicles for empire sessions."""

    # Staleness thresholds - regenerate if exceeded
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
        """Generate a full chronicle for the session.

        Returns cached version if available and recent.
        """
        # Check cache (unless force refresh)
        if not force_refresh:
            cached = self._get_cached_if_valid(session_id)
            if cached:
                return cached

        # Gather data (uses get_all_events - no 100 cap)
        data = self._gather_session_data(session_id)

        if not data["events"]:
            return {
                "chronicle": "No events recorded yet. The chronicle awaits the first chapters of history.",
                "cached": False,
                "event_count": 0,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        # Build prompt with ethics-based voice
        prompt = self._build_chronicler_prompt(data)

        # Call Gemini (blocking - endpoint should be sync def)
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

        # Dramatic LLM-powered recap (uses limited events - OK for recap)
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

    def _get_cached_if_valid(self, session_id: str) -> dict[str, Any] | None:
        """Get cached chronicle if still valid (not stale)."""
        cached = self.db.get_cached_chronicle(session_id)
        if not cached:
            return None

        # Check staleness by both event count AND snapshot count
        current_events = self.db.get_event_count(session_id)
        current_snapshots = self.db.get_snapshot_count(session_id)

        event_delta = current_events - cached["event_count"]
        snapshot_delta = current_snapshots - cached["snapshot_count"]

        if event_delta >= self.STALE_EVENT_THRESHOLD:
            return None  # Too many new events
        if snapshot_delta >= self.STALE_SNAPSHOT_THRESHOLD:
            return None  # Too many new snapshots (catches quiet periods)

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

        # Get events - use get_all_events for chronicles (no cap)
        if max_events is None:
            events = self.db.get_all_events(session_id=session_id)
        else:
            events = self.db.get_recent_events(session_id=session_id, limit=max_events)

        # Get briefing for identity/personality
        briefing_json = self.db.get_latest_session_briefing_json(session_id=session_id)
        briefing = json.loads(briefing_json) if briefing_json else {}

        # Get date range
        stats = self.db.get_session_snapshot_stats(session_id)

        return {
            "session": dict(session),
            "events": events,
            "briefing": briefing,
            "first_date": stats.get("first_game_date"),
            "last_date": stats.get("last_game_date"),
        }

    def _build_chronicler_prompt(self, data: dict[str, Any]) -> str:
        """Build the full chronicler prompt with ethics-based voice.

        See CHRONICLE_TESTING.md for validated prompt structure.
        """
        briefing = data["briefing"]
        identity = briefing.get("identity", {})

        empire_name = identity.get("empire_name", "Unknown Empire")
        ethics = ", ".join(identity.get("ethics", []))
        authority = identity.get("authority", "unknown")
        civics = ", ".join(identity.get("civics", []))

        # Ethics-based voice selection
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

        # Group by year for readability
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

            # Summarize if too many events in one year
            if len(year_events) > 15:
                notable_types = {
                    "war_started",
                    "war_ended",
                    "crisis_started",
                    "fallen_empire_awakened",
                    "war_in_heaven_started",
                    "federation_joined",
                    "alliance_formed",
                    "alliance_ended",
                    "colony_count_change",
                    "military_power_change",
                }
                notable = [e for e in year_events if e.get("event_type") in notable_types]
                for e in notable:
                    lines.append(f"  * {e.get('summary', e.get('event_type', 'Unknown event'))}")
                lines.append(f"  (+ {len(year_events) - len(notable)} other events)")
            else:
                for e in year_events:
                    lines.append(f"  * {e.get('summary', e.get('event_type', 'Unknown event'))}")

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
