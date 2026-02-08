"""Tests for chat memory behavior (short-term + save-scoped persistent summary)."""

from pathlib import Path

from backend.core.conversation import ConversationManager
from backend.core.database import GameDatabase


def test_conversation_expires_after_in_game_month_delta() -> None:
    """Short-term memory should expire when in-game month threshold is reached."""
    manager = ConversationManager(
        max_turns=5,
        max_game_months=12,
        timeout_minutes=24 * 60,
    )
    session_key = "scope-1"
    manager.record_turn(
        session_key=session_key,
        question="Should we build anchorages now?",
        answer="Yes, prioritize naval cap.",
        game_date="2200.01.01",
    )

    still_fresh = manager.build_prompt(
        session_key=session_key,
        briefing_json='{"meta":{"date":"2200.06.01"}}',
        game_date="2200.06.01",
        question="What next?",
    )
    assert "anchorages" in still_fresh

    expired = manager.build_prompt(
        session_key=session_key,
        briefing_json='{"meta":{"date":"2201.01.01"}}',
        game_date="2201.01.01",
        question="What now?",
    )
    assert "anchorages" not in expired
    assert "RECENT CONVERSATION:" not in expired


def test_conversation_fallback_timeout_when_game_date_missing() -> None:
    """Fallback real-time timeout should expire memory when dates are unavailable."""
    manager = ConversationManager(
        max_turns=5,
        max_game_months=12,
        timeout_minutes=1,
    )
    session_key = "scope-2"
    manager.record_turn(
        session_key=session_key,
        question="Remember this constraint",
        answer="Noted.",
        game_date=None,
    )

    # Force staleness beyond fallback timeout.
    manager._sessions[session_key].last_active = manager._now() - 120

    prompt = manager.build_prompt(
        session_key=session_key,
        briefing_json='{"meta":{"date":null}}',
        game_date=None,
        question="Can you still remember it?",
    )
    assert "Remember this constraint" not in prompt
    assert "RECENT CONVERSATION:" not in prompt


def test_recent_conversation_budget_prefers_latest_turns() -> None:
    """Prompt budget should keep the newest turns when not all turns fit."""
    manager = ConversationManager(
        max_turns=5,
        max_game_months=24,
        timeout_minutes=24 * 60,
        max_question_chars=200,
        max_answer_chars=200,
        max_recent_conversation_chars=130,
    )
    session_key = "scope-3"

    manager.record_turn(
        session_key=session_key,
        question="oldest-turn-question",
        answer="oldest-turn-answer with extra words to consume budget and force truncation pressure",
        game_date="2200.01.01",
    )
    manager.record_turn(
        session_key=session_key,
        question="middle-turn-question",
        answer="middle-turn-answer with extra words to consume budget and force truncation pressure",
        game_date="2200.02.01",
    )
    manager.record_turn(
        session_key=session_key,
        question="latest-turn-question",
        answer="latest-turn-answer with extra words to consume budget and force truncation pressure",
        game_date="2200.03.01",
    )

    prompt = manager.build_prompt(
        session_key=session_key,
        briefing_json='{"meta":{"date":"2200.03.01"}}',
        game_date="2200.03.01",
        question="current-turn",
    )

    assert "latest-turn-question" in prompt
    assert "oldest-turn-question" not in prompt


def test_save_scoped_advisor_memory_persists_round_trip(tmp_path: Path) -> None:
    """Advisor memory summary should persist and update by save_id."""
    db = GameDatabase(db_path=tmp_path / "memory.db")
    try:
        assert db.get_schema_version() >= 7

        assert db.get_advisor_memory_summary("save-123") is None

        db.upsert_advisor_memory_summary(
            save_id="save-123",
            summary_text="- [2200.01.01] User asked: early alloy rush",
            last_game_date="2200.01.01",
        )
        first = db.get_advisor_memory_summary("save-123")
        assert first is not None
        assert "early alloy rush" in first

        db.upsert_advisor_memory_summary(
            save_id="save-123",
            summary_text="- [2200.03.01] User asked: prep fleet timing",
            last_game_date="2200.03.01",
        )
        second = db.get_advisor_memory_summary("save-123")
        assert second is not None
        assert "prep fleet timing" in second
        assert "early alloy rush" not in second
    finally:
        db.close()
