"""Foundational Trade meaning survives topic selection within its version scope."""

import json

import pytest
from test_campaign_evidence_consumers import activate, make_companion

from stellaris_companion.game_knowledge import build_game_knowledge_prompt, load_game_knowledge


@pytest.mark.parametrize("version", ["4.0", "4.1.5", "4.2.4", "4.3.0", "4.3.5", "4.4.5"])
@pytest.mark.parametrize(
    "topic", ["", "What should I prioritize?", "이 수치로 무엇을 알 수 있나요?"]
)
def test_older_packs_retain_trade_meaning_without_a_topic_match(version, topic):
    prompt = build_game_knowledge_prompt(
        version, purpose="advisor", topics=topic, max_topic_sections=0
    )
    assert "## Critical 4.x Baseline" in prompt
    assert "Trade is the Galactic Market currency" in prompt
    assert "Energy is an ordinary resource" in prompt
    assert "stockpiled resource" in prompt
    assert "Trade Routes are removed" in prompt
    # The compact foundation must not drag unrelated reference tables into every request.
    assert "Empire Total (late-game)" not in prompt
    assert "### Naval Capacity & Fleet Scale" not in prompt
    assert "### Trade & Logistics" not in prompt
    assert "Base-Game Integrations" not in prompt  # Later rules remain version-scoped.


@pytest.mark.parametrize("provider", ["gemini", "openrouter", "custom", "chatgpt"])
@pytest.mark.parametrize("version", ["Cetus v4.3.0", "Cetus v4.3.5"])
def test_actual_trade_request_retains_foundation_and_coverage(monkeypatch, provider, version):
    companion, recorder = make_companion(monkeypatch, provider)
    briefing = {
        "meta": {"version": version, "date": "2300.01.01"},
        "identity": {"authority": "democratic"},
        "economy": {"resources": {"stockpiles": {"trade": 420}}},
    }
    activate(companion, briefing)
    source = companion.capture_advisor_source()
    response = companion.ask_precomputed_with_context(
        question=(
            "How much Trade do we have, is it increasing or decreasing, "
            "and can it cover market purchases?"
        ),
        session_key="trade-retrieval",
        source=source,
        persist_memory=False,
    )
    assert "error" not in response.stats
    prompt = recorder.request["system_prompt"]
    assert "Trade is the Galactic Market currency" in prompt
    assert "stockpiled resource" in prompt
    assert json.loads(source.briefing_json) == briefing
    if version.endswith("4.3.0"):
        assert "Mechanics coverage is verified only through 4.3." in prompt
        assert "do not assume older details remained unchanged" in prompt
    else:
        assert "Verified mechanics for Cetus v4.3.5" in prompt


@pytest.mark.parametrize("version", ["4.5.0", "4.5.2", "4.6.0", "unknown", "3.14.0"])
def test_trade_foundation_does_not_cross_unsupported_or_breaking_boundaries(version):
    for topics in (None, "trade and market purchases"):
        prompt = build_game_knowledge_prompt(version, purpose="advisor", topics=topics)
        assert "Trade is the Galactic Market currency" not in prompt
        assert "Trade Routes are removed" not in prompt
    knowledge = load_game_knowledge(version)
    if version.startswith("4.5"):
        assert knowledge.status == "partial"
        assert knowledge.notes_only


def test_chronicle_topic_selection_retains_older_trade_foundation():
    prompt = build_game_knowledge_prompt(
        "4.3.0", purpose="chronicle", topics="Diplomacy and exploration", max_topic_sections=0
    )
    assert "Trade is the Galactic Market currency" in prompt
    assert "Do not turn suggested actions into historical events" in prompt
