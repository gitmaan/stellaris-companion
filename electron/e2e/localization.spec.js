const { openChapterNavigation, closeChapterNavigation } = require('./helpers/chronicleNavigation')
const fs = require('node:fs/promises')
const os = require('node:os')
const path = require('node:path')
const { test, expect, _electron: electron } = require('@playwright/test')
const { createMockChronicleBackend } = require('./helpers/mockBackend')
const { getElectronLaunchArgs } = require('./helpers/electronLaunch')
const pseudoCatalog = require('../renderer/i18n/locales/en-XA/common.json')
const japanese = require('../renderer/i18n/locales/ja/common.json')
const german = require('../renderer/i18n/locales/de/common.json')
const chinese = require('../renderer/i18n/locales/zh-Hans/common.json')

const electronDir = path.resolve(__dirname, '..')
const artifacts = path.resolve(electronDir, '..', 'artifacts', 'localization-tiers-1-2')

async function launch(port, userDataDir, saveDir, exportPath = '', extraEnv = {}) {
  return electron.launch({
    args: getElectronLaunchArgs(path.join(electronDir, 'main.js')),
    env: {
      ...process.env,
      NODE_ENV: 'test', E2E: '1', E2E_SKIP_BACKEND_AUTOSTART: '1',
      E2E_USER_DATA_DIR: userDataDir, E2E_SAVE_DIR: saveDir,
      E2E_EXPORT_PATH: exportPath,
      STELLARIS_API_PORT: String(port), STELLARIS_API_TOKEN: 'localization-test-token',
      LANG: 'en_US.UTF-8',
      ...extraEnv,
    },
  })
}

async function saveScreenshot(page, name) {
  await fs.mkdir(artifacts, { recursive: true })
  await page.waitForTimeout(400)
  await page.screenshot({ path: path.join(artifacts, name), fullPage: true, animations: 'disabled' })
}

async function saveNativeScreenshot(app, name) {
  await fs.mkdir(artifacts, { recursive: true })
  await new Promise(resolve => setTimeout(resolve, 500))
  const capture = await app.evaluate(async ({ BrowserWindow }) => {
    const image = await BrowserWindow.getAllWindows()[0].webContents.capturePage()
    return image.toPNG().toString('base64')
  })
  await fs.writeFile(path.join(artifacts, name), Buffer.from(capture, 'base64'))
}

async function assertOnboardingFits(page, step) {
  await page.waitForTimeout(450)
  const geometry = await page.evaluate(activeStep => {
    const dialog = document.querySelector('[role="dialog"]')
    const content = dialog?.querySelector(`[data-onboarding-frame-step="${activeStep}"] .custom-scrollbar`)
    return {
      viewport: document.documentElement.clientWidth,
      document: document.documentElement.scrollWidth,
      contentWidth: content?.clientWidth,
      contentScrollWidth: content?.scrollWidth,
      dialog: dialog && { left: dialog.getBoundingClientRect().left, right: dialog.getBoundingClientRect().right },
    }
  }, step)
  expect(geometry.document, JSON.stringify(geometry)).toBeLessThanOrEqual(geometry.viewport + 2)
  expect(geometry.contentScrollWidth, JSON.stringify(geometry)).toBeLessThanOrEqual((geometry.contentWidth || 0) + 2)
  expect(geometry.dialog.left, JSON.stringify(geometry)).toBeGreaterThanOrEqual(-1)
  expect(geometry.dialog.right, JSON.stringify(geometry)).toBeLessThanOrEqual(geometry.viewport + 1)
}

