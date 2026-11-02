"""Keep provider evaluation on the selected game version and production selection path."""

import json
from types import SimpleNamespace

import pytest

from backend.core.advisor_providers import AdvisorGenerationResult
from scripts.experiments import eval_game_knowledge as evaluation


def test_repeated_evaluations_record_each_independent_sample(monkeypatch, tmp_path):
    output = tmp_path / "results.json"
    monkeypatch.setattr(
        evaluation,
        "parse_args",
        lambda: SimpleNamespace(
            suite="evidence",
            provider="custom",
            models=["test"],
            repeats=2,
            case_names=["supported_calculation"],
            list=False,
            json_out=output,
        ),
    )
    calls = []

    def run(args, model, case):
        calls.append(case.name)
        return evaluation.EvalResult(
            case=case.name,
            purpose=case.purpose,
            game_version="v4.5.2",
            provider="custom",
            requested_model=model,
            final_model=model,
            elapsed_seconds=0,
            response="Six months",
            provider_error=None,
            schema_fallback_used=False,
        )

    monkeypatch.setattr(evaluation, "run_case", run)
    assert evaluation.main() == 0
    payload = json.loads(output.read_text())
    assert calls == ["supported_calculation", "supported_calculation"]
    assert [row["repetition"] for row in payload["results"]] == [1, 2]
    assert all(row["human_label"] is None for row in payload["results"])
    assert {"accuracy", "grounding", "usefulness", "naturalness"} == payload["review_rubric"].keys()


def test_holdout_selection_is_explicit_and_does_not_make_provider_calls(monkeypatch, capsys):
    monkeypatch.setattr(
        evaluation,
        "parse_args",
        lambda: SimpleNamespace(
            suite="applicability", repeats=1, split="holdout", case_names=None, list=True
        ),
    )
    monkeypatch.setattr(
        evaluation, "run_case", lambda *args: pytest.fail("Listing must be offline")
    )
    assert evaluation.main() == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines and all("\tholdout\t" in line for line in lines)
    assert not any("energy_runway_unknown_mode" in line for line in lines)


@pytest.mark.parametrize(
    "suite,case_name,expected,excluded",
    [
        ("cygnus", "cygnus_conserve", "-50% Specialist Job Efficiency", "A normal Anchorage adds"),
        (
            "pegasus",
            "anchorage_costs",
            "A normal Anchorage adds 5 Naval Capacity",
            "-50% Specialist Job Efficiency",
        ),
    ],
)
def test_provider_eval_uses_selected_suite_and_question_topics(
    monkeypatch, suite, case_name, expected, excluded
):
    captured = {}

    class Generator:
        def generate(self, **kwargs):
            captured.update(kwargs)
            return AdvisorGenerationResult(
                text="recorded response", model="test", requested_model="test", provider="custom"
            )

    monkeypatch.setattr(evaluation, "create_advisor_generator", lambda **kwargs: Generator())
    args = SimpleNamespace(
        suite=suite,
        provider="custom",
        base_url="http://127.0.0.1:1",
        timeout=1,
        snapshots_dir=None,
        max_output_tokens=100,
    )
    case = next(case for case in evaluation.build_cases(suite) if case.name == case_name)

    result = evaluation.run_case(args, "test", case)

    assert result.provider_error is None
    assert result.game_version == evaluation.EVAL_VERSIONS[suite]
    assert case.prompt in captured["user_prompt"]
    assert '"model_context"' in captured["user_prompt"]
    assert "ASK MODE (NO TOOLS)" in captured["system_prompt"]
    assert "EMPIRE IDENTITY:" in captured["system_prompt"]
    assert result.assembled_system_prompt == captured["system_prompt"]
    assert result.assembled_user_prompt == captured["user_prompt"]
    assert expected in captured["system_prompt"]
    assert excluded not in captured["system_prompt"]
    assert "Psionics & the Shroud" not in captured["system_prompt"]


