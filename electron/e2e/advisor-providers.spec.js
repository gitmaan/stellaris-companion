const fs = require('fs/promises')
const http = require('http')
const os = require('os')
const path = require('path')

const { test, expect, _electron: electron } = require('@playwright/test')

const { createMockChronicleBackend } = require('./helpers/mockBackend')
const { getElectronLaunchArgs } = require('./helpers/electronLaunch')

const electronDir = path.resolve(__dirname, '..')

function startProviderServer() {
  let server
  let lastAuthorization = ''
  let lastCompletionModel = ''
  return new Promise((resolve, reject) => {
    server = http.createServer((req, res) => {
      if (req.method === 'GET' && req.url === '/v1/models') {
        lastAuthorization = req.headers.authorization || ''
        res.writeHead(200, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({
          data: [
            {
              id: 'local/strategist-small',
              name: 'Strategist Small',
              context_length: 8192,
            },
            {
              id: 'local/strategist-large',
              name: 'Strategist Large',
              context_length: 65536,
            },
          ],
        }))
        return
      }
      if (req.method === 'POST' && req.url === '/v1/chat/completions') {
        lastAuthorization = req.headers.authorization || ''
        const chunks = []
        req.on('data', (chunk) => chunks.push(chunk))
        req.on('end', () => {
          const body = JSON.parse(Buffer.concat(chunks).toString('utf8'))
          lastCompletionModel = body.model
          res.writeHead(200, { 'Content-Type': 'application/json' })
          res.end(JSON.stringify({
            model: body.model,
            choices: [{ message: { content: '{"status":"ok"}' } }],
          }))
        })
        return
      }
      res.writeHead(404, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ error: 'Not found' }))
    })
    server.once('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const address = server.address()
      resolve({
        port: address.port,
        getLastAuthorization: () => lastAuthorization,
        getLastCompletionModel: () => lastCompletionModel,
        stop: () => new Promise((done) => server.close(done)),
      })
    })
  })
}

async function launchApp(backendPort, userDataDir) {
  return electron.launch({
    args: getElectronLaunchArgs(path.join(electronDir, 'main.js')),
    env: {
      ...process.env,
      NODE_ENV: 'test',
      E2E: '1',
      E2E_ONBOARDING_COMPLETE: '1',
      E2E_BACKEND_CONFIGURED: '1',
      E2E_SKIP_BACKEND_AUTOSTART: '1',
      E2E_HEALTH_CHECK_INTERVAL_MS: '200',
      E2E_USER_DATA_DIR: userDataDir,
      STELLARIS_API_PORT: String(backendPort),
      STELLARIS_API_TOKEN: 'e2e-token',
    },
  })
}

test('keeps response diagnostics optional and humanizes Advisor style details', async () => {
  const backend = createMockChronicleBackend({
    chatResponse: 'Fortify the northern choke point before expanding again.',
    chatModel: 'Mock Advisor Model',
  })
  const backendPort = await backend.start()
  const userDataDir = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-advisor-surface-e2e-'))
  const app = await launchApp(backendPort, userDataDir)

  try {
    const page = await app.firstWindow()
    await page.waitForLoadState('domcontentloaded')

    const chatInput = page.getByPlaceholder('HOW CAN WE HELP?')
    await chatInput.fill('What should I do next?')
    await page.getByRole('button', { name: 'SEND' }).click()
    await expect(page.getByText('Fortify the northern choke point before expanding again.')).toBeVisible()

    const responseDetails = page.getByText('Response details', { exact: true })
    await expect(responseDetails).toBeVisible()
    await expect(page.getByText('MODEL: Mock Advisor Model')).toBeHidden()
    await responseDetails.click()
    await expect(page.getByText('MODEL: Mock Advisor Model')).toBeVisible()
    await expect(page.getByText('Response time: 0.01s')).toBeVisible()
    await expect(page.getByRole('button', { name: 'REPORT' })).toBeVisible()

    await page.getByRole('button', { name: 'Advisor Info' }).click()
    const styleDialog = page.getByRole('dialog', { name: 'Advisor style' })
    await expect(styleDialog).toBeVisible()
    await expect(styleDialog.getByText('Idealistic Foundation')).toBeVisible()
    await expect(styleDialog.getByText('Prosperous Unification')).toBeVisible()
    await expect(styleDialog.getByText('idealistic_foundation')).toHaveCount(0)
    await expect(styleDialog.getByLabel('Advisor personality instructions')).toBeVisible()
  } finally {
    await app.close()
    await backend.stop()
    await fs.rm(userDataDir, { recursive: true, force: true })
  }
})

