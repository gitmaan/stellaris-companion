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
