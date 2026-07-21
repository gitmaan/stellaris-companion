const assert = require('node:assert/strict')
const test = require('node:test')
const {
  ChroniclePublishingError,
  createChroniclePublishingService,
  normalizePublicationPayload,
} = require('../main/ipc/chroniclePublishing')

class MemoryStore {
  constructor(initial = {}) {
    this.values = new Map(Object.entries(initial))
  }

  get(key, fallback) {
    return this.values.has(key) ? this.values.get(key) : fallback
  }

  set(key, value) {
    this.values.set(key, value)
  }
}

function samplePublication(overrides = {}) {
  return {
    saveId: 'save-local-only-1',
    title: 'The Test Chronicle',
    empireName: 'Test Directorate',
    language: 'en',
    visibility: 'unlisted',
    document: {
      chapters: [{
        number: 1,
        title: 'First Light',
        start_date: '2200.01.01',
        end_date: '2202.03.04',
        narrative: 'The Directorate crossed the heliopause.',
        summary: 'The first survey began.',
        is_finalized: true,
        context_stale: false,
        can_regenerate: false,
        sections: [{ type: 'prose', text: 'A quiet star witnessed the beginning.', attribution: '' }],
      }],
      current_era: null,
    },
    ...overrides,
  }
}

function createHarness(fetchImpl) {
  const store = new MemoryStore()
  const secrets = new Map()
  const service = createChroniclePublishingService({
    store,
    getSecret: key => secrets.get(key) || null,
    setSecret: (key, value) => secrets.set(key, value),
    secretStoreKey: 'chronicle-secret',
    isEncryptionAvailable: () => true,
    fetchImpl,
    apiBaseUrl: 'https://example.test/api/chronicles',
  })
  return { service, store, secrets }
}

function receiptResponse(revision = 1) {
  return {
    story_id: '00cd337e-0852-45bb-a15f-9b645f8db2bd',
    public_url: 'https://galacticfilingcabinet.com/chronicles/00cd337e-0852-45bb-a15f-9b645f8db2bd',
    revision,
    visibility: 'unlisted',
    moderation_status: 'not_required',
    published_at: '2026-07-21T00:00:00.000Z',
    updated_at: `2026-07-21T00:0${revision}:00.000Z`,
  }
}

test('normalizes only the structured Chronicle fields and drops local-only data', () => {
  const normalized = normalizePublicationPayload({
    ...samplePublication(),
    savePath: '/private/game.sav',
    model: 'private-model-name',
    prompt: 'private prompt',
  })

  assert.equal(normalized.saveId, 'save-local-only-1')
  assert.equal('savePath' in normalized, false)
  assert.equal('model' in normalized, false)
  assert.equal('prompt' in normalized, false)
  assert.equal('current_era' in normalized.document, false)
  assert.equal('attribution' in normalized.document.chapters[0].sections[0], false)
})

test('publishes, updates, checks status, and deletes with an encrypted anonymous identity', async () => {
  const requests = []
  const { service, store, secrets } = createHarness(async (url, init) => {
    requests.push({ url, init, body: init.body ? JSON.parse(init.body) : null })
    const revision = init.method === 'PUT' ? 2 : 1
    if (init.method === 'DELETE') return new Response(null, { status: 204 })
    return Response.json(receiptResponse(revision), { status: init.method === 'POST' ? 201 : 200 })
  })

  const created = await service.publish(samplePublication())
  assert.equal(created.revision, 1)
  assert.match(store.get('chroniclePublisherId'), /^[0-9a-f-]{36}$/)
  assert.match(secrets.get('chronicle-secret'), /^[A-Za-z0-9_-]{43}$/)
  assert.equal(requests[0].init.method, 'POST')
  assert.equal(requests[0].init.redirect, 'error')
  assert.equal('saveId' in requests[0].body, false)
  assert.equal(requests[0].body.client_publication_id, created.clientPublicationId)

  const updated = await service.publish(samplePublication({ title: 'The Test Chronicle, Revised' }))
  assert.equal(updated.revision, 2)
  assert.equal(updated.title, 'The Test Chronicle, Revised')
  assert.equal(requests[1].init.method, 'PUT')
  assert.equal(requests[1].body.expected_revision, 1)

  const status = await service.getStatus('save-local-only-1')
  assert.equal(status.state, 'published')
  assert.equal(status.receipt.revision, 1)
  assert.equal(requests[2].init.method, 'GET')

  await service.remove('save-local-only-1')
  assert.equal(requests[3].init.method, 'DELETE')
  assert.deepEqual(store.get('chroniclePublications'), [])
})

test('preserves the idempotency identifier when the first network request fails', async () => {
  let attempt = 0
  const requestBodies = []
  const { service, store } = createHarness(async (_url, init) => {
    attempt += 1
    requestBodies.push(JSON.parse(init.body))
    if (attempt === 1) throw new Error('offline')
    return Response.json(receiptResponse(), { status: 201 })
  })

  await assert.rejects(service.publish(samplePublication()), (error) => (
    error instanceof ChroniclePublishingError && error.code === 'network_error'
  ))
  const pending = store.get('chroniclePublications')[0]
  assert.match(pending.clientPublicationId, /^[0-9a-f-]{36}$/)

  await service.publish(samplePublication())
  assert.equal(requestBodies[0].client_publication_id, requestBodies[1].client_publication_id)
})

test('refuses to create a management key without encrypted credential storage', () => {
  const service = createChroniclePublishingService({
    store: new MemoryStore(),
    getSecret: () => null,
    setSecret: () => {},
    secretStoreKey: 'chronicle-secret',
    isEncryptionAvailable: () => false,
    fetchImpl: async () => Response.json({}),
  })

  assert.throws(service.ensurePublisherIdentity, (error) => (
    error instanceof ChroniclePublishingError && error.code === 'secure_storage_unavailable'
  ))
})

test('rejects a service response that points outside the canonical story origin', async () => {
  const { service } = createHarness(async () => Response.json({
    ...receiptResponse(),
    public_url: 'https://evil.example/steal-management-key',
  }, { status: 201 }))

  await assert.rejects(service.publish(samplePublication()), (error) => (
    error instanceof ChroniclePublishingError && error.code === 'invalid_response'
  ))
})

test('allows plaintext publishing endpoints only on the local loopback interface', () => {
  assert.throws(() => createChroniclePublishingService({
    store: new MemoryStore(),
    getSecret: () => null,
    setSecret: () => {},
    secretStoreKey: 'chronicle-secret',
    isEncryptionAvailable: () => true,
    fetchImpl: async () => Response.json({}),
    apiBaseUrl: 'http://publishing.example/api/chronicles',
  }), /Invalid Chronicle publishing API URL/)

  assert.doesNotThrow(() => createChroniclePublishingService({
    store: new MemoryStore(),
    getSecret: () => null,
    setSecret: () => {},
    secretStoreKey: 'chronicle-secret',
    isEncryptionAvailable: () => true,
    fetchImpl: async () => Response.json({}),
    apiBaseUrl: 'http://127.0.0.1:8792/api/chronicles',
  }))
})
