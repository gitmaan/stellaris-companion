"""Model rollovers must preserve family, stability, explicit choices and provenance."""

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from backend.core.advisor_providers import (
    AdvisorProviderConfig,
    AdvisorProviderError,
    GeminiAdvisorGenerator,
    OpenAICompatibleAdvisorGenerator,
)
from stellaris_companion.model_catalog import (
    ModelCatalogCache,
    selection_family,
    stable_family_models,
)

CASES = json.loads((Path(__file__).parent / "fixtures/model-catalog.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_stable_selection_shared_with_electron(case):
    models = stable_family_models(
        case["entries"], case["provider"], case["family"], today=date(2026, 11, 2)
    )
    assert [model["id"] for model in models] == case["expected"]


def test_cache_refreshes_hourly_and_retries_outages_without_inventing_a_model():
    now = [0]
    cache = ModelCatalogCache(clock=lambda: now[0])
    entries = [{"id": "anthropic/claude-sonnet-5"}]
    calls = []

    def load():
        calls.append(True)
        return entries.copy()

    assert cache.get(load)[0]["id"].endswith("-5")
    entries[0] = {"id": "anthropic/claude-sonnet-5.5"}
    assert cache.get(load)[0]["id"].endswith("-5")
    now[0] = 3601
    assert cache.get(load)[0]["id"].endswith("-5.5")
    assert len(calls) == 2
    now[0] = 7202

    def unavailable():
        raise ValueError("Catalog unavailable")

    assert cache.get(unavailable)[0]["id"].endswith("-5.5")
    assert cache.get(load)[0]["id"].endswith("-5.5")
    assert len(calls) == 2
    now[0] += 61
    assert cache.get(lambda: []) == []


def test_native_gemini_valid_catalog_without_stable_models_fails_closed():
    generator = GeminiAdvisorGenerator(
        config=AdvisorProviderConfig(provider="gemini", model="unused", api_key="test"),
        client=SimpleNamespace(models=SimpleNamespace(list=lambda **kwargs: [])),
    )
    with pytest.raises(AdvisorProviderError, match="No stable Gemini"):
        generator.generate(system_prompt="System", user_prompt="User")


def test_unknown_or_wrong_provider_family_fails_closed():
    assert selection_family("anthropic/claude-sonnet-5", "openrouter") is None
    with pytest.raises(ValueError):
        selection_family("stellaris:latest-stable/unknown", "openrouter")
    with pytest.raises(ValueError):
        selection_family("stellaris:latest-stable/claude-sonnet", "custom")


def test_generation_resolves_family_once_per_catalog_refresh_and_preserves_requested_id():
    requests = []
    target = ["anthropic/claude-sonnet-5.5"]
    now = [0]

    def handle(request):
        requests.append(request)
        if request.method == "GET":
            assert request.url.path == "/api/v1/models"
            return httpx.Response(
                200, json={"data": [{"id": target[0]}, {"id": "anthropic/claude-sonnet-9-preview"}]}
            )
        body = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": body["model"],
                "choices": [{"message": {"content": "Answer"}, "finish_reason": "stop"}],
            },
        )

    selection = "stellaris:latest-stable/claude-sonnet"
    generator = OpenAICompatibleAdvisorGenerator(
        config=AdvisorProviderConfig(
            provider="openrouter",
            model=selection,
            base_url="https://openrouter.ai/api/v1",
            api_key="test-key",
        ),
        client=httpx.Client(transport=httpx.MockTransport(handle)),
    )
    generator._catalog = ModelCatalogCache(clock=lambda: now[0])
    first = generator.generate(system_prompt="System", user_prompt="User")
    target[0] = "anthropic/claude-sonnet-6"
    second = generator.generate(system_prompt="System", user_prompt="User")
    now[0] = 3601
    third = generator.generate(system_prompt="System", user_prompt="User")
    assert first.model == second.model == "anthropic/claude-sonnet-5.5"
    assert third.model == target[0]
    assert first.requested_model == third.requested_model == selection
    assert [r.method for r in requests] == ["GET", "POST", "POST", "GET", "POST"]
    pinned = generator.generate(
        system_prompt="System", user_prompt="User", model="anthropic/claude-sonnet-5"
    )
    assert pinned.model == pinned.requested_model == "anthropic/claude-sonnet-5"
    assert requests[-1].method == "POST"


@pytest.mark.parametrize(
    "catalog", [{"data": []}, {"data": [{"id": "anthropic/claude-sonnet-8-preview"}]}]
)
def test_unresolvable_family_never_reaches_generation(catalog):
    def handle(request):
        assert request.method == "GET"
        return httpx.Response(200, json=catalog)

    generator = OpenAICompatibleAdvisorGenerator(
        config=AdvisorProviderConfig(
            provider="openrouter",
            model="stellaris:latest-stable/claude-sonnet",
            base_url="https://openrouter.ai/api/v1",
            api_key="test-key",
        ),
        client=httpx.Client(transport=httpx.MockTransport(handle)),
    )
    with pytest.raises(AdvisorProviderError):
        generator.generate(system_prompt="System", user_prompt="User")


def test_native_gemini_refreshes_automatic_tiers_and_keeps_explicit_selection():
    calls = []

    class Model:
        def __init__(self, name):
            self.name = name

        def model_dump(self, **kwargs):
            return {"name": self.name, "supported_actions": ["generateContent"]}

    def generate(**kwargs):
        calls.append(kwargs["model"])
        return SimpleNamespace(text="Answer", model_version=kwargs["model"] + "-001")

    client = SimpleNamespace(
        models=SimpleNamespace(
            list=lambda **kwargs: [
                Model(name)
                for name in ["gemini-4-flash-lite", "gemini-4-flash", "gemini-9-flash-preview"]
            ],
            generate_content=generate,
        )
    )
    generator = GeminiAdvisorGenerator(
        config=AdvisorProviderConfig(provider="gemini", model="unused", api_key="test"),
        client=client,
    )
    result = generator.generate(system_prompt="System", user_prompt="User")
    generator.generate(system_prompt="System", user_prompt="User", purpose="chronicle")
    generator.generate(system_prompt="System", user_prompt="User", model="gemini-3.5-flash-lite")
    assert calls == ["gemini-4-flash-lite", "gemini-4-flash", "gemini-3.5-flash-lite"]
    assert result.model == "gemini-4-flash-lite-001"