def test_cygnus_chronicle_eval_keeps_evidence_boundaries(monkeypatch):
    captured = {}

    class Chronicle:
        def __init__(self, **kwargs):
            pass

        def _generate_structured_content(self, **kwargs):
            captured.update(kwargs)
            return None, SimpleNamespace(text="arrival", model="test", schema_fallback_used=False)

    monkeypatch.setattr(evaluation, "create_advisor_generator", lambda **kwargs: object())
    monkeypatch.setattr(evaluation, "ChronicleGenerator", Chronicle)
    args = SimpleNamespace(
        suite="cygnus",
        provider="custom",
        base_url="http://127.0.0.1:1",
        timeout=1,
        snapshots_dir=None,
        max_output_tokens=100,
    )
    case = next(case for case in evaluation.build_cases("cygnus") if case.structured)

    result = evaluation.run_case(args, "test", case)

    assert result.provider_error is None
    prompt = captured["game_knowledge_context"]
    assert "through 4.5.2" in prompt
    assert "never as evidence that an event occurred" in prompt
    assert "Taming or slaying the Toxic God" in prompt


def test_evidence_eval_includes_production_identity_and_previous_turns(monkeypatch):
    requests = []

    class Generator:
        def generate(self, **kwargs):
            requests.append(kwargs)
            return AdvisorGenerationResult(
                text="An evaluation answer.",
                model="test",
                requested_model="test",
                provider="custom",
            )

    monkeypatch.setattr(evaluation, "create_advisor_generator", lambda **kwargs: Generator())
    args = SimpleNamespace(
        suite="evidence",
        provider="custom",
        base_url="http://127.0.0.1:1",
        timeout=1,
        snapshots_dir=None,
        max_output_tokens=100,
    )
    case = evaluation.build_cases("evidence")[0]

    result = evaluation.run_case(args, "test", case)

    assert result.provider_error is None
    assert len(requests) == 1
    assert "Rogue Servitor" in result.assembled_system_prompt
    assert "ASK MODE (NO TOOLS)" in result.assembled_system_prompt
    assert "RECENT CONVERSATION" in result.assembled_user_prompt
    assert case.previous_turns[0]["answer"] in result.assembled_user_prompt
    assert "Current EMPIRE STATE overrides" in result.assembled_system_prompt
    assert '"unreported_dlc_status":"unknown"' in result.assembled_user_prompt


def test_evidence_eval_records_provider_failures_instead_of_treating_errors_as_answers(monkeypatch):
    class Generator:
        def generate(self, **kwargs):
            raise RuntimeError("synthetic provider failure")

    monkeypatch.setattr(evaluation, "create_advisor_generator", lambda **kwargs: Generator())
    args = SimpleNamespace(
        suite="evidence",
        provider="custom",
        base_url="http://127.0.0.1:1",
        timeout=1,
        snapshots_dir=None,
        max_output_tokens=100,
    )
    result = evaluation.run_case(args, "test", evaluation.build_cases("evidence")[0])

    assert result.response is None
    assert result.provider_error == "synthetic provider failure"
    assert "ASK MODE (NO TOOLS)" in result.assembled_system_prompt


@pytest.mark.parametrize("version", ["v4.3.5", "unknown"])
def test_evidence_eval_records_actual_campaign_version(monkeypatch, version):
    class Generator:
        def generate(self, **kwargs):
            return AdvisorGenerationResult(
                text="An evaluation answer.",
                model="test",
                requested_model="test",
                provider="custom",
            )

    monkeypatch.setattr(evaluation, "create_advisor_generator", lambda **kwargs: Generator())
    args = SimpleNamespace(
        suite="evidence",
        provider="custom",
        base_url="http://127.0.0.1:1",
        timeout=1,
        snapshots_dir=None,
        max_output_tokens=100,
    )
    case = next(
        case
        for case in evaluation.build_cases("evidence")
        if case.briefing["meta"].get("version") == version
    )

    result = evaluation.run_case(args, "test", case)

    assert result.provider_error is None
    assert result.game_version == version
    assert f'"game_version":"{version}"' in result.assembled_user_prompt
