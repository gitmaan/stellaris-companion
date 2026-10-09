const fs = require('node:fs/promises')
const os = require('node:os')
const path = require('node:path')
const { test, expect, _electron: electron } = require('@playwright/test')
const { createMockChronicleBackend } = require('./helpers/mockBackend')
const { getElectronLaunchArgs } = require('./helpers/electronLaunch')

const proof = path.resolve(__dirname, '../../artifacts/visual-quality')
const catalog = locale => require(`../renderer/i18n/locales/${locale}/common.json`)
const chapter = (number, paragraphs = 14) => ({
  id: `chapter-${number}`, number, title: `Chapter ${number}: Across the frontier`,
  narrative: Array.from({ length: paragraphs }, (_, i) => `Record ${number}.${i + 1}. The survey crews returned with carefully checked maps. The assembly debated each route before approving the next expedition. A new colony would need supplies, escorts, and a dependable path home.`).join('\n\n'),
  start_date: `220${number - 1}.01.01`, end_date: `220${number}.01.01`, summary: '', is_finalized: true, context_stale: false, can_regenerate: true,
})

test('background test windows remain hidden and cannot take native focus', async () => {
  test.skip(process.env.E2E_SHOW_WINDOWS === '1', 'Visible windows were explicitly requested')
  await withApp(createMockChronicleBackend({ chapters: [chapter(1)] }), async (page, app) => {
    await expect(page.locator('#page-chat textarea')).toBeEnabled()
    const state = await app.evaluate(({ app, BrowserWindow }) => {
      app.emit('activate')
      const window = BrowserWindow.getAllWindows()[0]
      return { visible: window.isVisible(), focused: window.isFocused(), focusable: window.isFocusable(), dockVisible: process.platform === 'darwin' ? app.dock.isVisible() : false }
    })
    expect(state).toEqual({ visible: false, focused: false, focusable: false, dockVisible: false })
    await page.locator('button[aria-controls="page-settings"]').click()
    await expect(page.locator('#page-settings')).toHaveAttribute('aria-hidden', 'false')
  })
})

async function withApp(backend, run) {
  const port = await backend.start()
  const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-visual-quality-'))
  let app
  try {
    app = await electron.launch({
      args: getElectronLaunchArgs(path.resolve(__dirname, '../main.js')),
      env: { ...process.env, NODE_ENV: 'test', E2E: '1', E2E_ONBOARDING_COMPLETE: '1', E2E_BACKEND_CONFIGURED: '1', E2E_SKIP_BACKEND_AUTOSTART: '1', E2E_FAKE_SECURE_STORAGE: '1', E2E_HEALTH_CHECK_INTERVAL_MS: '200', E2E_USER_DATA_DIR: profile, STELLARIS_API_PORT: String(port), STELLARIS_API_TOKEN: 'visual-quality-test-token' },
    })
    const page = await app.firstWindow()
    await page.waitForLoadState('domcontentloaded')
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    await run(page, app)
    expect(errors).toEqual([])
  } finally {
    if (app) await app.close()
    await backend.stop()
    await fs.rm(profile, { recursive: true, force: true })
  }
}

async function resize(app, width, height) {
  await app.evaluate(({ BrowserWindow }, size) => BrowserWindow.getAllWindows()[0].setSize(...size), [width, height])
}
async function preferences(page, values) {
  await page.evaluate(values => window.electronAPI.saveSettings({ chronicleRefreshMode: 'manual', ...values }), values)
  await page.reload()
  await expect(page.locator('#page-chat textarea')).toBeEnabled()
  await page.evaluate(() => document.fonts.ready)
}
async function screenshot(page, app, filename, crop) {
  await fs.mkdir(path.dirname(path.join(proof, filename)), { recursive: true })
  await page.waitForFunction(() => !document.querySelector('[data-overlay] [aria-hidden="true"][role="dialog"]'))
  await page.waitForFunction(() => Array.from(document.querySelectorAll('[data-overlay], .modal-surface')).every(element => {
    const style = getComputedStyle(element)
    return style.opacity === '1' && (style.transform === 'none' || style.transform === 'matrix(1, 0, 0, 1, 0, 0)')
  }))
  await page.waitForFunction(() => Array.from(document.querySelectorAll('.app-page')).every(page => getComputedStyle(page).opacity === (page.dataset.active === 'true' ? '1' : '0')))
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
  const png = await app.evaluate(async ({ BrowserWindow }, crop) => {
    const window = BrowserWindow.getAllWindows()[0]
    const image = await window.webContents.capturePage(crop)
    return image.resize({ width: crop?.width || window.getContentSize()[0] }).toPNG().toString('base64')
  }, crop)
  await fs.writeFile(path.join(proof, filename), Buffer.from(png, 'base64'))
}

