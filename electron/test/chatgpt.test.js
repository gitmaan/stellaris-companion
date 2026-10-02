const { test } = require('node:test')
const assert = require('node:assert/strict')
const crypto = require('node:crypto')
const { createChatGPTService, verifyIdentityToken, readResponseStream } = require('../main/chatgpt')
const { createChatGPTBridge } = require('../main/chatgptBridge')

function stream(events, chunkSize = 7) {
  const bytes = new TextEncoder().encode(events.map(event => `data: ${JSON.stringify(event)}\r\n\r\n`).join(''))
  return new Response(new ReadableStream({ start(controller) {
    for (let index = 0; index < bytes.length; index += chunkSize) controller.enqueue(bytes.slice(index, index + chunkSize))
    controller.close()
  } }))
}
const completed = (text = '{"ready":true}') => ({ type: 'response.completed', response: {
  model: 'strategist', status: 'completed', output: [{ content: [{ type: 'output_text', text }] }],
} })
function harness(overrides = {}) {
  const values = new Map(), secrets = new Map(), calls = []
  let captured, resolveURL
  const url = new Promise(resolve => { resolveURL = resolve })
  const store = { get: (key, fallback) => values.has(key) ? values.get(key) : fallback, set: (key, value) => values.set(key, value), delete: key => values.delete(key) }
  const service = createChatGPTService({ store, getSecret: key => secrets.get(key), setSecret: (key, value) => secrets.set(key, value),
    openExternal: value => { captured = new URL(value); resolveURL(captured) },
    verifyIdentity: async () => ({ sub: 'commander', email: 'commander@example.test', name: 'Commander' }),
    fetchImpl: async (value, options = {}) => {
      const request = { url: String(value), ...options }; calls.push(request)
      const custom = await overrides.fetch?.(request)
      if (custom) return custom
      if (request.url.endsWith('/oauth/token')) return Response.json({ access_token: 'access-secret', refresh_token: 'refresh-secret', id_token: 'identity-secret',
        token_type: 'Bearer', expires_in: 3600, scope: 'openid chatgpt.tokens.use.direct' })
      if (request.url.endsWith('/models')) return Response.json({ models: [
        { slug: 'hidden', visibility: 'hide' }, { slug: 'too-small', visibility: 'list', context_window: 8192 },
        { slug: 'strategist', display_name: 'Strategist', visibility: 'list', context_window: 128000 },
      ] })
      if (request.url.endsWith('/responses')) return stream([completed()])
      if (request.url.includes('/.well-known/')) return Response.json({ revocation_endpoint: 'https://auth.openai.com/revoke' })
      if (request.url.endsWith('/revoke')) return new Response(null, { status: 200 })
      throw new Error('Unexpected request')
    }, ...overrides.service,
  })
  async function callback(parameters = {}, target = captured) {
    const address = new URL(target.searchParams.get('redirect_uri'))
    address.search = new URLSearchParams({ state: target.searchParams.get('state'), code: 'code-secret', client_id: 'issued-client', ...parameters })
    return fetch(address)
  }
  const signIn = async () => {
    const attempt = service.signIn()
    attempt.catch(() => {})
    await url; await callback(); await attempt
  }
  return { service, store, values, secrets, calls, url, callback, signIn, account: () => JSON.parse(secrets.get('secrets.chatgpt-accounts'))['issued-client'] }
}

