const fs = require('node:fs/promises')
const os = require('node:os')
const path = require('node:path')
const http = require('node:http')
const { test, expect, _electron: electron } = require('@playwright/test')
const { createMockChronicleBackend } = require('./helpers/mockBackend')
const { getElectronLaunchArgs } = require('./helpers/electronLaunch')
const dir = path.resolve(__dirname, '..')
const artifacts = path.resolve(dir, '..', 'artifacts/onboarding-slim-2026-10-02')
async function fixture(options = {}) {
  const backend = createMockChronicleBackend()
  const port = await backend.start()
  const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-slim-wizard-'))
  const saves = path.join(profile, 'Stellaris/save games')
  await fs.mkdir(saves, { recursive: true })
  for (let i = 0; i < (options.saves || 0); i++) await fs.writeFile(path.join(saves, `fictional-${i}.sav`), 'UI fixture')
  if (options.settings) await fs.writeFile(path.join(profile, 'settings.json'), JSON.stringify({ hasCompletedOnboarding: false, ...options.settings }))
  let app
  try {
    app = await electron.launch({ args: getElectronLaunchArgs(path.join(dir, 'main.js')), env: {
      ...process.env, NODE_ENV: 'test', E2E: '1', E2E_CHATGPT_MOCK: '1', E2E_USER_DATA_DIR: profile, E2E_SAVE_DIR: saves,
      E2E_ONBOARDING_COMPLETE: '0', E2E_SKIP_BACKEND_AUTOSTART: '1', E2E_BACKEND_CONFIGURED: '1',
      STELLARIS_API_PORT: String(port), STELLARIS_API_TOKEN: 'e2e-token', E2E_HEALTH_CHECK_INTERVAL_MS: '200', ...options.env,
    } })
    const page = await app.firstWindow()
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setContentSize(1000, 700))
    return { app, page, saves, profile, close: async () => { await app.close(); await backend.stop(); await fs.rm(profile, { recursive: true, force: true }) } }
  } catch (error) { await app?.close(); await backend.stop(); await fs.rm(profile, { recursive: true, force: true }); throw error }
}
async function shot(page, name) {
  await fs.mkdir(artifacts, { recursive: true })
  await page.evaluate(() => document.fonts.ready)
  await page.waitForFunction(() => {
    const dialog = document.querySelector('[role="dialog"]')
    if (!dialog) return false
    const m = new DOMMatrixReadOnly(getComputedStyle(dialog).transform)
    return Math.abs(m.m41) < 0.2 && Math.abs(m.m42) < 0.2 && Math.abs(m.m11 - 1) < 0.001
  })
  await page.screenshot({ path: path.join(artifacts, name), animations: 'disabled' })
}
async function start(page) { await page.getByRole('button', { name: 'Get started', exact: true }).click() }
async function modelServer(models) {
  const requests = []
  const server = http.createServer(async (req, res) => {
    let body = ''; for await (const chunk of req) body += chunk
    requests.push({ url: req.url, authorization: req.headers.authorization, body: body && JSON.parse(body) })
    res.setHeader('content-type', 'application/json')
    res.end(JSON.stringify(req.url === '/v1/models' ? { data: models.map(id => ({ id })) } : { model: JSON.parse(body).model, choices: [{ message: { content: '{"status":"ok"}' } }] }))
  })
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  return { baseUrl: `http://127.0.0.1:${server.address().port}/v1`, requests, close: () => new Promise(resolve => server.close(resolve)) }
}