test('visual polish comparison uses matching content and compact window sizes', async () => {
  const stage = process.env.E2E_VISUAL_PROOF_STAGE === 'before' ? 'before' : 'after'
  const folder = `polish/${stage}`
  const backend = createMockChronicleBackend({
    chapters: [chapter(1)],
    conversations: [{ id: 'fleet-review', save_id: 'save-1', title: 'Fleet readiness', created_at: 1, updated_at: 2, turns: [{
      id: 'fleet-review-1', request_id: 'fleet-review-1', game_date: '2205.01.01', created_at: 1, language: 'en',
      question: 'How should we prepare for the next expedition?',
      answer: '## Prepare before departure\n\nYour frontier needs a dependable supply line. Reinforce the escort fleet, review the nearest shipyards, and leave enough alloys in reserve to replace losses.\n\n**Next step:** check fleet readiness before committing to another route.',
    }] }],
  })
  await withApp(backend, async (page, app) => {
    await resize(app, 1000, 700); await preferences(page, { uiScale: 1 })
    await expect(page.getByText('Prepare before departure', { exact: true })).toBeVisible()
    const input = page.locator('#page-chat textarea')
    await input.fill('Review my fleet readiness.')
    await expect(page.locator('#page-chat button[type=submit]')).toBeEnabled()
    await input.blur()
    await screenshot(page, app, `${folder}/advisor-1000.png`)
    await screenshot(page, app, `${folder}/composer-1000.png`, { x: 0, y: 536, width: 1000, height: 164 })
    await resize(app, 1400, 900)
    await screenshot(page, app, `${folder}/advisor-1400.png`)
    await resize(app, 800, 600); await preferences(page, { uiScale: 1.25 })
    await expect(page.getByText('Prepare before departure', { exact: true })).toBeVisible()
    await input.fill('Review my fleet readiness.'); await input.blur()
    await expect(page.locator('#page-chat button[type=submit]')).toBeEnabled()
    await screenshot(page, app, `${folder}/advisor-800-scale125.png`)
    const advisor = page.getByRole('button', { name: 'Advisor info' })
    await advisor.click()
    await expect(page.getByRole('dialog', { name: 'Advisor style' })).toBeVisible()
    await screenshot(page, app, `${folder}/advisor-tweaks-800-scale125.png`)
    await page.keyboard.press('Escape')
    await expect(advisor).toBeFocused()
    await page.locator('button[aria-controls="page-chronicle"]').click()
    await expect(page.locator('#chapter-1 .chronicle-narrative p').first()).toBeVisible()
    await page.locator('[data-chronicle-scroll]').evaluate(element => { element.scrollTop = 0 })
    await screenshot(page, app, `${folder}/chronicle-800-scale125.png`)
    const firstParagraph = await page.locator('#chapter-1 .chronicle-narrative p').first().boundingBox()
    await resize(app, 1400, 900); await preferences(page, { uiScale: 1 })
    await page.locator('button[aria-controls="page-chronicle"]').click()
    await expect(page.locator('.chronicle-header')).toBeVisible()
    await page.locator('[data-chronicle-scroll]').evaluate(element => { element.scrollTop = 0 })
    await screenshot(page, app, `${folder}/chronicle-1400.png`)
    await page.locator('button[aria-controls="page-settings"]').click()
    await page.getByLabel(catalog('en').settings.colorTheme, { exact: true }).selectOption('tactica-green')
    await expect(page.getByLabel(catalog('en').settings.colorTheme, { exact: true })).toBeEnabled()
    await screenshot(page, app, `${folder}/settings-1400.png`)
    await resize(app, 800, 600); await preferences(page, { uiScale: 1.4, uiTheme: 'stellaris-cyan' })
    await page.locator('button[aria-controls="page-settings"]').click()
    await page.getByLabel(catalog('en').settings.colorTheme, { exact: true }).selectOption('tactica-green')
    await expect(page.getByLabel(catalog('en').settings.colorTheme, { exact: true })).toBeEnabled()
    await screenshot(page, app, `${folder}/settings-800-scale140.png`)
    await fs.writeFile(path.join(proof, folder, 'geometry.json'), JSON.stringify({ firstParagraph }, null, 2))
  })
})

