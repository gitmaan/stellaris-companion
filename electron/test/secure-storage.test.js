const assert = require('node:assert/strict')
const test = require('node:test')

const {
  createSecretStorage,
  getSecretStorageStatus,
} = require('../main/secureStorage')

class MemoryStore {
  constructor(initial = {}) {
    this.values = new Map(Object.entries(initial))
  }

  get(key) {
    return this.values.get(key)
  }

  set(key, value) {
    this.values.set(key, value)
  }

  delete(key) {
    this.values.delete(key)
  }
}

function protectedSafeStorage({ backend = 'gnome_libsecret' } = {}) {
  return {
    isEncryptionAvailable: () => true,
    getSelectedStorageBackend: () => backend,
    encryptString: value => Buffer.from(`encrypted:${value}`),
    decryptString: value => value.toString('utf8').replace(/^encrypted:/, ''),
  }
}

test('persists secrets only when the selected backend protects data at rest', () => {
  const store = new MemoryStore()
  const storage = createSecretStorage({
    safeStorage: protectedSafeStorage(),
    store,
    platform: 'linux',
  })

  assert.deepEqual(storage.setSecret('api-key', 'secret-value'), { persisted: true })
  assert.equal(store.get('api-key'), Buffer.from('encrypted:secret-value').toString('base64'))
  assert.equal(storage.getSecret('api-key'), 'secret-value')
  assert.equal(storage.getStatus().persistentEncryptionAvailable, true)
})

test('treats Linux basic_text as unprotected and keeps new secrets in memory only', () => {
  const store = new MemoryStore()
  const storage = createSecretStorage({
    safeStorage: protectedSafeStorage({ backend: 'basic_text' }),
    store,
    platform: 'linux',
  })

  assert.deepEqual(storage.setSecret('api-key', 'session-secret'), { persisted: false })
  assert.equal(store.get('api-key'), undefined)
  assert.equal(storage.getSecret('api-key'), 'session-secret')
  assert.equal(storage.getStatus().persistentEncryptionAvailable, false)
})

test('migrates legacy insecure values out of persistent storage when read', () => {
  const legacyValue = Buffer.from('encrypted:legacy-secret').toString('base64')
  const store = new MemoryStore({ 'api-key': legacyValue })
  const storage = createSecretStorage({
    safeStorage: protectedSafeStorage({ backend: 'basic_text' }),
    store,
    platform: 'linux',
  })

  assert.equal(storage.getSecret('api-key'), 'legacy-secret')
  assert.equal(store.get('api-key'), undefined)
  assert.equal(storage.getSecret('api-key'), 'legacy-secret')
})

test('does not report encryption availability as protected storage on basic_text', () => {
  assert.deepEqual(
    getSecretStorageStatus(protectedSafeStorage({ backend: 'basic_text' }), 'linux'),
    {
      backend: 'basic_text',
      encryptionAvailable: true,
      persistentEncryptionAvailable: false,
    },
  )
})

test('fails closed when Linux cannot identify the selected storage backend', () => {
  assert.equal(
    getSecretStorageStatus({
      isEncryptionAvailable: () => true,
      getSelectedStorageBackend: () => 'unknown',
    }, 'linux').persistentEncryptionAvailable,
    false,
  )
})
