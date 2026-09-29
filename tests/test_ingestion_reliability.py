"""Campaign and persistence regressions using real state and SQLite, without an LLM."""

import json
import zipfile
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import backend.api.server as server
import backend.core.ingestion as ingestion_module
from backend.core.companion import Companion
from backend.core.database import GameDatabase
from backend.core.ingestion import IngestionManager


@pytest.fixture
def campaign_state(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    monkeypatch.setenv(server.ENV_API_TOKEN, "test-token")
    db = GameDatabase(tmp_path / "history.db")
    companion = Companion(save_path=None, auto_precompute=False)
    manager = IngestionManager(companion=companion, db=db)

    def ingest(campaign, date="2200.01.01", target=manager):
        path = tmp_path / f"{campaign}-{date}.sav"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("meta", f'name="Same Empire"\ndate="{date}"')
        meta = {"campaign_id": campaign, "player_id": 0, "empire_name": "Same Empire", "date": date}
        briefing = {"meta": meta, "identity": {"name": "Same Empire"}, "situation": {"date": date}}
        payload = {
            "meta": meta,
            "briefing_json": json.dumps(briefing),
            "game_date": date,
            "identity": briefing["identity"],
            "situation": briefing["situation"],
            "save_hash": f"{campaign}-{date}",
        }
        target.notify_save(path)
        # Run exactly one iteration of the real coordinator; no lingering daemon threads.
        with (
            patch.object(target, "_wait_for_stable_save", return_value=True),
            patch.object(target, "_run_worker_tier", return_value=payload),
            patch.object(target._wakeup, "wait", side_effect=[True, StopIteration]),
            pytest.raises(StopIteration),
        ):
            target._run()
        return target.get_health_payload()["save_id"]

    app = server.create_app()
    app.state.companion = companion
    app.state.ingestion = manager
    app.state.db = db
    with TestClient(app) as client:
        yield db, companion, manager, ingest, client
    db.close()


def test_campaign_instructions_survive_switches_autosaves_and_restart(campaign_state):
    db, companion, manager, ingest, client = campaign_state
    headers = {"Authorization": "Bearer test-token"}
    a_id = ingest("A")
    assert client.post(
        "/api/session-advisor-custom", headers=headers, json={"custom_instructions": "A_ONLY_STYLE"}
    ).json()["persisted"]
    b_id = ingest("B")
    assert a_id != b_id
    assert companion.custom_instructions is None
    assert client.post(
        "/api/session-advisor-custom", headers=headers, json={"custom_instructions": "B_ONLY_STYLE"}
    ).json()["persisted"]
    assert ingest("B", "2201.01.01") == b_id
    assert companion.custom_instructions == "B_ONLY_STYLE"
    assert ingest("A") == a_id
    assert companion.custom_instructions == "A_ONLY_STYLE"
    assert "A_ONLY_STYLE" in companion.system_prompt
    assert "B_ONLY_STYLE" not in companion.system_prompt

    restarted = Companion(save_path=None, auto_precompute=False)
    ingest("B", target=IngestionManager(companion=restarted, db=db))
    assert restarted.custom_instructions == "B_ONLY_STYLE"
    assert "B_ONLY_STYLE" in restarted.system_prompt


def test_failed_history_write_is_visible_and_clears_after_success(campaign_state):
    db, companion, manager, ingest, client = campaign_state
    ingest("A")
    with patch.object(
        ingestion_module, "record_snapshot_from_briefing", side_effect=OSError("disk full")
    ):
        ingest("B")
    health = manager.get_health_payload()
    assert health["precompute_ready"] is True
    assert companion.custom_instructions is None
    assert "disk full" in health["ingestion"]["last_error"]
    assert "history could not be saved" in health["ingestion"]["last_error"]
    assert not db.get_active_session_id(health["save_id"])
    ingest("B")
    assert manager.get_health_payload()["ingestion"]["last_error"] is None
    assert db.get_active_session_id(health["save_id"])


def test_instruction_edit_during_ingestion_does_not_change_previous_campaign(campaign_state):
    db, companion, manager, ingest, client = campaign_state
    a_id = ingest("A")
    headers = {"Authorization": "Bearer test-token"}
    client.post(
        "/api/session-advisor-custom", headers=headers, json={"custom_instructions": "A_ONLY_STYLE"}
    )
    manager.notify_save(companion.save_path)
    response = client.post(
        "/api/session-advisor-custom",
        headers=headers,
        json={"custom_instructions": "WRONG_CAMPAIGN"},
    )
    assert response.status_code == 409
    assert companion.custom_instructions == "A_ONLY_STYLE"
    assert (
        db.get_session_advisor_custom(session_id=db.get_active_session_id(a_id)) == "A_ONLY_STYLE"
    )
