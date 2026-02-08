"""Tests for snapshot-range event retrieval in GameDatabase."""

from pathlib import Path

from backend.core.database import GameDatabase


def _create_session_with_snapshots(db: GameDatabase, *, save_id: str) -> tuple[str, list[int]]:
    session_id = db.get_or_create_active_session(
        save_id=save_id,
        save_path=f"/tmp/{save_id}.sav",
        empire_name="Test Empire",
        last_game_date="2200.01.01",
    )

    snapshot_ids: list[int] = []
    for idx, game_date in enumerate(("2200.01.01", "2200.02.01", "2200.03.01"), start=1):
        snapshot_id = db.insert_snapshot(
            session_id=session_id,
            game_date=game_date,
            save_hash=f"{save_id}-hash-{idx}",
            military_power=None,
            colony_count=None,
            wars_count=None,
            energy_net=None,
            alloys_net=None,
            full_briefing_json="{}",
            event_state_json="{}",
        )
        snapshot_ids.append(snapshot_id)

    return session_id, snapshot_ids


def test_get_events_in_snapshot_range_uses_to_snapshot_id_metadata(tmp_path: Path) -> None:
    """Events should be filtered by their linked to_snapshot_id, not event row id."""
    db = GameDatabase(db_path=tmp_path / "range.db")
    session_id, snapshot_ids = _create_session_with_snapshots(db, save_id="save-a")

    db.insert_events(
        session_id=session_id,
        captured_at=300,
        game_date="2200.03.01",
        events=[
            {
                "event_type": "war_started",
                "summary": "War started",
                "data": {
                    "from_snapshot_id": snapshot_ids[1],
                    "to_snapshot_id": snapshot_ids[2],
                },
            }
        ],
    )

    rows = db.get_events_in_snapshot_range(
        save_id="save-a",
        from_snapshot_id=snapshot_ids[1],
        to_snapshot_id=snapshot_ids[2],
    )

    assert len(rows) == 1
    assert rows[0]["event_type"] == "war_started"


def test_get_events_in_snapshot_range_falls_back_to_captured_at_when_missing_snapshot_metadata(
    tmp_path: Path,
) -> None:
    """Older rows without to_snapshot_id still honor snapshot bounds via captured_at."""
    db = GameDatabase(db_path=tmp_path / "range_fallback.db")
    session_id, snapshot_ids = _create_session_with_snapshots(db, save_id="save-b")

    # Stabilize snapshot captured_at values for deterministic range checks.
    db.execute("UPDATE snapshots SET captured_at = 100 WHERE id = ?", (snapshot_ids[0],))
    db.execute("UPDATE snapshots SET captured_at = 200 WHERE id = ?", (snapshot_ids[1],))
    db.execute("UPDATE snapshots SET captured_at = 300 WHERE id = ?", (snapshot_ids[2],))

    db.insert_events(
        session_id=session_id,
        captured_at=250,
        game_date="2200.03.01",
        events=[
            {
                "event_type": "legacy_event",
                "summary": "Missing snapshot linkage",
                "data": {},
            }
        ],
    )
    db.insert_events(
        session_id=session_id,
        captured_at=150,
        game_date="2200.02.01",
        events=[
            {
                "event_type": "legacy_event_early",
                "summary": "Outside lower bound",
                "data": {},
            }
        ],
    )

    rows = db.get_events_in_snapshot_range(
        save_id="save-b",
        from_snapshot_id=snapshot_ids[1],
        to_snapshot_id=snapshot_ids[2],
    )
    event_types = {row["event_type"] for row in rows}

    assert "legacy_event" in event_types
    assert "legacy_event_early" not in event_types
