"""Native Gemini must never spend more than two requests on one generation."""

import json
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from google import genai
from google.genai import types

from backend.core.advisor_providers import (
    AdvisorProviderConfig,
    AdvisorProviderError,
    GeminiAdvisorGenerator,
)
from backend.core.chronicle import ChronicleGenerator, CurrentEraOutput
from backend.core.model_routing import clear_model_state

VALID_JSON = '{"sections":[{"type":"prose","text":"The colony endured."}]}'


@pytest.fixture(autouse=True)
def reset_routes():
    clear_model_state()
    yield
    clear_model_state()


def response(text="Complete answer", finish="STOP"):
    return SimpleNamespace(
        text=text,
        candidates=[SimpleNamespace(finish_reason=finish)],
        model_version="actual-server-model",
        usage_metadata=SimpleNamespace(
            prompt_token_count=100, thoughts_token_count=30, candidates_token_count=20
        ),
    )


def generator_with(*responses):
    models = MagicMock()
    models.generate_content.side_effect = list(responses)
    generator = GeminiAdvisorGenerator(
        config=AdvisorProviderConfig(provider="gemini", model="unused", api_key="secret-key"),
        client=SimpleNamespace(models=models),
    )
    return generator, models


@pytest.mark.parametrize(
    ("purpose", "limits"), [("advisor", [4096, 8192]), ("chronicle", [8192, 16384])]
)
def test_truncation_gets_one_larger_attempt_even_when_json_parses(purpose, limits, caplog):
    generator, models = generator_with(response(VALID_JSON, "MAX_TOKENS"), response(VALID_JSON))
    with caplog.at_level(logging.INFO):
        result = generator.generate(
            system_prompt="private system prompt",
            user_prompt="private save data",
            model="gemini-3-flash-preview",
            purpose=purpose,
            response_schema=CurrentEraOutput,
        )
    configs = [c.kwargs["config"] for c in models.generate_content.call_args_list]
    assert [c.max_output_tokens for c in configs] == limits
    assert all(c.http_options.retry_options.attempts == 1 for c in configs)
    assert (
        configs[0].thinking_config is None
        if purpose == "advisor"
        else configs[0].thinking_config.thinking_level == "LOW"
    )
    assert len(result.diagnostics) == 2
    assert result.diagnostics[-1]["returned_model"] == "actual-server-model"
    assert result.diagnostics[-1]["prompt_token_count"] == 100
    assert "private save data" not in caplog.text
    assert "private system prompt" not in caplog.text
    assert "secret-key" not in caplog.text


@pytest.mark.parametrize("first_text", ["", '{"sections":[', "not json"])
def test_schema_repairs_do_not_increase_output_allowance(first_text):
    generator, models = generator_with(response(first_text), response(VALID_JSON))
    chronicle = ChronicleGenerator(db=MagicMock(), provider_generator=generator)
    parsed, result = chronicle._generate_structured_content(
        contents="Write the current era.",
        response_schema=CurrentEraOutput,
        temperature=1,
        max_output_tokens=4096,
        purpose_label="Current era",
    )
    assert parsed.sections[0].text == "The colony endured."
    assert len(result.diagnostics) == 2
    assert [
        c.kwargs["config"].max_output_tokens for c in models.generate_content.call_args_list
    ] == [8192, 8192]


@pytest.mark.parametrize("last", [response("", "MAX_TOKENS"), response("not json"), response("")])
def test_fallback_and_repair_share_two_attempts(last):
    generator, models = generator_with(
        RuntimeError("429 quota exceeded"), last, response(VALID_JSON)
    )
    chronicle = ChronicleGenerator(db=MagicMock(), provider_generator=generator)
    with pytest.raises(AdvisorProviderError) as error:
        chronicle._generate_structured_content(
            contents="Write the current era.",
            response_schema=CurrentEraOutput,
            temperature=1,
            max_output_tokens=4096,
            purpose_label="Current era",
        )
    assert models.generate_content.call_count == 2
    assert [c.kwargs["model"] for c in models.generate_content.call_args_list] == [
        "gemini-3-flash-preview",
        "gemini-3.1-flash-lite",
    ]
    assert len(error.value.diagnostics) == 2


def test_quota_after_truncation_cannot_trigger_a_third_call():
    generator, models = generator_with(
        response("", "MAX_TOKENS"), RuntimeError("429 quota exceeded"), response()
    )
    with pytest.raises(AdvisorProviderError) as error:
        generator.generate(
            system_prompt="system", user_prompt="user", model_routing_mode="quality_first"
        )
    assert models.generate_content.call_count == 2
    assert error.value.code == "PROVIDER_RATE_LIMITED"


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("API key not valid"),
        RuntimeError("No available credits"),
        RuntimeError("404 NOT_FOUND: model not found"),
        httpx.ReadTimeout("Timed out"),
        RuntimeError("429 daily quota exhausted"),
    ],
)
def test_terminal_errors_do_not_retry_the_same_model(error):
    generator, models = generator_with(error, response())
    with pytest.raises(AdvisorProviderError):
        generator.generate(
            system_prompt="system", user_prompt="user", model="gemini-3.1-flash-lite"
        )
    assert models.generate_content.call_count == 1


def test_twice_truncated_answer_is_never_returned():
    generator, models = generator_with(
        response("partial", "MAX_TOKENS"), response("still partial", "MAX_TOKENS")
    )
    with pytest.raises(AdvisorProviderError) as error:
        generator.generate(system_prompt="system", user_prompt="user")
    assert error.value.code == "PROVIDER_INVALID_RESPONSE"
    assert len(error.value.diagnostics) == models.generate_content.call_count == 2


@pytest.mark.parametrize("prompt_blocked", [False, True])
def test_blocked_response_is_not_retried(prompt_blocked):
    blocked = response("", "SAFETY")
    if prompt_blocked:
        blocked.candidates = []
        blocked.prompt_feedback = SimpleNamespace(block_reason="SAFETY")
    generator, models = generator_with(blocked, response())
    with pytest.raises(AdvisorProviderError):
        generator.generate(system_prompt="system", user_prompt="user")
    assert models.generate_content.call_count == 1


def test_low_thinking_does_not_override_lite_default():
    generator, models = generator_with(response(VALID_JSON))
    generator.generate(
        system_prompt="system",
        user_prompt="user",
        purpose="chronicle",
        model="gemini-3.1-flash-lite",
    )
    assert models.generate_content.call_args.kwargs["config"].thinking_config is None


def test_sdk_does_not_add_hidden_transport_retries():
    requests = []

    def fail(request):
        requests.append(request)
        return httpx.Response(
            503, json={"error": {"code": 503, "status": "UNAVAILABLE", "message": "Busy"}}
        )

    with genai.Client(
        api_key="test-key",
        http_options=types.HttpOptions(
            client_args={"transport": httpx.MockTransport(fail)},
        ),
    ) as client:
        generator = GeminiAdvisorGenerator(
            config=AdvisorProviderConfig(provider="gemini", model="unused", api_key="test-key"),
            client=client,
        )
        with pytest.raises(AdvisorProviderError):
            generator.generate(
                system_prompt="system", user_prompt="user", model="gemini-3.1-flash-lite"
            )
    assert len(requests) == 1


def test_json_repair_still_works_without_a_network_retry():
    raw = json.dumps(json.loads(VALID_JSON)).replace(
        "The colony endured.", "First line.\nSecond line."
    )
    generator, models = generator_with(response(raw))
    generator.generate(system_prompt="system", user_prompt="user", response_schema=CurrentEraOutput)
    assert models.generate_content.call_count == 1
