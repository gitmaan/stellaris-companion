"""Technology misreadings reported by players (#104)."""

from __future__ import annotations

from ._synthetic import advisor_request, country, ingest_synthetic_save


def test_issue_104_research_options_carry_their_in_game_names(monkeypatch, tmp_path):
    """https://github.com/gitmaan/stellaris-companion/issues/104

    The game offered "Automated Colony Ships". Its save ID is
    ``tech_cryostasis_1``, which the Advisor received with no name, so the
    option looked like a different technology and the real one looked missing.
    """
    sections = {
        "player": [{"name": "Reporter", "country": "0"}],
        "galaxy": {"difficulty": "ensign"},
        "country": {
            "0": country(
                "Colony Union",
                government={"civics": []},
                tech_status={
                    "physics_queue": [{"technology": "tech_lasers_2", "progress": "120"}],
                    "alternatives": {
                        "physics": ["tech_cryostasis_1", "tech_my_mod_reactor"],
                        "society": ["tech_colonization_2"],
                        "engineering": [],
                    },
                },
            )
        },
    }
    payload = ingest_synthetic_save(
        monkeypatch,
        tmp_path,
        sections,
        duplicate_values={
            ("country", "0", "technology"): ["tech_colonization_1", "tech_my_mod_drive"]
        },
    )

    _, _, model_briefing = advisor_request(
        monkeypatch, payload, "Which physics technologies can I research?"
    )

    # The save-derived IDs are passed through unchanged.
    technology = model_briefing["technology"]
    assert technology["available_techs"]["physics"] == ["tech_cryostasis_1", "tech_my_mod_reactor"]
    assert technology["in_progress"]["physics"]["tech"] == "tech_lasers_2"

    naming = model_briefing["model_context"]["technology"]
    assert naming["names"]["tech_cryostasis_1"] == "Automated Colony Ships"
    assert naming["names"]["tech_colonization_2"] == "Atmospheric Filtering"
    assert naming["names"]["tech_lasers_2"] == "Blue Lasers"
    # Wilderness empires see the same technology under another name.
    assert naming["also_shown_as"]["tech_cryostasis_1"] == ["Seedling Incubation"]
    # Modded or newer IDs get no invented name.
    assert "tech_my_mod_reactor" not in naming["names"]
    assert "tech_cryostasis_1 is Automated Colony Ships" in naming["instruction"]
    assert "never invent an ID" in naming["instruction"]
    # Researched technologies reach the model under their in-game names too.
    assert technology["researched_techs"] == ["New Worlds Protocol", "tech_my_mod_drive"]
