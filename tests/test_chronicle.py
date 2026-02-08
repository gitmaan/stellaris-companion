"""Unit tests for chronicle.py."""

import json
from unittest.mock import MagicMock

import pytest

from backend.core.chronicle import (
    ERA_ENDING_EVENTS,
    NOTABLE_EVENT_TYPES,
    ChronicleGenerator,
    _repair_json_string,
    _sections_to_text,
)


class TestRepairJsonString:
    """Tests for _repair_json_string function."""

    def test_with_unescaped_newlines(self):
        """Test that literal newlines in strings are escaped."""
        raw = '{"text": "line1\nline2"}'
        repaired = _repair_json_string(raw)
        result = json.loads(repaired)
        assert "line1" in result["text"]
        assert "line2" in result["text"]

    def test_already_escaped_newlines(self):
        """Test that already-escaped newlines are preserved."""
        raw = '{"text": "line1\\nline2"}'
        repaired = _repair_json_string(raw)
        result = json.loads(repaired)
        assert result["text"] == "line1\nline2"

    def test_with_tabs(self):
        """Test that literal tabs in strings are escaped."""
        raw = '{"text": "col1\tcol2"}'
        repaired = _repair_json_string(raw)
        result = json.loads(repaired)
        assert "col1" in result["text"]
        assert "col2" in result["text"]

    def test_carriage_returns_removed(self):
        """Test that carriage returns are stripped from strings."""
        raw = '{"text": "line1\r\nline2"}'
        repaired = _repair_json_string(raw)
        result = json.loads(repaired)
        # \r is removed, \n is escaped
        assert "line1" in result["text"]
        assert "line2" in result["text"]
        assert "\r" not in result["text"]

    def test_empty_string(self):
        """Test empty string input."""
        raw = ""
        repaired = _repair_json_string(raw)
        assert repaired == ""

    def test_escaped_quotes(self):
        """Test that escaped quotes in strings are preserved."""
        raw = '{"text": "say \\"hello\\""}'
        repaired = _repair_json_string(raw)
        result = json.loads(repaired)
        assert result["text"] == 'say "hello"'

    def test_mixed_escapes(self):
        """Test combination of escaped and unescaped characters."""
        raw = '{"text": "line1\\nline2\nline3"}'
        repaired = _repair_json_string(raw)
        result = json.loads(repaired)
        # First newline is already escaped, second is literal and gets escaped
        assert "line1" in result["text"]
        assert "line2" in result["text"]
        assert "line3" in result["text"]

    def test_newlines_outside_strings_preserved(self):
        """Test that newlines in JSON structure (outside strings) are preserved."""
        raw = '{\n  "key": "value"\n}'
        repaired = _repair_json_string(raw)
        result = json.loads(repaired)
        assert result["key"] == "value"
        # Structural newlines should remain
        assert "\n" in repaired


