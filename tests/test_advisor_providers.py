"""Tests for Advisor provider normalization and compatible generation."""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest
from pydantic import BaseModel

from backend.core.advisor_providers import (
    AdvisorProviderConfig,
    AdvisorProviderError,
    GeminiAdvisorGenerator,
    OpenAICompatibleAdvisorGenerator,
    normalize_advisor_provider,
    normalize_base_url,
)
from backend.core.companion import Companion


class StructuredProbe(BaseModel):
    status: str


class StructuredDetail(BaseModel):
    note: str = ""


class NestedStructuredProbe(BaseModel):
    status: str
    detail: StructuredDetail


def test_companion_starts_without_ai_credentials(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("STELLARIS_ADVISOR_API_KEY", raising=False)
    monkeypatch.delenv("STELLARIS_ADVISOR_MODEL", raising=False)

    companion = Companion(save_path=None, auto_precompute=False)

    assert companion.get_advisor_provider() == "gemini"
    assert companion.is_advisor_configured() is False


def test_provider_config_uses_ollama_preset(monkeypatch):
    monkeypatch.setenv("STELLARIS_ADVISOR_PROVIDER", "ollama")
    monkeypatch.setenv("STELLARIS_ADVISOR_MODEL", "test-model:latest")

    config = AdvisorProviderConfig.from_environment()

    assert config.provider == "ollama"
    assert config.base_url == "http://127.0.0.1:11434/v1"
    assert config.model == "test-model:latest"
    assert config.is_configured is True


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("LM Studio", "lm_studio"),
        ("lmstudio", "lm_studio"),
        ("open-router", "openrouter"),
        ("unknown", "gemini"),
    ],
)
def test_normalize_advisor_provider(raw, expected):
    assert normalize_advisor_provider(raw) == expected


def test_normalize_base_url_removes_endpoint_suffix():
    assert (
        normalize_base_url("http://localhost:1234/v1/chat/completions")
        == "http://localhost:1234/v1"
    )


def test_normalize_base_url_allows_private_network_http():
    assert normalize_base_url("http://192.168.1.50:1234/v1") == ("http://192.168.1.50:1234/v1")


def test_normalize_base_url_requires_https_for_public_hosts():
    with pytest.raises(ValueError, match="must use HTTPS"):
        normalize_base_url("http://models.example.com/v1")


def test_compatible_generator_sends_common_chat_contract():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["authorization"] = request.headers.get("Authorization")
        captured["openrouter_title"] = request.headers.get("X-OpenRouter-Title")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "provider/answer-model",
                "choices": [{"message": {"content": "Build more alloy foundries."}}],
            },
        )

    config = AdvisorProviderConfig(
        provider="openrouter",
        model="provider/request-model",
        base_url="https://openrouter.ai/api/v1",
        api_key="secret-key",
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    generator = OpenAICompatibleAdvisorGenerator(config=config, client=client)

    result = generator.generate(
        system_prompt="System instructions",
        user_prompt="Game briefing",
    )

    assert result.text == "Build more alloy foundries."
    assert result.model == "provider/answer-model"
    assert result.requested_model == "provider/request-model"
    assert captured["path"] == "/api/v1/chat/completions"
    assert captured["authorization"] == "Bearer secret-key"
    assert captured["openrouter_title"] == "Stellaris Companion"
    assert captured["body"] == {
        "model": "provider/request-model",
        "messages": [
            {"role": "system", "content": "System instructions"},
            {"role": "user", "content": "Game briefing"},
        ],
        "temperature": 1.0,
        "max_tokens": 4096,
        "stream": False,
    }


def test_compatible_generator_reports_auth_failure_without_exposing_key():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"error": {"message": "Invalid token very-secret-key"}},
        )

    config = AdvisorProviderConfig(
        provider="openrouter",
        model="provider/model",
        base_url="https://openrouter.ai/api/v1",
        api_key="very-secret-key",
    )
    generator = OpenAICompatibleAdvisorGenerator(
        config=config,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(AdvisorProviderError) as exc_info:
        generator.generate(system_prompt="system", user_prompt="user")

    assert exc_info.value.code == "PROVIDER_AUTH_FAILED"
    assert "Invalid token" in str(exc_info.value)
    assert "[redacted]" in str(exc_info.value)
    assert "very-secret-key" not in str(exc_info.value)


def test_compatible_generator_reports_context_limit():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error": {"message": "This model's maximum context length is 8192 tokens."}},
        )

    config = AdvisorProviderConfig(
        provider="ollama",
        model="small-context-model",
        base_url="http://127.0.0.1:11434/v1",
    )
    generator = OpenAICompatibleAdvisorGenerator(
        config=config,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(AdvisorProviderError) as exc_info:
        generator.generate(system_prompt="system", user_prompt="large briefing")

    assert exc_info.value.code == "PROVIDER_CONTEXT_LIMIT"
    assert exc_info.value.status_code == 400
    assert "context window" in str(exc_info.value)


def test_compatible_generator_requests_structured_output():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "provider/structured-model",
                "choices": [{"message": {"content": '{"status":"CHRONICLE_READY"}'}}],
            },
        )

    config = AdvisorProviderConfig(
        provider="openrouter",
        model="provider/structured-model",
        base_url="https://openrouter.ai/api/v1",
        api_key="secret-key",
    )
    generator = OpenAICompatibleAdvisorGenerator(
        config=config,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = generator.generate(
        system_prompt="Return a probe.",
        user_prompt="Check Chronicle support.",
        response_schema=StructuredProbe,
        schema_name="chronicle probe",
        purpose="chronicle",
    )

    assert StructuredProbe.model_validate_json(result.text).status == "CHRONICLE_READY"
    assert result.provider == "openrouter"
    assert captured["body"]["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "chronicle_probe",
            "strict": True,
            "schema": {
                **StructuredProbe.model_json_schema(),
                "additionalProperties": False,
                "required": ["status"],
            },
        },
    }
    assert captured["body"]["provider"] == {"require_parameters": True}
    assert "temperature" not in captured["body"]
    assert "Return only one JSON object" in captured["body"]["messages"][1]["content"]


