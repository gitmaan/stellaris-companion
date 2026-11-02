const assert = require('node:assert/strict')
const test = require('node:test')
const { modelCatalog } = require('../main/modelCatalog')

const {
  discoverAdvisorModels,
  getAdvisorProviderBaseUrl,
  normalizeAdvisorProvider,
  normalizeProviderBaseUrl,
  testAdvisorModel,
} = require('../main/advisorProviders')

test('provider presets resolve known local endpoints', () => {
  assert.equal(normalizeAdvisorProvider('LM Studio'), 'lm_studio')
  assert.equal(getAdvisorProviderBaseUrl('ollama'), 'http://127.0.0.1:11434/v1')
  assert.equal(getAdvisorProviderBaseUrl('lm_studio'), 'http://127.0.0.1:1234/v1')
})

test('custom URL normalization accepts a chat endpoint and returns its API base', () => {
  assert.equal(
    normalizeProviderBaseUrl('http://localhost:8080/v1/chat/completions'),
    'http://localhost:8080/v1',
  )
})

test('custom URL normalization allows private HTTP and rejects public HTTP', () => {
  assert.equal(
    normalizeProviderBaseUrl('http://192.168.1.50:8080/v1'),
    'http://192.168.1.50:8080/v1',
  )
  assert.throws(
    () => normalizeProviderBaseUrl('http://models.example.com/v1'),
    /must use HTTPS/i,
  )
})

test('OpenRouter model discovery normalizes models and sends current attribution headers', async () => {
  let capturedUrl = null
  let capturedAuthorization = null
  let capturedTitle = null
  const fetchImpl = async (url, options) => {
    capturedUrl = url
    capturedAuthorization = options.headers.Authorization
    capturedTitle = options.headers['X-OpenRouter-Title']
    return {
      ok: true,
      status: 200,
      text: async () => JSON.stringify({
        data: [
          { id: 'provider/model-a', name: 'Model A', context_length: 32768 },
          { id: 'provider/model-b' },
          { id: 'provider/model-a' },
        ],
      }),
    }
  }

  const result = await discoverAdvisorModels({
    provider: 'openrouter',
    baseUrl: 'http://127.0.0.1:8080/v1',
    apiKey: 'secret',
    fetchImpl,
  })

  assert.equal(result.ok, true)
  assert.equal(capturedUrl, 'http://127.0.0.1:8080/v1/models?sort=top-weekly')
  assert.equal(capturedAuthorization, 'Bearer secret')
  assert.equal(capturedTitle, 'Stellaris Companion')
  assert.deepEqual(result.models, [
    { id: 'provider/model-a', name: 'Model A', contextLength: 32768 },
    { id: 'provider/model-b', name: 'provider/model-b', contextLength: undefined },
  ])
})

test('OpenRouter discovery recommends verified text models and omits non-chat entries', async () => {
  const result = await discoverAdvisorModels({
    provider: 'openrouter',
    apiKey: 'secret',
    fetchImpl: async () => ({
      ok: true,
      status: 200,
      text: async () => JSON.stringify({
        data: [
          {
            id: 'google/gemini-3.1-flash-lite',
            architecture: { output_modalities: ['text'] },
            supported_parameters: ['response_format'],
          },
          {
            id: 'provider/image-model',
            architecture: { output_modalities: ['image'] },
          },
          { id: 'provider/model:batch' },
        ],
      }),
    }),
  })

  assert.equal(result.ok, true)
  assert.equal(result.models.length, 2)
  assert.equal(result.models[0].id, 'stellaris:latest-stable/gemini-flash-lite')
  assert.equal(result.models[0].resolvedModel, 'google/gemini-3.1-flash-lite')
  assert.equal(result.models[0].recommended, true)
  assert.equal(result.models[0].updatePolicy, 'latest_stable')
  assert.deepEqual(result.models[0].supportedParameters, ['response_format'])
  assert.equal(result.models[1].id, 'google/gemini-3.1-flash-lite')
})

test('OpenRouter model discovery requires a key', async () => {
  const result = await discoverAdvisorModels({
    provider: 'openrouter',
    apiKey: '',
    fetchImpl: async () => {
      throw new Error('fetch should not run')
    },
  })

  assert.equal(result.ok, false)
  assert.match(result.error, /requires an API key/i)
})

