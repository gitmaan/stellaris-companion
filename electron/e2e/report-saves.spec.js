const fs = require('node:fs/promises')
const os = require('node:os')
const path = require('node:path')
const { test, expect, _electron: electron } = require('@playwright/test')
const { createMockChronicleBackend } = require('./helpers/mockBackend')
const { getElectronLaunchOptions } = require('./helpers/electronLaunch')
const en = require('../renderer/i18n/locales/en/common.json')

test('explicit save consent, failed upload retry, persistent receipt and deletion', async ({}, testInfo) => {
  const backend = createMockChronicleBackend({ chatResponse: 'Synthetic advisor response for reporting.' })
  const port = await backend.start()
  const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'report-save-ui-'))
  let app
  try {
    await fs.writeFile(path.join(profile, 'settings.json'), JSON.stringify({ language: 'en', hasCompletedOnboarding: true }))
    app = await electron.launch({ ...getElectronLaunchOptions(path.resolve(__dirname, '../main.js')), env: {
      ...process.env, NODE_ENV: 'test', E2E: '1', E2E_BACKEND_CONFIGURED: '1', E2E_SKIP_BACKEND_AUTOSTART: '1', E2E_FAKE_SECURE_STORAGE: '1',
      E2E_USER_DATA_DIR: profile, STELLARIS_API_PORT: String(port), STELLARIS_API_TOKEN: 'save-test',
    } })
    const page = await app.firstWindow()
    await page.route(/^https?:\/\//, route => route.abort())
    await app.evaluate(async ({ app, ipcMain, BrowserWindow }) => {
      const require = process.mainModule.require.bind(process.mainModule)
      const fs = require('node:fs/promises'), path = require('node:path')
      const { createReportSaveService, registerReportSaveIpc, CONSENT_VERSION } = require(path.join(app.getAppPath(), 'main/reportSaves'))
      const source = path.join(app.getPath('userData'), 'synthetic.sav')
      const bytes = Buffer.from('PK\x03\x04synthetic archive')
      await fs.writeFile(source, bytes)
      const values = new Map(), secrets = new Map()
      globalThis.saveFixture = { reports: [], uploads: 0, deletes: 0 }
      const service = createReportSaveService({
        directory: path.join(app.getPath('userData'), 'fixture-staging'),
        store: { get: (key, fallback) => values.get(key) ?? fallback, set: (key, value) => values.set(key, value) },
        getSecret: key => secrets.get(key), setSecret: (key, value) => secrets.set(key, value),
        describeSave: async () => {
          const stat = await fs.stat(source, { bigint: true })
          return { path: source, fingerprint: [stat.dev, stat.ino, stat.size, stat.mtimeNs, stat.ctimeNs].join(':'), filename: 'synthetic.sav', sizeBytes: bytes.length, empireName: 'Synthetic Nomads', gameDate: '2300.01.01', gameVersion: '4.5.2' }
        },
        notify: event => BrowserWindow.getAllWindows()[0].webContents.send('report-saves:progress', event),
        fetchImpl: async (url, options) => {
          if (url.endsWith('/capabilities')) return Response.json({ enabled: true, consentVersion: CONSENT_VERSION, retentionDays: 90 })
          if (url.endsWith('/report')) {
            const payload = JSON.parse(options.body)
            globalThis.saveFixture.reports.push(payload)
            return Response.json({ issueUrl: 'https://github.com/gitmaan/stellaris-companion/issues/79', saveAttachment: { id: payload.save_attachment.id, expiresAt: Date.now() + 90 * 86400000 } })
          }
          if (options.method === 'DELETE') { globalThis.saveFixture.deletes++; return Response.json({ status: 'deleted' }) }
          globalThis.saveFixture.uploads++
          if (globalThis.saveFixture.uploads === 1) throw new Error('Synthetic upload interruption. Use Retry upload.')
          const chunks = []
          for await (const chunk of options.body) chunks.push(chunk)
          if (!Buffer.concat(chunks).equals(bytes)) throw new Error('Snapshot mismatch')
          return Response.json({ status: 'ready' })
        },
      })
      for (const method of ['select', 'submit', 'retry', 'list', 'remove']) ipcMain.removeHandler(`report-saves:${method}`)
      registerReportSaveIpc({ ipcMain, validateSender: () => {}, service })
    })
    await page.locator('#page-chat textarea').fill('Synthetic save investigation')
    await page.locator('#page-chat button[type=submit]').click()
    await page.getByRole('button', { name: en.chat.message.report, exact: true }).click()
    const dialog = page.getByRole('dialog')
    await dialog.locator('select').selectOption('Bug')
    await dialog.locator('textarea').fill('Synthetic report for save attachment QA.')
    await dialog.getByRole('button', { name: en.report.saves.select }).click()
    await expect(dialog.getByText(/Synthetic Nomads/)).toBeVisible()
    const consent = dialog.getByLabel(en.report.saves.consent)
    await expect(consent).not.toBeChecked()
    expect(await app.evaluate(() => globalThis.saveFixture.reports.length)).toBe(0)
    await consent.check()
    await page.screenshot({ path: testInfo.outputPath('save-consent.png') })
    await dialog.getByRole('button', { name: en.report.submit, exact: true }).click()
    await expect(dialog.getByText(en.report.saves.pending, { exact: false })).toBeVisible()
    await expect(dialog.getByRole('button', { name: en.report.submit, exact: true })).toBeDisabled()
    await dialog.getByRole('button', { name: en.report.saves.retry, exact: true }).click()
    await expect(dialog.getByText(en.report.saves.uploaded, { exact: true })).toBeVisible()
    expect(await app.evaluate(() => ({ reports: globalThis.saveFixture.reports.length, uploads: globalThis.saveFixture.uploads }))).toEqual({ reports: 1, uploads: 2 })
    await dialog.getByRole('button', { name: en.report.close, exact: true }).click()
    await page.getByRole('button', { name: en.chat.message.report, exact: true }).click()
    await expect(dialog.getByText(en.report.saves.ready, { exact: false })).toBeVisible()
    await expect(dialog.getByLabel(en.report.saves.consent)).toHaveCount(0)
    await dialog.getByRole('button', { name: en.report.saves.delete, exact: true }).click()
    await expect(dialog.getByText(en.report.saves.deleted, { exact: true })).toBeVisible()
    expect(await app.evaluate(() => globalThis.saveFixture.deletes)).toBe(1)
  } finally {
    if (app) await app.close().catch(() => {})
    await backend.stop()
    await fs.rm(profile, { recursive: true, force: true })
  }
})