test('configures a compatible Advisor provider and discovers its models', async () => {
  const backend = createMockChronicleBackend()
  const backendPort = await backend.start()
  const provider = await startProviderServer()
  const userDataDir = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-provider-e2e-'))
  let app = await launchApp(backendPort, userDataDir)

  try {
    const page = await app.firstWindow()
    await page.waitForLoadState('domcontentloaded')
    await page.getByRole('button', { name: /Config/i }).click()

    await expect(page.getByRole('button', { name: /Gemini.*EASIEST SETUP/i })).toHaveAttribute('aria-pressed', 'true')
    await page.getByRole('button', { name: /Online provider/i }).click()
    const providerSelect = page.getByLabel('PROVIDER')
    await expect(providerSelect).toHaveValue('openrouter')
    await providerSelect.selectOption('custom')
    await expect(page.getByText(/relevant parts of your campaign are sent to this provider/i)).toBeVisible()

    await page.getByPlaceholder('https://provider.example/v1').fill(
      `http://127.0.0.1:${provider.port}/v1`,
    )
    await page.getByLabel('API KEY', { exact: true }).fill('tiny-key')
    await page.getByLabel('MODEL').fill('local/manual-fallback')
    await page.getByRole('button', { name: /Sooner/i }).click()
    await expect(providerSelect).toHaveValue('custom')
    await expect(page.getByPlaceholder('https://provider.example/v1')).toHaveValue(
      `http://127.0.0.1:${provider.port}/v1`,
    )
    await expect(page.getByLabel('MODEL')).toHaveValue('local/manual-fallback')
    await page.getByRole('button', { name: 'FIND AVAILABLE MODELS' }).click()

    await expect(page.getByText('READY', { exact: true })).toBeVisible()
    await expect(page.getByText(/2 models found/i)).toBeVisible()

    const modelSelect = page.getByLabel('MODEL')
    await expect(modelSelect).toHaveValue('local/manual-fallback')
    await page.getByText('SHOW ADVANCED CONNECTION', { exact: true }).click()
    await expect(page.getByText(/Context size was not reported/i)).toBeVisible()
    await modelSelect.selectOption('local/strategist-small')
    await expect(page.getByText(/8K context detected/i)).toBeVisible()
    await modelSelect.selectOption('local/strategist-large')
    await expect(page.getByText(/Reported context.*64K/i)).toBeVisible()
    await page.getByRole('button', { name: 'SAVE AI SETUP' }).click()
    await expect(page.getByText('AI setup saved.')).toBeVisible()

    await expect(providerSelect).toHaveValue('custom')
    await expect(modelSelect).toHaveValue('local/strategist-large')
    await page.getByRole('button', { name: 'CHECK SELECTED MODEL' }).click()
    await expect(page.getByText(/STRUCTURED RESPONSES SUPPORTED/i)).toBeVisible()
    await expect(page.getByText(/never send campaign data/i)).toBeVisible()
    expect(provider.getLastCompletionModel()).toBe('local/strategist-large')

    await app.close()
    app = await launchApp(backendPort, userDataDir)
    const reloadedPage = await app.firstWindow()
    await reloadedPage.waitForLoadState('domcontentloaded')
    await reloadedPage.getByRole('button', { name: /Config/i }).click()

    await expect(reloadedPage.getByLabel('PROVIDER')).toHaveValue('custom')
    const sessionOnlyStorage = await reloadedPage
      .getByText(/cannot securely save API keys right now/i)
      .isVisible()
    await expect(reloadedPage.getByLabel('API KEY', { exact: true })).toHaveValue(
      sessionOnlyStorage ? '' : '****...****',
    )
    await reloadedPage.getByLabel('MODEL').fill('local/after-reload')
    await reloadedPage.getByRole('button', { name: 'SAVE AI SETUP' }).click()
    await expect(reloadedPage.getByText('AI setup saved.')).toBeVisible()
    await reloadedPage.getByRole('button', { name: 'FIND AVAILABLE MODELS' }).click()
    await expect(reloadedPage.getByText('READY', { exact: true })).toBeVisible()
    expect(provider.getLastAuthorization()).toBe(sessionOnlyStorage ? '' : 'Bearer tiny-key')
  } finally {
    await app?.close()
    await provider.stop()
    await backend.stop()
    await fs.rm(userDataDir, { recursive: true, force: true })
  }
})