class TestSelectEventsForPrompt:
    """Tests for ChronicleGenerator._select_events_for_prompt method."""

    @pytest.fixture
    def generator(self):
        """Create a ChronicleGenerator with mocked database."""
        mock_db = MagicMock()
        return ChronicleGenerator(db=mock_db, api_key="fake-key")

    def test_empty_events_returns_empty_list(self, generator):
        """Empty events list returns empty list, not truncated."""
        selected, truncated = generator._select_events_for_prompt([], max_events=10)
        assert selected == []
        assert truncated is False

    def test_no_truncation_when_under_limit(self, generator):
        """Events under max_events limit are returned unchanged."""
        events = [
            {"game_date": "2200.01.01", "event_type": "test", "summary": "Event 1"},
            {"game_date": "2200.02.01", "event_type": "test", "summary": "Event 2"},
        ]
        selected, truncated = generator._select_events_for_prompt(events, max_events=5)
        assert selected == events
        assert truncated is False

    def test_deduplication_removes_duplicates(self, generator):
        """Duplicate events (same key) are deduplicated during truncation."""
        # Deduplication only happens when events exceed max_events
        # Create 5 events with 2 duplicates, limit to 3
        events = [
            {"game_date": "2200.01.01", "event_type": "war_started", "summary": "War begun"},
            {"game_date": "2200.01.01", "event_type": "war_started", "summary": "War begun"},
            {"game_date": "2200.02.01", "event_type": "test", "summary": "Event 2"},
            {"game_date": "2200.03.01", "event_type": "test", "summary": "Event 3"},
            {"game_date": "2200.04.01", "event_type": "test", "summary": "Event 4"},
        ]
        # After dedup: 4 unique events. Limit to 3 would truncate.
        selected, truncated = generator._select_events_for_prompt(events, max_events=3)
        assert len(selected) == 3
        # Should only have one war_started event (deduped)
        war_events = [e for e in selected if e["event_type"] == "war_started"]
        assert len(war_events) <= 1
        assert truncated is True

    def test_deduplication_preserves_order(self, generator):
        """Deduplication preserves original event order during truncation."""
        # Create events with duplicates, trigger truncation
        events = [
            {"game_date": "2200.01.01", "event_type": "first", "summary": "First"},
            {"game_date": "2200.02.01", "event_type": "second", "summary": "Second"},
            {"game_date": "2200.01.01", "event_type": "first", "summary": "First"},  # duplicate
            {"game_date": "2200.03.01", "event_type": "third", "summary": "Third"},
            {"game_date": "2200.04.01", "event_type": "fourth", "summary": "Fourth"},
            {"game_date": "2200.05.01", "event_type": "fifth", "summary": "Fifth"},
        ]
        # 5 unique events after dedup, limit to 4 triggers truncation
        selected, truncated = generator._select_events_for_prompt(events, max_events=4)
        assert len(selected) == 4
        # Check order is preserved (dates should be ascending within selected)
        dates = [e["game_date"] for e in selected]
        assert dates == sorted(dates)
        assert truncated is True

    def test_no_deduplication_when_under_limit(self, generator):
        """Events under limit are returned unchanged, even with duplicates."""
        events = [
            {"game_date": "2200.01.01", "event_type": "test", "summary": "Event"},
            {"game_date": "2200.01.01", "event_type": "test", "summary": "Event"},
        ]
        selected, truncated = generator._select_events_for_prompt(events, max_events=10)
        # No deduplication when under limit
        assert len(selected) == 2
        assert truncated is False

    def test_truncation_at_limit(self, generator):
        """Events exceeding max_events are truncated."""
        events = [
            {"game_date": f"2200.{i:02d}.01", "event_type": "test", "summary": f"Event {i}"}
            for i in range(1, 11)
        ]
        selected, truncated = generator._select_events_for_prompt(events, max_events=5)
        assert len(selected) == 5
        assert truncated is True

    def test_notable_events_prioritized(self, generator):
        """Notable events are prioritized over regular events."""
        # Create events: 5 regular, then 3 notable
        regular_events = [
            {"game_date": f"2200.0{i}.01", "event_type": "regular", "summary": f"Regular {i}"}
            for i in range(1, 6)
        ]
        notable_events = [
            {"game_date": f"2200.0{i}.15", "event_type": "war_started", "summary": f"War {i}"}
            for i in range(6, 9)
        ]
        events = regular_events + notable_events

        selected, truncated = generator._select_events_for_prompt(events, max_events=5)
        assert len(selected) == 5
        assert truncated is True
        # All notable events should be included
        notable_in_selected = [e for e in selected if e["event_type"] == "war_started"]
        assert len(notable_in_selected) == 3

    def test_max_events_zero_returns_empty(self, generator):
        """max_events=0 returns empty list with truncated=True if events exist."""
        events = [
            {"game_date": "2200.01.01", "event_type": "test", "summary": "Event"},
        ]
        selected, truncated = generator._select_events_for_prompt(events, max_events=0)
        assert selected == []
        assert truncated is True

    def test_max_events_zero_empty_list_not_truncated(self, generator):
        """max_events=0 with empty list returns truncated=False."""
        selected, truncated = generator._select_events_for_prompt([], max_events=0)
        assert selected == []
        assert truncated is False

    def test_all_notable_event_types_recognized(self, generator):
        """All NOTABLE_EVENT_TYPES are correctly prioritized."""
        # One event per notable type
        notable_events = [
            {"game_date": f"2200.{i:02d}.01", "event_type": etype, "summary": f"{etype} event"}
            for i, etype in enumerate(NOTABLE_EVENT_TYPES, start=1)
        ]
        # Add some regular events at the beginning
        regular_events = [
            {"game_date": "2199.01.01", "event_type": "regular", "summary": f"Regular {i}"}
            for i in range(5)
        ]
        events = regular_events + notable_events

        selected, truncated = generator._select_events_for_prompt(
            events, max_events=len(NOTABLE_EVENT_TYPES)
        )
        assert truncated is True
        # All notable events should be included
        selected_types = {e["event_type"] for e in selected}
        for etype in NOTABLE_EVENT_TYPES:
            assert etype in selected_types