test('catalog recommendations follow stable families and never invent absent targets', async () => {
  const ids = modelCatalog.openrouterRecommendations.map(family => modelCatalog.selectionPrefix + family)
  assert.equal(new Set(ids).size, ids.length)
  const discover = data => discoverAdvisorModels({
    provider: 'openrouter', apiKey: 'fixture-key',
    fetchImpl: async () => Response.json({ data }),
  })
  const result = await discover([
    { id: 'anthropic/claude-sonnet-5.5' }, { id: 'provider/new-option' },
    { id: 'google/gemini-3.5-flash-lite' }, { id: 'anthropic/claude-sonnet-5' },
    { id: 'anthropic/claude-sonnet-6-preview' },
  ])
  assert.equal(result.suggestedModel, ids[0])
  assert.equal(result.models.find(model => model.id === ids[2]).resolvedModel, 'anthropic/claude-sonnet-5.5')
  assert.equal(result.models.find(model => model.id === 'anthropic/claude-sonnet-5').recommended, undefined)
  assert.equal(result.models.find(model => model.id === 'provider/new-option').recommended, undefined)
  assert.equal(result.models.some(model => model.id === ids[1]), false)
  const unreviewed = await discover([{ id: 'provider/a' }, { id: 'provider/b' }])
  assert.equal(unreviewed.suggestedModel, undefined)
  assert.equal(unreviewed.models.length, 2)
})

test('missing capability metadata remains selectable while explicitly non-text models are excluded', async () => {
  const result = await discoverAdvisorModels({
    provider: 'custom', baseUrl: 'http://127.0.0.1:8080/v1',
    fetchImpl: async () => Response.json({ data: [
      { id: 'no-metadata' },
      { id: 'invalid-context', context_length: -1, supported_parameters: [] },
      { id: 'text-model', architecture: { output_modalities: ['text'] } },
      { id: 'image-model', architecture: { output_modalities: ['image'] } },
    ] }),
  })
  assert.equal(result.ok, true)
  assert.deepEqual(result.models.map(model => model.id), ['no-metadata', 'invalid-context', 'text-model'])
  assert.equal(result.models[0].contextLength, undefined)
  assert.equal(result.models[0].supportedParameters, undefined)
  assert.equal(result.models[1].contextLength, undefined)
})

test('a malformed catalog is a failed refresh, distinct from a valid empty catalog', async () => {
  const discover = payload => discoverAdvisorModels({
    provider: 'openrouter', apiKey: 'fixture-key',
    fetchImpl: async () => Response.json(payload),
  })
  assert.equal((await discover({ message: 'temporarily unavailable' })).ok, false)
  assert.equal((await discover({ data: null })).errorCode, 'PROVIDER_INVALID_RESPONSE')
  const empty = await discover({ data: [] })
  assert.equal(empty.ok, true)
  assert.deepEqual(empty.models, [])
  assert.equal(empty.suggestedModel, undefined)
})

test('model discovery redacts an echoed API key from provider errors', async () => {
  const result = await discoverAdvisorModels({
    provider: 'openrouter',
    apiKey: 'very-secret-key',
    fetchImpl: async () => ({
      ok: false,
      status: 401,
      text: async () => JSON.stringify({
        error: { message: 'Invalid token very-secret-key' },
      }),
    }),
  })

  assert.equal(result.ok, false)
  assert.match(result.error, /Invalid token/)
  assert.match(result.error, /\[redacted\]/)
  assert.equal(result.error.includes('very-secret-key'), false)
})

test('model test sends a structured Chronicle-compatible probe', async () => {
  let capturedBody = null
  const fetchImpl = async (_url, options) => {
    capturedBody = JSON.parse(options.body)
    return {
      ok: true,
      status: 200,
      text: async () => JSON.stringify({
        model: 'provider/answer-model',
        choices: [{ message: { content: '{"status":"ok"}' } }],
      }),
    }
  }

  const result = await testAdvisorModel({
    provider: 'openrouter',
    model: 'provider/request-model',
    apiKey: 'secret',
    fetchImpl,
  })

  assert.equal(result.ok, true)
  assert.equal(result.model, 'provider/answer-model')
  assert.equal(result.structuredOutput, true)
  assert.equal(capturedBody.response_format.type, 'json_schema')
  assert.deepEqual(capturedBody.provider, { require_parameters: true })
  assert.equal(capturedBody.max_tokens, 512)
  assert.equal('temperature' in capturedBody, false)
  assert.equal(capturedBody.messages[1].content.includes('campaign'), false)
  assert.equal(result.advisorReady, true)
  assert.equal(result.chronicleReady, true)
})

