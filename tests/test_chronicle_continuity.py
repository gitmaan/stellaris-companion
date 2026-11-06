"""Persistence and provenance contracts exercised against real SQLite databases."""

from __future__ import annotations

import json
import threading
from contextlib import closing
from copy import deepcopy

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.api import server
from backend.core.advisor_providers import (
    AdvisorGenerationResult,
    AdvisorProviderConfig,
    AdvisorProviderError,
    OpenAICompatibleAdvisorGenerator,
)
from backend.core.chronicle import ChronicleGenerator
from backend.core.chronicle_store import (
    ChronicleConflict,
    assemble_chronicle,
    cached_chronicle_response,
    chronicle_revision,
    load_chapters_data,
)
from backend.core.database import GameDatabase
from backend.core.history import record_snapshot_from_briefing
from backend.mcp.context import McpContextError, StellarisMcpContext

SAVE = "continuity-save"


def briefing(date, *, authority="auth_democratic", neighbor="Old Republic"):
    return {
        "meta": {"date": date, "version": "Corvus v4.2.4", "empire_name": "Dated Union"},
        "identity": {
            "empire_name": "Dated Union",
            "ethics": ["egalitarian"],
            "authority": authority,
        },
        "diplomacy": {"relations": [{"empire_name": neighbor, "opinion": 10}]},
        "economy": {"large_unrelated_section": [1] * 1000},
    }


def snapshot(
    db, session, date, *, historical=True, authority="auth_democratic", neighbor="Old Republic"
):
    value = briefing(date, authority=authority, neighbor=neighbor)
    added, ident = db.insert_snapshot_if_new(
        session_id=session,
        game_date=date,
        save_hash=f"{date}-{neighbor}",
        military_power=100,
        colony_count=1,
        wars_count=0,
        energy_net=5,
        alloys_net=2,
        full_briefing_json=json.dumps(value) if historical else None,
        event_state_json="{}",
    )
    assert added
    db.update_session_latest_briefing(
        session_id=session, latest_briefing_json=json.dumps(value), last_game_date=date
    )
    return ident


def event(db, session, snapshot_id, date, summary="A recorded development"):
    db.insert_events(
        session_id=session,
        captured_at=float(snapshot_id),
        game_date=date,
        events=[
            {
                "event_type": "tech_completed",
                "summary": summary,
                "data": {"to_snapshot_id": snapshot_id},
            }
        ],
    )


@pytest.fixture
def campaign(tmp_path):
    db = GameDatabase(tmp_path / "continuity.db")
    session = db.get_or_create_active_session(
        save_id=SAVE, empire_name="Dated Union", last_game_date="2200.01.01"
    )
    first = snapshot(db, session, "2200.01.01")
    latest = snapshot(db, session, "2204.01.01")
    event(db, session, latest, "2204.01.01")
    yield db, session, first, latest
    db.close()


def seed(db, session, first, latest):
    data = {
        "chapters": [
            {
                "number": number,
                "title": f"Chapter {number}",
                "narrative": f"Original {number}.",
                "summary": f"Original summary {number}.",
                "is_finalized": True,
                "start_date": "2200.01.01",
                "end_date": "2204.01.01",
                "start_snapshot_id": first,
                "end_snapshot_id": latest,
                "coverage_date": "2204.01.01",
                "generated_at": "2026-01-01T12:00:00Z",
            }
            for number in (1, 2)
        ],
        "current_era_start_snapshot_id": latest,
        "current_era_start_date": "2204.01.01",
        "coverage_date": "2204.01.01",
        "content_generated_at": "2026-01-01T12:00:00Z",
    }
    db.upsert_chronicle_by_save_id(
        save_id=SAVE,
        session_id=session,
        language="en",
        chronicle_text=assemble_chronicle(data),
        chapters_json=json.dumps(data),
        event_count=1,
        snapshot_count=2,
    )
    return cached_chronicle_response(db.get_cached_chronicle_for_save(SAVE))


def prepared_commit(db, session, data, revision):
    return db.commit_chronicle(
        save_id=SAVE,
        session_id=session,
        language="en",
        expected_revision=revision,
        chapters_data=data,
        event_count=1,
        snapshot_count=2,
    )


def fake_structured(*, contents, response_schema, **kwargs):
    if response_schema.__name__ == "ChapterOutput":
        parsed = {
            "title": "Verified chapter",
            "epigraph": "",
            "summary": "Recorded development.",
            "sections": [{"type": "prose", "text": "Verified prose."}],
        }
    else:
        parsed = {"sections": [{"type": "prose", "text": "Verified current era."}]}
    return parsed, AdvisorGenerationResult(
        text=json.dumps(parsed), provider="gemini", model="test", requested_model="test"
    )


