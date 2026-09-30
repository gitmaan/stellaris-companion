const fs = require('fs/promises')
const os = require('os')
const path = require('path')
const { test, expect, _electron: electron } = require('@playwright/test')
const { createMockChronicleBackend } = require('./helpers/mockBackend')
const { getElectronLaunchArgs } = require('./helpers/electronLaunch')

async function launchRelay() {
  const backend = createMockChronicleBackend()
  const port = await backend.start()
  const profile = await fs.mkdtemp(path.join(os.tmpdir(), 'stellaris-relay-e2e-'))
  const app = await electron.launch({
    args: getElectronLaunchArgs(path.resolve(__dirname, '..', 'main.js')),
    env: { ...process.env, NODE_ENV: 'test', E2E: '1', E2E_ONBOARDING_COMPLETE: '1', E2E_BACKEND_CONFIGURED: '1', E2E_FAKE_SECURE_STORAGE: '1', E2E_SKIP_BACKEND_AUTOSTART: '1', E2E_USER_DATA_DIR: profile, STELLARIS_API_PORT: String(port), STELLARIS_API_TOKEN: 'e2e-token' },
  })
  // Replace setup handlers before using any action; never touch installed AI apps.
  await app.evaluate(({ ipcMain }) => {
    globalThis.relayFixture = {
      clients: {
        claude: { configured: false, current: false },
        codex: { configured: false, current: false, available: false },
        cursor: { configured: false, current: false },
      },
      campaignReady: true, failConnect: false,
    }
    const state = globalThis.relayFixture
    const status = () => ({
      clients: state.clients, language: 'en', logPath: '/sample/mcp.log',
      snippets: { genericJson: '{"mcpServers":{"stellaris-companion":{}}}', codex: 'codex mcp add stellaris-companion -- sample-server' },
    })
    for (const name of ['status', 'health-check', 'connect-client', 'disconnect-client']) ipcMain.removeHandler(`mcp-relay:${name}`)
    ipcMain.handle('mcp-relay:status', () => status())
    ipcMain.handle('mcp-relay:health-check', () => ({ ok: true, serverHealthy: true, campaignReady: state.campaignReady, message: 'Ready', campaign: { empire_name: 'United Nations of Earth', game_date: '2242.06.01' } }))
    ipcMain.handle('mcp-relay:connect-client', (_event, { client }) => {
      if (state.failConnect) return { success: false, error: 'fixture: configuration write failed', status: status() }
      state.clients[client] = { configured: true, current: true }
      return { success: true, status: status() }
    })
    ipcMain.handle('mcp-relay:disconnect-client', (_event, { client }) => {
      state.clients[client] = { configured: false, current: false }
      return { success: true, status: status() }
    })
  })
  const page = await app.firstWindow()
  await page.waitForLoadState('domcontentloaded')
  await page.getByRole('button', { name: /Config/i }).click()
  await page.getByRole('button', { name: /Connect your AI app/ }).click()
  return { app, page, panel: page.locator('#ai-app-connections'), cleanup: async () => { await app.close(); await backend.stop(); await fs.rm(profile, { recursive: true, force: true }) } }
}

test('guides app setup and keeps first questions available when returning to Settings', async ({}, testInfo) => {
  const { app, page, panel, cleanup } = await launchRelay()
  try {
    const before = await page.evaluate(() => window.electronAPI.getSettings())
    await expect(panel.getByText('Campaign ready · United Nations of Earth · 2242.06.01')).toBeVisible()
    await expect(panel.getByRole('heading', { name: 'MCP RELAY', exact: true })).toBeVisible()
    await expect(panel.getByText('Setup added. Restart your AI app to use it.')).toHaveCount(0)
    await panel.getByRole('button', { name: 'Add to Claude Desktop', exact: true }).click()
    await expect(panel.getByText('Setup added. Restart your AI app to use it.')).toBeVisible()
    await expect(panel.getByText('CONNECTED', { exact: true })).toHaveCount(0)
    await panel.getByRole('button', { name: 'Copy question', exact: true }).click()
    expect(await app.evaluate(({ clipboard }) => clipboard.readText())).toBe('Use Stellaris Companion to summarize my empire and suggest my next three priorities.')
    await panel.getByRole('button', { name: 'Chronicle', exact: true }).click()
    await panel.getByRole('button', { name: 'Copy question', exact: true }).click()
    expect(await app.evaluate(({ clipboard }) => clipboard.readText())).toContain('Show me the draft before saving.')
    await expect(panel.getByText(/Review the draft, then ask/)).toBeVisible()
    await page.getByRole('button', { name: /Chat in Companion/ }).click()
    await expect(page.getByTestId('ai-setup-form')).toBeVisible()
    await page.getByRole('button', { name: /Connect your AI app/ }).click()
    await expect(panel.getByText('Setup added. Restart your AI app to use it.')).toBeVisible()
    await panel.getByRole('button', { name: 'ChatGPT desktop', exact: true }).click()
    await expect(panel.getByText(/Open or install ChatGPT desktop/)).toBeVisible()
    await expect(panel.getByRole('button', { name: 'Add to ChatGPT desktop', exact: true })).toBeDisabled()
    await expect(panel.getByText(/ChatGPT web uses a different setup/)).toBeVisible()
    const after = await page.evaluate(() => window.electronAPI.getSettings())
    expect(after.advisorProvider).toBe(before.advisorProvider)
    expect(after.googleApiKeySet).toBe(before.googleApiKeySet)
    await panel.getByRole('button', { name: 'Claude Desktop', exact: true }).click()
    await page.screenshot({ path: testInfo.outputPath('relay-settings.png') })
  } finally { await cleanup() }
})

test('offers recovery for failed setup and keeps campaign readiness separate', async () => {
  const { app, page, panel, cleanup } = await launchRelay()
  try {
    await app.evaluate(() => { globalThis.relayFixture.campaignReady = false; globalThis.relayFixture.failConnect = true })
    await panel.getByRole('button', { name: 'Check again', exact: true }).click()
    await expect(panel.getByText(/Load a Stellaris save in Companion/)).toBeVisible()
    await expect(panel.getByRole('button', { name: 'Choose save folder', exact: true })).toBeVisible()
    await app.evaluate(({ dialog }) => { dialog.showOpenDialog = async () => ({ canceled: true, filePaths: [] }) })
    await panel.getByRole('button', { name: 'Choose save folder', exact: true }).click()
    await panel.getByRole('button', { name: 'Cursor', exact: true }).click()
    await panel.getByRole('button', { name: 'Add to Cursor', exact: true }).click()
    await expect(panel.getByRole('alert')).toContainText('Setup needs attention.')
    await expect(panel.getByText('fixture: configuration write failed')).not.toBeVisible()
    await panel.getByText('Advanced MCP setup', { exact: true }).click()
    await expect(panel.getByText('fixture: configuration write failed')).toBeVisible()
    await app.evaluate(() => { globalThis.relayFixture.failConnect = false })
    await panel.getByRole('button', { name: 'Add to Cursor', exact: true }).click()
    await expect(panel.getByText('Setup added. Restart your AI app to use it.')).toBeVisible()
    await expect(panel.getByText(/Campaign ready ·/)).toHaveCount(0)
    page.once('dialog', dialog => dialog.accept())
    await panel.getByRole('button', { name: 'DISCONNECT', exact: true }).click()
    await expect(panel.getByRole('button', { name: 'Add to Cursor', exact: true })).toBeEnabled()
    await expect(panel.getByText('Setup added. Restart your AI app to use it.')).toHaveCount(0)
  } finally { await cleanup() }
})
