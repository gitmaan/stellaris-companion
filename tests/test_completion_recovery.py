"""Provider completion signals must survive recovery without multiplying requests."""

import json
import logging
from unittest.mock import MagicMock

import httpx
import pytest

from backend.core.advisor_providers import (
    AdvisorProviderConfig,
    AdvisorProviderError,
    OpenAICompatibleAdvisorGenerator,
    generation_output_limits,
)
from backend.core.chronicle import ChronicleGenerator, CurrentEraOutput

VALID_JSON = '{"sections":[{"type":"prose","text":"The colony endured."}]}'


def reply(text="完整回答。", finish="stop", **extra):
    return httpx.Response(
        200,
        json={
            "model": "returned-model",
            "choices": [{"message": {"content": text}, "finish_reason": finish}],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 80,
                "completion_tokens_details": {"reasoning_tokens": 20},
            },
            **extra,
        },
    )


def generator_with(*responses, model="deepseek-flash", url="https://api.deepseek.com/v1"):
    requests = []
    queue = iter(responses)

    def handle(request):
        requests.append(json.loads(request.content))
        item = next(queue)
        if isinstance(item, Exception):
            raise item
        return item

    generator = OpenAICompatibleAdvisorGenerator(
        config=AdvisorProviderConfig(
            provider="custom", model=model, base_url=url, api_key="secret"
        ),
        client=httpx.Client(transport=httpx.MockTransport(handle)),
    )
    return generator, requests


@pytest.mark.parametrize(
    ("model", "url", "limits"),
    [
        ("deepseek-flash", "https://api.deepseek.com/v1", [8192, 16384]),
        ("deepseek-chat", "https://api.deepseek.com", [8192, 8192]),
        ("deepseek-flash", "http://127.0.0.1:1234/v1", [4096, 4096]),
        ("future-model", "https://api.deepseek.com", [4096, 4096]),
        ("deepseek-flash", "https://proxy.example/v1", [4096, 4096]),
    ],
)
def test_truncation_recovers_once_with_supported_limits(model, url, limits, caplog):
    generator, requests = generator_with(reply("半个句子", "length"), reply(), model=model, url=url)
    with caplog.at_level(logging.INFO):
        result = generator.generate(
            system_prompt="private instructions", user_prompt="private campaign"
        )
    assert [request["max_tokens"] for request in requests] == limits
    assert result.text == "完整回答。"
    assert result.completion["status"] == "complete"
    assert result.completion["attempts"] == 2
    assert result.completion["recovered"] is True
    assert result.completion["usage"] == {
        "input_tokens": 100,
        "output_tokens": 80,
        "reasoning_tokens": 20,
    }
    assert "shorter, complete" in requests[1]["messages"][1]["content"]
    assert "private" not in caplog.text and "secret" not in caplog.text


@pytest.mark.parametrize(
    "last",
    [
        reply("仍未写完", "length"),
        reply("", "length"),
        httpx.Response(429, json={"error": {"message": "quota exhausted"}}),
        httpx.ReadTimeout("timed out"),
    ],
)
def test_exhausted_recovery_preserves_useful_advisor_text(last):
    generator, requests = generator_with(reply("尚未写完", "length"), last)
    result = generator.generate(system_prompt="system", user_prompt="question")
    assert result.text in {"尚未写完", "仍未写完"}
    assert result.completion["status"] == "truncated"
    assert result.completion["finish_reason"] == "length"
    assert result.completion["attempts"] == len(requests) == 2
    assert result.completion["recovered"] is False


@pytest.mark.parametrize(("purpose", "effort"), [("advisor", "low"), ("chronicle", "medium")])
def test_official_terra_uses_reasoning_budget_and_recovers_with_the_same_contract(purpose, effort):
    generator, requests = generator_with(
        reply("partial", "length"),
        reply(VALID_JSON),
        model="gpt-6.1-terra",
        url="https://api.openai.com/v1",
    )
    result = generator.generate(
        system_prompt="system",
        user_prompt="question",
        purpose=purpose,
        response_schema=CurrentEraOutput if purpose == "chronicle" else None,
    )
    assert result.completion["status"] == "complete"
    assert result.completion["output_limit"] == 16384
    assert [request["max_completion_tokens"] for request in requests] == [8192, 16384]
    for request in requests:
        assert request["model"] == "gpt-6.1-terra"
        assert request["reasoning_effort"] == effort
        assert "temperature" not in request and "max_tokens" not in request


@pytest.mark.parametrize(
    ("model", "purpose", "effort"),
    [
        ("gpt-6.1-sol", "advisor", "low"),
        ("gpt-6.1-sol", "chronicle", "medium"),
        ("gpt-6-astra", "advisor", "medium"),
        ("gpt-6-luna", "advisor", "none"),
        ("gpt-6-luna", "chronicle", "none"),
    ],
)
def test_other_official_reasoning_models_use_the_reasoning_contract(model, purpose, effort):
    generator, requests = generator_with(
        reply(VALID_JSON), model=model, url="https://api.openai.com/v1"
    )
    generator.generate(
        system_prompt="system",
        user_prompt="question",
        purpose=purpose,
        response_schema=CurrentEraOutput if purpose == "chronicle" else None,
    )
    assert requests[0]["model"] == model
    assert requests[0]["reasoning_effort"] == effort
    assert requests[0]["max_completion_tokens"] == 8192
    assert "temperature" not in requests[0] and "max_tokens" not in requests[0]