test('composer aligns controls, grows upward, and keeps advisor tweaks available during replies', async () => {
  let release
  const backend = createMockChronicleBackend({ onChat: () => new Promise(resolve => { release = () => resolve('Fleet review complete.') }) })
  await withApp(backend, async (page, app) => {
    try {
      await resize(app, 800, 600)
      for (const uiScale of [1, 1.25, 1.4]) {
        await preferences(page, { uiScale })
        const input = page.locator('#page-chat textarea')
        await input.fill('Review my fleet readiness.')
        await expect(page.locator('#page-chat button[type=submit]')).toBeEnabled()
        const alignment = await input.evaluate(element => {
          const input = element.getBoundingClientRect(), style = getComputedStyle(element)
          const form = element.closest('form'), bounds = form.getBoundingClientRect()
          const buttons = Array.from(form.querySelectorAll('button')).map(button => button.getBoundingClientRect())
          return {
            height: bounds.height,
            emptyFooter: form.parentElement.getBoundingClientRect().bottom - bounds.bottom,
            offsets: buttons.map(button => Math.abs(input.top + parseFloat(style.paddingTop) + parseFloat(style.lineHeight) / 2 - (button.top + button.height / 2))),
          }
        })
        expect(alignment.height).toBeLessThanOrEqual(58)
        expect(alignment.emptyFooter).toBeLessThanOrEqual(1)
        expect(alignment.offsets.every(offset => offset <= 1)).toBe(true)
        const singleLine = await page.locator('#page-chat form').boundingBox()
        await input.fill('Review my fleet readiness.\nInclude the nearest shipyard.\nKeep an alloy reserve.')
        const multiLine = await page.locator('#page-chat form').boundingBox()
        expect(multiLine.height).toBeGreaterThan(singleLine.height)
        expect(Math.abs(multiLine.y + multiLine.height - singleLine.y - singleLine.height)).toBeLessThanOrEqual(1)
      }
      const input = page.locator('#page-chat textarea')
      await resize(app, 1000, 600)
      await input.fill('Fleet readiness and nearby shipyards. '.repeat(5))
      const widerDraft = await input.boundingBox()
      await resize(app, 800, 600)
      await expect.poll(async () => (await input.boundingBox()).height).toBeGreaterThan(widerDraft.height)
      await input.fill('Review my fleet readiness.')
      const button = page.locator('#page-chat button[type=submit]')
      const before = await button.boundingBox()
      await button.click()
      await expect.poll(() => typeof release).toBe('function')
      const during = await button.boundingBox()
      expect(Math.abs(before.width - during.width)).toBeLessThanOrEqual(1)
      await input.fill('My next question stays here.')
      const advisor = page.getByRole('button', { name: 'Advisor info' })
      await advisor.click()
      const dialog = page.getByRole('dialog', { name: 'Advisor style' })
      const instructions = dialog.getByLabel(catalog('en').advisorPanel.personalityInstructions)
      await instructions.fill('Be concise and focus on fleet readiness.')
      await dialog.getByRole('button', { name: catalog('en').advisorPanel.saveStyle, exact: true }).click()
      await expect(dialog.getByText(catalog('en').advisorPanel.saved, { exact: true })).toBeVisible()
      backend.setHealth({ empire_name: 'United Nations of Sol' })
      await expect(dialog.getByText(/United Nations of Sol/)).toBeVisible()
      await expect(dialog.getByText(catalog('en').advisorPanel.saved, { exact: true })).toBeVisible()
      await page.keyboard.press('Escape'); await expect(advisor).toBeFocused()
      await advisor.click()
      await expect(instructions).toHaveValue('Be concise and focus on fleet readiness.')
      await page.keyboard.press('Escape')
      release()
      await expect(page.getByText('Fleet review complete.')).toBeVisible()
      await expect(input).toHaveValue('My next question stays here.')
    } finally { release?.() }
  })
})
async function geometry(page) {
  return page.evaluate(() => Object.fromEntries(['.status-bar', 'nav', 'main', '#page-chat header h1', '#page-chat form'].map(selector => {
    const { x, y, width, height } = document.querySelector(selector).getBoundingClientRect()
    return [selector, { x, y, width, height }]
  })))
}
function stable(before, after) {
  for (const selector of Object.keys(before)) for (const axis of ['x', 'y', 'width', 'height']) {
    expect(Math.abs(before[selector][axis] - after[selector][axis]), `${selector} ${axis}`).toBeLessThanOrEqual(1)
  }
}
async function fits(page, selectors) {
  const overflow = await page.evaluate(selectors => {
    const viewport = { width: innerWidth, height: innerHeight }
    return selectors.flatMap(selector => Array.from(document.querySelectorAll(selector)).filter(element => !element.closest('[inert], [aria-hidden="true"]')).map(element => {
      const rect = element.getBoundingClientRect()
      return { selector, x: rect.x, y: rect.y, right: rect.right, bottom: rect.bottom, width: element.clientWidth, scrollWidth: element.scrollWidth, viewport }
    }))
  }, selectors)
  for (const rect of overflow) {
    expect(rect.x, JSON.stringify(rect)).toBeGreaterThanOrEqual(-1)
    expect(rect.right, JSON.stringify(rect)).toBeLessThanOrEqual(rect.viewport.width + 1)
    expect(rect.y, JSON.stringify(rect)).toBeGreaterThanOrEqual(-1)
    expect(rect.bottom, JSON.stringify(rect)).toBeLessThanOrEqual(rect.viewport.height + 1)
    expect(rect.scrollWidth, JSON.stringify(rect)).toBeLessThanOrEqual(rect.width + 2)
  }
}

