"""Advisor model-provider configuration and generation adapters."""

from __future__ import annotations

import ipaddress
import json
import os
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx
from google.genai import types
from pydantic import BaseModel

from backend.core.model_routing import (
    GEMINI_FLASH_MODEL,
    classify_model_error,
    fallback_notice,
    get_model_unavailable_event,
    is_model_temporarily_unavailable,
    mark_model_failure,
    route_event_payload,
    route_models_for,
)

ADVISOR_PROVIDER_GEMINI = "gemini"
ADVISOR_PROVIDER_OLLAMA = "ollama"
ADVISOR_PROVIDER_LM_STUDIO = "lm_studio"
ADVISOR_PROVIDER_OPENROUTER = "openrouter"
ADVISOR_PROVIDER_CUSTOM = "custom"

ADVISOR_PROVIDERS = {
    ADVISOR_PROVIDER_GEMINI,
    ADVISOR_PROVIDER_OLLAMA,
    ADVISOR_PROVIDER_LM_STUDIO,
    ADVISOR_PROVIDER_OPENROUTER,
    ADVISOR_PROVIDER_CUSTOM,
}

PROVIDER_BASE_URLS = {
    ADVISOR_PROVIDER_OLLAMA: "http://127.0.0.1:11434/v1",
    ADVISOR_PROVIDER_LM_STUDIO: "http://127.0.0.1:1234/v1",
    ADVISOR_PROVIDER_OPENROUTER: "https://openrouter.ai/api/v1",
}

_PRIVATE_IPV4_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
)
_PRIVATE_IPV6_NETWORK = ipaddress.ip_network("fc00::/7")


def normalize_advisor_provider(value: Any) -> str:
    """Normalize a provider identifier, preserving Gemini as the default."""
    if not isinstance(value, str):
        return ADVISOR_PROVIDER_GEMINI
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "lmstudio": ADVISOR_PROVIDER_LM_STUDIO,
        "open_router": ADVISOR_PROVIDER_OPENROUTER,
        "openai_compatible": ADVISOR_PROVIDER_CUSTOM,
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in ADVISOR_PROVIDERS else ADVISOR_PROVIDER_GEMINI


def normalize_base_url(value: str | None) -> str:
    """Validate and normalize an OpenAI-compatible API base URL."""
    raw = str(value or "").strip().rstrip("/")
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Provider URL must be a valid HTTP or HTTPS URL")
    if parsed.username or parsed.password:
        raise ValueError("Provider credentials must not be embedded in the URL")
    if parsed.scheme == "http" and not _is_local_or_private_host(parsed.hostname):
        raise ValueError(
            "Public provider URLs must use HTTPS. HTTP is allowed only for local "
            "or private-network model servers"
        )

    for suffix in ("/chat/completions", "/models"):
        if raw.endswith(suffix):
            raw = raw[: -len(suffix)]
            break
    return raw.rstrip("/")


def _is_local_or_private_host(hostname: str | None) -> bool:
    host = str(hostname or "").strip().lower().rstrip(".")
    if not host:
        return False
    if (
        host == "localhost"
        or host.endswith(".localhost")
        or host.endswith(".local")
        or host == "host.docker.internal"
    ):
        return True

    address_text = host.split("%", 1)[0]
    try:
        address = ipaddress.ip_address(address_text)
    except ValueError:
        return False

    if address.is_loopback or address.is_link_local or address.is_unspecified:
        return True
    if isinstance(address, ipaddress.IPv4Address):
        return any(address in network for network in _PRIVATE_IPV4_NETWORKS)
    return address in _PRIVATE_IPV6_NETWORK


