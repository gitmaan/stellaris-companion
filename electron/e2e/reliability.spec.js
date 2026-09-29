const fs = require('fs/promises')
const os = require('os')
const path = require('path')
const { test, expect, _electron: electron } = require('@playwright/test')
const { createMockChronicleBackend } = require('./helpers/mockBackend')
const { getElectronLaunchArgs } = require('./helpers/electronLaunch')

test('campaign switches reset chat and discard late replies; autosaves retain chat', async () => {
  let releaseOldReply
  const backend = createMockChronicleBackend({
    onChat: body => body.message === 'Slow reply'
      ? new Promise(resolve => { releaseOldReply = () => resolve('Old campaign late reply.') })
      : `Response to ${body.message}`,
  })
  await withApp(backend, async page => {
    const input = page.getByPlaceholder('HOW CAN WE HELP?')
    await expect(input).toBeEnabled()
    await input.fill('First question')
    await page.getByRole('button', { name: 'SEND', exact: true }).click()
    await expect(page.getByText('Response to First question')).toBeVisible()
    const firstKey = backend.getChatRequests()[0].session_key

    backend.advanceCampaign()
    await expect(page.locator('.status-bar')).toContainText('2208.01.01')
    await expect(page.getByText('Response to First question')).toBeVisible()
    await input.fill('Slow reply')
    await page.getByRole('button', { name: 'SEND', exact: true }).click()
    await expect.poll(() => typeof releaseOldReply).toBe('function')
    backend.setHealth({ save_id: 'save-2', game_date: '2210.01.01' })
    await expect(page.locator('.status-bar')).toContainText('2210.01.01')
    await expect(page.getByText('Response to First question')).toHaveCount(0)
    await expect(input).toBeEnabled()
    await input.fill('New campaign question')
    await page.getByRole('button', { name: 'SEND', exact: true }).click()
    await expect(page.getByText('Response to New campaign question')).toBeVisible()
    releaseOldReply()
    await page.waitForTimeout(500)
    await expect(page.getByText('Old campaign late reply.')).toHaveCount(0)
    expect(backend.getChatRequests()[1].session_key).toBe(firstKey)
    expect(backend.getChatRequests()[2].session_key).not.toBe(firstKey)
  }, () => releaseOldReply?.())
})

test('keyboard focus stays out of inactive tabs', async () => {
  await withApp(createMockChronicleBackend(), async page => {
    await expect(page.locator('main > [inert]')).toHaveCount(2)
    await page.getByPlaceholder('HOW CAN WE HELP?').focus()
    for (let index = 0; index < 15; index += 1) {
      await page.keyboard.press('Tab')
      expect(await page.evaluate(() => !!document.activeElement.closest('[inert], [aria-hidden="true"]'))).toBe(false)
    }
    await page.getByRole('button', { name: /Config/ }).click()
    await expect(page.getByRole('combobox', { name: 'Text Size', exact: true })).toBeVisible()
    await expect(page.locator('main > [inert]')).toHaveCount(2)
  })
})

test('history write warning is visible while Advisor remains usable and clears on recovery', async () => {
  const backend = createMockChronicleBackend()
  await withApp(backend, async page => {
    backend.setHealth({ ingestion: { stage: 'ready', last_error: 'Campaign history could not be saved: disk full' } })
    await expect(page.locator('.status-bar')).toContainText('HISTORY NOT SAVED')
    await expect(page.getByPlaceholder('HOW CAN WE HELP?')).toBeEnabled()
    await expect(page.locator('[title="Campaign history could not be saved: disk full"]')).toBeVisible()
    backend.setHealth({ ingestion: { stage: 'ready', last_error: null } })
    await expect(page.locator('.status-bar')).toContainText('SYSTEMS ONLINE')
  })
})

test('empty Chronicle explains that history is needed', async () => {
  const backend = createMockChronicleBackend({ emptyChronicle: true, campaigns: [{
    saveId: 'save-1', empireName: 'United Nations of Earth', current: true,
    hasChronicle: false, eventCount: 0, snapshotCount: 2,
  }] })
  await withApp(backend, async page => {
    await page.getByRole('button', { name: /Chronicle/i }).click()
    await backend.waitForChronicleRequest(() => true)
    await expect(page.getByRole('heading', { name: 'No Chronicle Yet' })).toBeVisible()
    await expect(page.getByText('Select a chapter to view its content.')).toHaveCount(0)
  })
})

test('a locked credential stays masked and intact when settings are saved', async () => {
  await withApp(createMockChronicleBackend(), async (page, app, profile) => {
    const ciphertext = Buffer.from('original-unreadable-ciphertext').toString('base64')
    await app.evaluate(({ safeStorage }) => {
      safeStorage.isEncryptionAvailable = () => true
      safeStorage.decryptString = () => { throw new Error('Keychain locked for test') }
    })
    const settingsPath = path.join(profile, 'settings.json')
    const stored = JSON.parse(await fs.readFile(settingsPath, 'utf8'))
    stored.secrets = { ...stored.secrets, 'google-api-key': ciphertext }
    await fs.writeFile(settingsPath, JSON.stringify(stored))
    await page.reload()
    await page.getByRole('button', { name: /Config/ }).click()
    await expect(page.getByText(/Saved credentials could not be read/)).toBeVisible()
    const settings = await page.evaluate(() => window.electronAPI.getSettings())
    expect(settings.googleApiKey).toBe('...')
    expect(settings.googleApiKeySet).toBe(true)
    expect(settings.secretStorageReadFailed).toBe(true)
    await page.evaluate(masked => window.electronAPI.saveSettings({ googleApiKey: masked }), settings.googleApiKey)
    const preserved = JSON.parse(await fs.readFile(settingsPath, 'utf8')).secrets['google-api-key']
    expect(preserved).toBe(ciphertext)
  })
})

async function withApp(backend, run, beforeClose = () => {}) {
  const port = await backend.start()
  const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-reliability-'))
  let app
  try {
    app = await electron.launch({
      args: getElectronLaunchArgs(path.resolve(__dirname, '..', 'main.js')),
      env: {
        ...process.env, NODE_ENV: 'test', E2E: '1', E2E_ONBOARDING_COMPLETE: '1',
        E2E_BACKEND_CONFIGURED: '1', E2E_SKIP_BACKEND_AUTOSTART: '1',
        E2E_HEALTH_CHECK_INTERVAL_MS: '200', E2E_USER_DATA_DIR: profile,
        STELLARIS_API_PORT: String(port), STELLARIS_API_TOKEN: 'e2e-token',
      },
    })
    const page = await app.firstWindow()
    await page.waitForLoadState('domcontentloaded')
    await run(page, app, profile)
  } finally {
    beforeClose()
    if (app) await app.close()
    await backend.stop()
    await fs.rm(profile, { recursive: true, force: true })
  }
}
