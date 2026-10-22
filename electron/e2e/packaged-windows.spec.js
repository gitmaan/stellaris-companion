const fs = require('node:fs/promises')
const os = require('node:os')
const path = require('node:path')
const net = require('node:net')
const crypto = require('node:crypto')
const { execFileSync } = require('node:child_process')
const { test, expect, _electron: electron } = require('@playwright/test')
const { getElectronLaunchOptions, assertPackagedApp } = require('./helpers/electronLaunch')
const zh = require('../renderer/i18n/locales/zh-Hans/common.json')
const ja = require('../renderer/i18n/locales/ja/common.json')

async function freePort() {
  const server = net.createServer()
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  const port = server.address().port
  await new Promise(resolve => server.close(resolve))
  return port
}

test('installed app starts its bundled backend and restores settings with offline page loading', async ({}, testInfo) => {
  test.skip(process.platform !== 'win32' || !process.env.E2E_EXECUTABLE_PATH, 'Requires an installed Windows release candidate')
  test.setTimeout(120_000)
  const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-installed-'))
  const saves = path.join(profile, 'empty-saves')
  await fs.mkdir(saves)
  const port = await freePort()
  const log = []
  const backendProcesses = []
  const env = { ...process.env, NODE_ENV: 'test', E2E: '1', E2E_USER_DATA_DIR: profile,
    E2E_SAVE_DIR: saves, STELLARIS_API_PORT: String(port), STELLARIS_API_TOKEN: crypto.randomUUID(),
    E2E_HEALTH_CHECK_INTERVAL_MS: '200' }
  // The app must spawn its own real backend; no provider calls or personal save paths.
  for (const key of ['E2E_SKIP_BACKEND_AUTOSTART', 'E2E_BACKEND_CONFIGURED', 'E2E_ONBOARDING_COMPLETE',
    'E2E_FAKE_SECURE_STORAGE', 'GOOGLE_API_KEY', 'STELLARIS_ADVISOR_API_KEY', 'STELLARIS_SAVE_PATH']) delete env[key]
  let app
  async function launch() {
    app = await electron.launch({ ...getElectronLaunchOptions(path.resolve(__dirname, '../main.js')), env })
    app.process().stdout.on('data', data => log.push(data.toString()))
    app.process().stderr.on('data', data => log.push(data.toString()))
    await assertPackagedApp(app)
    expect(await app.evaluate(({ app }) => app.getPath('userData'))).toBe(profile)
    const page = await app.firstWindow()
    page.on('pageerror', error => log.push(`PAGE ERROR: ${error.message}\n`))
    await expect.poll(async () => (await page.evaluate(() => window.electronAPI.backend.health()))?.data?.status,
      { timeout: 45_000 }).toBe('ok')
    expect((await page.evaluate(() => window.electronAPI.backend.historyStorage())).ok).toBe(true)
    // Startup stdout can precede Playwright's listener. Verify the live child
    // executable instead, on both launches, to prove the installed backend is used.
    const appPid = await app.evaluate(() => process.pid)
    const expectedBackend = path.join(path.dirname(process.env.E2E_EXECUTABLE_PATH),
      'resources', 'python-backend', 'stellaris-backend.exe').toLowerCase()
    await expect.poll(() => {
      const output = execFileSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command',
        `Get-CimInstance Win32_Process -Filter "ParentProcessId = ${appPid}" | Where-Object { $_.Name -eq 'stellaris-backend.exe' } | Select-Object -ExpandProperty ExecutablePath | ConvertTo-Json -Compress`], { encoding: 'utf8' })
      const paths = JSON.parse(output.trim() || '[]')
      return (Array.isArray(paths) ? paths : [paths]).map(value => path.normalize(value).toLowerCase())
    }).toContain(expectedBackend)
    backendProcesses.push({ appPid, executable: expectedBackend })
    return page
  }
  async function close() {
    await app.close()
    app = undefined
    await expect.poll(() => fetch(`http://127.0.0.1:${port}/api/health`, { signal: AbortSignal.timeout(1000) })
      .then(() => true).catch(() => false), { timeout: 15_000 }).toBe(false)
  }
  try {
    let page = await launch()
    await expect(page.getByRole('dialog')).toBeVisible()
    await page.context().setOffline(true)
    await page.locator('#onboarding-language').selectOption('zh-Hans')
    await expect(page.locator('html')).toHaveAttribute('lang', 'zh-Hans')
    await page.evaluate(() => window.electronAPI.saveSettings({ uiScale: 1.25, updateChannel: 'stable' }))
    await page.evaluate(() => window.electronAPI.onboarding.complete())
    await page.reload()
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await page.locator('button[aria-controls="page-settings"]').click()
    await page.getByLabel(zh.settings.language, { exact: true }).selectOption('ja')
    await expect(page.locator('html')).toHaveAttribute('lang', 'ja')
    await page.locator('button[aria-controls="page-chronicle"]').click()
    await expect(page.locator('#page-chronicle')).toBeVisible()
    await page.screenshot({ path: testInfo.outputPath('installed-offline-chronicle.png') })
    await close()

    page = await launch()
    await page.context().setOffline(true)
    await expect(page.locator('html')).toHaveAttribute('lang', 'ja')
    await expect(page.getByRole('dialog')).toHaveCount(0)
    const settings = await page.evaluate(() => window.electronAPI.getSettings())
    expect(settings).toMatchObject({ language: 'ja', uiScale: 1.25, updateChannel: 'stable' })
    expect(await page.evaluate(() => window.electronAPI.onboarding.getStatus())).toBe(true)
    expect(await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].webContents.getZoomFactor())).toBeCloseTo(1.25, 2)
    await page.locator('button[aria-controls="page-settings"]').click()
    await expect(page.getByLabel(ja.settings.language, { exact: true })).toHaveValue('ja')
    await page.screenshot({ path: testInfo.outputPath('installed-restarted-settings.png') })
    expect(log.join('')).not.toContain('PAGE ERROR:')
    await testInfo.attach('installed-backend-processes', { body: JSON.stringify(backendProcesses), contentType: 'application/json' })
    await testInfo.attach('installed-runtime', { body: JSON.stringify(await app.evaluate(({ app }) => ({
      version: app.getVersion(), executable: process.execPath, resources: process.resourcesPath,
      userData: app.getPath('userData'), packaged: app.isPackaged,
    }))), contentType: 'application/json' })
  } finally {
    if (app) await app.close().catch(() => {})
    await fs.writeFile(testInfo.outputPath('installed-app.log'), log.join(''))
    await fs.cp(path.join(profile, 'logs'), testInfo.outputPath('backend-logs'), { recursive: true }).catch(() => {})
    await fs.rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 })
  }
})
