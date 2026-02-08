// Main process entry point
// Implements ELEC-002: Python subprocess management
// Implements ELEC-004: Settings IPC handlers (safeStorage + electron-store)
//
// Bundled Resources (see electron-builder.yml extraResources):
// - python-backend/: PyInstaller-bundled Python backend (stellaris-backend executable)
// - rust-parser/: Rust CLI parser binary (stellaris-parser) used by stellaris_companion/rust_bridge.py
//   The Rust parser handles Clausewitz save file parsing with proper edge case handling.

const { app, BrowserWindow, ipcMain, dialog, Tray, Menu, nativeImage, shell, safeStorage } = require('electron')
const { clipboard } = require('electron')
const path = require('path')
const { spawn } = require('child_process')
const crypto = require('crypto')
const { pathToFileURL, fileURLToPath } = require('url')
const Store = require('electron-store')
const net = require('net')
const { autoUpdater } = require('electron-updater')

const { createBackendClient } = require('./main/backendClient')
const { createAnnouncementsService } = require('./main/announcements')
const { createHealthCheckManager } = require('./main/healthcheck')
const { setupAutoUpdater, registerUpdateIpcHandlers, wireAutoUpdaterEvents } = require('./main/updates')
const { registerBackendIpcHandlers } = require('./main/ipc/backend')
const { registerSettingsIpcHandlers } = require('./main/ipc/settings')
const { registerExportIpcHandlers } = require('./main/ipc/export')
const { registerAnnouncementsIpcHandlers } = require('./main/ipc/announcements')
const { createDiscordOAuth } = require('./main/discord/oauth')
const { createDiscordRelay } = require('./main/discord/relay')
const { registerDiscordIpcHandlers } = require('./main/ipc/discord')

const IS_DEV = process.env.NODE_ENV === 'development'

// Configure electron-updater
setupAutoUpdater({ autoUpdater, app, isDev: IS_DEV })

// Global process error handlers (ELEC-xxx: diagnostics)
// Prevent silent failures in production builds.
let hasShownFatalErrorDialog = false
process.on('uncaughtException', async (err) => {
  console.error('Uncaught exception in main process:', err)
  if (!hasShownFatalErrorDialog && app?.isReady?.()) {
    hasShownFatalErrorDialog = true
    try {
      await dialog.showMessageBox({
        type: 'error',
        title: 'Stellaris Companion crashed',
        message: 'An unexpected error occurred in the app.',
        detail: err?.stack || String(err),
      })
    } catch (e) {
      // Ignore dialog errors
    }
  }
  try {
    app.quit()
  } catch (e) {
    // ignore
  }
})

process.on('unhandledRejection', (reason) => {
  console.error('Unhandled promise rejection in main process:', reason)
})

// Single-instance lock to prevent multiple Electron shells fighting over ports / subprocesses.
// In development, skip this to avoid focusing a hidden production instance (tray mode),
// which makes it look like code/CSS changes aren't taking effect.
if (!IS_DEV) {
  const gotSingleInstanceLock = app.requestSingleInstanceLock()
  if (!gotSingleInstanceLock) {
    app.quit()
  }
}

// Secrets are encrypted via Electron's safeStorage API and persisted in
// electron-store as base64 strings.  This replaces the deprecated keytar
// native module and eliminates architecture-mismatch crashes.
const SECRET_STORE_KEYS = {
  googleApiKey: 'secrets.google-api-key',
  discordToken: 'secrets.discord-token',
  discordAccessToken: 'secrets.discord-access-token',
  discordRefreshToken: 'secrets.discord-refresh-token',
}

function encryptSecret(plaintext) {
  if (!plaintext) return null
  if (!safeStorage.isEncryptionAvailable()) return Buffer.from(plaintext).toString('base64')
  return safeStorage.encryptString(plaintext).toString('base64')
}

function decryptSecret(stored) {
  if (!stored) return null
  const buf = Buffer.from(stored, 'base64')
  if (!safeStorage.isEncryptionAvailable()) return buf.toString('utf-8')
  try {
    return safeStorage.decryptString(buf)
  } catch {
    // Data was stored without encryption or is corrupt — treat as plaintext
    return buf.toString('utf-8')
  }
}

function getSecret(key) {
  return decryptSecret(store.get(key))
}

function setSecret(key, value) {
  if (value) {
    store.set(key, encryptSecret(value))
  } else {
    store.delete(key)
  }
}

// Initialize electron-store for non-secret settings
const store = new Store({
  name: 'settings',
  defaults: {
    // Save directory (folder) containing Stellaris "save games".
    // NOTE: Legacy key was `savePath` (directory), which is migrated on startup.
    saveDir: '',
    lastSaveFilePath: '',
    // Deprecated legacy key (kept only to avoid surprising defaults during migration).
    savePath: '',
    // Anonymous ID for rate-limiting and de-duping reports (no personal data).
    installId: '',
    discordEnabled: false,
    hasCompletedOnboarding: false,
    // Window state persistence
    windowState: {
      width: 1000,
      height: 700,
      x: undefined,
      y: undefined,
    },
    // Announcements
    announcementsDismissed: [],
    announcementsCache: null,
    announcementsLastRead: 0,
  },
})

const announcementsService = createAnnouncementsService({ app, store })

