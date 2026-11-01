const fs = require('node:fs')
const fsp = require('node:fs/promises')
const path = require('node:path')
const crypto = require('node:crypto')
const { Transform } = require('node:stream')
const { pipeline } = require('node:stream/promises')

const CONSENT_VERSION = 'report-save-2026-11-02'
const MAX_BYTES = 50 * 1024 * 1024
const RETENTION_MS = 90 * 86400000
const UUID = /^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/
const fingerprint = stat => [stat.dev, stat.ino, stat.size, stat.mtimeNs, stat.ctimeNs].join(':')

function createReportSaveService({ directory, store, getSecret, setSecret, describeSave, fetchImpl = globalThis.fetch, notify = () => {}, baseUrl = 'https://feedback.galacticfilingcabinet.com' }) {
  const selections = new Map()
  const active = new Set()
  const files = id => {
    if (!UUID.test(id)) throw new Error('Invalid save reference.')
    return { save: path.join(directory, `${id}.sav`), report: path.join(directory, `${id}.json`) }
  }
  const records = () => store.get('reportSaves', []).filter(r => UUID.test(r.id))
  const saveRecord = record => store.set('reportSaves', [...records().filter(r => r.id !== record.id), record])
  const publicRecord = ({ token, ...r }) => r
  const secretKey = id => `reportSaveToken-${id}`
  async function request(route, options = {}) {
    const response = await fetchImpl(`${baseUrl}${route}`, { ...options, redirect: 'error', signal: AbortSignal.timeout(120000) })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) {
      const error = new Error(typeof data.error === 'string' ? data.error : `Save request failed (${response.status}).`)
      error.status = response.status
      throw error
    }
    return data
  }
  async function discardFiles(id) {
    for (const file of Object.values(files(id))) await fsp.rm(file, { force: true })
  }
  async function list() {
    for (const record of records()) {
      if (active.has(record.id)) continue
      active.add(record.id)
      try {
        if (record.expiresAt <= Date.now()) {
          await discardFiles(record.id)
          setSecret(secretKey(record.id), null)
          store.set('reportSaves', records().filter(r => r.id !== record.id))
        } else if (record.createdAt + 3600000 <= Date.now() && record.status !== 'ready') {
          await discardFiles(record.id)
          saveRecord({ ...record, status: 'expired' })
        }
      } finally { active.delete(record.id) }
    }
    // Recover task-owned staging left by an interrupted capture before its receipt.
    for (const name of await fsp.readdir(directory).catch(() => [])) {
      const id = name.replace(/\.(sav|json)$/, '')
      if (!UUID.test(id) || active.has(id) || records().some(r => r.id === id)) continue
      const filename = path.join(directory, name)
      const stat = await fsp.lstat(filename)
      if (stat.isFile() && stat.mtimeMs < Date.now() - 3600000) await fsp.rm(filename)
    }
    return records().map(publicRecord)
  }
  async function select() {
    const capabilities = await request('/save-attachments/capabilities')
    if (!capabilities.enabled || capabilities.consentVersion !== CONSENT_VERSION || capabilities.retentionDays !== 90) throw new Error('Save sharing is currently unavailable. You can still send a report without a save.')
    const info = await describeSave()
    const stat = await fsp.stat(info.path, { bigint: true })
    if (!stat.isFile() || path.extname(info.path).toLowerCase() !== '.sav' || stat.size < 4 || stat.size > MAX_BYTES || Number(stat.size) !== info.sizeBytes || fingerprint(stat) !== info.fingerprint) throw new Error('This save changed or cannot be attached (maximum 50 MiB). Select it again.')
    selections.clear()
    const selectionId = crypto.randomUUID()
    selections.set(selectionId, { ...info, fingerprint: fingerprint(stat) })
    const { path: localPath, fingerprint: localFingerprint, ...preview } = info
    return { ...preview, selectionId, consentVersion: CONSENT_VERSION }
  }
  async function capture(info, id) {
    await fsp.mkdir(directory, { recursive: true, mode: 0o700 })
    const source = await fsp.open(info.path, fs.constants.O_RDONLY | (fs.constants.O_NOFOLLOW || 0))
    try {
      if (fingerprint(await source.stat({ bigint: true })) !== info.fingerprint) throw new Error('The save changed. Select it again and review the updated details.')
      let bytes = 0
      const hash = crypto.createHash('sha256')
      await pipeline(source.createReadStream({ autoClose: false }), new Transform({ transform(chunk, _, callback) {
        bytes += chunk.length
        if (bytes > MAX_BYTES) return callback(new Error('Save is too large.'))
        hash.update(chunk)
        callback(null, chunk)
      } }), fs.createWriteStream(files(id).save, { flags: 'wx', mode: 0o600 }))
      if (bytes !== info.sizeBytes || fingerprint(await source.stat({ bigint: true })) !== info.fingerprint || fingerprint(await fsp.stat(info.path, { bigint: true })) !== info.fingerprint) throw new Error('The save changed during capture. Select it again.')
      return hash.digest('hex')
    } finally { await source.close() }
  }
  async function retry(id) {
    if (active.has(id)) throw new Error('This attachment is already being sent.')
    const record = records().find(r => r.id === id)
    if (!record) throw new Error('Save reference not found.')
    if (record.status === 'ready') return publicRecord(record)
    if (record.createdAt + 3600000 <= Date.now()) throw new Error('Upload permission expired. Delete this attachment and submit a new report.')
    const token = getSecret(secretKey(id))
    if (!token) throw new Error('The attachment credential is unavailable on this device.')
    active.add(id)
    try {
      if (!record.issueUrl) {
        notify({ id, stage: 'report', percent: 0 })
        const payload = JSON.parse(await fsp.readFile(files(id).report, 'utf8'))
        const data = await request('/report', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...payload, save_attachment: { id, token, sha256: record.sha256, sizeBytes: record.sizeBytes, consent: true, consentVersion: CONSENT_VERSION, gameVersion: record.gameVersion, gameDate: record.gameDate } }) })
        if (!/^https:\/\/github\.com\/gitmaan\/stellaris-companion\/issues\/\d+$/.test(data.issueUrl) || data.saveAttachment?.id !== id) throw new Error('The server did not confirm this attachment. Retry to check the same report.')
        record.issueUrl = data.issueUrl
        record.expiresAt = data.saveAttachment.expiresAt
        record.status = 'pending'
        saveRecord(record)
        await fsp.rm(files(id).report, { force: true })
      }
      notify({ id, stage: 'upload', percent: 0 })
      // Use a private immutable snapshot, never a live autosave or renderer-provided path.
      const body = fs.createReadStream(files(id).save)
      async function* chunks() {
        let sent = 0
        for await (const chunk of body) {
          sent += chunk.length
          notify({ id, stage: 'upload', percent: Math.min(99, Math.floor(sent / record.sizeBytes * 100)) })
          yield chunk
        }
      }
      try {
        const receipt = await request(`/save-attachments/${id}`, { method: 'PUT', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/octet-stream', 'Content-Length': String(record.sizeBytes) }, body: chunks(), duplex: 'half' })
        if (receipt.status !== 'ready') throw new Error('The save upload was not confirmed. Retry to check its status.')
      } finally { body.destroy() }
      record.status = 'ready'
      saveRecord(record)
      await discardFiles(id)
      notify({ id, stage: 'complete', percent: 100 })
      return publicRecord(record)
    } finally { active.delete(id) }
  }
  async function submit({ selectionId, consent, consentVersion, report }) {
    if (consent !== true || consentVersion !== CONSENT_VERSION) throw new Error('Review and accept save-sharing consent first.')
    const info = selections.get(selectionId)
    if (!info) throw new Error('Select the current save again.')
    if (!report || typeof report !== 'object' || typeof report.description !== 'string' || !report.description.trim()) throw new Error('A report description is required.')
    const body = JSON.stringify(report)
    if (Buffer.byteLength(body) > 4 * 1024 * 1024) throw new Error('Report is too large.')
    selections.delete(selectionId)
    const id = crypto.randomUUID()
    active.add(id)
    try {
      const sha256 = await capture(info, id)
      await fsp.writeFile(files(id).report, body, { flag: 'wx', mode: 0o600 })
      setSecret(secretKey(id), crypto.randomBytes(32).toString('hex'))
      const createdAt = Date.now()
      saveRecord({ id, sha256, sizeBytes: info.sizeBytes, filename: info.filename, gameVersion: info.gameVersion, gameDate: info.gameDate, createdAt, expiresAt: createdAt + RETENTION_MS, status: 'pending', issueUrl: null })
    } catch (error) { await discardFiles(id); setSecret(secretKey(id), null); throw error }
    finally { active.delete(id) }
    try { return await retry(id) }
    catch (error) { error.attachmentId = id; throw error }
  }
  async function remove(id) {
    if (active.has(id)) throw new Error('Wait for the upload to finish before deleting it.')
    const record = records().find(r => r.id === id)
    if (!record) return
    const token = getSecret(secretKey(id))
    if (!token) throw new Error('Deletion credential unavailable. Contact the maintainer with this save reference to request deletion.')
    active.add(id)
    try {
      try { await request(`/save-attachments/${id}`, { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } }) }
      catch (error) { if (error.status !== 404 && error.status !== 410) throw error }
      await discardFiles(id)
      store.set('reportSaves', records().filter(r => r.id !== id))
      setSecret(secretKey(id), null)
    } finally { active.delete(id) }
  }
  return { select, submit, retry, list, remove }
}

function registerReportSaveIpc({ ipcMain, validateSender, service }) {
  for (const method of ['select', 'submit', 'retry', 'list', 'remove']) {
    ipcMain.handle(`report-saves:${method}`, async (event, input) => {
      validateSender(event)
      try { return { ok: true, data: await service[method](input) } }
      catch (error) { return { ok: false, error: error.message || 'Save sharing failed.', attachmentId: error.attachmentId } }
    })
  }
}
module.exports = { createReportSaveService, registerReportSaveIpc, CONSENT_VERSION }
