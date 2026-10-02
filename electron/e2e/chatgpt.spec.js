const fs = require('fs/promises')
const os = require('os')
const path = require('path')
const { test, expect, _electron: electron } = require('@playwright/test')
const { createMockChronicleBackend } = require('./helpers/mockBackend')
const { getElectronLaunchArgs } = require('./helpers/electronLaunch')
const electronDir = path.resolve(__dirname, '..')
const screenshots = path.resolve(electronDir, '..', 'artifacts', 'chatgpt')
async function launch(port, userData, onboarding = true, extraEnv = {}) {
  const saves = path.join(userData, 'empty-saves')
  await fs.mkdir(saves, { recursive: true })
  return electron.launch({ args: getElectronLaunchArgs(path.join(electronDir, 'main.js')), env: {
    ...process.env, NODE_ENV: 'test', E2E: '1', E2E_CHATGPT_MOCK: '1', E2E_USER_DATA_DIR: userData,
    E2E_SAVE_DIR: saves, E2E_ONBOARDING_COMPLETE: onboarding ? '1' : '0', E2E_BACKEND_CONFIGURED: '1', E2E_SKIP_BACKEND_AUTOSTART: '1',
    E2E_HEALTH_CHECK_INTERVAL_MS: '200', STELLARIS_API_PORT: String(port), STELLARIS_API_TOKEN: 'e2e-token',
    ...extraEnv,
  } })
}
async function screenshot(page, name) {
  await fs.mkdir(screenshots, { recursive: true })
  await page.waitForFunction(() => {
    let node = document.querySelector('[data-onboarding-frame-step]')
    while (node) {
      const matrix = new DOMMatrixReadOnly(getComputedStyle(node).transform)
      if (Math.abs(matrix.m41) > 0.2 || Math.abs(matrix.m42) > 0.2 || Math.abs(matrix.m11 - 1) > 0.001) return false
      node = node.parentElement
    }
    return true
  })
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
  const connection = page.getByTestId('chatgpt-connection')
  if (name.includes('settings') || name.includes('advanced')) await connection.scrollIntoViewIfNeeded()
  await page.screenshot({ path: path.join(screenshots, name), animations: 'disabled' })
}

test('connects, automatically verifies, saves the shared provider, and restores after restart', async () => {
  const backend = createMockChronicleBackend({ advisorProvider: 'chatgpt' })
  const port = await backend.start()
  const userData = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-chatgpt-e2e-'))
  let app = await launch(port, userData)
  try {
    let page = await app.firstWindow()
    await page.getByRole('button', { name: /Config/i }).click()
    await page.getByRole('button', { name: /^ChatGPT/ }).click()
    await expect(page.getByRole('button', { name: 'Continue with ChatGPT', exact: true })).toBeVisible()
    await expect(page.getByLabel('API KEY', { exact: true })).toHaveCount(0)
    await screenshot(page, '01-settings-connect.png')
    await page.getByRole('button', { name: 'Continue with ChatGPT', exact: true }).click()
    const welcome = page.getByRole('dialog', { name: 'Using your ChatGPT plan' })
    await expect(welcome).toBeVisible()
    await screenshot(page, '02-first-use.png')
    await welcome.getByRole('button', { name: 'Got it' }).click()
    await expect(page.getByText('ChatGPT connected', { exact: true })).toBeVisible()
    await expect(page.getByText(/UNSAVED CHANGES/i)).toHaveCount(0)
    await screenshot(page, '03-settings-connected.png')
    const status = await page.evaluate(() => window.electronAPI.chatgpt.status())
    expect(status.status.ready).toBe(true)
    expect(JSON.stringify(status)).not.toContain('fixture-access')
    const settings = await page.evaluate(() => window.electronAPI.getSettings())
    expect(settings.advisorProvider).toBe('chatgpt')
    expect(settings.advisorModel).toBe('fixture-strategist')
    const bridgeConfig = await app.evaluate((_electron, entrypoint) => {
      const env = process.getBuiltinModule('module').createRequire(entrypoint)(entrypoint).buildBackendEnv({ advisorProvider: 'chatgpt', advisorModel: 'fixture-strategist' })
      return { provider: env.STELLARIS_ADVISOR_PROVIDER, model: env.STELLARIS_ADVISOR_MODEL,
        localBridge: /^http:\/\/127\.0\.0\.1:\d+$/.test(env.STELLARIS_CHATGPT_BRIDGE_URL),
        hasLocalCapability: !!env.STELLARIS_CHATGPT_BRIDGE_TOKEN,
        hasProviderKey: !!env.STELLARIS_ADVISOR_API_KEY,
        containsOAuthToken: JSON.stringify(env).includes('fixture-access'),
      }
    }, path.join(electronDir, 'main.js'))
    expect(bridgeConfig).toEqual({ provider: 'chatgpt', model: 'fixture-strategist', localBridge: true,
      hasLocalCapability: true, hasProviderKey: false, containsOAuthToken: false })
    // Model choice is visible directly; account management stays collapsed.
    await expect(page.getByRole('combobox', { name: 'ChatGPT model', exact: true })).toHaveValue('fixture-strategist')
    await expect(page.getByLabel('ChatGPT account')).not.toBeVisible()
    await page.getByRole('combobox', { name: 'ChatGPT model', exact: true }).selectOption('fixture-strategist-fast')
    await expect.poll(async () => (await page.evaluate(() => window.electronAPI.getSettings())).advisorModel).toBe('fixture-strategist-fast')
    await screenshot(page, '04-advanced.png')
    await app.close(); app = await launch(port, userData)
    page = await app.firstWindow()
    await page.getByRole('button', { name: /Config/i }).click()
    await expect(page.getByRole('button', { name: /^ChatGPT/ })).toHaveAttribute('aria-pressed', 'true')
    if (settings.secretStorageAvailable) {
      await expect(page.getByText('ChatGPT connected', { exact: true })).toBeVisible()
      await expect(page.getByRole('combobox', { name: 'ChatGPT model', exact: true })).toHaveValue('fixture-strategist-fast')
      await expect(page.getByRole('dialog', { name: 'Using your ChatGPT plan' })).toHaveCount(0)
      await page.getByRole('button', { name: /◈\s*Advisor/i }).click()
      await expect(page.getByRole('combobox', { name: 'ChatGPT model', exact: true })).toBeVisible()
      await expect(page.getByRole('combobox', { name: 'ChatGPT model', exact: true })).toHaveValue('fixture-strategist-fast')
    } else await expect(page.getByRole('button', { name: 'Continue with ChatGPT', exact: true })).toBeVisible()
  } finally { await app?.close(); await backend.stop(); await fs.rm(userData, { recursive: true, force: true }) }
})

