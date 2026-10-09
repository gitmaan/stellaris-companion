const fs = require('node:fs/promises')
const os = require('node:os')
const path = require('node:path')
const { test, expect, _electron: electron } = require('@playwright/test')
const { createMockChronicleBackend } = require('./helpers/mockBackend')
const { getElectronLaunchArgs } = require('./helpers/electronLaunch')

const electronDir = path.resolve(__dirname, '..')

function announcement(id) {
  return { id, severity: 'info', title: `Fictional transmission: ${id}`, body: 'A local test announcement.', publishedAt: '2020-01-01T00:00:00Z' }
}

async function setup(settings) {
  const backend = createMockChronicleBackend()
  const port = await backend.start()
  const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-transmissions-e2e-'))
  const saves = path.join(profile, 'fictional-saves')
  await fs.mkdir(saves)
  await fs.writeFile(path.join(profile, 'settings.json'), JSON.stringify({ language: 'en', ...settings }))
  let app
  return {
    async launch(items) {
      if (app) await app.close()
      app = await electron.launch({
        args: getElectronLaunchArgs(path.join(electronDir, 'main.js')),
        env: {
          ...process.env,
          NODE_ENV: 'test', E2E: '1', E2E_SKIP_BACKEND_AUTOSTART: '1',
          E2E_USER_DATA_DIR: profile, E2E_SAVE_DIR: saves,
          E2E_ANNOUNCEMENTS_FIXTURE: JSON.stringify({ version: 1, announcements: items }),
          STELLARIS_API_PORT: String(port), STELLARIS_API_TOKEN: 'fictional-transmissions-token',
        },
      })
      return app.firstWindow()
    },
    async hide() {
      await app.evaluate(async ({ BrowserWindow }) => {
        const window = BrowserWindow.getAllWindows()[0]
        await new Promise((resolve) => {
          window.once('hide', () => resolve())
          window.hide()
        })
      })
    },
    async show() {
      await app.evaluate(async ({ BrowserWindow }) => {
        const window = BrowserWindow.getAllWindows()[0]
        await new Promise((resolve) => {
          window.once('show', () => resolve())
          window.show()
        })
        window.focus()
      })
    },
    async updateFeed(items, push = false) {
      await app.evaluate(({ BrowserWindow }, { items, push }) => {
        process.env.E2E_ANNOUNCEMENTS_FIXTURE = JSON.stringify({ version: 1, announcements: items })
        if (push) BrowserWindow.getAllWindows()[0].webContents.send('announcements-updated', items)
      }, { items, push })
    },
    async dispose() {
      if (app) await app.close().catch(() => {})
      await backend.stop()
      await fs.rm(profile, { recursive: true, force: true })
    },
  }
}

async function readIds(page) {
  return page.evaluate(() => window.electronAPI.announcements.getReadIds())
}

test('a transmission opens once across launches, and a delayed new ID still opens', async ({}, testInfo) => {
  test.setTimeout(90_000)
  const first = announcement('first')
  const delayed = announcement('delayed')
  const dismissed = announcement('dismissed')
  const fixture = await setup({ hasCompletedOnboarding: true, announcementsDismissed: [dismissed.id] })
  try {
    let page = await fixture.launch([first, dismissed])
    await expect(page.getByRole('heading', { name: first.title })).toBeVisible()
    await expect(page.getByRole('heading', { name: dismissed.title })).toHaveCount(0)
    await expect.poll(() => readIds(page)).toEqual([first.id])
    await page.screenshot({ path: testInfo.outputPath('transmission-opened.png'), animations: 'disabled' })
    await page.keyboard.press('Escape')
    await expect(page.getByRole('heading', { name: first.title })).toHaveCount(0)

    page = await fixture.launch([first, dismissed])
    await expect(page.getByTitle('Transmissions', { exact: true })).toBeVisible()
    await expect.poll(() => readIds(page)).toEqual([first.id])
    // Observe longer than the panel's entrance animation to catch a repeat auto-open.
    await page.waitForTimeout(500)
    await expect(page.getByRole('heading', { name: first.title })).toHaveCount(0)
    await page.getByTitle('Transmissions', { exact: true }).click()
    await expect(page.getByRole('heading', { name: first.title })).toBeVisible()

    page = await fixture.launch([first, delayed, dismissed])
    await expect(page.getByRole('heading', { name: delayed.title })).toBeVisible()
    await expect.poll(() => readIds(page)).toEqual([first.id, delayed.id])
    await expect(page.getByRole('heading', { name: dismissed.title })).toHaveCount(0)
    await page.getByRole('button', { name: 'Dismiss', exact: true }).last().click()
    await page.getByRole('button', { name: 'Dismiss', exact: true }).click()
    await expect(page.getByTitle('Transmissions', { exact: true })).toHaveCount(0)

    page = await fixture.launch([first, delayed, dismissed])
    await expect(page.getByRole('button', { name: /Config/ })).toBeVisible()
    await expect(page.getByRole('heading', { name: delayed.title })).toHaveCount(0)
    expect((await page.evaluate(() => window.electronAPI.announcements.getDismissed())).sort()).toEqual(['delayed', 'dismissed', 'first'])
  } finally {
    await fixture.dispose()
  }
})

