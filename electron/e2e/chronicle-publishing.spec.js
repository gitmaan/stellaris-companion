const fs = require('fs/promises')
const os = require('os')
const path = require('path')

const { test, expect, _electron: electron } = require('@playwright/test')

const { createMockChronicleBackend } = require('./helpers/mockBackend')
const { getElectronLaunchArgs } = require('./helpers/electronLaunch')

const electronDir = path.resolve(__dirname, '..')

async function launchApp(backendPort, userDataDir) {
  return electron.launch({
    args: getElectronLaunchArgs(path.join(electronDir, 'main.js')),
    env: {
      ...process.env,
      NODE_ENV: 'test',
      E2E: '1',
      E2E_ONBOARDING_COMPLETE: '1',
      E2E_BACKEND_CONFIGURED: '1',
      E2E_FAKE_SECURE_STORAGE: '1',
      E2E_SKIP_BACKEND_AUTOSTART: '1',
      E2E_USER_DATA_DIR: userDataDir,
      STELLARIS_API_PORT: String(backendPort),
      STELLARIS_API_TOKEN: 'e2e-token',
      STELLARIS_CHRONICLE_PUBLISHING_API_URL: `http://127.0.0.1:${backendPort}/api/chronicles`,
    },
  })
}

test('publishes, updates, and removes a Chronicle without sending save data', async () => {
  const backend = createMockChronicleBackend()
  const backendPort = await backend.start()
  const userDataDir = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-companion-publish-e2e-'))
  const app = await launchApp(backendPort, userDataDir)

  try {
    const page = await app.firstWindow()
    await page.waitForLoadState('domcontentloaded')

    await page.getByRole('button', { name: /Chronicle/i }).click()
    await expect(page.getByText('Old teaser.')).toBeVisible()

    await page.getByRole('button', { name: 'Share Chronicle' }).click()
    await expect(page.getByRole('dialog', { name: 'Share Chronicle' })).toBeVisible()
    await expect(page.getByText(/public story link/)).toBeVisible()
    await expect(page.getByText(/Never your save file, save path, API key, prompts, or AI provider details/)).toBeVisible()
    await expect(page.getByRole('radio')).toHaveCount(0)
    await expect(page.getByText('Anyone with the link', { exact: true })).toHaveCount(0)
    await expect(page.getByText('Request public discovery', { exact: true })).toHaveCount(0)
    await expect(page.getByText(/random management key/)).not.toBeVisible()
    await page.getByText('How updates and removal work', { exact: true }).click()
    await expect(page.getByText(/random management key/)).toBeVisible()
    expect(backend.getPublicationRequests().filter(request => request.method === 'POST')).toHaveLength(0)

    const storyTitle = page.getByLabel('Story title')
    await storyTitle.fill('The UNE Chronicle')
    await expect(page.getByText('17/120')).toHaveCount(0)
    await page.getByRole('button', { name: 'Publish publicly' }).click()

    await expect(page.getByText('Chronicle published')).toBeVisible()
    await expect(page.getByText('Your public link works now. Archive and search discovery are pending review, so the story remains noindex.')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Copy link' })).toBeVisible()

    const createRequest = await backend.waitForPublicationRequest((request) => request.method === 'POST')
    expect(createRequest.headers.authorization).toMatch(/^Bearer [A-Za-z0-9_-]{43}$/)
    expect(createRequest.headers['x-publisher-id']).toMatch(/^[0-9a-f-]{36}$/)
    expect(createRequest.body.title).toBe('The UNE Chronicle')
    expect(createRequest.body.empire_name).toBe('United Nations of Earth')
    expect(createRequest.body.visibility).toBe('discoverable')
    expect(createRequest.body.client_publication_id).toMatch(/^[0-9a-f-]{36}$/)
    expect(createRequest.body.document.current_era.narrative).toBe('Old teaser.')
    expect(createRequest.body.document.current_era.sections[0]).toEqual({
      type: 'prose',
      text: 'Old teaser.',
    })
    expect(JSON.stringify(createRequest.body)).not.toContain('save-1')
    expect(JSON.stringify(createRequest.body)).not.toContain('mock\\\\save.sav')

    await storyTitle.fill('The UNE Chronicle, Revised')
    await page.getByRole('dialog', { name: 'Share Chronicle' }).getByRole('button', { name: 'Update story' }).click()
    await expect(page.getByText('Your public link works now. Archive and search discovery are pending review, so the story remains noindex.')).toBeVisible()

    const updateRequest = await backend.waitForPublicationRequest((request) => request.method === 'PUT')
    expect(updateRequest.body.expected_revision).toBe(1)
    expect(updateRequest.body.visibility).toBe('discoverable')
    expect(updateRequest.body.title).toBe('The UNE Chronicle, Revised')

    await page.getByText('Manage publication', { exact: true }).click()
    await page.getByRole('button', { name: 'Remove published story' }).click()
    await page.getByRole('button', { name: 'Confirm permanent removal' }).click()
    await expect(page.getByText('Chronicle published')).not.toBeVisible()

    const deleteRequest = await backend.waitForPublicationRequest((request) => request.method === 'DELETE')
    expect(deleteRequest.body.expected_revision).toBe(2)
  } finally {
    await app.close()
    await backend.stop()
    await fs.rm(userDataDir, { recursive: true, force: true })
  }
})

test('updating an existing unlisted Chronicle preserves its visibility', async () => {
  const backend = createMockChronicleBackend()
  const backendPort = await backend.start()
  const userDataDir = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-companion-unlisted-e2e-'))
  const app = await launchApp(backendPort, userDataDir)

  try {
    const page = await app.firstWindow()
    await page.waitForLoadState('domcontentloaded')
    await page.getByRole('button', { name: /Chronicle/i }).click()
    await expect(page.getByText('Old teaser.')).toBeVisible()

    // Seed a publication from the previous UI through the real IPC against the local mock.
    const seeded = await page.evaluate(() => window.electronAPI.chroniclePublishing.publish({
      saveId: 'save-1',
      title: 'Existing unlisted story',
      empireName: 'United Nations of Earth',
      language: 'en',
      visibility: 'unlisted',
      document: {
        chapters: [],
        current_era: {
          start_date: '2200.01.01',
          events_covered: 2,
          narrative: 'Old teaser.',
          sections: [{ type: 'prose', text: 'Old teaser.' }],
        },
      },
    }))
    expect(seeded.ok, JSON.stringify(seeded)).toBe(true)

    await page.getByRole('button', { name: 'Share Chronicle' }).click()
    await expect(page.getByText('This story is private-by-link and excluded from search discovery.')).toBeVisible()
    await page.getByLabel('Story title').fill('Updated unlisted story')
    await page.getByRole('dialog', { name: 'Share Chronicle' }).getByRole('button', { name: 'Update story' }).click()

    const request = await backend.waitForPublicationRequest(request => request.method === 'PUT')
    expect(request.body.visibility).toBe('unlisted')
    expect(request.body.title).toBe('Updated unlisted story')
    await expect(page.getByText('This story is private-by-link and excluded from search discovery.')).toBeVisible()
  } finally {
    await app.close()
    await backend.stop()
    await fs.rm(userDataDir, { recursive: true, force: true })
  }
})
