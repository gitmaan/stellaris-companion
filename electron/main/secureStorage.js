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
  let persistenceFailed = false

  function getStatus() {
    const status = getSecretStorageStatus(safeStorage, platform)
    return persistenceFailed
      ? { ...status, persistentEncryptionAvailable: false }
      : status
  }

  function decryptStoredSecret(stored) {
    if (!stored) return null
    const buffer = Buffer.from(stored, 'base64')
    const status = getStatus()
    if (status.encryptionAvailable) {
      try {
        return { value: safeStorage.decryptString(buffer), legacyPlaintext: false }
      } catch {
        // Older builds stored base64 plaintext when safeStorage was unavailable.
      }
    }
    return { value: buffer.toString('utf8'), legacyPlaintext: true }
  }

  function getSecret(key) {
    if (sessionSecrets.has(key)) return sessionSecrets.get(key)

    const stored = store.get(key)
    if (!stored) return null

    const { value, legacyPlaintext } = decryptStoredSecret(stored)
    const status = getStatus()
    if (!status.persistentEncryptionAvailable) {
      if (value) sessionSecrets.set(key, value)
      store.delete(key)
    } else if (legacyPlaintext && value) {
      setSecret(key, value)
    }
    return value
  }

  function setSecret(key, value) {
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