@dataclass(frozen=True)
class AdvisorProviderConfig:
    """Resolved configuration for the selected Advisor provider."""

    provider: str
    model: str
    base_url: str = ""
    api_key: str = ""
    timeout_seconds: float = 180.0

    @classmethod
    def from_environment(
        cls,
        *,
        provider: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        advisor_api_key: str | None = None,
        google_api_key: str | None = None,
    ) -> AdvisorProviderConfig:
        selected_provider = normalize_advisor_provider(
            provider or os.environ.get("STELLARIS_ADVISOR_PROVIDER")
        )
        configured_model = str(model or os.environ.get("STELLARIS_ADVISOR_MODEL") or "").strip()
        if selected_provider == ADVISOR_PROVIDER_GEMINI and not configured_model:
            configured_model = GEMINI_FLASH_MODEL

        configured_url = str(
            base_url
            or os.environ.get("STELLARIS_ADVISOR_BASE_URL")
            or PROVIDER_BASE_URLS.get(selected_provider, "")
        ).strip()
        if configured_url:
            configured_url = normalize_base_url(configured_url)

        if selected_provider == ADVISOR_PROVIDER_GEMINI:
            configured_key = str(google_api_key or os.environ.get("GOOGLE_API_KEY") or "")
        else:
            configured_key = str(
                advisor_api_key or os.environ.get("STELLARIS_ADVISOR_API_KEY") or ""
            )

        return cls(
            provider=selected_provider,
            model=configured_model,
            base_url=configured_url,
            api_key=configured_key,
        )

    @property
    def is_configured(self) -> bool:
        if self.provider == ADVISOR_PROVIDER_GEMINI:
            return bool(self.api_key)
        if not self.base_url or not self.model:
            return False
        if self.provider == ADVISOR_PROVIDER_OPENROUTER:
            return bool(self.api_key)
        return True

    @property
    def display_name(self) -> str:
        return {
            ADVISOR_PROVIDER_GEMINI: "Gemini",
            ADVISOR_PROVIDER_OLLAMA: "Ollama",
            ADVISOR_PROVIDER_LM_STUDIO: "LM Studio",
            ADVISOR_PROVIDER_OPENROUTER: "OpenRouter",
            ADVISOR_PROVIDER_CUSTOM: "Custom provider",
        }[self.provider]


@dataclass(frozen=True)
class AdvisorGenerationResult:
    """Normalized result returned by every model-provider adapter."""

    text: str
    model: str
    requested_model: str
    provider: str
    routing: dict[str, Any] | None = None
    schema_fallback_used: bool = False


class AdvisorProviderError(RuntimeError):
    """A provider failure safe to expose through the local API."""

    def __init__(self, message: str, *, code: str, status_code: int = 502):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class AdvisorGenerator(Protocol):
    """Common generation contract shared by Advisor and Chronicle."""

    config: AdvisorProviderConfig

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        model_routing_mode: str | None = None,
        thinking_level: str = "dynamic",
        temperature: float = 1.0,
        max_output_tokens: int = 4096,
        purpose: str = "advisor",
        response_schema: type[BaseModel] | None = None,
        schema_name: str | None = None,
        allow_schema_fallback: bool = True,
    ) -> AdvisorGenerationResult: ...


