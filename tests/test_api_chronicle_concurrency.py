import threading
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

import backend.api.server as server
from backend.core.chronicle import ChronicleGenerator


def _make_app(monkeypatch):
    monkeypatch.setenv(server.ENV_API_TOKEN, "test-token")
    app = server.create_app()

    # Minimal DB surface for /api/chronicle.
    mock_db = MagicMock()
    mock_db.get_session_by_id.return_value = {"id": "session-1", "save_id": "save-1"}
    mock_db.get_save_id_for_session.return_value = "save-1"
    app.state.db = mock_db

    return app


def _auth_headers():
    return {"Authorization": "Bearer test-token"}


def test_api_chronicle_serializes_concurrent_requests(monkeypatch):
    # Clear any leaked state from previous tests.
    server._chronicle_in_flight.clear()

    started = threading.Event()
    unblock = threading.Event()

    def slow_generate_chronicle(self, session_id, *, force_refresh=False, chapter_only=False):
        started.set()
        # Hold the request open long enough for a second request to arrive.
        unblock.wait(timeout=10)
        return {"ok": True}

    monkeypatch.setattr(
        ChronicleGenerator,
        "generate_chronicle",
        slow_generate_chronicle,
        raising=True,
    )

    app = _make_app(monkeypatch)
    headers = _auth_headers()

    first_response: dict[str, object] = {}

    def _run_first_request():
        with TestClient(app) as client:
            first_response["resp"] = client.post(
                "/api/chronicle",
                json={"session_id": "session-1"},
                headers=headers,
            )

    t = threading.Thread(target=_run_first_request, daemon=True)
    t.start()

    assert started.wait(timeout=5), "First chronicle request never reached generator"

    with TestClient(app) as client:
        second = client.post("/api/chronicle", json={"session_id": "session-1"}, headers=headers)

    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "CHRONICLE_IN_PROGRESS"

    unblock.set()
    t.join(timeout=10)
    assert "resp" in first_response
    assert first_response["resp"].status_code == 200

    # Ensure the in-flight guard was released after completion.
    with TestClient(app) as client:
        third = client.post("/api/chronicle", json={"session_id": "session-1"}, headers=headers)
    assert third.status_code == 200


def test_api_chronicle_releases_lock_on_exception(monkeypatch):
    server._chronicle_in_flight.clear()

    def boom(self, session_id, *, force_refresh=False, chapter_only=False):
        raise RuntimeError("boom")

    app = _make_app(monkeypatch)
    headers = _auth_headers()

    monkeypatch.setattr(ChronicleGenerator, "generate_chronicle", boom, raising=True)
    with TestClient(app) as client:
        first = client.post("/api/chronicle", json={"session_id": "session-1"}, headers=headers)
    assert first.status_code == 500
    assert server._chronicle_in_flight == set()

    def ok(self, session_id, *, force_refresh=False, chapter_only=False):
        return {"ok": True}

    monkeypatch.setattr(ChronicleGenerator, "generate_chronicle", ok, raising=True)
    with TestClient(app) as client:
        second = client.post("/api/chronicle", json={"session_id": "session-1"}, headers=headers)
    assert second.status_code == 200
