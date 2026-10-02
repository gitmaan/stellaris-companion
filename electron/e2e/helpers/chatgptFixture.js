// Isolated desktop UI fixture. main.js gates it to unpackaged test runs only.
function createChatGPTFixture() {
  let nonce = ''
  return {
    openExternal: async value => {
      const url = new URL(value)
      nonce = url.searchParams.get('nonce')
      const callback = new URL(url.searchParams.get('redirect_uri'))
      callback.search = new URLSearchParams({ state: url.searchParams.get('state'), code: 'fixture-code', client_id: 'fixture-client' })
      if (process.env.E2E_CHATGPT_HOLD_SIGNIN === '1') {
        globalThis.__chatgptSignInOpens = (globalThis.__chatgptSignInOpens || 0) + 1
        globalThis.__chatgptContinue = () => fetch(callback)
      } else await fetch(callback)
    },
    verifyIdentity: async (_token, _clientId, expectedNonce) => {
      if (expectedNonce !== nonce) throw new Error('Invalid nonce')
      return { sub: 'fixture-commander', name: 'Commander', email: 'commander@example.test' }
    },
    fetchImpl: async (value, options = {}) => {
      const url = String(value)
      if (url.endsWith('/oauth/token')) return Response.json({ access_token: 'fixture-access', refresh_token: 'fixture-refresh',
        id_token: 'fixture-identity', expires_in: 3600, token_type: 'Bearer', scope: 'openid chatgpt.tokens.use.direct' })
      if (url.endsWith('/models')) {
        if (globalThis.__chatgptFailCatalog) return Response.json({ error: { code: 'server_error' } }, { status: 503 })
        if (globalThis.__chatgptHoldCatalog) await new Promise(resolve => { globalThis.__chatgptReleaseCatalog = resolve })
        const models = process.env.E2E_CHATGPT_MODEL_CATALOG === 'current'
          ? [['gpt-6-astra', 'GPT-6-Astra'], ['gpt-5.6-sol', 'GPT-5.6-Sol'], ['gpt-5.6-terra', 'GPT-5.6-Terra'], ['gpt-5.6-luna', 'GPT-5.6-Luna']]
          : [['fixture-strategist', 'Strategist'], ['fixture-strategist-fast', 'Strategist Fast']]
        return Response.json({ models: models.map(([slug, display_name]) => ({ slug, display_name, visibility: 'list', context_window: 272000 })) })
      }
      if (url.endsWith('/responses') && process.env.E2E_CHATGPT_HOLD_CHECK === '1') {
        await new Promise(resolve => { globalThis.__chatgptFinishCheck = resolve })
      }
      if (url.endsWith('/responses')) return new Response(`data: ${JSON.stringify({ type: 'response.completed',
        response: { status: 'completed', model: JSON.parse(options.body).model, output: [{ content: [{ type: 'output_text', text: '{"ready":true}' }] }] } })}\n\n`,
        { headers: { 'Content-Type': 'text/event-stream' } })
      if (url.includes('/.well-known/')) return Response.json({ revocation_endpoint: 'https://auth.openai.com/oauth/revoke' })
      if (url.endsWith('/oauth/revoke')) return new Response(null, { status: 200 })
      throw new Error('Unexpected fixture request')
    },
  }
}
module.exports = { createChatGPTFixture }