class GeminiAdvisorGenerator:
    """Native Gemini adapter retaining the existing quota fallback behavior."""

    def __init__(self, *, config: AdvisorProviderConfig, client: Any):
        self.config = config
        self.client = client

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        model_routing_mode: str | None = None,
        thinking_level: str = "dynamic",
        temperature: float = 1.0,
        max_output_tokens: int = 4096,
        purpose: str = "advisor",
        response_schema: type[BaseModel] | None = None,
        schema_name: str | None = None,
        allow_schema_fallback: bool = True,
    ) -> AdvisorGenerationResult:
        del schema_name, allow_schema_fallback
        config_kwargs: dict[str, Any] = {
            "system_instruction": system_prompt,
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
        }
        if response_schema is not None:
            config_kwargs.update(
                {
                    "response_mime_type": "application/json",
                    "response_schema": response_schema,
                }
            )
        cfg = types.GenerateContentConfig(
            **config_kwargs,
        )
        if thinking_level != "dynamic":
            cfg.thinking_config = types.ThinkingConfig(thinking_level=thinking_level)

        explicit_model = str(model or "").strip() or None
        candidate_models = route_models_for(
            mode=model_routing_mode,
            purpose=purpose,
            explicit_model=explicit_model,
        )
        if not candidate_models:
            candidate_models = [self.config.model]

        requested_model = candidate_models[0]
        route_event = None
        last_error: Exception | None = None

        for index, candidate_model in enumerate(candidate_models):
            fallback_model = (
                candidate_models[index + 1] if index + 1 < len(candidate_models) else None
            )
            if fallback_model and is_model_temporarily_unavailable(candidate_model):
                route_event = get_model_unavailable_event(
                    requested_model=requested_model,
                    skipped_model=candidate_model,
                    final_model=fallback_model,
                )
                continue

            try:
                response = self.client.models.generate_content(
                    model=candidate_model,
                    contents=user_prompt,
                    config=cfg,
                )
                response_text = response.text or ""
                if not response_text:
                    raise AdvisorProviderError(
                        "Gemini returned an empty response",
                        code="PROVIDER_EMPTY_RESPONSE",
                    )
                if route_event and route_event.final_model != candidate_model:
                    route_event.final_model = candidate_model
                return AdvisorGenerationResult(
                    text=response_text,
                    model=candidate_model,
                    requested_model=requested_model,
                    provider=self.config.provider,
                    routing=route_event_payload(route_event),
                )
            except AdvisorProviderError:
                raise
            except Exception as exc:
                last_error = exc
                failure = classify_model_error(exc)
                if failure and failure.reason != "billing" and fallback_model:
                    mark_model_failure(candidate_model, failure)
                    route_event = route_event or get_model_unavailable_event(
                        requested_model=requested_model,
                        skipped_model=candidate_model,
                        final_model=fallback_model,
                    )
                    if route_event:
                        route_event.reason = failure.reason
                        route_event.error = _redact_sensitive_text(
                            failure.message,
                            self.config.api_key,
                        )
                        route_event.notice = fallback_notice(
                            candidate_model,
                            fallback_model,
                            reason=failure.reason,
                        )
                    continue
                break

        message = _redact_sensitive_text(
            last_error or "No Gemini model was available",
            self.config.api_key,
        )
        if _is_context_limit_error(message):
            raise AdvisorProviderError(
                "The selected Gemini model cannot fit the current campaign briefing "
                "in its context window",
                code="PROVIDER_CONTEXT_LIMIT",
                status_code=400,
            )
        raise AdvisorProviderError(message, code=_gemini_error_code(message))


