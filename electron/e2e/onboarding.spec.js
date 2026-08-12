const fs = require('fs/promises')
const os = require('os')
const path = require('path')

const { test, expect, _electron: electron } = require('@playwright/test')

const { createMockChronicleBackend } = require('./helpers/mockBackend')
const { getElectronLaunchArgs } = require('./helpers/electronLaunch')

const electronDir = path.resolve(__dirname, '..')

async function launchApp(backendPort, userDataDir) {
  return electron.launch({
    args: getElectronLaunchArgs(path.join(electronDir, 'main.js')),
    env: {
      ...process.env,
      HOME: userDataDir,
      NODE_ENV: 'test',
      E2E: '1',
      E2E_ONBOARDING_COMPLETE: '0',
      E2E_BACKEND_CONFIGURED: '1',
      E2E_FAKE_SECURE_STORAGE: '1',
      E2E_SKIP_BACKEND_AUTOSTART: '1',
      E2E_USER_DATA_DIR: userDataDir,
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
    await expect(dialog.getByRole('heading', { name: 'FIRST CONTACT' })).toBeVisible()
    await dialog.getByRole('button', { name: 'GET STARTED' }).click()

    await expect(dialog.getByRole('heading', { name: 'CHOOSE YOUR AI' })).toBeVisible()
    await expect(dialog.getByRole('button', { name: /Gemini.*easiest setup/i })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    await expect(dialog.getByText('Get a Gemini key', { exact: true })).toBeVisible()

    await dialog.getByRole('button', { name: /On this device.*private by default/i }).click()
    await expect(dialog.getByRole('button', { name: /On this device.*private by default/i })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    await expect(dialog.getByLabel('LOCAL APP')).toHaveValue('ollama')
    await expect(dialog.getByText('Open your local AI app', { exact: true })).toBeVisible()
    await expect(dialog.getByText('Load a model', { exact: true })).toBeVisible()
    await expect(dialog.getByText('Find available models', { exact: true })).toBeVisible()

    const actionRow = dialog.locator('[data-onboarding-actions-row="true"]')
    const fitsCompactWindow = await actionRow.evaluate((row) => {
      const box = row.getBoundingClientRect()
      return box.left >= 0 && box.right <= window.innerWidth && box.bottom <= window.innerHeight
    })
    expect(fitsCompactWindow).toBe(true)

    await dialog.getByRole('button', { name: /^(SET UP LATER|FINISH)$/ }).click()
    await expect(dialog.getByRole('heading', { name: 'CONNECT YOUR SAVES' })).toBeVisible()
    await dialog.getByRole('button', { name: 'BACK' }).click()
    await expect(dialog.getByLabel('LOCAL APP')).toHaveValue('ollama')

    await dialog.getByRole('button', { name: /Gemini.*easiest setup/i }).click()
    await dialog.getByLabel('GEMINI KEY').fill('onboarding-test-key')
    await expect(dialog.getByRole('button', { name: 'CONTINUE' })).toBeEnabled()
    await dialog.getByRole('button', { name: 'CONTINUE' }).click()
    await expect(dialog.getByRole('heading', { name: 'CONNECT YOUR SAVES' })).toBeVisible()

    await dialog.getByRole('button', { name: /^(SET UP LATER|FINISH)$/ }).click()
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