def test_native_undo_preserves_unrelated_chapter_and_rejects_stale_reader(campaign):
    db, session, first, latest = campaign
    initial = seed(db, session, first, latest)
    anchor = initial["chapters"][0]["id"]
    edited = cached_chronicle_response(
        db.edit_chronicle_chapter(
            save_id=SAVE,
            chapter_number=1,
            language="en",
            expected_revision=initial["chronicle_revision"],
            title="Corrected title",
            narrative="Corrected first.",
        )
    )
    assert edited["chapters"][0]["manual_edit_locked"] and edited["chapters"][0]["can_undo"]
    assert edited["chapters"][0]["id"] == anchor
    with pytest.raises(ChronicleConflict):
        db.edit_chronicle_chapter(
            save_id=SAVE,
            chapter_number=1,
            language="en",
            expected_revision=initial["chronicle_revision"],
            undo=True,
        )
    second = cached_chronicle_response(
        db.edit_chronicle_chapter(
            save_id=SAVE,
            chapter_number=2,
            language="en",
            expected_revision=edited["chronicle_revision"],
            narrative="Corrected second.",
        )
    )
    undone = cached_chronicle_response(
        db.edit_chronicle_chapter(
            save_id=SAVE,
            chapter_number=1,
            language="en",
            expected_revision=second["chronicle_revision"],
            undo=True,
        )
    )
    assert undone["chapters"][0]["narrative"] == "Original 1."
    assert undone["chapters"][1]["narrative"] == "Corrected second."
    assert not undone["chapters"][0]["manual_edit_locked"]
    assert undone["chronicle_revision"] != initial["chronicle_revision"]


@pytest.mark.parametrize("operation", ["reset", "reset_undo", "delete", "trash", "instructions"])
def test_prepared_generation_cannot_overwrite_archive_lifecycle_change(campaign, operation):
    db, session, first, latest = campaign
    initial = seed(db, session, first, latest)
    data = load_chapters_data(db.get_cached_chronicle_for_save(SAVE))
    data["chapters"][0]["narrative"] = "Late generated prose."
    if operation in {"reset", "reset_undo"}:
        db.reset_chronicle(SAVE)
        if operation == "reset_undo":
            assert db.undo_chronicle_reset(SAVE)
    elif operation == "delete":
        db.delete_playthrough(SAVE)
    elif operation == "trash":
        db.trash_playthrough(SAVE)
    else:
        db.update_chronicle_custom_instructions(SAVE, "A changed style")
    with pytest.raises(ChronicleConflict):
        prepared_commit(db, session, data, initial["chronicle_revision"])
    cached = db.get_cached_chronicle_for_save(SAVE)
    assert "Late generated prose." not in (cached or {}).get("chronicle_text", "")


def test_two_connections_accept_exactly_one_competing_writer(campaign):
    db, session, first, latest = campaign
    initial = seed(db, session, first, latest)
    candidate = load_chapters_data(db.get_cached_chronicle_for_save(SAVE))
    other = GameDatabase(db.path)
    barrier = threading.Barrier(2)
    results = []

    def write(connection, text):
        data = deepcopy(candidate)
        data["chapters"][0]["narrative"] = text
        barrier.wait(timeout=5)
        try:
            prepared_commit(connection, session, data, initial["chronicle_revision"])
            results.append("accepted")
        except ChronicleConflict:
            results.append("conflict")

    workers = [
        threading.Thread(target=write, args=(connection, text))
        for connection, text in ((db, "First writer"), (other, "Second writer"))
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)
        assert not worker.is_alive()
    other.close()
    assert sorted(results) == ["accepted", "conflict"]
    assert cached_chronicle_response(db.get_cached_chronicle_for_save(SAVE))["chapters"][0][
        "can_undo"
    ]


def test_native_edit_and_mcp_share_revision_and_undo_history(campaign):
    db, session, first, latest = campaign
    initial = seed(db, session, first, latest)
    context = StellarisMcpContext(db=db)
    guard = context.get_cached_chronicle()
    assert guard["chronicle_revision"] == initial["chronicle_revision"]
    edited = db.edit_chronicle_chapter(
        save_id=SAVE,
        chapter_number=1,
        language="en",
        expected_revision=guard["chronicle_revision"],
        narrative="Native edit.",
    )
    with pytest.raises(McpContextError, match="changed"):
        context.update_chronicle_chapter(
            campaign_ref=guard["campaign_ref"],
            expected_revision=guard["chronicle_revision"],
            chapter_number=1,
            narrative="Stale MCP edit.",
        )
    fresh = cached_chronicle_response(edited)
    saved = context.update_chronicle_chapter(
        campaign_ref=guard["campaign_ref"],
        expected_revision=fresh["chronicle_revision"],
        chapter_number=1,
        narrative="MCP edit.",
    )
    native = cached_chronicle_response(db.get_cached_chronicle_for_save(SAVE))
    assert saved["chronicle_revision"] == native["chronicle_revision"]
    undone = cached_chronicle_response(
        db.edit_chronicle_chapter(
            save_id=SAVE,
            chapter_number=1,
            language="en",
            expected_revision=native["chronicle_revision"],
            undo=True,
        )
    )
    assert undone["chapters"][0]["narrative"] == "Native edit."


def test_manual_mode_has_zero_provider_calls_or_writes_and_force_refresh_works(
    campaign, monkeypatch
):
    db, session, _, _ = campaign
    generator = ChronicleGenerator(db)
    calls = []

    def generate(**kwargs):
        calls.append(kwargs)
        return fake_structured(**kwargs)

    monkeypatch.setattr(generator, "_generate_structured_content", generate)
    empty = generator.generate_chronicle(session, refresh_mode="manual")
    assert not empty["cached"] and db.get_cached_chronicle_for_save(SAVE) is None and not calls
    generated = generator.generate_chronicle(session, refresh_mode="manual", force_refresh=True)
    assert generated["coverage_date"] == "2204.01.01" and len(calls) == 1
    before = dict(db.get_cached_chronicle_for_save(SAVE))
    assert (
        generator.generate_chronicle(session, refresh_mode="manual", chapter_only=True)[
            "chronicle_revision"
        ]
        == generated["chronicle_revision"]
    )
    assert db.get_cached_chronicle_for_save(SAVE) == before and len(calls) == 1


