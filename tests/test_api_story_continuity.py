"""Native API continuation: current identity, durable choices and stale requests."""

import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.core.json_utils import json_dumps
from backend.core.story_continuity import StoryContinuity
from tests.test_api_advisor_continuity import HEADERS, ask, make_app, new_conversation
from tests.test_story_continuity import cache, capture, continue_from


def activate_story(companion, tmp_path, saved):
    briefing = saved[3]
    meta = briefing["meta"]
    path = tmp_path / f"{meta['player_id']}.sav"
    path.write_text("synthetic")
    companion.extractor = SimpleNamespace(get_player_empire_id=lambda: meta["player_id"])
    companion.apply_precomputed_briefing(
        save_path=path,
        briefing_json=json_dumps(briefing),
        game_date=meta["date"],
        identity=briefing["identity"],
        situation={},
        metadata=meta,
    )


def test_api_choice_keeps_current_identity_and_previous_chat_separate(monkeypatch, tmp_path):
    app, db, companion, generator = make_app(monkeypatch, tmp_path)
    try:
        old = capture(db, 0, "2300.01.01")
        cache(db, old, "The Omnian core endured.")
        child = capture(db, 7, "2301.01.01", colonies=2)
        activate_story(companion, tmp_path, old)
        with TestClient(app) as client:
            prior_chat = new_conversation(client, old[0])
            prior = ask(
                client, old[0], prior_chat, question="Remember the core's fortification plan."
            )
            assert prior.status_code == 200, prior.text
            activate_story(companion, tmp_path, child)
            url = f"/api/playthroughs/{child[0]}/story"
            offer = client.get(url, headers=HEADERS).json()
            assert offer["can_decide"] and offer["parts"] == []
            accepted = client.post(
                url,
                headers=HEADERS,
                json={
                    "predecessor_save_id": old[0],
                    "expected_revision": offer["offer_revision"],
                },
            )
            assert accepted.status_code == 200, accepted.text
            chat = new_conversation(client, child[0])
            reply = ask(client, child[0], chat, request_id="new-empire")
            assert reply.status_code == 200, reply.text
            prompt = generator.prompts[-1]
            model_state = json.loads(prompt.split("```json\n", 1)[1].split("\n```", 1)[0])
            assert model_state["identity"]["empire_name"] == "Barcalan Collective"
            assert model_state["identity"]["authority"] == "hive_mind"
            assert "The Omnian core endured." in prompt
            assert "core's fortification plan" in prompt
            assert "does not establish destruction" in prompt
            assert reply.json()["snapshot_id"] == child[2]
            assert len(db.get_advisor_turns(old[0], prior_chat)) == 1
            assert len(db.get_advisor_turns(child[0], chat)) == 1
            assert db.get_all_events_by_save_id(save_id=child[0]) == []
    finally:
        companion.close()
        db.close()


def test_story_api_rejects_stale_observation_and_campaign_switch(monkeypatch, tmp_path):
    app, db, companion, _ = make_app(monkeypatch, tmp_path)
    try:
        old = capture(db, 0, "2300.01.01")
        child = capture(db, 7, "2301.01.01")
        activate_story(companion, tmp_path, child)
        with TestClient(app) as client:
            url = f"/api/playthroughs/{child[0]}/story"
            assert client.get(url).status_code == 401
            offer = client.get(url, headers=HEADERS).json()
            choice = {"predecessor_save_id": old[0], "expected_revision": offer["offer_revision"]}
            activate_story(companion, tmp_path, old)
            changed = client.post(url, headers=HEADERS, json=choice)
            assert changed.status_code == 409
            assert changed.json()["detail"]["code"] == "CAMPAIGN_CHANGED"
            rewind = capture(db, 7, "2290.01.01")
            activate_story(companion, tmp_path, rewind)
            stale = client.post(url, headers=HEADERS, json=choice)
            assert stale.status_code == 409
            assert stale.json()["detail"]["code"] == "STORY_CHANGED"
            assert StoryContinuity(db).context(child[0])["parts"] == []
    finally:
        companion.close()
        db.close()


def test_advisor_rejects_reply_if_continuation_changes_during_generation(monkeypatch, tmp_path):
    app, db, companion, generator = make_app(monkeypatch, tmp_path)
    try:
        old = capture(db, 0, "2300.01.01")
        cache(db, old)
        child = capture(db, 7, "2301.01.01")
        continue_from(db, child, old)
        activate_story(companion, tmp_path, child)

        def disconnect(_):
            store = StoryContinuity(db)
            store.decide(
                child[0],
                predecessor_save_id=None,
                expected_revision=store.offer(child[0])["offer_revision"],
            )
            generator.callback = None
            return generator.generate(user_prompt="unused")

        generator.callback = disconnect
        with TestClient(app) as client:
            chat = new_conversation(client, child[0])
            result = ask(client, child[0], chat)
            assert result.status_code == 409, result.text
            assert db.get_advisor_turns(child[0], chat) == []
    finally:
        companion.close()
        db.close()


def test_advisor_rewind_catchup_keeps_old_turn_readable_but_out_of_live_prompt(
    monkeypatch, tmp_path
):
    app, db, companion, generator = make_app(monkeypatch, tmp_path)
    try:
        old = capture(db, 0, "2300.01.01")
        cache(db, old)
        child = capture(db, 7, "2301.01.01")
        continue_from(db, child, old)
        activate_story(companion, tmp_path, child)
        with TestClient(app) as client:
            chat = new_conversation(client, child[0])
            first = ask(client, child[0], chat)
            assert first.status_code == 200, first.text
            assert "The Omnian age." in generator.prompts[-1]
            capture(db, 7, "2290.01.01")
            caught_up = capture(db, 7, "2305.01.01")
            activate_story(companion, tmp_path, caught_up)
            later = ask(client, child[0], chat, request_id="after-rewind")
            assert later.status_code == 200, later.text
            assert "The Omnian age." not in generator.prompts[-1]
            assert "Second option: fortify Vega." not in generator.prompts[-1]
            assert len(db.get_advisor_turns(child[0], chat)) == 2
    finally:
        companion.close()
        db.close()


def _unsaved_newer(saved, date):
    """The loaded briefing moved on, but persisting its snapshot failed."""
    briefing = saved[3]
    return (*saved[:3], {**briefing, "meta": {**briefing["meta"], "date": date}})


def test_plain_campaign_still_answers_when_newest_snapshot_was_not_saved(monkeypatch, tmp_path):
    app, db, companion, _ = make_app(monkeypatch, tmp_path)
    try:
        saved = capture(db, 0, "2300.01.01")
        activate_story(companion, tmp_path, _unsaved_newer(saved, "2300.02.01"))
        with TestClient(app) as client:
            reply = ask(client, saved[0], new_conversation(client, saved[0]))
            assert reply.status_code == 200, reply.text
            assert reply.json()["snapshot_id"] is None
    finally:
        companion.close()
        db.close()


def test_continued_story_rejects_a_briefing_newer_than_its_snapshot(monkeypatch, tmp_path):
    app, db, companion, _ = make_app(monkeypatch, tmp_path)
    try:
        old = capture(db, 0, "2300.01.01")
        cache(db, old)
        child = capture(db, 7, "2301.01.01")
        continue_from(db, child, old)
        activate_story(companion, tmp_path, _unsaved_newer(child, "2301.02.01"))
        with TestClient(app) as client:
            reply = ask(client, child[0], new_conversation(client, child[0]))
            assert reply.status_code == 409, reply.text
            assert reply.json()["detail"]["code"] == "STORY_CHANGED"
    finally:
        companion.close()
        db.close()