test('first-run language selection persists and never configures the backend', async () => {
  test.setTimeout(120_000)
  const backend = createMockChronicleBackend()
  const port = await backend.start()
  const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-l10n-e2e-'))
  const saves = path.join(profile, 'fictional-saves')
  await fs.mkdir(saves)
  let app
  try {
    app = await launch(port, profile, saves)
    const page = await app.firstWindow()
    await expect(page.getByRole('dialog')).toBeVisible()
    await page.locator('#onboarding-language').selectOption('ja')
    await expect(page.locator('html')).toHaveAttribute('lang', 'ja')
    await expect(page.getByText(japanese.onboarding.welcome.title)).toBeVisible()
    await expect(page.getByText('ステップ 1 / 3', { exact: true })).toBeVisible()
    await expect(page.getByText('言語を保存できませんでした。もう一度お試しください。')).toHaveCount(0)
    const settings = JSON.parse(await fs.readFile(path.join(profile, 'settings.json'), 'utf8'))
    expect(settings.language).toBe('ja')
    expect(settings.hasCompletedOnboarding).toBe(false)
    await saveScreenshot(page, 'ja-onboarding-welcome-1000x700-scale100.png')

    await page.getByRole('button', { name: '始める' }).click()
    await expect(page.getByText('ステップ 2 / 3', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: /Gemini API キー/ }).click()
    await expect(page.getByRole('heading', { name: 'Gemini に接続' })).toBeVisible()
    await saveScreenshot(page, 'ja-onboarding-provider-1000x700-scale100.png')
    const providerKey = page.getByRole('dialog').getByPlaceholder('AIza...')
    await providerKey.fill('fictional-localization-key')
    await page.locator('#onboarding-language').selectOption('de')
    await expect(page.getByRole('heading', { name: 'Gemini verbinden' })).toBeVisible()
    await expect(providerKey).toHaveValue('fictional-localization-key')
    await page.locator('#onboarding-language').selectOption('ja')
    await expect(providerKey).toHaveValue('fictional-localization-key')
    await providerKey.fill('')
    await page.getByRole('button', { name: '戻る', exact: true }).click()
    await page.getByRole('button', { name: '後で設定' }).click()
    await expect(page.getByRole('heading', { name: 'セーブデータを検索' })).toBeVisible()
    await expect(page.getByText('ステップ 3 / 3', { exact: true })).toBeVisible()
    await saveScreenshot(page, 'ja-onboarding-saves-1000x700-scale100.png')

    await app.close()
    app = await launch(port, profile, saves)
    const relaunched = await app.firstWindow()
    await expect(relaunched.locator('html')).toHaveAttribute('lang', 'ja')
    await expect(relaunched.getByText(japanese.onboarding.welcome.title)).toBeVisible()

    const locales = ['en', 'de', 'fr', 'es', 'pt-BR', 'ja', 'zh-Hans']
    if (await relaunched.locator('#onboarding-language option[value="en-XA"]').count()) locales.push('en-XA')
    for (const locale of locales) {
      await relaunched.locator('#onboarding-language').selectOption(locale)
      await expect(relaunched.locator('html')).toHaveAttribute('lang', locale)
      const catalog = require(`../renderer/i18n/locales/${locale}/common.json`)
      const stepLabel = catalog.onboarding.step.replace('{{current}}', '1').replace('{{total}}', '3')
      await expect(relaunched.getByText(stepLabel, { exact: true })).toBeVisible()
      await saveScreenshot(relaunched, `${locale}-onboarding-welcome-1000x700-scale100.png`)
    }
    await relaunched.locator('#onboarding-language').selectOption('de')
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setSize(800, 600))
    await saveScreenshot(relaunched, 'de-onboarding-welcome-800x600-scale100.png')
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].webContents.setZoomFactor(1.4))
    await relaunched.waitForTimeout(300)
    const geometry = await relaunched.evaluate(() => {
      const panel = document.querySelector('[role="dialog"]')?.getBoundingClientRect()
      const primary = document.querySelector('[data-onboarding-primary]')?.getBoundingClientRect()
      return { width: innerWidth, height: innerHeight, panel: panel && { left: panel.left, right: panel.right, top: panel.top, bottom: panel.bottom }, primary: primary && { left: primary.left, right: primary.right, top: primary.top, bottom: primary.bottom } }
    })
    expect(geometry.panel.right).toBeLessThanOrEqual(geometry.width + 1)
    expect(geometry.primary.right).toBeLessThanOrEqual(geometry.width + 1)
    expect(geometry.primary.bottom).toBeLessThanOrEqual(geometry.height + 1)
    await saveNativeScreenshot(app, 'de-onboarding-welcome-800x600-scale140.png')
    await relaunched.getByRole('button', { name: 'Loslegen' }).click()
    await saveNativeScreenshot(app, 'de-onboarding-chooser-800x600-scale140.png')
    const buttonsFit = await relaunched.evaluate(() => Array.from(document.querySelectorAll('[data-onboarding-actions-row] button')).every(button => { const r = button.getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth + 1 && r.top >= 0 && r.bottom <= innerHeight + 1 }))
    expect(buttonsFit).toBe(true)
    await relaunched.getByRole('button', { name: /Gemini API-Schlüssel/ }).click()
    await expect(relaunched.getByRole('heading', { name: 'Gemini verbinden' })).toBeVisible()
    await saveNativeScreenshot(app, 'de-onboarding-provider-800x600-scale140.png')
    await relaunched.getByRole('button', { name: 'Zurück', exact: true }).click()
    await relaunched.getByRole('button', { name: 'Später einrichten' }).click()
    await expect(relaunched.getByRole('heading', { name: 'Finde deine Spielstände' })).toBeVisible()
    await saveNativeScreenshot(app, 'de-onboarding-saves-800x600-scale140.png')
    await relaunched.locator('#onboarding-language').selectOption('zh-Hans')
    await expect(relaunched.locator('html')).toHaveAttribute('lang', 'zh-Hans')
    await saveNativeScreenshot(app, 'zh-Hans-onboarding-saves-800x600-scale140.png')
    if (await relaunched.locator('#onboarding-language option[value="en-XA"]').count()) {
      await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].webContents.setZoomFactor(1))
      await relaunched.locator('#onboarding-language').selectOption('en-XA')
      await expect(relaunched.locator('html')).toHaveAttribute('lang', 'en-XA')
      await relaunched.getByRole('button', { name: pseudoCatalog.onboarding.actions.back }).click()
      await assertOnboardingFits(relaunched, 2)
      await saveScreenshot(relaunched, 'en-XA-onboarding-provider-800x600-scale100.png')
      await relaunched.getByRole('button', { name: pseudoCatalog.onboarding.actions.back }).click()
      await saveScreenshot(relaunched, 'en-XA-onboarding-choice-800x600-scale100.png')
      await relaunched.getByRole('button', { name: pseudoCatalog.onboarding.actions.back }).click()
      await saveScreenshot(relaunched, 'en-XA-onboarding-welcome-800x600-scale100.png')
      await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].webContents.setZoomFactor(1.4))
      await saveNativeScreenshot(app, 'en-XA-onboarding-welcome-800x600-scale140.png')
      await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].webContents.setZoomFactor(1))
      await relaunched.getByRole('button', { name: pseudoCatalog.onboarding.actions.initialize }).click()
      await relaunched.getByRole('button', { name: pseudoCatalog.onboarding.actions.setUpLater }).click()
      await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].webContents.setZoomFactor(1.4))
      await assertOnboardingFits(relaunched, 3)
      await saveNativeScreenshot(app, 'en-XA-onboarding-saves-800x600-scale140.png')
    }
  } finally {
    if (app) await app.close().catch(() => {})
    await backend.stop()
    await fs.rm(profile, { recursive: true, force: true })
  }
})