class OpenAICompatibleAdvisorGenerator:
    """OpenAI Chat Completions adapter used by local and hosted presets."""

    def __init__(
        self,
        *,
        config: AdvisorProviderConfig,
        client: httpx.Client | None = None,
    ):
        self.config = config
        self._client = client

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        model_routing_mode: str | None = None,
        thinking_level: str = "dynamic",
        temperature: float = 1.0,
        max_output_tokens: int = 4096,
        purpose: str = "advisor",
        response_schema: type[BaseModel] | None = None,
        schema_name: str | None = None,
        allow_schema_fallback: bool = True,
    ) -> AdvisorGenerationResult:
        del model_routing_mode, thinking_level, purpose
        if not self.config.is_configured:
            raise AdvisorProviderError(
                f"{self.config.display_name} is not fully configured",
                code="ADVISOR_PROVIDER_NOT_CONFIGURED",
                status_code=400,
            )

        requested_model = str(model or self.config.model).strip()
        effective_user_prompt = user_prompt
        if response_schema is not None:
            effective_user_prompt = _with_json_schema_instruction(
                user_prompt,
                response_schema=response_schema,
            )

        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        if self.config.provider == ADVISOR_PROVIDER_OPENROUTER:
            headers["HTTP-Referer"] = "https://github.com/gitmaan/stellaris-companion"
            headers["X-OpenRouter-Title"] = "Stellaris Companion"

        request_body: dict[str, Any] = {
            "model": requested_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": effective_user_prompt},
            ],
            "max_tokens": max_output_tokens,
            "stream": False,
        }
        if response_schema is None:
            request_body["temperature"] = temperature
        if response_schema is not None:
            request_body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": _structured_schema_name(response_schema, schema_name),
                    "strict": True,
                    "schema": _portable_json_schema(response_schema),
                },
            }
            if self.config.provider == ADVISOR_PROVIDER_OPENROUTER:
                request_body["provider"] = {"require_parameters": True}

        client = self._client or httpx.Client(
            timeout=httpx.Timeout(self.config.timeout_seconds, connect=10.0),
            follow_redirects=False,
        )
        close_client = self._client is None
        schema_fallback_used = False
        try:
            response = client.post(
                f"{self.config.base_url}/chat/completions",
                headers=headers,
                json=request_body,
            )
            if (
                response_schema is not None
                and allow_schema_fallback
                and _should_retry_without_schema(
                    response,
                    provider=self.config.provider,
                )
            ):
                fallback_body = dict(request_body)
                fallback_body.pop("response_format", None)
                fallback_body.pop("provider", None)
                schema_fallback_used = True
                response = client.post(
                    f"{self.config.base_url}/chat/completions",
                    headers=headers,
                    json=fallback_body,
                )
        except httpx.TimeoutException as exc:
            raise AdvisorProviderError(
                f"{self.config.display_name} timed out while generating a response",
                code="PROVIDER_TIMEOUT",
                status_code=504,
            ) from exc
        except httpx.RequestError as exc:
            raise AdvisorProviderError(
                f"Could not connect to {self.config.display_name} at {self.config.base_url}",
                code="PROVIDER_UNAVAILABLE",
                status_code=503,
            ) from exc
        finally:
            if close_client:
                client.close()

        if not response.is_success:
            error_message = _redact_sensitive_text(
                _compatible_error_message(response),
                self.config.api_key,
            )
            if response.status_code == 413 or _is_context_limit_error(error_message):
                raise AdvisorProviderError(
                    f"The selected {self.config.display_name} model cannot fit the "
                    "current campaign briefing in its context window",
                    code="PROVIDER_CONTEXT_LIMIT",
                    status_code=400,
                )
            if response.status_code in {401, 403}:
                code = "PROVIDER_AUTH_FAILED"
            elif response.status_code == 402:
                code = "PROVIDER_BILLING_FAILED"
            elif response.status_code in {408, 504}:
                code = "PROVIDER_TIMEOUT"
            elif response.status_code == 429:
                code = "PROVIDER_RATE_LIMITED"
            elif response.status_code == 404:
                code = "PROVIDER_MODEL_NOT_FOUND"
            elif response.status_code == 503:
                code = "PROVIDER_UNAVAILABLE"
            else:
                code = "PROVIDER_REQUEST_FAILED"
            raise AdvisorProviderError(
                f"{self.config.display_name}: {error_message}",
                code=code,
                status_code=502,
            )

        try:
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            response_text = _content_to_text(content)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AdvisorProviderError(
                f"{self.config.display_name} returned an invalid chat response",
                code="PROVIDER_INVALID_RESPONSE",
            ) from exc

        if not response_text:
            raise AdvisorProviderError(
                f"{self.config.display_name} returned an empty response",
                code="PROVIDER_EMPTY_RESPONSE",
            )

        response_model = str(payload.get("model") or requested_model)
        return AdvisorGenerationResult(
            text=response_text,
            model=response_model,
            requested_model=requested_model,
            provider=self.config.provider,
            schema_fallback_used=schema_fallback_used,
        )


def create_advisor_generator(
    *,
    config: AdvisorProviderConfig,
    gemini_client: Any | None = None,
) -> AdvisorGenerator | None:
    """Create the configured generator, or None when required settings are missing."""
    if not config.is_configured:
        return None
    if config.provider == ADVISOR_PROVIDER_GEMINI:
        if gemini_client is None:
            return None
        return GeminiAdvisorGenerator(config=config, client=gemini_client)
    return OpenAICompatibleAdvisorGenerator(config=config)