class TestShouldFinalizeChapter:
    """Tests for ChronicleGenerator._should_finalize_chapter method."""

    @pytest.fixture
    def generator(self):
        """Create a ChronicleGenerator with mocked database."""
        mock_db = MagicMock()
        # Default mock returns for snapshot range
        mock_db.get_snapshot_range_for_save.return_value = {
            "first_game_date": "2200.01.01",
            "first_snapshot_id": 1,
        }
        # Default: no events in range
        mock_db.get_events_in_snapshot_range.return_value = []
        return ChronicleGenerator(db=mock_db, api_key="fake-key")

    def test_returns_false_when_current_date_is_none(self, generator):
        """Returns (False, None) when current_date is None."""
        chapters_data = {"chapters": []}
        should_finalize, trigger = generator._should_finalize_chapter(
            save_id="test",
            chapters_data=chapters_data,
            current_date=None,
            current_snapshot_id=100,
        )
        assert should_finalize is False
        assert trigger is None

    def test_returns_false_when_year_cannot_be_parsed(self, generator):
        """Returns (False, None) when current_date year cannot be parsed."""
        chapters_data = {"chapters": []}
        should_finalize, trigger = generator._should_finalize_chapter(
            save_id="test",
            chapters_data=chapters_data,
            current_date="invalid-date",
            current_snapshot_id=100,
        )
        assert should_finalize is False
        assert trigger is None

    def test_time_threshold_triggers_finalization(self, generator):
        """Returns (True, 'time_threshold') when 50+ years have elapsed."""
        chapters_data = {"chapters": []}

        should_finalize, trigger = generator._should_finalize_chapter(
            save_id="test",
            chapters_data=chapters_data,
            current_date="2250.01.01",
            current_snapshot_id=100,
        )
        assert should_finalize is True
        assert trigger == "time_threshold"

    def test_time_threshold_49_years_no_finalization(self, generator):
        """Returns (False, None) when only 49 years have elapsed."""
        chapters_data = {"chapters": []}

        should_finalize, trigger = generator._should_finalize_chapter(
            save_id="test",
            chapters_data=chapters_data,
            current_date="2249.01.01",
            current_snapshot_id=100,
        )
        assert should_finalize is False
        assert trigger is None

    def test_era_ending_event_triggers_with_cooldown(self, generator):
        """Returns (True, event_type) for era-ending event with 5+ year cooldown."""
        chapters_data = {"chapters": []}

        generator.db.get_events_in_snapshot_range.return_value = [
            {"event_type": "war_ended", "game_date": "2205.01.01", "summary": "War ended"}
        ]

        should_finalize, trigger = generator._should_finalize_chapter(
            save_id="test",
            chapters_data=chapters_data,
            current_date="2210.01.01",
            current_snapshot_id=100,
        )
        assert should_finalize is True
        assert trigger == "war_ended"

    def test_era_ending_event_blocked_within_cooldown(self, generator):
        """Returns (False, None) for era-ending event within 5 year cooldown."""
        chapters_data = {"chapters": []}

        generator.db.get_events_in_snapshot_range.return_value = [
            {"event_type": "war_ended", "game_date": "2206.01.01", "summary": "War ended"}
        ]

        should_finalize, trigger = generator._should_finalize_chapter(
            save_id="test",
            chapters_data=chapters_data,
            current_date="2210.01.01",
            current_snapshot_id=100,
        )
        assert should_finalize is False
        assert trigger is None

    def test_continues_from_last_chapter_end_date(self, generator):
        """Uses last chapter's end_date as era start when chapters exist."""
        chapters_data = {
            "chapters": [
                {
                    "number": 1,
                    "end_date": "2250.01.01",
                    "end_snapshot_id": 50,
                }
            ]
        }

        should_finalize, trigger = generator._should_finalize_chapter(
            save_id="test",
            chapters_data=chapters_data,
            current_date="2300.01.01",
            current_snapshot_id=100,
        )
        assert should_finalize is True
        assert trigger == "time_threshold"

    def test_all_era_ending_events_recognized(self, generator):
        """All ERA_ENDING_EVENTS are correctly recognized as triggers."""
        chapters_data = {"chapters": []}

        for event_type in ERA_ENDING_EVENTS:
            generator.db.get_events_in_snapshot_range.return_value = [
                {
                    "event_type": event_type,
                    "game_date": "2205.01.01",
                    "summary": f"{event_type} event",
                }
            ]

            should_finalize, trigger = generator._should_finalize_chapter(
                save_id="test",
                chapters_data=chapters_data,
                current_date="2210.01.01",
                current_snapshot_id=100,
            )
            assert should_finalize is True, f"Failed for event_type: {event_type}"
            assert trigger == event_type

    def test_non_era_ending_event_ignored(self, generator):
        """Non-era-ending events do not trigger finalization."""
        chapters_data = {"chapters": []}

        generator.db.get_events_in_snapshot_range.return_value = [
            {"event_type": "tech_completed", "game_date": "2205.01.01", "summary": "Tech completed"}
        ]

        should_finalize, trigger = generator._should_finalize_chapter(
            save_id="test",
            chapters_data=chapters_data,
            current_date="2210.01.01",
            current_snapshot_id=100,
        )
        assert should_finalize is False
        assert trigger is None

    def test_uses_current_era_start_date_when_no_chapters(self, generator):
        """Uses current_era_start_date from chapters_data when no chapters exist."""
        chapters_data = {
            "chapters": [],
            "current_era_start_date": "2220.01.01",
            "current_era_start_snapshot_id": 20,
        }

        should_finalize, trigger = generator._should_finalize_chapter(
            save_id="test",
            chapters_data=chapters_data,
            current_date="2270.01.01",
            current_snapshot_id=100,
        )
        assert should_finalize is True
        assert trigger == "time_threshold"

    def test_first_chapter_uses_snapshot_range(self, generator):
        """First chapter uses snapshot range when no era start date set."""
        generator.db.get_snapshot_range_for_save.return_value = {
            "first_game_date": "2205.01.01",
            "first_snapshot_id": 5,
        }

        chapters_data = {"chapters": []}

        should_finalize, trigger = generator._should_finalize_chapter(
            save_id="test",
            chapters_data=chapters_data,
            current_date="2255.01.01",
            current_snapshot_id=100,
        )
        assert should_finalize is True
        assert trigger == "time_threshold"

    def test_time_threshold_takes_priority_over_era_events(self, generator):
        """Time threshold can trigger even if era events exist within cooldown."""
        chapters_data = {"chapters": []}

        generator.db.get_events_in_snapshot_range.return_value = [
            {"event_type": "war_ended", "game_date": "2248.01.01", "summary": "War ended"}
        ]

        should_finalize, trigger = generator._should_finalize_chapter(
            save_id="test",
            chapters_data=chapters_data,
            current_date="2250.01.01",
            current_snapshot_id=100,
        )
        assert should_finalize is True
        assert trigger == "time_threshold"

    def test_does_not_finalize_without_new_snapshot_progress(self, generator):
        """No finalization when snapshot id has not advanced since era start."""
        chapters_data = {
            "chapters": [],
            "current_era_start_date": "2200.01.01",
            "current_era_start_snapshot_id": 100,
        }

        should_finalize, trigger = generator._should_finalize_chapter(
            save_id="test",
            chapters_data=chapters_data,
            current_date="2300.01.01",
            current_snapshot_id=100,
        )
        assert should_finalize is False
        assert trigger is None