test('Japanese onboarding finds fictional Unicode saves and localizes folder picker', async () => {
  test.setTimeout(60_000)
  const backend = createMockChronicleBackend()
  const port = await backend.start()
  const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-ja-saves-'))
  const saves = path.join(profile, '架空のセーブ')
  await fs.mkdir(saves)
  await fs.writeFile(path.join(saves, '銀河連邦.sav'), 'fictional fixture')
  await fs.writeFile(path.join(saves, '辺境同盟.sav'), 'fictional fixture')
  await fs.writeFile(path.join(profile, 'settings.json'), JSON.stringify({ language: 'ja', hasCompletedOnboarding: false }))
  let app
  try {
    app = await launch(port, profile, saves)
    const page = await app.firstWindow()
    await page.getByRole('button', { name: '始める' }).click()
    await page.getByRole('button', { name: /Gemini API キー/ }).click()
    await page.getByRole('button', { name: '戻る', exact: true }).click()
    await page.getByRole('button', { name: '後で設定' }).click()
    await expect(page.getByText('2 件のセーブデータが見つかりました')).toBeVisible()
    await saveScreenshot(page, 'ja-onboarding-saves-found-1000x700-scale100.png')
    await app.evaluate(({ dialog }) => {
      dialog.showOpenDialog = async (_window, options) => {
        globalThis.__localizationFolderOptions = options
        return { canceled: true, filePaths: [] }
      }
    })
    await page.getByRole('button', { name: '別のフォルダーを選択' }).click()
    const folderOptions = await app.evaluate(() => globalThis.__localizationFolderOptions)
    expect(folderOptions.title).toBe('Stellarisのセーブフォルダーを選択')
    await page.getByRole('button', { name: 'Companion を開く' }).click()
    await expect(page.getByRole('dialog')).toHaveCount(0)
    const settings = JSON.parse(await fs.readFile(path.join(profile, 'settings.json'), 'utf8'))
    expect(settings.hasCompletedOnboarding).toBe(true)
    expect(settings.language).toBe('ja')
    expect(settings.saveDir).toBe(saves)
  } finally {
    if (app) await app.close().catch(() => {})
    await backend.stop()
    await fs.rm(profile, { recursive: true, force: true })
  }
})

