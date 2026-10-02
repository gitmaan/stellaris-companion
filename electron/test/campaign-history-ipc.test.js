const assert = require('node:assert/strict')
const test = require('node:test')
const { registerBackendIpcHandlers } = require('../main/ipc/backend')

function createHarness({ validateSender = () => {} } = {}) {
  const handlers = new Map()
  const calls = []
  registerBackendIpcHandlers({
    ipcMain: {
      handle(channel, handler) {
        handlers.set(channel, handler)
      },
    },
    validateSender,
    getResolvedLanguage: () => 'de',
    callBackendApiEnvelope: async (url, options) => {
      calls.push({ url, options })
      return { ok: true, data: {} }
    },
  })
  const invoke = (channel, payload) => handlers.get(channel)({}, payload)
  return { calls, invoke }
}

test('backend IPC rejects an invalid sender before calling the backend', async () => {
  const { calls, invoke } = createHarness({
    validateSender: () => {
      throw new Error('Untrusted renderer')
    },
  })

  const result = await invoke('backend:health')

  assert.deepEqual(result, {
    ok: false,
    error: 'Untrusted renderer',
    code: 'IPC_SENDER_INVALID',
  })
  assert.equal(calls.length, 0)
})

test('campaign history IPC uses language-scoped, URL-safe backend routes', async () => {
  const { calls, invoke } = createHarness()
  const saveId = 'campaign/with spaces'

  await invoke('backend:playthroughs', { include_trashed: true })
  await invoke('backend:cached-chronicle', { save_id: saveId })
  await invoke('backend:reset-chronicle', { save_id: saveId })
  await invoke('backend:undo-chronicle-reset', { save_id: saveId })

  assert.equal(calls[0].url, '/api/playthroughs?language=de&include_trashed=true')
  assert.equal(calls[1].url, '/api/playthroughs/campaign%2Fwith%20spaces/chronicle?language=de')
  assert.deepEqual(JSON.parse(calls[2].options.body), { confirm: true, language: 'de' })
  assert.deepEqual(JSON.parse(calls[3].options.body), { language: 'de' })
})

test('permanent deletion is always sent with explicit confirmation', async () => {
  const { calls, invoke } = createHarness()

  await invoke('backend:delete-playthrough', { save_id: 'save-1' })

  assert.deepEqual(calls[0], {
    url: '/api/playthroughs/save-1?confirm=true',
    options: { method: 'DELETE' },
  })
})

test('continuity routes preserve request identity, pagination and expected revision', async () => {
  const { calls, invoke } = createHarness()
  await invoke('backend:chat', { message: 'What about the second option?', save_id: 'campaign/1', conversation_id: 'chat-1', request_id: 'request-1' })
  assert.deepEqual(JSON.parse(calls[0].options.body), { message: 'What about the second option?', save_id: 'campaign/1', conversation_id: 'chat-1', request_id: 'request-1', model: null, model_routing_mode: null, language: 'de' })
  await invoke('backend:conversation', { save_id: 'campaign/1', conversation_id: 'chat/1', before_turn_id: 'turn 2' })
  assert.equal(calls[1].url, '/api/playthroughs/campaign%2F1/conversations/chat%2F1?limit=150&before_turn_id=turn+2')
  await invoke('backend:edit-chapter', { save_id: 'campaign/1', chapter_number: 2, expected_revision: 'revision-1', title: 'Title', narrative: 'Text' })
  assert.equal(calls[2].options.method, 'PUT')
  assert.deepEqual(JSON.parse(calls[2].options.body), { expected_revision: 'revision-1', title: 'Title', narrative: 'Text', language: 'de' })
  await invoke('backend:undo-chapter', { save_id: 'campaign/1', chapter_number: 2, expected_revision: 'revision-2' })
  assert.deepEqual(JSON.parse(calls[3].options.body), { expected_revision: 'revision-2', language: 'de' })
})