function migrateLegacySavePathToSaveDir() {
  const saveDir = store.get('saveDir', '')
  const legacySavePath = store.get('savePath', '')

  if ((!saveDir || saveDir.trim() === '') && legacySavePath && legacySavePath.trim() !== '') {
    store.set('saveDir', legacySavePath)
  }

  // Drop the legacy key so future code doesn't accidentally rely on it.
  if (legacySavePath && legacySavePath.trim() !== '') {
    store.delete('savePath')
  }
}

migrateLegacySavePathToSaveDir()

function ensureInstallId() {
  const current = store.get('installId', '')
  if (typeof current === 'string' && current.trim() !== '') return current

  let next = ''
  try {
    next = crypto.randomUUID()
  } catch {
    next = crypto.randomBytes(16).toString('hex')
  }
  store.set('installId', next)
  return next
}

ensureInstallId()

// Configuration
const BACKEND_HOST = '127.0.0.1'
const DEFAULT_BACKEND_PORT = (() => {
  const raw = process.env.STELLARIS_API_PORT
  const parsed = raw ? Number.parseInt(raw, 10) : 8742
  return Number.isFinite(parsed) && parsed > 0 && parsed <= 65535 ? parsed : 8742
})()
const HEALTH_CHECK_INTERVAL = 5000 // 5 seconds
const HEALTH_CHECK_TIMEOUT = 30000 // 30 seconds for initial startup
const HEALTH_CHECK_REQUEST_TIMEOUT = 4000 // 4 seconds per health request (increased from 2s)
const HEALTH_CHECK_FAIL_THRESHOLD = 2 // Require 2 consecutive failures before showing disconnected

// Discord configuration (DISC-007)
// These are set via environment or will use defaults for development
const DISCORD_CLIENT_ID = process.env.DISCORD_CLIENT_ID || '1460412463282524231'
const DISCORD_RELAY_URL = process.env.DISCORD_RELAY_URL || 'https://relay.galacticfilingcabinet.com'

// State
let mainWindow = null
let pythonProcess = null
let authToken = null
let backendPort = DEFAULT_BACKEND_PORT
let isQuitting = false
let tray = null
let lastTrayStatus = null // Track last status to avoid rebuilding menu unnecessarily
let backendConfigured = false
let lastBackendConnected = false
let lastBackendStatusPayload = null

/**
 * Generate a random auth token for this session.
 * The token is used to authenticate requests to the Python backend.
 */
function generateAuthToken() {
  return crypto.randomBytes(32).toString('hex')
}

/**
 * Get the path to the Python executable.
 * In development, uses system Python. In production, uses bundled backend.
 */
function getPythonPath() {
  if (app.isPackaged) {
    // In packaged app, use bundled Python backend
    const resourcePath = process.resourcesPath
    if (process.platform === 'win32') {
      return path.join(resourcePath, 'python-backend', 'stellaris-backend.exe')
    } else {
      return path.join(resourcePath, 'python-backend', 'stellaris-backend')
    }
  } else {
    // In development, try venv first, then system Python
    const fs = require('fs')
    const venvRoot = path.join(__dirname, '..', 'venv')
    const venvPythonCandidates = process.platform === 'win32'
      ? [
        path.join(venvRoot, 'Scripts', 'python.exe'),
        path.join(venvRoot, 'Scripts', 'python'),
      ]
      : [
        path.join(venvRoot, 'bin', 'python3'),
        path.join(venvRoot, 'bin', 'python'),
      ]

    for (const candidate of venvPythonCandidates) {
      if (fs.existsSync(candidate)) return candidate
    }

    // Use python3 on Unix (python may not exist on macOS)
    return process.platform === 'win32' ? 'python' : 'python3'
  }
}

/**
 * Build environment variables for the Python backend.
 * @param {Object} settings - User settings
 * @returns {Object} Environment variables
 */
function buildBackendEnv(settings) {
  const env = {
    ...process.env,
    STELLARIS_API_TOKEN: authToken,
    // DB path uses app data directory for persistence
    STELLARIS_DB_PATH: path.join(app.getPath('userData'), 'stellaris_history.db'),
    // Log path uses app data directory for persistence + rotation
    STELLARIS_LOG_DIR: path.join(app.getPath('userData'), 'logs'),
  }

  // Add Google API key if provided
  if (settings.googleApiKey) {
    env.GOOGLE_API_KEY = settings.googleApiKey
  }

  // Prefer an explicit directory, otherwise auto-detect a standard location.
  const effectiveSaveDir = getEffectiveSaveDir(settings)
  if (effectiveSaveDir) {
    env.STELLARIS_SAVE_DIR = effectiveSaveDir
  }

  // Cache hit: provide the last successfully loaded save file to skip any scans.
  if (settings.lastSaveFilePath) {
    env.STELLARIS_SAVE_PATH = settings.lastSaveFilePath
  }

  return env
}

/**
 * Start the Python backend process.
 * @param {Object} settings - User settings containing API keys
 */
