const fs = require('node:fs/promises')
const os = require('node:os')
const path = require('node:path')
const { test, expect, _electron: electron } = require('@playwright/test')
const { createMockChronicleBackend } = require('./helpers/mockBackend')
const { getElectronLaunchOptions, assertPackagedApp } = require('./helpers/electronLaunch')
const zh = require('../renderer/i18n/locales/zh-Hans/common.json')

async function withApp(run) {
  const backend = createMockChronicleBackend({ chatResponse: '这是一条完整的测试回复。舰队守护边境，研究者追踪古老的信号。最后一句也应该清晰可见。' })
  const port = await backend.start()
  const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-feedback-'))
  let app
  try {
    await fs.writeFile(path.join(profile, 'settings.json'), JSON.stringify({ language: 'zh-Hans', hasCompletedOnboarding: true }))
    app = await electron.launch({ ...getElectronLaunchOptions(path.resolve(__dirname, '../main.js')), env: {
      ...process.env, NODE_ENV: 'test', E2E: '1', E2E_BACKEND_CONFIGURED: '1', E2E_SKIP_BACKEND_AUTOSTART: '1', E2E_FAKE_SECURE_STORAGE: '1',
      E2E_USER_DATA_DIR: profile, STELLARIS_API_PORT: String(port), STELLARIS_API_TOKEN: 'feedback-fixture',
    } })
    await assertPackagedApp(app)
    const page = await app.firstWindow()
    // Deny all renderer network traffic; the one feedback request below is fulfilled locally.
    await page.route(/^https?:\/\//, route => route.abort())
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    await page.locator('#page-chat textarea').fill('下一步应该做什么？')
    await page.locator('#page-chat button[type=submit]').click()
    await page.getByRole('button', { name: zh.chat.message.report, exact: true }).click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await page.getByPlaceholder(zh.report.descriptionPlaceholder).fill('文字不全，显示有问题')
    await app.evaluate(({ BrowserWindow, clipboard }) => {
      // Keep the renderer/preload/main Copy path, without touching the host clipboard.
      globalThis.feedbackCopiedText = ''
      clipboard.writeText = text => { globalThis.feedbackCopiedText = text }
      const contents = BrowserWindow.getAllWindows()[0].webContents
      globalThis.feedbackCaptures = []
      globalThis.originalCapture = contents.capturePage.bind(contents)
      contents.capturePage = async (...args) => {
        globalThis.feedbackCaptures.push(await contents.executeJavaScript(`(() => {
          const panel = document.querySelector('[aria-labelledby="report-issue-title"]');
          return { hidden: getComputedStyle(panel.closest('[data-overlay]')).visibility, panelHidden: getComputedStyle(panel).visibility, backgroundInert: document.getElementById('root').inert };
        })()`))
        return globalThis.originalCapture(...args)
      }
    })
    await run(page, app)
    expect(errors).toEqual([])
  } finally {
    if (app) await app.close().catch(() => {})
    await backend.stop()
    await fs.rm(profile, { recursive: true, force: true })
  }
}

test('feedback previews the unobscured screen and submits exactly the opted-in preview', async ({}, testInfo) => {
  await withApp(async (page, app) => {
    const submissions = []
    // Always intercept before enabling Submit. These fixture reports never leave the test.
    await page.route('https://feedback.galacticfilingcabinet.com/**', async route => {
      submissions.push(route.request().postDataJSON())
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ issueUrl: 'https://example.test/fixture-report' }) })
    })
    expect(await app.evaluate(() => globalThis.feedbackCaptures)).toEqual([])
    await page.getByLabel(zh.report.includeScreenshot, { exact: true }).check()
    const preview = page.locator('[data-feedback-preview] img')
    await expect(preview).toBeVisible()
    await expect(page.getByLabel(zh.report.includeScreenshot, { exact: true })).toBeFocused()
    expect(await preview.evaluate(image => image.complete && image.naturalWidth > 0)).toBe(true)
    const image = await preview.getAttribute('src')
    expect(await app.evaluate(() => globalThis.feedbackCaptures)).toEqual([{ hidden: 'hidden', panelHidden: 'hidden', backgroundInert: true }])
    await fs.writeFile(testInfo.outputPath('feedback-unobscured.png'), Buffer.from(image.split(',')[1], 'base64'))
    await page.getByLabel(zh.report.includeDiagnostics, { exact: true }).check()
    await page.getByRole('button', { name: zh.report.copy, exact: true }).click()
    // Copy gathers native/backend diagnostics before invoking the clipboard IPC.
    await expect.poll(() => app.evaluate(() => globalThis.feedbackCopiedText)).toContain('"page": "chat"')
    const markdown = await app.evaluate(() => globalThis.feedbackCopiedText)
    expect(markdown).toContain('"language": "zh-Hans"')
    expect(markdown).toContain('"zoomFactor": 1')
    const submit = page.getByRole('button', { name: zh.report.submit, exact: true })
    if (process.env.E2E_FEEDBACK_SUBMIT === '1') await expect(submit).toBeEnabled()
    // Builds without a report endpoint can still exercise preview and clipboard behavior.
    if (await submit.isEnabled()) {
      await submit.click()
      await expect.poll(() => submissions.length).toBe(1)
      expect(submissions[0].context.screenshot).toBe(image)
      expect(submissions[0].context.diagnostics.display.language).toBe('zh-Hans')
      expect(submissions[0].context.diagnostics.display.displayScaleFactor).toBeGreaterThan(0)
      expect(submissions[0].context.llm).toBeUndefined()
      expect(submissions[0].context.backend_log_tail).toBeUndefined()
      expect(await app.evaluate(() => globalThis.feedbackCaptures.length)).toBe(1)
    }
    await page.getByLabel(zh.report.includeScreenshot, { exact: true }).uncheck()
    await page.getByLabel(zh.report.includeDiagnostics, { exact: true }).uncheck()
    await expect(preview).toHaveCount(0)
    if (await submit.isEnabled()) {
      await submit.click()
      await expect.poll(() => submissions.length).toBe(2)
      expect(submissions[1].context.screenshot).toBeUndefined()
      expect(submissions[1].context.diagnostics).toBeUndefined()
    }
    await page.getByRole('button', { name: zh.report.close, exact: true }).click()
    await expect(page.getByRole('dialog')).toHaveCount(0)
    expect(await page.locator('#root').evaluate(root => root.inert)).toBe(false)
  })
})

