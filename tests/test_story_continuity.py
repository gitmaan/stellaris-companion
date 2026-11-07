"""Synthetic regression coverage for issue #95; no saves or model calls."""

import json
from copy import deepcopy

import pytest

from backend.core.chronicle import ChronicleGenerator
from backend.core.chronicle_store import ChronicleConflict, chronicle_revision, load_chapters_data
from backend.core.database import GameDatabase
from backend.core.history import record_snapshot_from_briefing
from backend.core.story_continuity import NO_STORY, StoryContinuity, story_prompt
from backend.mcp.context import McpContextError, StellarisMcpContext
from tests.test_chronicle_continuity import fake_structured


@pytest.fixture
def db(tmp_path):
    database = GameDatabase(tmp_path / "history.db")
    yield database
    database.close()


def capture(db, player, date, *, galaxy="galaxy-95", colonies=10, name=None):
    name = name or ("Omnian Core" if player == 0 else "Barcalan Collective")
    briefing = {
        "meta": {"campaign_id": galaxy, "player_id": player, "empire_name": name, "date": date},
        "identity": {
            "empire_name": name,
            "ethics": ["gestalt_consciousness"],
            "authority": "hive_mind" if player else "machine_intelligence",
        },
        "territory": {"colonies": {"total_count": colonies}},
        "military": {"military_power": 100},
        "economy": {"net_monthly": {"energy": 12, "alloys": 4}},
    }
    _, snapshot, session = record_snapshot_from_briefing(
        db=db, save_path=None, save_hash=f"{galaxy}-{player}-{date}-{colonies}", briefing=briefing
    )
    return db.get_save_id_for_session(session), session, snapshot, briefing


def cache(db, saved, narrative="The Omnian age.", *, language="en"):
    save_id, session, snapshot, briefing = saved
    date = briefing["meta"]["date"]
    data = {
        "chapters": [
            {
                "number": 1,
                "title": "First age",
                "summary": narrative,
                "narrative": narrative,
                "start_date": date,
                "end_date": date,
                "start_snapshot_id": snapshot,
                "end_snapshot_id": snapshot,
                "is_finalized": True,
            }
        ],
        "coverage_date": date,
    }
    db.upsert_chronicle_by_save_id(
        save_id=save_id,
        session_id=session,
        chronicle_text=narrative,
        chapters_json=json.dumps(data),
        event_count=0,
        snapshot_count=1,
        language=language,
    )


def continue_from(db, child, parent):
    store = StoryContinuity(db)
    offer = store.offer(child[0])
    return store.decide(
        child[0], predecessor_save_id=parent[0], expected_revision=offer["offer_revision"]
    )


def test_story_continues_without_merging_empire_snapshots_or_events(db):
    old = capture(db, 0, "2300.01.01", colonies=10)
    cache(db, old)
    old_cache = db.get_chronicle_by_save_id(old[0])
    new = capture(db, 7, "2301.01.01", colonies=2)
    offer = StoryContinuity(db).offer(new[0])
    assert offer["parts"] == []
    assert [candidate["save_id"] for candidate in offer["candidates"]] == [old[0]]

    linked = continue_from(db, new, old)

    assert old[0] != new[0] and old[1] != new[1]
    assert db.get_chronicle_by_save_id(old[0]) == old_cache
    assert db.get_chronicle_by_save_id(new[0]) is None
    assert db.get_all_events_by_save_id(save_id=new[0]) == []
    assert "The Omnian age." in linked["parts"][0]["chronicle"]
    assert "Omnian Core" in story_prompt(linked)
    assert db.get_snapshot_range_for_save(new[0])["snapshot_count"] == 1


def test_decline_survives_restart_and_does_not_change_original_archive(db):
    old = capture(db, 0, "2300.01.01")
    cache(db, old)
    new = capture(db, 7, "2301.01.01")
    store = StoryContinuity(db)
    store.decide(
        new[0], predecessor_save_id=None, expected_revision=store.offer(new[0])["offer_revision"]
    )
    reopened = GameDatabase(db.path)
    try:
        offer = StoryContinuity(reopened).offer(new[0])
        assert offer["decision"] == "separate"
        # Declining is remembered but not final: the earlier empire stays linkable.
        assert [c["save_id"] for c in offer["candidates"]] == [old[0]]
        assert StoryContinuity(reopened).context(new[0])["parts"] == []
        assert reopened.get_chronicle_by_save_id(old[0])["chronicle_text"] == "The Omnian age."
    finally:
        reopened.close()


