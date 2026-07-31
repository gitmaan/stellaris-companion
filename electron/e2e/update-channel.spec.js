const fs = require('fs/promises')
const os = require('os')
const path = require('path')

const { test, expect, _electron: electron } = require('@playwright/test')

const { getElectronLaunchArgs } = require('./helpers/electronLaunch')

const electronDir = path.resolve(__dirname, '..')

function launchApp(userDataDir) {
  return electron.launch({
    args: getElectronLaunchArgs(path.join(electronDir, 'main.js')),
    env: {
      ...process.env,
      NODE_ENV: 'test',
      E2E: '1',
      E2E_ONBOARDING_COMPLETE: '1',
      E2E_BACKEND_CONFIGURED: '1',
      E2E_SKIP_BACKEND_AUTOSTART: '1',
      E2E_USER_DATA_DIR: userDataDir,
    },
  })
}

async function openUpdateSettings(app) {
  const page = await app.firstWindow()
  await page.waitForLoadState('domcontentloaded')
  await page.getByRole('button', { name: 'Config' }).click()
  const control = page.getByTestId('update-channel-control')
  await control.scrollIntoViewIfNeeded()
  return { page, control }
}

test('persists a Stable or Beta update preference across launches', async () => {
  const userDataDir = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-companion-updates-e2e-'))
  let app = await launchApp(userDataDir)

  try {
    let { control } = await openUpdateSettings(app)
    await expect(control.getByRole('button', { name: /Stable/ })).toHaveAttribute('aria-pressed', 'true')
    await control.getByRole('button', { name: /Beta/ }).click()
    await expect(control.getByRole('button', { name: /Beta/ })).toHaveAttribute('aria-pressed', 'true')
    await app.close()

    app = await launchApp(userDataDir)
    ;({ control } = await openUpdateSettings(app))
    await expect(control.getByRole('button', { name: /Beta/ })).toHaveAttribute('aria-pressed', 'true')
    await control.getByRole('button', { name: /Stable/ }).click()
    await expect(control.getByRole('button', { name: /Stable/ })).toHaveAttribute('aria-pressed', 'true')
  } finally {
    await app.close()
    await fs.rm(userDataDir, { recursive: true, force: true })
  }
})
