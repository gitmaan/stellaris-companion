const assert = require('node:assert/strict')
const test = require('node:test')

const {
  discoverAdvisorModels,
  getAdvisorProviderBaseUrl,
  normalizeAdvisorProvider,
  normalizeProviderBaseUrl,
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