function startPythonBackend(settings) {
  if (pythonProcess) {
    console.log('Python backend already running')
    return
  }

  if (!settings.googleApiKey) {
    console.log('Cannot start backend: Google API key not configured')
    return
  }

  const pythonPath = getPythonPath()
  const env = buildBackendEnv(settings)

  let args = []
  if (app.isPackaged) {
    // Packaged app runs the bundled executable directly
    args = ['--host', BACKEND_HOST, '--port', String(backendPort), '--parent-pid', String(process.pid)]
  } else {
    // Development runs the backend as a module so imports resolve naturally.
    // Note: Electron dev runs with cwd = electron/, so we set PYTHONPATH to repo root.
    env.PYTHONPATH = [
      path.join(__dirname, '..'),
      env.PYTHONPATH,
    ]
      .filter(Boolean)
      .join(process.platform === 'win32' ? ';' : ':')

    args = ['-m', 'backend.electron_main', '--host', BACKEND_HOST, '--port', String(backendPort), '--parent-pid', String(process.pid)]
  }

  console.log(`Starting Python backend: ${pythonPath} ${args.join(' ')}`)

  pythonProcess = spawn(pythonPath, args, {
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
    // Detach on Unix so we can kill the whole process group with -pid
    detached: process.platform !== 'win32',
  })

  pythonProcess.stdout.on('data', (data) => {
    console.log(`[Python] ${data.toString().trim()}`)
  })

  pythonProcess.stderr.on('data', (data) => {
    console.error(`[Python Error] ${data.toString().trim()}`)
  })

  pythonProcess.on('error', (err) => {
    console.error('Failed to start Python backend:', err)
    pythonProcess = null
  })

  pythonProcess.on('exit', (code, signal) => {
    console.log(`Python backend exited with code ${code}, signal ${signal}`)
    pythonProcess = null

    // If not quitting, notify renderer of disconnect
    if (!isQuitting && mainWindow) {
      mainWindow.webContents.send('backend-status', { connected: false })
    }
  })
}

/**
 * Stop the Python backend process.
 */
function stopPythonBackend() {
  if (!pythonProcess) {
    return Promise.resolve()
  }

  console.log('Stopping Python backend...')

  healthCheckManager.stop()

  const child = pythonProcess
  pythonProcess = null

  const waitForExit = (timeoutMs) => new Promise((resolve) => {
    let settled = false
    const settle = () => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      child.removeListener('exit', settle)
      child.removeListener('close', settle)
      resolve()
    }
    const timer = setTimeout(settle, timeoutMs)
    child.once('exit', settle)
    child.once('close', settle)
  })

  const kill = async () => {
    if (process.platform === 'win32') {
      // Windows: prefer Node-native kill. The backend is responsible for exiting its own child processes.
      try {
        child.kill()
      } catch (e) {
        // ignore
      }
      await waitForExit(1500)
      return
    }

    // Unix: try killing the process group (requires detached: true), fallback to direct kill.
    try {
      process.kill(-child.pid, 'SIGTERM')
    } catch (e) {
      try {
        child.kill('SIGTERM')
      } catch (e2) {
        // ignore
      }
    }
    await waitForExit(1500)
  }

  return kill()
}

/**
 * Restart the Python backend with new settings.
 * @param {Object} settings - New settings
 */
function restartPythonBackend(settings) {
  stopPythonBackend()
    .catch(() => {})
    .finally(() => {
      // Small delay to ensure port is released
      setTimeout(() => {
        startPythonBackend(settings)
        // Start health check after restart
        startHealthCheck()
      }, 500)
    })
}

const backendClient = createBackendClient({
  host: BACKEND_HOST,
  getPort: () => backendPort,
  getAuthToken: () => authToken,
})

// Compatibility wrappers (preserve existing call sites + export shape)
async function callBackendApiOrThrow(endpoint, options = {}) {
  return backendClient.callBackendApiOrThrow(endpoint, options)
}

async function callBackendApiEnvelope(endpoint, options = {}) {
  return backendClient.callBackendApiEnvelope(endpoint, options)
}

// =============================================================================
// Discord wiring (DISC-007 / DISC-008 / DISC-011)
// =============================================================================

const discordOAuth = createDiscordOAuth({
  clientId: DISCORD_CLIENT_ID,
  shell,
  store,
  getSecret,
  setSecret,
  secretKeys: {
    accessToken: SECRET_STORE_KEYS.discordAccessToken,
    refreshToken: SECRET_STORE_KEYS.discordRefreshToken,
  },
})

const discordRelay = createDiscordRelay({
  relayUrl: DISCORD_RELAY_URL,
  getMainWindow: () => mainWindow,
  callBackendApiOrThrow,
  getDiscordTokens: () => discordOAuth.getDiscordTokens(),
  ensureValidTokens: () => discordOAuth.ensureValidTokens(),
})

discordOAuth.setOnConnected(async () => {
  await discordRelay.startDiscordRelayIfConnected()
})

async function checkBackendHealth() {
  return callBackendApiOrThrow('/api/health', { timeoutMs: HEALTH_CHECK_REQUEST_TIMEOUT })
}

