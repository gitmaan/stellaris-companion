const assert = require('node:assert/strict')
const test = require('node:test')

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
  assert.equal(capturedUrl, 'http://127.0.0.1:8080/v1/models')
  assert.equal(capturedAuthorization, 'Bearer secret')
  assert.equal(capturedTitle, 'Stellaris Companion')
  assert.deepEqual(result.models, [
    { id: 'provider/model-a', name: 'Model A', contextLength: 32768 },
    { id: 'provider/model-b', name: 'provider/model-b', contextLength: undefined },
  ])
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
  assert.equal(capturedBody.messages[1].content.includes('campaign'), false)
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
  assert.equal(requestBodies.length, 2)
  assert.equal('response_format' in requestBodies[1], false)
  assert.equal('provider' in requestBodies[1], false)
})

test('model test rejects an answer Chronicle cannot validate', async () => {
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

  assert.equal(result.ok, false)
  assert.match(result.error, /structured output/i)
})