def test_continuation_is_frozen_across_parent_edits_and_app_restarts(db):
    old = capture(db, 0, "2300.01.01")
    cache(db, old)
    new = capture(db, 7, "2301.01.01")
    linked = continue_from(db, new, old)
    cache(db, old, "Changed later.")
    reopened = GameDatabase(db.path)
    try:
        assert StoryContinuity(reopened).context(new[0])["parts"] == linked["parts"]
    finally:
        reopened.close()


def test_known_legacy_session_archive_can_continue_without_rewriting_it(db):
    old = capture(db, 0, "2300.01.01")
    cache(db, old, "A preserved legacy chapter.")
    db.execute("UPDATE cached_chronicles SET save_id=NULL WHERE session_id=?", (old[1],))
    before = db.get_cached_chronicle_for_save(old[0])
    child = capture(db, 7, "2301.01.01")
    result = continue_from(db, child, old)
    assert "A preserved legacy chapter." in result["parts"][0]["chronicle"]
    assert db.get_cached_chronicle_for_save(old[0]) == before


def test_rewind_detaches_ancestry_even_after_dates_catch_up(db):
    old = capture(db, 0, "2300.01.01")
    cache(db, old)
    new = capture(db, 7, "2301.01.01")
    linked = continue_from(db, new, old)
    capture(db, 7, "2303.01.01")
    assert StoryContinuity(db).context(new[0])["revision"] == linked["revision"]
    capture(db, 7, "2299.01.01")
    capture(db, 7, "2304.01.01")
    current = StoryContinuity(db).context(new[0])
    assert current["status"] == "rewound"
    assert current["parts"] == [] and story_prompt(current) == ""
    # Historical readers can still resolve the receipt taken before the rewind.
    assert StoryContinuity(db).context(new[0], snapshot_id=new[2])["parts"] == linked["parts"]


def test_stale_offer_cannot_link_a_different_loaded_observation(db):
    old = capture(db, 0, "2300.01.01")
    new = capture(db, 7, "2301.01.01")
    store = StoryContinuity(db)
    offer = store.offer(new[0])
    capture(db, 7, "2290.01.01")
    with pytest.raises(ChronicleConflict):
        store.decide(new[0], predecessor_save_id=old[0], expected_revision=offer["offer_revision"])
    assert store.context(new[0])["parts"] == []


def test_same_name_missing_identity_other_galaxy_and_future_do_not_offer(db):
    capture(db, 0, "2310.01.01")
    capture(db, 1, "2200.01.01", galaxy="different", name="Omnian Core")
    capture(db, 2, "2200.01.01", galaxy=None, name="Omnian Core")
    child = capture(db, 7, "2301.01.01")
    assert StoryContinuity(db).offer(child[0])["candidates"] == []


def test_switching_back_does_not_reparent_original_or_create_a_cycle(db):
    old = capture(db, 0, "2300.01.01")
    new = capture(db, 7, "2301.01.01")
    continue_from(db, new, old)
    returning = capture(db, 0, "2302.01.01")
    assert returning[0] == old[0]
    assert StoryContinuity(db).offer(old[0])["candidates"] == []
    third = capture(db, 8, "2303.01.01", name="Third Empire")
    linked = continue_from(db, third, new)
    assert [part["save_id"] for part in linked["parts"]] == [old[0], new[0]]


def test_ancestor_prose_and_events_from_abandoned_future_are_excluded(db):
    capture(db, 0, "2299.01.01", colonies=10)
    future = capture(db, 0, "2308.01.01", colonies=20)
    cache(db, future, "ABANDONED VICTORY")
    capture(db, 0, "2300.01.01", colonies=11)
    child = capture(db, 7, "2301.01.01")
    linked = continue_from(db, child, future)
    prompt = story_prompt(linked)
    assert "ABANDONED VICTORY" not in prompt
    assert "20" not in json.dumps(linked["parts"][0]["events"])
    assert db.get_chronicle_by_save_id(future[0])["chronicle_text"] == "ABANDONED VICTORY"


