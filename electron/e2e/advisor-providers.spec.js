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
            { id: 'local/strategist-small', name: 'Strategist Small' },
            { id: 'local/strategist-large', name: 'Strategist Large' },
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

    const providerSelect = page.getByLabel('AI PROVIDER')
    await expect(providerSelect).toHaveValue('gemini')
    await providerSelect.selectOption('custom')
    await expect(page.getByText(/extracted game context are sent to this provider/i)).toBeVisible()

    await page.getByPlaceholder('https://provider.example/v1').fill(
      `http://127.0.0.1:${provider.port}/v1`,
    )
    await page.getByLabel('API KEY', { exact: true }).fill('tiny-key')
    await page.getByLabel('AI MODEL').fill('local/manual-fallback')
    await page.getByRole('button', { name: /Frequent/i }).click()
    await expect(providerSelect).toHaveValue('custom')
    await expect(page.getByPlaceholder('https://provider.example/v1')).toHaveValue(
      `http://127.0.0.1:${provider.port}/v1`,
    )
    await expect(page.getByLabel('AI MODEL')).toHaveValue('local/manual-fallback')
    await page.getByRole('button', { name: 'CHECK CONNECTION' }).click()

    await expect(page.getByText('CONNECTED', { exact: true })).toBeVisible()
    await expect(page.getByText(/2 models available/i)).toBeVisible()

    const modelSelect = page.getByLabel('AI MODEL')
    await expect(modelSelect).toHaveValue('local/manual-fallback')
    await modelSelect.selectOption('local/strategist-large')
    await page.getByRole('button', { name: 'APPLY CHANGES' }).click()
    await expect(page.getByText(/CONFIGURATION SAVED/)).toBeVisible()

    await expect(providerSelect).toHaveValue('custom')
    await expect(modelSelect).toHaveValue('local/strategist-large')
    await page.getByRole('button', { name: 'TEST MODEL' }).click()
    await expect(page.getByText('READY FOR ADVISOR + CHRONICLE')).toBeVisible()
    expect(provider.getLastCompletionModel()).toBe('local/strategist-large')

    await app.close()
    app = await launchApp(backendPort, userDataDir)
    const reloadedPage = await app.firstWindow()
    await reloadedPage.waitForLoadState('domcontentloaded')
    await reloadedPage.getByRole('button', { name: /Config/i }).click()

    await expect(reloadedPage.getByLabel('AI PROVIDER')).toHaveValue('custom')
    await expect(reloadedPage.getByLabel('API KEY', { exact: true })).toHaveValue('****...****')
    await reloadedPage.getByLabel('AI MODEL').fill('local/after-reload')
    await reloadedPage.getByRole('button', { name: 'APPLY CHANGES' }).click()
    await expect(reloadedPage.getByText(/CONFIGURATION SAVED/)).toBeVisible()
    await reloadedPage.getByRole('button', { name: 'CHECK CONNECTION' }).click()
    await expect(reloadedPage.getByText('CONNECTED', { exact: true })).toBeVisible()
    expect(provider.getLastAuthorization()).toBe('Bearer tiny-key')
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
    await expect(page.getByLabel('AI PROVIDER')).toBeVisible()
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
    await expect(page.getByLabel('AI PROVIDER')).toBeVisible()
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
    await expect(page.getByLabel('AI PROVIDER')).toBeVisible()
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
