import json
from pathlib import Path

from backend.core.database import GameDatabase
from backend.core.history import record_snapshot_from_briefing
from backend.core.utils import compute_save_hash_from_briefing


def _briefing_for_hash(
    *,
    date: str = "2227.07.01",
    military_power: int = 1000,
    colony_count: int = 5,
    energy: float = 10.0,
    alloys: float = 5.0,
    tech_count: int = 20,
) -> dict:
    return {
        "meta": {
            "date": date,
            "empire_name": "Kilik Cooperative",
            "campaign_id": "campaign-1",
            "player_id": 0,
        },
        "military": {
            "military_power": military_power,
            "fleet_count": 4,
            "military_fleets": 4,
        },
        "territory": {"colonies": {"total_count": colony_count}},
        "economy": {"net_monthly": {"energy": energy, "alloys": alloys}},
        "technology": {"tech_count": tech_count},
    }


def test_compute_save_hash_changes_when_same_date_state_changes() -> None:
    base = _briefing_for_hash()
    changed = _briefing_for_hash(colony_count=6)

    base_hash = compute_save_hash_from_briefing(base)
    changed_hash = compute_save_hash_from_briefing(changed)

    assert base_hash is not None
    assert changed_hash is not None
    assert base_hash != changed_hash


def test_compute_save_hash_low_collision_under_same_date_variation() -> None:
    hashes: set[str] = set()
    sample_count = 200

    for i in range(sample_count):
        briefing = _briefing_for_hash(
            military_power=1000 + (i % 7),
            colony_count=5 + (i % 11),
            energy=10.0 + (i * 0.5),
            alloys=5.0 + (i * 0.25),
            tech_count=20 + (i % 13),
        )
        h = compute_save_hash_from_briefing(briefing)
        assert h is not None
        hashes.add(h)

    # Practical stress check: for this varied set, collisions should be absent.
    assert len(hashes) == sample_count


def test_dedupe_skip_still_updates_session_last_game_date(tmp_path: Path) -> None:
    db = GameDatabase(db_path=tmp_path / "dedupe.db")
    session_id = db.get_or_create_active_session(
        save_id="save-1",
        save_path="/tmp/save-1.sav",
        empire_name="Kilik Cooperative",
        last_game_date="2200.01.01",
    )

    inserted, snapshot_id = db.insert_snapshot_if_new(
        session_id=session_id,
        game_date="2200.01.01",
        save_hash="same-hash",
        military_power=1000,
        colony_count=5,
        wars_count=None,
        energy_net=10.0,
        alloys_net=5.0,
        full_briefing_json="{}",
        event_state_json="{}",
    )
    assert inserted is True
    assert snapshot_id is not None

    inserted2, snapshot_id2 = db.insert_snapshot_if_new(
        session_id=session_id,
        game_date="2200.02.01",
        save_hash="same-hash",
        military_power=1000,
        colony_count=6,
        wars_count=None,
        energy_net=11.0,
        alloys_net=6.0,
        full_briefing_json="{}",
        event_state_json="{}",
    )

    assert inserted2 is False
    assert snapshot_id2 is None

    session = db.get_session_by_id(session_id)
    assert session is not None
    assert session["last_game_date"] == "2200.02.01"
    assert session["snapshot_count"] == 1


def test_dedupe_skip_refreshes_latest_briefing_after_extractor_change(tmp_path: Path) -> None:
    db = GameDatabase(db_path=tmp_path / "briefing-refresh.db")
    briefing = _briefing_for_hash()
    briefing["endgame"] = {"lgate": {"lgate_opened": True}}

    inserted, _, session_id = record_snapshot_from_briefing(
        db=db,
        save_path=Path("/tmp/save-1.sav"),
        save_hash="same-save",
        briefing=briefing,
    )
    assert inserted is True

    corrected = json.loads(json.dumps(briefing))
    corrected["endgame"]["lgate"]["lgate_opened"] = False
    inserted_again, snapshot_id, same_session_id = record_snapshot_from_briefing(
        db=db,
        save_path=Path("/tmp/save-1.sav"),
        save_hash="same-save",
        briefing=corrected,
    )

    assert inserted_again is False
    assert snapshot_id is None
    assert same_session_id == session_id
    latest = db.get_latest_session_briefing_json(session_id=session_id)
    assert latest is not None
    assert json.loads(latest)["endgame"]["lgate"]["lgate_opened"] is False
    assert db.get_snapshot_count(session_id) == 1
