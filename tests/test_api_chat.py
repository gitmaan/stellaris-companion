from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

import backend.api.server as server


def _auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


class _DummyCompanion:
    def __init__(self) -> None:
        self.is_loaded = True
        self.metadata = {"name": "Test Empire"}
        self.save_path = Path("/tmp/test.sav")
        self.extractor = SimpleNamespace(get_player_empire_id=lambda: 7)
        self._last_model = "gemini-3-flash-preview"
        self.last_request: dict[str, str | None] | None = None

    def get_precompute_status(self) -> dict[str, object]:
        return {"ready": True, "game_date": "2230.07.01"}

    def ask_precomputed(
        self,
        *,
        question: str,
        session_key: str,
        save_id: str | None = None,
        history_context: str | None = None,
        model_name: str | None = None,
        model_routing_mode: str | None = None,
    ) -> tuple[str, float]:
        self._last_model = model_name or self._last_model
        self.last_request = {
            "question": question,
            "session_key": session_key,
            "save_id": save_id,
            "model_name": model_name,
            "model_routing_mode": model_routing_mode,
        }
        return "Test response", 0.01

    def get_call_stats(self) -> dict[str, object]:
        return {"model": self._last_model}

    def get_advisor_model(self) -> str:
        return "gemini-3-flash-preview"


def _make_app(monkeypatch) -> tuple[object, _DummyCompanion]:
    monkeypatch.setenv(server.ENV_API_TOKEN, "test-token")
    app = server.create_app()
    companion = _DummyCompanion()
    app.state.companion = companion
    return app, companion


def test_api_chat_passes_model_override(monkeypatch):
    app, companion = _make_app(monkeypatch)

    with TestClient(app) as client:
        resp = client.post(
            "/api/chat",
            headers=_auth_headers(),
            json={
                "message": "Test question",
                "session_key": "chat-123",
                "model": "gemma-4-31b-it",
            },
        )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["text"] == "Test response"
    assert payload["model"] == "gemma-4-31b-it"
    assert companion.last_request is not None
    assert companion.last_request["model_name"] == "gemma-4-31b-it"


def test_api_chat_uses_default_model_when_override_is_missing(monkeypatch):
    app, companion = _make_app(monkeypatch)

    with TestClient(app) as client:
        resp = client.post(
            "/api/chat",
            headers=_auth_headers(),
            json={"message": "Test question", "session_key": "chat-123"},
        )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["model"] == "gemini-3-flash-preview"
    assert companion.last_request is not None
    assert companion.last_request["model_name"] is None


def test_api_chat_passes_model_routing_mode(monkeypatch):
    app, companion = _make_app(monkeypatch)

    with TestClient(app) as client:
        resp = client.post(
            "/api/chat",
            headers=_auth_headers(),
            json={
                "message": "Test question",
                "session_key": "chat-123",
                "model_routing_mode": "conserve",
            },
        )

    assert resp.status_code == 200
    assert companion.last_request is not None
    assert companion.last_request["model_routing_mode"] == "conserve"
