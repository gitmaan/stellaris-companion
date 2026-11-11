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


def test_issue_104_technologies_still_in_research_are_not_reported_as_researched(
    monkeypatch, tmp_path
):
    """https://github.com/gitmaan/stellaris-companion/issues/104

    A country's research queues hold ``technology=`` keys too. The entry-wide
    lookup counted them, so the technology being researched was reported as
    already researched (and as an available option at the same time), a queued
    naval technology raised the naval cap early, and a level-3 repeatable was
    read as level 1 or 2. A special project at the head of a queue hid the
    technology waiting behind it.
    """
    researched = ["tech_colonization_1", "tech_repeatable_naval_cap"]
    queued = ["tech_cryostasis_1", "tech_doctrine_navy_size_1", "tech_repeatable_naval_cap"]
    sections = {
        "player": [{"name": "Reporter", "country": "0"}],
        "galaxy": {"difficulty": "ensign"},
        "country": {
            "0": country(
                "Colony Union",
                government={"civics": []},
                used_naval_capacity="20",
                tech_status={
                    "physics_queue": [{"technology": "tech_cryostasis_1", "progress": "120"}],
                    "society_queue": [
                        {"special_project": "1", "progress": "205.4"},
                        {"technology": "tech_doctrine_navy_size_1", "progress": "82.8"},
                    ],
                    "engineering_queue": [
                        {"technology": "tech_repeatable_naval_cap", "progress": "5"}
                    ],
                    "alternatives": {
                        "physics": ["tech_cryostasis_1"],
                        "society": ["tech_doctrine_navy_size_1"],
                        "engineering": ["tech_repeatable_naval_cap"],
                    },
                },
            )
        },
    }

    def ingest(duplicate_values):
        payload = ingest_synthetic_save(
            monkeypatch, tmp_path, sections, duplicate_values=duplicate_values
        )
        return advisor_request(monkeypatch, payload, "What have I researched?")[2]

    model_briefing = ingest(
        {
            # What the save holds anywhere under the country, queues included...
            ("country", "0", "technology"): researched + queued,
            # ...and what tech_status itself lists as finished, with levels.
            ("country", "0", "technology", "tech_status"): researched,
            ("country", "0", "level", "tech_status"): ["1", "3"],
        }
    )

    technology = model_briefing["technology"]
    assert technology["completed_count"] == 2
    assert technology["researched_techs"] == ["New Worlds Protocol", "Fleet Management Procedures"]
    assert technology["repeatables"] == {"naval_cap": 3}
    assert technology["repeatables_total_levels"] == 3
    assert technology["in_progress"]["physics"]["tech"] == "tech_cryostasis_1"
    society = technology["in_progress"]["society"]
    assert society["tech"] is None
    assert society["special_project"] is True
    assert society["queued_techs"] == ["tech_doctrine_navy_size_1"]
    naming = model_briefing["model_context"]["technology"]
    assert naming["names"]["tech_doctrine_navy_size_1"] == "Doctrine: Fleet Support"
    assert "is not researched yet" in naming["instruction"]

    # Naval cap: three repeatable levels count, the queued doctrine does not.
    naval = model_briefing["military"]["naval_capacity"]
    assert naval["max"] == 110
    assert naval["analysis"]["breakdown"]["flat_additions"] == {"Repeatable naval-cap tech": 60.0}

    # Saves that repeat the key per level instead of writing level= still count levels.
    older = ingest(
        {
            ("country", "0", "technology"): ["tech_repeatable_naval_cap"] * 2 + queued,
            ("country", "0", "technology", "tech_status"): ["tech_repeatable_naval_cap"] * 2,
        }
    )
    assert older["technology"]["repeatables"] == {"naval_cap": 2}
    assert older["technology"]["completed_count"] == 1
