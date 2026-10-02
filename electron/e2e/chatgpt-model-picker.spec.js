const fs = require('fs/promises')
const os = require('os')
const path = require('path')
const { test, expect, _electron: electron } = require('@playwright/test')
const { createMockChronicleBackend } = require('./helpers/mockBackend')
const { getElectronLaunchArgs } = require('./helpers/electronLaunch')
const electronDir = path.resolve(__dirname, '..')
const proofDir = path.resolve(electronDir, '../artifacts/chatgpt-picker-polish-2026-10-02')
const picker = page => page.getByRole('combobox', { name: 'ChatGPT model', exact: true })

async function fixture(options = {}) {
  const backend = createMockChronicleBackend({ advisorProvider: 'chatgpt', ...options })
  const port = await backend.start()
  const userData = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-model-picker-'))
  const saves = path.join(userData, 'saves')
  await fs.mkdir(saves)
  await fs.writeFile(path.join(userData, 'settings.json'), JSON.stringify({ saveDir: saves }))
  const app = await electron.launch({ args: getElectronLaunchArgs(path.join(electronDir, 'main.js')), env: {
    ...process.env, NODE_ENV: 'test', E2E: '1', E2E_CHATGPT_MOCK: '1', E2E_CHATGPT_MODEL_CATALOG: 'current',
    E2E_USER_DATA_DIR: userData, E2E_SAVE_DIR: saves, E2E_ONBOARDING_COMPLETE: '1', E2E_BACKEND_CONFIGURED: '1',
    E2E_SKIP_BACKEND_AUTOSTART: '1', E2E_HEALTH_CHECK_INTERVAL_MS: '200', STELLARIS_API_PORT: String(port), STELLARIS_API_TOKEN: 'e2e-token',
  } })
  const page = await app.firstWindow()
  await page.getByRole('button', { name: /Config/i }).click()
  await page.getByRole('button', { name: /^ChatGPT/ }).click()
  await page.getByRole('button', { name: 'Continue with ChatGPT', exact: true }).click()
  await page.getByRole('dialog', { name: 'Using your ChatGPT plan' }).getByRole('button', { name: 'Got it' }).click()
  await expect(picker(page)).toHaveValue('gpt-5.6-terra')
  return { app, page, backend, userData, close: async () => {
    await app.close(); await backend.stop(); await fs.rm(userData, { recursive: true, force: true })
  } }
}
async function shot(page, name) {
  await fs.mkdir(proofDir, { recursive: true })
  await page.screenshot({ path: path.join(proofDir, name), animations: 'disabled' })
}

test('shared picker switches in place, retains provider drafts and conversation, and keeps Chronicle in sync', async () => {
  const f = await fixture()
  const { page, app } = f
  try {
    await expect(picker(page).locator('option')).toHaveText([
      'GPT-5.6-Terra · Recommended', 'GPT-5.6-Luna · Lower usage', 'GPT-6-Astra', 'GPT-5.6-Sol',
    ])
    await expect(picker(page).locator('optgroup')).toHaveAttribute('label', 'More models')
    await expect(page.getByText('Advisor and Chronicle are ready to use your ChatGPT plan.', { exact: true })).not.toBeVisible()
    await page.getByRole('button', { name: /Gemini.*easiest setup/i }).click()
    await page.getByLabel('GEMINI KEY', { exact: true }).fill('unsaved-provider-key')
    await page.getByRole('button', { name: /◈\s*Advisor/i }).click()
    const input = page.getByPlaceholder('HOW CAN WE HELP?')
    await input.fill('Give me a concise campaign priority.')
    await page.getByRole('button', { name: 'SEND', exact: true }).click()
    await expect(page.getByText('Mock strategic response.', { exact: true })).toBeVisible()
    await input.fill('Keep this unsent question.')
    await picker(page).selectOption('gpt-5.6-luna')
    await expect(page.getByRole('status').getByText('Model updated', { exact: true })).toBeVisible()
    await expect(page.getByText('Mock strategic response.', { exact: true })).toBeVisible()
    await expect(input).toHaveValue('Keep this unsent question.')
    await expect(page.getByRole('heading', { name: 'CONFIGURATION', exact: true })).not.toBeVisible()
    expect((await page.evaluate(() => window.electronAPI.getSettings())).advisorModel).toBe('gpt-5.6-luna')
    await shot(page, '01-advisor-inline.png')
    await page.getByRole('button', { name: /Chronicle/i }).click()
    await expect(picker(page)).toHaveValue('gpt-5.6-luna')
    await page.getByRole('button', { name: /Config/i }).click()
    await expect(page.getByLabel('GEMINI KEY', { exact: true })).toHaveValue('unsaved-provider-key')
    await page.getByRole('button', { name: /^ChatGPT/ }).click()
    await expect(picker(page)).toHaveValue('gpt-5.6-luna')
    await picker(page).selectOption('gpt-6-astra')
    await expect(picker(page)).toHaveValue('gpt-6-astra')
    expect((await page.evaluate(() => window.electronAPI.getSettings())).advisorModel).toBe('gpt-6-astra')
    await expect(page.getByText('UNSAVED CHANGES', { exact: true })).toHaveCount(0)
    await picker(page).selectOption('gpt-5.6-terra')
    await expect(picker(page)).toHaveValue('gpt-5.6-terra')
    await page.getByTestId('chatgpt-connection').scrollIntoViewIfNeeded()
    await expect(page.getByText('Model updated', { exact: true })).toHaveCount(0)
    await shot(page, '02-settings.png')
  } finally { await f.close() }
})

