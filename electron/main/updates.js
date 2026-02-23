function setupAutoUpdater({ autoUpdater, app, isDev }) {
  if (isDev) return
  if (!app?.isPackaged) return
  if (process.windowsStore) return

  // On macOS, running directly from a mounted .dmg (e.g. /Volumes/...) can cause
  // updater errors. Only auto-check once installed.
  if (process.platform === 'darwin' && process.execPath.includes('/Volumes/')) {
    return
  }

  // We use a custom in-app updater UX, so avoid native notifications.
  autoUpdater.autoDownload = true

  // On macOS, keep installs explicitly user-triggered to avoid "silent wait"
  // states where the app appears idle after pressing restart.
  if (process.platform === 'darwin') {
    autoUpdater.autoInstallOnAppQuit = false
  }

  // Avoid startup crashes on platforms/configs where update checks can throw
  // synchronously or reject promises (network, feed parsing, etc).
  try {
    const p = autoUpdater.checkForUpdates()
    if (p && typeof p.catch === 'function') {
      p.catch((err) => console.error('Auto-updater error (startup):', err))
    }
  } catch (err) {
    console.error('Auto-updater error (startup):', err)
  }

  setInterval(() => {
    try {
      const p = autoUpdater.checkForUpdates()
      if (p && typeof p.catch === 'function') {
        p.catch((err) => console.error('Auto-updater error (interval):', err))
      }
    } catch (err) {
      console.error('Auto-updater error (interval):', err)
    }
  }, 3600000)
}

const updaterState = {
  downloadedVersion: null,
  installing: false,
  installTimeout: null,
}

function sendUpdateEvent(getMainWindow, channel, payload) {
  const mainWindow = getMainWindow()
  if (!mainWindow || mainWindow.isDestroyed()) return
  mainWindow.webContents.send(channel, payload)
}

function registerUpdateIpcHandlers({ ipcMain, autoUpdater, app, isDev, getMainWindow, prepareForUpdateQuit }) {
  ipcMain.handle('check-for-update', async () => {
    if (isDev) {
      return { updateAvailable: false }
    }

    try {
      const result = await autoUpdater.checkForUpdates()
      return {
        updateAvailable: result?.updateInfo?.version !== app.getVersion(),
        version: result?.updateInfo?.version,
      }
    } catch (err) {
      console.error('Failed to check for updates:', err)
      return { updateAvailable: false, error: err instanceof Error ? err.message : String(err) }
    }
  })

  ipcMain.handle('install-update', async () => {
    if (isDev) {
      return { success: false, error: 'Updates disabled in development' }
    }

    if (process.windowsStore) {
      return { success: false, error: 'Updates are managed by Microsoft Store builds' }
    }

    if (updaterState.installing) {
      return { success: true, alreadyInProgress: true }
    }

    try {
      updaterState.installing = true
      sendUpdateEvent(getMainWindow, 'update-installing', { version: updaterState.downloadedVersion })

      if (updaterState.installTimeout) {
        clearTimeout(updaterState.installTimeout)
        updaterState.installTimeout = null
      }
      updaterState.installTimeout = setTimeout(() => {
        if (!updaterState.installing) return
        updaterState.installing = false
        sendUpdateEvent(
          getMainWindow,
          'update-error',
          'Update restart is taking longer than expected. Please quit and reopen the app.'
        )
      }, 45000)

      // If we don't already have a ready update, ensure one is downloaded first.
      if (!updaterState.downloadedVersion) {
        await autoUpdater.downloadUpdate()
      }

      // Install is explicitly user-triggered from renderer UI.
      // Important: mark app as quitting-for-update before calling quitAndInstall.
      // electron-updater may close windows before app's before-quit event fires.
      if (typeof prepareForUpdateQuit === 'function') {
        prepareForUpdateQuit()
      }
      autoUpdater.quitAndInstall()
      return { success: true }
    } catch (err) {
      updaterState.installing = false
      if (updaterState.installTimeout) {
        clearTimeout(updaterState.installTimeout)
        updaterState.installTimeout = null
      }
      console.error('Failed to download/install update:', err)
      return { success: false, error: err instanceof Error ? err.message : String(err) }
    }
  })
}

function wireAutoUpdaterEvents({ autoUpdater, getMainWindow }) {
  autoUpdater.on('checking-for-update', () => {
    sendUpdateEvent(getMainWindow, 'update-checking')
  })

  autoUpdater.on('update-available', (info) => {
    console.log('Update available:', info.version)
    sendUpdateEvent(getMainWindow, 'update-available', { version: info.version })
  })

  autoUpdater.on('update-not-available', () => {
    console.log('No update available')
    updaterState.installing = false
    if (updaterState.installTimeout) {
      clearTimeout(updaterState.installTimeout)
      updaterState.installTimeout = null
    }
  })

  autoUpdater.on('download-progress', (progress) => {
    sendUpdateEvent(getMainWindow, 'update-download-progress', Math.round(progress.percent))
  })

  autoUpdater.on('update-downloaded', (info) => {
    console.log('Update downloaded:', info.version)
    updaterState.downloadedVersion = info.version || null
    sendUpdateEvent(getMainWindow, 'update-downloaded', { version: info.version })
    console.log('Update ready to install; awaiting explicit user action')
  })

  autoUpdater.on('error', (err) => {
    updaterState.installing = false
    if (updaterState.installTimeout) {
      clearTimeout(updaterState.installTimeout)
      updaterState.installTimeout = null
    }
    console.error('Auto-updater error:', err)
    sendUpdateEvent(getMainWindow, 'update-error', err instanceof Error ? err.message : String(err))
  })
}

module.exports = {
  setupAutoUpdater,
  registerUpdateIpcHandlers,
  wireAutoUpdaterEvents,
}
