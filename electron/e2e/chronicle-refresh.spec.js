const fs = require('fs/promises')
const os = require('os')
const path = require('path')

const { test, expect, _electron: electron } = require('@playwright/test')

const { createMockChronicleBackend } = require('./helpers/mockBackend')

const electronDir = path.resolve(__dirname, '..')

async function installVisibilityShim(page) {
  await page.evaluate(() => {
    if (window.__e2eVisibilityShimInstalled) return

    let visibilityState = 'visible'
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => visibilityState,
    })
    Object.defineProperty(document, 'hidden', {
      configurable: true,
      get: () => visibilityState !== 'visible',
    })

    window.__setE2EVisibilityState = (nextState) => {
      visibilityState = nextState
      document.dispatchEvent(new Event('visibilitychange'))
      window.dispatchEvent(new Event(nextState === 'visible' ? 'focus' : 'blur'))
    }

    window.__e2eVisibilityShimInstalled = true
  })
}

async function setVisibilityState(page, nextState) {
  await page.evaluate((state) => {
    window.__setE2EVisibilityState(state)
  }, nextState)
}

test('chronicle auto-refreshes with a visible full refresh after live progress advances', async () => {
  const backend = createMockChronicleBackend()
  const backendPort = await backend.start()
  const userDataDir = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-companion-e2e-'))

  const app = await electron.launch({
    args: [path.join(electronDir, 'main.js')],
    env: {
      ...process.env,
      NODE_ENV: 'test',
      E2E: '1',
      E2E_ONBOARDING_COMPLETE: '1',
      E2E_BACKEND_CONFIGURED: '1',
      E2E_SKIP_BACKEND_AUTOSTART: '1',
      E2E_HEALTH_CHECK_INTERVAL_MS: '200',
      E2E_HEALTH_CHECK_REQUEST_TIMEOUT_MS: '750',
      E2E_HEALTH_CHECK_TIMEOUT_MS: '3000',
      E2E_USER_DATA_DIR: userDataDir,
      STELLARIS_API_PORT: String(backendPort),
      STELLARIS_API_TOKEN: 'e2e-token',
    },
  })

  try {
    const page = await app.firstWindow()
    await page.waitForLoadState('domcontentloaded')
    await installVisibilityShim(page)

    await page.getByRole('button', { name: /Chronicle/i }).click()
    await expect(page.getByText('Old teaser.')).toBeVisible()
    await expect(page.getByText('2 events in this era')).toBeVisible()

    await backend.waitForChronicleRequest((request) => request.chapter_only === false)

    backend.advanceCampaign()

    await expect(page.getByText('Updated after visible refresh.')).toBeVisible()
    await expect(page.getByText('5 events in this era')).toBeVisible()

    await backend.waitForChronicleRequest((_request, requests) => (
      requests.length >= 2 && requests[requests.length - 1].chapter_only === false
    ))

    const chronicleRequests = backend.getChronicleRequests()
    expect(chronicleRequests.length).toBeGreaterThanOrEqual(2)
    expect(chronicleRequests.at(-1).chapter_only).toBe(false)
  } finally {
    await app.close()
    await backend.stop()
    await fs.rm(userDataDir, { recursive: true, force: true })
  }
})

test('chronicle defers teaser refresh while hidden and catches up after the window returns', async () => {
  const backend = createMockChronicleBackend()
  const backendPort = await backend.start()
  const userDataDir = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-companion-e2e-'))

  const app = await electron.launch({
    args: [path.join(electronDir, 'main.js')],
    env: {
      ...process.env,
      NODE_ENV: 'test',
      E2E: '1',
      E2E_ONBOARDING_COMPLETE: '1',
      E2E_BACKEND_CONFIGURED: '1',
      E2E_SKIP_BACKEND_AUTOSTART: '1',
      E2E_HEALTH_CHECK_INTERVAL_MS: '200',
      E2E_HEALTH_CHECK_REQUEST_TIMEOUT_MS: '750',
      E2E_HEALTH_CHECK_TIMEOUT_MS: '3000',
      E2E_USER_DATA_DIR: userDataDir,
      STELLARIS_API_PORT: String(backendPort),
      STELLARIS_API_TOKEN: 'e2e-token',
    },
  })

  try {
    const page = await app.firstWindow()
    await page.waitForLoadState('domcontentloaded')
    await installVisibilityShim(page)

    await page.getByRole('button', { name: /Chronicle/i }).click()
    await expect(page.getByText('Old teaser.')).toBeVisible()
    await backend.waitForChronicleRequest((request) => request.chapter_only === false)

    await setVisibilityState(page, 'hidden')
    await expect.poll(async () => page.evaluate(() => document.visibilityState)).toBe('hidden')

    backend.advanceCampaign()

    await backend.waitForChronicleRequest((_request, requests) => (
      requests.length >= 2 && requests[requests.length - 1].chapter_only === true
    ))

    await expect(page.getByText('Old teaser.')).toBeVisible()

    await setVisibilityState(page, 'visible')
    await expect.poll(async () => page.evaluate(() => document.visibilityState)).toBe('visible')

    await expect(page.getByText('Updated after visible refresh.')).toBeVisible()
    await expect(page.getByText('5 events in this era')).toBeVisible()

    await backend.waitForChronicleRequest((_request, requests) => (
      requests.length >= 3 && requests[requests.length - 1].chapter_only === false
    ))

    const chronicleRequests = backend.getChronicleRequests()
    expect(chronicleRequests.length).toBeGreaterThanOrEqual(3)
    expect(chronicleRequests[1].chapter_only).toBe(true)
    expect(chronicleRequests.at(-1).chapter_only).toBe(false)
  } finally {
    await app.close()
    await backend.stop()
    await fs.rm(userDataDir, { recursive: true, force: true })
  }
})
