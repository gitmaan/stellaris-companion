"""Conversation management for multi-turn chat sessions.

Provides sliding-window conversation memory with per-session isolation,
automatic timeout handling, and prompt building for the LLM advisor.

The design is intentionally simple: each turn re-injects the full briefing,
and only recent chat history is retained for follow-up context. This avoids
unbounded context growth while supporting conversational continuity.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class Turn:
    """A single question-answer exchange in a conversation.

    Attributes:
        question: The user's question text.
        answer: The advisor's response text.
        game_date: The in-game date when this turn occurred (e.g., "2250.03.15").
        created_at: Unix timestamp when this turn was recorded.
    """

    question: str
    answer: str
    game_date: str | None
    created_at: float = field(default_factory=time.time)


@dataclass
class Session:
    """A conversation session containing turn history and metadata.

    Attributes:
        history: List of Turn objects in chronological order.
        last_game_date: Most recent in-game date seen in this session.
        last_active: Unix timestamp of last activity (for timeout detection).
    """

    history: list[Turn] = field(default_factory=list)
    last_game_date: str | None = None
    last_active: float = field(default_factory=time.time)


class ConversationManager:
    """Sliding-window, per-session conversation memory.

    This is intentionally simple: /ask re-injects the full briefing each turn,
    and we keep only a small amount of recent chat history to support follow-ups.

    Attributes:
        max_turns: Maximum number of turns to retain in history.
        timeout_seconds: Fallback inactivity expiry when game date is unavailable.
        max_game_months: Expire short-term memory after this in-game month delta.
        max_answer_chars: Maximum characters to include from previous answers.
    """

    def __init__(
        self,
        *,
        max_turns: int = 5,
        timeout_minutes: int = 24 * 60,
        max_game_months: int = 12,
        max_answer_chars: int = 500,
        max_question_chars: int = 320,
        max_recent_conversation_chars: int = 5000,
        max_summary_chars: int = 1800,
        max_history_context_chars: int = 3500,
    ) -> None:
        self.max_turns = max(1, int(max_turns))
        self.timeout_seconds = max(60, int(timeout_minutes) * 60)
        self.max_game_months = max(1, int(max_game_months))
        self.max_answer_chars = max(50, int(max_answer_chars))
        self.max_question_chars = max(80, int(max_question_chars))
        self.max_recent_conversation_chars = max(300, int(max_recent_conversation_chars))
        self.max_summary_chars = max(200, int(max_summary_chars))
        self.max_history_context_chars = max(500, int(max_history_context_chars))

        self._lock = threading.RLock()
        self._sessions: dict[str, Session] = {}

    def _now(self) -> float:
        """Return current Unix timestamp."""
        return time.time()

    def _parse_game_date(self, value: str | None) -> tuple[int, int, int] | None:
        """Parse Stellaris game date strings (e.g. 2250.03.15)."""
        if not value:
            return None
        raw = str(value).strip()
        if not raw:
            return None
        parts = raw.split(".")
        if len(parts) < 2:
            return None
        try:
            year = int(parts[0])
            month = int(parts[1])
            day = int(parts[2]) if len(parts) >= 3 else 1
        except Exception:
            return None
        if year < 0 or not (1 <= month <= 12):
            return None
        day = max(1, min(day, 31))
        return year, month, day

    def _game_month_delta(self, older: str | None, newer: str | None) -> int | None:
        """Return in-game month delta (newer - older), or None if unparsable."""
        old_parsed = self._parse_game_date(older)
        new_parsed = self._parse_game_date(newer)
        if not old_parsed or not new_parsed:
            return None
        old_year, old_month, _ = old_parsed
        new_year, new_month, _ = new_parsed
        return ((new_year - old_year) * 12) + (new_month - old_month)

    def _is_expired(self, session: Session, *, current_game_date: str | None) -> bool:
        """Check if a session has exceeded in-game or fallback real-time staleness."""
        # Primary staleness rule: if enough in-game time passed, prior tactical turns are stale.
        delta_months = self._game_month_delta(session.last_game_date, current_game_date)
        if delta_months is not None:
            if delta_months < 0:
                # Save rolled back in time (or switched branch): reset short-term memory.
                return True
            if delta_months >= self.max_game_months:
                return True

        # Fallback for missing/unparseable game dates.
        return (self._now() - float(session.last_active or 0.0)) > self.timeout_seconds

    def _get_or_create(self, session_key: str, *, current_game_date: str | None = None) -> Session:
        """Get existing session or create a new one, expiring stale sessions.

        Args:
            session_key: Unique identifier for the session (e.g., playthrough ID).

        Returns:
            The active Session object with updated last_active timestamp.
        """
        with self._lock:
            session = self._sessions.get(session_key)
            if session and self._is_expired(session, current_game_date=current_game_date):
                session = None
                self._sessions.pop(session_key, None)
            if session is None:
                session = Session()
                self._sessions[session_key] = session
            session.last_active = self._now()
            return session

    def clear(self, session_key: str) -> None:
        """Remove a session and its history.

        Args:
            session_key: Unique identifier for the session to clear.
        """
        with self._lock:
            self._sessions.pop(session_key, None)

    def build_prompt(
        self,
        *,
        session_key: str,
        briefing_json: str,
        game_date: str | None,
        question: str,
        data_note: str | None = None,
        history_context: str | None = None,
        long_term_summary: str | None = None,
    ) -> str:
        """Build the full prompt for the LLM including context and history.

        Assembles a prompt containing:
        - Optional data note (warnings about data quality)
        - Game date change notification if date progressed
        - Current empire state as JSON briefing
        - Optional history context for trend questions
        - Recent conversation turns (sliding window)
        - The current user question

        Args:
            session_key: Unique identifier for the session.
            briefing_json: JSON string of current empire state.
            game_date: Current in-game date (e.g., "2250.03.15").
            question: The user's current question.
            data_note: Optional warning about data quality/freshness.
            history_context: Optional historical data for trend analysis.

        Returns:
            The assembled prompt string ready for LLM input.
        """
        session = self._get_or_create(session_key, current_game_date=game_date)

        lines: list[str] = []

        if data_note:
            lines.append(f"[Data note: {data_note}]")
            lines.append("")

        if session.last_game_date and game_date and session.last_game_date != game_date:
            lines.append(f"[Game updated: {session.last_game_date} → {game_date}]")
            lines.append("")

        if game_date:
            lines.append(f"EMPIRE STATE ({game_date}):")
        else:
            lines.append("EMPIRE STATE (date unknown):")
        lines.append("```json")
        lines.append(briefing_json)
        lines.append("```")
        lines.append("")

        if long_term_summary:
            lines.append("SAVE MEMORY (key goals and prior commitments):")
            lines.append(long_term_summary[: self.max_summary_chars])
            lines.append("")

        if history_context:
            lines.append("HISTORY CONTEXT (only relevant for changes over time):")
            lines.append(history_context[: self.max_history_context_chars])
            lines.append("")

        if session.history:
            lines.append("RECENT CONVERSATION:")
            selected_blocks: list[str] = []
            used_chars = 0
            for turn in reversed(session.history[-self.max_turns :]):
                answer = (turn.answer or "").strip()
                if len(answer) > self.max_answer_chars:
                    answer = answer[: self.max_answer_chars].rstrip() + "..."
                question_text = (turn.question or "").strip()
                if len(question_text) > self.max_question_chars:
                    question_text = question_text[: self.max_question_chars].rstrip() + "..."
                block = f"User: {question_text}\nAdvisor: {answer}\n"
                # Keep most recent context first when budget is tight.
                if (
                    selected_blocks
                    and (used_chars + len(block)) > self.max_recent_conversation_chars
                ):
                    continue
                selected_blocks.append(block)
                used_chars += len(block)
                if used_chars >= self.max_recent_conversation_chars:
                    break
            for block in reversed(selected_blocks):
                lines.extend(block.rstrip("\n").splitlines())
                lines.append("")

        lines.append("CURRENT QUESTION:")
        lines.append(question)

        return "\n".join(lines).strip()

    def record_turn(
        self,
        *,
        session_key: str,
        question: str,
        answer: str,
        game_date: str | None,
    ) -> None:
        """Record a completed question-answer exchange in the session history.

        Appends the turn to history and trims to max_turns if needed.
        Updates the session's last_game_date and last_active timestamp.

        Args:
            session_key: Unique identifier for the session.
            question: The user's question text.
            answer: The advisor's response text.
            game_date: The in-game date when this turn occurred.
        """
        session = self._get_or_create(session_key, current_game_date=game_date)
        session.history.append(Turn(question=question, answer=answer, game_date=game_date))
        session.last_game_date = game_date or session.last_game_date
        session.last_active = self._now()
        if len(session.history) > self.max_turns:
            session.history = session.history[-self.max_turns :]
