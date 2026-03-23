/**
 * Shared LLM Provider Constants
 * =============================
 *
 * Central source of truth for LLM provider configuration used across
 * Settings page and Onboarding modal.
 */

export const LLM_PROVIDER_VALUES = ['gemini', 'openai', 'anthropic', 'openai-compatible', 'ollama'] as const
export type LLMProvider = (typeof LLM_PROVIDER_VALUES)[number]
export const DEFAULT_LLM_PROVIDER: LLMProvider = 'gemini'

export function normalizeLLMProvider(rawValue: unknown): LLMProvider {
  if (typeof rawValue !== 'string') return DEFAULT_LLM_PROVIDER
  return (LLM_PROVIDER_VALUES as readonly string[]).includes(rawValue)
    ? rawValue as LLMProvider
    : DEFAULT_LLM_PROVIDER
}

export const LLM_PROVIDER_OPTIONS: { value: LLMProvider; label: string }[] = [
  { value: 'gemini', label: 'Google Gemini' },
  { value: 'openai', label: 'OpenAI GPT' },
  { value: 'anthropic', label: 'Anthropic Claude' },
  { value: 'openai-compatible', label: 'OpenAI-Compatible (Local)' },
  { value: 'ollama', label: 'Ollama (Local)' },
]

/**
 * Maps each provider to the type of API key it requires.
 * 'none' means no API key is needed (local providers).
 */
export const PROVIDER_API_KEY_MAP: Record<LLMProvider, 'google' | 'openai' | 'anthropic' | 'none'> = {
  'gemini': 'google',
  'openai': 'openai',
  'anthropic': 'anthropic',
  'openai-compatible': 'none',
  'ollama': 'none',
}

/**
 * Default base URLs for local providers.
 * These should match the Python backend defaults in llm_providers.py.
 */
export const DEFAULT_BASE_URLS: Partial<Record<LLMProvider, string>> = {
  'openai-compatible': 'http://localhost:1234/v1',
  'ollama': 'http://localhost:11434',
}

/**
 * Providers that require model selection (no sensible default).
 */
export const LOCAL_PROVIDERS: LLMProvider[] = ['openai-compatible', 'ollama']

/**
 * Check if a provider is a local provider (doesn't require API key).
 */
export function isLocalProvider(provider: LLMProvider): boolean {
  return LOCAL_PROVIDERS.includes(provider)
}

/**
 * Check if a provider requires an API key.
 */
export function requiresApiKey(provider: LLMProvider): boolean {
  return PROVIDER_API_KEY_MAP[provider] !== 'none'
}

/**
 * Ollama model information from the /api/tags endpoint.
 */
export interface OllamaModel {
  name: string
  size: number
  modifiedAt: string
}