def test_cached_refresh_keeps_actual_writing_date_revision_and_coverage(campaign, monkeypatch):
    db, session, _, _ = campaign
    generator = ChronicleGenerator(db)
    monkeypatch.setattr(generator, "_generate_structured_content", fake_structured)
    generated = generator.generate_chronicle(session, force_refresh=True)
    snapshot(db, session, "2204.03.01")
    before = db.get_cached_chronicle_for_save(SAVE)
    cached = generator.generate_chronicle(session)
    assert cached["cached"]
    assert cached["coverage_date"] == generated["coverage_date"] == "2204.01.01"
    assert cached["generated_at"] == generated["generated_at"]
    assert cached["chronicle_revision"] == generated["chronicle_revision"]
    assert db.get_cached_chronicle_for_save(SAVE) == before


def test_truncated_refresh_never_replaces_a_complete_chronicle(campaign):
    db, session, _, _ = campaign
    requests = []

    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"sections":[{"type":"prose","text":"A complete record."}]}'
                        },
                        "finish_reason": "stop" if len(requests) == 1 else "length",
                    }
                ]
            },
        )

    provider = OpenAICompatibleAdvisorGenerator(
        config=AdvisorProviderConfig(
            provider="custom", model="test", base_url="http://127.0.0.1:1234/v1"
        ),
        client=httpx.Client(transport=httpx.MockTransport(handle)),
    )
    generator = ChronicleGenerator(db, provider_generator=provider)
    original = generator.generate_chronicle(session, force_refresh=True)
    before = dict(db.get_cached_chronicle_for_save(SAVE))
    assert original["current_era"]["narrative"] == "A complete record."
    with pytest.raises(AdvisorProviderError):
        generator.generate_chronicle(session, force_refresh=True)
    assert len(requests) == 3  # One successful generation, then two bounded attempts.
    assert db.get_cached_chronicle_for_save(SAVE) == before


def test_generation_captures_exact_source_before_late_ingestion(campaign, monkeypatch):
    db, session, _, latest = campaign
    generator = ChronicleGenerator(db)
    prompts = []

    def generate(**kwargs):
        prompts.append(kwargs["contents"])
        new_id = snapshot(db, session, "2205.01.01", neighbor="Future Dominion")
        event(db, session, new_id, "2205.01.01", "A future fact must wait")
        return fake_structured(**kwargs)

    monkeypatch.setattr(generator, "_generate_structured_content", generate)
    result = generator.generate_chronicle(session, force_refresh=True)
    assert "Future Dominion" not in prompts[0] and "A future fact must wait" not in prompts[0]
    assert result["coverage_date"] == result["current_era"]["coverage_date"] == "2204.01.01"
    data = load_chapters_data(db.get_cached_chronicle_for_save(SAVE))
    assert data["current_era_cache"]["last_snapshot_id"] == latest
    assert result["event_count"] == 1


def test_generation_outside_transaction_cannot_overwrite_edit_during_model_call(
    campaign, monkeypatch
):
    db, session, first, latest = campaign
    seed(db, session, first, latest)
    generator = ChronicleGenerator(db)

    def generate(**kwargs):
        assert not db._conn.in_transaction
        cache = cached_chronicle_response(db.get_cached_chronicle_for_save(SAVE))
        db.edit_chronicle_chapter(
            save_id=SAVE,
            chapter_number=1,
            language="en",
            expected_revision=cache["chronicle_revision"],
            narrative="Player correction during generation.",
        )
        return fake_structured(**kwargs)

    monkeypatch.setattr(generator, "_generate_structured_content", generate)
    with pytest.raises(ChronicleConflict):
        generator.regenerate_chapter(session, 1, confirm=True)
    assert (
        "Player correction during generation."
        in db.get_cached_chronicle_for_save(SAVE)["chronicle_text"]
    )


def test_new_chapter_source_is_historical_and_regeneration_reuses_bundle(campaign, monkeypatch):
    db, session, first, latest = campaign
    generator = ChronicleGenerator(db)
    monkeypatch.setattr(generator, "_generate_structured_content", fake_structured)
    data = load_chapters_data(None)
    assert generator._finalize_chapter(
        SAVE,
        data,
        briefing={"identity": {"authority": "Future Politics"}},
        trigger="time_threshold",
    )
    chapter = data["chapters"][0]
    assert chapter["source_bundle"]["briefing"]["identity"]["authority"] == "auth_democratic"
    assert "economy" not in chapter["source_bundle"]["briefing"]
    assert chapter["source_bundle"]["coverage_date"] == "2204.01.01"
    saved = prepared_commit(db, session, data, chronicle_revision(load_chapters_data(None)))
    new_id = snapshot(
        db, session, "2220.01.01", authority="auth_imperial", neighbor="Future Dominion"
    )
    event(db, session, new_id, "2220.01.01", "Future event")
    # Even changes to the live old event table cannot alter this chapter's captured evidence.
    db.execute("UPDATE events SET summary='Rewritten event database'")
    inputs = []

    def capture(**kwargs):
        inputs.append(kwargs)
        return {
            "title": "Regenerated",
            "epigraph": "",
            "narrative": "Recorded events.",
            "summary": "Known facts.",
        }

    monkeypatch.setattr(generator, "_generate_chapter_content", capture)
    regenerated = generator.regenerate_chapter(
        session,
        1,
        confirm=True,
        expected_revision=cached_chronicle_response(saved)["chronicle_revision"],
    )
    assert inputs[0]["briefing"]["identity"]["authority"] == "auth_democratic"
    assert inputs[0]["events"][0]["summary"] == "A recorded development"
    assert regenerated["chapters"][0]["can_undo"]
    assert "source_bundle" not in regenerated["chapters"][0]