test('model saves show success only when persisted, and a failed selection retains the previous model', async () => {
  const f = await fixture()
  const { page, app } = f
  try {
    await app.evaluate(() => { globalThis.__chatgptHoldCatalog = true })
    await picker(page).selectOption('gpt-5.6-luna')
    await expect(picker(page)).toBeDisabled()
    await expect(page.getByText('Checking your connection…', { exact: true })).not.toBeVisible()
    await expect(page.getByText('Model updated', { exact: true })).not.toBeVisible()
    await app.evaluate(() => { globalThis.__chatgptHoldCatalog = false; globalThis.__chatgptReleaseCatalog() })
    await expect(picker(page)).toHaveValue('gpt-5.6-luna')
    await expect(page.getByText('Model updated', { exact: true })).toBeVisible()
    await expect(picker(page)).toBeEnabled()
    await app.evaluate(() => { globalThis.__chatgptFailCatalog = true })
    await picker(page).selectOption('gpt-5.6-terra')
    await expect(page.getByRole('alert').getByText('ChatGPT is temporarily unavailable.', { exact: false })).toBeVisible()
    await expect(picker(page)).toHaveValue('gpt-5.6-luna')
    expect((await page.evaluate(() => window.electronAPI.getSettings())).advisorModel).toBe('gpt-5.6-luna')
    await app.evaluate(() => { globalThis.__chatgptFailCatalog = false })
    await picker(page).selectOption('gpt-5.6-terra')
    await expect(picker(page)).toHaveValue('gpt-5.6-terra')
  } finally { await f.close() }
})

test('picker is keyboard reachable, disables during requests, and fits the minimum window', async () => {
  let release
  const pending = new Promise(resolve => { release = resolve })
  const f = await fixture({ onChat: async () => { await pending; return 'Reply completed.' } })
  const { page, app, backend } = f
  try {
    await page.getByRole('button', { name: /◈\s*Advisor/i }).click()
    await page.getByRole('button', { name: 'Manage usage', exact: true }).focus()
    await page.keyboard.press('Shift+Tab')
    await expect(picker(page)).toBeFocused()
    await page.keyboard.press('Tab')
    await expect(page.getByRole('button', { name: 'Manage usage', exact: true })).toBeFocused()
    await picker(page).selectOption('gpt-5.6-luna')
    await expect(picker(page)).toHaveValue('gpt-5.6-luna')
    await page.getByPlaceholder('HOW CAN WE HELP?').fill('Keep the current reply safe.')
    await page.getByRole('button', { name: 'SEND', exact: true }).click()
    await expect.poll(() => backend.getChatRequests().length).toBe(1)
    await expect(picker(page)).toBeDisabled()
    release()
    await expect(page.getByText('Reply completed.', { exact: true })).toBeVisible()
    await expect(picker(page)).toBeEnabled()
    await app.evaluate(({ BrowserWindow }) => { const window = BrowserWindow.getAllWindows()[0]; window.setFullScreen(false); window.setSize(800, 600) })
    await expect.poll(() => page.evaluate(() => window.innerWidth)).toBe(800)
    await expect(picker(page)).toBeInViewport()
    const bounds = await picker(page).boundingBox()
    expect(bounds.x).toBeGreaterThanOrEqual(0)
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(800)
    expect(bounds.y + bounds.height).toBeLessThanOrEqual(600)
    await expect(page.getByText('Model updated', { exact: true })).toHaveCount(0)
    await shot(page, '03-advisor-small.png')
    await page.getByRole('button', { name: /Config/i }).click()
    await page.getByTestId('chatgpt-connection').scrollIntoViewIfNeeded()
    await expect(picker(page)).toBeInViewport()
    await shot(page, '04-settings-small.png')
  } finally { release(); await f.close() }
})
