const http = require('node:http')
const crypto = require('node:crypto')
const { ChatGPTError } = require('./chatgpt')

// Python receives this short-lived local capability, never an OpenAI token.
function createChatGPTBridge(service) {
  const token = crypto.randomBytes(32).toString('base64url')
  let url = ''
  const server = http.createServer(async (request, response) => {
    response.setHeader('Content-Type', 'application/json')
    response.setHeader('Cache-Control', 'no-store')
    const send = (status, body) => { response.writeHead(status); response.end(JSON.stringify(body)) }
    const authorization = Buffer.from(request.headers.authorization || '')
    const expected = Buffer.from(`Bearer ${token}`)
    // Browser-origin requests cannot use this bridge, even with a leaked token.
    if (request.headers.origin || authorization.length !== expected.length || !crypto.timingSafeEqual(authorization, expected)) {
      send(401, { code: 'CHATGPT_RECONNECT', error: 'ChatGPT connection required.' }); return
    }
    if (request.method !== 'POST' || request.url !== '/generate') { send(404, { error: 'Not found' }); return }
    try {
      let bytes = 0
      const chunks = []
      for await (const chunk of request) {
        bytes += chunk.length
        if (bytes > 16 * 1024 * 1024) { send(413, { code: 'PROVIDER_CONTEXT_LIMIT', error: 'Campaign context is too large.' }); return }
        chunks.push(chunk)
      }
      const payload = JSON.parse(Buffer.concat(chunks).toString('utf8'))
      if (typeof payload.input !== 'string' || typeof payload.instructions !== 'string'
          || (payload.model !== undefined && typeof payload.model !== 'string')
          || (payload.purpose !== undefined && !['advisor', 'chronicle'].includes(payload.purpose))
          || (payload.schema && (typeof payload.schema !== 'object' || Array.isArray(payload.schema)))
          || (payload.schemaName && !/^[a-zA-Z0-9_-]{1,64}$/.test(payload.schemaName))) {
        send(400, { code: 'CHATGPT_INVALID_RESPONSE', error: 'Invalid generation request.' }); return
      }
      const result = await service.generate(payload)
      send(200, result)
    } catch (error) {
      if (error instanceof ChatGPTError) send(error.status, { code: error.code, error: error.message })
      else send(503, { code: 'CHATGPT_UNAVAILABLE', error: 'ChatGPT is temporarily unavailable. Please try again.' })
    }
  })
  server.requestTimeout = 200_000
  server.headersTimeout = 10_000
  return {
    start: () => new Promise((resolve, reject) => {
      server.once('error', reject)
      server.listen(0, '127.0.0.1', () => { url = `http://127.0.0.1:${server.address().port}`; resolve() })
    }),
    connection: () => ({ url, token }),
    close: () => { server.close(); server.closeAllConnections() },
  }
}

module.exports = { createChatGPTBridge }
