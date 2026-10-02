const fs = require('fs/promises')
const os = require('os')
const path = require('path')
const { test, expect, _electron: electron } = require('@playwright/test')
const { createMockChronicleBackend } = require('./helpers/mockBackend')
const { getElectronLaunchArgs } = require('./helpers/electronLaunch')
const proof = process.env.CONTINUITY_SCREENSHOTS || path.resolve(__dirname, '../../artifacts/campaign-continuity')
const chapter = (number, title, text) => ({ id: `chapter-${number}`, number, title, narrative: text, start_date: `220${number - 1}.01.01`, end_date: `220${number}.01.01`, summary: '', is_finalized: true, context_stale: false, can_regenerate: true })
const chapters = [chapter(1, 'A Quiet Beginning', 'The first survey ships left Sol with a modest promise: to return with a map worth following.\n\nOn Earth, the assembly approved a new colony ship. Engineers carried their plans to the docks, while scientists argued over the faint signals arriving from nearby stars.'), chapter(2, 'Beyond the Familiar', Array.from({ length: 8 }, (_, i) => `Record ${i + 1}. The crews explored another stretch of the frontier. Each report made the distance from Earth feel smaller, and the responsibilities waiting there more tangible.`).join('\n\n'))]
async function screenshot(page, filename) { await fs.mkdir(proof, { recursive: true }); await page.screenshot({ path: path.join(proof, filename), animations: 'disabled' }) }
async function withApp(backend, run) {
  const port = await backend.start()
  const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-continuity-'))
  let app
  try {
    app = await electron.launch({ args: getElectronLaunchArgs(path.resolve(__dirname, '..', 'main.js')), env: { ...process.env, NODE_ENV: 'test', E2E: '1', E2E_ONBOARDING_COMPLETE: '1', E2E_BACKEND_CONFIGURED: '1', E2E_SKIP_BACKEND_AUTOSTART: '1', E2E_HEALTH_CHECK_INTERVAL_MS: '200', E2E_USER_DATA_DIR: profile, STELLARIS_API_PORT: String(port), STELLARIS_API_TOKEN: 'e2e-token' } })
    const page = await app.firstWindow(); await page.waitForLoadState('domcontentloaded'); await run(page, app)
  } finally { if (app) await app.close(); await backend.stop(); await fs.rm(profile, { recursive: true, force: true }) }
}
async function manual(page) { await page.evaluate(() => window.electronAPI.saveSettings({ chronicleRefreshMode: 'manual' })); await page.reload(); await expect(page.getByPlaceholder('HOW CAN WE HELP?')).toBeEnabled() }

test('Advisor restores saved chats, preserves New Chat history and keeps source dates', async () => {
  const backend = createMockChronicleBackend({ chatResponse: 'Build two science ships, then survey the nearby chokepoint. Keep an alloy reserve before committing to another colony.' })
  await withApp(backend, async (page, app) => {
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setSize(1280, 900))
    const input = page.getByPlaceholder('HOW CAN WE HELP?'); await expect(input).toBeEnabled()
    await input.fill('What should I prioritize over the next five years?'); await page.getByRole('button', { name: 'SEND', exact: true }).click()
    await expect(page.getByText('Based on save 2205.01.01')).toBeVisible()
    await page.reload(); await expect(page.getByText('Build two science ships, then survey the nearby chokepoint. Keep an alloy reserve before committing to another colony.')).toBeVisible()
    await page.getByRole('button', { name: 'New Chat', exact: true }).click(); await expect(input).toBeEnabled()
    await input.fill('Can I afford another colony?'); await page.getByRole('button', { name: 'SEND', exact: true }).click()
    await expect.poll(() => backend.getChatRequests().length).toBe(2); await expect(page.getByText('Based on save 2205.01.01')).toBeVisible()
    await page.getByRole('button', { name: 'Chats ▾' }).click(); await expect(page.getByRole('menuitem', { name: /What should I prioritize/ })).toBeVisible()
    await screenshot(page, 'advisor-saved-chats.png')
    await page.getByRole('menuitem', { name: /What should I prioritize/ }).click(); await expect(page.getByText('What should I prioritize over the next five years?', { exact: true })).toBeVisible()
    expect(backend.getChatRequests()[0].request_id).toBeTruthy(); expect(backend.getChatRequests()[0].save_id).toBe('save-1')
  })
})