test('model test redacts an echoed API key from provider errors', async () => {
  const result = await testAdvisorModel({
    provider: 'openrouter',
    model: 'provider/model',
    apiKey: 'very-secret-key',
    fetchImpl: async () => ({
      ok: false,
      status: 401,
      text: async () => JSON.stringify({
        error: { message: 'Invalid token very-secret-key' },
      }),
    }),
  })

  assert.equal(result.ok, false)
  assert.match(result.error, /Invalid token/)
  assert.match(result.error, /\[redacted\]/)
  assert.equal(result.error.includes('very-secret-key'), false)
})

test('model test retries without native response format on compatible HTTP 400', async () => {
  const requestBodies = []
  const fetchImpl = async (_url, options) => {
    requestBodies.push(JSON.parse(options.body))
    if (requestBodies.length === 1) {
      return {
        ok: false,
        status: 400,
        text: async () => JSON.stringify({ error: { message: 'response_format unsupported' } }),
      }
    }
    return {
      ok: true,
      status: 200,
      text: async () => JSON.stringify({
        choices: [{ message: { content: '```json\\n{"status":"ok"}\\n```' } }],
      }),
    }
  }

  const result = await testAdvisorModel({
    provider: 'ollama',
    model: 'local-model',
    fetchImpl,
  })

  assert.equal(result.ok, true)
  assert.equal(result.structuredOutput, false)
  assert.equal(result.chronicleReady, true)
  assert.equal(requestBodies.length, 2)
  assert.equal('response_format' in requestBodies[1], false)
  assert.equal('provider' in requestBodies[1], false)
})

test('OpenRouter model test retries when no route supports schema parameters', async () => {
  const requestBodies = []
  const fetchImpl = async (_url, options) => {
    requestBodies.push(JSON.parse(options.body))
    if (requestBodies.length === 1) {
      return {
        ok: false,
        status: 503,
        text: async () => JSON.stringify({
          error: { message: 'No available model provider meets your routing requirements' },
        }),
      }
    }
    return {
      ok: true,
      status: 200,
      text: async () => JSON.stringify({
        choices: [{ message: { content: '{"status":"ok"}' } }],
      }),
    }
  }

  const result = await testAdvisorModel({
    provider: 'openrouter',
    model: 'provider/model',
    apiKey: 'secret',
    fetchImpl,
  })

  assert.equal(result.ok, true)
  assert.equal(result.structuredOutput, false)
  assert.equal(result.chronicleReady, true)
  assert.equal(requestBodies.length, 2)
  assert.equal('response_format' in requestBodies[1], false)
  assert.equal('provider' in requestBodies[1], false)
})

test('model test reports Advisor-only when Chronicle cannot validate the answer', async () => {
  const result = await testAdvisorModel({
    provider: 'lm_studio',
    model: 'local-model',
    fetchImpl: async () => ({
      ok: true,
      status: 200,
      text: async () => JSON.stringify({
        choices: [{ message: { content: 'Ready!' } }],
      }),
    }),
  })

  assert.equal(result.ok, true)
  assert.equal(result.advisorReady, true)
  assert.equal(result.chronicleReady, false)
})

test('OpenRouter model test retries route-specific HTTP 404 without schema parameters', async () => {
  const requestBodies = []
  const fetchImpl = async (_url, options) => {
    requestBodies.push(JSON.parse(options.body))
    if (requestBodies.length === 1) {
      return {
        ok: false,
        status: 404,
        text: async () => JSON.stringify({
          error: { message: 'No endpoints can handle requested parameters' },
        }),
      }
    }
    return {
      ok: true,
      status: 200,
      text: async () => JSON.stringify({
        choices: [{ message: { content: '{"status":"ok"}' } }],
      }),
    }
  }

  const result = await testAdvisorModel({
    provider: 'openrouter',
    model: 'provider/model',
    apiKey: 'secret',
    fetchImpl,
  })

  assert.equal(result.ok, true)
  assert.equal(result.chronicleReady, true)
  assert.equal(requestBodies.length, 2)
  assert.equal('response_format' in requestBodies[1], false)
})

