const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs/promises')
const path = require('node:path')
const os = require('node:os')
const crypto = require('node:crypto')
const { createReportSaveService, CONSENT_VERSION } = require('../main/reportSaves')

async function fixture(t) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'report-save-test-'))
  t.after(() => fs.rm(root, { recursive: true, force: true }))
  const source = path.join(root, 'autosave.sav')
  const bytes = Buffer.from('PK\x03\x04synthetic Stellaris archive')
  await fs.writeFile(source, bytes)
  const state = new Map(), secrets = new Map(), requests = []
  let failUpload = false, failReport = false
  const store = { get: (key, fallback) => state.get(key) ?? fallback, set: (key, value) => state.set(key, value) }
  const service = createReportSaveService({
    directory: path.join(root, 'staging'), store,
    getSecret: key => secrets.get(key), setSecret: (key, value) => value ? secrets.set(key, value) : secrets.delete(key),
    describeSave: async () => {
      const stat = await fs.stat(source, { bigint: true })
      return { path: source, fingerprint: [stat.dev, stat.ino, stat.size, stat.mtimeNs, stat.ctimeNs].join(':'), filename: 'autosave.sav', sizeBytes: bytes.length, empireName: 'Test empire', gameDate: '2300.01.01', gameVersion: '4.5.2' }
    },
    fetchImpl: async (url, options) => {
      requests.push({ url, options })
      if (url.endsWith('/capabilities')) return Response.json({ enabled: true, consentVersion: CONSENT_VERSION, retentionDays: 90 })
      if (url.endsWith('/report')) {
        if (failReport) throw new Error('Network disconnected')
        const save = JSON.parse(options.body).save_attachment
        assert.equal(save.consent, true)
        assert.equal(save.sha256, crypto.createHash('sha256').update(bytes).digest('hex'))
        return Response.json({ issueUrl: 'https://github.com/gitmaan/stellaris-companion/issues/79', saveAttachment: { id: save.id, expiresAt: Date.now() + 90 * 86400000 } })
      }
      if (options.method === 'DELETE') return Response.json({ status: 'deleted' })
      if (failUpload) throw new Error('Upload disconnected')
      const chunks = []
      for await (const chunk of options.body) chunks.push(chunk)
      assert.deepEqual(Buffer.concat(chunks), bytes)
      return Response.json({ status: 'ready' })
    },
  })
  const input = async () => ({ selectionId: (await service.select()).selectionId, consent: true, consentVersion: CONSENT_VERSION, report: { category: 'Bug', description: 'Synthetic report', context: {} } })
  return { service, input, root, source, state, secrets, requests, failUpload: value => { failUpload = value }, failReport: value => { failReport = value } }
}

test('preview reveals no local path; each upload requires current explicit consent', async t => {
  const f = await fixture(t)
  const preview = await f.service.select()
  assert.equal(preview.path, undefined)
  assert.equal(preview.fingerprint, undefined)
  assert.equal(preview.empireName, 'Test empire')
  await assert.rejects(f.service.submit({ ...(await f.input()), consent: false }), /consent/)
  assert.equal(f.requests.some(r => r.options.method === 'POST'), false)
})

test('captures exactly the selected bytes and deletes staging files after upload', async t => {
  const f = await fixture(t)
  const receipt = await f.service.submit(await f.input())
  assert.equal(receipt.status, 'ready')
  assert.deepEqual(await fs.readdir(path.join(f.root, 'staging')), [])
  assert.equal(JSON.stringify(await f.service.list()).includes([...f.secrets.values()][0]), false)
  await f.service.remove(receipt.id)
  assert.deepEqual(await f.service.list(), [])
  assert.equal(f.secrets.size, 0)
})

test('refuses an autosave changed after the user reviewed its metadata', async t => {
  const f = await fixture(t), input = await f.input()
  await fs.writeFile(f.source, 'changed save bytes')
  await assert.rejects(f.service.submit(input), /changed/)
  assert.equal(f.requests.some(r => r.options.method === 'POST'), false)
  assert.deepEqual(await fs.readdir(path.join(f.root, 'staging')), [])
})

test('retries upload against the same issue and immutable snapshot after the original changes', async t => {
  const f = await fixture(t)
  f.failUpload(true)
  await assert.rejects(f.service.submit(await f.input()), error => !!error.attachmentId)
  const [pending] = await f.service.list()
  assert.equal(pending.issueUrl, 'https://github.com/gitmaan/stellaris-companion/issues/79')
  await fs.writeFile(f.source, 'next autosave')
  f.failUpload(false)
  assert.equal((await f.service.retry(pending.id)).status, 'ready')
  assert.equal(f.requests.filter(r => r.url.endsWith('/report')).length, 1)
})

test('lost report response retries the same attachment ID and credential', async t => {
  const f = await fixture(t)
  f.failReport(true)
  await assert.rejects(f.service.submit(await f.input()), /disconnected/)
  const [pending] = await f.service.list()
  f.failReport(false)
  await f.service.retry(pending.id)
  const bodies = f.requests.filter(r => r.url.endsWith('/report')).map(r => JSON.parse(r.options.body))
  assert.deepEqual(bodies[0], bodies[1])
})

test('expired pending snapshots are removed while deletion receipts remain available', async t => {
  const f = await fixture(t)
  f.failUpload(true)
  await assert.rejects(f.service.submit(await f.input()))
  f.state.get('reportSaves')[0].createdAt -= 3600001
  assert.equal((await f.service.list())[0].status, 'expired')
  assert.deepEqual(await fs.readdir(path.join(f.root, 'staging')), [])
  assert.equal(f.secrets.size, 1)
})