test('readiness and long status changes keep shell, welcome heading, and composer anchored', async () => {
  const backend = createMockChronicleBackend()
  backend.setHealth({ precompute_ready: false })
  await withApp(backend, async (page, app) => {
    await resize(app, 1400, 900)
    await expect(page.getByText(catalog('en').visualQuality.analyzingHelp)).toBeVisible()
    await page.evaluate(() => document.fonts.ready)
    const before = await geometry(page)
    backend.setHealth({ precompute_ready: true, empire_name: 'The United Interstellar Confederation of the Democratic Outer Rim and Associated Frontier Territories', ingestion: { stage: 'extracting', updated_at: 2000 } })
    await expect(page.locator('#page-chat textarea')).toBeEnabled()
    await expect(page.getByText(catalog('en').chat.welcome.suggested)).toBeVisible()
    const after = await geometry(page)
    stable(before, after)
    await screenshot(page, app, 'advisor-ready-1400.png')
    await fs.writeFile(path.join(proof, 'readiness-geometry.json'), JSON.stringify({ before, after }, null, 2))
    await resize(app, 800, 600)
    const compact = await geometry(page)
    backend.setHealth({ empire_name: 'Sol', advisor_provider: 'chatgpt', ingestion: { last_error: 'History temporarily unavailable', updated_at: 3000 } })
    await expect(page.locator('.status-bar')).toContainText('Sol')
    await expect(page.locator('#page-chat').getByText(catalog('en').chatgpt.usingPlan, { exact: true })).toBeVisible()
    stable(compact, await geometry(page))
  })
})

test('no-save and offline states explain recovery instead of scanning indefinitely', async () => {
  const backend = createMockChronicleBackend()
  backend.setHealth({ save_loaded: false, save_id: null, precompute_ready: false })
  await withApp(backend, async (page, app) => {
    await expect(page.getByText(catalog('en').visualQuality.noSave)).toBeVisible()
    await expect(page.locator('#page-chat textarea')).toBeDisabled()
    await page.getByRole('button', { name: 'Check save settings' }).click()
    await expect(page.locator('#save-data')).toBeInViewport()
    await page.locator('button[aria-controls="page-chat"]').click()
    backend.setHealth({ status: 'unavailable', connected: false, save_loaded: false, precompute_ready: false })
    await expect(page.getByText(catalog('en').visualQuality.offline)).toBeVisible()
    await expect(page.getByText(catalog('en').visualQuality.offlineHelp)).toBeVisible()
    await screenshot(page, app, 'advisor-offline.png')
  })
})

test('composer retains the next draft and respects focus while a reply is pending', async () => {
  let release
  const backend = createMockChronicleBackend({ onChat: () => new Promise(resolve => { release = () => resolve('Build another science ship before expanding the fleet.') }) })
  await withApp(backend, async (page, app) => {
    try {
      await app.evaluate(({ clipboard }) => { clipboard.writeText = value => { globalThis.__visualQualityCopied = value } })
      const input = page.locator('#page-chat textarea')
      await expect(input).toBeEnabled()
      await input.fill('What should I build first?')
      const send = page.locator('#page-chat button[type=submit]')
      const buttonWidth = (await send.boundingBox()).width
      await send.click()
      await expect.poll(() => typeof release).toBe('function')
      await expect(input).toBeEnabled()
      await expect(input).toBeFocused()
      expect((await send.boundingBox()).width).toBeCloseTo(buttonWidth, 0)
      await input.fill('What about the next colony?')
      await page.getByRole('button', { name: /Config/i }).click()
      release()
      await expect(page.getByRole('button', { name: /Config/i })).toBeFocused()
      await page.locator('button[aria-controls="page-chat"]').click()
      await expect(input).toHaveValue('What about the next colony?')
      await expect(page.getByText('Build another science ship before expanding the fleet.')).toBeVisible()
      await page.getByRole('button', { name: 'Copy response' }).click()
      await expect(page.getByRole('status').filter({ hasText: /^Copied$/ })).toHaveCount(1)
      expect(await app.evaluate(() => globalThis.__visualQualityCopied)).toBe('Build another science ship before expanding the fleet.')
      expect(backend.getChatRequests()).toHaveLength(1)
    } finally { release?.() }
  })
})

