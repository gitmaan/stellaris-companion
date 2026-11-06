"""Megastructure-status misreadings reported by players (#12)."""

from __future__ import annotations

from contextlib import closing

from backend.core.database import GameDatabase

from ._synthetic import (
    advisor_request,
    country,
    ingest_synthetic_save,
    persist_snapshot,
    synthetic_meta,
)

NO_BUILD_QUEUE = "4294967295"


def _archive_save(*, build_queue: str) -> dict:
    return {
        "player": [{"name": "Reporter", "country": "0"}],
        "country": {"0": country("Archivist Union")},
        "megastructures": {
            "3": {
                "type": "grand_archive_0",
                "owner": "0",
                "planet": "4294967295",
                "build_queue": build_queue,
            }
        },
    }


def test_issue_12_completed_grand_archive_is_complete_for_advisor_and_history(
    monkeypatch, tmp_path
):
    """https://github.com/gitmaan/stellaris-companion/issues/12

    The Grand Archive's only type is ``grand_archive_0``, so the ``_0`` suffix
    never changes when it finishes. Status must come from live construction
    state (the build queue), and history must record the completion.
    """
    building = ingest_synthetic_save(
        monkeypatch,
        tmp_path,
        _archive_save(build_queue="17753"),
        meta=synthetic_meta(date="2300.01.01"),
        filename="building.sav",
    )
    completed = ingest_synthetic_save(
        monkeypatch,
        tmp_path,
        _archive_save(build_queue=NO_BUILD_QUEUE),
        meta=synthetic_meta(date="2301.01.01"),
        filename="completed.sav",
    )

    _, _, model_briefing = advisor_request(monkeypatch, completed, "What should I build next?")
    [archive] = model_briefing["military"]["megastructures"]["megastructures"]
    assert archive["display_type"] == "grand_archive"
    assert archive["status"] == "complete"

    with closing(GameDatabase(tmp_path / "history.db")) as db:
        inserted, first_id, session_id = persist_snapshot(db, building)
        assert inserted
        inserted, second_id, same_session = persist_snapshot(db, completed)
        assert inserted and same_session == session_id
        events = db.get_recent_events(session_id=session_id, limit=50)

    event_types = [event["event_type"] for event in events]
    assert "megastructure_construction_completed" in event_types
    assert "megastructure_started" not in event_types
