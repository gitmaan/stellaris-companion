const fs = require('node:fs/promises')
const path = require('node:path')
const os = require('node:os')
const { test, expect, _electron: electron } = require('@playwright/test')
const { createMockChronicleBackend } = require('./helpers/mockBackend')
const { getElectronLaunchArgs } = require('./helpers/electronLaunch')
const en = require('../renderer/i18n/locales/en/common.json')
const ja = require('../renderer/i18n/locales/ja/common.json')
const dist = path.resolve(__dirname, '../renderer/dist')

async function withApp(run, { backend = createMockChronicleBackend(), settings = {}, extraEnv = {} } = {}) {
  const port = await backend.start()
  const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-renderer-perf-e2e-'))
  let app
  try {
    await fs.writeFile(path.join(profile, 'settings.json'), JSON.stringify(settings))
    app = await electron.launch({
      args: getElectronLaunchArgs(path.resolve(__dirname, '../main.js')),
      env: { ...process.env, NODE_ENV: 'test', E2E: '1', E2E_ONBOARDING_COMPLETE: '1', E2E_BACKEND_CONFIGURED: '1', E2E_SKIP_BACKEND_AUTOSTART: '1', E2E_FAKE_SECURE_STORAGE: '1', E2E_HEALTH_CHECK_INTERVAL_MS: '200', E2E_USER_DATA_DIR: profile, STELLARIS_API_PORT: String(port), STELLARIS_API_TOKEN: 'renderer-perf-test-token', ...extraEnv },
    })
    const page = await app.firstWindow()
    await expect(page.locator('#page-chat textarea')).toBeEnabled()
    await run(page, app, backend)
  } finally {
    if (app) await app.close()
    await backend.stop()
    await fs.rm(profile, { recursive: true, force: true })
  }
}

async function loadedScripts(app, page) {
  const names = new Set()
  const cdp = await app.context().newCDPSession(page)
  cdp.on('Debugger.scriptParsed', script => {
    if (script.url.startsWith('file:') && script.url.endsWith('.js')) names.add(path.basename(script.url))
  })
  await cdp.send('Debugger.enable')
  await cdp.send('Debugger.disable')
  await cdp.detach()
  return names
}

async function manifest() {
  return JSON.parse(await fs.readFile(path.join(dist, '.vite/manifest.json'), 'utf8'))
}

test('a restored language becomes ready from the initial health result before another poll', async () => {
  // A sixty-second poll cannot satisfy the normal ten-second assertion timeout.
  // This exercises the preload cache with an asynchronously loaded language.
  await withApp(async page => {
    await expect(page.locator('html')).toHaveAttribute('lang', 'ja')
    await expect(page.locator('#page-chat textarea')).toBeEnabled()
    await page.locator('button[aria-controls="page-settings"]').click()
    await expect(page.getByLabel(ja.settings.language, { exact: true })).toHaveValue('ja')
  }, { settings: { language: 'ja' }, extraEnv: { E2E_HEALTH_CHECK_INTERVAL_MS: '60000' } })
})

test('startup defers feature pages and retains drafts and Settings state after visiting', async () => {
  await withApp(async (page, app) => {
    const chunks = await manifest()
    const scripts = await loadedScripts(app, page)
    for (const source of ['pages/ChroniclePage.tsx', 'pages/SettingsPage.tsx']) {
      expect(scripts.has(path.basename(chunks[source].file)), source).toBe(false)
    }
    const localeChunks = Object.entries(chunks).filter(([source]) => source.includes('i18n/locales/'))
    for (const [source, chunk] of localeChunks) expect(scripts.has(path.basename(chunk.file)), source).toBe(false)
    await page.locator('#page-chat textarea').fill('Keep this draft while I inspect settings.')
    await page.locator('button[aria-controls="page-settings"]').click()
    await page.getByRole('combobox', { name: en.visualQuality.settingsSections, exact: true }).selectOption('save-data')
    await page.getByRole('button', { name: en.settings.saveData.multiplayerSettings }).click()
    await page.getByLabel(en.settings.saveData.playerNameLabel, { exact: true }).fill('Unsaved captain')
    await page.locator('button[aria-controls="page-chat"]').click()
    await expect(page.locator('#page-chat textarea')).toHaveValue('Keep this draft while I inspect settings.')
    await page.locator('button[aria-controls="page-settings"]').click()
    await expect(page.getByLabel(en.settings.saveData.playerNameLabel, { exact: true })).toHaveValue('Unsaved captain')
    expect((await loadedScripts(app, page)).has(path.basename(chunks['pages/SettingsPage.tsx'].file))).toBe(true)
    expect((await loadedScripts(app, page)).has(path.basename(chunks['pages/ChroniclePage.tsx'].file))).toBe(false)
  })
})

