import json
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

import backend.api.server as server
from backend.core.database import GameDatabase
from backend.core.history import compute_save_id


def _auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


def _make_app(monkeypatch, tmp_path):
    monkeypatch.setenv(server.ENV_API_TOKEN, "test-token")
    app = server.create_app()
    db = GameDatabase(tmp_path / "history.db")
    app.state.db = db
    return app, db


def _add_campaign(db: GameDatabase, save_id: str = "save-1") -> str:
    session_id = db.create_session(
        save_id=save_id,
        empire_name="Kilik Cooperative",
        last_game_date="2240.01.01",
    )
    db.upsert_cached_chronicle(
        session_id,
        "A preserved Chronicle",
        2,
        3,
        json.dumps(
            {
                "chapters": [
                    {
                        "number": 1,
                        "title": "The Beginning",
                        "narrative": "A people reached for the stars.",
                    }
                ]
            }
        ),
        save_id,
        "en",
    )
    return session_id


def test_cached_chronicle_route_is_read_only_and_provider_independent(monkeypatch, tmp_path):
    app, db = _make_app(monkeypatch, tmp_path)
    _add_campaign(db)
    before = dict(db.execute("SELECT * FROM cached_chronicles;").fetchone())

    with TestClient(app) as client:
        campaigns = client.get("/api/playthroughs", headers=_auth_headers())
        chronicle = client.get(
            "/api/playthroughs/save-1/chronicle",
            headers=_auth_headers(),
        )

    assert campaigns.status_code == 200
    assert campaigns.json()["playthroughs"][0]["has_chronicle"] is True
    assert chronicle.status_code == 200
    assert chronicle.json()["cached"] is True
    assert chronicle.json()["chronicle"] == "A preserved Chronicle"
    assert chronicle.json()["chapters"][0]["summary"] == ""
    assert dict(db.execute("SELECT * FROM cached_chronicles;").fetchone()) == before
    db.close()


def test_lifecycle_routes_require_trash_and_preserve_cache_until_delete(monkeypatch, tmp_path):
    app, db = _make_app(monkeypatch, tmp_path)
    _add_campaign(db)
    before = dict(db.execute("SELECT * FROM cached_chronicles;").fetchone())

    with TestClient(app) as client:
        no_confirm = client.delete("/api/playthroughs/save-1", headers=_auth_headers())
        not_trashed = client.delete(
            "/api/playthroughs/save-1?confirm=true",
            headers=_auth_headers(),
        )
        label = client.post(
            "/api/playthroughs/save-1/label",
            headers=_auth_headers(),
            json={"display_label": "My favorite run"},
        )
        trash = client.post("/api/playthroughs/save-1/trash", headers=_auth_headers())
        assert dict(db.execute("SELECT * FROM cached_chronicles;").fetchone()) == before
        restore = client.post("/api/playthroughs/save-1/restore", headers=_auth_headers())
        assert dict(db.execute("SELECT * FROM cached_chronicles;").fetchone()) == before
        client.post("/api/playthroughs/save-1/trash", headers=_auth_headers())
        deleted = client.delete(
            "/api/playthroughs/save-1?confirm=true",
            headers=_auth_headers(),
        )

    assert no_confirm.status_code == 400
    assert not_trashed.status_code == 409
    assert label.status_code == 200
    assert trash.status_code == 200
    assert restore.status_code == 200
    assert deleted.status_code == 200
    assert db.get_playthrough("save-1") is None
    db.close()


def test_reset_routes_are_explicit_and_reversible(monkeypatch, tmp_path):
    app, db = _make_app(monkeypatch, tmp_path)
    _add_campaign(db)
    before = dict(db.execute("SELECT * FROM cached_chronicles;").fetchone())

    with TestClient(app) as client:
        unconfirmed = client.post(
            "/api/playthroughs/save-1/reset-chronicle",
            headers=_auth_headers(),
            json={"language": "en"},
        )
        reset = client.post(
            "/api/playthroughs/save-1/reset-chronicle",
            headers=_auth_headers(),
            json={"confirm": True, "language": "en"},
        )
        undo = client.post(
            "/api/playthroughs/save-1/undo-reset",
            headers=_auth_headers(),
            json={"language": "en"},
        )

    assert unconfirmed.status_code == 400
    assert reset.status_code == 200
    assert undo.status_code == 200
    assert dict(db.execute("SELECT * FROM cached_chronicles;").fetchone()) == before
    db.close()


def test_current_campaign_cannot_be_trashed(monkeypatch, tmp_path):
    app, db = _make_app(monkeypatch, tmp_path)
    save_path = tmp_path / "current.sav"
    save_path.write_bytes(b"save")
    save_id = compute_save_id(
        campaign_id="campaign-1",
        player_id=7,
        empire_name="Kilik Cooperative",
        save_path=save_path,
    )
    _add_campaign(db, save_id)
    ingestion = MagicMock()
    ingestion.get_status.return_value = {
        "save_loaded": True,
        "current_save_path": str(save_path),
        "t2_meta": {
            "campaign_id": "campaign-1",
            "player_id": 7,
            "empire_name": "Kilik Cooperative",
        },
    }
    app.state.ingestion = ingestion

    with TestClient(app) as client:
        campaigns = client.get("/api/playthroughs", headers=_auth_headers())
        trashed = client.post(
            f"/api/playthroughs/{save_id}/trash",
            headers=_auth_headers(),
        )

    assert campaigns.json()["playthroughs"][0]["is_current"] is True
    assert trashed.status_code == 409
    assert db.get_playthrough(save_id)["is_trashed"] is False
    db.close()
