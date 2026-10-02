"""Durable Advisor history must not outlive its campaign or become current-save evidence."""

import hashlib
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import backend.api.server as server
from backend.core.advisor_providers import AdvisorGenerationResult, AdvisorProviderError
from backend.core.companion import Companion
from backend.core.database import GameDatabase
from backend.core.history import compute_save_id

HEADERS = {"Authorization": "Bearer continuity-test"}


class Generator:
    def __init__(self, callback=None):
        self.prompts = []
        self.callback = callback

    def generate(self, **kwargs):
        self.prompts.append(kwargs["user_prompt"])
        if self.callback:
            return self.callback(kwargs)
        return AdvisorGenerationResult(
            text="First option: expand. "
            + "Supporting detail. " * 40
            + "Second option: fortify Vega.",
            model=kwargs.get("model") or "test/strategist",
            requested_model="test/strategist",
            provider="custom",
        )


def activate(companion, db, tmp_path, *, campaign="alpha", date="2200.06.15", alloys=10):
    path = tmp_path / f"{campaign}.sav"
    path.write_text("fixture")
    save_id = compute_save_id(
        campaign_id=campaign, player_id=7, empire_name=campaign, save_path=path
    )
    if not db.get_active_or_latest_session_id(save_id=save_id):
        db.create_session(
            save_id=save_id, save_path=str(path), empire_name=campaign, last_game_date=date
        )
    briefing = json.dumps(
        {
            "meta": {
                "campaign_id": campaign,
                "player_id": 7,
                "empire_name": campaign,
                "date": date,
            },
            "economy": {"net_monthly": {"alloys": alloys}},
        }
    )
    companion.extractor = SimpleNamespace(get_player_empire_id=lambda: 7)
    companion.apply_precomputed_briefing(
        save_path=path,
        briefing_json=briefing,
        game_date=date,
        identity={},
        situation={},
        metadata={"campaign_id": campaign, "name": campaign, "date": date},
    )
    return save_id, briefing


def make_app(monkeypatch, tmp_path, *, database=None, generator=None):
    monkeypatch.setenv(server.ENV_API_TOKEN, "continuity-test")
    # Keep the legacy summary cache inside the disposable test directory too.
    monkeypatch.setenv("STELLARIS_DB_PATH", str(tmp_path / "legacy.db"))
    generator = generator or Generator()
    companion = Companion(
        auto_precompute=False,
        advisor_provider="custom",
        advisor_model="test/strategist",
        advisor_base_url="http://127.0.0.1:8080/v1",
        advisor_generator=generator,
    )
    db = database or GameDatabase(tmp_path / "history.db")
    app = server.create_app()
    app.state.db, app.state.companion = db, companion
    return app, db, companion, generator


def new_conversation(client, save_id):
    response = client.post(f"/api/playthroughs/{save_id}/conversations", headers=HEADERS, json={})
    assert response.status_code == 200, response.text
    return response.json()["conversation"]["id"]


def ask(
    client,
    save_id,
    conversation_id,
    *,
    question="What are my options?",
    request_id="request-1",
    model=None,
    language=None,
):
    return client.post(
        "/api/chat",
        headers=HEADERS,
        json={
            "message": question,
            "save_id": save_id,
            "conversation_id": conversation_id,
            "request_id": request_id,
            "model": model,
            "language": language,
        },
    )


def test_restart_rehydrates_recent_followup_and_new_chat_keeps_archive(monkeypatch, tmp_path):
    app, db, companion, generator = make_app(monkeypatch, tmp_path)
    save_id, _ = activate(companion, db, tmp_path)
    with TestClient(app) as client:
        conversation = new_conversation(client, save_id)
        first = ask(client, save_id, conversation)
        assert first.status_code == 200
        assert first.json()["history_saved"] is True
    companion.close()
    db.close()

    app, db, companion, generator = make_app(monkeypatch, tmp_path)
    activate(companion, db, tmp_path)
    with TestClient(app) as client:
        listing = client.get(f"/api/playthroughs/{save_id}/conversations", headers=HEADERS).json()
        assert listing["conversations"][0]["id"] == conversation
        restored = client.get(
            f"/api/playthroughs/{save_id}/conversations/{conversation}", headers=HEADERS
        ).json()
        assert restored["turns"][0]["answer"].endswith("Second option: fortify Vega.")
        followup = ask(
            client,
            save_id,
            conversation,
            question="What about your second option?",
            request_id="request-2",
        )
        assert followup.status_code == 200
        assert "Second option: fortify Vega." in generator.prompts[-1]
        assert "[Save 2200.06.15]" in generator.prompts[-1]
        fresh = new_conversation(client, save_id)
        ask(client, save_id, fresh, question="A fresh topic", request_id="request-3")
        assert "Second option: fortify Vega." not in generator.prompts[-1]
        assert len(db.get_advisor_turns(save_id, conversation)) == 2
    companion.close()
    db.close()