def test_localized_history_stays_language_scoped_and_choices_invalidate_writers(db):
    old = capture(db, 0, "2300.01.01")
    cache(db, old, "English prose.")
    cache(db, old, "Deutsche Chronik.", language="de")
    child = capture(db, 7, "2301.01.01")
    cache(db, child, "Child archive.")
    before = db.get_chronicle_by_save_id(child[0])
    data = load_chapters_data(before)
    revision = chronicle_revision(data)
    continue_from(db, child, old)
    assert (
        "Deutsche Chronik."
        in StoryContinuity(db).context(child[0], language="de")["parts"][0]["chronicle"]
    )
    assert "English prose." not in story_prompt(
        StoryContinuity(db).context(child[0], language="de")
    )
    with pytest.raises(ChronicleConflict):
        db.commit_chronicle(
            save_id=child[0],
            session_id=child[1],
            language="en",
            expected_revision=revision,
            chapters_data=data,
            event_count=0,
            snapshot_count=1,
        )
    assert db.get_chronicle_by_save_id(child[0])["chronicle_text"] == before["chronicle_text"]


def test_trash_hides_ancestry_and_permanent_delete_erases_frozen_copies(db):
    old = capture(db, 0, "2300.01.01")
    cache(db, old, "PRIVATE OLD PROSE")
    child = capture(db, 7, "2301.01.01")
    continue_from(db, child, old)
    db.trash_playthrough(old[0])
    assert StoryContinuity(db).context(child[0])["parts"] == []
    db.restore_playthrough(old[0])
    assert StoryContinuity(db).context(child[0])["parts"]
    db.delete_playthrough(old[0])
    assert StoryContinuity(db).context(child[0])["parts"] == []
    assert "PRIVATE OLD PROSE" not in str(
        db.execute("SELECT history_json FROM story_continuations").fetchall()[0][0]
    )


def test_migration_backfills_strong_identity_without_rewriting_histories(db):
    old = capture(db, 0, "2300.01.01")
    cache(db, old)
    before = deepcopy(db.get_chronicle_by_save_id(old[0]))
    db.execute("DROP TABLE campaign_sources")
    db.execute("DROP TABLE story_continuations")
    db.execute("UPDATE schema_version SET version=11")
    db.execute("PRAGMA user_version=11")
    db.apply_migrations()
    assert db.get_schema_version() == 12
    assert db.get_chronicle_by_save_id(old[0]) == before
    child = capture(db, 7, "2301.01.01")
    assert StoryContinuity(db).offer(child[0])["candidates"][0]["save_id"] == old[0]
    assert StoryContinuity(db).context(child[0])["revision"] == NO_STORY


def test_native_chronicle_continues_with_new_identity_and_preserves_rewound_prose(db, monkeypatch):
    old = capture(db, 0, "2300.01.01")
    cache(db, old)
    child = capture(db, 7, "2301.01.01")
    continue_from(db, child, old)
    generator = ChronicleGenerator(db)
    prompts = []

    def generate(**kwargs):
        prompts.append(kwargs["contents"])
        return fake_structured(**kwargs)

    monkeypatch.setattr(generator, "_generate_structured_content", generate)
    result = generator.generate_chronicle(child[1], force_refresh=True)
    assert result["current_era"]
    assert "Barcalan Collective" in prompts[0] and "The Omnian age." in prompts[0]
    assert "does not establish destruction" in prompts[0]
    original = db.get_chronicle_by_save_id(child[0])
    capture(db, 7, "2290.01.01")
    capture(db, 7, "2305.01.01")
    result = generator.generate_chronicle(child[1], force_refresh=True)
    assert result["story_reset_required"] and len(prompts) == 1
    assert db.get_chronicle_by_save_id(child[0]) == original