const healthCheckManager = createHealthCheckManager({
  checkBackendHealth,
  getMainWindow: () => (mainWindow && !mainWindow.isDestroyed() ? mainWindow : null),
  getBackendConfigured: () => backendConfigured,
  onStatusPayload: (payload) => {
    lastBackendConnected = !!payload.connected
    lastBackendStatusPayload = payload

    // Cache the last successfully loaded save file so future launches can skip directory scans.
    const currentSavePath = payload?.ingestion?.current_save_path
    if (typeof currentSavePath === 'string' && currentSavePath.endsWith('.sav')) {
      const previous = store.get('lastSaveFilePath', '')
      if (currentSavePath && currentSavePath !== previous) {
        try {
          const fs = require('fs')
          if (fs.existsSync(currentSavePath)) {
            store.set('lastSaveFilePath', currentSavePath)
          }
        } catch {
          // Ignore cache write errors
        }
      }
    }
  },
  updateTrayMenu,
  intervalMs: HEALTH_CHECK_INTERVAL,
  failThreshold: HEALTH_CHECK_FAIL_THRESHOLD,
})

function listenOnce(port) {
  return new Promise((resolve) => {
    const server = net.createServer()
    server.unref()
    server.once('error', () => resolve(null))
    server.listen({ host: BACKEND_HOST, port }, () => {
      const address = server.address()
      const assignedPort = typeof address === 'object' && address ? address.port : null
      server.close(() => resolve(assignedPort))
    })
  })
}

async function findAvailablePort(preferredPort) {
  const start = Number.isFinite(preferredPort) ? preferredPort : 8742
  const attempts = 20
  for (let offset = 0; offset < attempts; offset++) {
    const candidate = start + offset
    if (candidate > 65535) break
    const bound = await listenOnce(candidate)
    if (bound === candidate) return candidate
  }

  const ephemeral = await listenOnce(0)
  if (!ephemeral) {
    throw new Error('Failed to find an available port for backend')
  }
  return ephemeral
}

/**
 * Wait for the backend to become healthy.
 * @param {number} timeout - Timeout in milliseconds
 * @returns {Promise<boolean>} True if healthy, false if timeout
 */
async function waitForBackendReady(timeout = HEALTH_CHECK_TIMEOUT) {
  const startTime = Date.now()
  const checkInterval = 500 // Check every 500ms

  while (Date.now() - startTime < timeout) {
    try {
      await checkBackendHealth()
      console.log('Backend is ready')
      return true
    } catch (e) {
      // Not ready yet, wait and retry
      await new Promise((resolve) => setTimeout(resolve, checkInterval))
    }
  }

  console.error('Backend health check timed out')
  return false
}

/**
 * Start periodic health checks.
 */
function startHealthCheck() {
  healthCheckManager.start()
}

/**
 * Mask a secret key for display (show first 4 chars and last 4 chars).
 * @param {string} key - The secret key
 * @returns {string} Masked key like "abcd...wxyz" or empty if not set
 */
function maskSecret(key) {
  if (!key || key.length < 12) {
    return key ? '****' : ''
  }
  return `${key.substring(0, 4)}...${key.substring(key.length - 4)}`
}

/**
 * Validate that an IPC event comes from a trusted origin.
 * @param {Electron.IpcMainInvokeEvent} event - The IPC event
 * @throws {Error} If the sender origin is not trusted
 */
function normalizeLocalPath(filePath) {
  const normalized = path.normalize(filePath)
  return process.platform === 'win32' ? normalized.toLowerCase() : normalized
}

function getPackagedRendererEntryPath() {
  return path.join(__dirname, 'renderer', 'dist', 'index.html')
}

function isTrustedRendererUrl(candidateUrl) {
  if (!candidateUrl || typeof candidateUrl !== 'string') return false
  if (IS_DEV) {
    return candidateUrl.startsWith('http://localhost:5173')
  }
  try {
    const candidatePath = normalizeLocalPath(fileURLToPath(candidateUrl))
    const trustedPath = normalizeLocalPath(getPackagedRendererEntryPath())
    return candidatePath === trustedPath
  } catch {
    return false
  }
}

function validateSender(event) {
  const senderUrl = event.senderFrame?.url
  if (!senderUrl) {
    throw new Error('IPC sender validation failed: no sender URL')
  }

  if (!isTrustedRendererUrl(senderUrl)) {
    throw new Error(`IPC sender validation failed: untrusted origin ${senderUrl}`)
  }

  if (!mainWindow || mainWindow.isDestroyed()) {
    throw new Error('IPC sender validation failed: main window unavailable')
  }

  if (event.sender !== mainWindow.webContents) {
    throw new Error('IPC sender validation failed: unexpected webContents sender')
  }

  const trustedMainFrame = mainWindow.webContents.mainFrame
  if (trustedMainFrame && event.senderFrame && event.senderFrame.routingId !== trustedMainFrame.routingId) {
    throw new Error('IPC sender validation failed: unexpected frame sender')
  }
}

/**
 * Get settings from storage.
 * Uses safeStorage-encrypted electron-store for secrets (returns masked),
 * plain electron-store for non-secrets.
 * @returns {Object} Settings with masked secrets
 */
function getSettings() {
  const googleApiKey = getSecret(SECRET_STORE_KEYS.googleApiKey)
  const discordToken = getSecret(SECRET_STORE_KEYS.discordToken)

  const saveDir = store.get('saveDir', '')
  const discordEnabled = store.get('discordEnabled', false)

  return {
    googleApiKey: maskSecret(googleApiKey),
    googleApiKeySet: !!googleApiKey,
    discordToken: maskSecret(discordToken),
    discordTokenSet: !!discordToken,
    saveDir,
    // Backwards-compat: older renderer builds expect `savePath`.
    savePath: saveDir,
    discordEnabled,
  }
}

