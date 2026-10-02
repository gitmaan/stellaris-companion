// ChatGPT plan usage for the open-source desktop app. Credentials stay here.
const crypto = require('node:crypto')
const http = require('node:http')

const AUTH_ORIGIN = 'https://auth.openai.com'
const RESOURCE = 'https://api.openai.com/v1'
const SCOPES = 'openid profile email offline_access resource.invoke chatgpt.tokens.use.direct'
const SECRET_KEY = 'secrets.chatgpt-accounts'
// Prefer balanced models for new accounts while preserving saved selections.
const TESTED_MODEL_PREFERENCE = ['gpt-5.6-terra', 'gpt-5.6-luna', 'gpt-5.6-sol']
const preferredModel = models => TESTED_MODEL_PREFERENCE.map(id => models.find(model => model.id === id)).find(Boolean) || models[0]
const MESSAGES = {
  CHATGPT_CANCELLED: 'Sign-in cancelled. You can try again whenever you’re ready.',
  CHATGPT_RECONNECT: 'Reconnect your ChatGPT account to continue.',
  CHATGPT_PERMISSION: 'Allow ChatGPT plan usage when connecting your account.',
  CHATGPT_INELIGIBLE: 'This account cannot use its ChatGPT plan here. Try another account or provider.',
  CHATGPT_LIMIT: 'Your ChatGPT plan or app usage limit has been reached. Open Manage usage to review it.',
  CHATGPT_UNAVAILABLE: 'ChatGPT is temporarily unavailable. Your connection is saved; try again shortly.',
  CHATGPT_INVALID_RESPONSE: 'ChatGPT did not finish the response. Please try again.',
  CHATGPT_MODEL: 'The selected model is unavailable for this account. Choose another model in Settings.',
  PROVIDER_CONTEXT_LIMIT: 'This campaign is too large for the selected model. Choose another model in Settings.',
}

class ChatGPTError extends Error {
  constructor(code, status = 502) {
    super(MESSAGES[code] || 'Could not connect to ChatGPT. Please try again.')
    this.code = code
    this.status = status
  }
}

function apiError(status, error = {}) {
  const code = error.code || ''
  if (code === 'subscription_sharing_usage_limit_exceeded') return new ChatGPTError('CHATGPT_LIMIT', 429)
  if (code === 'subscription_sharing_user_not_eligible' || status === 403) return new ChatGPTError('CHATGPT_INELIGIBLE', 403)
  if (code === 'context_length_exceeded') return new ChatGPTError('PROVIDER_CONTEXT_LIMIT', 400)
  if (status === 401) return new ChatGPTError('CHATGPT_RECONNECT', 401)
  if (code === 'model_not_found' || status === 404) return new ChatGPTError('CHATGPT_MODEL', 400)
  return new ChatGPTError('CHATGPT_UNAVAILABLE', status === 429 ? 429 : 503)
}

let remoteKeys
async function verifyIdentityToken(token, clientId, nonce, keys) {
  const { jwtVerify, createRemoteJWKSet } = await import('jose')
  remoteKeys ||= createRemoteJWKSet(new URL(`${AUTH_ORIGIN}/.well-known/jwks.json`))
  const { payload } = await jwtVerify(token, keys || remoteKeys, {
    issuer: AUTH_ORIGIN, audience: clientId, algorithms: ['RS256', 'ES256'],
    requiredClaims: ['sub', 'exp', 'iat', 'nonce'], clockTolerance: 5,
  })
  if (payload.nonce !== nonce || typeof payload.sub !== 'string' || !payload.sub
      || (payload.azp && payload.azp !== clientId)
      || (Array.isArray(payload.aud) && payload.aud.length > 1 && payload.azp !== clientId)) {
    throw new ChatGPTError('CHATGPT_RECONNECT', 401)
  }
  return payload
}

