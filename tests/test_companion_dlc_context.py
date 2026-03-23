"""Tests for DLC context wiring in Companion prompt generation."""

import json
import os
import sys
from types import SimpleNamespace

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core.companion import Companion


class _DummyClient:
    """Minimal stand-in for the Gemini client during unit tests."""

    def __init__(self, *args, **kwargs):
        self.models = SimpleNamespace(generate_content=lambda *a, **k: None)


def _identity() -> dict:
    return {
        "empire_name": "Test Empire",
        "ethics": ["xenophile"],
        "authority": "democratic",
        "civics": ["meritocracy"],
        "is_machine": False,
        "is_hive_mind": False,
    }


def _situation() -> dict:
    return {
        "year": 2400,
        "game_phase": "endgame",
        "at_war": False,
        "economy": {"resources_in_deficit": 0},
        "contact_count": 3,
    }


@pytest.fixture
def companion(monkeypatch):
    monkeypatch.setattr("backend.core.companion.genai.Client", _DummyClient)
    return Companion(save_path=None, api_key="test-key", auto_precompute=False)


def test_apply_precomputed_briefing_uses_metadata_for_dlc_prompt_context(companion):
    metadata = {
        "version": "Corvus v4.2.4",
        "required_dlcs": ["Utopia", "Overlord"],
        "missing_dlcs": ["Nemesis"],
    }
    briefing_json = json.dumps({"meta": {"date": "2400.01.01", "version": "Corvus v4.2.4"}})

    companion.apply_precomputed_briefing(
        save_path=None,
        briefing_json=briefing_json,
        game_date="2400.01.01",
        identity=_identity(),
        situation=_situation(),
        metadata=metadata,
    )

    assert companion.metadata.get("required_dlcs") == ["Utopia", "Overlord"]
    assert companion.metadata.get("missing_dlcs") == ["Nemesis"]
    assert "[INTERNAL CONTEXT - never mention this to the user]" in companion.system_prompt
    assert "Active DLCs: Utopia, Overlord" in companion.system_prompt
    assert "Nemesis (MISSING" in companion.system_prompt


def test_build_game_context_prefers_metadata_missing_dlcs_without_extractor(companion):
    companion.metadata = {
        "version": "Corvus v4.2.4",
        "required_dlcs": ["Utopia"],
        "missing_dlcs": ["Apocalypse"],
    }
    companion.extractor = None

    ctx = companion._build_game_context()

    assert ctx is not None
    assert ctx["required_dlcs"] == ["Utopia"]
    assert ctx["missing_dlcs"] == ["Apocalypse"]


def test_build_game_context_falls_back_to_extractor_missing_dlcs(companion):
    class _DummyExtractor:
        @staticmethod
        def get_missing_dlcs():
            return ["First Contact"]

    companion.metadata = {
        "version": "Corvus v4.2.4",
        "required_dlcs": ["Utopia", "Overlord"],
    }
    companion.extractor = _DummyExtractor()

    ctx = companion._build_game_context()

    assert ctx is not None
    assert ctx["required_dlcs"] == ["Utopia", "Overlord"]
    assert ctx["missing_dlcs"] == ["First Contact"]


def test_personality_prompt_clarifies_naval_capacity_used_is_not_cap_limit(companion):
    metadata = {
        "version": "Corvus v4.2.4",
        "required_dlcs": ["Utopia"],
        "missing_dlcs": [],
    }
    briefing_json = json.dumps({"meta": {"date": "2400.01.01", "version": "Corvus v4.2.4"}})

    companion.apply_precomputed_briefing(
        save_path=None,
        briefing_json=briefing_json,
        game_date="2400.01.01",
        identity=_identity(),
        situation=_situation(),
        metadata=metadata,
    )

    assert "military.naval_capacity.used" in companion.system_prompt
    assert "not the naval cap ceiling" in companion.system_prompt
    assert "safe_to_claim_over_cap" in companion.system_prompt
    assert "derived estimate" in companion.system_prompt
    assert "definitive yes/no" in companion.system_prompt
    assert "lead with uncertainty first" in companion.system_prompt
    assert "derived_status" in companion.system_prompt