test('turns provider failures into actionable Chat recovery', async () => {
  const backend = createMockChronicleBackend({
    advisorProvider: 'ollama',
    chatError: {
      status: 503,
      code: 'PROVIDER_UNAVAILABLE',
      error: 'connect ECONNREFUSED 127.0.0.1:11434',
    },
  })
  const backendPort = await backend.start()
  const userDataDir = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-provider-error-e2e-'))
  const app = await launchApp(backendPort, userDataDir)

  try {
    const page = await app.firstWindow()
    await page.waitForLoadState('domcontentloaded')

    const chatInput = page.getByPlaceholder('HOW CAN WE HELP?')
    await expect(chatInput).toBeEnabled()
    await chatInput.fill('Could we win a war right now?')
    await page.getByRole('button', { name: 'SEND' }).click()

    await expect(page.getByText(/Ollama could not be reached/i)).toBeVisible()
    await expect(page.getByText(/ECONNREFUSED/i)).toHaveCount(0)

    await page.getByRole('button', { name: 'OPEN PROVIDER SETTINGS' }).click()
    await expect(page.getByText('WHERE SHOULD AI RUN?')).toBeVisible()
  } finally {
    await app.close()
    await backend.stop()
    await fs.rm(userDataDir, { recursive: true, force: true })
  }
})

test('guides an unconfigured Advisor directly to provider settings', async () => {
  const backend = createMockChronicleBackend({
    advisorProvider: 'ollama',
    advisorConfigured: false,
  })
  const backendPort = await backend.start()
  const userDataDir = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-provider-setup-e2e-'))
  const app = await launchApp(backendPort, userDataDir)

  try {
    const page = await app.firstWindow()
    await page.waitForLoadState('domcontentloaded')

    await expect(page.getByText('ADVISOR CONNECTION REQUIRED')).toBeVisible()
    await expect(page.getByText(/Ollama is selected but not ready/i)).toBeVisible()

    await page.getByRole('button', { name: 'OPEN PROVIDER SETTINGS' }).click()
    await expect(page.getByText('WHERE SHOULD AI RUN?')).toBeVisible()
  } finally {
    await app.close()
    await backend.stop()
    await fs.rm(userDataDir, { recursive: true, force: true })
  }
})

test('keeps existing Chronicle readable while guiding provider setup', async () => {
  const backend = createMockChronicleBackend({
    advisorProvider: 'lm_studio',
    chronicleConfigured: false,
  })
  const backendPort = await backend.start()
  const userDataDir = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-chronicle-key-e2e-'))
  const app = await launchApp(backendPort, userDataDir)

  try {
    const page = await app.firstWindow()
    await page.waitForLoadState('domcontentloaded')
    await page.getByRole('button', { name: /Chronicle/i }).click()

    await expect(page.getByText('Old teaser.')).toBeVisible()
    await expect(
      page.getByText('AI PROVIDER CONNECTION REQUIRED'),
    ).toBeVisible()

    await page.getByRole('button', { name: 'OPEN PROVIDER SETTINGS' }).click()
    await expect(page.getByText('WHERE SHOULD AI RUN?')).toBeVisible()
  } finally {
    await app.close()
    await backend.stop()
    await fs.rm(userDataDir, { recursive: true, force: true })
  }
})

test('keeps cached Chronicle readable when its provider goes offline', async () => {
  const backend = createMockChronicleBackend({
    advisorProvider: 'lm_studio',
  })
  const backendPort = await backend.start()
  const userDataDir = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-chronicle-error-e2e-'))
  const app = await launchApp(backendPort, userDataDir)

  try {
    const page = await app.firstWindow()
    await page.waitForLoadState('domcontentloaded')
    await page.getByRole('button', { name: /Chronicle/i }).click()
    await expect(page.getByText('Old teaser.')).toBeVisible()
    await backend.waitForChronicleRequest((request) => request.chapter_only === false)

    backend.setChronicleError({
      status: 503,
      code: 'PROVIDER_UNAVAILABLE',
      error: 'connect ECONNREFUSED 127.0.0.1:1234',
    })
    backend.advanceCampaign()

    await expect(page.getByText(/LM Studio could not be reached/i)).toBeVisible()
    await expect(page.getByText('Old teaser.')).toBeVisible()
    await expect(page.getByText(/ECONNREFUSED/i)).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'OPEN PROVIDER SETTINGS' })).toBeVisible()
  } finally {
    await app.close()
    await backend.stop()
    await fs.rm(userDataDir, { recursive: true, force: true })
  }
})
