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
    },
  })
}

function historyCampaigns() {
  return [
    {
      saveId: 'save-current',
      sessionId: 'session-current',
      empireName: 'United Nations of Earth',
      current: true,
      hasChronicle: true,
      snapshotCount: 4,
      eventCount: 2,
    },
    {
      saveId: 'save-empty-1',
      empireName: 'Duplicate Start One',
      current: false,
      hasChronicle: false,
      snapshotCount: 1,
      eventCount: 0,
    },
    {
      saveId: 'save-empty-2',
      empireName: 'Duplicate Start Two',
      current: false,
      hasChronicle: false,
      snapshotCount: 0,
      eventCount: 0,
    },
  ]
}

test('campaign manager supports bulk cleanup, restore, labels, reset undo, and permanent delete', async () => {
  const backend = createMockChronicleBackend({ campaigns: historyCampaigns() })
  const backendPort = await backend.start()
  const userDataDir = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-companion-history-e2e-'))
  const app = await launchApp(backendPort, userDataDir)

  try {
    const page = await app.firstWindow()
    await page.waitForLoadState('domcontentloaded')
    await page.getByRole('button', { name: /Chronicle/i }).click()
    await expect(page.getByText('Old teaser.')).toBeVisible()

    await page.getByRole('button', { name: 'Manage campaigns' }).click()
    const dialog = page.getByRole('dialog', { name: 'Campaign History' })
    await expect(dialog).toBeVisible()
    await dialog.getByRole('button', { name: 'Select empty starts (2)' }).click()
    await dialog.getByRole('button', { name: 'Move selected to Trash (2)' }).click()
    await expect(dialog.getByRole('button', { name: 'Campaigns (1)' })).toBeVisible()

    await dialog.getByRole('button', { name: 'Trash (2)' }).click()
    const restoredRow = dialog.locator('article').filter({ hasText: 'Duplicate Start One' })
    await restoredRow.getByRole('button', { name: 'Restore' }).click()
    await dialog.getByRole('button', { name: 'Campaigns (2)' }).click()

    const activeRow = dialog.locator('article').filter({ hasText: 'Duplicate Start One' })
    await activeRow.getByRole('button', { name: 'Rename' }).click()
    await activeRow.getByPlaceholder('Duplicate Start One').fill('Clean Test Run')
    await activeRow.getByRole('button', { name: 'Save' }).click()
    await expect(dialog.getByText('Clean Test Run')).toBeVisible()

    const currentRow = dialog.locator('article').filter({ hasText: 'United Nations of Earth' })
    await currentRow.getByRole('button', { name: 'Reset Chronicle' }).click()
    await currentRow.getByRole('button', { name: 'Confirm reset' }).click()
    await expect(page.getByText('Chronicle reset. Campaign history was kept.')).toBeVisible()
    await page.getByRole('button', { name: 'Undo', exact: true }).click()

    const cleanRow = dialog.locator('article').filter({ hasText: 'Clean Test Run' })
    await cleanRow.getByRole('button', { name: 'Move to Trash' }).click()
    await dialog.getByRole('button', { name: 'Trash (2)' }).click()
    const deleteRow = dialog.locator('article').filter({ hasText: 'Clean Test Run' })
    await deleteRow.getByRole('button', { name: 'Delete permanently' }).click()
    await deleteRow.getByRole('button', { name: 'Confirm delete' }).click()
    await expect(dialog.getByText('Clean Test Run')).not.toBeVisible()
  } finally {
    await app.close()
    await backend.stop()
    await fs.rm(userDataDir, { recursive: true, force: true })
  }
})

test('selecting historical campaigns reads cache without generating Chronicle content', async () => {
  const campaigns = historyCampaigns()
  campaigns[1] = {
    ...campaigns[1],
    hasChronicle: true,
    snapshotCount: 3,
    eventCount: 1,
    narrative: 'A historical Chronicle read from cache.',
  }
  const backend = createMockChronicleBackend({ campaigns })
  const backendPort = await backend.start()
  const userDataDir = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-companion-history-cache-e2e-'))
  const app = await launchApp(backendPort, userDataDir)

  try {
    const page = await app.firstWindow()
    await page.waitForLoadState('domcontentloaded')
    await page.getByRole('button', { name: /Chronicle/i }).click()
    await expect(page.getByText('Old teaser.')).toBeVisible()
    await backend.waitForChronicleRequest(() => true)
    const generationCount = backend.getChronicleRequests().length

    await page.locator('select').filter({ has: page.locator('option', { hasText: 'Duplicate Start One' }) }).selectOption('save-empty-1')
    await expect(page.getByText('A historical Chronicle read from cache.')).toBeVisible()
    await page.waitForTimeout(750)

    expect(backend.getChronicleRequests()).toHaveLength(generationCount)
  } finally {
    await app.close()
    await backend.stop()
    await fs.rm(userDataDir, { recursive: true, force: true })
  }
})