test('a saved language loads its local catalog without loading other languages', async () => {
  await withApp(async (page, app) => {
    await expect(page.locator('html')).toHaveAttribute('lang', 'ja')
    await expect(page.locator('button[aria-controls="page-chat"]')).toContainText(ja.app.tabs.chat)
    const scripts = await loadedScripts(app, page)
    const chunks = await manifest()
    for (const [source, chunk] of Object.entries(chunks).filter(([source]) => source.includes('i18n/locales/'))) {
      expect(scripts.has(path.basename(chunk.file)), source).toBe(source.includes('/ja/'))
    }
  }, { settings: { language: 'ja' } })
})

test('a missing startup catalog falls back to English and a failed switch leaves preferences intact', async () => {
  const chunks = await manifest()
  const catalog = path.join(dist, chunks['i18n/locales/de/common.json'].file)
  const unavailable = `${catalog}.unavailable-for-test`
  await fs.rename(catalog, unavailable)
  try {
    await withApp(async (page) => {
      await expect(page.locator('html')).toHaveAttribute('lang', 'en')
      await expect(page.locator('button[aria-controls="page-chat"]')).toContainText(en.app.tabs.chat)
    }, { settings: { language: 'de' } })
    await withApp(async (page) => {
      await page.locator('button[aria-controls="page-settings"]').click()
      const language = page.getByLabel(en.settings.language, { exact: true })
      await language.selectOption('de')
      await expect(language).toBeEnabled()
      await expect(language).toHaveValue('en')
      await expect(page.locator('html')).toHaveAttribute('lang', 'en')
      expect((await page.evaluate(() => window.electronAPI.getSettings())).language).toBe('en')
    }, { settings: { language: 'en' } })
  } finally {
    await fs.rename(unavailable, catalog)
  }
})

test('background chapter finalization starts even when Chronicle has never been opened', async () => {
  await withApp(async (page, app, backend) => {
    const chunks = await manifest()
    expect((await loadedScripts(app, page)).has(path.basename(chunks['pages/ChroniclePage.tsx'].file))).toBe(false)
    await page.evaluate(() => {
      Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' })
      document.dispatchEvent(new Event('visibilitychange'))
    })
    await backend.waitForChronicleRequest(request => request.chapter_only === true)
    expect(backend.getChronicleRequests().every(request => request.chapter_only)).toBe(true)
    await expect(page.locator('#page-chat')).toHaveAttribute('data-active', 'true')
    backend.advanceCampaign()
    await page.evaluate(() => {
      Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'visible' })
      document.dispatchEvent(new Event('visibilitychange'))
    })
    await page.locator('button[aria-controls="page-chronicle"]').click()
    await expect(page.getByText('Updated after visible refresh.')).toBeVisible()
    await backend.waitForChronicleRequest(request => request.chapter_only === false)
  })
})