def test_native_chronicle_rejects_in_flight_choice_change(db, monkeypatch):
    old = capture(db, 0, "2300.01.01")
    cache(db, old)
    child = capture(db, 7, "2301.01.01")
    continue_from(db, child, old)
    generator = ChronicleGenerator(db)

    def generate(**kwargs):
        store = StoryContinuity(db)
        store.decide(
            child[0],
            predecessor_save_id=None,
            expected_revision=store.offer(child[0])["offer_revision"],
        )
        return fake_structured(**kwargs)

    monkeypatch.setattr(generator, "_generate_structured_content", generate)
    with pytest.raises(ChronicleConflict):
        generator.generate_chronicle(child[1], force_refresh=True)
    assert db.get_chronicle_by_save_id(child[0]) is None


def test_mcp_uses_same_ancestry_and_rejects_prepared_writes_after_rewind(db):
    old = capture(db, 0, "2300.01.01")
    cache(db, old)
    child = capture(db, 7, "2301.01.01")
    continue_from(db, child, old)
    context = StellarisMcpContext(db=db)
    briefing = context.get_strategy_context()
    assert "The Omnian age." in briefing["story_context"]
    assert "Barcalan Collective" in json.dumps(briefing["response_guidance"])
    source = context.get_chronicle_source_material()
    assert source["story_context"] == briefing["story_context"]
    assert context.get_cached_chronicle()["story_history"][0]["save_id"] == old[0]
    context.save_chronicle_current_era(
        campaign_ref=source["campaign_ref"],
        expected_revision=source["chronicle_revision"],
        narrative="A continued era.",
    )
    prepared = context.get_chronicle_source_material()
    before = db.get_chronicle_by_save_id(child[0])
    capture(db, 7, "2290.01.01")
    capture(db, 7, "2305.01.01")
    with pytest.raises(McpContextError, match="changed"):
        context.save_chronicle_current_era(
            campaign_ref=prepared["campaign_ref"],
            expected_revision=prepared["chronicle_revision"],
            narrative="Stale prose.",
        )
    refreshed = context.get_chronicle_source_material()
    assert refreshed["story_context"] == ""
    with pytest.raises(McpContextError, match="earlier story continuation"):
        context.save_chronicle_current_era(
            campaign_ref=refreshed["campaign_ref"],
            expected_revision=refreshed["chronicle_revision"],
            narrative="Do not reuse prior linked prose on this branch.",
        )
    assert db.get_chronicle_by_save_id(child[0]) == before


def test_a_declined_story_can_be_linked_later(db):
    old = capture(db, 0, "2300.01.01")
    cache(db, old, "The Omnian age.")
    new = capture(db, 7, "2301.01.01")
    store = StoryContinuity(db)
    store.decide(
        new[0], predecessor_save_id=None, expected_revision=store.offer(new[0])["offer_revision"]
    )
    linked = continue_from(db, new, old)
    assert linked["decision"] == "continue" and linked["candidates"] == []
    assert [p["save_id"] for p in store.context(new[0])["parts"]] == [old[0]]
    assert "The Omnian age." in story_prompt(store.context(new[0]))


def test_disconnecting_keeps_the_earlier_empire_available_to_relink(db):
    old = capture(db, 0, "2300.01.01")
    cache(db, old)
    new = capture(db, 7, "2301.01.01")
    continue_from(db, new, old)
    store = StoryContinuity(db)
    disconnected = store.decide(
        new[0], predecessor_save_id=None, expected_revision=store.offer(new[0])["offer_revision"]
    )
    assert disconnected["decision"] == "separate" and disconnected["parts"] == []
    assert [c["save_id"] for c in disconnected["candidates"]] == [old[0]]
    continue_from(db, new, old)
    assert [p["save_id"] for p in store.context(new[0])["parts"]] == [old[0]]


def test_a_story_detached_by_rewind_can_be_linked_again(db):
    old = capture(db, 0, "2300.01.01")
    cache(db, old)
    new = capture(db, 7, "2301.01.01")
    continue_from(db, new, old)
    capture(db, 7, "2300.06.01")  # rewind before the link's anchor
    store = StoryContinuity(db)
    offer = store.offer(new[0])
    assert offer["status"] == "rewound" and offer["decision"] == "continue"
    assert [c["save_id"] for c in offer["candidates"]] == [old[0]]
    continue_from(db, new, old)
    assert store.context(new[0])["status"] == "continued"
