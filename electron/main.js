// Main process entry point
// Implements ELEC-002: Python subprocess management
// Implements ELEC-004: Settings IPC handlers (keytar + electron-store)

const { app, BrowserWindow, ipcMain, dialog, Tray, Menu, nativeImage, shell } = require('electron')
const path = require('path')
const { spawn } = require('child_process')
const crypto = require('crypto')
const Store = require('electron-store')
const keytar = require('keytar')
const net = require('net')

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
const gotSingleInstanceLock = app.requestSingleInstanceLock()
if (!gotSingleInstanceLock) {
  app.quit()
}

// Constants for keytar service names
const KEYTAR_SERVICE = 'StellarisCompanion'
const KEYTAR_ACCOUNT_GOOGLE_API = 'google-api-key'
const KEYTAR_ACCOUNT_DISCORD = 'discord-token'

// Initialize electron-store for non-secret settings
const store = new Store({
  name: 'settings',
  defaults: {
    savePath: '',
    discordEnabled: false,
  },
})

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

// State
let mainWindow = null
let pythonProcess = null
let authToken = null
let backendPort = DEFAULT_BACKEND_PORT
let healthCheckTimer = null
let healthCheckInFlight = false
let healthCheckFailCount = 0 // Track consecutive failures to prevent flickering
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
 * Get the path to the electron_main.py script.
 */
