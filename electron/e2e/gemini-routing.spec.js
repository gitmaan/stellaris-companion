const fs = require('node:fs/promises')
const os = require('node:os')
const path = require('node:path')
const { test, expect, _electron: electron } = require('@playwright/test')
const { createMockChronicleBackend } = require('./helpers/mockBackend')
const { getElectronLaunchArgs } = require('./helpers/electronLaunch')

async function withApp(saved, run) {
  const backend = createMockChronicleBackend({
    chatResponse: 'Check current Trade before committing to imports.',
    chatModel: 'Gemini 3.5 Flash-Lite',
    chatModelRouting: { fallback: true, reason: 'daily_quota', final_model: 'gemini-3.5-flash-lite',
      final_model_display: 'Gemini 3.5 Flash-Lite',
      notice: 'Gemini 3.8 Flash quota is exhausted. Routing via Gemini 3.5 Flash-Lite.' },
  })
  const port = await backend.start()
  const cwd = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-gemini-routing-'))
  let app
  try {
    if (saved) await fs.writeFile(path.join(cwd, 'settings.json'), JSON.stringify(saved))
    const launch = async () => {
      app = await electron.launch({ args: getElectronLaunchArgs(path.resolve(__dirname, '../main.js')),
        env: { ...process.env, NODE_ENV: 'test', E2E: '1', E2E_ONBOARDING_COMPLETE: '1',
          E2E_BACKEND_CONFIGURED: '1', E2E_SKIP_BACKEND_AUTOSTART: '1',
          E2E_FAKE_SECURE_STORAGE: '1', E2E_USER_DATA_DIR: cwd,
          STELLARIS_API_PORT: String(port), STELLARIS_API_TOKEN: 'routing-test' } })
      const page = await app.firstWindow()
      await page.waitForLoadState('domcontentloaded')
      await expect(page.locator('#page-chat textarea')).toBeEnabled()
      return page
    }
    await run(await launch(), async () => { await app.close(); return launch() })
  } finally {
    await app?.close()
    await backend.stop()
    await fs.rm(cwd, { recursive: true, force: true })
  }
}

test('new Gemini setup prefers Flash, shows Lite fallback, and persists an explicit Lite choice', async ({}, info) => {
  await withApp(undefined, async (page, restart) => {
    expect((await page.evaluate(() => window.electronAPI.getSettings())).modelRoutingMode).toBe('quality_first')
    await page.locator('#page-chat textarea').fill('How should I handle imports?')
    await page.locator('#page-chat textarea').press('Enter')
    await expect(page.getByText('Routing via Gemini 3.5 Flash-Lite.', { exact: true })).toBeVisible()
    await expect(page.getByText('ROUTING VIA Gemini 3.5 Flash-Lite', { exact: true })).toBeHidden()
    await page.screenshot({ path: info.outputPath('visible-lite-fallback.png') })
    await page.getByRole('button', { name: /Config/i }).click()
    await expect(page.locator('#page-settings')).toHaveCSS('opacity', '1')
    const flash = page.getByRole('button', { name: 'Set Gemini model preference to Flash', exact: true })
    const lite = page.getByRole('button', { name: 'Set Gemini model preference to Flash-Lite', exact: true })
    await expect(flash).toHaveAttribute('aria-pressed', 'true')
    await expect(flash).toContainText('RECOMMENDED FOR ADVICE')
    await lite.click()
    await expect(lite).toHaveAttribute('aria-pressed', 'true')
    await page.screenshot({ path: info.outputPath('gemini-model-choice.png') })
    page = await restart()
    expect((await page.evaluate(() => window.electronAPI.getSettings())).modelRoutingMode).toBe('conserve')
    await page.getByRole('button', { name: /Config/i }).click()
    await expect(page.getByRole('button', { name: 'Set Gemini model preference to Flash-Lite', exact: true })).toHaveAttribute('aria-pressed', 'true')
  })
})

for (const saved of [
  { advisorProvider: 'gemini', advisorModel: 'gemini-3.5-flash-lite' },
  { advisorProvider: 'gemini', advisorModel: 'gemini-3.8-flash', modelRoutingMode: 'quality_first' },
]) {
  test(`upgrade preserves ${saved.modelRoutingMode || 'legacy Lite'} and explicit model across restart`, async () => {
    await withApp(saved, async (page, restart) => {
      const expected = { ...saved, modelRoutingMode: saved.modelRoutingMode || 'conserve' }
      expect(await page.evaluate(() => window.electronAPI.getSettings())).toMatchObject(expected)
      page = await restart()
      expect(await page.evaluate(() => window.electronAPI.getSettings())).toMatchObject(expected)
    })
  })
}