/**
 * Get the actual (unmasked) secrets for internal use.
 * @returns {Object} Settings with actual secret values
 */
function getSettingsWithSecrets() {
  const googleApiKey = getSecret(SECRET_STORE_KEYS.googleApiKey) || ''
  const discordToken = getSecret(SECRET_STORE_KEYS.discordToken) || ''
  const saveDir = store.get('saveDir', '')
  const lastSaveFilePath = store.get('lastSaveFilePath', '')
  const discordEnabled = store.get('discordEnabled', false)

  return {
    googleApiKey,
    discordToken,
    saveDir,
    // Backwards-compat: older renderer builds may still send/expect `savePath`.
    savePath: saveDir,
    lastSaveFilePath,
    discordEnabled,
  }
}

/**
 * Save settings to storage.
 * Secrets are encrypted via safeStorage, non-secrets go to electron-store.
 * @param {Object} settings - Settings to save
 * @returns {Object} Result with success status
 */
function saveSettings(settings) {
  if (settings.googleApiKey !== undefined && !settings.googleApiKey.includes('...')) {
    setSecret(SECRET_STORE_KEYS.googleApiKey, settings.googleApiKey || null)
  }

  if (settings.discordToken !== undefined && !settings.discordToken.includes('...')) {
    setSecret(SECRET_STORE_KEYS.discordToken, settings.discordToken || null)
  }

  const nextSaveDir = settings.saveDir !== undefined ? settings.saveDir : settings.savePath
  if (nextSaveDir !== undefined) {
    store.set('saveDir', nextSaveDir)
    // Save path changes invalidate any cached "last save file" selection.
    store.set('lastSaveFilePath', '')
  }

  if (settings.discordEnabled !== undefined) {
    store.set('discordEnabled', settings.discordEnabled)
  }

  return { success: true }
}

function getSaveDirCandidates() {
  const os = require('os')

  // Covers Steam, GOG, Paradox Launcher ("Stellaris Plaza"), Xbox Game Pass, and Flatpak Steam
  const homedir = os.homedir()
  const candidates = []
  if (process.platform === 'linux') {
    const localShare = path.join(homedir, '.local', 'share', 'Paradox Interactive')
    const flatpakShare = path.join(
      homedir,
      '.var',
      'app',
      'com.valvesoftware.Steam',
      '.local',
      'share',
      'Paradox Interactive',
    )
    candidates.push(
      path.join(localShare, 'Stellaris', 'save games'),
      path.join(localShare, 'Stellaris Plaza', 'save games'),
      path.join(flatpakShare, 'Stellaris', 'save games'),
    )
  } else {
    let documentsPath
    try {
      documentsPath = app.getPath('documents')
    } catch (err) {
      console.warn('Failed to resolve OS documents path, falling back to homedir/Documents:', err)
    }
    const docsBase = documentsPath || path.join(homedir, 'Documents')
    const docs = path.join(docsBase, 'Paradox Interactive')
    candidates.push(
      path.join(docs, 'Stellaris', 'save games'),
      path.join(docs, 'Stellaris Plaza', 'save games'),
    )
    if (process.platform === 'win32') {
      candidates.push(path.join(docs, 'Stellaris GamePass', 'save games'))
    }
  }

  return candidates
}

function deriveSaveDirFromLastSaveFilePath(lastSaveFilePath) {
  if (!lastSaveFilePath || typeof lastSaveFilePath !== 'string' || !lastSaveFilePath.endsWith('.sav')) {
    return ''
  }

  const parent = path.dirname(lastSaveFilePath)
  const grandparent = path.dirname(parent)
  if (path.basename(grandparent).toLowerCase() === 'save games') {
    return grandparent
  }
  return parent
}

function detectDefaultSaveDirFast() {
  const fs = require('fs')
  for (const dir of getSaveDirCandidates()) {
    try {
      fs.accessSync(dir, fs.constants.R_OK)
      return dir
    } catch {
      // keep trying
    }
  }
  return ''
}

function getEffectiveSaveDir(settings) {
  const explicit = settings?.saveDir || settings?.savePath || ''
  if (explicit) return explicit

  const fromLast = deriveSaveDirFromLastSaveFilePath(settings?.lastSaveFilePath)
  if (fromLast) return fromLast

  return detectDefaultSaveDirFast()
}

// System Tray (ELEC-006)

/**
 * Get the path to the tray icon.
 * Uses template image for macOS (trayTemplate.png) and regular icon for other platforms.
 * @returns {string} Path to tray icon
 */
function getTrayIconPath() {
  if (app.isPackaged) {
    if (process.platform === 'darwin') {
      return path.join(process.resourcesPath, 'assets', 'trayTemplate.png')
    }
    return path.join(process.resourcesPath, 'assets', 'icon.png')
  } else {
    // Development - use assets folder
    if (process.platform === 'darwin') {
      return path.join(__dirname, 'assets', 'trayTemplate.png')
    }
    return path.join(__dirname, 'assets', 'icon.png')
  }
}