def test_campaign_switch_restores_only_its_own_conversation(monkeypatch, tmp_path):
    app, db, companion, generator = make_app(monkeypatch, tmp_path)
    with TestClient(app) as client:
        alpha, _ = activate(companion, db, tmp_path)
        a = new_conversation(client, alpha)
        ask(client, alpha, a, question="Protect Alpha's secret outpost")
        beta, _ = activate(companion, db, tmp_path, campaign="beta")
        b = new_conversation(client, beta)
        assert ask(client, alpha, a, request_id="wrong-campaign").status_code == 409
        assert (
            client.get(f"/api/playthroughs/{beta}/conversations/{a}", headers=HEADERS).status_code
            == 404
        )
        ask(client, beta, b, question="Beta's economy", request_id="beta-request")
        assert "Alpha's secret" not in generator.prompts[-1]
        activate(companion, db, tmp_path)
        ask(client, alpha, a, question="Continue our discussion", request_id="return-alpha")
        assert "Protect Alpha's secret outpost" in generator.prompts[-1]
        assert "Beta's economy" not in generator.prompts[-1]
    companion.close()
    db.close()


def test_same_month_day_rollback_resets_context_but_preserves_archive(monkeypatch, tmp_path):
    app, db, companion, generator = make_app(monkeypatch, tmp_path)
    save_id, _ = activate(companion, db, tmp_path, date="2200.06.25")
    with TestClient(app) as client:
        conversation = new_conversation(client, save_id)
        ask(client, save_id, conversation, question="Future branch question")
        activate(companion, db, tmp_path, date="2200.06.15")
        ask(client, save_id, conversation, question="Reloaded earlier save", request_id="rollback")
        assert "Future branch question" not in generator.prompts[-1]
        ask(
            client,
            save_id,
            conversation,
            question="Continue after reload",
            request_id="after-rollback",
        )
        assert "Future branch question" not in generator.prompts[-1]
        assert "Reloaded earlier save" in generator.prompts[-1]
        assert len(db.get_advisor_turns(save_id, conversation)) == 3
        activate(companion, db, tmp_path, date="2201.06.15")
        ask(client, save_id, conversation, question="A year later", request_id="expired")
        assert "Continue after reload" not in generator.prompts[-1]
        ask(client, save_id, conversation, question="This year's next step", request_id="new-year")
        assert "Continue after reload" not in generator.prompts[-1]
        assert "A year later" in generator.prompts[-1]
    companion.close()
    db.close()


def test_source_date_hash_stay_with_captured_save_during_generation(monkeypatch, tmp_path):
    app, db, companion, generator = make_app(monkeypatch, tmp_path)
    save_id, briefing = activate(companion, db, tmp_path, date="2200.06.15", alloys=10)

    def advance(kwargs):
        activate(companion, db, tmp_path, campaign="beta", date="2201.01.01", alloys=99)
        return AdvisorGenerationResult(
            text="Alloys are 10.",
            model="snapshot-model",
            requested_model="snapshot-model",
            provider="custom",
        )

    generator.callback = advance
    with TestClient(app) as client:
        conversation = new_conversation(client, save_id)
        response = ask(client, save_id, conversation).json()
    assert response["history_saved"] is True
    assert response["save_id"] == save_id
    assert response["game_date"] == "2200.06.15"
    assert response["source_hash"] == hashlib.sha256(briefing.encode()).hexdigest()
    assert '"alloys":10' in generator.prompts[0]
    stored = db.get_advisor_turns(save_id, conversation)[0]
    assert stored["game_date"] == response["game_date"]
    assert stored["save_id"] == response["save_id"]
    assert stored["source_hash"] == response["source_hash"]
    assert stored["model"] == response["model"]
    companion.close()
    db.close()