test('skipping optional onboarding steps preserves saved credentials and folder', async () => {
  const backend = createMockChronicleBackend()
  const port = await backend.start()
  const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-onboarding-preserve-'))
  const saves = path.join(profile, 'empty-fictional-saves')
  const priorFolder = path.join(profile, 'previously-selected-folder')
  await fs.mkdir(saves)
  await fs.writeFile(path.join(profile, 'settings.json'), JSON.stringify({
    language: 'ja', hasCompletedOnboarding: false, saveDir: priorFolder,
  }))
  let app
  try {
    app = await launch(port, profile, saves)
    const page = await app.firstWindow()
    await page.evaluate(() => window.electronAPI.saveSettings({ googleApiKey: 'fictional-preserved-key' }))
    expect((await page.evaluate(() => window.electronAPI.getSettings())).googleApiKeySet).toBe(true)

    await page.getByRole('button', { name: '始める' }).click()
    await page.getByRole('button', { name: /Gemini API キー/ }).click()
    await page.getByRole('button', { name: '戻る', exact: true }).click()
    await page.getByRole('button', { name: '後で設定' }).click()
    await expect(page.getByRole('heading', { name: 'セーブデータを検索' })).toBeVisible()
    await page.getByRole('button', { name: '後で設定' }).click()
    await expect(page.getByRole('dialog')).toHaveCount(0)

    const settings = await page.evaluate(() => window.electronAPI.getSettings())
    expect(settings.googleApiKeySet).toBe(true)
    expect(settings.saveDir).toBe(priorFolder)
    expect(settings.language).toBe('ja')
    expect(JSON.parse(await fs.readFile(path.join(profile, 'settings.json'), 'utf8')).hasCompletedOnboarding).toBe(true)
  } finally {
    if (app) await app.close().catch(() => {})
    await backend.stop()
    await fs.rm(profile, { recursive: true, force: true })
  }
})

test('macOS native tray menu rebuilds in the selected language', async () => {
  test.skip(process.platform !== 'darwin', 'Native macOS tray inspection requires macOS')
  const backend = createMockChronicleBackend()
  const port = await backend.start()
  const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-tray-l10n-'))
  const saves = path.join(profile, 'fictional-saves')
  await fs.mkdir(saves)
  let app
  try {
    app = await launch(port, profile, saves, '', { E2E_ENABLE_TRAY: '1' })
    const page = await app.firstWindow()
    await expect(page.getByRole('dialog')).toBeVisible()
    await expect.poll(() => app.evaluate(() => globalThis.__e2eTrayLabels?.[0])).toBe('Open Stellaris Companion')
    await page.locator('#onboarding-language').selectOption('ja')
    await expect.poll(() => app.evaluate(() => globalThis.__e2eTrayLabels?.[0])).toBe('Stellaris Companionを開く')
    const labels = await app.evaluate(() => globalThis.__e2eTrayLabels)
    expect(labels).toContain('終了')
    expect(labels.some(label => label?.startsWith('状態：'))).toBe(true)
  } finally {
    if (app) await app.close().catch(() => {})
    await backend.stop()
    await fs.rm(profile, { recursive: true, force: true })
  }
})