// Accept SSE frames across arbitrary network chunk boundaries. Never accept a
// partial stream as completed output, including an error after text deltas.
async function readResponseStream(response) {
  if (!response.body) throw new ChatGPTError('CHATGPT_INVALID_RESPONSE')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = '', text = '', completed = false, model = ''
  function frame(raw) {
    const data = raw.split('\n').filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n')
    if (!data || data === '[DONE]') return
    const event = JSON.parse(data)
    if (event.type === 'response.output_text.delta') text += event.delta || ''
    if (event.type === 'error' || event.type === 'response.failed') throw apiError(502, event.error || event.response?.error)
    if (event.type === 'response.incomplete') throw new ChatGPTError('CHATGPT_INVALID_RESPONSE')
    if (event.type === 'response.completed') {
      if (event.response?.status && event.response.status !== 'completed') throw new ChatGPTError('CHATGPT_INVALID_RESPONSE')
      completed = true
      model = event.response?.model || ''
      if (!text) text = (event.response?.output || []).flatMap(item => item.content || [])
        .filter(item => item.type === 'output_text').map(item => item.text || '').join('')
    }
    if (text.length > 1_000_000) throw new ChatGPTError('CHATGPT_INVALID_RESPONSE')
  }
  try {
    while (true) {
      const { value, done } = await reader.read()
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true })
      buffer = buffer.replace(/\r\n/g, '\n')
      let end
      while ((end = buffer.indexOf('\n\n')) >= 0) {
        frame(buffer.slice(0, end))
        buffer = buffer.slice(end + 2)
      }
      if (buffer.length > 2_000_000) throw new ChatGPTError('CHATGPT_INVALID_RESPONSE')
      if (done) break
    }
    if (buffer.trim()) frame(buffer)
    if (!completed || !text.trim()) throw new ChatGPTError('CHATGPT_INVALID_RESPONSE')
    return { text: text.trim(), model }
  } finally {
    await reader.cancel().catch(() => {})
    reader.releaseLock()
  }
}

