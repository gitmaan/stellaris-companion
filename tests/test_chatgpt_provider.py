"""Desktop ChatGPT bridge contract; no OpenAI credentials enter Python."""

import httpx
import pytest
from pydantic import BaseModel

from backend.core.advisor_providers import (
    AdvisorProviderConfig,
    AdvisorProviderError,
    ChatGPTAdvisorGenerator,
    create_advisor_generator,
)


class ChapterProbe(BaseModel):
    title: str
    text: str


def config():
    return AdvisorProviderConfig(
        provider="chatgpt",
        model="account-model",
        base_url="http://127.0.0.1:54321",
        api_key="local-capability",
    )


def test_chatgpt_uses_desktop_bridge_environment(monkeypatch):
    monkeypatch.setenv("STELLARIS_ADVISOR_PROVIDER", "chatgpt")
    monkeypatch.setenv("STELLARIS_ADVISOR_MODEL", "account-model")
    monkeypatch.setenv("STELLARIS_CHATGPT_BRIDGE_URL", "http://127.0.0.1:54321")
    monkeypatch.setenv("STELLARIS_CHATGPT_BRIDGE_TOKEN", "local-capability")
    monkeypatch.setenv("STELLARIS_ADVISOR_API_KEY", "unrelated-key")
    resolved = AdvisorProviderConfig.from_environment()
    assert resolved.is_configured
    assert resolved.api_key == "local-capability"
    assert resolved.display_name == "ChatGPT"
    assert isinstance(create_advisor_generator(config=resolved), ChatGPTAdvisorGenerator)
    for url in [
        "https://provider.example",
        "http://localhost:54321",
        "http://127.0.0.1:54321/other",
        "http://127.0.0.1:54321?secret=1",
    ]:
        monkeypatch.setenv("STELLARIS_CHATGPT_BRIDGE_URL", url)
        assert not AdvisorProviderConfig.from_environment().is_configured


def test_chronicle_schema_travels_through_bridge_and_output_remains_validatable():
    seen = []

    def handle(request):
        import json

        seen.append(json.loads(request.content))
        assert request.headers["Authorization"] == "Bearer local-capability"
        assert str(request.url) == "http://127.0.0.1:54321/generate"
        return httpx.Response(
            200,
            json={
                "text": '{"title":"First Contact","text":"A new era."}',
                "model": "account-model",
                "schemaFallbackUsed": True,
            },
        )

    generator = ChatGPTAdvisorGenerator(
        config=config(), client=httpx.Client(transport=httpx.MockTransport(handle))
    )
    result = generator.generate(
        system_prompt="Narrate the empire",
        user_prompt="Campaign briefing",
        response_schema=ChapterProbe,
        purpose="chronicle",
    )
    assert ChapterProbe.model_validate_json(result.text).title == "First Contact"
    assert result.provider == "chatgpt"
    assert result.schema_fallback_used
    assert seen[0]["instructions"] == "Narrate the empire"
    assert seen[0]["purpose"] == "chronicle"
    assert "model" not in seen[0]
    assert "Campaign briefing" in seen[0]["input"]
    assert "JSON" in seen[0]["input"]
    assert seen[0]["schema"]["additionalProperties"] is False
    assert set(seen[0]["schema"]["required"]) == {"title", "text"}
    assert "temperature" not in seen[0]
    assert "max_output_tokens" not in seen[0]


def test_explicit_model_override_is_forwarded_and_actual_selection_is_reported():
    def handle(request):
        import json

        assert json.loads(request.content)["model"] == "explicit-model"
        assert json.loads(request.content)["purpose"] == "advisor"
        return httpx.Response(200, json={"text": "Advice", "model": "explicit-model"})

    generator = ChatGPTAdvisorGenerator(
        config=config(), client=httpx.Client(transport=httpx.MockTransport(handle))
    )
    result = generator.generate(
        system_prompt="Advisor", user_prompt="Briefing", model="explicit-model"
    )
    assert result.requested_model == "explicit-model"


@pytest.mark.parametrize(
    "code,status",
    [
        ("CHATGPT_LIMIT", 429),
        ("CHATGPT_RECONNECT", 401),
        ("CHATGPT_UNAVAILABLE", 503),
        ("CHATGPT_INVALID_RESPONSE", 502),
    ],
)
def test_bridge_failures_are_actionable_and_do_not_expose_credentials(code, status):
    generator = ChatGPTAdvisorGenerator(
        config=config(),
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    status,
                    json={"code": code, "error": "local-capability access-token secret details"},
                )
            )
        ),
    )
    with pytest.raises(AdvisorProviderError) as failure:
        generator.generate(system_prompt="Advisor", user_prompt="Briefing")
    assert failure.value.code == code
    assert failure.value.status_code == status
    assert "local-capability" not in str(failure.value)
    assert "access-token" not in str(failure.value)


def test_empty_bridge_output_is_never_a_success():
    generator = ChatGPTAdvisorGenerator(
        config=config(),
        client=httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"text": ""}))
        ),
    )
    with pytest.raises(AdvisorProviderError, match="did not finish"):
        generator.generate(system_prompt="Advisor", user_prompt="Briefing")