test('Chinese active workflows remain readable at default and maximum text scale', async () => {
  test.setTimeout(90_000)
  const backend = createMockChronicleBackend({
    initialNarrative: '晨星共同体发现了通往未知星系的航路。舰队守护边境，研究者追踪古老的信号。\n\n我们的抉择将写入未来的编年史。',
    campaigns: [
      { saveId: 'save-1', empireName: '晨星共同体', current: true, hasChronicle: true, snapshotCount: 3, eventCount: 2 },
      { saveId: 'save-2', empireName: '远星联盟', current: false, hasChronicle: false, snapshotCount: 1, eventCount: 0 },
    ],
  })
  const port = await backend.start()
  const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-zh-workflows-'))
  const saves = path.join(profile, 'fictional-saves')
  await fs.mkdir(saves)
  await fs.writeFile(path.join(profile, 'settings.json'), JSON.stringify({ language: 'zh-Hans', hasCompletedOnboarding: true }))
  let app
  try {
    app = await launch(port, profile, saves)
    const page = await app.firstWindow()
    await expect(page.locator('html')).toHaveAttribute('lang', 'zh-Hans')
    await page.getByRole('button', { name: '顾问信息' }).click()
    await expect(page.getByText(chinese.advisorPanel.personality)).toBeVisible()
    await saveScreenshot(page, 'zh-Hans-advisor-customization-1000x700-scale100-default.png')
    await page.keyboard.press('Escape')
    await page.getByRole('button', { name: '编年史' }).click()
    await expect(page.getByText('晨星共同体发现了通往未知星系的航路。舰队守护边境，研究者追踪古老的信号。')).toBeVisible()
    await page.evaluate(() => {
      const style = document.createElement('style')
      style.id = 'legacy-cjk-drop-cap-comparison'
      style.textContent = 'html[lang="zh-Hans"] .chronicle-drop-cap::first-letter { font-size: 3.5em; float: left; line-height: 0.8; padding-right: 0.1em; margin-top: 0.05em; color: #00d4ff; }'
      document.head.appendChild(style)
    })
    await saveScreenshot(page, 'zh-Hans-chronicle-before-dropcap-1000x700-scale100-default.png')
    await page.evaluate(() => document.getElementById('legacy-cjk-drop-cap-comparison')?.remove())
    await saveScreenshot(page, 'zh-Hans-chronicle-after-dropcap-1000x700-scale100-default.png')
    await (await openChapterNavigation(page)).getByRole('button', { name: chinese.chronicle.sidebar.manageCampaigns }).click()
    await expect(page.getByRole('dialog', { name: chinese.chronicle.history.title })).toBeVisible()
    await saveScreenshot(page, 'zh-Hans-campaign-management-1000x700-scale100-default.png')
    await app.evaluate(({ BrowserWindow }) => {
      const window = BrowserWindow.getAllWindows()[0]
      window.setSize(800, 600)
      window.webContents.setZoomFactor(1.4)
    })
    await saveNativeScreenshot(app, 'zh-Hans-campaign-management-800x600-scale140-default.png')
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].webContents.setZoomFactor(1))
    await page.getByRole('dialog', { name: chinese.chronicle.history.title }).getByRole('button', { name: chinese.chronicle.history.close }).click()
    await expect(page.getByRole('dialog', { name: chinese.chronicle.history.title })).toHaveCount(0)
    await closeChapterNavigation(page)
    await page.getByRole('button', { name: '⚙ 配置', exact: true }).click()
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].webContents.setZoomFactor(1.4))
    await saveNativeScreenshot(app, 'zh-Hans-settings-800x600-scale140-default.png')
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].webContents.setZoomFactor(1))
    await page.getByText(chinese.settings.moreSettings.title).click()
    await page.getByRole('button', { name: chinese.common.reportIssue }).click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await saveNativeScreenshot(app, 'zh-Hans-reporting-800x600-scale140-default.png')
  } finally {
    if (app) await app.close().catch(() => {})
    await backend.stop()
    await fs.rm(profile, { recursive: true, force: true })
  }
})

test('Japanese announcement panel ignores composition Escape', async () => {
  test.setTimeout(45_000)
  const backend = createMockChronicleBackend()
  const port = await backend.start()
  const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-ja-announcement-'))
  const saves = path.join(profile, 'fictional-saves')
  await fs.mkdir(saves)
  await fs.writeFile(path.join(profile, 'settings.json'), JSON.stringify({ language: 'ja', hasCompletedOnboarding: true }))
  const fixture = { version: 1, announcements: [{
    id: 'fictional-announcement', severity: 'info', title: '架空のお知らせ',
    body: 'これはローカライズテスト用のお知らせです。', publishedAt: '2026-01-01T00:00:00Z',
  }] }
  let app
  try {
    app = await launch(port, profile, saves, '', { E2E_ANNOUNCEMENTS_FIXTURE: JSON.stringify(fixture) })
    const page = await app.firstWindow()
    await expect(page.locator('html')).toHaveAttribute('lang', 'ja')
    if (process.env.E2E_SHOW_WINDOWS !== '1') {
      await page.getByTitle(japanese.announcements.title, { exact: true }).click()
    }
    await expect(page.getByText('架空のお知らせ')).toBeVisible()
    await saveScreenshot(page, 'ja-announcements-1000x700-scale100-default.png')
    await page.evaluate(() => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', isComposing: true, bubbles: true })))
    await expect(page.getByText('架空のお知らせ')).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByText('架空のお知らせ')).toHaveCount(0)
  } finally {
    if (app) await app.close().catch(() => {})
    await backend.stop()
    await fs.rm(profile, { recursive: true, force: true })
  }
})

