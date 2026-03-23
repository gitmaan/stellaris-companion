"""Tests for the LLM provider abstraction layer.

Tests cover:
- ProviderType enum alias parsing (_missing_ method)
- ProviderType.requires_api_key() method
- LLMConfig.from_env() with provider-specific fallbacks
"""

import os

import pytest

from backend.core.llm_providers import LLMConfig, ProviderType


class TestProviderTypeAliasParsing:
    """Tests for ProviderType._missing_() alias handling."""

    def test_standard_enum_values_work(self):
        """Standard enum values should parse correctly."""
        assert ProviderType("google_gemini") == ProviderType.GOOGLE_GEMINI
        assert ProviderType("openai") == ProviderType.OPENAI
        assert ProviderType("anthropic") == ProviderType.ANTHROPIC
        assert ProviderType("openai_compatible") == ProviderType.OPENAI_COMPATIBLE
        assert ProviderType("ollama") == ProviderType.OLLAMA

    def test_gemini_alias_maps_to_google_gemini(self):
        """'gemini' alias from UI should map to GOOGLE_GEMINI."""
        assert ProviderType("gemini") == ProviderType.GOOGLE_GEMINI

    def test_google_alias_maps_to_google_gemini(self):
        """'google' alias should map to GOOGLE_GEMINI."""
        assert ProviderType("google") == ProviderType.GOOGLE_GEMINI

    def test_hyphenated_openai_compatible_works(self):
        """'openai-compatible' with hyphen (from UI) should work."""
        assert ProviderType("openai-compatible") == ProviderType.OPENAI_COMPATIBLE

    def test_case_insensitive_parsing(self):
        """Provider names should be case-insensitive."""
        assert ProviderType("GOOGLE_GEMINI") == ProviderType.GOOGLE_GEMINI
        assert ProviderType("Gemini") == ProviderType.GOOGLE_GEMINI
        assert ProviderType("OPENAI") == ProviderType.OPENAI
        assert ProviderType("OpenAI-Compatible") == ProviderType.OPENAI_COMPATIBLE
        assert ProviderType("OLLAMA") == ProviderType.OLLAMA

    def test_whitespace_trimmed(self):
        """Leading/trailing whitespace should be trimmed."""
        assert ProviderType("  gemini  ") == ProviderType.GOOGLE_GEMINI
        assert ProviderType("\topenai\n") == ProviderType.OPENAI

    def test_unknown_provider_raises_value_error(self):
        """Unknown provider names should raise ValueError."""
        with pytest.raises(ValueError):
            ProviderType("unknown_provider")
        with pytest.raises(ValueError):
            ProviderType("chatgpt")
        with pytest.raises(ValueError):
            ProviderType("")


class TestProviderTypeRequiresApiKey:
    """Tests for ProviderType.requires_api_key() method."""

    def test_cloud_providers_require_api_key(self):
        """Cloud providers (Gemini, OpenAI, Anthropic) require API keys."""
        assert ProviderType.requires_api_key(ProviderType.GOOGLE_GEMINI) is True
        assert ProviderType.requires_api_key(ProviderType.OPENAI) is True
        assert ProviderType.requires_api_key(ProviderType.ANTHROPIC) is True

    def test_local_providers_do_not_require_api_key(self):
        """Local providers (OpenAI-compatible, Ollama) don't require API keys."""
        assert ProviderType.requires_api_key(ProviderType.OPENAI_COMPATIBLE) is False
        assert ProviderType.requires_api_key(ProviderType.OLLAMA) is False