def test_terra_schema_fallback_preserves_reasoning_and_token_parameters():
    generator, requests = generator_with(
        httpx.Response(400, json={"error": {"message": "response_format is unsupported"}}),
        reply(VALID_JSON),
        model="gpt-6.1-terra",
        url="https://api.openai.com/v1",
    )
    result = generator.generate(
        system_prompt="system",
        user_prompt="history",
        purpose="chronicle",
        response_schema=CurrentEraOutput,
    )
    assert result.schema_fallback_used is True
    assert len(requests) == 2
    assert "response_format" in requests[0] and "response_format" not in requests[1]
    for request in requests:
        assert request["reasoning_effort"] == "medium"
        assert request["max_completion_tokens"] == 8192
        assert "temperature" not in request and "max_tokens" not in request


@pytest.mark.parametrize(
    ("model", "url"),
    [
        ("gpt-6.1-terra", "https://proxy.example/v1"),
        ("gpt-6.1-terra", "https://api.openai.com.example/v1"),
        ("gpt-6.1-terra", "http://127.0.0.1:1234/v1"),
        ("gpt-6-luna", "https://proxy.example/v1"),
        ("existing-model", "https://api.openai.com/v1"),
    ],
)
def test_terra_compatibility_does_not_change_other_models_or_endpoints(model, url):
    generator, requests = generator_with(reply(), model=model, url=url)
    generator.generate(system_prompt="system", user_prompt="question")
    assert requests[0]["max_tokens"] == 4096
    assert requests[0]["temperature"] == 1
    assert "max_completion_tokens" not in requests[0]
    assert "reasoning_effort" not in requests[0]


@pytest.mark.parametrize(
    "first",
    [
        reply(VALID_JSON, "length"),
        reply("not JSON"),
        reply(""),
        httpx.Response(400, json={"error": {"message": "response_format is not supported"}}),
    ],
)
def test_chronicle_recovery_and_schema_fallback_share_one_allowance(first):
    generator, requests = generator_with(first, reply(VALID_JSON, "length"))
    chronicle = ChronicleGenerator(db=MagicMock(), provider_generator=generator)
    with pytest.raises(AdvisorProviderError) as error:
        chronicle._generate_structured_content(
            contents="write history",
            response_schema=CurrentEraOutput,
            temperature=1,
            max_output_tokens=4096,
            purpose_label="Current era",
        )
    assert len(error.value.diagnostics) == len(requests) == 2
    assert error.value.code == "PROVIDER_INVALID_RESPONSE"


@pytest.mark.parametrize("first", [reply("not JSON"), reply("")])
def test_schema_repair_uses_same_allowance(first):
    generator, requests = generator_with(first, reply(VALID_JSON))
    result = generator.generate(
        system_prompt="system",
        user_prompt="history",
        response_schema=CurrentEraOutput,
        purpose="chronicle",
    )
    assert result.text == VALID_JSON
    assert [request["max_tokens"] for request in requests] == [8192, 8192]


def test_missing_finish_reason_is_unknown_and_does_not_invent_usage():
    generator, requests = generator_with(reply(finish=None, usage=None))
    result = generator.generate(system_prompt="system", user_prompt="question")
    assert result.completion["status"] == "unknown"
    assert result.completion["usage"] == {
        "input_tokens": None,
        "output_tokens": None,
        "reasoning_tokens": None,
    }
    assert len(requests) == 1


@pytest.mark.parametrize("status", [400, 413])
def test_context_limit_never_triggers_more_output(status):
    generator, requests = generator_with(
        httpx.Response(status, json={"error": {"message": "maximum context length exceeded"}})
    )
    with pytest.raises(AdvisorProviderError) as error:
        generator.generate(system_prompt="system", user_prompt="question")
    assert error.value.code == "PROVIDER_CONTEXT_LIMIT"
    assert len(requests) == 1


@pytest.mark.parametrize("finish", ["content_filter", "tool_calls", "unrecognized"])
def test_blocked_or_unsupported_finish_never_surfaces_partial(finish):
    generator, requests = generator_with(reply("partial", "length"), reply("blocked", finish))
    with pytest.raises(AdvisorProviderError):
        generator.generate(system_prompt="system", user_prompt="question")
    assert len(requests) == 2


def test_unknown_gemini_and_openrouter_models_keep_conservative_budget():
    for provider, model in [("gemini", "custom-gemini"), ("openrouter", "google/gemini-3.8-flash")]:
        assert generation_output_limits(
            AdvisorProviderConfig(provider=provider, model=model), model, "advisor"
        ) == (4096, 4096)


def test_chronicle_rejects_partial_even_from_an_adapter_that_returns_valid_json():
    generator, _ = generator_with(reply(VALID_JSON))
    result = generator.generate(system_prompt="system", user_prompt="question")
    result.completion["status"] = "truncated"
    generator.generate = MagicMock(return_value=result)
    chronicle = ChronicleGenerator(db=MagicMock(), provider_generator=generator)
    with pytest.raises(AdvisorProviderError):
        chronicle._generate_structured_content(
            contents="history",
            response_schema=CurrentEraOutput,
            temperature=1,
            max_output_tokens=4096,
            purpose_label="Current era",
        )
    assert generator.generate.call_count == 1