test('Chronicle shows coverage, protects native edits, and supports targeted undo', async () => {
  await withApp(createMockChronicleBackend({ chapters }), async (page, app) => {
    await manual(page); await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setSize(1280, 900)); await page.getByRole('button', { name: /Chronicle/i }).click()
    await expect(page.getByText('Story covers through 2205.01.01')).toBeVisible()
    const block = page.locator('#chapter-1'); await block.locator('summary').click(); await expect(block.getByRole('button', { name: 'Edit text', exact: true })).toBeEnabled()
    await screenshot(page, 'chronicle-chapter-actions.png'); await block.getByRole('button', { name: 'Edit text', exact: true }).click()
    await page.getByRole('textbox', { name: 'Chapter title', exact: true }).fill('The First Survey')
    await page.getByRole('textbox', { name: 'Chapter text', exact: true }).fill('The survey crews returned to Sol with a carefully checked map.\n\nThe assembly chose patience, and the next colony waited until the docks were ready.')
    await page.getByRole('button', { name: 'Save changes', exact: true }).scrollIntoViewIfNeeded(); await screenshot(page, 'chronicle-native-editor.png'); await page.getByRole('button', { name: 'Save changes', exact: true }).click()
    await expect(block.getByRole('heading', { name: 'The First Survey' })).toBeVisible(); await page.reload(); await page.getByRole('button', { name: /Chronicle/i }).click()
    await expect(block.getByRole('heading', { name: 'The First Survey' })).toBeVisible(); await block.locator('summary').click()
    await expect(block.getByText('Edited by you · preserved during updates')).toBeVisible(); await block.getByRole('button', { name: 'Undo latest change' }).click()
    await expect(block.getByRole('heading', { name: 'A Quiet Beginning' })).toBeVisible(); await expect(page.locator('#chapter-2').getByRole('heading', { name: 'Beyond the Familiar' })).toBeVisible()
  })
})

test('Manual mode suppresses passive work across ingestion and focus; explicit update works', async () => {
  const backend = createMockChronicleBackend({ chapters })
  await withApp(backend, async page => {
    await manual(page); await page.getByRole('button', { name: /Chronicle/i }).click(); await expect(page.getByText('Story covers through 2205.01.01')).toBeVisible()
    backend.advanceCampaign(); await page.evaluate(() => window.dispatchEvent(new Event('focus'))); await expect(page.locator('.status-bar')).toContainText('2208.01.01'); await page.waitForTimeout(1200)
    expect(backend.getChronicleRequests()).toHaveLength(0)
    await page.getByRole('button', { name: /Update|Generate/i }).first().click(); await expect.poll(() => backend.getChronicleRequests().length).toBe(1)
    expect(backend.getChronicleRequests()[0]).toMatchObject({ force_refresh: true, refresh_mode: 'manual' }); await expect(page.getByText('Story covers through 2208.01.01')).toBeVisible()
  })
})

test('Chronicle resumes a paragraph after reload without moving on passive updates', async () => {
  const backend = createMockChronicleBackend({ chapters })
  await withApp(backend, async page => {
    await manual(page); await page.getByRole('button', { name: /Chronicle/i }).click(); await expect(page.locator('#chapter-2')).toBeAttached()
    const reader = page.locator('.absolute.inset-0.overflow-y-auto.p-6')
    await reader.evaluate(container => { const paragraph = container.querySelector('#chapter-2 .chronicle-narrative p:nth-child(4)'); container.scrollTop += paragraph.getBoundingClientRect().top - container.getBoundingClientRect().top + 30 })
    await expect.poll(() => page.evaluate(() => JSON.parse(localStorage.getItem('chronicle-reading:save-1:en') || 'null')?.anchor)).toBe('chapter-2')
    const before = await reader.evaluate(container => container.scrollTop); backend.advanceCampaign(); await page.waitForTimeout(600)
    expect(await reader.evaluate(container => container.scrollTop)).toBeCloseTo(before, 0)
    await page.reload(); await page.getByRole('button', { name: /Chronicle/i }).click(); await expect.poll(() => reader.evaluate(container => container.scrollTop)).toBeGreaterThan(before - 40)
    expect(await reader.evaluate(container => container.scrollTop)).toBeLessThan(before + 40); await screenshot(page, 'chronicle-resumed-reading.png')
  })
})