function createChatGPTService({ store, getSecret, setSecret, openExternal,
  fetchImpl = globalThis.fetch, verifyIdentity = verifyIdentityToken, onChange = () => {} }) {
  let pending = null
  let epoch = 0
  const refreshes = new Map(), requests = new Set(), catalogs = new Map()
  let hostId = store.get('chatgpt.hostId')
  if (!hostId) { hostId = `urn:uuid:${crypto.randomUUID()}`; store.set('chatgpt.hostId', hostId) }
  const accounts = () => {
    try { return JSON.parse(getSecret(SECRET_KEY) || '{}') } catch { return {} }
  }
  const saveAccount = account => {
    const all = accounts(); all[account.id] = account; setSecret(SECRET_KEY, JSON.stringify(all))
  }
  const active = () => accounts()[store.get('chatgpt.activeId')] || null
  const summary = account => ({ id: account.id, email: account.email || '', name: account.name || '', model: account.model || '', modelName: account.modelName || '' })
  function status() {
    const account = active()
    return {
      connected: !!account?.accessToken, ready: !!account?.accessToken && account.scopes?.includes('chatgpt.tokens.use.direct') && !!account.model && !!account.verified,
      account: account ? summary(account) : null,
      accounts: Object.values(accounts()).map(summary),
      model: account?.model || '', models: catalogs.get(account?.id) || [],
      recommendedModel: preferredModel(catalogs.get(account?.id) || [])?.id || '',
      connecting: !!pending, welcomePending: !!account?.accessToken && !store.get('chatgpt.welcomeSeen', false),
    }
  }
  function abortRequests() { epoch++; for (const controller of requests) controller.abort(); requests.clear() }
  async function fetchSafe(url, options = {}, timeout = 20_000) {
    return fetchImpl(url, { ...options, redirect: 'error', signal: options.signal
      ? AbortSignal.any([options.signal, AbortSignal.timeout(timeout)]) : AbortSignal.timeout(timeout) })
  }
  async function tokenRequest(body, signal) {
    const response = await fetchSafe(`${AUTH_ORIGIN}/api/accounts/oauth/token`, {
      method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body, signal,
    })
    const data = await response.json()
    if (!response.ok) {
      const terminal = ['invalid_grant', 'invalid_refresh_token', 'refresh_token_expired', 'refresh_token_reused', 'refresh_token_invalidated'].includes(data.error?.code || data.error)
      throw new ChatGPTError(terminal ? 'CHATGPT_RECONNECT' : 'CHATGPT_UNAVAILABLE', terminal ? 401 : 503)
    }
    if (typeof data.access_token !== 'string' || typeof data.refresh_token !== 'string'
        || data.token_type?.toLowerCase() !== 'bearer' || !Number.isFinite(data.expires_in) || data.expires_in <= 0) {
      throw new ChatGPTError('CHATGPT_RECONNECT', 401)
    }
    return data
  }
  function withTokens(account, tokens) {
    return { ...account, accessToken: tokens.access_token, refreshToken: tokens.refresh_token,
      idToken: tokens.id_token || account.idToken, expiresAt: Date.now() + tokens.expires_in * 1000,
      scopes: typeof tokens.scope === 'string' ? tokens.scope.split(/\s+/) : account.scopes || [] }
  }
  async function credential(account) {
    if (!account?.accessToken) throw new ChatGPTError('CHATGPT_RECONNECT', 401)
    if (!account.scopes?.includes('chatgpt.tokens.use.direct')) throw new ChatGPTError('CHATGPT_PERMISSION', 403)
    if (account.expiresAt > Date.now() + 60_000) return account
    if (!refreshes.has(account.id)) {
      refreshes.set(account.id, (async () => {
        try {
          const tokens = await tokenRequest(new URLSearchParams({ grant_type: 'refresh_token',
            client_id: account.clientId, refresh_token: account.refreshToken, resource: RESOURCE }))
          const latest = accounts()[account.id]
          if (!latest?.accessToken || latest.refreshToken !== account.refreshToken) throw new ChatGPTError('CHATGPT_RECONNECT', 401)
          const updated = withTokens(latest, tokens); saveAccount(updated); return updated
        } catch (error) {
          if (error.code === 'CHATGPT_RECONNECT') {
            const latest = accounts()[account.id]
            if (latest?.refreshToken === account.refreshToken) saveAccount({ ...latest, accessToken: '', refreshToken: '', idToken: '' })
            onChange(status())
          }
          throw error
        } finally { refreshes.delete(account.id) }
      })())
    }
    return refreshes.get(account.id)
  }
  async function authorizedFetch(account, url, options = {}, timeout) {
    const generation = epoch
    const send = credentials => fetchSafe(url, { ...options,
      headers: { ...options.headers, Authorization: `Bearer ${credentials.accessToken}` } }, timeout)
    let response = await send(account)
    // A token can expire or be rotated before its locally stored expiry.
    if (response.status === 401 && generation === epoch) {
      account = await credential({ ...account, expiresAt: 0 })
      if (generation !== epoch) throw new ChatGPTError('CHATGPT_CANCELLED', 409)
      response = await send(account)
    }
    return response
  }
  async function listModels() {
    const generation = epoch
    const account = await credential(active())
    const response = await authorizedFetch(account, `${RESOURCE}/models`)
    if (!response.ok) throw apiError(response.status, (await response.json().catch(() => ({}))).error)
    const data = await response.json()
    if (generation !== epoch) throw new ChatGPTError('CHATGPT_CANCELLED', 409)
    const models = (data.models || []).filter(item => item.visibility === 'list' && typeof item.slug === 'string')
      .map(item => ({ id: item.slug, name: item.display_name || item.slug, contextLength: item.context_window || item.context_length || undefined }))
      .filter(item => !item.contextLength || item.contextLength >= 32768)
    if (!models.length) throw new ChatGPTError('CHATGPT_MODEL', 400)
    catalogs.set(account.id, models)
    const current = accounts()[account.id]
    const selected = models.find(item => item.id === current?.model) || preferredModel(models)
    saveAccount({ ...current, model: selected.id, modelName: selected.name })
    return models
  }
  async function generate({ model, instructions, input, purpose = 'advisor', schema, schemaName = 'chronicle', allowSchemaFallback = true }) {
    const generation = epoch
    const account = await credential(active())
    const models = catalogs.get(account.id) || await listModels()
    model ||= active()?.model
    if (!models.some(item => item.id === model)) throw new ChatGPTError('CHATGPT_MODEL', 400)
    if (generation !== epoch) throw new ChatGPTError('CHATGPT_CANCELLED', 409)
    const controller = new AbortController(); requests.add(controller)
    const body = { model, instructions, input: [{ role: 'user', content: input }], store: false, stream: true }
    if (TESTED_MODEL_PREFERENCE.includes(model)) body.reasoning = { effort: purpose === 'chronicle' ? 'medium' : 'low' }
    if (schema) body.text = { format: { type: 'json_schema', name: schemaName, strict: true, schema } }
    try {
      const response = await authorizedFetch(account, `${RESOURCE}/responses`, { method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify(body), signal: controller.signal,
      }, 180_000)
      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        // Prompt-based JSON fallback only for an explicit schema incompatibility.
        if (schema && allowSchemaFallback && response.status === 400 && /text|schema|format/.test(data.error?.param || '')) {
          const result = await generate({ model, instructions, input, purpose })
          return { ...result, schemaFallbackUsed: true }
        }
        throw apiError(response.status, data.error)
      }
      const result = await readResponseStream(response)
      if (generation !== epoch) throw new ChatGPTError('CHATGPT_CANCELLED', 409)
      return { ...result, model: result.model || model, schemaFallbackUsed: false }
    } catch (error) {
      if (error instanceof ChatGPTError) throw error
      throw new ChatGPTError(controller.signal.aborted ? 'CHATGPT_CANCELLED' : 'CHATGPT_UNAVAILABLE', 503)
    } finally { requests.delete(controller) }
  }
  async function check() {
    const generation = epoch
    await listModels()
    if (generation !== epoch) throw new ChatGPTError('CHATGPT_CANCELLED', 409)
    const result = await generate({ input: 'Return exactly {"ready":true}.', instructions: 'Verify this connection. Return the requested JSON object.',
      schemaName: 'connection_check', schema: { type: 'object', properties: { ready: { type: 'boolean' } }, required: ['ready'], additionalProperties: false } })
    try {
      if (JSON.parse(result.text).ready !== true) throw new Error('Invalid check')
    } catch { throw new ChatGPTError('CHATGPT_INVALID_RESPONSE') }
    if (generation !== epoch) throw new ChatGPTError('CHATGPT_CANCELLED', 409)
    saveAccount({ ...active(), verified: true }); onChange(status())
    return status()
  }
  function cancel() {
    abortRequests()
    if (pending) {
      pending.controller.abort(); pending.server.close(); pending.reject(new ChatGPTError('CHATGPT_CANCELLED', 409))
      pending = null; onChange(status())
    }
  }
  async function reopen() {
    if (!pending?.authorizeUrl) throw new ChatGPTError('CHATGPT_CANCELLED', 409)
    await openExternal(pending.authorizeUrl)
    return status()
  }
  async function signIn({ profileId, newAccount = false } = {}) {
    cancel()
    const previous = profileId ? accounts()[profileId] : !newAccount ? active() : null
    if (profileId && !previous) throw new ChatGPTError('CHATGPT_RECONNECT', 401)
    const clientId = previous?.clientId || store.get('chatgpt.pendingClientId') || 'dynamic_agent_client'
    const state = crypto.randomBytes(32).toString('base64url'), nonce = crypto.randomBytes(32).toString('base64url')
    const verifier = crypto.randomBytes(64).toString('base64url'), controller = new AbortController()
    const result = await new Promise((resolve, reject) => {
      let consumed = false
      const server = http.createServer(async (request, response) => {
        const callback = new URL(request.url, 'http://127.0.0.1')
        response.setHeader('Cache-Control', 'no-store')
        response.setHeader('Content-Type', 'text/html; charset=utf-8')
        response.setHeader('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'")
        if (request.method !== 'GET' || callback.pathname !== '/auth/callback') { response.writeHead(404); response.end(); return }
        const returnedState = callback.searchParams.get('state') || ''
        if (consumed || Buffer.byteLength(returnedState) !== Buffer.byteLength(state) || !crypto.timingSafeEqual(Buffer.from(returnedState), Buffer.from(state))) {
          response.writeHead(400); response.end('Sign-in could not be verified. Return to Stellaris Companion and try again.'); return
        }
        consumed = true
        response.end('<!doctype html><title>Stellaris Companion</title><body style="font:18px system-ui;background:#101820;color:white;padding:48px"><h1>Return to Stellaris Companion</h1><p>You can close this tab. Your app will finish connecting.</p></body>')
        server.close()
        try {
          if (callback.searchParams.has('error')) throw new ChatGPTError('CHATGPT_CANCELLED', 409)
          const code = callback.searchParams.get('code'), issued = callback.searchParams.get('client_id') || (clientId !== 'dynamic_agent_client' ? clientId : '')
          if (!code || !issued || issued === 'dynamic_agent_client' || (clientId !== 'dynamic_agent_client' && issued !== clientId)) throw new ChatGPTError('CHATGPT_RECONNECT', 401)
          if (!previous) store.set('chatgpt.pendingClientId', issued)
          const tokens = await tokenRequest(new URLSearchParams({ grant_type: 'authorization_code', code, client_id: issued,
            code_verifier: verifier, redirect_uri: redirectUri, resource: RESOURCE }), controller.signal)
          const identity = await verifyIdentity(tokens.id_token, issued, nonce)
          if (previous && identity.sub !== previous.subject) throw new ChatGPTError('CHATGPT_RECONNECT', 401)
          if (controller.signal.aborted) throw new ChatGPTError('CHATGPT_CANCELLED', 409)
          const account = withTokens({ id: issued, clientId: issued, subject: identity.sub,
            email: identity.email || '', name: identity.name || '', model: previous?.model || '' }, tokens)
          saveAccount(account); store.delete('chatgpt.pendingClientId')
          abortRequests(); store.set('chatgpt.activeId', account.id)
          resolve(account)
        } catch (error) { reject(error instanceof ChatGPTError ? error : new ChatGPTError('CHATGPT_RECONNECT', 401)) }
      })
      let redirectUri
      pending = { server, reject, controller }
      server.listen(0, '127.0.0.1', async () => {
        if (controller.signal.aborted) { server.close(); return }
        redirectUri = `http://127.0.0.1:${server.address().port}/auth/callback`
        const url = new URL(`${AUTH_ORIGIN}/api/accounts/authorize`)
        url.search = new URLSearchParams({ client_id: clientId, ext_agent_host_id: hostId, response_type: 'code', redirect_uri: redirectUri,
          scope: SCOPES, resource: RESOURCE, state, nonce, code_challenge_method: 'S256',
          code_challenge: crypto.createHash('sha256').update(verifier).digest('base64url') }).toString()
        if (clientId === 'dynamic_agent_client') url.searchParams.set('agent_name_hint', 'Stellaris Companion')
        if (previous?.idToken) url.searchParams.set('id_token_hint', previous.idToken)
        if (previous?.accessToken && !previous.scopes?.includes('chatgpt.tokens.use.direct')) url.searchParams.set('prompt', 'consent')
        if (pending?.controller === controller) pending.authorizeUrl = url.href
        onChange(status())
        try { await openExternal(url.href) } catch { cancel() }
      })
      server.on('error', () => reject(new ChatGPTError('CHATGPT_UNAVAILABLE')))
      const timer = setTimeout(() => { controller.abort(); server.close(); reject(new ChatGPTError('CHATGPT_CANCELLED', 409)) }, 5 * 60_000)
      timer.unref()
      controller.signal.addEventListener('abort', () => clearTimeout(timer), { once: true })
      server.on('close', () => clearTimeout(timer))
    }).finally(() => { if (pending?.controller === controller) pending = null; onChange(status()) })
    if (!result.scopes.includes('chatgpt.tokens.use.direct')) throw new ChatGPTError('CHATGPT_PERMISSION', 403)
    return check()
  }
  async function selectAccount(id) {
    if (!accounts()[id]) throw new ChatGPTError('CHATGPT_RECONNECT', 401)
    abortRequests(); store.set('chatgpt.activeId', id); onChange(status())
    if (!active().verified) return check()
    await listModels(); return status()
  }
  async function selectModel(model) {
    const models = await listModels()
    if (!models.some(item => item.id === model)) throw new ChatGPTError('CHATGPT_MODEL', 400)
    // Running requests keep their captured model; the new choice is used on the
    // next request. Account changes/disconnects still cancel for isolation.
    saveAccount({ ...active(), model, modelName: models.find(item => item.id === model).name }); onChange(status()); return status()
  }
  async function disconnect() {
    cancel(); abortRequests()
    const account = active()
    if (!account) return { ...status(), revocationConfirmed: true }
    let revocationConfirmed = false
    try {
      const discovery = await (await fetchSafe(`${AUTH_ORIGIN}/.well-known/openid-configuration`)).json()
      const endpoint = new URL(discovery.revocation_endpoint)
      if (endpoint.origin !== AUTH_ORIGIN) throw new Error('Invalid revocation endpoint')
      const response = await fetchSafe(endpoint.href, { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ token: account.refreshToken, token_type_hint: 'refresh_token', client_id: account.clientId }) })
      revocationConfirmed = response.ok
    } catch { /* Keep a truthful local disconnect even when offline. */ }
    saveAccount({ ...account, accessToken: '', refreshToken: '', idToken: '' }); catalogs.delete(account.id)
    onChange(status()); return { ...status(), revocationConfirmed }
  }
  return { status, signIn, cancel, reopen, listModels, generate, check, selectAccount, selectModel, disconnect,
    acknowledgeWelcome: () => { store.set('chatgpt.welcomeSeen', true); onChange(status()) },
    close: () => { cancel(); abortRequests() } }
}

module.exports = { createChatGPTService, verifyIdentityToken, readResponseStream, ChatGPTError, apiError }
