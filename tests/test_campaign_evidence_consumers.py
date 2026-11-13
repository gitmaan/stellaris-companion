"""Exercise the production request and historical paths with contradictory evidence."""

import hashlib
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from backend.core.advisor_providers import AdvisorGenerationResult
from backend.core.chronicle import _chronicle_game_knowledge
from backend.core.chronicle_store import compact_chronicle_context
from backend.core.companion import FALLBACK_SYSTEM_PROMPT, Companion
from backend.core.model_briefing import build_model_briefing
from stellaris_companion.evidence_policy import build_evidence_policy, build_evidence_prompt
from stellaris_companion.personality import build_optimized_prompt


class RecordingProvider:
    def __init__(self, provider):
        self.provider = provider
        self.request = None

    def generate(self, **kwargs):
        self.request = kwargs
        return AdvisorGenerationResult(
            text="A recorded answer.",
            model="test-model",
            requested_model="test-model",
            provider=self.provider,
            completion={"status": "complete"},
        )


def make_companion(monkeypatch, provider="openrouter"):
    monkeypatch.setattr(
        "backend.core.companion.genai.Client", lambda **kwargs: SimpleNamespace(models=None)
    )
    recorder = RecordingProvider(provider)
    companion = Companion(
        auto_precompute=False,
        api_key="test-key",
        advisor_provider=provider,
        advisor_model="test-model",
        advisor_api_key="test-key",
        advisor_base_url="http://127.0.0.1:1" if provider == "custom" else None,
        advisor_generator=recorder,
    )
    return companion, recorder


def activate(companion, briefing):
    companion.apply_precomputed_briefing(
        save_path=None,
        briefing_json=json.dumps(briefing),
        game_date=briefing.get("meta", {}).get("date"),
        identity=briefing.get("identity", {}),
        situation=briefing.get("situation", {}),
        metadata=briefing.get("meta", {}),
    )


@pytest.mark.parametrize("provider", ["gemini", "openrouter", "custom", "chatgpt"])
@pytest.mark.parametrize(
    "authority,civics,label",
    [
        ("machine_intelligence", ["machine_servitor", "machine_replication"], "Rogue Servitor"),
        ("machine_intelligence", ["machine_assimilator"], "Driven Assimilator"),
        ("hive_mind", ["hive_devouring_swarm"], "Devouring Swarm"),
        ("democratic", ["meritocracy"], "Meritocracy"),
        ("modded_authority", ["modded_logistics"], "modded_logistics"),
    ],
)
def test_full_request_preserves_observed_identity_across_providers(
    monkeypatch, provider, authority, civics, label
):
    companion, recorder = make_companion(monkeypatch, provider)
    briefing = {
        "meta": {
            "version": "Cygnus v4.5.2",
            "date": "2300.01.01",
            "missing_dlcs": ["Synthetic Dawn", "Utopia"],
        },
        "identity": {"empire_name": "Test Empire", "authority": authority, "civics": civics},
        "situation": {"economy": None},
    }
    original = deepcopy(briefing)
    activate(companion, briefing)
    source = companion.capture_advisor_source()
    # Later live changes must not contaminate this request's captured evidence.
    companion.metadata = {"version": "v4.3.5", "required_dlcs": []}
    companion.system_prompt = "This stale cached interpretation must not be reused."
    reply = companion.ask_precomputed_with_context(
        question="Can you explain my options and what still needs checking?",
        session_key="evidence",
        source=source,
        persist_memory=False,
    )

    assert "error" not in reply.stats
    assert source.source_hash == hashlib.sha256(source.briefing_json.encode()).hexdigest()
    assert json.loads(source.briefing_json) == original == briefing
    system = recorder.request["system_prompt"]
    assert label in system
    assert "stale cached interpretation" not in system
    assert "do NOT exist in this game" not in system
    assert "ALL numbers and factual claims" not in system
    assert "partial campaign snapshot" in system
    assert build_evidence_prompt("advisor") in system
    assert "safe_to_claim_over_cap" in system  # Applies to machine/hive voices too.
    payload = recorder.request["user_prompt"].split("```json\n", 1)[1].split("\n```", 1)[0]
    model_briefing = json.loads(payload)
    assert model_briefing["identity"] == original["identity"]
    assert "missing_dlcs" not in model_briefing["meta"]
    context = model_briefing["model_context"]
    assert context["content_availability"]["base_game_dlcs"] == [
        "Humanoids",
        "Synthetic Dawn",
        "Utopia",
    ]
    assert context["content_availability"]["dlc_evidence_status"] == "not_recorded"
    assert context["evidence"] == build_evidence_policy()


@pytest.mark.parametrize("version", ["v4.3.5", "v4.3.6", "Cygnus v4.5.2", "unknown"])
def test_historical_compaction_retains_identity_and_content_evidence(version):
    briefing = {
        "meta": {
            "version": version,
            "required_dlcs": [f"Pack {n}" for n in range(20)],
            "required_dlcs_status": "reported",
            "mods": [f"Mod {n}" for n in range(20)],
        },
        "identity": {
            "authority": "machine_intelligence",
            "civics": [f"mod_civic_{n}" for n in range(15)] + ["machine_servitor"],
        },
    }
    compact = compact_chronicle_context(briefing)
    assert compact["meta"] == briefing["meta"]
    assert compact["identity"] == briefing["identity"]
    expected = build_model_briefing(briefing)["model_context"]
    actual = build_model_briefing(compact)["model_context"]
    assert actual == expected
    prompt = _chronicle_game_knowledge(build_model_briefing(compact))
    assert "Rogue Servitor" in prompt
    assert build_evidence_prompt("chronicle") in prompt
    assert "Do not turn suggested actions into historical events" in prompt


@pytest.mark.parametrize("authority", ["machine_intelligence", "hive_mind", "democratic"])
def test_unknown_situation_does_not_turn_into_peace_or_zero_values(authority):
    prompt = build_optimized_prompt({"authority": authority}, {"economy": None})
    assert "0 deficits" not in prompt
    assert "0 resource inefficiencies" not in prompt
    assert "peace" not in prompt
    assert "Year 2200" not in prompt
    assert "unknown" in prompt


def test_fallback_uses_shared_policy_instead_of_prohibiting_calculations():
    assert build_evidence_prompt("advisor") in FALLBACK_SYSTEM_PROMPT
    assert "NEVER estimate" not in FALLBACK_SYSTEM_PROMPT