def test_legacy_historical_context_is_limited_and_never_uses_latest_politics(campaign, monkeypatch):
    db, session, first, _ = campaign
    old = snapshot(db, session, "2206.01.01", historical=False)
    db.update_session_latest_briefing(
        session_id=session,
        latest_briefing_json=json.dumps(
            briefing("2240.01.01", authority="auth_imperial", neighbor="Future Dominion")
        ),
    )
    historical = db.get_historical_chronicle_briefing(SAVE, old)
    assert historical["historical_context_limited"] and "authority" not in historical["identity"]
    assert "diplomacy" not in historical and "version" not in historical["meta"]
    seed(db, session, first, old)
    generator = ChronicleGenerator(db)
    captured = []

    def generate(**kwargs):
        captured.append(kwargs)
        return {
            "title": "Legacy",
            "epigraph": "",
            "narrative": "Only known evidence.",
            "summary": "Known.",
        }

    monkeypatch.setattr(generator, "_generate_chapter_content", generate)
    result = generator.regenerate_chapter(session, 1, confirm=True)
    assert result["chapters"][0]["historical_context_limited"]
    assert "Future Dominion" not in json.dumps(captured[0]) and "auth_imperial" not in json.dumps(
        captured[0]
    )


def test_external_current_era_and_finalized_edits_survive_automatic_generation(
    campaign, monkeypatch
):
    db, session, first, latest = campaign
    seed(db, session, first, latest)
    context = StellarisMcpContext(db=db)
    guard = context.get_cached_chronicle()
    external = context.save_chronicle_current_era(
        campaign_ref=guard["campaign_ref"],
        expected_revision=guard["chronicle_revision"],
        narrative="Protected external era.",
    )
    edited = db.edit_chronicle_chapter(
        save_id=SAVE,
        chapter_number=1,
        language="en",
        expected_revision=external["chronicle_revision"],
        narrative="Protected player chapter.",
    )
    fresh = snapshot(db, session, "2204.06.01")
    for index in range(5):
        event(db, session, fresh, "2204.06.01", f"New fact {index}")
    generator = ChronicleGenerator(db)

    def unexpected(**kwargs):
        raise AssertionError("Protected prose must not invoke a provider")

    monkeypatch.setattr(generator, "_generate_structured_content", unexpected)
    result = generator.generate_chronicle(session)
    assert result["current_era"]["narrative"] == "Protected external era."
    assert result["chapters"][0]["narrative"] == "Protected player chapter."
    assert result["chronicle_revision"] == cached_chronicle_response(edited)["chronicle_revision"]


def test_api_edit_undo_shapes_conflict_and_validation(campaign, monkeypatch):
    db, session, first, latest = campaign
    initial = seed(db, session, first, latest)
    monkeypatch.setenv(server.ENV_API_TOKEN, "test-token")
    app = server.create_app()
    app.state.db = db
    headers = {"Authorization": "Bearer test-token"}
    route = f"/api/playthroughs/{SAVE}/chronicle/chapters/1"
    with TestClient(app) as client:
        edited = client.put(
            route,
            headers=headers,
            json={
                "expected_revision": initial["chronicle_revision"],
                "title": "Updated",
                "narrative": "API correction.",
            },
        )
        assert edited.status_code == 200 and edited.json()["chapters"][0]["can_undo"]
        stale = client.post(
            route + "/undo",
            headers=headers,
            json={"expected_revision": initial["chronicle_revision"]},
        )
        assert stale.status_code == 409 and stale.json()["detail"]["code"] == "CHRONICLE_CONFLICT"
        undone = client.post(
            route + "/undo",
            headers=headers,
            json={"expected_revision": edited.json()["chronicle_revision"]},
        )
        assert (
            undone.status_code == 200 and undone.json()["chapters"][0]["narrative"] == "Original 1."
        )
        assert (
            client.put(
                route,
                headers=headers,
                json={"expected_revision": undone.json()["chronicle_revision"], "narrative": " "},
            ).status_code
            == 400
        )
        assert (
            client.put(route, headers=headers, json={"narrative": "Missing revision"}).status_code
            == 422
        )
        assert (
            client.get(f"/api/playthroughs/{SAVE}/chronicle", headers=headers).json()[
                "chronicle_revision"
            ]
            == undone.json()["chronicle_revision"]
        )


def test_snapshot_range_dates_belong_to_captured_rows_on_rewind(campaign):
    db, session, first, _ = campaign
    rewound = snapshot(db, session, "2201.01.01")
    bounds = db.get_snapshot_range_for_save(SAVE)
    assert bounds["first_snapshot_id"] == first
    assert bounds["last_snapshot_id"] == rewound and bounds["last_game_date"] == "2201.01.01"