test('loopback OAuth binds PKCE, state, host and registration; no secrets leave main', async () => {
  const h = harness()
  try {
    const attempt = h.service.signIn()
    const url = await h.url
    assert.equal(url.origin, 'https://auth.openai.com')
    assert.equal(url.searchParams.get('client_id'), 'dynamic_agent_client')
    assert.equal(url.searchParams.get('agent_name_hint'), 'Stellaris Companion')
    assert.match(url.searchParams.get('ext_agent_host_id'), /^urn:uuid:/)
    assert.equal(new URL(url.searchParams.get('redirect_uri')).hostname, '127.0.0.1')
    assert.equal((await h.callback({ state: 'wrong-state' })).status, 400)
    assert.equal((await h.callback({ state: 'é'.repeat(43) })).status, 400)
    assert.equal(h.calls.length, 0)
    await h.callback(); await attempt
    const exchange = h.calls.find(call => call.url.endsWith('/oauth/token')).body
    assert.equal(exchange.get('client_id'), 'issued-client')
    assert.equal(exchange.get('redirect_uri'), url.searchParams.get('redirect_uri'))
    assert.equal(crypto.createHash('sha256').update(exchange.get('code_verifier')).digest('base64url'), url.searchParams.get('code_challenge'))
    assert.equal(h.service.status().ready, true)
    assert.equal(h.service.status().model, 'strategist')
    assert.equal(h.service.status().models.length, 1)
    assert.doesNotMatch(JSON.stringify(h.service.status()), /access-secret|refresh-secret|identity-secret|code-secret/)
    const body = JSON.parse(h.calls.find(call => call.url.endsWith('/responses')).body)
    assert.equal(body.store, false); assert.equal(body.stream, true)
    assert.deepEqual(body.input, [{ role: 'user', content: 'Return exactly {"ready":true}.' }])
    assert.equal(body.temperature, undefined); assert.equal(body.max_output_tokens, undefined)
    h.service.acknowledgeWelcome(); assert.equal(h.service.status().welcomePending, false)
    await h.service.disconnect()
    assert.equal(h.service.status().connected, false)
    assert.equal(h.account().clientId, 'issued-client')
    assert.equal(h.account().refreshToken, '')
    assert.equal(h.store.get('chatgpt.hostId'), url.searchParams.get('ext_agent_host_id'))
  } finally { h.service.close() }
})

test('cancel closes the callback and keeps an existing account selected', async () => {
  const h = harness()
  const attempt = h.service.signIn()
  await h.url; h.service.cancel()
  await assert.rejects(attempt, { code: 'CHATGPT_CANCELLED' })
  assert.equal(h.service.status().connected, false)
  h.service.close()
})

test('first-use defaults to tested Terra while catalog order and saved choices are preserved', async () => {
  const models = ['gpt-6-astra', 'gpt-5.6-sol', 'gpt-5.6-terra', 'gpt-5.6-luna', 'gpt-6.1-sol']
  const h = harness({ fetch: request => request.url.endsWith('/models') ? Response.json({
    models: models.map(slug => ({ slug, display_name: slug, visibility: 'list', context_window: 272000 })),
  }) : null })
  try {
    await h.signIn()
    assert.equal(h.service.status().model, 'gpt-5.6-terra')
    assert.equal(h.service.status().recommendedModel, 'gpt-5.6-terra')
    assert.deepEqual(h.service.status().models.map(model => model.id), models)
    for (const selected of ['gpt-5.6-luna', 'gpt-6-astra']) {
      await h.service.selectModel(selected); await h.service.listModels()
      assert.equal(h.service.status().model, selected)
    }
    await assert.rejects(h.service.selectModel('not-in-account'), { code: 'CHATGPT_MODEL' })
    assert.equal(h.service.status().model, 'gpt-6-astra')
  } finally { h.service.close() }
})

test('purpose selects tested reasoning effort and schema fallback preserves it', async () => {
  let failSchema = false
  const h = harness({ fetch: request => {
    if (request.url.endsWith('/models')) return Response.json({ models: [
      { slug: 'gpt-5.6-terra', visibility: 'list', context_window: 272000 },
    ] })
    if (failSchema && request.url.endsWith('/responses') && JSON.parse(request.body).text) {
      return Response.json({ error: { param: 'text.format' } }, { status: 400 })
    }
  } })
  try {
    await h.signIn()
    await h.service.generate({ instructions: 'Advisor', input: 'Ask' })
    assert.equal(JSON.parse(h.calls.at(-1).body).reasoning.effort, 'low')
    failSchema = true
    const answer = await h.service.generate({ instructions: 'Chronicle', input: 'Events', purpose: 'chronicle', schema: { type: 'object' } })
    assert.equal(answer.schemaFallbackUsed, true)
    assert.equal(JSON.parse(h.calls.at(-1).body).reasoning.effort, 'medium')
    assert.equal(JSON.parse(h.calls.at(-1).body).model, 'gpt-5.6-terra')
  } finally { h.service.close() }
})

