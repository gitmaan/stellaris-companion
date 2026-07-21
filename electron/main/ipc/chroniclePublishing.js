const crypto = require('crypto')

const DEFAULT_API_BASE_URL = 'https://galacticfilingcabinet.com/api/chronicles'
const PUBLIC_ORIGIN = 'https://galacticfilingcabinet.com'
const MAX_RESPONSE_BYTES = 64 * 1024
const REQUEST_TIMEOUT_MS = 12000
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
const SECRET_PATTERN = /^[A-Za-z0-9_-]{43}$/
const LANGUAGE_PATTERN = /^[a-z]{2,3}(?:-[a-z0-9]{2,8})*$/i
const VISIBILITIES = new Set(['unlisted', 'discoverable'])
const SECTION_TYPES = new Set(['prose', 'quote', 'declaration'])

class ChroniclePublishingError extends Error {
  constructor(message, code = 'publishing_failed', status = null, currentRevision = null) {
    super(message)
    this.name = 'ChroniclePublishingError'
    this.code = code
    this.status = status
    this.currentRevision = currentRevision
  }
}

function createChroniclePublishingService({
  store,
  getSecret,
  setSecret,
  secretStoreKey,
  isEncryptionAvailable,
  fetchImpl = globalThis.fetch,
  apiBaseUrl = process.env.STELLARIS_CHRONICLE_PUBLISHING_API_URL || DEFAULT_API_BASE_URL,
}) {
  if (typeof fetchImpl !== 'function') {
    throw new Error('Chronicle publishing requires a fetch implementation')
  }

  const normalizedApiBaseUrl = normalizeApiBaseUrl(apiBaseUrl)

  async function publish(payload) {
    const publication = normalizePublicationPayload(payload)
    const identity = ensurePublisherIdentity()
    const records = readPublicationRecords(store)
    const existing = records.find(record => record.saveId === publication.saveId) || null
    const clientPublicationId = existing?.clientPublicationId || crypto.randomUUID()

    if (!existing) {
      writePublicationRecord(store, {
        saveId: publication.saveId,
        clientPublicationId,
        state: 'publishing',
        title: publication.title,
      })
    }

    const hasPublishedStory = Boolean(existing?.storyId && existing?.revision)
    const requestBody = hasPublishedStory
      ? {
        schema_version: 1,
        expected_revision: existing.revision,
        title: publication.title,
        empire_name: publication.empireName,
        language: publication.language,
        visibility: publication.visibility,
        document: publication.document,
      }
      : {
        schema_version: 1,
        client_publication_id: clientPublicationId,
        title: publication.title,
        empire_name: publication.empireName,
        language: publication.language,
        visibility: publication.visibility,
        document: publication.document,
      }

    const response = await requestJson({
      method: hasPublishedStory ? 'PUT' : 'POST',
      path: hasPublishedStory ? `/${existing.storyId}` : '',
      identity,
      body: requestBody,
    })
    const receipt = normalizeReceipt(response, publication.title, clientPublicationId)
    writePublicationRecord(store, { saveId: publication.saveId, state: 'published', ...receipt })
    return receipt
  }

  async function getStatus(saveIdValue) {
    const saveId = normalizeSaveId(saveIdValue)
    const record = readPublicationRecords(store).find(item => item.saveId === saveId) || null
    if (!record?.storyId || !record.revision) {
      return { state: 'unpublished' }
    }

    try {
      const identity = ensurePublisherIdentity()
      const response = await requestJson({ method: 'GET', path: `/${record.storyId}`, identity })
      const receipt = normalizeReceipt(response, record.title || '', record.clientPublicationId)
      writePublicationRecord(store, { saveId, state: 'published', ...receipt })
      return { state: 'published', receipt }
    } catch (error) {
      if (error instanceof ChroniclePublishingError && error.code === 'not_found') {
        removePublicationRecord(store, saveId)
        return { state: 'unpublished' }
      }
      return {
        state: 'published',
        receipt: recordToReceipt(record),
        syncWarning: toPublicError(error).message,
      }
    }
  }

  async function remove(saveIdValue) {
    const saveId = normalizeSaveId(saveIdValue)
    const record = readPublicationRecords(store).find(item => item.saveId === saveId) || null
    if (!record?.storyId || !record.revision) {
      throw new ChroniclePublishingError('This Chronicle has not been published.', 'not_found', 404)
    }

    const identity = ensurePublisherIdentity()
    await requestJson({
      method: 'DELETE',
      path: `/${record.storyId}`,
      identity,
      body: { expected_revision: record.revision },
      allowEmpty: true,
    })
    removePublicationRecord(store, saveId)
    return { removed: true }
  }

  function ensurePublisherIdentity() {
    if (!isEncryptionAvailable()) {
      throw new ChroniclePublishingError(
        'Secure credential storage is unavailable on this device. Chronicle publishing is disabled to protect the management key.',
        'secure_storage_unavailable',
      )
    }

    let publisherId = store.get('chroniclePublisherId', '')
    if (typeof publisherId !== 'string' || !UUID_PATTERN.test(publisherId)) {
      publisherId = crypto.randomUUID()
      store.set('chroniclePublisherId', publisherId)
    }

    let publisherSecret = getSecret(secretStoreKey)
    if (typeof publisherSecret !== 'string' || !SECRET_PATTERN.test(publisherSecret)) {
      publisherSecret = crypto.randomBytes(32).toString('base64url')
      setSecret(secretStoreKey, publisherSecret)
    }

    return { publisherId: publisherId.toLowerCase(), publisherSecret }
  }

  async function requestJson({ method, path, identity, body, allowEmpty = false }) {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
    let response

    try {
      response = await fetchImpl(`${normalizedApiBaseUrl}${path}`, {
        method,
        redirect: 'error',
        headers: {
          Accept: 'application/json',
          Authorization: `Bearer ${identity.publisherSecret}`,
          'Content-Type': 'application/json',
          'X-Publisher-Id': identity.publisherId,
        },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
        signal: controller.signal,
      })
    } catch (error) {
      if (error?.name === 'AbortError') {
        throw new ChroniclePublishingError('The Chronicle service timed out. Please try again.', 'timeout')
      }
      throw new ChroniclePublishingError('Could not reach the Chronicle service. Check your connection and try again.', 'network_error')
    } finally {
      clearTimeout(timeout)
    }

    const contentLength = Number(response.headers?.get?.('content-length') || '0')
    if (Number.isFinite(contentLength) && contentLength > MAX_RESPONSE_BYTES) {
      throw new ChroniclePublishingError('The Chronicle service returned an invalid response.', 'invalid_response')
    }

    const responseText = await response.text()
    if (Buffer.byteLength(responseText, 'utf8') > MAX_RESPONSE_BYTES) {
      throw new ChroniclePublishingError('The Chronicle service returned an invalid response.', 'invalid_response')
    }

    if (response.ok) {
      if (!responseText && allowEmpty) return null
      try {
        return JSON.parse(responseText)
      } catch {
        throw new ChroniclePublishingError('The Chronicle service returned an invalid response.', 'invalid_response')
      }
    }

    let apiError = null
    try {
      apiError = JSON.parse(responseText)?.error || null
    } catch {
      apiError = null
    }
    throw new ChroniclePublishingError(
      typeof apiError?.message === 'string' ? apiError.message : 'The Chronicle service rejected the request.',
      typeof apiError?.code === 'string' ? apiError.code : 'publishing_failed',
      response.status,
      Number.isInteger(apiError?.current_revision) ? apiError.current_revision : null,
    )
  }

  return { publish, getStatus, remove, ensurePublisherIdentity }
}