@pytest.mark.parametrize("empty_cached_start", [False, True])
def test_chronicle_can_start_after_loading_a_save_before_first_capture(
    tmp_path, monkeypatch, empty_cached_start
):
    with closing(GameDatabase(tmp_path / "rewound.db")) as db:
        session = db.get_or_create_active_session(save_id=SAVE, empire_name="Dated Union")
        future = snapshot(db, session, "2308.04.01")
        event(db, session, future, "2308.04.01", "Future branch fact")
        if empty_cached_start:
            db.upsert_chronicle_by_save_id(
                save_id=SAVE,
                session_id=session,
                language="en",
                chronicle_text="",
                chapters_json=json.dumps(
                    {
                        "chapters": [],
                        "current_era_start_date": "2308.04.01",
                        "current_era_start_snapshot_id": future,
                    }
                ),
                event_count=0,
                snapshot_count=1,
            )
        first = snapshot(db, session, "2303.04.01")
        latest = snapshot(db, session, "2304.04.01")
        event(db, session, latest, "2304.04.01", "Earlier branch fact")
        generator = ChronicleGenerator(db)
        prompts = []

        def generate(**kwargs):
            prompts.append(kwargs["contents"])
            return fake_structured(**kwargs)

        monkeypatch.setattr(generator, "_generate_structured_content", generate)
        result = generator.generate_chronicle(session, force_refresh=True)
        assert result["current_era"] is not None
        assert result["coverage_date"] == "2304.04.01"
        assert len(prompts) == 1
        assert "Earlier branch fact" in prompts[0] and "Future branch fact" not in prompts[0]
        bounds = db.get_chronicle_snapshot_range(SAVE, upper_snapshot_id=latest)
        assert bounds["first_snapshot_id"] == first
        assert bounds["first_game_date"] == "2303.04.01"
        assert bounds["last_snapshot_id"] == latest
        assert bounds["snapshot_count"] == 3
        original = db.get_chronicle_snapshot_range(SAVE, upper_snapshot_id=future)
        assert original["first_snapshot_id"] == original["last_snapshot_id"] == future


@pytest.mark.parametrize("capture_future_first", [False, True])
def test_sparse_snapshots_finalize_at_real_boundaries_without_getting_stuck(
    tmp_path, monkeypatch, capture_future_first
):
    with closing(GameDatabase(tmp_path / "sparse.db")) as db:
        session = db.get_or_create_active_session(save_id=SAVE, empire_name="Dated Union")
        if capture_future_first:
            future = snapshot(db, session, "2350.04.01", neighbor="Future empire")
            event(db, session, future, "2350.04.01", "Future branch fact")
        first = snapshot(db, session, "2303.04.01")
        latest = snapshot(db, session, "2310.04.01", neighbor="Current empire")
        for index in range(10):
            event(db, session, latest, "2310.04.01", f"Recorded fact {index}")
        generator = ChronicleGenerator(db)
        prompts = []

        def generate(**kwargs):
            prompts.append(kwargs["contents"])
            return fake_structured(**kwargs)

        monkeypatch.setattr(generator, "_generate_structured_content", generate)
        result = generator.generate_chronicle(session, force_refresh=True)
        assert len(result["chapters"]) == 1
        chapter = result["chapters"][0]
        assert (chapter["start_date"], chapter["end_date"]) == ("2303.04.01", "2310.04.01")
        assert (chapter["start_snapshot_id"], chapter["end_snapshot_id"]) == (first, latest)
        stored = load_chapters_data(db.get_chronicle_by_save_id(SAVE))
        assert stored["chapters"][0]["source_bundle"]["coverage_date"] == "2310.04.01"
        assert result["pending_chapters"] == 0
        assert len(prompts) == 1
        assert "Recorded fact 9" in prompts[0] and "Future branch fact" not in prompts[0]
        assert "Current empire" in prompts[0] and "Future empire" not in prompts[0]
        repeat = generator.generate_chronicle(session, force_refresh=True)
        assert repeat["chronicle_revision"] == result["chronicle_revision"]
        assert len(prompts) == 1

        # The same sparse-boundary rule applies to later, thirty-year chapters.
        last = snapshot(db, session, "2345.04.01", neighbor="Later empire")
        event(db, session, last, "2345.04.01", "Later chapter fact")
        later = generator.generate_chronicle(session, force_refresh=True)
        assert len(later["chapters"]) == 2
        assert later["chapters"][0] == chapter
        assert later["chapters"][1]["end_snapshot_id"] == last
        assert later["chapters"][1]["end_date"] == "2345.04.01"
        assert later["pending_chapters"] == 0
        assert len(prompts) == 2


def test_future_events_do_not_satisfy_first_chapter_threshold(campaign, monkeypatch):
    db, session, _, _ = campaign
    future = snapshot(db, session, "2220.01.01")
    for index in range(10):
        event(db, session, future, "2220.01.01", f"Future branch fact {index}")
    earlier = snapshot(db, session, "2206.01.01")
    event(db, session, earlier, "2206.01.01", "Earlier branch fact")
    generator = ChronicleGenerator(db)
    prompts = []

    def generate(**kwargs):
        prompts.append(kwargs["contents"])
        return fake_structured(**kwargs)

    monkeypatch.setattr(generator, "_generate_structured_content", generate)
    result = generator.generate_chronicle(session, force_refresh=True)
    assert result["chapters"] == []
    assert result["pending_chapters"] == 0
    assert result["current_era"] is not None
    assert len(prompts) == 1
    assert "Earlier branch fact" in prompts[0] and "Future branch fact" not in prompts[0]