/**
 * Create and configure the system tray.
 * Implements:
 * - Tray icon appears on launch
 * - Context menu with Open, Status, Quit options
 * - Click toggles window visibility
 * - macOS: app stays running when window closed
 */
function createTray() {
  // Create tray icon - use a placeholder if file doesn't exist
  let trayIcon
  try {
    const iconPath = getTrayIconPath()
    trayIcon = nativeImage.createFromPath(iconPath)

    // If icon is empty (file doesn't exist), create a simple placeholder
    if (trayIcon.isEmpty()) {
      // Create a simple 16x16 placeholder icon
      trayIcon = nativeImage.createEmpty()
    }
  } catch (e) {
    console.error('Failed to load tray icon:', e)
    trayIcon = nativeImage.createEmpty()
  }

  // For macOS, mark as template image for proper menu bar appearance
  if (process.platform === 'darwin') {
    trayIcon.setTemplateImage(true)
  }

  tray = new Tray(trayIcon)
  tray.setToolTip('Stellaris Companion')

  // Update tray context menu
  updateTrayMenu()

  // Click handler - toggle window visibility
  tray.on('click', () => {
    if (mainWindow) {
      if (mainWindow.isVisible()) {
        mainWindow.hide()
      } else {
        mainWindow.show()
        mainWindow.focus()
      }
    } else {
      // Window was destroyed, recreate it
      createWindow()
    }
  })
}

/**
 * Update the tray context menu with current status.
 * Called periodically to update status display.
 * Only rebuilds menu when status actually changes to prevent memory leaks.
 */
function updateTrayMenu() {
  if (!tray) return

  const currentStatus = lastBackendConnected ? 'Connected' : (backendConfigured ? 'Disconnected' : 'Not configured')

  // Only rebuild menu if status changed to avoid Menu object accumulation
  if (lastTrayStatus === currentStatus) {
    return
  }
  lastTrayStatus = currentStatus

  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Open Stellaris Companion',
      click: () => {
        if (mainWindow) {
          mainWindow.show()
          mainWindow.focus()
        } else {
          createWindow()
        }
      },
    },
    {
      label: `Status: ${currentStatus}`,
      enabled: false,
    },
    { type: 'separator' },
    {
      label: 'Quit',
      click: () => {
        isQuitting = true
        app.quit()
      },
    },
  ])

  tray.setContextMenu(contextMenu)
}

// Window Management

function createWindow() {
  // Restore window state from previous session
  const windowState = store.get('windowState', { width: 1000, height: 700 })

  mainWindow = new BrowserWindow({
    width: windowState.width,
    height: windowState.height,
    x: windowState.x,
    y: windowState.y,
    minWidth: 800,
    minHeight: 600,
    titleBarStyle: 'hiddenInset',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      webviewTag: false,
    },
  })

  // Remove default menu bar on Windows/Linux (macOS uses system menu bar)
  if (process.platform !== 'darwin') {
    mainWindow.removeMenu()
  }

  // Save window state on resize/move (debounced to avoid excessive writes)
  let saveStateTimeout = null
  const saveWindowState = () => {
    if (saveStateTimeout) clearTimeout(saveStateTimeout)
    saveStateTimeout = setTimeout(() => {
      if (mainWindow && !mainWindow.isDestroyed() && !mainWindow.isMinimized()) {
        const bounds = mainWindow.getBounds()
        store.set('windowState', bounds)
      }
    }, 500)
  }
  mainWindow.on('resize', saveWindowState)
  mainWindow.on('move', saveWindowState)

  // Navigation lockdown - prevent opening new windows, open external URLs in system browser
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    // Open external URLs in system browser
    if (url.startsWith('http://') || url.startsWith('https://')) {
      shell.openExternal(url)
    }
    // Deny all new window creation
    return { action: 'deny' }
  })

  // Block navigation away from app origin
  mainWindow.webContents.on('will-navigate', (event, url) => {
    const isAllowed = isTrustedRendererUrl(url)
    if (!isAllowed) {
      event.preventDefault()
      // Open external URLs in system browser instead
      if (url.startsWith('http://') || url.startsWith('https://')) {
        shell.openExternal(url)
      }
      console.warn(`Blocked navigation to untrusted URL: ${url}`)
    }
  })

  // In development, load from Vite dev server
  if (IS_DEV) {
    mainWindow.loadURL('http://localhost:5173')
    // Keep the app layout stable in dev by not auto-docking DevTools.
    // Opt-in via env so normal runs match production visuals.
    if (process.env.OPEN_DEVTOOLS === '1') {
      mainWindow.webContents.openDevTools({ mode: 'detach' })
    }
  } else {
    // In production, load the built renderer
    mainWindow.loadURL(pathToFileURL(getPackagedRendererEntryPath()).toString())
  }

  // Minimize to tray on close (instead of quitting).
  // NOTE: In development, allow the window to close so hot-reload/restarts are reliable.
  mainWindow.on('close', (event) => {
    if (IS_DEV) return
    if (!isQuitting) {
      event.preventDefault()
      mainWindow.hide()
    }
  })

  mainWindow.on('closed', () => {
    mainWindow = null
  })

  // Ensure the renderer always receives at least one status event.
  mainWindow.webContents.on('did-finish-load', () => {
    if (!mainWindow) return
    if (lastBackendStatusPayload) {
      mainWindow.webContents.send('backend-status', lastBackendStatusPayload)
    } else {
      mainWindow.webContents.send('backend-status', {
        connected: false,
        backend_configured: backendConfigured,
      })
    }
    // Push cached announcements so renderer has data immediately
    announcementsService.fetchAnnouncements().then((announcements) => {
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('announcements-updated', announcements)
      }
    }).catch(() => {})
  })
}