test('Gemini check uses the default model and verifies an actual structured answer', async () => {
  const result = await testAdvisorModel({ provider: 'gemini', apiKey: 'secret', fetchImpl: async (url, options) => {
    if (url.includes('?pageSize=')) return Response.json({ models: [{ name: 'models/gemini-3.5-flash-lite', supportedGenerationMethods: ['generateContent'] }] })
    assert.equal(url, 'https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent')
    assert.equal(options.headers['x-goog-api-key'], 'secret')
    const body = JSON.parse(options.body)
    assert.equal(body.generationConfig.maxOutputTokens, 512)
    assert.equal(body.contents[0].parts[0].text.includes('campaign'), false)
    return { ok: true, text: async () => JSON.stringify({ candidates: [{ content: { parts: [{ thought: true, text: 'Reasoning' }, { text: '{"status":"ok"}' }] } }] }) }
  } })
  assert.equal(result.ok, true)
  assert.equal(result.chronicleReady, true)
})

test('Gemini connection errors distinguish missing models, authentication, and billing', async () => {
  for (const [status, message, code] of [[404, 'Model retired', 'PROVIDER_MODEL_NOT_FOUND'], [400, 'API key not valid', 'PROVIDER_AUTH_FAILED'], [429, 'Quota exceeded', 'PROVIDER_RATE_LIMITED'], [402, 'Credits required', 'PROVIDER_BILLING_FAILED']]) {
    const result = await testAdvisorModel({ provider: 'gemini', apiKey: 'secret', fetchImpl: async () => ({ ok: false, status, text: async () => JSON.stringify({ error: { message } }) }) })
    assert.equal(result.ok, false)
    assert.equal(result.errorCode, code)
  }
})

test('empty model responses never pass the setup check', async () => {
  for (const provider of ['gemini', 'ollama']) {
    const result = await testAdvisorModel({ provider, apiKey: 'secret', model: 'model', fetchImpl: async url => url.includes('?pageSize=') ? Response.json({ models: [{ name: 'models/gemini-3.5-flash-lite', supportedGenerationMethods: ['generateContent'] }] }) : ({ ok: true, text: async () => '{}' }) })
    assert.equal(result.ok, false)
    assert.equal(result.errorCode, 'PROVIDER_EMPTY_RESPONSE')
  }
})

test('model discovery preserves prices without treating unknown pricing as free', async () => {
  const result = await discoverAdvisorModels({ provider: 'openrouter', apiKey: 'secret', fetchImpl: async () => ({ ok: true, text: async () => JSON.stringify({ data: [
    { id: 'paid', pricing: { prompt: '0.00000025', completion: '0.0000015' } },
    { id: 'unknown' }, { id: 'free', pricing: { prompt: '0', completion: '0' } },
  ] }) }) })
  assert.deepEqual(result.models[0].pricing, { inputPerMillion: 0.25, outputPerMillion: 1.5 })
  assert.equal(result.models[1].pricing, undefined)
  assert.deepEqual(result.models[2].pricing, { inputPerMillion: 0, outputPerMillion: 0 })
})


test('Gemini checks the key through its catalog, without putting secrets in the URL', async () => {
  let request
  const result = await discoverAdvisorModels({ provider: 'gemini', apiKey: ' gemini-secret ', fetchImpl: async (url, options) => {
    request = { url, options }
    return Response.json({ models: [
      { name: 'models/text-model', displayName: 'Text model', supportedGenerationMethods: ['generateContent'] },
      { name: 'models/embedding', supportedGenerationMethods: ['embedContent'] },
      { supportedGenerationMethods: ['generateContent'] },
    ] })
  } })
  assert.equal(result.ok, true)
  assert.equal(request.options.headers['x-goog-api-key'], 'gemini-secret')
  assert.equal(request.options.redirect, 'error')
  assert.equal(request.url.includes('gemini-secret'), false)
  assert.deepEqual(result.models.map(model => model.id), ['text-model'])
})

test('Gemini rejects missing, invalid, or unusable keys and redacts provider errors', async () => {
  const missing = await discoverAdvisorModels({ provider: 'gemini', apiKey: '', fetchImpl: () => { throw new Error('unexpected') } })
  assert.equal(missing.ok, false)
  const invalid = await discoverAdvisorModels({ provider: 'gemini', apiKey: 'gemini-secret', fetchImpl: async () => Response.json({ error: { message: 'Invalid gemini-secret' } }, { status: 403 }) })
  assert.equal(invalid.ok, false)
  assert.equal(invalid.error.includes('gemini-secret'), false)
  const empty = await discoverAdvisorModels({ provider: 'gemini', apiKey: 'key', fetchImpl: async () => Response.json({ models: [] }) })
  assert.equal(empty.ok, false)
})
