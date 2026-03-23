"""
LLM Provider Abstraction Layer
==============================

Provides a unified interface for multiple LLM backends:
- Google Gemini (cloud)
- OpenAI GPT (cloud)
- Anthropic Claude (cloud)
- OpenAI-compatible API (local: LM Studio, vLLM, LocalAI, text-generation-webui)
- Ollama native API (local)

Usage:
    from backend.core.llm_providers import get_provider, LLMConfig

    config = LLMConfig.from_env()
    provider = get_provider(config)
    response = provider.generate(
        prompt="Hello, world!",
        system_prompt="You are a helpful assistant.",
        temperature=0.7,
        max_tokens=1024,
    )
"""

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypeVar

logger = logging.getLogger(__name__)


class ProviderType(str, Enum):
    """Supported LLM provider types."""

    GOOGLE_GEMINI = "google_gemini"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OPENAI_COMPATIBLE = "openai_compatible"
    OLLAMA = "ollama"

    @classmethod
    def _missing_(cls, value: object) -> "ProviderType | None":
        """Allow common alias values used by the UI / environment configuration.

        Examples:
            - "gemini" -> ProviderType.GOOGLE_GEMINI
            - "openai-compatible" -> ProviderType.OPENAI_COMPATIBLE
        """
        if not isinstance(value, str):
            return None
        # Normalize: lowercase, replace hyphens with underscores
        normalized = value.strip().lower().replace("-", "_")

        # First, try to match normalized value directly to an existing enum value
        for member in cls:
            if member.value == normalized:
                return member

        # Then, handle known aliases that don't match 1:1 with enum values
        aliases = {
            "gemini": cls.GOOGLE_GEMINI,
            "google": cls.GOOGLE_GEMINI,
        }
        return aliases.get(normalized)

    @classmethod
    def requires_api_key(cls, provider: "ProviderType") -> bool:
        """Check if a provider requires an API key."""
        return provider in {cls.GOOGLE_GEMINI, cls.OPENAI, cls.ANTHROPIC}


@dataclass
class LLMConfig:
    """Configuration for LLM provider.

    Attributes:
        provider: The provider type to use
        api_key: API key for cloud providers (not needed for local)
        model: Model name/ID to use
        base_url: Base URL for API (required for local providers)
        temperature: Default temperature for generation
        max_tokens: Default max tokens for generation
        timeout: Request timeout in seconds
        extra: Provider-specific extra configuration
    """

    provider: ProviderType
    api_key: str | None = None
    model: str | None = None
    base_url: str | None = None
    temperature: float = 1.0
    max_tokens: int = 4096
    timeout: int = 120
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def get_default_model(cls, provider: ProviderType) -> str:
        """Get the default model for a provider."""
        defaults = {
            ProviderType.GOOGLE_GEMINI: "gemini-2.0-flash",
            ProviderType.OPENAI: "gpt-4o",
            ProviderType.ANTHROPIC: "claude-sonnet-4-20250514",
            ProviderType.OPENAI_COMPATIBLE: "default",
            ProviderType.OLLAMA: "llama3.2",
        }
        return defaults.get(provider, "default")

    @classmethod
    def from_env(cls) -> "LLMConfig":
        """Create config from environment variables.

        Environment variables:
            LLM_PROVIDER: Provider type (google_gemini, openai, anthropic, openai_compatible, ollama)
            LLM_API_KEY: API key (also checks provider-specific vars like GOOGLE_API_KEY)
            LLM_MODEL: Model name
            LLM_BASE_URL: Base URL for local providers
            LLM_TEMPERATURE: Default temperature
            LLM_MAX_TOKENS: Default max tokens
            LLM_TIMEOUT: Request timeout in seconds

        Falls back to GOOGLE_API_KEY for backward compatibility.
        """
        provider_str = os.environ.get("LLM_PROVIDER", "google_gemini").lower()

        try:
            provider = ProviderType(provider_str)
        except ValueError:
            logger.warning(f"Unknown provider '{provider_str}', defaulting to google_gemini")
            provider = ProviderType.GOOGLE_GEMINI

        # Get API key with fallbacks
        api_key = os.environ.get("LLM_API_KEY")
        if not api_key:
            if provider == ProviderType.GOOGLE_GEMINI:
                api_key = os.environ.get("GOOGLE_API_KEY")
            elif provider == ProviderType.OPENAI:
                api_key = os.environ.get("OPENAI_API_KEY")
            elif provider == ProviderType.ANTHROPIC:
                api_key = os.environ.get("ANTHROPIC_API_KEY")

        # Get model with provider-specific defaults
        model = os.environ.get("LLM_MODEL")
        if not model:
            model = cls.get_default_model(provider)

        # Get base URL for local providers
        base_url = os.environ.get("LLM_BASE_URL")
        if not base_url:
            if provider == ProviderType.OLLAMA:
                base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
            elif provider == ProviderType.OPENAI_COMPATIBLE:
                # Default to LM Studio-style endpoint to match Electron UI
                base_url = os.environ.get("OPENAI_COMPATIBLE_BASE_URL", "http://localhost:1234/v1")

        # Parse numeric values
        temperature = float(os.environ.get("LLM_TEMPERATURE", "1.0"))
        max_tokens = int(os.environ.get("LLM_MAX_TOKENS", "4096"))
        timeout = int(os.environ.get("LLM_TIMEOUT", "120"))

        return cls(
            provider=provider,
            api_key=api_key,
            model=model,
            base_url=base_url,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )


@dataclass
class LLMResponse:
    """Response from LLM generation.

    Attributes:
        text: The generated text content
        model: Model that generated the response
        usage: Token usage statistics (if available)
        raw: Raw response object from the provider
    """

    text: str
    model: str | None = None
    usage: dict[str, int] | None = None
    raw: Any = None


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, config: LLMConfig):
        self.config = config
        self._client: Any = None

    @property
    @abstractmethod
    def client(self) -> Any:
        """Lazy-initialized client instance."""
        pass

    @abstractmethod
    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        """Generate text from the LLM.

        Args:
            prompt: User prompt/message
            system_prompt: System instructions
            temperature: Generation temperature (uses config default if None)
            max_tokens: Maximum tokens to generate (uses config default if None)
            response_format: Optional structured output schema

        Returns:
            LLMResponse with generated text
        """
        pass

    @abstractmethod
    def generate_structured(
        self,
        prompt: str,
        schema: type,
        *,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Generate structured output from the LLM.

        Args:
            prompt: User prompt/message
            schema: Pydantic model class for response schema
            system_prompt: System instructions
            temperature: Generation temperature
            max_tokens: Maximum tokens to generate

        Returns:
            LLMResponse with text containing valid JSON matching schema
        """
        pass

    def _get_temperature(self, temperature: float | None) -> float:
        return temperature if temperature is not None else self.config.temperature

    def _get_max_tokens(self, max_tokens: int | None) -> int:
        return max_tokens if max_tokens is not None else self.config.max_tokens


class GeminiProvider(LLMProvider):
    """Google Gemini provider using the google-genai SDK."""

    @property
    def client(self):
        if self._client is None:
            try:
                from google import genai
            except ImportError:
                raise ImportError(
                    "google-genai package not installed. Run: pip install google-genai"
                )

            if not self.config.api_key:
                raise ValueError("GOOGLE_API_KEY or LLM_API_KEY not set for Gemini provider")

            self._client = genai.Client(api_key=self.config.api_key)
        return self._client

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        from google.genai import types

        config_dict: dict[str, Any] = {
            "temperature": self._get_temperature(temperature),
            "max_output_tokens": self._get_max_tokens(max_tokens),
        }

        if system_prompt:
            config_dict["system_instruction"] = system_prompt

        if response_format:
            config_dict["response_mime_type"] = "application/json"
            if "schema" in response_format:
                config_dict["response_schema"] = response_format["schema"]

        response = self.client.models.generate_content(
            model=self.config.model or "gemini-2.0-flash",
            contents=prompt,
            config=types.GenerateContentConfig(**config_dict),
        )

        return LLMResponse(
            text=response.text or "",
            model=self.config.model,
            raw=response,
        )

    def generate_structured(
        self,
        prompt: str,
        schema: type,
        *,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        from google.genai import types

        config_dict: dict[str, Any] = {
            "temperature": self._get_temperature(temperature),
            "max_output_tokens": self._get_max_tokens(max_tokens),
            "response_mime_type": "application/json",
            "response_schema": schema,
        }

        if system_prompt:
            config_dict["system_instruction"] = system_prompt

        response = self.client.models.generate_content(
            model=self.config.model or "gemini-2.0-flash",
            contents=prompt,
            config=types.GenerateContentConfig(**config_dict),
        )

        return LLMResponse(
            text=response.text or "",
            model=self.config.model,
            raw=response,
        )


class OpenAIProvider(LLMProvider):
    """OpenAI GPT provider using the official openai SDK."""

    @property
    def client(self):
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError:
                raise ImportError("openai package not installed. Run: pip install openai")

            if not self.config.api_key:
                raise ValueError("OPENAI_API_KEY or LLM_API_KEY not set for OpenAI provider")

            self._client = OpenAI(
                api_key=self.config.api_key,
                timeout=self.config.timeout,
            )
        return self._client

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict[str, Any] = {
            "model": self.config.model or "gpt-4o",
            "messages": messages,
            "temperature": self._get_temperature(temperature),
            "max_tokens": self._get_max_tokens(max_tokens),
        }

        if response_format and response_format.get("type") == "json_object":
            kwargs["response_format"] = {"type": "json_object"}

        response = self.client.chat.completions.create(**kwargs)

        usage = None
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return LLMResponse(
            text=response.choices[0].message.content or "",
            model=response.model,
            usage=usage,
            raw=response,
        )

    def generate_structured(
        self,
        prompt: str,
        schema: type,
        *,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        # For OpenAI, we add JSON instructions to the prompt and use json_object mode
        json_instruction = (
            f"\n\nRespond with valid JSON matching this schema:\n"
            f"{json.dumps(schema.model_json_schema(), indent=2)}"
        )

        full_system = (system_prompt or "") + json_instruction

        return self.generate(
            prompt=prompt,
            system_prompt=full_system,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider using the official anthropic SDK."""

    @property
    def client(self):
        if self._client is None:
            try:
                from anthropic import Anthropic
            except ImportError:
                raise ImportError("anthropic package not installed. Run: pip install anthropic")

            if not self.config.api_key:
                raise ValueError("ANTHROPIC_API_KEY or LLM_API_KEY not set for Anthropic provider")

            self._client = Anthropic(
                api_key=self.config.api_key,
                timeout=self.config.timeout,
            )
        return self._client

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": self.config.model or "claude-sonnet-4-20250514",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self._get_temperature(temperature),
            "max_tokens": self._get_max_tokens(max_tokens),
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        response = self.client.messages.create(**kwargs)

        usage = None
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            }

        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text += block.text

        return LLMResponse(
            text=text,
            model=response.model,
            usage=usage,
            raw=response,
        )

    def generate_structured(
        self,
        prompt: str,
        schema: type,
        *,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        # For Anthropic, we add JSON instructions to the system prompt
        json_instruction = (
            f"\n\nYou must respond with valid JSON matching this schema:\n"
            f"{json.dumps(schema.model_json_schema(), indent=2)}\n"
            f"Output ONLY the JSON, no other text."
        )

        full_system = (system_prompt or "") + json_instruction

        return self.generate(
            prompt=prompt,
            system_prompt=full_system,
            temperature=temperature,
            max_tokens=max_tokens,
        )


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI-compatible API provider for local servers.

    Supports: LM Studio, vLLM, LocalAI, text-generation-webui, etc.
    """

    @property
    def client(self):
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError:
                raise ImportError("openai package not installed. Run: pip install openai")

            if not self.config.base_url:
                raise ValueError("LLM_BASE_URL not set for OpenAI-compatible provider")

            # Most local servers don't need an API key, but some do
            api_key = self.config.api_key or "not-needed"

            self._client = OpenAI(
                api_key=api_key,
                base_url=self.config.base_url,
                timeout=self.config.timeout,
            )
        return self._client

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict[str, Any] = {
            "model": self.config.model or "default",
            "messages": messages,
            "temperature": self._get_temperature(temperature),
            "max_tokens": self._get_max_tokens(max_tokens),
        }

        # Only add response_format if the server supports it
        # Most local servers don't, so we skip it by default
        if response_format and self.config.extra.get("supports_json_mode"):
            kwargs["response_format"] = {"type": "json_object"}

        response = self.client.chat.completions.create(**kwargs)

        usage = None
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return LLMResponse(
            text=response.choices[0].message.content or "",
            model=response.model,
            usage=usage,
            raw=response,
        )

    def generate_structured(
        self,
        prompt: str,
        schema: type,
        *,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        # For local models, we add JSON instructions to the prompt
        json_instruction = (
            f"\n\nYou must respond with valid JSON matching this schema:\n"
            f"{json.dumps(schema.model_json_schema(), indent=2)}\n"
            f"Output ONLY the JSON, no other text."
        )

        full_system = (system_prompt or "") + json_instruction

        return self.generate(
            prompt=prompt,
            system_prompt=full_system,
            temperature=temperature,
            max_tokens=max_tokens,
        )


class OllamaProvider(LLMProvider):
    """Ollama native API provider for local models.

    Uses Ollama's native REST API directly for maximum compatibility.
    """

    @property
    def client(self):
        # Ollama uses direct HTTP requests, so we just validate config
        if self._client is None:
            try:
                import httpx
            except ImportError:
                raise ImportError("httpx package not installed. Run: pip install httpx")

            base_url = self.config.base_url or "http://localhost:11434"
            self._client = httpx.Client(
                base_url=base_url,
                timeout=self.config.timeout,
            )
        return self._client

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.config.model or "llama3.2",
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self._get_temperature(temperature),
                "num_predict": self._get_max_tokens(max_tokens),
            },
        }

        if system_prompt:
            payload["system"] = system_prompt

        if response_format and response_format.get("type") == "json_object":
            payload["format"] = "json"

        response = self.client.post("/api/generate", json=payload)
        response.raise_for_status()
        data = response.json()

        usage = None
        if "prompt_eval_count" in data or "eval_count" in data:
            usage = {
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
                "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
            }

        return LLMResponse(
            text=data.get("response", ""),
            model=data.get("model"),
            usage=usage,
            raw=data,
        )

    def generate_structured(
        self,
        prompt: str,
        schema: type,
        *,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        # For Ollama, we can use the format: json option plus schema instructions
        json_instruction = (
            f"\n\nYou must respond with valid JSON matching this schema:\n"
            f"{json.dumps(schema.model_json_schema(), indent=2)}\n"
            f"Output ONLY the JSON, no other text."
        )

        full_system = (system_prompt or "") + json_instruction

        return self.generate(
            prompt=prompt,
            system_prompt=full_system,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )


# Provider registry
_PROVIDERS: dict[ProviderType, type[LLMProvider]] = {
    ProviderType.GOOGLE_GEMINI: GeminiProvider,
    ProviderType.OPENAI: OpenAIProvider,
    ProviderType.ANTHROPIC: AnthropicProvider,
    ProviderType.OPENAI_COMPATIBLE: OpenAICompatibleProvider,
    ProviderType.OLLAMA: OllamaProvider,
}


def get_provider(config: LLMConfig | None = None) -> LLMProvider:
    """Get an LLM provider instance.

    Args:
        config: LLM configuration. If None, loads from environment.

    Returns:
        Configured LLMProvider instance.
    """
    if config is None:
        config = LLMConfig.from_env()

    provider_class = _PROVIDERS.get(config.provider)
    if provider_class is None:
        raise ValueError(f"Unknown provider type: {config.provider}")

    return provider_class(config)


def get_provider_from_env() -> LLMProvider:
    """Convenience function to get provider from environment variables."""
    return get_provider(LLMConfig.from_env())


# Backward compatibility: create a default provider that mimics the old genai.Client interface
class LegacyGeminiCompatClient:
    """Wrapper that provides backward compatibility with the old genai.Client interface.

    This allows gradual migration of existing code.
    """

    def __init__(self, provider: LLMProvider):
        self._provider = provider
        self.models = self

    def generate_content(
        self,
        model: str,
        contents: str,
        config: Any = None,
    ) -> Any:
        """Generate content with backward-compatible interface."""
        system_prompt = None
        temperature = 1.0
        max_tokens = 4096
        response_schema = None

        if config is not None:
            if hasattr(config, "system_instruction"):
                system_prompt = config.system_instruction
            elif isinstance(config, dict):
                system_prompt = config.get("system_instruction")

            if hasattr(config, "temperature"):
                temperature = config.temperature
            elif isinstance(config, dict):
                temperature = config.get("temperature", 1.0)

            if hasattr(config, "max_output_tokens"):
                max_tokens = config.max_output_tokens
            elif isinstance(config, dict):
                max_tokens = config.get("max_output_tokens", 4096)

            if hasattr(config, "response_schema"):
                response_schema = config.response_schema
            elif isinstance(config, dict):
                response_schema = config.get("response_schema")

        if response_schema:
            response = self._provider.generate_structured(
                prompt=contents,
                schema=response_schema,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        else:
            response = self._provider.generate(
                prompt=contents,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        # Return a response object with .text attribute for compatibility
        return _LegacyResponse(response)


class _LegacyResponse:
    """Response wrapper for backward compatibility."""

    def __init__(self, response: LLMResponse):
        self._response = response
        self.text = response.text