class TestFinalizeChapter:
    """Tests for ChronicleGenerator._finalize_chapter behavior."""

    @pytest.fixture
    def generator(self):
        """Create a ChronicleGenerator with mocked database."""
        mock_db = MagicMock()
        mock_db.get_snapshot_range_for_save.return_value = {
            "first_game_date": "2200.01.01",
            "first_snapshot_id": 1,
            "last_snapshot_id": 3,
            "last_game_date": "2300.01.01",
        }
        mock_db.get_latest_snapshot_at_or_before.return_value = None
        mock_db.get_events_in_snapshot_range.return_value = [
            {"event_type": "war_started", "game_date": "2300.01.01", "summary": "War begun"}
        ]
        generator = ChronicleGenerator(db=mock_db, api_key="fake-key")
        generator._generate_chapter_content = MagicMock(  # type: ignore[method-assign]
            return_value={
                "title": "The Turning Point",
                "epigraph": "Steel before stars.",
                "sections": [{"type": "prose", "text": "History changed.", "attribution": ""}],
                "narrative": "History changed.",
                "summary": "A major shift occurred.",
            }
        )
        return generator

    def test_time_threshold_falls_back_to_latest_snapshot_when_sparse(self, generator):
        """Sparse snapshots should finalize at the latest available snapshot."""
        chapters_data = {"chapters": []}

        finalized = generator._finalize_chapter(  # type: ignore[attr-defined]
            save_id="save-1",
            chapters_data=chapters_data,
            briefing={},
            trigger="time_threshold",
        )

        assert finalized is True
        assert len(chapters_data["chapters"]) == 1
        chapter = chapters_data["chapters"][0]
        assert chapter["end_snapshot_id"] == 3
        assert chapter["end_date"] == "2300.01.01"
        assert chapters_data["current_era_start_snapshot_id"] == 3
        assert chapters_data["current_era_start_date"] == "2300.01.01"

    def test_skips_finalization_when_snapshot_range_has_not_advanced(self, generator):
        """Chapter finalization should be skipped when end snapshot is not newer."""
        chapters_data = {
            "chapters": [
                {
                    "number": 1,
                    "title": "Prior Chapter",
                    "start_date": "2200.01.01",
                    "end_date": "2300.01.01",
                    "start_snapshot_id": 1,
                    "end_snapshot_id": 3,
                    "epigraph": "",
                    "sections": [],
                    "narrative": "Prior narrative.",
                    "summary": "Prior summary.",
                    "is_finalized": True,
                    "context_stale": False,
                }
            ],
            "current_era_start_date": "2300.01.01",
            "current_era_start_snapshot_id": 3,
        }

        finalized = generator._finalize_chapter(  # type: ignore[attr-defined]
            save_id="save-1",
            chapters_data=chapters_data,
            briefing={},
            trigger="time_threshold",
        )

        assert finalized is False
        assert len(chapters_data["chapters"]) == 1