def test_compatible_generator_normalizes_nested_strict_schema():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"status":"ok","detail":{"note":""}}'}}]},
        )

    config = AdvisorProviderConfig(
        provider="openrouter",
        model="provider/model",
        base_url="https://openrouter.ai/api/v1",
        api_key="secret-key",
    )
    generator = OpenAICompatibleAdvisorGenerator(
        config=config,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    generator.generate(
        system_prompt="Return a probe.",
        user_prompt="Check Chronicle support.",
        response_schema=NestedStructuredProbe,
    )

    schema = captured["body"]["response_format"]["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["status", "detail"]
    assert schema["$defs"]["StructuredDetail"]["additionalProperties"] is False
    assert schema["$defs"]["StructuredDetail"]["required"] == ["note"]
    assert "default" not in schema["$defs"]["StructuredDetail"]["properties"]["note"]


def test_compatible_generator_retries_without_schema_parameter():
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            return httpx.Response(
                400,
                json={"error": {"message": "response_format is not supported"}},
            )
        return httpx.Response(
            200,
            json={
                "model": "local/model",
                "choices": [{"message": {"content": '{"status":"CHRONICLE_READY"}'}}],
            },
        )

    config = AdvisorProviderConfig(
        provider="ollama",
        model="local/model",
        base_url="http://127.0.0.1:11434/v1",
    )
    generator = OpenAICompatibleAdvisorGenerator(
        config=config,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = generator.generate(
        system_prompt="Return a probe.",
        user_prompt="Check Chronicle support.",
        response_schema=StructuredProbe,
    )

    assert StructuredProbe.model_validate_json(result.text).status == "CHRONICLE_READY"
    assert len(requests) == 2
    assert result.schema_fallback_used is True
    assert "response_format" in requests[0]
    assert "response_format" not in requests[1]
    assert "Return only one JSON object" in requests[1]["messages"][1]["content"]


def test_openrouter_retries_when_no_route_supports_schema():
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            return httpx.Response(
                503,
                json={
                    "error": {
                        "message": "No available model provider meets your routing requirements"
                    }
                },
            )
        return httpx.Response(
            200,
            json={
                "model": "provider/model",
                "choices": [{"message": {"content": '{"status":"CHRONICLE_READY"}'}}],
            },
        )

    config = AdvisorProviderConfig(
        provider="openrouter",
        model="provider/model",
        base_url="https://openrouter.ai/api/v1",
        api_key="secret-key",
    )
    generator = OpenAICompatibleAdvisorGenerator(
        config=config,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = generator.generate(
        system_prompt="Return a probe.",
        user_prompt="Check Chronicle support.",
        response_schema=StructuredProbe,
    )

    assert StructuredProbe.model_validate_json(result.text).status == "CHRONICLE_READY"
    assert len(requests) == 2
    assert result.schema_fallback_used is True
    assert "response_format" in requests[0]
    assert requests[0]["provider"] == {"require_parameters": True}
    assert "response_format" not in requests[1]
    assert "provider" not in requests[1]


def test_openrouter_retries_route_specific_404_without_schema():
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            return httpx.Response(
                404,
                json={"error": {"message": "No endpoints can handle requested parameters"}},
            )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"status":"ok"}'}}]},
        )

    config = AdvisorProviderConfig(
        provider="openrouter",
        model="provider/model",
        base_url="https://openrouter.ai/api/v1",
        api_key="secret-key",
    )
    generator = OpenAICompatibleAdvisorGenerator(
        config=config,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = generator.generate(
        system_prompt="Return a probe.",
        user_prompt="Check Chronicle support.",
        response_schema=StructuredProbe,
    )

    assert len(requests) == 2
    assert result.schema_fallback_used is True
    assert "response_format" not in requests[1]


def test_openrouter_does_not_retry_generic_model_not_found():
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(404, json={"error": {"message": "Model not found"}})

    config = AdvisorProviderConfig(
        provider="openrouter",
        model="missing/model",
        base_url="https://openrouter.ai/api/v1",
        api_key="secret-key",
    )
    generator = OpenAICompatibleAdvisorGenerator(
        config=config,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(AdvisorProviderError) as exc_info:
        generator.generate(
            system_prompt="Return a probe.",
            user_prompt="Check Chronicle support.",
            response_schema=StructuredProbe,
        )

    assert exc_info.value.code == "PROVIDER_MODEL_NOT_FOUND"
    assert len(requests) == 1


def test_compatible_generator_can_disable_schema_fallback_for_request_budget():
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(
            400,
            json={"error": {"message": "response_format is not supported"}},
        )

    config = AdvisorProviderConfig(
        provider="ollama",
        model="local/model",
        base_url="http://127.0.0.1:11434/v1",
    )
    generator = OpenAICompatibleAdvisorGenerator(
        config=config,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(AdvisorProviderError):
        generator.generate(
            system_prompt="Return a probe.",
            user_prompt="Check Chronicle support.",
            response_schema=StructuredProbe,
            allow_schema_fallback=False,
        )

    assert len(requests) == 1


def test_compatible_generator_reports_billing_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(402, json={"error": {"message": "Insufficient credits"}})

    config = AdvisorProviderConfig(
        provider="openrouter",
        model="provider/model",
        base_url="https://openrouter.ai/api/v1",
        api_key="secret-key",
    )
    generator = OpenAICompatibleAdvisorGenerator(
        config=config,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(AdvisorProviderError) as exc_info:
        generator.generate(system_prompt="system", user_prompt="user")

    assert exc_info.value.code == "PROVIDER_BILLING_FAILED"


def test_openrouter_requires_api_key():
    config = AdvisorProviderConfig(
        provider="openrouter",
        model="provider/model",
        base_url="https://openrouter.ai/api/v1",
    )
    generator = OpenAICompatibleAdvisorGenerator(config=config)

    with pytest.raises(AdvisorProviderError) as exc_info:
        generator.generate(system_prompt="system", user_prompt="user")

    assert exc_info.value.code == "ADVISOR_PROVIDER_NOT_CONFIGURED"


def test_gemini_billing_failure_is_not_retried_or_reported_as_rate_limit():
    class FailingModels:
        def __init__(self):
            self.calls = 0

        def generate_content(self, **kwargs):
            self.calls += 1
            raise RuntimeError("No available credits for this billing account")

    models = FailingModels()
    config = AdvisorProviderConfig(
        provider="gemini",
        model="gemini-3-flash-preview",
        api_key="test-key",
    )
    generator = GeminiAdvisorGenerator(
        config=config,
        client=SimpleNamespace(models=models),
    )

    with pytest.raises(AdvisorProviderError) as exc_info:
        generator.generate(
            system_prompt="system",
            user_prompt="user",
            model_routing_mode="quality_first",
        )

    assert exc_info.value.code == "PROVIDER_BILLING_FAILED"
    assert models.calls == 1


def test_gemini_generator_accepts_chronicle_schema():
    class CapturingModels:
        def __init__(self):
            self.request = None

        def generate_content(self, **kwargs):
            self.request = kwargs
            return SimpleNamespace(text='{"status":"CHRONICLE_READY"}')

    models = CapturingModels()
    config = AdvisorProviderConfig(
        provider="gemini",
        model="gemini-test-model",
        api_key="test-key",
    )
    generator = GeminiAdvisorGenerator(
        config=config,
        client=SimpleNamespace(models=models),
    )

    result = generator.generate(
        system_prompt="Return a probe.",
        user_prompt="Check Chronicle support.",
        model="gemini-test-model",
        purpose="chronicle",
        response_schema=StructuredProbe,
    )

    assert StructuredProbe.model_validate_json(result.text).status == "CHRONICLE_READY"
    assert result.provider == "gemini"
    assert models.request is not None
    assert models.request["model"] == "gemini-test-model"
    assert models.request["config"].response_schema is StructuredProbe