def ingest(db, date, *, techs, colonies, wars=()):
    """Record a capture through the real ingestion path, including event diffing."""
    value = briefing(date)
    value["meta"].update(campaign_id="timeline-campaign", player_id=0)
    value["technology"] = {"tech_count": techs}
    value["territory"] = {"colonies": {"total_count": colonies}}
    value["history"] = {"wars": {"count": len(wars), "wars": list(wars)}}
    inserted, snapshot_id, session = record_snapshot_from_briefing(
        db=db, save_path=None, save_hash=f"timeline-{date}", briefing=value
    )
    assert inserted
    return session, snapshot_id


def events_at(db, session, snapshot_id):
    return [
        (row["event_type"], json.loads(row["data_json"]).get("from_snapshot_id"))
        for row in db.get_recent_events(session_id=session, limit=100)
        if json.loads(row["data_json"]).get("to_snapshot_id") == snapshot_id
    ]


def recording_generator(db, prompts):
    generator = ChronicleGenerator(db)

    def generate(**kwargs):
        prompts.append(kwargs["contents"])
        return fake_structured(**kwargs)

    generator._generate_structured_content = generate
    return generator


def test_loaded_older_save_is_diffed_against_its_own_past(tmp_path):
    with closing(GameDatabase(tmp_path / "rewind-diff.db")) as db:
        session, past = ingest(db, "2303.04.01", techs=10, colonies=3)
        _, future = ingest(db, "2308.04.01", techs=20, colonies=5, wars=["Great War"])
        assert {kind for kind, _ in events_at(db, session, future)} == {
            "tech_completed",
            "colony_count_change",
            "war_started",
        }
        _, rewound = ingest(db, "2304.04.01", techs=12, colonies=3)
        # Loading 2304 must not read as losing the 2308 colonies, war and research.
        assert events_at(db, session, rewound) == [("tech_completed", past)]

        prompts = []
        result = recording_generator(db, prompts).generate_chronicle(session, force_refresh=True)
        assert result["current_era"] is not None and len(prompts) == 1
        assert "War ended" not in prompts[0] and "5 → 3" not in prompts[0]
        assert "10 → 12" in prompts[0]


def test_save_loaded_before_first_capture_records_no_regression_events(tmp_path):
    with closing(GameDatabase(tmp_path / "rewind-first.db")) as db:
        session, _ = ingest(db, "2308.04.01", techs=20, colonies=5, wars=["Great War"])
        _, rewound = ingest(db, "2303.04.01", techs=10, colonies=3)
        _, latest = ingest(db, "2304.04.01", techs=12, colonies=4)
        assert events_at(db, session, rewound) == []
        assert {kind for kind, _ in events_at(db, session, latest)} == {
            "tech_completed",
            "colony_count_change",
        }
        assert all(source == rewound for _, source in events_at(db, session, latest))


def test_abandoned_timeline_does_not_leak_into_current_era(tmp_path):
    with closing(GameDatabase(tmp_path / "branches.db")) as db:
        session = db.get_or_create_active_session(save_id=SAVE, empire_name="Dated Union")
        snapshot(db, session, "2303.01.01")
        abandoned = snapshot(db, session, "2310.01.01", neighbor="Abandoned empire")
        event(db, session, abandoned, "2310.01.01", "Abandoned branch fact")
        reloaded = snapshot(db, session, "2305.01.01")
        event(db, session, reloaded, "2305.01.01", "Reloaded branch fact")
        # Databases written before this fix diffed the reload against the abandoned future.
        db.insert_events(
            session_id=session,
            captured_at=float(reloaded),
            game_date="2305.01.01",
            events=[
                {
                    "event_type": "war_ended",
                    "summary": "Legacy rewind regression",
                    "data": {"from_snapshot_id": abandoned, "to_snapshot_id": reloaded},
                }
            ],
        )
        latest = snapshot(db, session, "2312.01.01", neighbor="Live empire")
        event(db, session, latest, "2312.01.01", "Continued branch fact")

        prompts = []
        result = recording_generator(db, prompts).generate_chronicle(session, force_refresh=True)
        assert result["chapters"] == [] and result["current_era"] is not None
        assert len(prompts) == 1
        assert "Reloaded branch fact" in prompts[0] and "Continued branch fact" in prompts[0]
        assert "Abandoned branch fact" not in prompts[0]
        assert "Legacy rewind regression" not in prompts[0]
        assert "Abandoned empire" not in prompts[0]

        live = db.get_events_in_snapshot_range(save_id=SAVE, to_snapshot_id=latest)
        assert [row["summary"] for row in live] == [
            "Reloaded branch fact",
            "Continued branch fact",
        ]
        # History written while the abandoned branch was live stays citeable.
        then = db.get_events_in_snapshot_range(save_id=SAVE, to_snapshot_id=abandoned)
        assert [row["summary"] for row in then] == ["Abandoned branch fact"]


def test_chapter_boundary_is_never_taken_from_an_abandoned_timeline(tmp_path):
    with closing(GameDatabase(tmp_path / "branch-chapter.db")) as db:
        session = db.get_or_create_active_session(save_id=SAVE, empire_name="Dated Union")
        first = snapshot(db, session, "2300.01.01")
        abandoned = snapshot(db, session, "2304.01.01", neighbor="Abandoned empire")
        for index in range(10):
            event(db, session, abandoned, "2304.01.01", f"Abandoned branch fact {index}")
        reloaded = snapshot(db, session, "2301.01.01")
        event(db, session, reloaded, "2301.01.01", "Reloaded branch fact")
        latest = snapshot(db, session, "2310.01.01", neighbor="Live empire")
        for index in range(10):
            event(db, session, latest, "2310.01.01", f"Live branch fact {index}")

        prompts = []
        result = recording_generator(db, prompts).generate_chronicle(session, force_refresh=True)
        chapter = result["chapters"][0]
        assert chapter["start_snapshot_id"] == first
        assert chapter["end_snapshot_id"] in {reloaded, latest}
        assert chapter["end_snapshot_id"] != abandoned
        assert prompts and all("Abandoned branch fact" not in prompt for prompt in prompts)
        assert all("Abandoned empire" not in prompt for prompt in prompts)
        assert any("Reloaded branch fact" in prompt for prompt in prompts)