test('scrolling and response feedback preserve unchanged Markdown nodes in a long chat', async () => {
  const turns = Array.from({ length: 150 }, (_, i) => ({
    id: `turn-${i}`, request_id: `turn-${i}`, question: `Review expedition ${i}.`,
    answer: `## Expedition ${i}\n\n${'Review the **escort fleet** before departure. '.repeat(5)}\n\n[Official site](https://www.paradoxinteractive.com/).`, created_at: 1700000000 + i, language: 'en',
  }))
  const backend = createMockChronicleBackend({ conversations: [{ id: 'long-chat', save_id: 'save-1', title: 'Expeditions', created_at: 1, updated_at: 2, turns }] })
  await withApp(async (page, app) => {
    await page.addInitScript(() => {
      window.__messageResizeCounts = {}
      const NativeResizeObserver = window.ResizeObserver
      window.ResizeObserver = class extends NativeResizeObserver {
        constructor(callback) {
          super((entries, observer) => {
            for (const entry of entries) {
              const id = entry.target.dataset.messageId
              if (id) window.__messageResizeCounts[id] = (window.__messageResizeCounts[id] || 0) + 1
            }
            callback(entries, observer)
          })
        }
      }
    })
    await page.reload()
    const scroller = page.locator('[data-chat-scroll]')
    await expect(page.locator('[data-message-id="turn-149"]')).toBeVisible()
    await scroller.evaluate(element => { element.scrollTop -= 2000 })
    await page.waitForTimeout(200)
    const id = await scroller.evaluate(element => {
      const bounds = element.getBoundingClientRect()
      const link = Array.from(element.querySelectorAll('.markdown-content a')).find(link => {
        const rect = link.getBoundingClientRect()
        return rect.top > bounds.top + 30 && rect.bottom < bounds.bottom - 30
      })
      if (!link) throw new Error('Expected a visible response link')
      window.__unchangedMessageLink = link
      return link.closest('[data-message-id]').dataset.messageId
    })
    await scroller.evaluate(async element => {
      for (let i = 0; i < 12; i++) {
        element.scrollTop += 1
        await new Promise(resolve => requestAnimationFrame(resolve))
      }
    })
    expect(await page.evaluate(id => document.querySelector(`[data-message-id="${id}"] .markdown-content a`) === window.__unchangedMessageLink, id)).toBe(true)
    // Preserve the user's clipboard while exercising Copy's local feedback state.
    await page.evaluate(() => { window.electronAPI = { ...window.electronAPI, copyToClipboard: async () => ({ success: true }) } })
    const response = page.locator(`[data-message-id="${id}"]`)
    await response.getByRole('button', { name: en.visualQuality.copy, exact: true }).click()
    await expect(response.getByRole('status')).toHaveText(en.visualQuality.copied)
    expect(await page.evaluate(id => document.querySelector(`[data-message-id="${id}"] .markdown-content a`) === window.__unchangedMessageLink, id)).toBe(true)
    const resizeCount = await page.evaluate(id => window.__messageResizeCounts[id] || 0, id)
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setSize(800, 700))
    await expect.poll(() => page.evaluate(id => window.__messageResizeCounts[id] || 0, id)).toBeGreaterThan(resizeCount)
    expect(await page.locator('[data-message-id]').count()).toBeLessThan(40)
  }, { backend })
})

test('returning to a previously viewed history page does not replay message entrances', async () => {
  const turns = Array.from({ length: 151 }, (_, i) => ({
    id: `turn-${i}`, request_id: `turn-${i}`, question: `Question ${i}`,
    answer: `Saved response ${i}.`, created_at: 1700000000 + i, language: 'en',
  }))
  const backend = createMockChronicleBackend({ conversations: [{ id: 'paged-chat', save_id: 'save-1', title: 'Saved history', created_at: 1, updated_at: 2, turns }] })
  await withApp(async page => {
    await page.emulateMedia({ reducedMotion: 'no-preference' })
    await expect(page.locator('[data-message-id="turn-150"]')).toBeVisible()
    await page.getByRole('button', { name: en.continuity.earlierMessages, exact: true }).click()
    await expect(page.locator('[data-message-id="turn-0"]')).toBeVisible()
    await page.evaluate(() => {
      window.__historyEntranceFrames = new Promise(resolve => {
        const values = []
        const started = performance.now()
        let firstSeen
        const sample = () => {
          const message = document.querySelector('[data-message-id="turn-150"]')
          const now = performance.now()
          if (message) {
            firstSeen ??= now
            values.push(Number(getComputedStyle(message).opacity))
          }
          if ((firstSeen !== undefined && now - firstSeen > 250) || now - started > 10000) resolve(values)
          else requestAnimationFrame(sample)
        }
        requestAnimationFrame(sample)
      })
    })
    await page.getByRole('button', { name: en.continuity.latestMessages, exact: true }).click()
    const opacities = await page.evaluate(() => window.__historyEntranceFrames)
    expect(opacities.length).toBeGreaterThan(0)
    expect(Math.min(...opacities)).toBe(1)
  }, { backend })
})
