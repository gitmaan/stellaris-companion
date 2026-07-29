const net = require('node:net')

const ADVISOR_PROVIDER_VALUES = ['gemini', 'ollama', 'lm_studio', 'openrouter', 'custom']
const DEFAULT_ADVISOR_PROVIDER = 'gemini'

const ADVISOR_PROVIDER_PRESETS = {
  ollama: {
    label: 'Ollama',
    baseUrl: 'http://127.0.0.1:11434/v1',
    requiresApiKey: false,
  },
  lm_studio: {
    label: 'LM Studio',
    baseUrl: 'http://127.0.0.1:1234/v1',
    requiresApiKey: false,
  },
  openrouter: {
    label: 'OpenRouter',
    baseUrl: 'https://openrouter.ai/api/v1',
    requiresApiKey: true,
  },
}

function normalizeAdvisorProvider(rawValue) {
  if (typeof rawValue !== 'string') return DEFAULT_ADVISOR_PROVIDER
  const normalized = rawValue.trim().toLowerCase().replace(/[ -]/g, '_')
  const aliases = {
    lmstudio: 'lm_studio',
    open_router: 'openrouter',
    openai_compatible: 'custom',
  }
  const resolved = aliases[normalized] || normalized
  return ADVISOR_PROVIDER_VALUES.includes(resolved) ? resolved : DEFAULT_ADVISOR_PROVIDER
}

function normalizeProviderBaseUrl(rawValue) {
  const value = String(rawValue || '').trim().replace(/\/+$/, '')
  if (!value) return ''

  let parsed
  try {
    parsed = new URL(value)
  } catch {
    throw new Error('Enter a valid HTTP or HTTPS provider URL.')
  }
  if (!['http:', 'https:'].includes(parsed.protocol)) {
    throw new Error('Provider URL must use HTTP or HTTPS.')
  }
  if (parsed.username || parsed.password) {
    throw new Error('Enter API credentials separately from the provider URL.')
  }
  if (parsed.protocol === 'http:' && !isLocalOrPrivateHost(parsed.hostname)) {
    throw new Error(
      'Public provider URLs must use HTTPS. HTTP is allowed only for local or private-network model servers.',
    )
  }

  for (const suffix of ['/chat/completions', '/models']) {
    if (value.endsWith(suffix)) {
      return value.slice(0, -suffix.length).replace(/\/+$/, '')
    }
  }
  return value
}

function isLocalOrPrivateHost(rawHostname) {
  const hostname = String(rawHostname || '')
    .trim()
    .toLowerCase()
    .replace(/^\[|\]$/g, '')
    .replace(/\.$/, '')
  if (!hostname) return false
  if (
    hostname === 'localhost'
    || hostname.endsWith('.localhost')
    || hostname.endsWith('.local')
    || hostname === 'host.docker.internal'
  ) {
    return true
  }

  const address = hostname.split('%', 1)[0]
  if (net.isIPv4(address)) {
    const octets = address.split('.').map(Number)
    return octets[0] === 0
      || octets[0] === 10
      || octets[0] === 127
      || (octets[0] === 169 && octets[1] === 254)
      || (octets[0] === 172 && octets[1] >= 16 && octets[1] <= 31)
      || (octets[0] === 192 && octets[1] === 168)
  }
  if (net.isIPv6(address)) {
    if (address === '::' || address === '::1') return true
    if (address.startsWith('::ffff:')) {
      return isLocalOrPrivateHost(address.slice('::ffff:'.length))
    }
    const firstGroup = Number.parseInt(address.split(':', 1)[0], 16)
    return (firstGroup >= 0xfc00 && firstGroup <= 0xfdff)
      || (firstGroup >= 0xfe80 && firstGroup <= 0xfebf)
  }
  return false
}

function getAdvisorProviderBaseUrl(provider, override = '') {
  const selected = normalizeAdvisorProvider(provider)
  const normalizedOverride = normalizeProviderBaseUrl(override)
  if (normalizedOverride) return normalizedOverride
  return ADVISOR_PROVIDER_PRESETS[selected]?.baseUrl || ''
}

