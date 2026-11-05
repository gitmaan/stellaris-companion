import json
from copy import deepcopy

import pytest

from scripts.experiments.eval_game_knowledge import build_cases
from scripts.experiments.eval_review import REVIEW_RUBRIC, prepare_review, summarize_review


def _run_file(tmp_path, variant):
    run = {
        "variant": variant,
        "cases": [
            {
                "name": "case",
                "prompt": "What should I do?",
                "review_criteria": ["Useful advice."],
                "family": "economy",
                "split": "holdout",
            }
        ],
        "results": [
            {
                "case": "case",
                "game_version": "4.4.6",
                "requested_model": "private-model-id",
                "final_model": "private-model-id",
                "response": "A useful answer.",
                "provider_error": None,
                "elapsed_seconds": 2,
                "assembled_system_prompt": "private-system",
                "assembled_user_prompt": "private-user",
                "repetition": 1,
            },
            {
                "case": "case",
                "game_version": "4.4.6",
                "requested_model": "private-model-id",
                "response": None,
                "provider_error": "Transport failed",
                "elapsed_seconds": 1,
                "repetition": 2,
            },
        ],
    }
    path = tmp_path / f"{variant}.json"
    path.write_text(json.dumps(run))
    return path


def test_review_packets_blind_variants_models_and_prompts_and_leave_ratings_blank(tmp_path):
    paths = [_run_file(tmp_path, variant) for variant in ("before", "after")]
    packet, key = prepare_review(paths, seed=4)
    text = json.dumps(packet)
    for private in ("before", "after", "private-model-id", "private-system", "private-user"):
        assert private not in text
    assert len(packet["samples"]) == 2
    assert len(key["provider_errors"]) == 2
    for sample in packet["samples"]:
        assert all(sample["review"][dimension] is None for dimension in REVIEW_RUBRIC)
    summary = summarize_review(packet, key)
    assert all(group["ratings"]["accuracy"] == {"unreviewed": 1} for group in summary["groups"])
    assert len(summary["provider_errors"]) == 2


def test_accuracy_usefulness_and_naturalness_remain_independent_and_attributed(tmp_path):
    packet, key = prepare_review([_run_file(tmp_path, "candidate")])
    packet["samples"][0]["review"].update(
        reviewer="Independent model review",
        reviewer_kind="model",
        accuracy="sound",
        grounding="supported",
        usefulness="unhelpful",
        naturalness="distracting",
        rationale="Correct but evasive and dominated by roleplay.",
    )
    group = summarize_review(packet, key)["groups"][0]
    assert group["reviewer_kinds"] == {"model": 1}
    assert group["ratings"]["accuracy"] == {"sound": 1}
    assert group["ratings"]["usefulness"] == {"unhelpful": 1}
    assert group["ratings"]["naturalness"] == {"distracting": 1}
    assert "pass" not in group


def test_invalid_unattributed_or_missing_reviews_cannot_silently_become_passes(tmp_path):
    packet, key = prepare_review([_run_file(tmp_path, "candidate")])
    invalid = deepcopy(packet)
    invalid["samples"][0]["review"]["accuracy"] = "passes"
    with pytest.raises(ValueError, match="Invalid accuracy"):
        summarize_review(invalid, key)
    invalid["samples"][0]["review"]["accuracy"] = "sound"
    with pytest.raises(ValueError, match="attributed"):
        summarize_review(invalid, key)
    invalid["samples"] = []
    with pytest.raises(ValueError, match="missing samples"):
        summarize_review(invalid, key)


def test_applicability_suite_covers_quality_and_keeps_holdout_families_separate():
    cases = build_cases("applicability")
    assert len(cases) == len({case.name for case in cases})
    holdout = {case.family for case in cases if case.split == "holdout"}
    tuning = {case.family for case in cases if case.split != "holdout"}
    assert holdout and tuning and not holdout & tuning
    assert {case.split for case in cases} == {"regression", "development", "holdout"}
    assert all(case.references and case.review_criteria and case.briefing for case in cases)
    assert {"accuracy", "grounding", "usefulness", "naturalness"} == REVIEW_RUBRIC.keys()
    assert any(case.previous_turns for case in cases)
    assert any(case.briefing["meta"]["version"] == "unknown" for case in cases)