test('model changes apply to the next request without cancelling an in-flight reply', async () => {
  let hold = false, release, signalStarted
  const started = new Promise(resolve => { signalStarted = resolve })
  const h = harness({ fetch: async request => {
    if (request.url.endsWith('/models')) return Response.json({ models: ['gpt-5.6-terra', 'gpt-5.6-luna']
      .map(slug => ({ slug, visibility: 'list', context_window: 272000 })) })
    if (request.url.endsWith('/responses')) {
      const body = JSON.parse(request.body)
      if (hold) { signalStarted(); await new Promise(resolve => { release = resolve }) }
      return stream([{ type: 'response.completed', response: { status: 'completed', model: body.model,
        output: [{ content: [{ type: 'output_text', text: 'Victory' }] }] } }])
    }
  } })
  try {
    // Seed an existing verified account to focus this test on model switching.
    h.secrets.set('secrets.chatgpt-accounts', JSON.stringify({ existing: {
      id: 'existing', clientId: 'existing', accessToken: 'access-secret', refreshToken: 'refresh-secret',
      expiresAt: Date.now() + 3600000, scopes: ['chatgpt.tokens.use.direct'], verified: true, model: 'gpt-5.6-terra',
    } }))
    h.store.set('chatgpt.activeId', 'existing'); await h.service.listModels()
    hold = true
    const pending = h.service.generate({ instructions: 'Advisor', input: 'First question' })
    await started
    await h.service.selectModel('gpt-5.6-luna')
    hold = false; release()
    assert.equal((await pending).model, 'gpt-5.6-terra')
    assert.equal((await h.service.generate({ instructions: 'Advisor', input: 'Next question' })).model, 'gpt-5.6-luna')
    assert.equal(h.service.status().model, 'gpt-5.6-luna')
  } finally { h.service.close() }
})

test('refresh is serialized and rotating token pairs are stored together', async () => {
  let refreshCount = 0
  const h = harness({ fetch: async request => {
    if (request.body?.get?.('grant_type') !== 'refresh_token') return
    refreshCount++
    await new Promise(resolve => setTimeout(resolve, 10))
    return Response.json({ access_token: 'rotated-access', refresh_token: 'rotated-refresh', token_type: 'Bearer', expires_in: 3600 })
  } })
  try {
    await h.signIn()
    h.secrets.set('secrets.chatgpt-accounts', JSON.stringify({ 'issued-client': { ...h.account(), expiresAt: 0 } }))
    await Promise.all([h.service.listModels(), h.service.listModels(), h.service.listModels()])
    assert.equal(refreshCount, 1)
    assert.equal(h.account().accessToken, 'rotated-access'); assert.equal(h.account().refreshToken, 'rotated-refresh')
    assert.deepEqual(h.account().scopes, ['openid', 'chatgpt.tokens.use.direct'])
  } finally { h.service.close() }
})

test('terminal refresh errors require reconnect; temporary failures retain credentials', async () => {
  for (const terminal of [false, true]) {
    const h = harness({ fetch: request => request.body?.get?.('grant_type') === 'refresh_token'
      ? Response.json({ error: terminal ? 'invalid_grant' : 'server_error' }, { status: terminal ? 400 : 503 }) : null })
    try {
      await h.signIn()
      h.secrets.set('secrets.chatgpt-accounts', JSON.stringify({ 'issued-client': { ...h.account(), expiresAt: 0 } }))
      await assert.rejects(h.service.listModels(), { code: terminal ? 'CHATGPT_RECONNECT' : 'CHATGPT_UNAVAILABLE' })
      assert.equal(h.service.status().connected, !terminal)
    } finally { h.service.close() }
  }
})

