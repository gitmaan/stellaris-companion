from unittest.mock import MagicMock

from fastapi.testclient import TestClient

import backend.api.server as server


def _auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


def _make_app(monkeypatch, sessions_data):
    monkeypatch.setenv(server.ENV_API_TOKEN, "test-token")
    app = server.create_app()
    db = MagicMock()
    db.get_sessions.return_value = sessions_data
    app.state.db = db
    return app


def _session_row(
    *,
    last_game_date: str | None,
    last_game_date_computed: str | None,
) -> dict[str, object]:
    return {
        "id": "session-1",
        "save_id": "save-1",
        "empire_name": "Kilik Cooperative",
        "started_at": 1,
        "ended_at": None,
        "first_game_date": "2200.01.01",
        "last_game_date": last_game_date,
        "last_game_date_computed": last_game_date_computed,
        "snapshot_count": 1,
    }


def test_api_sessions_uses_newer_session_last_game_date_when_snapshots_are_stale(monkeypatch):
    app = _make_app(
        monkeypatch,
        [
            _session_row(
                last_game_date="2227.07.01",
                last_game_date_computed="2200.01.01",
            )
        ],
    )

    with TestClient(app) as client:
        resp = client.get("/api/sessions", headers=_auth_headers())

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["sessions"][0]["last_game_date"] == "2227.07.01"


def test_api_sessions_keeps_snapshot_date_when_it_is_newer(monkeypatch):
    app = _make_app(
        monkeypatch,
        [
            _session_row(
                last_game_date="2508.01.01",
                last_game_date_computed="2509.07.01",
            )
        ],
    )

    with TestClient(app) as client:
        resp = client.get("/api/sessions", headers=_auth_headers())

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["sessions"][0]["last_game_date"] == "2509.07.01"
