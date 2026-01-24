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
        timeout_seconds: Seconds of inactivity before session expires.
        max_answer_chars: Maximum characters to include from previous answers.
    """

    def __init__(
        self,
        *,
        max_turns: int = 5,
        timeout_minutes: int = 15,
        max_answer_chars: int = 500,
    ) -> None:
        self.max_turns = max(1, int(max_turns))
        self.timeout_seconds = max(60, int(timeout_minutes) * 60)
        self.max_answer_chars = max(50, int(max_answer_chars))

        self._lock = threading.RLock()
        self._sessions: dict[str, Session] = {}

    def _now(self) -> float:
        """Return current Unix timestamp."""
        return time.time()

    def _is_expired(self, session: Session) -> bool:
        """Check if a session has exceeded the inactivity timeout."""
        return (self._now() - float(session.last_active or 0.0)) > self.timeout_seconds

    def _get_or_create(self, session_key: str) -> Session:
        """Get existing session or create a new one, expiring stale sessions.

        Args:
            session_key: Unique identifier for the session (e.g., Discord user ID).

        Returns:
            The active Session object with updated last_active timestamp.
        """
        with self._lock:
            session = self._sessions.get(session_key)
            if session and self._is_expired(session):
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
        session = self._get_or_create(session_key)

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

        if history_context:
            lines.append("HISTORY CONTEXT (only relevant for changes over time):")
            lines.append(history_context[:3500])
            lines.append("")

        if session.history:
            lines.append("RECENT CONVERSATION:")
            for turn in session.history[-self.max_turns :]:
                answer = (turn.answer or "").strip()
                if len(answer) > self.max_answer_chars:
                    answer = answer[: self.max_answer_chars].rstrip() + "..."
                lines.append(f"User: {turn.question}")
                lines.append(f"Advisor: {answer}")
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
        session = self._get_or_create(session_key)
        session.history.append(
            Turn(question=question, answer=answer, game_date=game_date)
        )
        session.last_game_date = game_date or session.last_game_date
        session.last_active = self._now()
        if len(session.history) > self.max_turns:
            session.history = session.history[-self.max_turns :]
