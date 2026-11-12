"""The Advisor answer check: its questions come from the save, and its scoring is exact."""

from __future__ import annotations

from scripts.check_advisor_answers import (
    build_cases,
    format_summary,
    run_cases,
    score_answer,
    summarize,
)

BRIEFING = {
    "territory": {
        "planets": {
            "planets": [
                {"name": "Outpost", "population": 40, "buildings": ["Research Labs"]},
                {
                    "name": "Earth",
                    "population": 900,
                    "buildings": ["Alloy Mega-Forges", "Holo-Theatres", "Holo-Theatres"],
                },
                {"name": "Empty", "population": 5000, "buildings": []},
            ]
        }
    },
    "progression": {
        "traditions": {"by_tree": {"Fortification": {"adopted": True}, "unknown": {"picked": []}}},
        "ascension_perks": {"ascension_perks": []},
        "factions": {"factions": [{"name": "Peace Movement"}, {"name": "Free Traders"}]},
    },
    "defense": {
        "starbases": [
            {"system_name": "Sol", "modules": ["Trade Hub"], "buildings": []},
            {
                "system_name": "Sirius",
                "modules": ["Shipyard", "Shipyard", "Anchorage"],
                "buildings": ["Crew Quarters"],
            },
        ]
    },
    "leadership": {"leaders": [{"name": "Qing", "traits": ["Unifier", "Careful"]}]},
    "technology": {
        "in_progress": {
            "physics": {"tech": "tech_lasers_2"},
            "society": {"tech": None},
            "engineering": {"tech": "tech_my_mod"},
        }
    },
    "model_context": {"technology": {"names": {"tech_lasers_2": "Blue Lasers"}}},
    "situation": {"wars": []},
}


def test_the_questions_and_their_answers_come_from_the_briefing() -> None:
    cases = {case.kind: case for case in build_cases(BRIEFING)}

    # The most populous planet that has buildings, each building once.
    assert "Earth" in cases["planet_buildings"].question
    assert cases["planet_buildings"].expected == ["Alloy Mega-Forges", "Holo-Theatres"]
    assert cases["tradition_trees"].expected == ["Fortification"]
    # The starbase with the most to list.
    assert "Sirius" in cases["starbase_fittings"].question
    assert cases["starbase_fittings"].expected == ["Shipyard", "Anchorage", "Crew Quarters"]
    assert cases["leader_traits"].expected == ["Unifier", "Careful"]
    # A technology the game has no name for cannot be asked for by name.
    assert cases["current_research"].expected == ["Blue Lasers"]
    assert cases["factions"].expected == ["Peace Movement", "Free Traders"]
    # Nothing to list, no question.
    assert "ascension_perks" not in cases
    assert "wars" not in cases
    assert build_cases({}) == []


def test_a_name_counts_only_when_its_words_are_given_exactly() -> None:
    score = score_answer(
        "Earth has **alloy mega forges**, two Holo Theatres and a research_lab_3.",
        ["Alloy Mega-Forges", "Holo-Theatres", "Research Labs"],
    )

    assert score.exact == ["Alloy Mega-Forges", "Holo-Theatres"]
    assert score.missing == ["Research Labs"]
    assert score.raw_ids == ["research_lab_3"]


def test_a_longer_name_does_not_also_count_as_the_shorter_one_inside_it() -> None:
    expected = ["Research Complexes", "Advanced Research Complexes"]

    assert score_answer("Advanced Research Complexes.", expected).missing == ["Research Complexes"]
    both = score_answer("Research Complexes and Advanced Research Complexes.", expected)
    assert both.exact == expected
    # Part of a word is not the word.
    assert score_answer("Shipyards", ["Shipyard"]).exact == []


def test_every_question_is_asked_and_a_failed_call_is_counted_not_raised() -> None:
    cases = build_cases(BRIEFING)
    asked: list[str] = []

    def ask(question: str) -> str:
        asked.append(question)
        if "traits" in question:
            raise TimeoutError("model did not answer")
        return "Fortification. Shipyard and Anchorage. Peace Movement, Free Traders."

    results = run_cases("campaign", cases, ask, runs=2, workers=1)
    summary = summarize(results)

    assert len(asked) == 2 * len(cases)
    assert summary["leader_traits"] == {
        "answers": 2,
        "expected": 0,
        "exact": 0,
        "raw_ids": 0,
        "errors": 2,
    }
    assert summary["starbase_fittings"]["exact"] == 4
    assert summary["starbase_fittings"]["expected"] == 6
    assert summary["factions"]["exact"] == summary["factions"]["expected"] == 4
    assert summary["total"]["errors"] == 2
    table = format_summary(summary)
    assert "starbase_fittings" in table and "4/6" in table and "67%" in table
