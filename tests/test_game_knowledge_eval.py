"""Keep provider evaluation on the selected game version and production selection path."""

from types import SimpleNamespace

import pytest

from scripts.experiments import eval_game_knowledge as evaluation


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
            return SimpleNamespace(
                text="recorded response", model="test", schema_fallback_used=False
            )

    monkeypatch.setattr(evaluation, "create_advisor_generator", lambda **kwargs: Generator())
    args = SimpleNamespace(
        suite=suite,
        provider="custom",
        base_url="http://unused.invalid",
        timeout=1,
        snapshots_dir=None,
        max_output_tokens=100,
    )
    case = next(case for case in evaluation.build_cases(suite) if case.name == case_name)

    result = evaluation.run_case(args, "test", case)

    assert result.provider_error is None
    assert captured["user_prompt"] == case.prompt
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
        base_url="http://unused.invalid",
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