function getAdvisorProviderLabel(provider) {
  const selected = normalizeAdvisorProvider(provider)
  if (selected === 'gemini') return 'Gemini'
  if (selected === 'custom') return 'Custom provider'
  return ADVISOR_PROVIDER_PRESETS[selected]?.label || 'Provider'
}

async function discoverAdvisorModels({
  provider,
  baseUrl,
  apiKey,
  timeoutMs = 10_000,
  fetchImpl = globalThis.fetch,
}) {
  const selected = normalizeAdvisorProvider(provider)
  if (selected === 'gemini') {
    return { ok: true, models: [], baseUrl: '', provider: selected }
  }
  if (typeof fetchImpl !== 'function') {
    return { ok: false, error: 'Model discovery is unavailable in this build.' }
  }

  let resolvedBaseUrl
  try {
    resolvedBaseUrl = getAdvisorProviderBaseUrl(selected, baseUrl)
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : 'Invalid provider URL.' }
  }
  if (!resolvedBaseUrl) {
    return { ok: false, error: 'Enter the provider URL before checking the connection.' }
  }
  if (ADVISOR_PROVIDER_PRESETS[selected]?.requiresApiKey && !String(apiKey || '').trim()) {
    return { ok: false, error: `${getAdvisorProviderLabel(selected)} requires an API key.` }
  }

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  const headers = { Accept: 'application/json' }
  if (apiKey) headers.Authorization = `Bearer ${apiKey}`
  if (selected === 'openrouter') {
    headers['HTTP-Referer'] = 'https://github.com/gitmaan/stellaris-companion'
    headers['X-OpenRouter-Title'] = 'Stellaris Companion'
  }

  try {
    const response = await fetchImpl(`${resolvedBaseUrl}/models`, {
      method: 'GET',
      headers,
      signal: controller.signal,
      redirect: 'error',
    })
    const rawBody = await response.text()
    let payload = null
    try {
      payload = rawBody ? JSON.parse(rawBody) : null
    } catch {
      payload = null
    }

    if (!response.ok) {
      const providerMessage = payload?.error?.message || payload?.error || payload?.detail
      const suffix = providerMessage ? `: ${String(providerMessage).slice(0, 300)}` : ''
      return {
        ok: false,
        error: `${getAdvisorProviderLabel(selected)} returned HTTP ${response.status}${suffix}`,
      }
    }

    const entries = Array.isArray(payload?.data)
      ? payload.data
      : Array.isArray(payload?.models)
        ? payload.models
        : []
    const seen = new Set()
    const models = []
    for (const entry of entries) {
      const id = typeof entry === 'string'
        ? entry.trim()
        : String(entry?.id || entry?.name || entry?.model || '').trim()
      if (!id || seen.has(id)) continue
      seen.add(id)
      models.push({
        id,
        name: String(entry?.name || entry?.display_name || id),
        contextLength: Number(entry?.context_length || entry?.context_window || 0) || undefined,
      })
    }

    return {
      ok: true,
      models,
      baseUrl: resolvedBaseUrl,
      provider: selected,
    }
  } catch (error) {
    if (error?.name === 'AbortError') {
      return { ok: false, error: `${getAdvisorProviderLabel(selected)} did not respond in time.` }
    }
    return {
      ok: false,
      error: `Could not connect to ${getAdvisorProviderLabel(selected)} at ${resolvedBaseUrl}.`,
    }
  } finally {
    clearTimeout(timer)
  }
}

module.exports = {
  ADVISOR_PROVIDER_VALUES,
  ADVISOR_PROVIDER_PRESETS,
  DEFAULT_ADVISOR_PROVIDER,
  isLocalOrPrivateHost,
  normalizeAdvisorProvider,
  normalizeProviderBaseUrl,
  getAdvisorProviderBaseUrl,
  discoverAdvisorModels,
}
