const crypto = require('node:crypto')
const http = require('node:http')

function createOpenRouterOAuth({
  openExternal,
  fetchImpl = globalThis.fetch,
  timeoutMs = 180_000,
}) {
  let active = null
  let credential = null

  function cancel() {
    credential = null
    active?.finish({ ok: false, errorCode: 'CONNECTION_CANCELLED' })
  }

  function getKey(id) {
    if (!id || credential?.id !== id || credential.expiresAt < Date.now()) {
      throw new Error('OpenRouter authorization expired. Connect again.')
    }
    return credential.key
  }

  function discard(id) {
    if (credential?.id === id) credential = null
  }

  async function connect() {
    cancel()
    const verifier = crypto.randomBytes(32).toString('base64url')
    const challenge = crypto.createHash('sha256').update(verifier).digest('base64url')
    const callbackPath = `/callback/${crypto.randomBytes(24).toString('hex')}`
    const controller = new AbortController()
    return new Promise((resolve) => {
      let finished = false
      let exchanging = false
      let timer
      const finish = (result) => {
        if (finished) return
        finished = true
        clearTimeout(timer)
        controller.abort()
        server.close()
        server.closeIdleConnections?.()
        if (active?.finish === finish) active = null
        resolve(result)
      }
      const reply = (res, status, message) => {
        res.writeHead(status, {
          'Content-Type': 'text/plain; charset=utf-8',
          'Cache-Control': 'no-store',
          'Content-Security-Policy': "default-src 'none'; frame-ancestors 'none'",
          'X-Content-Type-Options': 'nosniff',
          Connection: 'close',
        })
        res.end(message)
      }
      const server = http.createServer(async (req, res) => {
        const address = server.address()
        const expectedHost = `127.0.0.1:${address?.port}`
        let url
        try {
          url = new URL(req.url, `http://${expectedHost}`)
        } catch {
          reply(res, 400, 'Invalid request.')
          return
        }
        if (
          req.method !== 'GET' ||
          req.headers.host !== expectedHost ||
          url.pathname !== callbackPath
        ) {
          reply(res, 404, 'Not found.')
          return
        }
        if (finished || exchanging) {
          reply(res, 409, 'This connection request has already been handled.')
          return
        }
        if (url.searchParams.has('error')) {
          reply(res, 200, 'Connection cancelled. Return to Stellaris Companion.')
          finish({ ok: false, errorCode: 'CONNECTION_CANCELLED' })
          return
        }
        const code = url.searchParams.get('code')
        if (!code || code.length > 4096) {
          reply(
            res,
            400,
            'Missing authorization code. Return to Stellaris Companion and connect again.'
          )
          return
        }
        exchanging = true
        try {
          const response = await fetchImpl('https://openrouter.ai/api/v1/auth/keys', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code, code_verifier: verifier, code_challenge_method: 'S256' }),
            signal: controller.signal,
            redirect: 'error',
          })
          const payload = await response.json()
          if (!response.ok || typeof payload?.key !== 'string' || !payload.key.trim()) {
            throw new Error('Authorization exchange failed')
          }
          if (finished) {
            reply(res, 409, 'This connection request has expired.')
            return
          }
          const id = crypto.randomBytes(24).toString('hex')
          // Keep the key in the main process until the user verifies and saves setup.
          credential = { id, key: payload.key, expiresAt: Date.now() + 15 * 60_000 }
          reply(
            res,
            200,
            'OpenRouter connected. Return to Stellaris Companion to choose a model and save setup.'
          )
          finish({ ok: true, credentialId: id })
        } catch {
          reply(
            res,
            502,
            'Could not connect OpenRouter. Return to Stellaris Companion and try again.'
          )
          finish({ ok: false, errorCode: 'CONNECTION_FAILED' })
        }
      })
      server.requestTimeout = 10_000
      server.headersTimeout = 10_000
      server.maxConnections = 8
      active = { finish }
      timer = setTimeout(() => finish({ ok: false, errorCode: 'CONNECTION_TIMEOUT' }), timeoutMs)
      server.on('error', () => finish({ ok: false, errorCode: 'CONNECTION_FAILED' }))
      server.listen(0, '127.0.0.1', async () => {
        if (finished) {
          server.close()
          return
        }
        const url = new URL('https://openrouter.ai/auth')
        url.searchParams.set(
          'callback_url',
          `http://127.0.0.1:${server.address().port}${callbackPath}`
        )
        url.searchParams.set('code_challenge', challenge)
        url.searchParams.set('code_challenge_method', 'S256')
        url.searchParams.set('key_label', 'Stellaris Companion')
        try {
          await openExternal(url.toString())
        } catch {
          finish({ ok: false, errorCode: 'CONNECTION_FAILED' })
        }
      })
    })
  }

  return { connect, cancel, getKey, discard }
}

module.exports = { createOpenRouterOAuth }
