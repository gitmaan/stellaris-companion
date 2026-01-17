// Main process entry point
// Implements ELEC-002: Python subprocess management

const { app, BrowserWindow, ipcMain, dialog } = require('electron')
const path = require('path')
const { spawn } = require('child_process')
const crypto = require('crypto')

// Configuration
const BACKEND_HOST = '127.0.0.1'
const BACKEND_PORT = 8742
const HEALTH_CHECK_INTERVAL = 5000 // 5 seconds
const HEALTH_CHECK_TIMEOUT = 30000 // 30 seconds for initial startup

// State
let mainWindow = null
let pythonProcess = null
let authToken = null
let healthCheckTimer = null
let isQuitting = false

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
    // In development, use system Python
    return 'python'
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
    args = ['--host', BACKEND_HOST, '--port', String(BACKEND_PORT)]
  } else {
    // Development runs the Python script
    args = [getBackendScriptPath(), '--host', BACKEND_HOST, '--port', String(BACKEND_PORT)]
  }

  console.log(`Starting Python backend: ${pythonPath} ${args.join(' ')}`)

  pythonProcess = spawn(pythonPath, args, {
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
    // Detach on Windows to allow proper cleanup
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
    return
  }

  console.log('Stopping Python backend...')

  // Clear health check timer
  if (healthCheckTimer) {
    clearInterval(healthCheckTimer)
    healthCheckTimer = null
  }

  // Kill the process
  if (process.platform === 'win32') {
    // Windows needs taskkill
    spawn('taskkill', ['/pid', pythonProcess.pid, '/f', '/t'])
  } else {
    // Unix - kill the process group
    try {
      process.kill(-pythonProcess.pid, 'SIGTERM')
    } catch (e) {
      // Process may have already exited
      try {
        pythonProcess.kill('SIGTERM')
      } catch (e2) {
        // Ignore
      }
    }
  }

  pythonProcess = null
}

/**
 * Restart the Python backend with new settings.
 * @param {Object} settings - New settings
 */
function restartPythonBackend(settings) {
  stopPythonBackend()
  // Small delay to ensure port is released
  setTimeout(() => {
    startPythonBackend(settings)
    // Start health check after restart
    startHealthCheck()
  }, 500)
}

/**
 * Call the Python backend API.
 * @param {string} endpoint - API endpoint (e.g., '/api/health')
 * @param {Object} options - Fetch options
 * @returns {Promise<Object>} API response
 */
async function callBackendApi(endpoint, options = {}) {
  const url = `http://${BACKEND_HOST}:${BACKEND_PORT}${endpoint}`

  const fetchOptions = {
    ...options,
    headers: {
      ...options.headers,
      Authorization: `Bearer ${authToken}`,
      'Content-Type': 'application/json',
    },
  }

  const response = await fetch(url, fetchOptions)

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

/**
 * Check if the backend is healthy.
 * @returns {Promise<Object>} Health response
 */
async function checkBackendHealth() {
  return callBackendApi('/api/health')
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

  healthCheckTimer = setInterval(async () => {
    if (!pythonProcess || isQuitting) {
      return
    }

    try {
      const health = await checkBackendHealth()
      if (mainWindow) {
        mainWindow.webContents.send('backend-status', { connected: true, ...health })
      }
    } catch (e) {
      if (mainWindow) {
        mainWindow.webContents.send('backend-status', { connected: false })
      }
    }
  }, HEALTH_CHECK_INTERVAL)
}

/**
 * Get settings from storage (placeholder - full implementation in ELEC-004).
 * @returns {Object} Settings
 */
async function getSettings() {
  // Import electron-store and keytar for full implementation
  // For now, return env-based settings for testing
  return {
    googleApiKey: process.env.GOOGLE_API_KEY || '',
    savePath: process.env.STELLARIS_SAVE_PATH || '',
    discordEnabled: false,
    discordToken: '',
  }
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
    },
  })

  // In development, load from Vite dev server
  if (process.env.NODE_ENV === 'development') {
    mainWindow.loadURL('http://localhost:5173')
    mainWindow.webContents.openDevTools()
  } else {
    // In production, load the built renderer
    mainWindow.loadFile(path.join(__dirname, 'renderer', 'dist', 'index.html'))
  }

  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

// IPC Handlers - Backend Proxy (requires ELEC-005 for full implementation)
// Basic handlers for backend proxy

ipcMain.handle('backend:health', async () => {
  try {
    return await callBackendApi('/api/health')
  } catch (e) {
    return { error: e.message, connected: false }
  }
})

ipcMain.handle('backend:chat', async (event, { message, session_key }) => {
  try {
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

// Settings handlers (placeholder - full implementation in ELEC-004)
ipcMain.handle('get-settings', async () => {
  return getSettings()
})

ipcMain.handle('save-settings', async (event, settings) => {
  // Full implementation in ELEC-004 with keytar + electron-store
  // For now, just restart backend with new settings
  if (settings.googleApiKey) {
    process.env.GOOGLE_API_KEY = settings.googleApiKey
  }
  if (settings.savePath) {
    process.env.STELLARIS_SAVE_PATH = settings.savePath
  }

  const currentSettings = await getSettings()
  restartPythonBackend({ ...currentSettings, ...settings })

  return { success: true }
})

ipcMain.handle('show-folder-dialog', async () => {
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
  // Generate auth token for this session
  authToken = generateAuthToken()
  console.log('Generated auth token for session')

  // Create the main window
  createWindow()

  // Get settings and start backend
  const settings = await getSettings()
  if (settings.googleApiKey) {
    startPythonBackend(settings)

    // Wait for backend to be ready
    const ready = await waitForBackendReady()
    if (ready) {
      console.log('Backend health check passed')
      startHealthCheck()
    } else {
      console.error('Backend failed to start')
    }
  } else {
    console.log('No Google API key configured, skipping backend start')
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow()
    }
  })
})

app.on('before-quit', () => {
  isQuitting = true
})

app.on('will-quit', () => {
  // Kill Python backend on quit
  stopPythonBackend()
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