test('Japanese active workflows and offline Chronicle export retain Unicode and escaped names', async () => {
  test.setTimeout(120_000)
  const empireName = '星海連邦 & <探索者>'
  const narrative = '星海連邦は新たな航路を見つけた。星々の間に広がる静けさは、次の決断を待っている。\n\n艦隊は国境を守り、研究者たちは未知の信号を調べた。私たちの選択が未来の年代記を形づくる。'
  const backend = createMockChronicleBackend({
    initialNarrative: narrative,
    chapters: [{ number: 1, title: '新たな航路', start_date: '2200.01.01', end_date: '2205.01.01', narrative: '星海連邦は最初の星系を探査した。', summary: '探査の始まり。', is_finalized: true, context_stale: false, can_regenerate: false }],
    chronicleConfigured: false,
    advisorProvider: 'lm_studio',
    campaigns: [
      { saveId: 'save-1', empireName, current: true, hasChronicle: true, snapshotCount: 3, eventCount: 2 },
      { saveId: 'save-2', empireName: '銀河辺境同盟', current: false, hasChronicle: false, snapshotCount: 1, eventCount: 0 },
    ],
  })
  const port = await backend.start()
  const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-ja-workflows-'))
  const saves = path.join(profile, 'fictional-saves')
  await fs.mkdir(saves)
  await fs.writeFile(path.join(profile, 'settings.json'), JSON.stringify({ language: 'ja', hasCompletedOnboarding: true, uiTheme: 'tactica-green' }))
  const htmlPath = path.join(artifacts, 'ja-chronicle-offline.html')
  let app
  try {
    app = await launch(port, profile, saves, htmlPath)
    await app.evaluate(({ dialog }) => {
      dialog.showSaveDialog = async (_window, options) => {
        globalThis.__localizationDialogOptions = options
        return { canceled: false, filePath: globalThis.__localizationHtmlPath }
      }
      globalThis.__localizationHtmlPath = process.env.E2E_EXPORT_PATH
    })
    const page = await app.firstWindow()
    await expect(page.locator('html')).toHaveAttribute('lang', 'ja')
    await page.getByRole('button', { name: 'アドバイザー情報' }).click()
    await expect(page.getByText(japanese.advisorPanel.personality)).toBeVisible()
    await saveScreenshot(page, 'ja-advisor-customization-1000x700-scale100-tactica-green.png')
    await page.getByPlaceholder(japanese.advisorPanel.placeholder).dispatchEvent('keydown', { key: 'Escape', code: 'Escape', isComposing: true, keyCode: 229 })
    await expect(page.getByText(japanese.advisorPanel.personality)).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByText(japanese.advisorPanel.personality)).toHaveCount(0)

    await page.getByRole('button', { name: '年代記' }).click()
    await expect(page.getByText(narrative.split('\n\n')[0])).toBeVisible()
    await expect(page.getByText(japanese.chronicle.providerSetup.title)).toBeVisible()
    await saveScreenshot(page, 'ja-chronicle-provider-error-1000x700-scale100-tactica-green.png')
    await (await openChapterNavigation(page)).getByRole('button', { name: japanese.chronicle.sidebar.storyStyle }).click()
    await expect(page.getByText(japanese.chronicle.narrator.instructions)).toBeVisible()
    await page.getByPlaceholder(japanese.chronicle.narrator.placeholder).dispatchEvent('keydown', { key: 'Escape', code: 'Escape', isComposing: true, keyCode: 229 })
    await expect(page.getByText(japanese.chronicle.narrator.instructions)).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByText(japanese.chronicle.narrator.instructions)).toHaveCount(0)
    await (await openChapterNavigation(page)).getByRole('button', { name: japanese.chronicle.sidebar.publish }).click()
    await expect(page.getByRole('dialog', { name: japanese.chronicle.publish.title })).toBeVisible()
    await page.getByRole('textbox', { name: '物語のタイトル' }).dispatchEvent('keydown', { key: 'Escape', code: 'Escape', isComposing: true, keyCode: 229 })
    await expect(page.getByRole('dialog', { name: japanese.chronicle.publish.title })).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog', { name: japanese.chronicle.publish.title })).toHaveCount(0)
    await (await openChapterNavigation(page)).getByRole('button', { name: japanese.chronicle.sidebar.manageCampaigns }).click()
    const history = page.getByRole('dialog', { name: japanese.chronicle.history.title })
    await expect(history).toBeVisible()
    await saveScreenshot(page, 'ja-campaign-management-1000x700-scale100-tactica-green.png')
    await history.locator('article').filter({ hasText: '銀河辺境同盟' }).getByRole('button', { name: japanese.chronicle.history.rename }).click()
    const rename = history.getByPlaceholder('銀河辺境同盟')
    await rename.fill('新しい銀河辺境同盟')
    await saveScreenshot(page, 'ja-campaign-rename-1000x700-scale100-tactica-green.png')
    await rename.dispatchEvent('keydown', { key: 'Enter', code: 'Enter', isComposing: true, keyCode: 229 })
    await expect(rename).toBeVisible()
    await rename.dispatchEvent('keydown', { key: 'Escape', code: 'Escape', isComposing: true, keyCode: 229 })
    await expect(rename).toBeVisible()
    await rename.press('Enter')
    await expect(history.getByText('新しい銀河辺境同盟')).toBeVisible()
    await history.getByRole('button', { name: japanese.chronicle.history.close }).click()

    await page.getByRole('button', { name: 'エクスポート' }).click()
    await expect.poll(() => fs.readFile(htmlPath, 'utf8').catch(() => '')).toContain('<html lang="ja">')
    const exported = await fs.readFile(htmlPath, 'utf8')
    expect(exported).toContain('<html lang="ja">')
    expect(exported).toContain('星海連邦 &amp; &lt;探索者&gt;の年代記')
    expect(exported).toContain('現在の時代')
    expect(exported).toContain('第1章')
    expect(exported).toContain(narrative.split('\n\n')[0])
    const japaneseDialog = await app.evaluate(() => globalThis.__localizationDialogOptions)
    expect(japaneseDialog.title).toBe('年代記を書き出す')
    expect(japaneseDialog.filters[0].name).toBe('HTML文書')

    await closeChapterNavigation(page)
    await page.getByRole('button', { name: '⚙ 設定', exact: true }).click()
    await saveScreenshot(page, 'ja-settings-1000x700-scale100-tactica-green.png')
    await page.getByText(japanese.settings.moreSettings.title).click()
    await page.getByRole('button', { name: japanese.common.reportIssue }).click()
    await expect(page.getByRole('dialog', { name: '問題の報告・フィードバック' })).toBeVisible()
    await page.waitForTimeout(2000)
    await saveScreenshot(page, 'ja-reporting-1000x700-scale100-tactica-green.png')
    await app.evaluate(({ clipboard }) => {
      clipboard.writeText = text => { globalThis.__localizationCopiedReport = text }
    })
    const reportDialog = page.getByRole('dialog', { name: '問題の報告・フィードバック' })
    expect(await reportDialog.locator('input[type="checkbox"]').evaluateAll(inputs => inputs.every(input => !input.checked))).toBe(true)
    await reportDialog.locator('select').selectOption('Bug')
    await expect(reportDialog.locator('select')).toHaveValue('Bug')
    await reportDialog.locator('textarea').fill('架空のテスト用説明')
    await reportDialog.getByRole('button', { name: '報告をコピー' }).click()
    const copiedReport = await app.evaluate(() => globalThis.__localizationCopiedReport)
    expect(copiedReport).toContain('# 不具合')
    expect(copiedReport).toContain('## 何が起きましたか')
    expect(copiedReport).toContain('アプリのバージョン：')
    expect(copiedReport).toContain('プラットフォーム：')
    expect(copiedReport).toContain('## 再現手順')
    await app.evaluate(({ shell }) => {
      shell.openExternal = async url => { globalThis.__localizationOpenedIssueUrl = url }
    })
    await reportDialog.getByRole('button', { name: 'GitHubで報告' }).click()
    const openedIssueUrl = await app.evaluate(() => globalThis.__localizationOpenedIssueUrl)
    const issue = new URL(openedIssueUrl)
    expect(issue.searchParams.get('title')).toContain('[Bug]')
    expect(issue.searchParams.get('body')).toContain('クリップボードの報告をここに貼り付けてください。')
    await page.goto(`file://${htmlPath}`)
    await expect(page.locator('html')).toHaveAttribute('lang', 'ja')
    await saveScreenshot(page, 'ja-chronicle-export-browser-1000x700-scale100.png')
  } finally {
    if (app) await app.close().catch(() => {})
    await backend.stop()
    await fs.rm(profile, { recursive: true, force: true })
  }
})