test('offers simple onboarding and retains another-provider setup', async () => {
  const backend = createMockChronicleBackend()
  const port = await backend.start()
  const userData = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-chatgpt-onboarding-'))
  const app = await launch(port, userData, false)
  try {
    const page = await app.firstWindow()
    await page.getByRole('button', { name: /Get started/i }).click()
    await expect(page.getByRole('button', { name: 'Continue with ChatGPT', exact: true })).toBeVisible()
    await screenshot(page, '05-onboarding.png')
    await page.getByRole('button', { name: /Gemini API key/ }).click()
    await expect(page.getByPlaceholder('AIza...')).toBeVisible()
    await page.getByRole('button', { name: 'Back', exact: true }).click()
    await page.getByRole('button', { name: 'Continue with ChatGPT', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Find your saves' })).toBeVisible()
    await expect(page.getByText('ChatGPT connected', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: /Set up later/i }).click()
    await expect(page.getByRole('dialog', { name: 'Using your ChatGPT plan' })).toBeVisible()
    await page.getByRole('button', { name: 'Got it' }).click()
    expect((await page.evaluate(() => window.electronAPI.getSettings())).advisorProvider).toBe('chatgpt')
  } finally { await app.close(); await backend.stop(); await fs.rm(userData, { recursive: true, force: true }) }
})

test('usage limits keep the question and open ChatGPT usage settings', async () => {
  const backend = createMockChronicleBackend({ advisorProvider: 'chatgpt', chatError: {
    status: 429, code: 'CHATGPT_LIMIT', error: 'subscription_sharing_usage_limit_exceeded',
  } })
  const port = await backend.start()
  const userData = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-chatgpt-limit-'))
  const app = await launch(port, userData)
  try {
    const page = await app.firstWindow()
    await app.evaluate(({ shell }) => { global.__chatgptOpened = []; shell.openExternal = async value => { global.__chatgptOpened.push(value) } })
    const input = page.getByPlaceholder('HOW CAN WE HELP?')
    await expect(input).toBeEnabled()
    await input.fill('How should we prepare for the next war?')
    await page.getByRole('button', { name: 'SEND', exact: true }).click()
    await expect(page.getByText('ChatGPT usage limit reached.', { exact: false })).toBeVisible()
    await expect(input).toHaveValue('How should we prepare for the next war?')
    await expect(page.getByText('Using ChatGPT plan', { exact: true }).first()).toBeVisible()
    await screenshot(page, '06-usage-limit.png')
    await page.getByRole('button', { name: 'Manage usage', exact: true }).first().click()
    expect(await app.evaluate(() => global.__chatgptOpened)).toContain('https://chatgpt.com/settings/usage')
  } finally { await app.close(); await backend.stop(); await fs.rm(userData, { recursive: true, force: true }) }
})

test('cached Chronicle stays readable after a ChatGPT limit', async () => {
  const backend = createMockChronicleBackend({ advisorProvider: 'chatgpt' })
  const port = await backend.start()
  const userData = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-chatgpt-chronicle-'))
  const app = await launch(port, userData)
  try {
    const page = await app.firstWindow()
    await page.getByRole('button', { name: /Chronicle/i }).click()
    await expect(page.getByText('Old teaser.', { exact: true })).toBeVisible()
    await backend.waitForChronicleRequest(request => request.chapter_only === false)
    backend.setChronicleError({ status: 429, code: 'CHATGPT_LIMIT', error: 'subscription_sharing_usage_limit_exceeded' })
    backend.advanceCampaign()
    await expect(page.getByText('ChatGPT usage limit reached.', { exact: false })).toBeVisible()
    await expect(page.getByText('Old teaser.', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Manage usage', exact: true }).first()).toBeVisible()
    await screenshot(page, '07-chronicle-limit.png')
  } finally { await app.close(); await backend.stop(); await fs.rm(userData, { recursive: true, force: true }) }
})