class TestGenerateChronicleChapterOnly:
    """Tests for chapter-only chronicle generation mode."""

    @pytest.fixture
    def generator(self):
        """Create a ChronicleGenerator with mocked database."""
        mock_db = MagicMock()
        mock_db.get_save_id_for_session.return_value = "save-1"
        mock_db.get_chronicle_custom_instructions.return_value = None
        mock_db.get_snapshot_range_for_save.return_value = {
            "snapshot_count": 2,
            "first_game_date": "2200.01.01",
            "first_snapshot_id": 1,
            "last_game_date": "2205.01.01",
            "last_snapshot_id": 2,
        }
        mock_db.get_latest_session_briefing_json.return_value = "{}"
        mock_db.get_all_events_by_save_id.return_value = [
            {"event_type": "war_started", "summary": "War begun", "game_date": "2205.01.01"}
        ]
        mock_db.upsert_chronicle_by_save_id.return_value = None

        cached_chapters = {
            "format_version": 1,
            "chapters": [],
            "current_era_start_date": "2200.01.01",
            "current_era_start_snapshot_id": 1,
            "current_era_cache": {
                "start_date": "2200.01.01",
                "start_snapshot_id": 1,
                "last_snapshot_id": 1,
                "generated_at": "2026-01-01T00:00:00Z",
                "current_era": {
                    "start_date": "2200.01.01",
                    "narrative": "Existing current era narrative.",
                    "events_covered": 4,
                    "sections": [{"type": "prose", "text": "Existing.", "attribution": ""}],
                },
            },
        }
        mock_db.get_chronicle_by_save_id.return_value = {
            "chapters_json": json.dumps(cached_chapters),
            "event_count": 4,
            "snapshot_count": 2,
        }

        return ChronicleGenerator(db=mock_db, api_key="fake-key")

    def test_chapter_only_skips_current_era_generation(self, generator):
        """Chapter-only mode should not call current-era Gemini generation."""
        generator._should_finalize_chapter = MagicMock(return_value=(False, None))  # type: ignore[method-assign]
        generator._count_pending_chapters = MagicMock(return_value=0)  # type: ignore[method-assign]
        generator._generate_current_era = MagicMock(  # type: ignore[method-assign]
            return_value={
                "start_date": "2200.01.01",
                "narrative": "Generated current era",
                "events_covered": 5,
                "sections": [],
            }
        )

        result = generator.generate_chronicle("session-1", chapter_only=True)

        generator._generate_current_era.assert_not_called()  # type: ignore[attr-defined]
        assert result["current_era"] is not None
        assert result["current_era"]["narrative"] == "Existing current era narrative."
        assert result["cached"] is True

    def test_chapter_only_keeps_existing_current_era_cache_after_finalization(self, generator):
        """Chapter-only finalization keeps previous current-era text until visible refresh."""

        def fake_should_finalize(*args, **kwargs):
            if not hasattr(fake_should_finalize, "called"):
                fake_should_finalize.called = True  # type: ignore[attr-defined]
                return True, "time_threshold"
            return False, None

        def fake_finalize(*args, **kwargs):
            chapters_data = kwargs["chapters_data"]
            chapters_data["chapters"].append(
                {
                    "number": 1,
                    "title": "The First Turning",
                    "start_date": "2200.01.01",
                    "end_date": "2250.01.01",
                    "start_snapshot_id": 1,
                    "end_snapshot_id": 2,
                    "epigraph": "",
                    "sections": [{"type": "prose", "text": "A chapter closes.", "attribution": ""}],
                    "narrative": "A chapter closes.",
                    "summary": "An era ended.",
                    "is_finalized": True,
                    "context_stale": False,
                }
            )
            chapters_data["current_era_start_date"] = "2250.01.01"
            chapters_data["current_era_start_snapshot_id"] = 2
            return True

        generator._should_finalize_chapter = MagicMock(side_effect=fake_should_finalize)  # type: ignore[method-assign]
        generator._finalize_chapter = MagicMock(side_effect=fake_finalize)  # type: ignore[method-assign]
        generator._count_pending_chapters = MagicMock(return_value=0)  # type: ignore[method-assign]
        generator._generate_current_era = MagicMock(return_value=None)  # type: ignore[method-assign]

        result = generator.generate_chronicle("session-1", chapter_only=True)

        generator._generate_current_era.assert_not_called()  # type: ignore[attr-defined]
        assert result["current_era"] is not None
        assert result["current_era"]["narrative"] == "Existing current era narrative."
        assert result["chapters"][0]["title"] == "The First Turning"

        upsert_kwargs = generator.db.upsert_chronicle_by_save_id.call_args.kwargs
        stored = json.loads(upsert_kwargs["chapters_json"])
        assert "current_era_cache" in stored