test('retry replaces the failed turn and keeps its request identity', async () => {
  const backend = createMockChronicleBackend({ chatError: { code: 'PROVIDER_TIMEOUT' } })
  await withApp(backend, async page => {
    const input = page.locator('#page-chat textarea')
    await expect(input).toBeEnabled()
    await input.fill('Review my fleet readiness.')
    await page.locator('#page-chat button[type=submit]').click()
    await expect(page.getByRole('button', { name: 'Retry', exact: true })).toBeVisible()
    backend.setChatError(null)
    await page.getByRole('button', { name: 'Retry', exact: true }).click()
    await expect(page.getByText('Mock strategic response.')).toBeVisible()
    await expect(page.getByText('Review my fleet readiness.', { exact: true })).toHaveCount(1)
    const requests = backend.getChatRequests()
    expect(requests).toHaveLength(2)
    expect(requests[1].request_id).toBe(requests[0].request_id)
  })
})

test('drawers trap focus, honor composition, and restore focus through nested dialogs', async () => {
  await withApp(createMockChronicleBackend({ chapters: [chapter(1)] }), async (page, app) => {
    await resize(app, 800, 600)
    await preferences(page, { uiScale: 1.25 })
    const advisor = page.getByRole('button', { name: 'Advisor info' })
    await advisor.click()
    const dialog = page.getByRole('dialog', { name: 'Advisor style' })
    await expect(dialog).toBeVisible()
    expect(await page.locator('#root').evaluate(element => element.inert)).toBe(true)
    for (let i = 0; i < 12; i++) {
      await page.keyboard.press(i % 3 ? 'Tab' : 'Shift+Tab')
      expect(await dialog.evaluate(element => element.contains(document.activeElement))).toBe(true)
    }
    await dialog.dispatchEvent('keydown', { key: 'Escape', isComposing: true, bubbles: true })
    await expect(dialog).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(dialog).toHaveCount(0)
    await expect(advisor).toBeFocused()
    expect(await page.locator('#root').evaluate(element => element.inert)).toBe(false)
    await page.getByRole('button', { name: /Chronicle/i }).click()
    await expect(page.locator('#chapter-1')).toBeAttached()
    const articleBefore = await page.locator('#page-chronicle article').boundingBox()
    const chaptersButton = page.getByRole('button', { name: 'Chapters', exact: true })
    await chaptersButton.click()
    const drawer = page.getByRole('dialog', { name: 'Chapters', exact: true })
    await expect(drawer).toBeVisible()
    expect((await page.locator('#page-chronicle article').boundingBox()).width).toBeCloseTo(articleBefore.width, 0)
    const manager = drawer.getByRole('button', { name: 'Manage campaigns' })
    await manager.click()
    const nested = page.getByRole('dialog', { name: 'Campaign History' })
    await expect(nested).toBeVisible()
    await page.keyboard.press('Tab')
    expect(await nested.evaluate(element => element.contains(document.activeElement))).toBe(true)
    await page.keyboard.press('Escape')
    await expect(nested).toHaveCount(0)
    await expect(manager).toBeFocused()
    await page.keyboard.press('Escape')
    await expect(drawer).toHaveCount(0)
    await expect(chaptersButton).toBeFocused()
    await screenshot(page, app, 'chronicle-800-scale125.png')
  })
})