test('first-run onboarding finishes before transmissions are opened or marked read', async () => {
  test.setTimeout(60_000)
  const item = announcement('after-onboarding')
  const fixture = await setup({ hasCompletedOnboarding: false })
  try {
    const page = await fixture.launch([item])
    await expect(page.getByRole('dialog')).toBeVisible()
    // The status-bar entry proves the feed has arrived while onboarding is open.
    await expect(page.getByRole('button', { name: /Transmissions/ })).toBeAttached()
    await expect(page.getByRole('heading', { name: item.title })).toHaveCount(0)
    expect(await readIds(page)).toEqual([])
    await page.getByRole('button', { name: 'Get started', exact: true }).click()
    await page.getByRole('button', { name: 'Set up later', exact: true }).click()
    await page.getByRole('heading', { name: 'Find your saves', exact: true }).waitFor()
    expect(await readIds(page)).toEqual([])
    await page.getByRole('button', { name: 'Set up later', exact: true }).click()
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await expect(page.getByRole('heading', { name: item.title })).toBeVisible()
    await expect.poll(() => readIds(page)).toEqual([item.id])
  } finally {
    await fixture.dispose()
  }
})

test('reopening from the tray refreshes the feed and does not lose hidden transmissions', async () => {
  test.setTimeout(60_000)
  const first = announcement('first')
  const hidden = announcement('received-while-hidden')
  const fresh = announcement('fresh-on-reopen')
  const fixture = await setup({ hasCompletedOnboarding: true })
  try {
    const page = await fixture.launch([first])
    await expect(page.getByRole('heading', { name: first.title })).toBeVisible()
    await expect.poll(() => readIds(page)).toEqual([first.id])
    await page.keyboard.press('Escape')
    await expect(page.getByRole('heading', { name: first.title })).toHaveCount(0)

    await fixture.hide()
    await expect.poll(() => page.evaluate(() => window.electronAPI.getWindowVisible())).toBe(false)
    await fixture.updateFeed([first, hidden], true)
    await expect(page.getByTitle('Transmissions', { exact: true }).locator('.animate-pulse')).toHaveCount(1)
    expect(await readIds(page)).toEqual([first.id])
    await expect(page.getByRole('heading', { name: hidden.title })).toHaveCount(0)

    await fixture.show()
    await expect(page.getByRole('heading', { name: hidden.title })).toBeVisible()
    await expect.poll(() => readIds(page)).toEqual([first.id, hidden.id])
    await page.keyboard.press('Escape')
    await expect(page.getByRole('heading', { name: hidden.title })).toHaveCount(0)

    await fixture.hide()
    await expect.poll(() => page.evaluate(() => window.electronAPI.getWindowVisible())).toBe(false)
    // No push: visibility alone must refresh a feed that changed in the tray.
    await fixture.updateFeed([first, hidden, fresh])
    expect(await page.evaluate(async () => (await window.electronAPI.announcements.fetch(true)).map((item) => item.id))).toEqual([first.id, hidden.id, fresh.id])
    await fixture.show()
    await expect(page.getByRole('heading', { name: fresh.title })).toBeVisible()
    await expect.poll(() => readIds(page)).toEqual([first.id, hidden.id, fresh.id])
  } finally {
    await fixture.dispose()
  }
})
