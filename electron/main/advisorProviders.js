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

function buildProviderHeaders(selected, apiKey, { contentType = false } = {}) {
  const headers = contentType
    ? { Accept: 'application/json', 'Content-Type': 'application/json' }
    : { Accept: 'application/json' }
  if (apiKey) headers.Authorization = `Bearer ${apiKey}`
  if (selected === 'openrouter') {
    headers['HTTP-Referer'] = 'https://github.com/gitmaan/stellaris-companion'
    headers['X-OpenRouter-Title'] = 'Stellaris Companion'
  }
  return headers
}

function redactProviderMessage(rawMessage, apiKey) {
  let message = String(rawMessage)
  const candidates = [...new Set([String(apiKey || ''), String(apiKey || '').trim()])]
    .filter(Boolean)
    .sort((left, right) => right.length - left.length)
  for (const candidate of candidates) {
    message = message.split(candidate).join('[redacted]')
  }
  return message.slice(0, 300)
}

function providerHttpError(selected, response, payload, apiKey) {
  const providerMessage = payload?.error?.message || payload?.error || payload?.detail
  const suffix = providerMessage ? `: ${redactProviderMessage(providerMessage, apiKey)}` : ''
  return `${getAdvisorProviderLabel(selected)} returned HTTP ${response.status}${suffix}`
}

async function readJsonResponse(response) {
  const rawBody = await response.text()
  try {
    return rawBody ? JSON.parse(rawBody) : null
  } catch {
    return null
  }
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
  const headers = buildProviderHeaders(selected, apiKey)

  try {
    const response = await fetchImpl(`${resolvedBaseUrl}/models`, {
      method: 'GET',
      headers,
      signal: controller.signal,
      redirect: 'error',
    })
    const payload = await readJsonResponse(response)

    if (!response.ok) {
      return {
        ok: false,
        error: providerHttpError(selected, response, payload, apiKey),
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
      const modelEntry = {
        id,
        name: String(entry?.name || entry?.display_name || id),
        contextLength: Number(entry?.context_length || entry?.context_window || 0) || undefined,
      }
      if (Array.isArray(entry?.supported_parameters)) {
        modelEntry.supportedParameters = entry.supported_parameters.map(String)
      }
      models.push(modelEntry)
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

async function testAdvisorModel({
  provider,
  baseUrl,
  apiKey,
  model,
  timeoutMs = 30_000,
  fetchImpl = globalThis.fetch,
}) {
  const selected = normalizeAdvisorProvider(provider)
  if (selected === 'gemini') {
    return { ok: false, error: 'Gemini is verified when the app starts its AI connection.' }
  }
  if (typeof fetchImpl !== 'function') {
    return { ok: false, error: 'Model testing is unavailable in this build.' }
  }

  let resolvedBaseUrl
  try {
    resolvedBaseUrl = getAdvisorProviderBaseUrl(selected, baseUrl)
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : 'Invalid provider URL.' }
  }
  if (!resolvedBaseUrl) {
    return { ok: false, error: 'Enter the provider URL before testing the model.' }
  }
  if (ADVISOR_PROVIDER_PRESETS[selected]?.requiresApiKey && !String(apiKey || '').trim()) {
    return { ok: false, error: `${getAdvisorProviderLabel(selected)} requires an API key.` }
  }

  const selectedModel = String(model || '').trim()
  if (!selectedModel) {
    return { ok: false, error: 'Choose or enter a model before testing it.' }
  }

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  const headers = buildProviderHeaders(selected, apiKey, { contentType: true })
  const responseSchema = {
    type: 'object',
    additionalProperties: false,
    properties: {
      status: { type: 'string', enum: ['ok'] },
    },
    required: ['status'],
  }
  const baseBody = {
    model: selectedModel,
    messages: [
      {
        role: 'system',
        content: 'This is a private connection test. Return only JSON matching the requested schema.',
      },
      {
        role: 'user',
        content: 'Return exactly one JSON object with status set to ok. Do not add Markdown.',
      },
    ],
    temperature: 0,
    max_tokens: 32,
    stream: false,
  }
  const structuredBody = {
    ...baseBody,
    response_format: {
      type: 'json_schema',
      json_schema: {
        name: 'stellaris_connection_test',
        strict: true,
        schema: responseSchema,
      },
    },
  }
  if (selected === 'openrouter') {
    structuredBody.provider = { require_parameters: true }
  }

  const send = async (body) => {
    const response = await fetchImpl(`${resolvedBaseUrl}/chat/completions`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      signal: controller.signal,
      redirect: 'error',
    })
    return { response, payload: await readJsonResponse(response) }
  }

  try {
    let structuredOutput = true
    let { response, payload } = await send(structuredBody)
    if (response.status === 400) {
      structuredOutput = false
      ;({ response, payload } = await send(baseBody))
    }
    if (!response.ok) {
      return { ok: false, error: providerHttpError(selected, response, payload, apiKey) }
    }

    const content = payload?.choices?.[0]?.message?.content
    const text = typeof content === 'string'
      ? content
      : Array.isArray(content)
        ? content.map((part) => typeof part === 'string' ? part : part?.text || '').join('\n')
        : ''
    const start = text.indexOf('{')
    const end = text.lastIndexOf('}')
    if (start < 0 || end < start) {
      return {
        ok: false,
        error: `${getAdvisorProviderLabel(selected)} answered, but did not return usable structured output.`,
      }
    }

    let probe
    try {
      probe = JSON.parse(text.slice(start, end + 1))
    } catch {
      return {
        ok: false,
        error: `${getAdvisorProviderLabel(selected)} answered, but returned invalid JSON.`,
      }
    }
    if (String(probe?.status || '').toLowerCase() !== 'ok') {
      return {
        ok: false,
        error: `${getAdvisorProviderLabel(selected)} answered, but failed the structured output check.`,
      }
    }

    return {
      ok: true,
      provider: selected,
      model: String(payload?.model || selectedModel),
      baseUrl: resolvedBaseUrl,
      structuredOutput,
    }
  } catch (error) {
    if (error?.name === 'AbortError') {
      return {
        ok: false,
        error: `${getAdvisorProviderLabel(selected)} did not complete the model test in time.`,
      }
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
  testAdvisorModel,
}
