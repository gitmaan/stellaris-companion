from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class Turn:
    question: str
    answer: str
    game_date: str | None
    created_at: float = field(default_factory=time.time)


@dataclass
class Session:
    history: list[Turn] = field(default_factory=list)
    last_game_date: str | None = None
    last_active: float = field(default_factory=time.time)


class ConversationManager:
    """Sliding-window, per-session conversation memory.

    This is intentionally simple: /ask re-injects the full briefing each turn,
    and we keep only a small amount of recent chat history to support follow-ups.
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
        return time.time()

    def _is_expired(self, session: Session) -> bool:
        return (self._now() - float(session.last_active or 0.0)) > self.timeout_seconds

    def _get_or_create(self, session_key: str) -> Session:
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
        session = self._get_or_create(session_key)
        session.history.append(Turn(question=question, answer=answer, game_date=game_date))
        session.last_game_date = game_date or session.last_game_date
        session.last_active = self._now()
        if len(session.history) > self.max_turns:
            session.history = session.history[-self.max_turns :]

