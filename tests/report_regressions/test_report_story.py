"""An empire change can continue a story without changing historical ownership."""

import json
from contextlib import closing

from backend.core.database import GameDatabase
from backend.core.story_continuity import StoryContinuity
from backend.mcp.context import StellarisMcpContext

from ._synthetic import country, ingest_synthetic_save, persist_snapshot, synthetic_meta


def test_issue_95_country_change_continues_story_with_separate_empire_evidence(
    monkeypatch, tmp_path
):
    """https://github.com/gitmaan/stellaris-companion/issues/95

    The player follows the Barcalan Collective after the Omnian Core. The
    galaxy is unchanged, but no save evidence establishes how the Core ended.
    """
    countries = {
        "0": country(
            "Omnian Core",
            government={"authority": "auth_machine_intelligence"},
            ethos={"ethic": "ethic_gestalt_consciousness"},
            owned_planets=["1", "2"],
        ),
        "7": country(
            "Barcalan Collective",
            government={"authority": "auth_hive_mind"},
            ethos={"ethic": "ethic_gestalt_consciousness"},
            owned_planets=["3"],
        ),
    }
    with closing(GameDatabase(tmp_path / "story.db")) as db:
        perspectives = []
        for player, name, date in [
            (0, "Omnian Core", "2300.01.01"),
            (7, "Barcalan Collective", "2301.01.01"),
        ]:
            payload = ingest_synthetic_save(
                monkeypatch,
                tmp_path,
                {
                    "galaxy": {"name": "synthetic-galaxy-95"},
                    "player": [{"name": "Player", "country": str(player)}],
                    "country": countries,
                },
                meta=synthetic_meta(name=name, date=date),
                filename=f"perspective-{player}.sav",
            )
            _, snapshot, session = persist_snapshot(db, payload)
            save_id = db.get_save_id_for_session(session)
            perspectives.append((save_id, snapshot, session))
        old, child = perspectives
        db.upsert_chronicle_by_save_id(
            save_id=old[0],
            session_id=old[2],
            language="en",
            event_count=0,
            snapshot_count=1,
            chronicle_text="The Core remembers.",
            chapters_json=json.dumps(
                {
                    "chapters": [
                        {
                            "number": 1,
                            "title": "The Core",
                            "narrative": "The Core remembers.",
                            "summary": "The Core remembers.",
                            "start_date": "2300.01.01",
                            "end_date": "2300.01.01",
                            "start_snapshot_id": old[1],
                            "end_snapshot_id": old[1],
                        }
                    ]
                }
            ),
        )
        original = db.get_chronicle_by_save_id(old[0])
        store = StoryContinuity(db)
        offer = store.offer(child[0])
        assert [item["save_id"] for item in offer["candidates"]] == [old[0]]
        store.decide(
            child[0], predecessor_save_id=old[0], expected_revision=offer["offer_revision"]
        )

        context = StellarisMcpContext(db=db)
        advice = context.get_strategy_context()
        assert "The Core remembers." in advice["story_context"]
        voice = advice["response_guidance"]["advisor_voice"]
        assert voice["empire_identity"]["name"] == "Barcalan Collective"
        assert voice["empire_identity"]["authority"] == "Hive Mind"
        assert "does not establish destruction" in advice["story_context"]
        assert db.get_all_events_by_save_id(save_id=child[0]) == []
        assert db.get_snapshot_range_for_save(child[0])["snapshot_count"] == 1
        assert db.get_chronicle_by_save_id(old[0]) == original

        # An explicit switch back follows the original identity, not a merged story.
        assert store.context(old[0])["parts"] == []
        assert old[0] != child[0]