def test_advisor_and_mcp_event_readers_skip_abandoned_timeline_rows(tmp_path):
    with closing(GameDatabase(tmp_path / "branch-readers.db")) as db:
        session = db.get_or_create_active_session(save_id=SAVE, empire_name="Dated Union")
        snapshot(db, session, "2303.01.01")
        abandoned = snapshot(db, session, "2310.01.01")
        event(db, session, abandoned, "2310.01.01", "Abandoned branch fact")
        reloaded = snapshot(db, session, "2305.01.01")
        event(db, session, reloaded, "2305.01.01", "Reloaded branch fact")
        # Stored before the ingestion fix: the reload diffed against the abandoned future.
        db.insert_events(
            session_id=session,
            captured_at=float(reloaded),
            game_date="2305.01.01",
            events=[
                {
                    "event_type": "war_ended",
                    "summary": "Legacy rewind regression",
                    "data": {"from_snapshot_id": abandoned, "to_snapshot_id": reloaded},
                }
            ],
        )

        def summaries(rows):
            return {row["summary"] for row in rows}

        assert summaries(db.get_recent_events(session_id=session, limit=1)) == {
            "Reloaded branch fact"
        }
        assert summaries(db.get_recent_events(session_id=session)) == {"Reloaded branch fact"}
        assert summaries(db.get_all_events(session_id=session)) == {"Reloaded branch fact"}
        context = StellarisMcpContext(db=db)
        assert summaries(context.get_recent_events(limit=10)["events"]) == {"Reloaded branch fact"}
        for scope in ("latest_session", "full_summary", "current_era"):
            source = context.get_chronicle_source_material(scope=scope)
            assert summaries(source["events"]) == {"Reloaded branch fact"}, scope


def test_brief_look_at_an_old_save_supersedes_the_captures_it_skipped(tmp_path):
    """Pins a known limitation: a written save during a brief look at an old save
    starts a new branch, so returning to the latest save is one coarse diff."""
    with closing(GameDatabase(tmp_path / "peek.db")) as db:
        session, start = ingest(db, "2250.01.01", techs=10, colonies=3)
        _, middle = ingest(db, "2270.01.01", techs=20, colonies=5, wars=["Middle War"])
        _, tip = ingest(db, "2300.01.01", techs=30, colonies=8)
        _, peek = ingest(db, "2250.06.01", techs=10, colonies=3)
        _, returned = ingest(db, "2300.02.01", techs=30, colonies=8)
        _, latest = ingest(db, "2301.01.01", techs=31, colonies=8)

        path, superseded = db.get_snapshot_timeline(save_id=db.get_save_id_for_session(session))
        assert [snapshot_id for snapshot_id, _ in path] == [start, peek, returned, latest]
        assert superseded == {middle, tip}
        assert events_at(db, session, peek) == []
        assert sorted(events_at(db, session, returned)) == [
            ("colony_count_change", peek),
            ("tech_completed", peek),
        ]
        recent = db.get_recent_events(session_id=session, limit=100)
        assert {json.loads(row["data_json"])["to_snapshot_id"] for row in recent} == {
            returned,
            latest,
        }
        assert not any("Middle War" in row["summary"] for row in recent)


def test_mcp_archive_undo_cannot_erase_a_later_native_chapter_edit(campaign):
    db, session, first, latest = campaign
    seed(db, session, first, latest)
    context = StellarisMcpContext(db=db)
    guard = context.get_cached_chronicle()
    external = context.update_chronicle_chapter(
        campaign_ref=guard["campaign_ref"],
        expected_revision=guard["chronicle_revision"],
        chapter_number=1,
        narrative="External first chapter.",
    )
    native = cached_chronicle_response(
        db.edit_chronicle_chapter(
            save_id=SAVE,
            chapter_number=2,
            language="en",
            expected_revision=external["chronicle_revision"],
            narrative="Later native second chapter.",
        )
    )
    with pytest.raises(McpContextError, match="newer"):
        context.undo_chronicle_edit(
            campaign_ref=guard["campaign_ref"],
            expected_revision=native["chronicle_revision"],
            edit_receipt=external["edit_receipt"],
        )
    assert (
        cached_chronicle_response(db.get_cached_chronicle_for_save(SAVE))["chapters"][1][
            "narrative"
        ]
        == "Later native second chapter."
    )


def test_current_era_reports_bounded_partial_evidence_and_dated_facts(campaign, monkeypatch):
    db, session, _, latest = campaign
    for index in range(210):
        event(db, session, latest, "2204.01.01", f"Recorded fact {index}")
    generator = ChronicleGenerator(db)
    prompts = []

    def generate(**kwargs):
        prompts.append(kwargs["contents"])
        return fake_structured(**kwargs)

    monkeypatch.setattr(generator, "_generate_structured_content", generate)
    response = generator.generate_chronicle(session, force_refresh=True)
    assert response["current_era"]["partial_coverage"]
    assert response["current_era"]["events_covered"] == 211
    assert response["current_era"]["selected_event_count"] == 200
    assert "2204.01.01: Recorded fact" in prompts[0]
    assert "Event list truncated" in prompts[0]