test('schema fallback is bounded and only occurs for an explicit incompatible parameter', async () => {
  let fail = false
  const h = harness({ fetch: request => {
    if (!fail || !request.url.endsWith('/responses')) return
    const body = JSON.parse(request.body)
    if (body.text) return Response.json({ error: { code: 'unsupported_capability', param: 'text.format' } }, { status: 400 })
  } })
  try {
    await h.signIn(); fail = true
    const result = await h.service.generate({ instructions: 'Return JSON', input: 'schema in prompt', schema: { type: 'object' } })
    assert.equal(result.schemaFallbackUsed, true)
    await assert.rejects(h.service.generate({ instructions: 'Return JSON', input: 'schema in prompt', schema: {}, allowSchemaFallback: false }), { code: 'CHATGPT_UNAVAILABLE' })
  } finally { h.service.close() }
})

test('SSE requires completed output and preserves Unicode across chunk boundaries', async () => {
  const result = await readResponseStream(stream([{ type: 'response.output_text.delta', delta: 'Victory 🚀' }, completed('ignored')], 1))
  assert.equal(result.text, 'Victory 🚀')
  for (const events of [
    [{ type: 'response.output_text.delta', delta: 'partial' }],
    [{ type: 'response.output_text.delta', delta: 'partial' }, { type: 'response.incomplete' }],
    [{ type: 'response.output_text.delta', delta: 'partial' }, { type: 'response.failed', response: { error: { code: 'subscription_sharing_usage_limit_exceeded' } } }],
    [completed(), { type: 'error', error: { code: 'subscription_sharing_usage_limit_exceeded' } }],
  ]) await assert.rejects(readResponseStream(stream(events)))
})

test('identity tokens enforce signature, issuer, audience, expiry and nonce', async () => {
  const { generateKeyPair, SignJWT } = await import('jose')
  const { publicKey, privateKey } = await generateKeyPair('RS256')
  const sign = (patch = {}, options = {}) => new SignJWT({ sub: 'commander', nonce: 'expected', ...patch })
    .setProtectedHeader({ alg: 'RS256' }).setIssuer(options.issuer || 'https://auth.openai.com').setAudience('issued-client')
    .setIssuedAt().setExpirationTime(options.expiry || '5m').sign(privateKey)
  const token = await sign()
  assert.equal((await verifyIdentityToken(token, 'issued-client', 'expected', publicKey)).sub, 'commander')
  await assert.rejects(verifyIdentityToken(await sign({}, { issuer: 'https://example.test' }), 'issued-client', 'expected', publicKey))
  await assert.rejects(verifyIdentityToken(await sign({}, { expiry: Math.floor(Date.now() / 1000) - 60 }), 'issued-client', 'expected', publicKey))
  await assert.rejects(verifyIdentityToken(token, 'wrong-client', 'expected', publicKey))
  await assert.rejects(verifyIdentityToken(token, 'issued-client', 'wrong-nonce', publicKey))
  const other = await generateKeyPair('RS256')
  await assert.rejects(verifyIdentityToken(token, 'issued-client', 'expected', other.publicKey))
  await assert.rejects(verifyIdentityToken(await sign({ nonce: '' }), 'issued-client', 'expected', publicKey))
})

test('local bridge requires a capability, rejects browser origins and returns only completed output', async () => {
  let count = 0
  const bridge = createChatGPTBridge({ generate: async () => { count++; return { text: 'Victory', model: 'strategist' } } })
  await bridge.start()
  const { url, token } = bridge.connection()
  try {
    assert.equal((await fetch(`${url}/generate`, { method: 'POST' })).status, 401)
    assert.equal((await fetch(`${url}/generate`, { method: 'POST', headers: { Authorization: `Bearer ${token}`, Origin: 'https://example.test' } })).status, 401)
    const response = await fetch(`${url}/generate`, { method: 'POST', headers: { Authorization: `Bearer ${token}` },
      body: JSON.stringify({ instructions: 'strategy', input: 'campaign' }) })
    assert.equal(response.status, 200); assert.equal((await response.json()).text, 'Victory'); assert.equal(count, 1)
  } finally { bridge.close() }
})