def test_request_id_dedupes_model_call_and_rejects_different_question(monkeypatch, tmp_path):
    app, db, companion, generator = make_app(monkeypatch, tmp_path)
    save_id, _ = activate(companion, db, tmp_path)
    with TestClient(app) as client:
        conversation = new_conversation(client, save_id)
        first = ask(client, save_id, conversation).json()
        replay = ask(client, save_id, conversation).json()
        assert first == replay
        assert len(generator.prompts) == 1
        assert ask(client, save_id, conversation, question="Another question").status_code == 409
    assert len(db.get_advisor_turns(save_id, conversation)) == 1
    companion.close()
    db.close()


def test_concurrent_duplicate_requests_return_one_saved_exchange(monkeypatch, tmp_path):
    entered, release = threading.Event(), threading.Event()

    def generate(kwargs):
        entered.set()
        assert release.wait(timeout=5)
        return AdvisorGenerationResult(
            text="One answer",
            model="actual-model",
            requested_model="requested-model",
            routing={"reason": "original-route"},
            provider="custom",
        )

    app, db, companion, generator = make_app(monkeypatch, tmp_path, generator=Generator(generate))
    save_id, _ = activate(companion, db, tmp_path)
    with TestClient(app) as client:
        conversation = new_conversation(client, save_id)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(ask, client, save_id, conversation)
            assert entered.wait(timeout=5)
            second = pool.submit(ask, client, save_id, conversation)
            release.set()
            assert first.result(timeout=10).json() == second.result(timeout=10).json()
    assert len(generator.prompts) == 1
    assert len(db.get_advisor_turns(save_id, conversation)) == 1
    assert server._advisor_locks == {}
    companion.close()
    db.close()


def test_empty_new_chat_is_latest_and_prompt_never_loads_legacy_topic_cache(monkeypatch, tmp_path):
    app, db, companion, generator = make_app(monkeypatch, tmp_path)
    save_id, _ = activate(companion, db, tmp_path)
    monkeypatch.setattr(
        companion, "_load_save_memory_summary", lambda **kwargs: "Legacy future topic"
    )
    with TestClient(app) as client:
        old = new_conversation(client, save_id)
        ask(client, save_id, old)
        # Same timestamps still preserve creation order for an empty conversation.
        monkeypatch.setattr("backend.core.database.time.time", lambda: 2_000_000_000.0)
        first = new_conversation(client, save_id)
        latest = new_conversation(client, save_id)
        listing = client.get(f"/api/playthroughs/{save_id}/conversations", headers=HEADERS).json()
        assert [row["id"] for row in listing["conversations"]] == [latest, first, old]
        assert listing["conversations"][0]["turn_count"] == 0
        ask(client, save_id, latest, question="A new topic", request_id="fresh")
        assert "Legacy future topic" not in generator.prompts[-1]
        assert "Second option: fortify Vega." not in generator.prompts[-1]
    companion.close()
    db.close()


@pytest.mark.parametrize("failure", ["all_reads", "recent_turns"])
def test_history_read_failure_keeps_live_reply_and_archive_reports_unavailable(
    monkeypatch, tmp_path, failure
):
    app, db, companion, _ = make_app(monkeypatch, tmp_path)
    save_id, _ = activate(companion, db, tmp_path)

    def unavailable(*args, **kwargs):
        raise sqlite3.OperationalError("disk unavailable")

    with TestClient(app) as client:
        conversation = new_conversation(client, save_id)
        methods = ["get_advisor_turns"]
        if failure == "all_reads":
            methods += [
                "get_active_or_latest_session_id",
                "get_advisor_conversation",
                "get_advisor_turn_by_request",
                "list_advisor_conversations",
            ]
        for method in methods:
            monkeypatch.setattr(db, method, unavailable)
        reply = ask(client, save_id, conversation)
        assert reply.status_code == 200
        assert reply.json()["text"].endswith("fortify Vega.")
        assert reply.json()["history_saved"] is False
        archive = client.get(
            f"/api/playthroughs/{save_id}/conversations/{conversation}",
            headers=HEADERS,
        )
        assert archive.status_code == 503
        assert archive.json()["detail"]["code"] == "CHAT_HISTORY_UNAVAILABLE"
        if failure == "all_reads":
            listing = client.get(f"/api/playthroughs/{save_id}/conversations", headers=HEADERS)
            created = client.post(f"/api/playthroughs/{save_id}/conversations", headers=HEADERS)
            assert listing.status_code == created.status_code == 503
    companion.close()
    db.close()


