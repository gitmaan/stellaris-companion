const fs = require('node:fs/promises')
const os = require('node:os')
const path = require('node:path')
const { test, expect, _electron: electron } = require('@playwright/test')
const { createMockChronicleBackend } = require('./helpers/mockBackend')
const { getElectronLaunchArgs } = require('./helpers/electronLaunch')

const electronDir = path.resolve(__dirname, '..')
const japanese = require('../renderer/i18n/locales/ja/common.json')
const german = require('../renderer/i18n/locales/de/common.json')

test('Windows Electron first run, language persistence, and native folder label', async ({}, testInfo) => {
  test.skip(process.platform !== 'win32', 'Hosted Windows smoke only')
  test.setTimeout(90_000)

  const backend = createMockChronicleBackend()
  const port = await backend.start()
  const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-win-l10n-'))
  const saves = path.join(profile, 'fictional-saves')
  await fs.mkdir(saves)
  await fs.writeFile(path.join(profile, 'settings.json'), JSON.stringify({ language: 'ja', hasCompletedOnboarding: false }))

  const launch = () => electron.launch({
    args: getElectronLaunchArgs(path.join(electronDir, 'main.js')),
    env: {
      ...process.env,
      NODE_ENV: 'test', E2E: '1', E2E_SKIP_BACKEND_AUTOSTART: '1',
      E2E_USER_DATA_DIR: profile, E2E_SAVE_DIR: saves,
      STELLARIS_API_PORT: String(port), STELLARIS_API_TOKEN: 'windows-localization-fixture',
    },
  })

  let app
  try {
    app = await launch()
    let page = await app.firstWindow()
    await expect(page.locator('html')).toHaveAttribute('lang', 'ja')
    await expect(page.getByText(japanese.onboarding.welcome.title)).toBeVisible()
    await page.screenshot({ path: testInfo.outputPath('windows-ja-onboarding-1000x700-scale100.png') })

    await app.evaluate(({ dialog }) => {
      dialog.showOpenDialog = async (_window, options) => {
        globalThis.__windowsFolderOptions = options
        return { canceled: true, filePaths: [] }
      }
    })
    await page.getByRole('button', { name: japanese.onboarding.actions.initialize }).click()
    await page.getByRole('button', { name: japanese.onboarding.actions.setUpLater }).click()
    await page.getByRole('button', { name: japanese.onboarding.slim.chooseFolder }).click()
    expect((await app.evaluate(() => globalThis.__windowsFolderOptions)).title).toBe(japanese.native.dialogs.selectSaveFolder)

    await page.locator('#onboarding-language').selectOption('de')
    await expect(page.locator('html')).toHaveAttribute('lang', 'de')
    await page.getByRole('button', { name: german.onboarding.slim.chooseFolder }).click()
    expect((await app.evaluate(() => globalThis.__windowsFolderOptions)).title).toBe(german.native.dialogs.selectSaveFolder)
    await page.screenshot({ path: testInfo.outputPath('windows-de-onboarding-saves-1000x700-scale100.png') })

    await page.getByRole('button', { name: german.onboarding.actions.setUpLater }).click()
    await expect(page.getByRole('dialog')).toHaveCount(0)
    const persisted = JSON.parse(await fs.readFile(path.join(profile, 'settings.json'), 'utf8'))
    expect(persisted.language).toBe('de')
    expect(persisted.hasCompletedOnboarding).toBe(true)

    await app.close()
    app = await launch()
    page = await app.firstWindow()
    await expect(page.locator('html')).toHaveAttribute('lang', 'de')
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await page.screenshot({ path: testInfo.outputPath('windows-de-relaunch-1000x700-scale100.png') })
  } finally {
    if (app) await app.close().catch(() => {})
    await backend.stop()
    await fs.rm(profile, { recursive: true, force: true })
  }
})
