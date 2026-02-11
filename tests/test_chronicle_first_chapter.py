from unittest.mock import MagicMock

import pytest

from backend.core.chronicle import ChronicleGenerator


@pytest.fixture
def generator():
    mock_db = MagicMock()
    return ChronicleGenerator(db=mock_db, api_key="fake-key")


def _base_chapters_data():
    return {
        "format_version": 1,
        "chapters": [],
        "current_era_start_date": None,
        "current_era_start_snapshot_id": None,
    }


def test_first_chapter_does_not_finalize_too_early_without_events(generator):
    generator.db.get_snapshot_range_for_save.return_value = {
        "first_game_date": "2200.01.01",
        "first_snapshot_id": 1,
    }
    generator.db.get_events_in_snapshot_range.return_value = []

    should, trigger = generator._should_finalize_chapter(
        save_id="save-1",
        chapters_data=_base_chapters_data(),
        current_date="2202.01.01",
        current_snapshot_id=5,
    )
    assert should is False
    assert trigger is None


def test_first_chapter_finalizes_on_milestone_after_min_years(generator):
    generator.db.get_snapshot_range_for_save.return_value = {
        "first_game_date": "2200.01.01",
        "first_snapshot_id": 1,
    }
    generator.db.get_events_in_snapshot_range.return_value = [
        {"game_date": "2201.01.01", "event_type": "military_power_change", "summary": "Navy grows"},
        {"game_date": "2201.06.01", "event_type": "colony_count_change", "summary": "New colony"},
        {"game_date": "2202.03.01", "event_type": "first_contact", "summary": "We are not alone"},
        {
            "game_date": "2202.04.01",
            "event_type": "military_power_change",
            "summary": "Fleet refit",
        },
    ]

    should, trigger = generator._should_finalize_chapter(
        save_id="save-1",
        chapters_data=_base_chapters_data(),
        current_date="2202.08.01",
        current_snapshot_id=8,
    )
    assert should is True
    # A milestone event type should be used as the trigger.
    assert trigger in {"first_contact", "colony_count_change"}


def test_first_chapter_finalizes_on_short_time_threshold_when_enough_events(generator):
    generator.db.get_snapshot_range_for_save.return_value = {
        "first_game_date": "2200.01.01",
        "first_snapshot_id": 1,
    }
    generator.db.get_events_in_snapshot_range.return_value = [
        {"game_date": "2201.01.01", "event_type": "military_power_change", "summary": "Navy grows"},
        {
            "game_date": "2201.02.01",
            "event_type": "military_power_change",
            "summary": "Navy grows again",
        },
        {"game_date": "2201.03.01", "event_type": "colony_count_change", "summary": "New colony"},
        {"game_date": "2202.01.01", "event_type": "military_power_change", "summary": "More ships"},
        {"game_date": "2202.02.01", "event_type": "military_power_change", "summary": "More ships"},
        {"game_date": "2203.01.01", "event_type": "military_power_change", "summary": "More ships"},
        {"game_date": "2204.01.01", "event_type": "military_power_change", "summary": "More ships"},
        {"game_date": "2205.01.01", "event_type": "military_power_change", "summary": "More ships"},
    ]

    should, trigger = generator._should_finalize_chapter(
        save_id="save-1",
        chapters_data=_base_chapters_data(),
        current_date="2205.01.01",
        current_snapshot_id=12,
    )
    assert should is True
    assert trigger == "time_threshold"