test('reauthorization reuses the registration and rejects another account subject', async () => {
  let subject = 'commander'
  const authorizationURLs = []
  const h = harness({ service: {
    verifyIdentity: async () => ({ sub: subject, email: 'commander@example.test' }),
    openExternal: value => { authorizationURLs.push(new URL(value)) },
  } })
  try {
    const first = h.service.signIn()
    await new Promise(resolve => setImmediate(resolve))
    const initial = authorizationURLs[0]
    await h.callback({}, initial); await first
    const reauth = h.service.signIn()
    reauth.catch(() => {})
    await new Promise(resolve => setImmediate(resolve))
    const returning = authorizationURLs[1]
    assert.equal(returning.searchParams.get('client_id'), 'issued-client')
    assert.equal(returning.searchParams.get('agent_name_hint'), null)
    assert.equal(returning.searchParams.get('id_token_hint'), 'identity-secret')
    assert.notEqual(returning.searchParams.get('state'), initial.searchParams.get('state'))
    subject = 'another-account'
    await h.callback({}, returning)
    await assert.rejects(reauth, { code: 'CHATGPT_RECONNECT' })
    assert.equal(h.account().subject, 'commander')
    assert.equal(h.service.status().ready, true)
  } finally { h.service.close() }
})

test('authorization without plan permission cannot invoke inference', async () => {
  const h = harness({ fetch: request => request.url.endsWith('/oauth/token') ? Response.json({
    access_token: 'access-secret', refresh_token: 'refresh-secret', id_token: 'identity-secret',
    token_type: 'Bearer', expires_in: 3600, scope: 'openid email',
  }) : null })
  try {
    await assert.rejects(h.signIn(), { code: 'CHATGPT_PERMISSION' })
    assert.equal(h.service.status().ready, false)
    assert.equal(h.calls.filter(call => call.url.endsWith('/responses')).length, 0)
  } finally { h.service.close() }
})

test('Python structured generation traverses the authenticated real local bridge', async t => {
  const path = require('node:path')
  const { execFile } = require('node:child_process')
  const root = path.resolve(__dirname, '../..')
  const candidates = [process.env.STELLARIS_TEST_PYTHON, process.env.PYTHON_BIN, '.venv/bin/python', '.venv/Scripts/python.exe', 'venv/bin/python', 'venv/Scripts/python.exe'].filter(Boolean)
  const python = candidates.map(value => path.resolve(root, value)).find(value => require('node:fs').existsSync(value))
  if (!python) { t.skip('Set STELLARIS_TEST_PYTHON to an environment with the backend dependencies'); return }
  const h = harness()
  const bridge = createChatGPTBridge(h.service)
  try {
    await h.signIn(); await bridge.start()
    const connection = bridge.connection()
    const output = await new Promise((resolve, reject) => execFile(
      python, ['-c', `
from pydantic import BaseModel
from backend.core.advisor_providers import AdvisorProviderConfig, create_advisor_generator
class Ready(BaseModel):
    ready: bool
generator = create_advisor_generator(config=AdvisorProviderConfig.from_environment())
result = generator.generate(system_prompt='Return the requested JSON', user_prompt='Confirm readiness', response_schema=Ready)
assert Ready.model_validate_json(result.text).ready
assert result.provider == 'chatgpt'
print('bridge verified')
`], { cwd: path.resolve(__dirname, '../..'), env: { ...process.env,
      STELLARIS_ADVISOR_PROVIDER: 'chatgpt', STELLARIS_ADVISOR_MODEL: 'strategist',
      STELLARIS_CHATGPT_BRIDGE_URL: connection.url, STELLARIS_CHATGPT_BRIDGE_TOKEN: connection.token,
    } }, (error, stdout) => error ? reject(error) : resolve(stdout)))
    assert.match(output, /bridge verified/)
    const body = JSON.parse(h.calls.filter(call => call.url.endsWith('/responses')).at(-1).body)
    assert.equal(body.text.format.schema.additionalProperties, false)
  } finally { bridge.close(); h.service.close() }
})