function registerChroniclePublishingIpcHandlers({ ipcMain, validateSender, service }) {
  ipcMain.handle('chronicle-publishing:publish', async (event, payload) => {
    validateSender(event)
    return invokeSafely(() => service.publish(payload))
  })
  ipcMain.handle('chronicle-publishing:status', async (event, { saveId } = {}) => {
    validateSender(event)
    return invokeSafely(() => service.getStatus(saveId))
  })
  ipcMain.handle('chronicle-publishing:delete', async (event, { saveId } = {}) => {
    validateSender(event)
    return invokeSafely(() => service.remove(saveId))
  })
}

async function invokeSafely(operation) {
  try {
    return { ok: true, data: await operation() }
  } catch (error) {
    return { ok: false, error: toPublicError(error) }
  }
}

function toPublicError(error) {
  if (error instanceof ChroniclePublishingError) {
    return {
      code: error.code,
      message: error.message,
      ...(error.status === null ? {} : { status: error.status }),
      ...(error.currentRevision === null ? {} : { currentRevision: error.currentRevision }),
    }
  }
  return { code: 'publishing_failed', message: 'Chronicle publishing could not complete the request.' }
}

function normalizePublicationPayload(value) {
  const record = requireRecord(value, 'publication')
  const saveId = normalizeSaveId(record.saveId)
  const title = requireText(record.title, 'title', 120)
  const empireName = requireText(record.empireName, 'empireName', 120)
  const language = requireText(record.language, 'language', 16)
  if (!LANGUAGE_PATTERN.test(language)) {
    throw new ChroniclePublishingError('The Chronicle language is invalid.', 'invalid_request')
  }
  if (!VISIBILITIES.has(record.visibility)) {
    throw new ChroniclePublishingError('Choose unlisted or discoverable visibility.', 'invalid_request')
  }

  const document = normalizeDocument(record.document)
  if (Buffer.byteLength(JSON.stringify(document), 'utf8') > 256 * 1024) {
    throw new ChroniclePublishingError('The Chronicle is too large to publish.', 'payload_too_large')
  }

  return {
    saveId,
    title,
    empireName,
    language,
    visibility: record.visibility,
    document,
  }
}