class TestSectionsToText:
    """Tests for _sections_to_text helper."""

    def test_prose_only(self):
        """Prose sections produce plain text paragraphs."""
        sections = [
            {"type": "prose", "text": "The empire rose from the ashes.", "attribution": ""},
            {"type": "prose", "text": "A new age had begun.", "attribution": ""},
        ]
        result = _sections_to_text(sections)
        assert "The empire rose from the ashes." in result
        assert "A new age had begun." in result

    def test_quote_with_attribution(self):
        """Quote sections produce blockquote with attribution."""
        sections = [
            {"type": "quote", "text": "We shall not yield.", "attribution": "Emperor Kaal"},
        ]
        result = _sections_to_text(sections)
        assert '> "We shall not yield."' in result
        assert "> \u2014 Emperor Kaal" in result

    def test_quote_without_attribution(self):
        """Quote sections without attribution omit the attribution line."""
        sections = [
            {"type": "quote", "text": "Stars guide us.", "attribution": ""},
        ]
        result = _sections_to_text(sections)
        assert '> "Stars guide us."' in result
        assert "\u2014" not in result

    def test_declaration(self):
        """Declaration sections produce centered uppercase blocks."""
        sections = [
            {"type": "declaration", "text": "THE COMMONWEALTH SHALL NOT YIELD", "attribution": ""},
        ]
        result = _sections_to_text(sections)
        assert "=== THE COMMONWEALTH SHALL NOT YIELD ===" in result

    def test_with_epigraph(self):
        """Epigraph is prepended as a quoted line."""
        sections = [
            {"type": "prose", "text": "History unfolds.", "attribution": ""},
        ]
        result = _sections_to_text(sections, epigraph="From dust, empire.")
        assert '"From dust, empire."' in result
        assert "History unfolds." in result

    def test_empty_sections(self):
        """Empty sections list produces empty string."""
        result = _sections_to_text([])
        assert result == ""