test('capture errors restore the dialog and allow retry without losing the report', async () => {
  await withApp(async (page, app) => {
    await app.evaluate(({ BrowserWindow }) => { BrowserWindow.getAllWindows()[0].webContents.capturePage = async () => { throw new Error('Fixture capture failure') } })
    await page.getByLabel(zh.report.includeScreenshot, { exact: true }).check()
    await expect(page.getByRole('dialog')).toBeVisible()
    await expect(page.getByText(zh.report.screenshotFailed)).toBeVisible()
    await expect(page.getByPlaceholder(zh.report.descriptionPlaceholder)).toHaveValue('文字不全，显示有问题')
    await expect(page.getByRole('button', { name: zh.report.submit, exact: true })).toBeDisabled()
    await app.evaluate(({ BrowserWindow }) => { BrowserWindow.getAllWindows()[0].webContents.capturePage = globalThis.originalCapture })
    await page.getByRole('button', { name: zh.report.retakeScreenshot, exact: true }).click()
    await expect(page.locator('[data-feedback-preview] img')).toBeVisible()
    await page.getByRole('button', { name: zh.report.close, exact: true }).click()
    await page.getByRole('button', { name: zh.chat.message.report, exact: true }).click()
    await expect(page.getByLabel(zh.report.includeScreenshot, { exact: true })).not.toBeChecked()
    await expect(page.locator('[data-feedback-preview] img')).toHaveCount(0)
  })
})