def test_campaign_deleted_during_reply_is_not_resurrected(monkeypatch, tmp_path):
    app, db, companion, generator = make_app(monkeypatch, tmp_path)
    save_id, _ = activate(companion, db, tmp_path)

    def delete_campaign(kwargs):
        db.delete_playthrough(save_id)
        return AdvisorGenerationResult(
            text="Still usable", model="model", requested_model="model", provider="custom"
        )

    generator.callback = delete_campaign
    with TestClient(app) as client:
        conversation = new_conversation(client, save_id)
        reply = ask(client, save_id, conversation).json()
        assert reply["text"] == "Still usable"
        assert reply["history_saved"] is False
    assert db.get_advisor_conversation(save_id, conversation) is None
    assert db.get_advisor_turns(save_id, conversation) == []
    companion.close()
    db.close()


def test_archive_pages_keep_order_and_never_cross_conversations(monkeypatch, tmp_path):
    app, db, companion, _ = make_app(monkeypatch, tmp_path)
    save_id, _ = activate(companion, db, tmp_path)
    with TestClient(app) as client:
        conversation = new_conversation(client, save_id)
        for number in range(5):
            ask(
                client,
                save_id,
                conversation,
                question=f"Question {number}",
                request_id=f"r{number}",
            )
        path = f"/api/playthroughs/{save_id}/conversations/{conversation}"
        latest = client.get(path, headers=HEADERS, params={"limit": 2}).json()
        assert [turn["question"] for turn in latest["turns"]] == ["Question 3", "Question 4"]
        assert latest["has_more"] is True
        earlier = client.get(
            path,
            headers=HEADERS,
            params={"limit": 2, "before_turn_id": latest["turns"][0]["id"]},
        ).json()
        assert [turn["question"] for turn in earlier["turns"]] == ["Question 1", "Question 2"]
        oldest = client.get(
            path,
            headers=HEADERS,
            params={"limit": 2, "before_turn_id": earlier["turns"][0]["id"]},
        ).json()
        assert [turn["question"] for turn in oldest["turns"]] == ["Question 0"]
        assert oldest["has_more"] is False
        other = new_conversation(client, save_id)
        unrelated = client.get(
            f"/api/playthroughs/{save_id}/conversations/{other}",
            headers=HEADERS,
            params={"before_turn_id": latest["turns"][0]["id"]},
        ).json()
        assert unrelated["turns"] == []
    companion.close()
    db.close()


def test_rollback_boundary_is_preserved_when_language_changes(monkeypatch, tmp_path):
    app, db, companion, generator = make_app(monkeypatch, tmp_path)
    save_id, _ = activate(companion, db, tmp_path, date="2200.06.25")
    with TestClient(app) as client:
        conversation = new_conversation(client, save_id)
        ask(client, save_id, conversation, question="Old future branch question", language="en")
        activate(companion, db, tmp_path, date="2200.06.15")
        ask(
            client,
            save_id,
            conversation,
            question="Earlier Spanish branch",
            request_id="spanish",
            language="es",
        )
        activate(companion, db, tmp_path, date="2200.06.26")
        ask(
            client,
            save_id,
            conversation,
            question="Back to English",
            request_id="english",
            language="en",
        )
        assert "Old future branch question" not in generator.prompts[-1]
        assert "Earlier Spanish branch" not in generator.prompts[-1]
    companion.close()
    db.close()


def test_expired_wall_clock_context_stays_expired_after_new_reply(monkeypatch, tmp_path):
    app, db, companion, generator = make_app(monkeypatch, tmp_path)
    save_id, _ = activate(companion, db, tmp_path)
    with TestClient(app) as client:
        conversation = new_conversation(client, save_id)
        ask(client, save_id, conversation, question="Yesterday's tactical discussion")
        db.execute("UPDATE advisor_turns SET created_at = created_at - 90000")
        ask(client, save_id, conversation, question="Today's plan", request_id="today")
        assert "Yesterday's tactical discussion" not in generator.prompts[-1]
        ask(client, save_id, conversation, question="Continue today's plan", request_id="continue")
        assert "Yesterday's tactical discussion" not in generator.prompts[-1]
        assert "Today's plan" in generator.prompts[-1]
    companion.close()
    db.close()