function normalizeDocument(value) {
  const record = requireRecord(value, 'document')
  if (!Array.isArray(record.chapters) || record.chapters.length > 100) {
    throw new ChroniclePublishingError('The Chronicle chapter list is invalid.', 'invalid_request')
  }

  const chapters = record.chapters.map((value, index) => {
    const chapter = requireRecord(value, `chapter ${index + 1}`)
    const number = requireInteger(chapter.number, `chapter ${index + 1} number`, 0, 10000)
    return {
      number,
      title: requireText(chapter.title, 'chapter title', 160),
      start_date: requireText(chapter.start_date, 'chapter start date', 32),
      end_date: requireText(chapter.end_date, 'chapter end date', 32),
      narrative: requireText(chapter.narrative, 'chapter narrative', 50000),
      summary: requireText(chapter.summary, 'chapter summary', 1000),
      is_finalized: requireBoolean(chapter.is_finalized, 'chapter finalized state'),
      context_stale: requireBoolean(chapter.context_stale, 'chapter context state'),
      can_regenerate: requireBoolean(chapter.can_regenerate, 'chapter regeneration state'),
      ...optionalTextField(chapter.epigraph, 'epigraph', 'chapter epigraph', 1000),
      ...(chapter.sections == null ? {} : { sections: normalizeSections(chapter.sections) }),
    }
  })

  let currentEra
  if (record.current_era != null) {
    const era = requireRecord(record.current_era, 'current era')
    currentEra = {
      start_date: requireText(era.start_date, 'current era start date', 32),
      narrative: requireText(era.narrative, 'current era narrative', 50000),
      events_covered: requireInteger(era.events_covered, 'current era event count', 0, 1000000),
      ...(era.sections == null ? {} : { sections: normalizeSections(era.sections) }),
    }
  }

  if (chapters.length === 0 && !currentEra) {
    throw new ChroniclePublishingError('There is no Chronicle text to publish yet.', 'empty_chronicle')
  }

  return { chapters, ...(currentEra ? { current_era: currentEra } : {}) }
}

function normalizeSections(value) {
  if (!Array.isArray(value) || value.length > 40) {
    throw new ChroniclePublishingError('A Chronicle section list is invalid.', 'invalid_request')
  }
  return value.map((value) => {
    const section = requireRecord(value, 'section')
    if (!SECTION_TYPES.has(section.type)) {
      throw new ChroniclePublishingError('A Chronicle section type is invalid.', 'invalid_request')
    }
    return {
      type: section.type,
      text: requireText(section.text, 'section text', 20000),
      ...optionalTextField(section.attribution, 'attribution', 'section attribution', 200),
    }
  })
}

function normalizeReceipt(value, title, clientPublicationId) {
  const record = requireRecord(value, 'service response')
  const storyId = requireUuid(record.story_id, 'story ID')
  const publicUrl = normalizePublicUrl(record.public_url, storyId)
  const revision = requireInteger(record.revision, 'revision', 1, Number.MAX_SAFE_INTEGER)
  if (!VISIBILITIES.has(record.visibility)) {
    throw new ChroniclePublishingError('The Chronicle service returned an invalid visibility.', 'invalid_response')
  }
  if (!['not_required', 'pending', 'approved', 'rejected'].includes(record.moderation_status)) {
    throw new ChroniclePublishingError('The Chronicle service returned an invalid moderation state.', 'invalid_response')
  }
  return {
    clientPublicationId,
    storyId,
    publicUrl,
    title,
    revision,
    visibility: record.visibility,
    moderationStatus: record.moderation_status,
    publishedAt: requireIsoDate(record.published_at, 'published date'),
    updatedAt: requireIsoDate(record.updated_at, 'updated date'),
  }
}

