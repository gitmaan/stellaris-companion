const fs = require('fs/promises')
const os = require('os')
const path = require('path')

const { test, expect, _electron: electron } = require('@playwright/test')

const { createMockChronicleBackend } = require('./helpers/mockBackend')

const electronDir = path.resolve(__dirname, '..')

async function launchApp(backendPort, userDataDir) {
  return electron.launch({
    args: [path.join(electronDir, 'main.js')],
    env: {
      ...process.env,
      NODE_ENV: 'test',
      E2E: '1',
      E2E_ONBOARDING_COMPLETE: '1',
      E2E_BACKEND_CONFIGURED: '1',
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

    await page.getByRole('button', { name: 'Publish' }).click()
    await expect(page.getByRole('dialog', { name: 'Publish Chronicle' })).toBeVisible()
    await expect(page.getByText(/without creating an account/)).toBeVisible()
    await expect(page.getByText('Never your save file, save path, API key, prompts, or AI provider details.')).toBeVisible()
    await expect(page.getByRole('radio', { name: /Anyone with the link/ })).toBeChecked()

    const storyTitle = page.getByLabel('Story title')
    await storyTitle.fill('The UNE Chronicle')
    await page.getByRole('button', { name: 'Publish story' }).click()

    await expect(page.getByText('Story published')).toBeVisible()
    await expect(page.getByText('This story is private-by-link and excluded from search discovery.')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Copy link' })).toBeVisible()

    const createRequest = await backend.waitForPublicationRequest((request) => request.method === 'POST')
    expect(createRequest.headers.authorization).toMatch(/^Bearer [A-Za-z0-9_-]{43}$/)
    expect(createRequest.headers['x-publisher-id']).toMatch(/^[0-9a-f-]{36}$/)
    expect(createRequest.body.title).toBe('The UNE Chronicle')
    expect(createRequest.body.empire_name).toBe('United Nations of Earth')
    expect(createRequest.body.visibility).toBe('unlisted')
    expect(createRequest.body.client_publication_id).toMatch(/^[0-9a-f-]{36}$/)
    expect(createRequest.body.document.current_era.narrative).toBe('Old teaser.')
    expect(createRequest.body.document.current_era.sections[0]).toEqual({
      type: 'prose',
      text: 'Old teaser.',
    })
    expect(JSON.stringify(createRequest.body)).not.toContain('save-1')
    expect(JSON.stringify(createRequest.body)).not.toContain('mock\\\\save.sav')

    await page.getByText('Request public discovery', { exact: true }).click()
    await expect(page.getByRole('radio', { name: /Request public discovery/ })).toBeChecked()
    await page.getByRole('button', { name: 'Update story' }).click()
    await expect(page.getByText('Your link works now. Public discovery is pending review, so the story remains noindex.')).toBeVisible()

    const updateRequest = await backend.waitForPublicationRequest((request) => request.method === 'PUT')
    expect(updateRequest.body.expected_revision).toBe(1)
    expect(updateRequest.body.visibility).toBe('discoverable')

    await page.getByRole('button', { name: 'Remove published story' }).click()
    await page.getByRole('button', { name: 'Confirm permanent removal' }).click()
    await expect(page.getByText('Story published')).not.toBeVisible()

    const deleteRequest = await backend.waitForPublicationRequest((request) => request.method === 'DELETE')
    expect(deleteRequest.body.expected_revision).toBe(2)
  } finally {
    await app.close()
    await backend.stop()
    await fs.rm(userDataDir, { recursive: true, force: true })
  }
})
