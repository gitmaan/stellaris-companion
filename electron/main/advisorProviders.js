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

const OPENROUTER_RECOMMENDED_MODEL_IDS = new Set([
  'google/gemini-3.1-flash-lite',
  'deepseek/deepseek-v4-flash',
  'anthropic/claude-sonnet-5',
])

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

function providerErrorCode(status, message = '') {
  const normalized = String(message).toLowerCase().replace(/_/g, ' ')
  if (/context|token limit|too many tokens/.test(normalized)) return 'PROVIDER_CONTEXT_LIMIT'
  if (status === 402 || /billing|insufficient credits|no available credits/.test(normalized)) return 'PROVIDER_BILLING_FAILED'
  if ([401, 403].includes(status) || /api key.*(invalid|not valid)|invalid api key/.test(normalized)) return 'PROVIDER_AUTH_FAILED'
  if (status === 404 || /model.*not found/.test(normalized)) return 'PROVIDER_MODEL_NOT_FOUND'
  if (status === 429) return 'PROVIDER_RATE_LIMITED'
  if ([408, 504].includes(status)) return 'PROVIDER_TIMEOUT'
  if (status >= 500) return 'PROVIDER_UNAVAILABLE'
  return 'PROVIDER_REQUEST_FAILED'
}

function providerFailure(selected, response, payload, apiKey) {
  const error = providerHttpError(selected, response, payload, apiKey)
  return { ok: false, error, errorCode: providerErrorCode(response.status, error), status: response.status }
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
    return { ok: false, error: `${getAdvisorProviderLabel(selected)} requires an API key.`, errorCode: 'PROVIDER_AUTH_FAILED' }
  }

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  const headers = buildProviderHeaders(selected, apiKey)
  const modelsUrl = selected === 'openrouter'
    ? `${resolvedBaseUrl}/models?sort=top-weekly`
    : `${resolvedBaseUrl}/models`

  try {
    const response = await fetchImpl(modelsUrl, {
      method: 'GET',
      headers,
      signal: controller.signal,
      redirect: 'error',
    })
    const payload = await readJsonResponse(response)

    if (!response.ok) {
      return providerFailure(selected, response, payload, apiKey)
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
      const outputModalities = Array.isArray(entry?.architecture?.output_modalities)
        ? entry.architecture.output_modalities.map(String)
        : []
      if (id.endsWith(':batch') || (outputModalities.length && !outputModalities.includes('text'))) {
        continue
      }
      seen.add(id)
      const modelEntry = {
        id,
        name: String(entry?.name || entry?.display_name || id),
        contextLength: Number(entry?.context_length || entry?.context_window || 0) || undefined,
      }
      const inputPrice = entry?.pricing?.prompt == null || entry.pricing.prompt === '' ? NaN : Number(entry.pricing.prompt)
      const outputPrice = entry?.pricing?.completion == null || entry.pricing.completion === '' ? NaN : Number(entry.pricing.completion)
      if (Number.isFinite(inputPrice) && inputPrice >= 0 && Number.isFinite(outputPrice) && outputPrice >= 0) {
        modelEntry.pricing = { inputPerMillion: inputPrice * 1_000_000, outputPerMillion: outputPrice * 1_000_000 }
      }
      if (Array.isArray(entry?.supported_parameters)) {
        modelEntry.supportedParameters = entry.supported_parameters.map(String)
      }
      if (outputModalities.length) modelEntry.outputModalities = outputModalities
      if (selected === 'openrouter' && OPENROUTER_RECOMMENDED_MODEL_IDS.has(id)) {
        modelEntry.recommended = true
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
      return { ok: false, error: `${getAdvisorProviderLabel(selected)} did not respond in time.`, errorCode: 'PROVIDER_TIMEOUT' }
    }
    return {
      ok: false,
      error: `Could not connect to ${getAdvisorProviderLabel(selected)} at ${resolvedBaseUrl}.`,
      errorCode: 'PROVIDER_UNAVAILABLE',
    }
  } finally {
    clearTimeout(timer)
  }
}