def test_generation_cannot_commit_after_reset_during_provider_call(campaign, monkeypatch):
    db, session, first, latest = campaign
    seed(db, session, first, latest)
    generator = ChronicleGenerator(db)

    def generate(**kwargs):
        db.reset_chronicle(SAVE)
        return fake_structured(**kwargs)

    monkeypatch.setattr(generator, "_generate_structured_content", generate)
    with pytest.raises(ChronicleConflict):
        generator.regenerate_chapter(session, 1, confirm=True)
    assert db.get_cached_chronicle_for_save(SAVE)["chronicle_text"] == ""
    assert db.get_playthrough(SAVE)["can_undo_reset"]


def test_same_year_rollback_does_not_leak_future_events_into_current_era(campaign, monkeypatch):
    db, session, _, _ = campaign
    future = snapshot(db, session, "2204.12.01")
    event(db, session, future, "2204.12.01", "Future branch fact")
    earlier = snapshot(db, session, "2204.06.01")
    event(db, session, earlier, "2204.06.01", "Earlier branch fact")
    generator = ChronicleGenerator(db)
    prompts = []

    def generate(**kwargs):
        prompts.append(kwargs["contents"])
        return fake_structured(**kwargs)

    monkeypatch.setattr(generator, "_generate_structured_content", generate)
    result = generator.generate_chronicle(session, force_refresh=True)
    assert result["coverage_date"] == "2204.06.01"
    assert "Earlier branch fact" in prompts[0] and "Future branch fact" not in prompts[0]


def test_save_before_finalized_chapter_preserves_archive_with_no_model_calls(campaign, monkeypatch):
    db, session, first, latest = campaign
    initial = seed(db, session, first, latest)
    snapshot(db, session, "2203.12.01")
    generator = ChronicleGenerator(db)

    def unexpected(**kwargs):
        raise AssertionError("A rewound save cannot generate over the later archive")

    monkeypatch.setattr(generator, "_generate_structured_content", unexpected)
    for options in ({"force_refresh": True}, {"chapter_only": True}, {}):
        response = generator.generate_chronicle(session, **options)
        assert response["chronicle_revision"] == initial["chronicle_revision"]
        assert "predates" in response["message"]
        assert response["chapters"] == initial["chapters"]


def test_mcp_edit_clears_old_summary_marks_downstream_context_and_unknown_era_source(
    campaign, monkeypatch
):
    db, session, first, latest = campaign
    seed(db, session, first, latest)
    context = StellarisMcpContext(db=db)
    guard = context.get_cached_chronicle()
    era = context.save_chronicle_current_era(
        campaign_ref=guard["campaign_ref"],
        expected_revision=guard["chronicle_revision"],
        narrative="External era without a verified source date.",
    )
    response = cached_chronicle_response(db.get_cached_chronicle_for_save(SAVE))
    assert response["current_era"]["coverage_date"] is None
    external = context.update_chronicle_chapter(
        campaign_ref=guard["campaign_ref"],
        expected_revision=era["chronicle_revision"],
        chapter_number=1,
        narrative="Corrected external chapter.",
    )
    response = cached_chronicle_response(db.get_cached_chronicle_for_save(SAVE))
    assert response["chapters"][0]["summary"] == ""
    assert response["chapters"][1]["context_stale"] and response["current_era"]["context_stale"]
    generator = ChronicleGenerator(db)

    def unexpected(**kwargs):
        raise AssertionError("Update Story cannot silently replace protected imported prose")

    monkeypatch.setattr(generator, "_generate_structured_content", unexpected)
    preserved = generator.generate_chronicle(session, force_refresh=True)
    assert preserved["current_era"]["narrative"] == response["current_era"]["narrative"]
    assert preserved["chronicle_revision"] == external["chronicle_revision"]
    assert preserved["cached"]


def test_native_edit_preserves_multiline_text_without_duplicate_epigraph(campaign):
    db, session, first, latest = campaign
    seed(db, session, first, latest)
    cache = db.get_cached_chronicle_for_save(SAVE)
    data = load_chapters_data(cache)
    data["chapters"][0].update(
        epigraph="A recorded opening",
        narrative='"A recorded opening"\n\nFirst paragraph.\n\nSecond paragraph.',
    )
    saved = prepared_commit(db, session, data, chronicle_revision(load_chapters_data(cache)))
    original = cached_chronicle_response(saved)
    edited = cached_chronicle_response(
        db.edit_chronicle_chapter(
            save_id=SAVE,
            chapter_number=1,
            language="en",
            expected_revision=original["chronicle_revision"],
            narrative=original["chapters"][0]["narrative"] + "\n\nCorrection.",
        )
    )
    assert edited["chapters"][0]["epigraph"] == "" and edited["chapters"][0]["sections"] is None
    assert edited["chapters"][0]["narrative"].count("A recorded opening") == 1
    undone = cached_chronicle_response(
        db.edit_chronicle_chapter(
            save_id=SAVE,
            chapter_number=1,
            language="en",
            expected_revision=edited["chronicle_revision"],
            undo=True,
        )
    )
    assert undone["chapters"][0]["epigraph"] == "A recorded opening"
