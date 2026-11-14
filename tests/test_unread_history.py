"""A part of the history that could not be read is not a part that is empty.

The worker has always tolerated a failure while building the history signals. It
used to store the snapshot without them, and the next comparison then recorded
every war as ended and every leader as removed, and all of them back again at
the following save.
"""

from __future__ import annotations

import json
from contextlib import closing

import pytest

from backend.core import history, signals
from backend.core.database import GameDatabase
from backend.core.events import carry_unread_history, compute_events
from backend.core.snapshot_reader import HISTORY_SIGNALS
from tests.report_regressions._synthetic import (
    country,
    ingest_synthetic_save,
    persist_snapshot,
    synthetic_meta,
    system,
)

WAR = {
    "0": {
        "name": {"key": "Synthetic War", "literal": "yes"},
        "start_date": "2290.01.01",
        "attackers": [{"country": "15"}],
        "defenders": [{"country": "0"}],
        "attacker_war_goal": {"type": "wg_conquest"},
        "battles": [],
    }
}


def _sections(*, at_war: bool = True) -> dict:
    sections = {
        "player": [{"name": "Reporter", "country": "0"}],
        "country": {"0": country("Reporter Republic"), "15": country("Aggressor Imperium")},
        "galactic_object": {"8": system("Home Reach"), "9": system("Enemy Prime")},
    }
    if at_war:
        sections["war"] = WAR
    return sections


def _fail(*args, **kwargs):
    raise KeyError("injected")


def _ingest(monkeypatch, tmp_path, date, *, at_war=True, broken=None):
    """One save of the campaign; ``broken`` is ``(module, name)`` of a step that fails."""
    with monkeypatch.context() as patch:
        if broken:
            patch.setattr(*broken, _fail)
        return ingest_synthetic_save(
            patch,
            tmp_path,
            _sections(at_war=at_war),
            meta=synthetic_meta(date=date),
            filename=f"{date}.sav",
        )


def _recorded_events(tmp_path, payloads) -> list[tuple[str, str]]:
    with closing(GameDatabase(tmp_path / "history.db")) as db:
        session_id = None
        for payload in payloads:
            _, _, session_id = persist_snapshot(db, payload)
        events = db.get_recent_events(session_id=session_id, limit=50)
    return sorted((event["game_date"], event["event_type"]) for event in events)


WAR_SIGNAL = (signals, "_extract_war_signals")


def test_a_signal_that_could_not_be_built_is_named_and_the_rest_are_kept(monkeypatch, tmp_path):
    payload = _ingest(monkeypatch, tmp_path, "2300.02.01", broken=WAR_SIGNAL)

    stored = json.loads(payload["briefing_json"])["history"]
    assert stored["unread"] == ["wars"]
    assert "wars" not in stored
    assert "diplomacy" in stored and "leaders" in stored


def test_an_unchanged_campaign_records_nothing_when_one_save_could_not_read_its_wars(
    monkeypatch, tmp_path
):
    saves = [
        _ingest(monkeypatch, tmp_path, "2300.01.01"),
        _ingest(monkeypatch, tmp_path, "2300.02.01", broken=WAR_SIGNAL),
        _ingest(monkeypatch, tmp_path, "2300.03.01"),
    ]

    assert _recorded_events(tmp_path, saves) == []


def test_a_war_that_ended_while_unread_is_recorded_once_when_it_is_read_again(
    monkeypatch, tmp_path
):
    saves = [
        _ingest(monkeypatch, tmp_path, "2300.01.01"),
        _ingest(monkeypatch, tmp_path, "2300.02.01", at_war=False, broken=WAR_SIGNAL),
        _ingest(monkeypatch, tmp_path, "2300.03.01", at_war=False, broken=WAR_SIGNAL),
        _ingest(monkeypatch, tmp_path, "2300.04.01", at_war=False),
    ]

    assert _recorded_events(tmp_path, saves) == [("2300.04.01", "war_ended")]


def test_a_campaign_whose_first_save_could_not_read_its_wars_starts_no_war_later(
    monkeypatch, tmp_path
):
    saves = [
        _ingest(monkeypatch, tmp_path, "2300.01.01", broken=WAR_SIGNAL),
        _ingest(monkeypatch, tmp_path, "2300.02.01"),
        _ingest(monkeypatch, tmp_path, "2300.03.01", at_war=False),
    ]

    assert _recorded_events(tmp_path, saves) == [("2300.03.01", "war_ended")]


def test_a_history_that_could_not_be_built_at_all_records_nothing(monkeypatch, tmp_path):
    broken = (history, "build_history_enrichment")
    failed = _ingest(monkeypatch, tmp_path, "2300.02.01", broken=broken)
    saves = [
        _ingest(monkeypatch, tmp_path, "2300.01.01"),
        failed,
        _ingest(monkeypatch, tmp_path, "2300.03.01"),
    ]

    assert json.loads(failed["briefing_json"])["history"] == {"unread": sorted(HISTORY_SIGNALS)}
    assert _recorded_events(tmp_path, saves) == []


def _snapshot(wars: dict[str, str] | None, *, unread: list[str] | None = None) -> dict:
    stored: dict = {"leaders": {"leaders": []}}
    if wars is not None:
        stored["wars"] = {"count": len(wars), "wars": list(wars.values()), "by_id": wars}
    if unread:
        stored["unread"] = unread
    return {"meta": {"date": "2300.01.01", "player_id": 0}, "history": stored}


def _event_types(prev: dict, curr: dict) -> list[str]:
    events = compute_events(prev=prev, curr=curr, from_snapshot_id=1, to_snapshot_id=2)
    return [event.event_type for event in events]


def test_snapshots_that_read_everything_are_compared_as_they_are():
    prev, curr = _snapshot({"7": "Border War"}), _snapshot({})

    assert carry_unread_history(prev, curr) == (prev, curr)
    assert carry_unread_history(prev, curr)[1] is curr
    assert _event_types(prev, curr) == ["war_ended"]


def test_the_stored_snapshot_keeps_the_last_reading_and_is_no_longer_unread():
    prev, curr = _snapshot({"7": "Border War"}), _snapshot(None, unread=["wars"])

    compared_prev, stored = carry_unread_history(prev, curr)

    assert _event_types(compared_prev, stored) == []
    assert stored["history"]["wars"] == prev["history"]["wars"]
    assert "unread" not in stored["history"]
    assert "wars" not in curr["history"], "the snapshot passed in is not changed"


def test_a_signal_neither_snapshot_read_stays_unread():
    prev = _snapshot(None, unread=["wars"])
    curr = _snapshot(None, unread=["wars"])

    compared_prev, stored = carry_unread_history(prev, curr)

    assert _event_types(compared_prev, stored) == []
    assert stored["history"]["unread"] == ["wars"]


@pytest.mark.parametrize("legacy_history", [None, {}])
def test_a_snapshot_stored_without_any_history_gives_nothing_to_carry(legacy_history):
    prev = {"meta": {"date": "2299.12.01", "player_id": 0}}
    if legacy_history is not None:
        prev["history"] = legacy_history
    curr = _snapshot(None, unread=["wars"])

    compared_prev, stored = carry_unread_history(prev, curr)

    assert stored["history"]["unread"] == ["wars"]
    # The next save, which reads its wars, starts none.
    assert _event_types(stored, _snapshot({"7": "Border War"})) == ["war_started"]
    compared_prev, _ = carry_unread_history(stored, _snapshot({"7": "Border War"}))
    assert _event_types(compared_prev, _snapshot({"7": "Border War"})) == []