function getBackendScriptPath() {
  return path.join(__dirname, '..', 'backend', 'electron_main.py')
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

  // Add save path if provided
  if (settings.savePath) {
    env.STELLARIS_SAVE_PATH = settings.savePath
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
    args = ['--host', BACKEND_HOST, '--port', String(backendPort)]
  } else {
    // Development runs the Python script
    args = [getBackendScriptPath(), '--host', BACKEND_HOST, '--port', String(backendPort)]
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

  // Clear health check timer
  if (healthCheckTimer) {
    clearInterval(healthCheckTimer)
    healthCheckTimer = null
  }

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
      // Windows: taskkill the full tree and wait briefly.
      await new Promise((resolve) => {
        const killer = spawn('taskkill', ['/pid', String(child.pid), '/f', '/t'], { stdio: 'ignore' })
        killer.on('error', resolve)
        killer.on('close', resolve)
      })
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

/**
 * Call the Python backend API.
 * @param {string} endpoint - API endpoint (e.g., '/api/health')
 * @param {Object} options - Fetch options
 * @returns {Promise<Object>} API response
 */
async function callBackendApi(endpoint, options = {}) {
  const url = `http://${BACKEND_HOST}:${backendPort}${endpoint}`

  const { timeoutMs, ...restOptions } = options
  const controller = timeoutMs ? new AbortController() : null
  const timer = timeoutMs
    ? setTimeout(() => {
      try {
        controller.abort()
      } catch (e) {
        // ignore
      }
    }, timeoutMs)
    : null

  const fetchOptions = {
    ...restOptions,
    signal: controller ? controller.signal : undefined,
    headers: {
      ...restOptions.headers,
      Authorization: `Bearer ${authToken}`,
      'Content-Type': 'application/json',
    },
  }

  let response
  try {
    response = await fetch(url, fetchOptions)
  } finally {
    if (timer) clearTimeout(timer)
  }

  const rawBody = await response.text().catch(() => '')
  let parsedBody = null
  if (rawBody) {
    try {
      parsedBody = JSON.parse(rawBody)
    } catch (e) {
      parsedBody = null
    }
  }

  if (!response.ok) {
    const detail = parsedBody?.detail?.error || parsedBody?.detail || parsedBody?.error
    const fallback = rawBody ? rawBody.slice(0, 500) : null
    throw new Error(detail || fallback || `HTTP ${response.status}`)
  }

  if (parsedBody === null) {
    throw new Error('Invalid JSON response from backend')
  }

  return parsedBody
}

/**
 * Check if the backend is healthy.
 * @returns {Promise<Object>} Health response
 */
async function checkBackendHealth() {
  return callBackendApi('/api/health', { timeoutMs: HEALTH_CHECK_REQUEST_TIMEOUT })
}

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
  if (healthCheckTimer) {
    clearInterval(healthCheckTimer)
  }
  healthCheckFailCount = 0 // Reset fail count on fresh start

  const perform = async () => {
    if (isQuitting || healthCheckInFlight) return
    healthCheckInFlight = true
    try {
      const health = await checkBackendHealth()
      healthCheckFailCount = 0 // Reset on success
      lastBackendConnected = true
      lastBackendStatusPayload = {
        connected: true,
        backend_configured: backendConfigured,
        ...health,
      }
      if (mainWindow) {
        mainWindow.webContents.send('backend-status', lastBackendStatusPayload)
      }
    } catch (e) {
      healthCheckFailCount++
      // Only mark as disconnected after consecutive failures to prevent flickering
      if (healthCheckFailCount >= HEALTH_CHECK_FAIL_THRESHOLD) {
        lastBackendConnected = false
        lastBackendStatusPayload = {
          connected: false,
          backend_configured: backendConfigured,
          error: e.message,
        }
        if (mainWindow) {
          mainWindow.webContents.send('backend-status', lastBackendStatusPayload)
        }
      }
      // If below threshold, keep previous successful status (don't update UI)
    } finally {
      healthCheckInFlight = false
      updateTrayMenu()
    }
  }

  // Emit an immediate status so renderer never sticks on "Connecting..."
  perform()
  healthCheckTimer = setInterval(perform, HEALTH_CHECK_INTERVAL)
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
function validateSender(event) {
  const senderUrl = event.senderFrame?.url
  if (!senderUrl) {
    throw new Error('IPC sender validation failed: no sender URL')
  }

  const allowedOrigins = [
    'http://localhost:5173', // Dev
    'file://', // Prod
  ]

  const isAllowed = allowedOrigins.some((origin) => senderUrl.startsWith(origin))
  if (!isAllowed) {
    throw new Error(`IPC sender validation failed: untrusted origin ${senderUrl}`)
  }
}

/**
 * Get settings from storage.
 * Uses keytar for secrets (returns masked), electron-store for non-secrets.
 * @returns {Promise<Object>} Settings with masked secrets
 */
async function getSettings() {
  // Get secrets from keytar (masked for display)
  const googleApiKey = await keytar.getPassword(KEYTAR_SERVICE, KEYTAR_ACCOUNT_GOOGLE_API)
  const discordToken = await keytar.getPassword(KEYTAR_SERVICE, KEYTAR_ACCOUNT_DISCORD)

  // Get non-secrets from electron-store
  const savePath = store.get('savePath', '')
  const discordEnabled = store.get('discordEnabled', false)

  return {
    googleApiKey: maskSecret(googleApiKey),
    googleApiKeySet: !!googleApiKey,
    discordToken: maskSecret(discordToken),
    discordTokenSet: !!discordToken,
    savePath,
    discordEnabled,
  }
}

/**
 * Get the actual (unmasked) secrets for internal use.
 * @returns {Promise<Object>} Settings with actual secret values
 */
async function getSettingsWithSecrets() {
  const googleApiKey = (await keytar.getPassword(KEYTAR_SERVICE, KEYTAR_ACCOUNT_GOOGLE_API)) || ''
  const discordToken = (await keytar.getPassword(KEYTAR_SERVICE, KEYTAR_ACCOUNT_DISCORD)) || ''
  const savePath = store.get('savePath', '')
  const discordEnabled = store.get('discordEnabled', false)

  return {
    googleApiKey,
    discordToken,
    savePath,
    discordEnabled,
  }
}

/**
 * Save settings to storage.
 * Secrets go to keytar, non-secrets go to electron-store.
 * @param {Object} settings - Settings to save
 * @returns {Promise<Object>} Result with success status
 */
async function saveSettings(settings) {
  // Save secrets to keytar (only if provided and not masked)
  if (settings.googleApiKey !== undefined && !settings.googleApiKey.includes('...')) {
    if (settings.googleApiKey) {
      await keytar.setPassword(KEYTAR_SERVICE, KEYTAR_ACCOUNT_GOOGLE_API, settings.googleApiKey)
    } else {
      await keytar.deletePassword(KEYTAR_SERVICE, KEYTAR_ACCOUNT_GOOGLE_API)
    }
  }

  if (settings.discordToken !== undefined && !settings.discordToken.includes('...')) {
    if (settings.discordToken) {
      await keytar.setPassword(KEYTAR_SERVICE, KEYTAR_ACCOUNT_DISCORD, settings.discordToken)
    } else {
      await keytar.deletePassword(KEYTAR_SERVICE, KEYTAR_ACCOUNT_DISCORD)
    }
  }

  // Save non-secrets to electron-store
  if (settings.savePath !== undefined) {
    store.set('savePath', settings.savePath)
  }

  if (settings.discordEnabled !== undefined) {
    store.set('discordEnabled', settings.discordEnabled)
  }

  return { success: true }
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
  mainWindow = new BrowserWindow({
    width: 1000,
    height: 700,
    minWidth: 800,
    minHeight: 600,
    titleBarStyle: 'hiddenInset',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      webviewTag: false,
    },
  })

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
    const allowedOrigins = [
      'http://localhost:5173', // Dev
      'file://', // Prod
    ]
    const isAllowed = allowedOrigins.some((origin) => url.startsWith(origin))
    if (!isAllowed) {
      event.preventDefault()
      // Open external URLs in system browser instead
      if (url.startsWith('http://') || url.startsWith('https://')) {
        shell.openExternal(url)
      }
    }
  })

  // In development, load from Vite dev server
  if (process.env.NODE_ENV === 'development') {
    mainWindow.loadURL('http://localhost:5173')
    mainWindow.webContents.openDevTools()
  } else {
    // In production, load the built renderer
    mainWindow.loadFile(path.join(__dirname, 'renderer', 'dist', 'index.html'))
  }

  // Minimize to tray on close (instead of quitting)
  // On macOS, apps typically stay running in the background
  mainWindow.on('close', (event) => {
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
  })
}