test('ChatGPT leads, completes automatically, saves the folder, and shows one brief first-use notice', async () => {
  const f = await fixture({ saves: 3 })
  try {
    const { page } = f
    await expect(page.getByRole('heading', { name: 'First contact' })).toBeVisible()
    await expect(page.getByText('Welcome to Stellaris Companion', { exact: true })).toBeVisible()
    await shot(page, '01-first-contact.png')
    await start(page)
    await expect(page.getByRole('button', { name: /Gemini API key/ })).toBeVisible()
    await expect(page.getByRole('button', { name: /OpenRouter API key/ })).toBeVisible()
    await expect(page.getByRole('button', { name: /Local models Ollama/ })).toBeVisible()
    await shot(page, '02-choose-advisor.png')
    const language = page.getByTestId('onboarding-language')
    await language.focus(); await page.keyboard.press('Shift+Tab')
    await expect(page.getByRole('button', { name: 'Set up later' })).toBeFocused()
    await page.getByRole('button', { name: 'Continue with ChatGPT', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Find your saves' })).toBeVisible()
    await expect(page.getByText('3 saves found', { exact: true })).toBeVisible()
    await expect(page.getByText('ChatGPT connected', { exact: true })).toBeVisible()
    await shot(page, '13-saves-found.png')
    await page.getByRole('button', { name: 'Show full location' }).click()
    await expect(page.getByText(f.saves, { exact: true })).toHaveCount(2)
    await page.getByRole('button', { name: 'Hide full location' }).click()
    await page.getByRole('button', { name: 'Open Companion' }).click()
    const notice = page.getByRole('dialog', { name: 'Using your ChatGPT plan' })
    await expect(notice).toBeVisible()
    await shot(page, '15-chatgpt-first-use.png')
    await notice.getByRole('button', { name: 'Got it' }).click()
    await expect(page.getByRole('dialog')).toHaveCount(0)
    const settings = await page.evaluate(() => window.electronAPI.getSettings())
    expect(settings.advisorProvider).toBe('chatgpt'); expect(settings.saveDir).toBe(f.saves)
    expect((await page.evaluate(() => window.electronAPI.chatgpt.status())).status.welcomePending).toBe(false)
  } finally { await f.close() }
})

test('browser sign-in can reopen, cancellation ignores late work, and skipping keeps prior settings', async () => {
  const f = await fixture({ env: { E2E_CHATGPT_HOLD_SIGNIN: '1', E2E_CHATGPT_HOLD_CHECK: '1' }, settings: { saveDir: '/previous/save games' } })
  try {
    const { page, app } = f
    await page.evaluate(() => window.electronAPI.saveSettings({ googleApiKey: 'fictional-preserved' }))
    await start(page)
    await page.getByRole('button', { name: 'Continue with ChatGPT', exact: true }).click()
    await expect(page.getByText('Finish signing in in your browser', { exact: true })).toBeVisible()
    await shot(page, '03-chatgpt-browser.png')
    await page.getByRole('button', { name: 'Reopen sign-in' }).click()
    expect(await app.evaluate(() => globalThis.__chatgptSignInOpens)).toBe(2)
    await app.evaluate(() => globalThis.__chatgptContinue().then(() => null))
    await expect(page.getByText('Checking your connection…', { exact: true })).toBeVisible()
    await expect.poll(() => app.evaluate(() => typeof globalThis.__chatgptFinishCheck)).toBe('function')
    await shot(page, '04-chatgpt-checking.png')
    await page.getByRole('button', { name: 'Set up later' }).click()
    await app.evaluate(() => globalThis.__chatgptFinishCheck())
    await expect(page.getByRole('heading', { name: 'Find your saves' })).toBeVisible()
    await expect(page.getByText('ChatGPT connected', { exact: true })).toHaveCount(0)
    await expect(page.getByText('No saves found', { exact: true })).toBeVisible()
    await shot(page, '14-saves-missing.png')
    await page.getByRole('button', { name: 'Set up later' }).click()
    await expect(page.getByRole('dialog')).toHaveCount(0)
    const settings = await page.evaluate(() => window.electronAPI.getSettings())
    expect(settings.advisorProvider).toBe('gemini'); expect(settings.googleApiKeySet).toBe(true); expect(settings.saveDir).toBe('/previous/save games')
  } finally { await f.close() }
})

test('cloud key errors recover, drafts survive Back, and failed storage does not advance', async () => {
  const f = await fixture()
  try {
    const { page, app } = f
    await app.evaluate(({ ipcMain }) => {
      globalThis.__cloudRequests = []
      ipcMain.removeHandler('advisor-provider:list-models')
      ipcMain.handle('advisor-provider:list-models', (_event, config) => {
        globalThis.__cloudRequests.push(config)
        return config.apiKey === 'valid-fixture-key' ? { ok: true, models: [{ id: 'fixture-model', name: 'Fixture model', recommended: true }] } : { ok: false, error: 'Invalid API key. Try another key.' }
      })
      ipcMain.removeHandler('advisor-provider:test-model')
      ipcMain.handle('advisor-provider:test-model', (_event, config) => ({ ok: true, chronicleReady: true, model: config.model }))
    })
    await start(page); await page.getByRole('button', { name: /Gemini API key/ }).click()
    await expect(page.getByRole('button', { name: 'Connect Gemini', exact: true })).toBeDisabled()
    await shot(page, '06-gemini-key.png')
    await page.getByLabel('API key', { exact: true }).fill('invalid-fixture-key')
    await page.getByLabel('API key', { exact: true }).press('Enter')
    await expect(page.getByText('We couldn’t connect.', { exact: true })).toBeVisible()
    await shot(page, '05-connection-error.png')
    await page.getByRole('button', { name: 'Edit connection details' }).click()
    await expect(page.getByLabel('API key', { exact: true })).toHaveValue('invalid-fixture-key')
    await page.getByRole('button', { name: 'Back', exact: true }).click()
    await page.getByRole('button', { name: /OpenRouter API key/ }).click()
    await shot(page, '07-openrouter-key.png')
    await page.getByRole('button', { name: 'Back', exact: true }).click()
    await page.getByRole('button', { name: /Gemini API key/ }).click()
    await expect(page.getByLabel('API key', { exact: true })).toHaveValue('invalid-fixture-key')
    await page.getByLabel('API key', { exact: true }).fill('valid-fixture-key')
    // Override storage only after language and onboarding have finished loading.
    await app.evaluate(({ ipcMain }) => { ipcMain.removeHandler('save-settings'); ipcMain.handle('save-settings', () => ({ success: false })) })
    await page.getByRole('button', { name: 'Connect Gemini', exact: true }).click()
    await expect(page.getByRole('alert')).toHaveText('Could not save your connection. Try again.')
    await expect(page.locator('[data-onboarding-frame-step="2"]')).toBeVisible()
    await page.getByRole('button', { name: 'Edit connection details' }).click()
    await expect(page.getByLabel('API key', { exact: true })).toHaveValue('valid-fixture-key')
  } finally { await f.close() }
})

test('local models use real discovery and verification; custom endpoints preserve the chosen model and key', async () => {
  const server = await modelServer(['local-small', 'local-large'])
  const f = await fixture()
  try {
    const { page } = f
    await start(page); await page.getByRole('button', { name: /Local models Ollama/ }).click()
    await shot(page, '08-local-app.png')
    await page.getByRole('radio', { name: 'LM Studio' }).check()
    await page.getByRole('button', { name: 'Connection details' }).click()
    await expect(page.getByLabel('Server URL')).toHaveValue('http://127.0.0.1:1234/v1')
    await shot(page, '10-local-details.png')
    await page.getByLabel('Server URL').fill(server.baseUrl)
    await page.getByLabel('API key (optional)', { exact: true }).fill('fixture-local-key')
    await page.getByRole('button', { name: 'Save & connect' }).click()
    await expect(page.getByRole('radio', { name: 'local-small' })).toBeChecked()
    await page.getByRole('radio', { name: 'local-small' }).focus(); await page.keyboard.press('ArrowRight')
    await expect(page.getByRole('radio', { name: 'local-large' })).toBeChecked()
    await shot(page, '09-local-model.png')
    await page.getByRole('button', { name: 'Use this model' }).click()
    await expect(page.getByRole('heading', { name: 'Find your saves' })).toBeVisible()
    let settings = await page.evaluate(() => window.electronAPI.getSettings())
    expect(settings.advisorProvider).toBe('lm_studio'); expect(settings.advisorModel).toBe('local-large'); expect(settings.advisorBaseUrl).toBe(server.baseUrl)
    expect(server.requests.at(-1).authorization).toBe('Bearer fixture-local-key')
    expect(server.requests.at(-1).body.model).toBe('local-large')
    await page.getByRole('button', { name: 'Back', exact: true }).click()
    await page.getByRole('button', { name: 'Custom endpoint', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Connect', exact: true })).toBeDisabled()
    await shot(page, '11-custom-endpoint.png')
    await page.getByLabel('Server URL').fill(server.baseUrl)
    await page.getByLabel('Model', { exact: true }).fill('custom-model')
    await page.getByLabel('API key (optional)', { exact: true }).fill('fixture-custom-key')
    await page.getByLabel('API key (optional)', { exact: true }).press('Enter')
    await expect(page.getByRole('heading', { name: 'Find your saves' })).toBeVisible()
    settings = await page.evaluate(() => window.electronAPI.getSettings())
    expect(settings.advisorProvider).toBe('custom'); expect(settings.advisorModel).toBe('custom-model')
    expect(server.requests.at(-1).authorization).toBe('Bearer fixture-custom-key')
  } finally { await f.close(); await server.close() }
})

test('a late cloud discovery result cannot activate a provider after skipping', async () => {
  const f = await fixture()
  try {
    const { page, app } = f
    await app.evaluate(({ ipcMain }) => {
      ipcMain.removeHandler('advisor-provider:list-models')
      ipcMain.handle('advisor-provider:list-models', () => new Promise(resolve => { globalThis.__finishDiscovery = () => resolve({ ok: true, models: [{ id: 'fixture' }] }) }))
    })
    await start(page); await page.getByRole('button', { name: /Gemini API key/ }).click()
    await page.getByLabel('API key', { exact: true }).fill('fixture-key')
    await page.getByRole('button', { name: 'Connect Gemini', exact: true }).click()
    await expect.poll(() => app.evaluate(() => typeof globalThis.__finishDiscovery)).toBe('function')
    await page.getByRole('button', { name: 'Set up later' }).click()
    await app.evaluate(() => globalThis.__finishDiscovery())
    await expect(page.getByRole('heading', { name: 'Find your saves' })).toBeVisible()
    await expect(page.getByText('Gemini connected', { exact: true })).toHaveCount(0)
    expect((await page.evaluate(() => window.electronAPI.getSettings())).googleApiKeySet).toBe(false)
  } finally { await f.close() }
})

test('one local model advances directly; an empty catalog can recover after loading a model', async () => {
  const server = await modelServer([])
  const f = await fixture()
  try {
    const { page, app } = f
    await app.evaluate(({ ipcMain }) => {
      globalThis.__localModels = []
      ipcMain.removeHandler('advisor-provider:list-models')
      ipcMain.handle('advisor-provider:list-models', (_event, config) => ({ ok: true, models: globalThis.__localModels, baseUrl: config.baseUrl }))
    })
    await start(page); await page.getByRole('button', { name: /Local models Ollama/ }).click()
    await page.getByRole('button', { name: 'Connection details' }).click()
    await page.getByLabel('Server URL').fill(server.baseUrl)
    await page.getByRole('button', { name: 'Save & connect' }).click()
    await expect(page.getByRole('alert')).toHaveText('No models found. Load a model in your local app, then try again.')
    await app.evaluate(() => { globalThis.__localModels = [{ id: 'one-model', name: 'One model' }] })
    await page.getByRole('button', { name: 'Try again' }).click()
    await expect(page.getByRole('heading', { name: 'Find your saves' })).toBeVisible()
    expect((await page.evaluate(() => window.electronAPI.getSettings())).advisorModel).toBe('one-model')
  } finally { await f.close(); await server.close() }
})

test('save scanning can go Back safely, choose a folder, and recover a failed completion', async () => {
  const f = await fixture()
  try {
    const { page, app } = f
    await app.evaluate(({ ipcMain }) => {
      ipcMain.removeHandler('onboarding:detect-saves')
      ipcMain.handle('onboarding:detect-saves', () => new Promise(resolve => { globalThis.__finishScan = () => resolve({ found: false, directory: null, saveCount: 0, latest: null }) }))
    })
    await start(page); await page.getByRole('button', { name: 'Set up later' }).click()
    await expect(page.getByText('Finding Stellaris saves…', { exact: true })).toBeVisible()
    await shot(page, '12-saves-scanning.png')
    await page.getByRole('button', { name: 'Back', exact: true }).click()
    await app.evaluate(() => globalThis.__finishScan())
    await expect(page.getByRole('heading', { name: 'Connect your advisor' })).toBeVisible()
    const chosen = path.join(f.profile, 'chosen-saves')
    await fs.mkdir(chosen); await fs.writeFile(path.join(chosen, 'fictional.sav'), 'UI fixture')
    await app.evaluate(({ ipcMain, dialog }, directory) => {
      ipcMain.removeHandler('onboarding:detect-saves')
      globalThis.__scanCount = 0
      ipcMain.handle('onboarding:detect-saves', () => { globalThis.__scanCount++; return { found: false, directory: null, saveCount: 0, latest: null } })
      dialog.showOpenDialog = () => new Promise(resolve => { globalThis.__chooseFolder = () => resolve({ canceled: false, filePaths: [directory] }) })
      ipcMain.removeHandler('onboarding:complete')
      let fail = true
      ipcMain.handle('onboarding:complete', () => { const success = !fail; fail = false; return { success } })
    }, chosen)
    await page.getByRole('button', { name: 'Set up later' }).click()
    await page.getByRole('button', { name: 'Choose folder' }).click()
    await expect.poll(() => app.evaluate(() => globalThis.__scanCount)).toBeGreaterThanOrEqual(2)
    await app.evaluate(() => globalThis.__chooseFolder())
    await expect(page.getByText('1 save found', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Open Companion' }).click()
    await expect(page.getByRole('alert')).toHaveText('Could not finish setup. Try again.')
    await page.getByRole('button', { name: 'Open Companion' }).click()
    await expect(page.getByRole('dialog')).toHaveCount(0)
    expect((await page.evaluate(() => window.electronAPI.getSettings())).saveDir).toBe(chosen)
  } finally { await f.close() }
})

test('OpenRouter can recover by choosing another model, and Gemini saves only after a successful key check', async () => {
  const f = await fixture()
  try {
    const { page, app } = f
    await app.evaluate(({ ipcMain }) => {
      ipcMain.removeHandler('advisor-provider:list-models')
      ipcMain.handle('advisor-provider:list-models', (_event, config) => config.apiKey === 'valid-fixture-key'
        ? { ok: true, models: [{ id: 'limited-model', name: 'Limited model', recommended: true }, { id: 'compatible-model', name: 'Compatible model' }] }
        : { ok: false, error: 'Invalid key' })
      ipcMain.removeHandler('advisor-provider:test-model')
      ipcMain.handle('advisor-provider:test-model', (_event, config) => ({ ok: true, chronicleReady: config.provider === 'gemini' || config.model === 'compatible-model', model: config.model }))
    })
    await start(page); await page.getByRole('button', { name: /OpenRouter API key/ }).click()
    await page.getByLabel('API key', { exact: true }).fill('valid-fixture-key')
    await page.getByRole('button', { name: 'Connect OpenRouter', exact: true }).click()
    await expect(page.getByRole('alert')).toHaveText('This model could not produce the structured response Chronicle needs. Choose another model.')
    await page.getByRole('button', { name: 'Choose a model.', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Connect OpenRouter' })).toBeVisible()
    await page.getByRole('radio', { name: 'Compatible model' }).check()
    await page.getByRole('button', { name: 'Use this model' }).click()
    await expect(page.getByRole('heading', { name: 'Find your saves' })).toBeVisible()
    let settings = await page.evaluate(() => window.electronAPI.getSettings())
    expect(settings.advisorProvider).toBe('openrouter'); expect(settings.advisorModel).toBe('compatible-model'); expect(settings.openRouterApiKeySet).toBe(true)
    await page.getByRole('button', { name: 'Back', exact: true }).click()
    await page.getByRole('button', { name: /Gemini API key/ }).click()
    await page.getByLabel('API key', { exact: true }).fill('valid-fixture-key')
    await page.getByRole('button', { name: 'Connect Gemini', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Find your saves' })).toBeVisible()
    settings = await page.evaluate(() => window.electronAPI.getSettings())
    expect(settings.advisorProvider).toBe('gemini'); expect(settings.advisorModel).toBe(''); expect(settings.googleApiKeySet).toBe(true); expect(settings.openRouterApiKeySet).toBe(true)
    await page.getByRole('button', { name: 'Set up later' }).click()
    await expect(page.getByRole('dialog')).toHaveCount(0)
  } finally { await f.close() }
})

test('OpenRouter browser credentials stay opaque and late sign-in cannot save after cancellation', async () => {
  const f = await fixture()
  try {
    const { page, app } = f
    await app.evaluate(({ ipcMain }) => {
      globalThis.__browserSaves = []
      globalThis.__browserConfigs = []
      globalThis.__browserCancelled = 0
      ipcMain.removeHandler('advisor-provider:connect-openrouter')
      ipcMain.handle('advisor-provider:connect-openrouter', () => globalThis.__holdRouterSignIn
        ? new Promise(resolve => { globalThis.__finishRouterSignIn = () => resolve({ ok: true, credentialId: 'late-fixture-id' }) })
        : { ok: true, credentialId: 'opaque-fixture-id' })
      ipcMain.removeHandler('advisor-provider:cancel-openrouter')
      ipcMain.handle('advisor-provider:cancel-openrouter', () => { globalThis.__browserCancelled++; return { ok: true } })
      for (const channel of ['advisor-provider:list-models', 'advisor-provider:test-model']) {
        ipcMain.removeHandler(channel)
        ipcMain.handle(channel, (_event, config) => {
          globalThis.__browserConfigs.push(config)
          return { ok: true, models: [{ id: 'browser-model', name: 'Browser model' }], chronicleReady: true, model: 'browser-model' }
        })
      }
      ipcMain.removeHandler('save-settings')
      ipcMain.handle('save-settings', (_event, values) => { globalThis.__browserSaves.push(values); return { success: true } })
    })
    await start(page)
    await page.getByRole('button', { name: /OpenRouter API key/ }).click()
    await page.getByRole('button', { name: 'Sign in with OpenRouter', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Find your saves' })).toBeVisible()
    const first = await app.evaluate(() => ({ saved: globalThis.__browserSaves, requests: globalThis.__browserConfigs }))
    expect(first.saved).toHaveLength(1)
    expect(first.saved[0]).toMatchObject({ advisorProvider: 'openrouter', advisorModel: 'browser-model', openRouterCredentialId: 'opaque-fixture-id', openRouterApiKey: '' })
    expect(first.requests).toHaveLength(2)
    for (const request of first.requests) expect(request).toMatchObject({ provider: 'openrouter', credentialId: 'opaque-fixture-id' })
    await page.getByRole('button', { name: 'Back', exact: true }).click()
    await page.getByRole('button', { name: /OpenRouter API key/ }).click()
    await app.evaluate(() => { globalThis.__holdRouterSignIn = true })
    await page.getByRole('button', { name: 'Sign in with OpenRouter', exact: true }).click()
    await expect(page.getByText('Finish signing in in your browser', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Set up later', exact: true }).click()
    await app.evaluate(() => globalThis.__finishRouterSignIn())
    await expect(page.getByRole('heading', { name: 'Find your saves' })).toBeVisible()
    expect(await app.evaluate(() => globalThis.__browserCancelled)).toBe(1)
    expect(await app.evaluate(() => globalThis.__browserSaves.length)).toBe(1)
  } finally { await f.close() }
})