test('all text sizes fit the minimum window in long and CJK locales', async () => {
  test.setTimeout(120_000)
  await withApp(createMockChronicleBackend({ chapters: [chapter(1)] }), async (page, app) => {
    await resize(app, 800, 600)
    for (const language of ['en', 'de', 'fr', 'es', 'pt-BR', 'en-XA', 'ja', 'zh-Hans']) {
      for (const uiScale of [1, 1.1, 1.25, 1.4]) {
        await preferences(page, { language, uiScale })
        await fits(page, ['.status-bar', 'nav', '#page-chat form', '#page-chat textarea', '#page-chat button[type=submit]'])
        await page.getByRole('button', { name: new RegExp(catalog(language).app.tabs.chronicle.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')) }).click()
        await expect(page.locator('#chapter-1')).toBeAttached()
        await page.locator('[data-chronicle-scroll]').evaluate(element => { element.scrollTop = 0 })
        await fits(page, ['[data-chronicle-scroll]'])
        const width = await page.locator('#page-chronicle article').evaluate(element => element.clientWidth)
        expect(width).toBeGreaterThan(470)
        await fits(page, ['.chronicle-toolbar', '.chronicle-header', '.chronicle-display-title'])
        const title = await page.locator('.chronicle-display-title').evaluate(element => ({ height: element.clientHeight, scrollHeight: element.scrollHeight }))
        expect(title.scrollHeight).toBeLessThanOrEqual(title.height + 1)
        if (uiScale === 1.4 && ['de', 'ja'].includes(language)) await screenshot(page, app, `${language}-chronicle-800-scale140.png`)
        const paragraph = page.locator('#chapter-1 .chronicle-narrative p').first()
        await paragraph.scrollIntoViewIfNeeded()
        await expect(paragraph).toBeInViewport()
        await expect(page.getByRole('button', { name: catalog(language).chronicle.sidebar.chapters, exact: true })).toBeInViewport()
        await page.locator('button[aria-controls="page-settings"]').click()
        const sectionPicker = page.getByRole('combobox', { name: catalog(language).visualQuality.settingsSections, exact: true })
        await expect(sectionPicker).toBeVisible()
        await fits(page, ['.settings-heading-row', '.settings-sections'])
        for (const label of ['textSize', 'colorTheme', 'language']) {
          const control = page.getByRole('combobox', { name: catalog(language).settings[label], exact: true })
          await control.scrollIntoViewIfNeeded()
          await expect(control).toBeInViewport()
          const bounds = await control.evaluate(element => ({ right: element.getBoundingClientRect().right, viewport: innerWidth }))
          expect(bounds.right).toBeLessThanOrEqual(bounds.viewport + 1)
        }
      }
    }
  })
})

test('reduced motion disables decorative animation, tab scaling, and smooth chapter scrolling', async () => {
  await withApp(createMockChronicleBackend({ chapters: [chapter(1), chapter(2)] }), async (page, app) => {
    await resize(app, 1280, 900)
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await preferences(page, {})
    await page.getByRole('button', { name: /Chronicle/i }).click()
    await expect(page.locator('#chapter-2')).toBeAttached()
    const behavior = await page.evaluate(() => {
      window.__scrollBehaviors = []
      const original = Element.prototype.scrollIntoView
      Element.prototype.scrollIntoView = function (options) { window.__scrollBehaviors.push(options?.behavior); return original.call(this, options) }
      return getComputedStyle(document.querySelector('#page-chronicle')).transform
    })
    expect(behavior).toBe('none')
    await page.getByRole('complementary').getByRole('button', { name: /II Across the frontier/ }).click()
    expect(await page.evaluate(() => window.__scrollBehaviors.at(-1))).toBe('auto')
    expect(await page.evaluate(() => document.getAnimations().filter(animation => animation.effect?.target?.closest('.app-page') && animation.effect?.getTiming().iterations === Infinity).length)).toBe(0)
  })
})

test('long ChatGPT chat keeps provider and history controls usable and preserves reading position', async () => {
  let release
  const turns = Array.from({ length: 151 }, (_, i) => ({
    id: `turn-${i}`, question: `Question ${i + 1}: review this sector.`,
    answer: `Response ${i + 1}. ${'Survey the surrounding systems and maintain an alloy reserve before the next expansion. '.repeat(i % 5 + 1)}`,
    created_at: i + 1, game_date: '2205.01.01', language: 'en',
  }))
  const backend = createMockChronicleBackend({
    advisorProvider: 'chatgpt',
    conversations: [{ id: 'long-chat', save_id: 'save-1', title: 'Sector reviews', created_at: 1, updated_at: 150, turns }],
    onChat: () => new Promise(resolve => { release = () => resolve('The latest strategic response has arrived.') }),
  })
  await withApp(backend, async (page, app) => {
    try {
      await resize(app, 800, 600); await preferences(page, { uiScale: 1.4 })
      const input = page.locator('#page-chat textarea')
      await expect(input).toBeEnabled()
      const reader = page.locator('[data-chat-scroll]')
      await expect(page.getByText('Question 151: review this sector.', { exact: true })).toBeVisible()
      await expect(page.getByRole('button', { name: catalog('en').continuity.earlierMessages, exact: true })).toBeVisible()
      await fits(page, ['.chat-toolbar', '.chat-toolbar button', '.chatgpt-usage'])
      await screenshot(page, app, 'polish/after/chatgpt-history-800-scale140.png')
      await input.fill('One more review.'); await page.locator('#page-chat button[type=submit]').click()
      await expect.poll(() => typeof release).toBe('function')
      await reader.evaluate(element => { element.scrollTop = element.scrollHeight * 0.4 })
      const jump = page.getByRole('button', { name: 'Jump to latest' })
      await expect(jump).toBeVisible()
      // Let virtual rows settle after being measured, then use an actual visible message as the anchor.
      await page.waitForTimeout(250)
      const anchor = await reader.evaluate(element => {
        const top = element.getBoundingClientRect().top
        const message = Array.from(element.querySelectorAll('[data-message-id]')).find(node => node.getBoundingClientRect().bottom > top + 16)
        return { id: message.dataset.messageId, y: message.getBoundingClientRect().top }
      })
      release()
      await expect(input).toHaveAttribute('placeholder', 'HOW CAN WE HELP?')
      await expect(jump).toBeVisible()
      await expect.poll(async () => Math.abs((await page.locator(`[data-message-id="${anchor.id}"]`).boundingBox()).y - anchor.y)).toBeLessThanOrEqual(1)
      await page.locator('button[aria-controls="page-settings"]').click()
      await page.locator('button[aria-controls="page-chat"]').click()
      expect(Math.abs((await page.locator(`[data-message-id="${anchor.id}"]`).boundingBox()).y - anchor.y)).toBeLessThanOrEqual(1)
      await jump.click()
      await expect(page.getByText('The latest strategic response has arrived.')).toBeVisible()
      await expect(jump).toHaveCount(0)
      expect(await reader.locator('[data-message-id]').count()).toBeLessThan(40)
      await reader.evaluate(element => { element.scrollTop = 0 })
      // Old messages must appear fully visible on their first painted frame after remount.
      const opacities = await reader.evaluate(element => new Promise(resolve => requestAnimationFrame(() => resolve(Array.from(element.querySelectorAll('[data-message-id]')).map(node => getComputedStyle(node).opacity)))))
      expect(opacities.every(opacity => opacity === '1')).toBe(true)
    } finally { release?.() }
  })
})

test('Chronicle keeps the current paragraph across a responsive rail change and restores the opening when left at the top', async () => {
  await withApp(createMockChronicleBackend({ chapters: [chapter(1), chapter(2)] }), async (page, app) => {
    await resize(app, 1280, 900); await preferences(page, {})
    await page.locator('button[aria-controls="page-chronicle"]').click()
    const paragraph = page.locator('#chapter-2 .chronicle-narrative p').nth(5)
    await expect(paragraph).toBeAttached()
    const reader = page.locator('[data-chronicle-scroll]')
    await reader.evaluate(element => {
      const paragraph = element.querySelectorAll('#chapter-2 .chronicle-narrative p')[5]
      element.scrollTop += paragraph.getBoundingClientRect().top - element.getBoundingClientRect().top + paragraph.offsetHeight * 0.25 - 12
    })
    await page.waitForTimeout(100)
    const fraction = () => paragraph.evaluate(element => (element.closest('[data-chronicle-scroll]').getBoundingClientRect().top + 12 - element.getBoundingClientRect().top) / element.offsetHeight)
    const before = await fraction()
    await resize(app, 800, 600)
    await expect(page.getByRole('button', { name: 'Chapters', exact: true })).toBeVisible()
    await expect.poll(async () => Math.abs(await fraction() - before)).toBeLessThan(0.03)
    await page.locator('button[aria-controls="page-chat"]').click()
    await page.locator('button[aria-controls="page-chronicle"]').click()
    expect(Math.abs(await fraction() - before)).toBeLessThan(0.03)
    await screenshot(page, app, 'chronicle-preserved-paragraph.png')
    await reader.evaluate(element => { element.scrollTop = 0 })
    await page.reload()
    await expect(page.locator('#page-chat textarea')).toBeEnabled()
    await page.locator('button[aria-controls="page-chronicle"]').click()
    await expect(page.locator('.chronicle-header')).toBeVisible()
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
    await expect(page.locator('.chronicle-header')).toBeInViewport()
    expect(await reader.evaluate(element => element.scrollTop)).toBe(0)
  })
})

test('settings feedback stays inline without moving controls; the section picker reveals and focuses its target', async () => {
  await withApp(createMockChronicleBackend(), async (page, app) => {
    await resize(app, 800, 600); await preferences(page, { uiScale: 1.4 })
    const config = page.locator('button[aria-controls="page-settings"]')
    await config.focus(); await page.keyboard.press('Enter')
    expect(await config.evaluate(element => getComputedStyle(element).outlineStyle)).toBe('solid')
    // Chromium snaps the 2 CSS-pixel outline down to whole device pixels.
    // Compare in physical pixels so 140% zoom works on both 1x and 2x displays.
    const outline = await config.evaluate(element => ({
      physicalWidth: parseFloat(getComputedStyle(element).outlineWidth) * devicePixelRatio,
      expectedWidth: Math.floor(2 * devicePixelRatio),
    }))
    expect(outline.physicalWidth).toBeGreaterThanOrEqual(outline.expectedWidth - 0.01)
    const picker = page.getByRole('combobox', { name: catalog('en').visualQuality.settingsSections, exact: true })
    await fits(page, ['.settings-heading-row', '.settings-sections'])
    expect((await picker.boundingBox()).y).toBeLessThan((await page.locator('.settings-preferences').boundingBox()).y)
    await page.getByLabel(catalog('en').settings.colorTheme, { exact: true }).scrollIntoViewIfNeeded()
    const preferencesBefore = await page.locator('.settings-preferences').boundingBox()
    await page.getByLabel(catalog('en').settings.colorTheme, { exact: true }).selectOption('tactica-green')
    await expect(page.locator('.settings-preferences [role=status]').filter({ hasText: /^Saved$/ })).toBeVisible()
    await expect(page.locator('[data-notifications] > div')).toHaveCount(0)
    const preferencesAfter = await page.locator('.settings-preferences').boundingBox()
    stable({ preferences: preferencesBefore }, { preferences: preferencesAfter })
    await page.locator('.settings-scroll').evaluate(element => { element.scrollTop = 0 })
    await screenshot(page, app, 'settings-feedback-800-scale140.png')
    await picker.selectOption('communications')
    await expect(page.locator('#communications')).toBeFocused()
    await expect(page.locator('#communications h2')).toBeInViewport()
    await expect(page.locator('#communications').locator('xpath=ancestor::details')).toHaveAttribute('open', '')
  })
})

test('update and report dialogs share keyboard dismissal and focus restoration', async () => {
  await withApp(createMockChronicleBackend(), async (page, app) => {
    await resize(app, 800, 600); await preferences(page, { uiScale: 1.25 })
    const config = page.locator('button[aria-controls="page-settings"]')
    await config.click(); await config.focus()
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].webContents.send('update-downloaded', { version: '9.9.9', releaseNotes: '- A local test release.' }))
    const update = page.getByRole('dialog', { name: catalog('en').update.title })
    await expect(update).toBeVisible()
    for (let i = 0; i < 5; i++) { await page.keyboard.press('Tab'); expect(await update.evaluate(element => element.contains(document.activeElement))).toBe(true) }
    await fits(page, ['[role=dialog]'])
    await page.keyboard.press('Escape'); await expect(update).toHaveCount(0); await expect(config).toBeFocused()
    await page.getByRole('combobox', { name: catalog('en').visualQuality.settingsSections, exact: true }).selectOption('diagnostics')
    const reportButton = page.getByRole('button', { name: catalog('en').common.reportIssue, exact: true })
    await reportButton.click()
    const report = page.getByRole('dialog', { name: catalog('en').report.title })
    await expect(report).toBeVisible()
    await page.keyboard.press('Shift+Tab')
    expect(await report.evaluate(element => element.contains(document.activeElement))).toBe(true)
    await page.keyboard.press('Escape'); await expect(report).toHaveCount(0); await expect(reportButton).toBeFocused()
  })
})

test('tab transitions preserve text geometry and record frame timings', async () => {
  await withApp(createMockChronicleBackend({ chapters: [chapter(1)] }), async (page, app) => {
    await resize(app, 1280, 900); await preferences(page, {})
    const metrics = await page.evaluate(async () => {
      const shifts = [], longTasks = [], intervals = [], samples = []
      const layoutObserver = new PerformanceObserver(list => shifts.push(...list.getEntries().map(entry => ({ value: entry.value, afterInput: entry.hadRecentInput }))))
      const taskObserver = new PerformanceObserver(list => longTasks.push(...list.getEntries().map(entry => entry.duration)))
      layoutObserver.observe({ type: 'layout-shift' }); taskObserver.observe({ type: 'longtask' })
      const main = document.querySelector('main').getBoundingClientRect()
      for (const tab of ['chronicle', 'settings', 'chat', 'chronicle', 'settings', 'chat']) {
        document.querySelector(`button[aria-controls="page-${tab}"]`).click()
        await new Promise(resolve => {
          const started = performance.now(); let last = started
          const frame = now => {
            intervals.push(now - last); last = now
            const bounds = document.querySelector('main').getBoundingClientRect()
            samples.push({ tab, delta: Math.max(Math.abs(bounds.x - main.x), Math.abs(bounds.y - main.y), Math.abs(bounds.width - main.width), Math.abs(bounds.height - main.height)), transform: getComputedStyle(document.querySelector(`#page-${tab}`)).transform })
            if (now - started < 300) requestAnimationFrame(frame); else resolve()
          }
          requestAnimationFrame(frame)
        })
      }
      layoutObserver.disconnect(); taskObserver.disconnect()
      const sorted = intervals.filter(value => value > 0).sort((a, b) => a - b)
      return { samples, layoutShifts: shifts, longTasksMs: longTasks, frameCount: sorted.length, p95FrameMs: sorted[Math.floor(sorted.length * 0.95)], maxFrameMs: sorted.at(-1) }
    })
    expect(metrics.samples.every(sample => sample.delta <= 1 && sample.transform === 'none')).toBe(true)
    await fs.mkdir(proof, { recursive: true })
    await fs.writeFile(path.join(proof, 'motion-profile.json'), JSON.stringify(metrics, null, 2))
  })
})