registerBackendIpcHandlers({ ipcMain, validateSender, callBackendApiEnvelope })

// =============================================================================
// Feedback reporting handlers
// =============================================================================

// Screenshot capture for feedback reports
ipcMain.handle('capture-screenshot', async (event) => {
  validateSender(event)
  try {
    if (!mainWindow || mainWindow.isDestroyed()) {
      return null
    }
    const image = await mainWindow.webContents.capturePage()
    return image.toDataURL()
  } catch (e) {
    console.error('Failed to capture screenshot:', e)
    return null
  }
})

// App version for feedback reports
ipcMain.handle('get-app-version', async (event) => {
  validateSender(event)
  return app.getVersion()
})

ipcMain.handle('get-install-id', async (event) => {
  validateSender(event)
  return ensureInstallId()
})

ipcMain.handle('copy-to-clipboard', async (event, { text }) => {
  validateSender(event)
  if (typeof text !== 'string') return { success: false }
  clipboard.writeText(text)
  return { success: true }
})

ipcMain.handle('open-external', async (event, { url }) => {
  validateSender(event)
  if (typeof url !== 'string' || !/^https?:\/\//.test(url)) return { success: false }
  await shell.openExternal(url)
  return { success: true }
})

ipcMain.handle('get-backend-log-tail', async (event, { maxBytes } = {}) => {
  validateSender(event)
  const fs = require('fs')
  const logPath = path.join(app.getPath('userData'), 'logs', 'stellaris-companion-backend.log')
  const bytes = Number.isFinite(maxBytes) ? Math.max(0, Math.min(Number(maxBytes), 1024 * 256)) : 32 * 1024
  try {
    const stat = fs.statSync(logPath)
    const start = Math.max(0, stat.size - bytes)
    const fd = fs.openSync(logPath, 'r')
    try {
      const buf = Buffer.alloc(stat.size - start)
      fs.readSync(fd, buf, 0, buf.length, start)
      return { ok: true, data: buf.toString('utf8') }
    } finally {
      fs.closeSync(fd)
    }
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : 'Failed to read backend log' }
  }
})

registerSettingsIpcHandlers({
  ipcMain,
  validateSender,
  dialog,
  getMainWindow: () => mainWindow,
  getSettings,
  saveSettings,
  getSettingsWithSecrets,
  onSettingsSaved: async (fullSettings) => {
    backendConfigured = !!fullSettings.googleApiKey
    restartPythonBackend(fullSettings)
  },
})

registerExportIpcHandlers({
  ipcMain,
  validateSender,
  dialog,
  getMainWindow: () => mainWindow,
  app,
})

// =============================================================================
// Auto-Update Handlers (ELEC-006: electron-updater integration)
// =============================================================================
registerUpdateIpcHandlers({ ipcMain, autoUpdater, app, isDev: IS_DEV })
wireAutoUpdaterEvents({ autoUpdater, getMainWindow: () => mainWindow })

// =============================================================================
// Onboarding IPC Handlers
// =============================================================================

/**
 * Detect Stellaris save files in platform-default directories.
 * Scans recursively for .sav files without needing the Python backend.
 * @returns {Promise<Object>} Detection result with found, directory, saveCount, latest
 */
async function detectStellarissaves() {
  const fs = require('fs')
  const candidates = getSaveDirCandidates()

  for (const dir of candidates) {
    try {
      await fs.promises.access(dir)
    } catch {
      continue
    }

    // Recursively find .sav files
    const savFiles = []
    const walk = async (current) => {
      let entries
      try {
        entries = await fs.promises.readdir(current, { withFileTypes: true })
      } catch {
        return
      }
      for (const entry of entries) {
        const fullPath = path.join(current, entry.name)
        if (entry.isDirectory()) {
          await walk(fullPath)
        } else if (entry.name.endsWith('.sav')) {
          try {
            const stat = await fs.promises.stat(fullPath)
            savFiles.push({ name: entry.name, modified: stat.mtimeMs, path: fullPath })
          } catch {
            // Skip inaccessible files
          }
        }
      }
    }

    await walk(dir)

    if (savFiles.length > 0) {
      savFiles.sort((a, b) => b.modified - a.modified)
      const latest = savFiles[0]
      return {
        found: true,
        directory: dir,
        saveCount: savFiles.length,
        latest: { name: latest.name, modified: new Date(latest.modified).toISOString() },
      }
    }

    // Directory exists but no saves found
    return { found: false, directory: dir, saveCount: 0, latest: null }
  }

  return { found: false, directory: null, saveCount: 0, latest: null }
}

ipcMain.handle('onboarding:status', async (event) => {
  validateSender(event)
  return store.get('hasCompletedOnboarding', false)
})

ipcMain.handle('onboarding:complete', async (event) => {
  validateSender(event)
  store.set('hasCompletedOnboarding', true)
  return { success: true }
})