async function testGeminiConnection({ apiKey, timeoutMs, fetchImpl }) {
  if (!String(apiKey || '').trim()) {
    return { ok: false, errorCode: 'PROVIDER_AUTH_FAILED', error: 'Enter a Gemini API key.' }
  }
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  // Matches the default Advisor route in backend/core/model_routing.py.
  const model = 'gemini-3.1-flash-lite'
  try {
    const response = await fetchImpl(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-goog-api-key': apiKey.trim() },
      body: JSON.stringify({
        contents: [{ parts: [{ text: 'Return only a JSON object with status set to ok.' }] }],
        generationConfig: { maxOutputTokens: 512, responseMimeType: 'application/json', thinkingConfig: { thinkingLevel: 'MINIMAL' } },
      }),
      signal: controller.signal,
      redirect: 'error',
    })
    const payload = await readJsonResponse(response)
    if (!response.ok) return providerFailure('gemini', response, payload, apiKey)
    const answer = payload?.candidates?.[0]?.content?.parts?.filter(part => !part.thought).map(part => part.text || '').join('') || ''
    if (!answer.trim()) return { ok: false, errorCode: 'PROVIDER_EMPTY_RESPONSE', error: 'Gemini returned no answer.' }
    let chronicleReady = false
    try { chronicleReady = JSON.parse(answer).status === 'ok' } catch { /* Plain text can still serve Advisor. */ }
    return { ok: true, provider: 'gemini', model, advisorReady: true, chronicleReady, structuredOutput: chronicleReady }
  } catch (error) {
    return { ok: false, errorCode: error?.name === 'AbortError' ? 'PROVIDER_TIMEOUT' : 'PROVIDER_UNAVAILABLE', error: 'Could not complete the Gemini connection check.' }
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
    return testGeminiConnection({ apiKey, timeoutMs, fetchImpl })
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
    return { ok: false, error: `${getAdvisorProviderLabel(selected)} requires an API key.`, errorCode: 'PROVIDER_AUTH_FAILED' }
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
        content: [
          'Return exactly one JSON object with status set to ok. Do not add Markdown.',
          'The JSON must match this schema:',
          JSON.stringify(responseSchema),
        ].join('\n'),
      },
    ],
    max_tokens: 512,
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
    if (shouldRetryWithoutSchema(selected, response, payload)) {
      structuredOutput = false
      ;({ response, payload } = await send(baseBody))
    }
    if (!response.ok) {
      return providerFailure(selected, response, payload, apiKey)
    }

    const content = payload?.choices?.[0]?.message?.content
    const text = typeof content === 'string'
      ? content
      : Array.isArray(content)
        ? content.map((part) => typeof part === 'string' ? part : part?.text || '').join('\n')
        : ''
    if (!text.trim()) return { ok: false, errorCode: 'PROVIDER_EMPTY_RESPONSE', error: 'The model returned no answer.' }
    const start = text.indexOf('{')
    const end = text.lastIndexOf('}')
    if (start < 0 || end < start) {
      return {
        ok: true,
        advisorReady: true,
        chronicleReady: false,
        provider: selected,
        model: String(payload?.model || selectedModel),
        baseUrl: resolvedBaseUrl,
        structuredOutput: false,
      }
    }

    let probe
    try {
      probe = JSON.parse(text.slice(start, end + 1))
    } catch {
      return {
        ok: true,
        advisorReady: true,
        chronicleReady: false,
        provider: selected,
        model: String(payload?.model || selectedModel),
        baseUrl: resolvedBaseUrl,
        structuredOutput: false,
      }
    }
    if (String(probe?.status || '').toLowerCase() !== 'ok') {
      return {
        ok: true,
        advisorReady: true,
        chronicleReady: false,
        provider: selected,
        model: String(payload?.model || selectedModel),
        baseUrl: resolvedBaseUrl,
        structuredOutput: false,
      }
    }

    return {
      ok: true,
      provider: selected,
      model: String(payload?.model || selectedModel),
      baseUrl: resolvedBaseUrl,
      advisorReady: true,
      chronicleReady: true,
      structuredOutput,
    }
  } catch (error) {
    if (error?.name === 'AbortError') {
      return {
        ok: false,
        error: `${getAdvisorProviderLabel(selected)} did not complete the model test in time.`,
        errorCode: 'PROVIDER_TIMEOUT',
      }
    }
    return {
      ok: false,
      error: `Could not connect to ${getAdvisorProviderLabel(selected)} at ${resolvedBaseUrl}.`,
      errorCode: 'PROVIDER_UNAVAILABLE',
    }
  } finally {
    clearTimeout(timer)
  }
}

function shouldRetryWithoutSchema(selected, response, payload) {
  const message = String(payload?.error?.message || payload?.error || payload?.detail || '')
    .toLowerCase()
    .replaceAll('_', ' ')
    .replace(/\s+/g, ' ')
    .trim()
  const contextMarkers = [
    'context length',
    'context window',
    'maximum context',
    'too many tokens',
    'token limit',
    'prompt is too long',
    'input is too long',
  ]
  if (contextMarkers.some((marker) => message.includes(marker))) return false
  if (response.status === 400 || response.status === 422) return true
  if (selected !== 'openrouter') return false
  if (response.status === 503) return true
  if (response.status !== 404) return false
  return [
    'no endpoints can handle requested parameters',
    'no endpoints found that can handle requested parameters',
    'routing requirements',
    'require parameters',
  ].some((marker) => message.includes(marker))
}

module.exports = {
  ADVISOR_PROVIDER_VALUES,
  ADVISOR_PROVIDER_PRESETS,
  OPENROUTER_RECOMMENDED_MODEL_IDS,
  DEFAULT_ADVISOR_PROVIDER,
  isLocalOrPrivateHost,
  normalizeAdvisorProvider,
  normalizeProviderBaseUrl,
  getAdvisorProviderBaseUrl,
  discoverAdvisorModels,
  testAdvisorModel,
}