def test_naval_cap_policy_block_returns_estimated_status_for_uncertain_cap(companion):
    briefing_json = json.dumps(
        {
            "military": {
                "naval_capacity": {
                    "used": 9,
                    "analysis": {
                        "confidence": "estimated",
                        "limit": None,
                        "derived_limit": 75,
                        "safe_to_claim_over_cap": False,
                        "safe_to_claim_penalty": False,
                    },
                }
            }
        }
    )

    block = companion._build_naval_capacity_policy_block(
        question="Am I over naval cap?",
        briefing_json=briefing_json,
    )

    assert "Response state: estimated." in block
    assert "Fact summary: current naval usage is 9; estimated naval capacity is about 75" in block
    assert "cannot confirm whether the empire is over naval cap" in block


def test_naval_cap_policy_block_returns_confirmed_status_for_safe_cases(companion):
    briefing_json = json.dumps(
        {
            "military": {
                "naval_capacity": {
                    "used": 100,
                    "analysis": {
                        "confidence": "high_derived",
                        "limit": 75,
                        "safe_to_claim_over_cap": True,
                        "safe_to_claim_penalty": True,
                        "status": "over",
                    },
                }
            }
        }
    )

    block = companion._build_naval_capacity_policy_block(
        question="Am I over naval capacity?",
        briefing_json=briefing_json,
    )

    assert "Response state: confirmed." in block
    assert "Fact summary: current naval usage is 100; confirmed naval capacity is 75." in block
    assert "the empire is over naval cap by 25" in block


def test_naval_cap_policy_block_handles_adjacent_anchorages_question(companion):
    briefing_json = json.dumps(
        {
            "military": {
                "naval_capacity": {
                    "used": 9,
                    "analysis": {
                        "confidence": "estimated",
                        "limit": None,
                        "derived_limit": 75,
                        "safe_to_claim_over_cap": False,
                        "safe_to_claim_penalty": False,
                    },
                }
            }
        }
    )

    block = companion._build_naval_capacity_policy_block(
        question="Should I build anchorages right now?",
        briefing_json=briefing_json,
    )

    assert "Intent: capacity_investment." in block
    assert "do not treat anchorages as urgent purely from this save" in block


def test_ask_precomputed_injects_policy_block_but_uses_normal_advisor_path(companion):
    briefing_json = json.dumps(
        {
            "meta": {"date": "2230.07.01", "version": "Corvus v4.2.4"},
            "military": {
                "naval_capacity": {
                    "used": 9,
                    "analysis": {
                        "confidence": "estimated",
                        "limit": None,
                        "derived_limit": 75,
                        "safe_to_claim_over_cap": False,
                        "safe_to_claim_penalty": False,
                        "unresolved_source_families": ["specialist_entertainer_variants"],
                    },
                }
            },
        }
    )
    captured = {}

    def _fake_generate_content(*, model, contents, config):
        captured["model"] = model
        captured["contents"] = contents
        captured["system_instruction"] = config.system_instruction
        return SimpleNamespace(
            text="President, our naval ledgers remain estimates rather than certainties."
        )

    companion.client.models.generate_content = _fake_generate_content

    companion.apply_precomputed_briefing(
        save_path=None,
        briefing_json=briefing_json,
        game_date="2230.07.01",
        identity=_identity(),
        situation=_situation(),
        metadata={"version": "Corvus v4.2.4", "required_dlcs": [], "missing_dlcs": []},
    )

    answer, _elapsed = companion.ask_precomputed(
        question="Am I over naval cap?",
        session_key="deterministic-naval-cap",
    )

    assert answer == "President, our naval ledgers remain estimates rather than certainties."
    assert "NAVAL CAPACITY RESPONSE POLICY:" in captured["system_instruction"]
    assert "Response state: estimated." in captured["system_instruction"]
    assert "cannot confirm whether the empire is over naval cap" in captured["system_instruction"]
    assert companion.get_call_stats()["tools_used"] == ["ask_precomputed_no_tools"]