ipcMain.handle('onboarding:detect-saves', async (event) => {
  validateSender(event)
  return detectStellarisaves()
})

// =============================================================================
// Announcements IPC Handlers
// =============================================================================
registerAnnouncementsIpcHandlers({ ipcMain, validateSender, store, announcementsService })

// =============================================================================
// Discord IPC Handlers (DISC-007 / DISC-008)
// =============================================================================
registerDiscordIpcHandlers({ ipcMain, validateSender, discordOAuth, discordRelay })

// App Lifecycle

// Timing helper for startup diagnostics
function logTiming(label, startTime) {
  const elapsed = Date.now() - startTime
  console.log(`[TIMING] ${label}: ${elapsed}ms`)
  return Date.now()
}

app.whenReady().then(async () => {
  const appStartTime = Date.now()
  let phaseStart = appStartTime
  console.log('[TIMING] ═══════════════════════════════════════════')
  console.log('[TIMING] Electron app startup begin')

  // If a second instance is started, focus the existing window instead.
  // (Production only; in dev we skip the single-instance lock entirely.)
  if (!IS_DEV) {
    app.on('second-instance', () => {
      if (!mainWindow) return
      if (mainWindow.isMinimized()) mainWindow.restore()
      mainWindow.show()
      mainWindow.focus()
    })
  }

  // Use existing token from env (dev mode) or generate new one (production)
  authToken = process.env.STELLARIS_API_TOKEN || generateAuthToken()
  phaseStart = logTiming('Auth token configured', phaseStart)

  // Check if backend is already running on default port BEFORE finding a new port.
  // This handles dev.sh starting the backend externally.
  backendPort = DEFAULT_BACKEND_PORT
  let backendAlreadyRunning = false
  try {
    await checkBackendHealth()
    backendAlreadyRunning = true
    console.log('Backend already running on default port')
    phaseStart = logTiming('Found existing backend', phaseStart)
  } catch (e) {
    backendPort = await findAvailablePort(DEFAULT_BACKEND_PORT)
    if (backendPort !== DEFAULT_BACKEND_PORT) {
      console.warn(`Default port ${DEFAULT_BACKEND_PORT} unavailable; using port ${backendPort}`)
    }
    phaseStart = logTiming('Port availability check', phaseStart)
  }

  // Create window and tray immediately (user sees UI fast)
  createWindow()
  phaseStart = logTiming('Create window', phaseStart)

  createTray()
  phaseStart = logTiming('Create tray', phaseStart)

  // Start health checks immediately - UI handles "connecting..." state
  startHealthCheck()
  phaseStart = logTiming('Start health check', phaseStart)

  // Load settings (backend health already checked above)
  const settings = await getSettingsWithSecrets()
  backendConfigured = !!settings.googleApiKey
  phaseStart = logTiming('Load settings', phaseStart)

  if (backendAlreadyRunning) {
    // Already logged above
  } else if (settings.googleApiKey) {
    startPythonBackend(settings)
    phaseStart = logTiming('Start Python backend (spawn)', phaseStart)

    // Wait for backend to be ready
    const ready = await waitForBackendReady()
    phaseStart = logTiming('Wait for backend ready', phaseStart)
    if (ready) {
      console.log('Backend health check passed')
    } else {
      console.error('Backend failed to start')
    }
  } else {
    console.log('No Google API key configured, skipping backend start')
  }

  console.log('[TIMING] ═══════════════════════════════════════════')
  console.log(`[TIMING] TOTAL Electron startup: ${Date.now() - appStartTime}ms`)
  console.log('[TIMING] ═══════════════════════════════════════════')

  // Start Discord relay connection if user is already connected
  // This ensures relay reconnects on app restart after previous OAuth
  discordRelay.startDiscordRelayIfConnected().catch((e) => {
    console.error('Failed to start Discord relay on startup:', e.message)
  })

  // Announcements: initial fetch + periodic polling
  announcementsService.fetchAnnouncements().then((announcements) => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('announcements-updated', announcements)
    }
  }).catch(() => {})

  announcementsService.startPolling({
    onAnnouncements: (announcements) => {
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('announcements-updated', announcements)
      }
    },
  })

  app.on('activate', () => {
    // macOS: clicking dock icon should show the window
    if (mainWindow) {
      mainWindow.show()
      mainWindow.focus()
    } else if (BrowserWindow.getAllWindows().length === 0) {
      createWindow()
    }
  })
})

let quitCleanupStarted = false
app.on('before-quit', (event) => {
  if (quitCleanupStarted) return
  quitCleanupStarted = true
  isQuitting = true
  healthCheckManager.setIsQuitting(true)

  announcementsService.stopPolling()

  // Ensure backend shutdown completes (esp. on Windows) before the app exits.
  event.preventDefault()
  Promise.race([
    stopPythonBackend(),
    new Promise((resolve) => setTimeout(resolve, 2000)),
  ]).finally(() => {
    if (tray) {
      tray.destroy()
      tray = null
    }
    app.exit(0)
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

// Export for testing
module.exports = {
  generateAuthToken,
  getPythonPath,
  buildBackendEnv,
  callBackendApiOrThrow,
  callBackendApiEnvelope,
}