def _compatible_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip()[:500] or f"HTTP {response.status_code}"
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        message = error.get("message") or error.get("detail")
        if message:
            return str(message)[:500]
    if error:
        return str(error)[:500]
    return f"HTTP {response.status_code}"


def _redact_sensitive_text(value: Any, *secrets: str, limit: int = 500) -> str:
    message = str(value)
    candidates = {
        candidate
        for secret in secrets
        for candidate in (str(secret or ""), str(secret or "").strip())
        if candidate
    }
    for candidate in sorted(candidates, key=len, reverse=True):
        message = message.replace(candidate, "[redacted]")
    return message[:limit]


def _is_context_limit_error(message: str) -> bool:
    normalized = " ".join(str(message or "").lower().replace("_", " ").split())
    markers = (
        "context length",
        "context window",
        "maximum context",
        "too many tokens",
        "token limit",
        "prompt is too long",
        "input is too long",
        "request is too large",
        "exceeds the model's context",
        "exceeds this model's context",
    )
    return any(marker in normalized for marker in markers)


def _gemini_error_code(message: str) -> str:
    failure = classify_model_error(message)
    if failure is not None:
        if failure.reason == "billing":
            return "PROVIDER_BILLING_FAILED"
        return "PROVIDER_RATE_LIMITED"

    normalized = " ".join(str(message or "").lower().replace("_", " ").split())
    auth_markers = (
        "api key not valid",
        "invalid api key",
        "api key invalid",
        "unauthenticated",
        "permission denied",
    )
    if any(marker in normalized for marker in auth_markers):
        return "PROVIDER_AUTH_FAILED"
    return "PROVIDER_REQUEST_FAILED"


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(part for part in parts if part).strip()
    return ""


def _should_retry_without_schema(response: httpx.Response, *, provider: str) -> bool:
    """Allow one prompt-JSON fallback for structured-parameter incompatibility."""
    message = _compatible_error_message(response)
    if _is_context_limit_error(message):
        return False
    if response.status_code in {400, 422}:
        return True
    if provider != ADVISOR_PROVIDER_OPENROUTER:
        return False
    if response.status_code == 503:
        return True
    if response.status_code != 404:
        return False

    normalized = " ".join(message.lower().replace("_", " ").split())
    route_markers = (
        "no endpoints can handle requested parameters",
        "no endpoints found that can handle requested parameters",
        "routing requirements",
        "require parameters",
    )
    return any(marker in normalized for marker in route_markers)


def _portable_json_schema(response_schema: type[BaseModel]) -> dict[str, Any]:
    """Normalize Pydantic output for strict OpenAI-compatible schema validators."""
    schema = deepcopy(response_schema.model_json_schema())

    def normalize(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                normalize(item)
            return
        if not isinstance(node, dict):
            return

        node.pop("default", None)
        properties = node.get("properties")
        if isinstance(properties, dict):
            node["additionalProperties"] = False
            node["required"] = list(properties)
        for value in node.values():
            normalize(value)

    normalize(schema)
    return schema


def _structured_schema_name(
    response_schema: type[BaseModel],
    explicit_name: str | None,
) -> str:
    raw_name = str(explicit_name or response_schema.__name__ or "structured_response")
    normalized = "".join(
        character.lower() if character.isalnum() else "_" for character in raw_name
    )
    normalized = "_".join(part for part in normalized.split("_") if part)
    return (normalized or "structured_response")[:64]


def _with_json_schema_instruction(
    user_prompt: str,
    *,
    response_schema: type[BaseModel],
) -> str:
    schema_json = json.dumps(
        _portable_json_schema(response_schema),
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return (
        f"{user_prompt.rstrip()}\n\n"
        "=== REQUIRED OUTPUT FORMAT ===\n"
        "Return only one JSON object matching this JSON Schema. "
        "Do not wrap it in Markdown or add commentary.\n"
        f"{schema_json}"
    )