function normalizePublicUrl(value, storyId) {
  if (typeof value !== 'string') {
    throw new ChroniclePublishingError('The Chronicle service returned an invalid public URL.', 'invalid_response')
  }
  let parsed
  try {
    parsed = new URL(value)
  } catch {
    throw new ChroniclePublishingError('The Chronicle service returned an invalid public URL.', 'invalid_response')
  }
  if (parsed.origin !== PUBLIC_ORIGIN || parsed.pathname !== `/chronicles/${storyId}` || parsed.search || parsed.hash) {
    throw new ChroniclePublishingError('The Chronicle service returned an invalid public URL.', 'invalid_response')
  }
  return parsed.toString()
}

function normalizeApiBaseUrl(value) {
  let parsed
  try {
    parsed = new URL(value)
  } catch {
    throw new Error('Invalid Chronicle publishing API URL')
  }
  const isLoopbackHttp = parsed.protocol === 'http:'
    && ['127.0.0.1', 'localhost', '[::1]'].includes(parsed.hostname)
  if ((parsed.protocol !== 'https:' && !isLoopbackHttp) || parsed.search || parsed.hash) {
    throw new Error('Invalid Chronicle publishing API URL')
  }
  return parsed.toString().replace(/\/$/, '')
}

function normalizeSaveId(value) {
  if (typeof value !== 'string' || !value.trim() || value.length > 256 || /[\u0000-\u001f\u007f]/.test(value)) {
    throw new ChroniclePublishingError('The selected save is invalid.', 'invalid_request')
  }
  return value.trim()
}

function requireRecord(value, field) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new ChroniclePublishingError(`${field} is invalid.`, 'invalid_request')
  }
  return value
}

function requireText(value, field, maxLength) {
  if (typeof value !== 'string') {
    throw new ChroniclePublishingError(`${field} is invalid.`, 'invalid_request')
  }
  const normalized = value.replace(/\r\n?/g, '\n').trim()
  if (!normalized || normalized.length > maxLength || /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(normalized)) {
    throw new ChroniclePublishingError(`${field} is invalid.`, 'invalid_request')
  }
  return normalized
}

function optionalTextField(value, key, field, maxLength) {
  if (value == null || (typeof value === 'string' && value.trim() === '')) return {}
  return { [key]: requireText(value, field, maxLength) }
}

function requireBoolean(value, field) {
  if (typeof value !== 'boolean') {
    throw new ChroniclePublishingError(`${field} is invalid.`, 'invalid_request')
  }
  return value
}

function requireInteger(value, field, minimum, maximum) {
  if (!Number.isInteger(value) || value < minimum || value > maximum) {
    throw new ChroniclePublishingError(`${field} is invalid.`, 'invalid_request')
  }
  return value
}

function requireUuid(value, field) {
  if (typeof value !== 'string' || !UUID_PATTERN.test(value)) {
    throw new ChroniclePublishingError(`${field} is invalid.`, 'invalid_response')
  }
  return value.toLowerCase()
}

function requireIsoDate(value, field) {
  if (typeof value !== 'string' || Number.isNaN(Date.parse(value))) {
    throw new ChroniclePublishingError(`${field} is invalid.`, 'invalid_response')
  }
  return value
}

function readPublicationRecords(store) {
  const records = store.get('chroniclePublications', [])
  if (!Array.isArray(records)) return []
  return records.filter(record => (
    record && typeof record === 'object' && typeof record.saveId === 'string'
  ))
}

function writePublicationRecord(store, record) {
  const records = readPublicationRecords(store).filter(item => item.saveId !== record.saveId)
  records.push(record)
  store.set('chroniclePublications', records)
}

function removePublicationRecord(store, saveId) {
  store.set('chroniclePublications', readPublicationRecords(store).filter(item => item.saveId !== saveId))
}

function recordToReceipt(record) {
  return {
    clientPublicationId: record.clientPublicationId,
    storyId: record.storyId,
    publicUrl: record.publicUrl,
    title: record.title || '',
    revision: record.revision,
    visibility: record.visibility,
    moderationStatus: record.moderationStatus,
    publishedAt: record.publishedAt,
    updatedAt: record.updatedAt,
  }
}

module.exports = {
  ChroniclePublishingError,
  createChroniclePublishingService,
  normalizePublicationPayload,
  registerChroniclePublishingIpcHandlers,
}
