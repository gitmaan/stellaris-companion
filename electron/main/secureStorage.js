function getSecretStorageStatus(safeStorage, platform = process.platform) {
  let encryptionAvailable = false
  try {
    encryptionAvailable = Boolean(safeStorage?.isEncryptionAvailable?.())
  } catch {
    encryptionAvailable = false
  }

  let backend = null
  if (platform === 'linux' && typeof safeStorage?.getSelectedStorageBackend === 'function') {
    try {
      backend = safeStorage.getSelectedStorageBackend()
    } catch {
      backend = null
    }
  }

  const linuxBackendIsProtected = platform !== 'linux'
    || Boolean(backend && !['basic_text', 'unknown'].includes(backend))

  return {
    backend,
    encryptionAvailable,
    persistentEncryptionAvailable: encryptionAvailable && linuxBackendIsProtected,
  }
}

function createSecretStorage({
  safeStorage,
  store,
  platform = process.platform,
}) {
  const sessionSecrets = new Map()
  const unreadableSecrets = new Set()
  let persistenceFailed = false

  function getStatus() {
    const status = getSecretStorageStatus(safeStorage, platform)
    return {
      ...status,
      persistentEncryptionAvailable: status.persistentEncryptionAvailable && !persistenceFailed,
      decryptionFailed: unreadableSecrets.size > 0,
    }
  }

  function getSecret(key) {
    if (sessionSecrets.has(key)) return sessionSecrets.get(key)

    const stored = store.get(key)
    if (!stored) return null

    const status = getStatus()
    let value
    try {
      if (!status.encryptionAvailable) throw new Error('Credential storage unavailable')
      value = safeStorage.decryptString(Buffer.from(stored, 'base64'))
      unreadableSecrets.delete(key)
    } catch {
      // A failed decrypt cannot distinguish ciphertext from old base64 plaintext.
      // Preserve the original so a temporarily unavailable keychain can recover.
      unreadableSecrets.add(key)
      return null
    }
    if (!status.persistentEncryptionAvailable) {
      if (value) sessionSecrets.set(key, value)
      store.delete(key)
    }
    return value
  }

  function setSecret(key, value) {
    unreadableSecrets.delete(key)
    if (!value) {
      sessionSecrets.delete(key)
      store.delete(key)
      return { persisted: false }
    }

    if (!getStatus().persistentEncryptionAvailable) {
      sessionSecrets.set(key, value)
      store.delete(key)
      return { persisted: false }
    }

    try {
      const encrypted = safeStorage.encryptString(value).toString('base64')
      store.set(key, encrypted)
      sessionSecrets.delete(key)
      return { persisted: true }
    } catch {
      persistenceFailed = true
      sessionSecrets.set(key, value)
      store.delete(key)
      return { persisted: false }
    }
  }

  return {
    getSecret,
    getStatus,
    setSecret,
  }
}

module.exports = {
  createSecretStorage,
  getSecretStorageStatus,
}