// IPC Handlers - Backend Proxy (requires ELEC-005 for full implementation)
// Basic handlers for backend proxy

ipcMain.handle('backend:health', async (event) => {
  try {
    validateSender(event)
    return await callBackendApi('/api/health')
  } catch (e) {
    return { error: e.message, connected: false }
  }
})

ipcMain.handle('backend:chat', async (event, { message, session_key }) => {
  try {
    validateSender(event)
    return await callBackendApi('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ message, session_key }),
    })
  } catch (e) {
    return { error: e.message }
  }
})

ipcMain.handle('backend:status', async () => {
  try {
    return await callBackendApi('/api/status')
  } catch (e) {
    return { error: e.message }
  }
})

ipcMain.handle('backend:sessions', async () => {
  try {
    return await callBackendApi('/api/sessions')
  } catch (e) {
    return { error: e.message }
  }
})

ipcMain.handle('backend:session-events', async (event, { session_id, limit }) => {
  try {
    let url = `/api/sessions/${session_id}/events`
    if (limit) {
      url += `?limit=${limit}`
    }
    return await callBackendApi(url)
  } catch (e) {
    return { error: e.message }
  }
})

ipcMain.handle('backend:recap', async (event, { session_id }) => {
  try {
    return await callBackendApi('/api/recap', {
      method: 'POST',
      body: JSON.stringify({ session_id }),
    })
  } catch (e) {
    return { error: e.message }
  }
})

ipcMain.handle('backend:end-session', async () => {
  try {
    return await callBackendApi('/api/end-session', {
      method: 'POST',
    })
  } catch (e) {
    return { error: e.message }
  }
})

// Settings handlers (ELEC-004: keytar + electron-store)
ipcMain.handle('load-settings', async (event) => {
  validateSender(event)
  return getSettings()
})

ipcMain.handle('save-settings', async (event, settings) => {
  validateSender(event)
  // Save settings to keytar (secrets) and electron-store (non-secrets)
  await saveSettings(settings)

  // Get the full settings with actual secrets for backend restart
  const fullSettings = await getSettingsWithSecrets()
  backendConfigured = !!fullSettings.googleApiKey

  // Restart the Python backend with new settings
  restartPythonBackend(fullSettings)

  return { success: true }
})

ipcMain.handle('select-folder', async (event) => {
  validateSender(event)
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory'],
    title: 'Select Stellaris Save Folder',
  })

  if (result.canceled || !result.filePaths.length) {
    return null
  }

  return result.filePaths[0]
})

// Update handlers (placeholder - full implementation later)
ipcMain.handle('check-for-update', async () => {
  // Full implementation with electron-updater
  return { updateAvailable: false }
})

ipcMain.handle('install-update', async () => {
  // Full implementation with electron-updater
  return { success: false, error: 'Not implemented' }
})

// App Lifecycle

app.whenReady().then(async () => {
  // If a second instance is started, focus the existing window instead.
  app.on('second-instance', () => {
    if (!mainWindow) return
    if (mainWindow.isMinimized()) mainWindow.restore()
    mainWindow.show()
    mainWindow.focus()
  })

  // Use existing token from env (dev mode) or generate new one (production)
  authToken = process.env.STELLARIS_API_TOKEN || generateAuthToken()
  console.log('Auth token configured')

  try {
    const chosenPort = await findAvailablePort(DEFAULT_BACKEND_PORT)
    backendPort = chosenPort
    if (chosenPort !== DEFAULT_BACKEND_PORT) {
      console.warn(`Default port ${DEFAULT_BACKEND_PORT} in use; using port ${chosenPort} instead`)
    }
  } catch (e) {
    console.error('Failed to pick backend port:', e)
  }

  // Create the main window
  createWindow()

  // Create the system tray (ELEC-006)
  createTray()

  // Get settings with actual secrets and start backend if needed
  const settings = await getSettingsWithSecrets()
  backendConfigured = !!settings.googleApiKey

  // Always start health checks (even if we don't spawn Python) so the UI gets accurate status.
  startHealthCheck()

  // If backend is reachable already, don't spawn another process.
  let backendAlreadyRunning = false
  try {
    await checkBackendHealth()
    backendAlreadyRunning = true
    console.log('Backend already running')
  } catch (e) {
    // Not running or not authorized (still shows status via health checks).
  }

  if (!backendAlreadyRunning && settings.googleApiKey) {
    startPythonBackend(settings)

    // Wait for backend to be ready
    const ready = await waitForBackendReady()
    if (ready) {
      console.log('Backend health check passed')
    } else {
      console.error('Backend failed to start')
    }
  } else {
    if (!settings.googleApiKey) {
      console.log('No Google API key configured, skipping backend start')
    }
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow()
    }
  })
})

let quitCleanupStarted = false
app.on('before-quit', (event) => {
  if (quitCleanupStarted) return
  quitCleanupStarted = true
  isQuitting = true

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
  callBackendApi,
}