class TestLLMConfigFromEnv:
    """Tests for LLMConfig.from_env() environment variable handling."""

    def test_defaults_to_google_gemini(self, monkeypatch):
        """Without LLM_PROVIDER, defaults to google_gemini."""
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

        config = LLMConfig.from_env()
        assert config.provider == ProviderType.GOOGLE_GEMINI

    def test_parses_provider_aliases(self, monkeypatch):
        """UI-style provider names should be parsed correctly."""
        monkeypatch.setenv("LLM_PROVIDER", "gemini")
        config = LLMConfig.from_env()
        assert config.provider == ProviderType.GOOGLE_GEMINI

        monkeypatch.setenv("LLM_PROVIDER", "openai-compatible")
        config = LLMConfig.from_env()
        assert config.provider == ProviderType.OPENAI_COMPATIBLE

    def test_google_api_key_fallback_only_for_gemini(self, monkeypatch):
        """GOOGLE_API_KEY fallback should only apply for Gemini provider."""
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.setenv("GOOGLE_API_KEY", "test-google-key")

        # Gemini should pick up GOOGLE_API_KEY
        monkeypatch.setenv("LLM_PROVIDER", "gemini")
        config = LLMConfig.from_env()
        assert config.api_key == "test-google-key"

        # OpenAI should NOT pick up GOOGLE_API_KEY
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        config = LLMConfig.from_env()
        assert config.api_key is None

        # Ollama should NOT pick up GOOGLE_API_KEY
        monkeypatch.setenv("LLM_PROVIDER", "ollama")
        config = LLMConfig.from_env()
        assert config.api_key is None

    def test_openai_api_key_fallback_only_for_openai(self, monkeypatch):
        """OPENAI_API_KEY fallback should only apply for OpenAI provider."""
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")

        # OpenAI should pick up OPENAI_API_KEY
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        config = LLMConfig.from_env()
        assert config.api_key == "test-openai-key"

        # Gemini should NOT pick up OPENAI_API_KEY
        monkeypatch.setenv("LLM_PROVIDER", "gemini")
        config = LLMConfig.from_env()
        assert config.api_key is None

    def test_anthropic_api_key_fallback_only_for_anthropic(self, monkeypatch):
        """ANTHROPIC_API_KEY fallback should only apply for Anthropic provider."""
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")

        # Anthropic should pick up ANTHROPIC_API_KEY
        monkeypatch.setenv("LLM_PROVIDER", "anthropic")
        config = LLMConfig.from_env()
        assert config.api_key == "test-anthropic-key"

        # Gemini should NOT pick up ANTHROPIC_API_KEY
        monkeypatch.setenv("LLM_PROVIDER", "gemini")
        config = LLMConfig.from_env()
        assert config.api_key is None

    def test_llm_api_key_takes_precedence(self, monkeypatch):
        """LLM_API_KEY should take precedence over provider-specific keys."""
        monkeypatch.setenv("LLM_API_KEY", "generic-key")
        monkeypatch.setenv("GOOGLE_API_KEY", "google-key")

        monkeypatch.setenv("LLM_PROVIDER", "gemini")
        config = LLMConfig.from_env()
        assert config.api_key == "generic-key"

    def test_ollama_default_base_url(self, monkeypatch):
        """Ollama should default to localhost:11434."""
        monkeypatch.setenv("LLM_PROVIDER", "ollama")
        monkeypatch.delenv("LLM_BASE_URL", raising=False)
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)

        config = LLMConfig.from_env()
        assert config.base_url == "http://localhost:11434"

    def test_openai_compatible_default_base_url(self, monkeypatch):
        """OpenAI-compatible should default to localhost:1234/v1 (LM Studio style)."""
        monkeypatch.setenv("LLM_PROVIDER", "openai-compatible")
        monkeypatch.delenv("LLM_BASE_URL", raising=False)
        monkeypatch.delenv("OPENAI_COMPATIBLE_BASE_URL", raising=False)

        config = LLMConfig.from_env()
        assert config.base_url == "http://localhost:1234/v1"

    def test_unknown_provider_falls_back_to_gemini(self, monkeypatch):
        """Unknown provider names should fall back to Gemini with a warning."""
        monkeypatch.setenv("LLM_PROVIDER", "unknown_provider_xyz")

        config = LLMConfig.from_env()
        assert config.provider == ProviderType.GOOGLE_GEMINI


class TestLLMConfigDefaults:
    """Tests for LLMConfig default model selection."""

    def test_default_models_for_each_provider(self):
        """Each provider should have a sensible default model."""
        assert LLMConfig.get_default_model(ProviderType.GOOGLE_GEMINI) == "gemini-2.0-flash"
        assert LLMConfig.get_default_model(ProviderType.OPENAI) == "gpt-4o"
        assert LLMConfig.get_default_model(ProviderType.ANTHROPIC) == "claude-sonnet-4-20250514"
        assert LLMConfig.get_default_model(ProviderType.OPENAI_COMPATIBLE) == "default"
        assert LLMConfig.get_default_model(ProviderType.OLLAMA) == "llama3.2"
