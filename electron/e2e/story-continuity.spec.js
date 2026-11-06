const fs = require('fs/promises')
const os = require('os')
const path = require('path')
const { test, expect, _electron: electron } = require('@playwright/test')
const { createMockChronicleBackend } = require('./helpers/mockBackend')
const { getElectronLaunchArgs } = require('./helpers/electronLaunch')

async function captureProof(page, filename) {
  if (!process.env.STORY_CONTINUITY_SCREENSHOTS) return
  await fs.mkdir(process.env.STORY_CONTINUITY_SCREENSHOTS, { recursive: true })
  await page.screenshot({ path: path.join(process.env.STORY_CONTINUITY_SCREENSHOTS, filename), animations: 'disabled' })
}

async function scenario(run, options = {}) {
  const backend = createMockChronicleBackend({
    campaigns: [{ saveId: 'save-new', empireName: 'Barcalan Collective', current: true, hasChronicle: true }],
    story: {
      save_id: 'save-new', revision: 'story_none', offer_revision: 'offer-1', can_decide: true,
      status: 'separate', parts: [],
      candidates: [{ save_id: 'save-old', empire_name: 'Omnian Core', snapshot_id: 1, game_date: '2300.01.01' }],
    },
    storyParts: [{ save_id: 'save-old', empire_name: 'Omnian Core', snapshot_id: 1, game_date: '2300.01.01',
      chronicle: 'The old Core remembers.', discussions: [{ question: 'Protect the old core.', answer: 'Fortify its borders.', game_date: '2300.01.01', language: 'en' }] }],
    ...options,
  })
  backend.setHealth({ save_id: 'save-new', empire_name: 'Barcalan Collective', game_date: '2301.01.01' })
  const port = await backend.start()
  const userDataDir = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-story-e2e-'))
  let app
  try {
    app = await electron.launch({
      args: getElectronLaunchArgs(path.resolve(__dirname, '..', 'main.js')),
      env: { ...process.env, NODE_ENV: 'test', E2E: '1', E2E_ONBOARDING_COMPLETE: '1',
        E2E_BACKEND_CONFIGURED: '1', E2E_FAKE_SECURE_STORAGE: '1', E2E_SKIP_BACKEND_AUTOSTART: '1',
        E2E_USER_DATA_DIR: userDataDir, STELLARIS_API_PORT: String(port), STELLARIS_API_TOKEN: 'e2e-token' },
    })
    const page = await app.firstWindow()
    await page.waitForLoadState('domcontentloaded')
    await run(page)
  } finally {
    if (app) await app.close()
    await backend.stop()
    await fs.rm(userDataDir, { recursive: true, force: true })
  }
}

test('continue story exposes the earlier archive in Advisor and Chronicle', async () => {
  await scenario(async page => {
    const panel = page.getByRole('region', { name: 'Story continuity' })
    await expect(panel.getByText('Continue an earlier story?')).toBeVisible()
    await captureProof(page, 'story-choice.png')
    await panel.getByRole('button', { name: 'Continue story', exact: true }).click()
    await expect(panel.getByText('Story continues from Omnian Core.')).toBeVisible()
    await panel.getByRole('button', { name: 'Earlier in this story' }).click()
    const archive = page.getByRole('dialog', { name: 'Earlier in this story' })
    await expect(archive.getByText('The old Core remembers.')).toBeVisible()
    await archive.getByText('Recent earlier discussions').click()
    await expect(archive.getByText('Protect the old core.')).toBeVisible()
    await captureProof(page, 'earlier-story.png')
    await archive.getByRole('button', { name: 'Close', exact: true }).click()
    await page.getByRole('button', { name: /Chronicle/i }).click()
    await expect(panel.getByText('Story continues from Omnian Core.')).toBeVisible()
    await panel.getByRole('button', { name: 'Earlier in this story' }).click()
    await archive.getByRole('button', { name: 'Disconnect story' }).click()
    await expect(archive).not.toBeVisible()
    await expect(panel).not.toBeVisible()
  })
})

test('keeping separate dismisses the offer without exposing earlier prose', async () => {
  await scenario(async page => {
    const panel = page.getByRole('region', { name: 'Story continuity' })
    await panel.getByRole('button', { name: 'Keep separate' }).click()
    await expect(panel).not.toBeVisible()
    await page.getByRole('button', { name: /Chronicle/i }).click()
    await expect(panel).not.toBeVisible()
  })
})

test('a stale story choice displays an error without linking', async () => {
  await scenario(async page => {
    const panel = page.getByRole('region', { name: 'Story continuity' })
    await panel.getByRole('button', { name: 'Continue story', exact: true }).click()
    await expect(panel.getByRole('alert')).toContainText('The campaign or story changed.')
    await expect(panel.getByRole('button', { name: 'Earlier in this story' })).not.toBeVisible()
  }, { storyConflict: true })
})