test('a failed code exchange retains the issued client ID for the next registration attempt', async () => {
  const authorizationURLs = []
  const h = harness({ service: { openExternal: value => authorizationURLs.push(new URL(value)) },
    fetch: request => request.url.endsWith('/oauth/token') ? Response.json({ error: 'invalid_grant' }, { status: 400 }) : null })
  try {
    const first = h.service.signIn({ newAccount: true }); first.catch(() => {})
    await new Promise(resolve => setImmediate(resolve))
    await h.callback({}, authorizationURLs[0]); await assert.rejects(first, { code: 'CHATGPT_RECONNECT' })
    assert.equal(h.store.get('chatgpt.pendingClientId'), 'issued-client')
    const second = h.service.signIn({ newAccount: true }); second.catch(() => {})
    await new Promise(resolve => setImmediate(resolve))
    assert.equal(authorizationURLs[1].searchParams.get('client_id'), 'issued-client')
    h.service.cancel(); await assert.rejects(second, { code: 'CHATGPT_CANCELLED' })
  } finally { h.service.close() }
})

test('explicit retry after declining plan permissions requests fresh consent', async () => {
  const authorizationURLs = []
  const h = harness({ service: { openExternal: value => authorizationURLs.push(new URL(value)) },
    fetch: request => request.url.endsWith('/oauth/token') ? Response.json({ access_token: 'access-secret',
      refresh_token: 'refresh-secret', id_token: 'identity-secret', token_type: 'Bearer', expires_in: 3600, scope: 'openid email' }) : null })
  try {
    const first = h.service.signIn(); first.catch(() => {})
    await new Promise(resolve => setImmediate(resolve))
    assert.equal(authorizationURLs[0].searchParams.get('prompt'), null)
    await h.callback({}, authorizationURLs[0]); await assert.rejects(first, { code: 'CHATGPT_PERMISSION' })
    const second = h.service.signIn(); second.catch(() => {})
    await new Promise(resolve => setImmediate(resolve))
    assert.equal(authorizationURLs[1].searchParams.get('client_id'), 'issued-client')
    assert.equal(authorizationURLs[1].searchParams.get('prompt'), 'consent')
    assert.equal(authorizationURLs[1].searchParams.get('force_reconsent'), null)
    h.service.cancel(); await assert.rejects(second, { code: 'CHATGPT_CANCELLED' })
  } finally { h.service.close() }
})

test('reopening sign-in uses the same pending URL internally and exposes no authorization details', async () => {
  const opened = []
  const h = harness({ service: { openExternal: url => opened.push(url) } })
  try {
    await assert.rejects(h.service.reopen(), { code: 'CHATGPT_CANCELLED' })
    const attempt = h.service.signIn(); attempt.catch(() => {})
    await new Promise(resolve => setImmediate(resolve))
    const status = await h.service.reopen()
    assert.equal(opened.length, 2)
    assert.equal(opened[0], opened[1])
    assert.equal(status.connecting, true)
    assert.doesNotMatch(JSON.stringify(status), /authorize|code_challenge|nonce|state/)
    h.service.cancel()
    await assert.rejects(attempt, { code: 'CHATGPT_CANCELLED' })
    await assert.rejects(h.service.reopen(), { code: 'CHATGPT_CANCELLED' })
  } finally { h.service.close() }
})

test('cancelling during model discovery prevents verification and any later inference request', async () => {
  let release, started
  const waiting = new Promise(resolve => { started = resolve })
  let hold = false
  const h = harness({ fetch: async request => {
    if (hold && request.url.endsWith('/models')) {
      started()
      return new Promise(resolve => { release = () => resolve(Response.json({ models: [{ slug: 'strategist', visibility: 'list', context_window: 128000 }] })) })
    }
  } })
  try {
    await h.signIn(); hold = true
    const before = h.calls.filter(call => call.url.endsWith('/responses')).length
    const attempt = h.service.check(); attempt.catch(() => {})
    await waiting; h.service.cancel(); release()
    await assert.rejects(attempt, { code: 'CHATGPT_CANCELLED' })
    assert.equal(h.calls.filter(call => call.url.endsWith('/responses')).length, before)
  } finally { h.service.close() }
})
