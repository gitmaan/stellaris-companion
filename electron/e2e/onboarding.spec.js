const fs = require('fs/promises')
const os = require('os')
const path = require('path')

const { test, expect, _electron: electron } = require('@playwright/test')

const { createMockChronicleBackend } = require('./helpers/mockBackend')
const { getElectronLaunchArgs } = require('./helpers/electronLaunch')

const electronDir = path.resolve(__dirname, '..')

async function launchApp(backendPort, userDataDir) {
  const saves = path.join(userDataDir, 'saves')
  await fs.mkdir(saves, { recursive: true })
  return electron.launch({
    args: getElectronLaunchArgs(path.join(electronDir, 'main.js')),
    env: {
      ...process.env,
      NODE_ENV: 'test',
      E2E: '1',
      E2E_ONBOARDING_COMPLETE: '0',
      E2E_BACKEND_CONFIGURED: '1',
      E2E_FAKE_SECURE_STORAGE: '1',
      E2E_SKIP_BACKEND_AUTOSTART: '1',
      E2E_USER_DATA_DIR: userDataDir,
      E2E_SAVE_DIR: saves,
      STELLARIS_API_PORT: String(backendPort),
      STELLARIS_API_TOKEN: 'e2e-token',
    },
  })
}

test('guides first-time players through a visual AI choice without forcing setup', async () => {
  const backend = createMockChronicleBackend()
  const backendPort = await backend.start()
  const userDataDir = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-onboarding-e2e-'))
  const app = await launchApp(backendPort, userDataDir)

  try {
    const page = await app.firstWindow()
    await page.setViewportSize({ width: 800, height: 650 })
    await page.waitForLoadState('domcontentloaded')

    const dialog = page.getByRole('dialog')
    await expect(dialog.getByRole('heading', { name: 'First contact' })).toBeVisible()
    await dialog.getByRole('button', { name: 'Get started' }).click()
    await expect(dialog.getByRole('heading', { name: 'Connect your advisor' })).toBeVisible()
    await expect(dialog.getByRole('button', { name: 'Continue with ChatGPT', exact: true })).toBeVisible()
    await dialog.getByRole('button', { name: /Local models Ollama/ }).click()
    await expect(dialog.getByRole('radio', { name: 'Ollama', exact: true })).toBeChecked()
    await dialog.getByRole('button', { name: 'Connection details' }).click()
    await expect(dialog.getByLabel('Server URL')).toHaveValue('http://127.0.0.1:11434/v1')
    const actionRow = dialog.locator('[data-onboarding-actions-row="true"]')
    expect(await actionRow.evaluate(row => {
      const box = row.getBoundingClientRect()
      return box.left >= 0 && box.right <= window.innerWidth && box.bottom <= window.innerHeight
    })).toBe(true)
    await dialog.getByRole('button', { name: 'Back', exact: true }).click()
    await dialog.getByRole('button', { name: 'Back', exact: true }).click()
    await dialog.getByRole('button', { name: 'Set up later', exact: true }).click()
    await expect(dialog.getByRole('heading', { name: 'Find your saves' })).toBeVisible()
    await dialog.getByRole('button', { name: 'Back', exact: true }).click()
    await dialog.getByRole('button', { name: /Gemini API key/ }).click()
    // Exercise catalog authentication and the real structured connection probe.
    await app.evaluate(() => {
      const realFetch = globalThis.fetch
      globalThis.__onboardingProbeCount = 0
      globalThis.fetch = async (url, options) => {
        if (!String(url).startsWith('https://generativelanguage.googleapis.com/')) return realFetch(url, options)
        if (String(url).includes(':generateContent')) {
          globalThis.__onboardingProbeCount++
          return Response.json({ candidates: [{ content: { parts: [{ text: '{"status":"ok"}' }] } }] })
        }
        return Response.json({ models: [{ name: 'models/fixture-text', supportedGenerationMethods: ['generateContent'] }] })
      }
    })
    await dialog.getByLabel('API key', { exact: true }).fill('onboarding-test-key')
    await dialog.getByRole('button', { name: 'Connect Gemini', exact: true }).click()
    await expect(dialog.getByRole('heading', { name: 'Find your saves' })).toBeVisible()
    expect(await app.evaluate(() => globalThis.__onboardingProbeCount)).toBe(1)
    await dialog.getByRole('button', { name: 'Set up later', exact: true }).click()
    await expect(dialog).not.toBeVisible()
    await expect.poll(() => page.evaluate(() => window.electronAPI.onboarding.getStatus())).toBe(true)

    const settings = await page.evaluate(() => window.electronAPI.getSettings())
    expect(settings.advisorProvider).toBe('gemini')
  } finally {
    await app.close()
    await backend.stop()
    await fs.rm(userDataDir, { recursive: true, force: true })
  }
})

test('opens existing AI app connections after onboarding without a provider key', async () => {
  const backend = createMockChronicleBackend()
  const port = await backend.start()
  const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-ai-app-onboarding-'))
  const app = await launchApp(port, profile)
  try {
    const page = await app.firstWindow()
    const dialog = page.getByRole('dialog')
    await dialog.getByRole('button', { name: 'Get started' }).click()
    await dialog.getByRole('button', { name: /Connect your AI app/ }).click()
    await expect(dialog.getByRole('heading', { name: 'MCP RELAY' })).toBeVisible()
    await expect(dialog.getByRole('button', { name: 'Claude Desktop', exact: true })).toBeVisible()
    await dialog.getByRole('button', { name: 'CONTINUE', exact: true }).click()
    await expect(dialog.getByRole('heading', { name: 'Find your saves' })).toBeVisible()
    await dialog.getByRole('button', { name: 'Set up later', exact: true }).click()
    await expect(dialog).not.toBeVisible()
    await expect(page.locator('#ai-app-connections')).toBeInViewport()
    await expect(page.locator('#ai-app-connections').getByText(/^Claude Desktop$/i)).toBeVisible()
    expect((await page.evaluate(() => window.electronAPI.getSettings())).googleApiKeySet).toBe(false)
  } finally {
    await app.close()
    await backend.stop()
    await fs.rm(profile, { recursive: true, force: true })
  }
})
