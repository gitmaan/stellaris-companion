const assert = require('node:assert/strict')
const crypto = require('node:crypto')
const test = require('node:test')
const http = require('node:http')
const { createOpenRouterOAuth } = require('../main/openRouterOAuth')

function pendingAuthorization(options = {}) {
  let opened
  const url = new Promise((resolve) => {
    opened = resolve
  })
  const oauth = createOpenRouterOAuth({ openExternal: opened, timeoutMs: 1000, ...options })
  const result = oauth.connect()
  return { oauth, result, url: url.then((value) => new URL(value)) }
}

test('OpenRouter browser authorization uses PKCE and exposes only a temporary credential ID', async () => {
  let body
  const flow = pendingAuthorization({
    fetchImpl: async (url, options) => {
      assert.equal(url, 'https://openrouter.ai/api/v1/auth/keys')
      assert.equal(options.redirect, 'error')
      body = JSON.parse(options.body)
      return { ok: true, json: async () => ({ key: 'private-test-key' }) }
    },
  })
  try {
    const auth = await flow.url
    assert.equal(auth.origin, 'https://openrouter.ai')
    assert.equal(auth.pathname, '/auth')
    assert.equal(auth.searchParams.get('code_challenge_method'), 'S256')
    const callback = new URL(auth.searchParams.get('callback_url'))
    assert.equal(callback.hostname, '127.0.0.1')
    const wrongPath = new URL('/callback?code=wrong', callback)
    assert.equal((await fetch(wrongPath)).status, 404)
    callback.searchParams.set('code', 'one-time-code')
    const wrongHostStatus = await new Promise((resolve, reject) => {
      const req = http.get(callback, { headers: { Host: 'attacker.example' } }, (res) => {
        res.resume()
        resolve(res.statusCode)
      })
      req.on('error', reject)
    })
    assert.equal(wrongHostStatus, 404)
    const response = await fetch(callback)
    assert.equal(response.status, 200)
    assert.equal(response.headers.get('cache-control'), 'no-store')
    assert.equal((await response.text()).includes('private-test-key'), false)
    assert.equal(body.code, 'one-time-code')
    assert.equal(
      crypto.createHash('sha256').update(body.code_verifier).digest('base64url'),
      auth.searchParams.get('code_challenge')
    )
    const result = await flow.result
    assert.deepEqual(Object.keys(result).sort(), ['credentialId', 'ok'])
    assert.equal(flow.oauth.getKey(result.credentialId), 'private-test-key')
    assert.throws(() => flow.oauth.getKey('other-id'), /expired/)
    flow.oauth.discard(result.credentialId)
    assert.throws(() => flow.oauth.getKey(result.credentialId), /expired/)
  } finally {
    flow.oauth.cancel()
  }
})

test('cancelling an exchange prevents late credentials from becoming usable', async () => {
  let finishExchange
  let started
  const exchanging = new Promise((resolve) => {
    started = resolve
  })
  const flow = pendingAuthorization({
    fetchImpl: async () => {
      started()
      return new Promise((resolve) => {
        finishExchange = () => resolve({ ok: true, json: async () => ({ key: 'late-secret' }) })
      })
    },
  })
  const callback = new URL((await flow.url).searchParams.get('callback_url'))
  callback.searchParams.set('code', 'code')
  const request = fetch(callback)
  await exchanging
  const duplicate = await fetch(callback)
  assert.equal(duplicate.status, 409)
  flow.oauth.cancel()
  assert.deepEqual(await flow.result, { ok: false, errorCode: 'CONNECTION_CANCELLED' })
  finishExchange()
  assert.equal((await request).status, 409)
  assert.throws(() => flow.oauth.getKey(''), /expired/)
})

test('browser failure, exchange rejection, and timeout return safe errors', async () => {
  const browser = createOpenRouterOAuth({
    openExternal: async () => {
      throw new Error('private browser details')
    },
  })
  assert.deepEqual(await browser.connect(), { ok: false, errorCode: 'CONNECTION_FAILED' })
  const timed = pendingAuthorization({ timeoutMs: 30 })
  await timed.url
  assert.deepEqual(await timed.result, { ok: false, errorCode: 'CONNECTION_TIMEOUT' })
  const rejected = pendingAuthorization({
    fetchImpl: async () => ({ ok: false, json: async () => ({ error: 'secret details' }) }),
  })
  const callback = new URL((await rejected.url).searchParams.get('callback_url'))
  callback.searchParams.set('code', 'code')
  const response = await fetch(callback)
  assert.equal(response.status, 502)
  assert.equal((await response.text()).includes('secret details'), false)
  assert.deepEqual(await rejected.result, { ok: false, errorCode: 'CONNECTION_FAILED' })
})