def test_parallel_calls_have_request_local_diagnostics(monkeypatch, tmp_path):
    barrier = threading.Barrier(2)

    def generate(kwargs):
        barrier.wait(timeout=5)
        return AdvisorGenerationResult(
            text=kwargs["model"],
            model=kwargs["model"],
            requested_model=kwargs["model"],
            provider="custom",
        )

    app, db, companion, _ = make_app(monkeypatch, tmp_path, generator=Generator(generate))
    save_id, _ = activate(companion, db, tmp_path)
    with TestClient(app) as client:
        a, b = new_conversation(client, save_id), new_conversation(client, save_id)
        with ThreadPoolExecutor(max_workers=2) as pool:
            calls = [
                pool.submit(ask, client, save_id, cid, request_id=model, model=model)
                for cid, model in ((a, "model-a"), (b, "model-b"))
            ]
            results = [call.result(timeout=10).json() for call in calls]
    assert [(row["text"], row["model"]) for row in results] == [
        ("model-a", "model-a"),
        ("model-b", "model-b"),
    ]
    assert all(row["history_saved"] for row in results)
    companion.close()
    db.close()


def test_storage_failure_leaves_usable_unsaved_reply_and_provider_failure_saves_nothing(
    monkeypatch, tmp_path
):
    app, db, companion, generator = make_app(monkeypatch, tmp_path)
    save_id, _ = activate(companion, db, tmp_path)

    def fail_save(**kwargs):
        raise sqlite3.OperationalError("disk full")

    with TestClient(app) as client:
        conversation = new_conversation(client, save_id)
        monkeypatch.setattr(db, "save_advisor_turn", fail_save)
        reply = ask(client, save_id, conversation)
        assert reply.status_code == 200
        assert reply.json()["text"].endswith("fortify Vega.")
        assert reply.json()["history_saved"] is False
        assert db.get_advisor_turns(save_id, conversation) == []

        def fail_provider(kwargs):
            raise AdvisorProviderError("offline", code="PROVIDER_UNAVAILABLE", status_code=503)

        generator.callback = fail_provider
        failed = ask(client, save_id, conversation, request_id="failed-provider")
        assert failed.status_code == 503
        assert db.get_advisor_turns(save_id, conversation) == []
    companion.close()
    db.close()


def test_first_request_without_history_does_not_use_legacy_topic_cache(monkeypatch, tmp_path):
    app, db, companion, generator = make_app(monkeypatch, tmp_path)
    save_id, _ = activate(companion, db, tmp_path)
    app.state.db = None
    monkeypatch.setattr(
        companion, "_load_save_memory_summary", lambda **kwargs: "Legacy goal cache"
    )
    updated = []
    monkeypatch.setattr(
        companion, "_update_save_memory_summary", lambda **kwargs: updated.append(kwargs)
    )
    with TestClient(app) as client:
        reply = client.post(
            "/api/chat",
            headers=HEADERS,
            json={"message": "Fresh question", "save_id": save_id, "request_id": "first-fallback"},
        )
        assert reply.status_code == 200
        assert reply.json()["history_saved"] is False
        assert "Legacy goal cache" not in generator.prompts[-1]
        assert updated == []
    companion.close()
    db.close()


def test_backup_trash_restore_delete_include_conversations(monkeypatch, tmp_path):
    app, db, companion, _ = make_app(monkeypatch, tmp_path)
    save_id, _ = activate(companion, db, tmp_path)
    with TestClient(app) as client:
        conversation = new_conversation(client, save_id)
        ask(client, save_id, conversation)
    backup = tmp_path / "backup.db"
    db.create_backup(backup)
    with sqlite3.connect(backup) as saved:
        assert saved.execute("SELECT count(*) FROM advisor_turns").fetchone()[0] == 1
    db.trash_playthrough(save_id)
    assert len(db.get_advisor_turns(save_id, conversation)) == 1
    db.restore_playthrough(save_id)
    assert db.get_advisor_conversation(save_id, conversation)["turn_count"] == 1
    db.delete_playthrough(save_id)
    assert db.get_advisor_conversation(save_id, conversation) is None
    assert db.get_advisor_turns(save_id, conversation) == []
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    companion.close()
    db.close()
