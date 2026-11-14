"""Saves the app could not read because of a Fallen Empire's relation entry (#135)."""

from __future__ import annotations

import json

from ._synthetic import country, ingest_synthetic_save, synthetic_meta


def test_issue_135_a_fallen_empire_without_an_opinion_score_does_not_stop_the_save(
    monkeypatch, tmp_path
):
    """https://github.com/gitmaan/stellaris-companion/issues/135

    Two Fallen Empires in a Cygnus 4.5.4 save. One has a relation entry for the
    player that carries no opinion score; the other has one. Reading the first
    raised KeyError('relation_current'), the whole save failed to load, and the
    Advisor had nothing to answer from.
    """
    sections = {
        "player": [{"name": "Reporter", "country": "0"}],
        "country": {
            "0": country("Knights of the Long Road", military_power="12000"),
            "1": country(
                "Silent Wardens",
                type="fallen_empire",
                ethos={"ethic": "ethic_fanatic_xenophobe"},
                military_power="90000",
                relations_manager={
                    "relation": [
                        {"owner": "1", "country": "5", "relation_current": "3"},
                        # The player's entry, with no opinion score.
                        {"owner": "1", "country": "0", "border_range": "420"},
                    ]
                },
            ),
            "2": country(
                "Keepers of Knowledge",
                type="fallen_empire",
                ethos={"ethic": "ethic_fanatic_materialist"},
                military_power="80000",
                relations_manager={
                    "relation": {"owner": "2", "country": "0", "relation_current": "-40"}
                },
            ),
        },
    }

    payload = ingest_synthetic_save(
        monkeypatch,
        tmp_path,
        sections,
        meta=synthetic_meta(
            name="Knights of the Long Road", date="2254.08.01", version="Cygnus v4.5.4"
        ),
    )

    fallen = json.loads(payload["briefing_json"])["fallen_empires"]
    by_id = {empire["country_id"]: empire for empire in fallen["fallen_empires"]}
    assert set(by_id) == {1, 2}
    # No score in the save means no score in the briefing, not a made-up zero.
    assert "opinion_of_player" not in by_id[1]
    assert by_id[1]["archetype"] == "Militant Isolationists"
    assert by_id[2]["opinion_of_player"] == -40