test('a conflicting chapter save retains the draft and explains how to recover', async () => {
  await withApp(createMockChronicleBackend({ chapters, editConflict: true }), async page => {
    await manual(page); await page.getByRole('button', { name: /Chronicle/i }).click(); const block = page.locator('#chapter-1')
    await block.locator('summary').click(); await block.getByRole('button', { name: 'Edit text', exact: true }).click()
    const text = page.getByRole('textbox', { name: 'Chapter text', exact: true }); await text.fill('My unsaved draft stays here.'); await page.getByRole('button', { name: 'Save changes', exact: true }).click()
    await expect(page.getByText(/This chapter changed while you were editing/)).toBeVisible(); await expect(text).toHaveValue('My unsaved draft stays here.'); await screenshot(page, 'chronicle-conflict-recovery.png')
  })
})

test('long chats paginate without losing history or mixing old follow-ups into the current conversation', async () => {
  const turns = Array.from({ length: 160 }, (_, index) => ({ id: `turn-${index}`, question: `Question ${index}`, answer: `Saved answer ${index}`, game_date: '2205.01.01', created_at: 1000 + index, response_time_ms: 12 }))
  await withApp(createMockChronicleBackend({ conversations: [{ id: 'long-chat', save_id: 'save-1', title: 'Long chat', created_at: 1000, updated_at: 1160, turn_count: 160, last_game_date: '2205.01.01', turns }] }), async page => {
    await expect(page.getByText('Saved answer 159', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Earlier messages' }).click()
    await expect(page.getByText('Saved answer 9', { exact: true })).toBeVisible()
    await expect(page.getByPlaceholder('HOW CAN WE HELP?')).toBeDisabled()
    await page.getByRole('button', { name: 'Return to latest' }).click()
    await expect(page.getByText('Saved answer 159', { exact: true })).toBeVisible()
    await expect(page.getByPlaceholder('HOW CAN WE HELP?')).toBeEnabled()
  })
})

test('unavailable history is disclosed while a new Advisor question remains usable', async () => {
  const backend = createMockChronicleBackend({ historyUnavailable: true })
  await withApp(backend, async page => {
    await expect(page.getByRole('button', { name: 'Chat history unavailable · Retry' })).toBeVisible()
    const input = page.getByPlaceholder('HOW CAN WE HELP?'); await expect(input).toBeEnabled()
    await input.fill('What is the current priority?'); await page.getByRole('button', { name: 'SEND', exact: true }).click()
    await expect(page.getByText('Mock strategic response.')).toBeVisible()
    await expect(page.getByText('This reply could not be saved.')).toBeVisible()
    backend.setHistoryUnavailable(false)
    await input.fill('Can I build another science ship?'); await page.getByRole('button', { name: 'SEND', exact: true }).click()
    await expect.poll(() => backend.getChatRequests().length).toBe(2)
    expect(backend.getChatRequests()[1].conversation_id).toBeUndefined()
    await expect(page.getByRole('button', { name: 'Chat history unavailable · Retry' })).toHaveCount(0)
  })
})

test('the compact settings panel offers Manual and persists it', async () => {
  await withApp(createMockChronicleBackend({ chapters }), async (page, app) => {
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setSize(1000, 720))
    await page.getByRole('button', { name: /Config/ }).click()
    const choice = page.getByRole('button').filter({ hasText: /^ManualOn request$/ })
    await choice.click(); await expect(choice).toHaveAttribute('aria-pressed', 'true')
    await screenshot(page, 'manual-refresh-settings-1000x720.png')
    await page.reload(); await page.getByRole('button', { name: /Config/ }).click(); await expect(choice).toHaveAttribute('aria-pressed', 'true')
  })
})