test('German Chronicle export translates chapter structure and opens offline', async () => {
  test.setTimeout(90_000)
  const empireName = 'Sternenbund & <Nova>'
  const chapter = {
    number: 1, title: 'Ein neuer Horizont', start_date: '2200.01.01', end_date: '2205.01.01',
    narrative: 'Der Sternenbund erkundete fremde Systeme und schloss ein Bündnis. Die Zukunft lag offen vor ihm.',
    summary: 'Erste Entdeckungen und ein neues Bündnis.',
    is_finalized: true, context_stale: false, can_regenerate: false,
  }
  const backend = createMockChronicleBackend({
    chapters: [chapter],
    initialNarrative: 'Eine neue Ära begann. Die Flotte kehrte aus dem Grenzgebiet zurück.',
    campaigns: [{ saveId: 'save-1', empireName, current: true, hasChronicle: true, snapshotCount: 3, eventCount: 2 }],
  })
  const port = await backend.start()
  const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-de-export-'))
  const saves = path.join(profile, 'fictional-saves')
  await fs.mkdir(saves)
  await fs.writeFile(path.join(profile, 'settings.json'), JSON.stringify({ language: 'de', hasCompletedOnboarding: true, uiTheme: 'command-amber' }))
  const htmlPath = path.join(artifacts, 'de-chronicle-offline.html')
  let app
  try {
    app = await launch(port, profile, saves, htmlPath)
    await app.evaluate(({ dialog }) => {
      dialog.showSaveDialog = async (_window, options) => {
        globalThis.__localizationDialogOptions = options
        return { canceled: false, filePath: process.env.E2E_EXPORT_PATH }
      }
    })
    const page = await app.firstWindow()
    const chatInput = page.locator('form textarea')
    await expect(chatInput).toBeEnabled()
    await chatInput.fill('Wie steht das Reich?')
    await chatInput.dispatchEvent('keydown', { key: 'Enter', code: 'Enter', isComposing: true, keyCode: 229 })
    expect(backend.getChatRequests()).toHaveLength(0)
    await expect(chatInput).toHaveValue('Wie steht das Reich?')
    await chatInput.press('Enter')
    await expect.poll(() => backend.getChatRequests().length).toBe(1)
    await page.getByRole('button', { name: /Chronik/ }).click()
    await expect(page.getByRole('heading', { name: 'Ein neuer Horizont' })).toBeVisible()
    await saveScreenshot(page, 'de-chronicle-1000x700-scale100-command-amber.png')
    await (await openChapterNavigation(page)).getByRole('button', { name: 'Exportieren' }).click()
    const exported = await fs.readFile(htmlPath, 'utf8')
    expect(exported).toContain('<html lang="de">')
    expect(exported).toContain('Chronik von Sternenbund &amp; &lt;Nova&gt;')
    expect(exported).toContain('Kapitel 1')
    expect(exported).toContain('Zusammenfassung')
    expect(exported).not.toContain('<script')
    expect(exported).not.toContain('<link')
    const germanDialog = await app.evaluate(() => globalThis.__localizationDialogOptions)
    expect(germanDialog.title).toBe('Chronik exportieren')
    expect(germanDialog.filters[0].name).toBe('HTML-Dokument')
    await page.goto(`file://${htmlPath}`)
    await expect(page.locator('html')).toHaveAttribute('lang', 'de')
    await saveScreenshot(page, 'de-chronicle-export-browser-1000x700-scale100.png')
  } finally {
    if (app) await app.close().catch(() => {})
    await backend.stop()
    await fs.rm(profile, { recursive: true, force: true })
  }
})
