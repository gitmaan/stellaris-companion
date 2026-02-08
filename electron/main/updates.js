function setupAutoUpdater({ autoUpdater, app, isDev }) {
  if (isDev) return
  if (!app?.isPackaged) return
  if (process.windowsStore) return

  // On macOS, running directly from a mounted .dmg (e.g. /Volumes/...) can cause
  // updater errors. Only auto-check once installed.
  if (process.platform === 'darwin' && process.execPath.includes('/Volumes/')) {
    return
  }

  // Avoid startup crashes on platforms/configs where update checks can throw
  // synchronously or reject promises (network, feed parsing, etc).
  try {
    const p = autoUpdater.checkForUpdatesAndNotify()
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

function registerUpdateIpcHandlers({ ipcMain, autoUpdater, app, isDev }) {
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

    try {
      await autoUpdater.downloadUpdate()
      // Install is explicitly user-triggered from renderer UI.
      autoUpdater.quitAndInstall()
      return { success: true }
    } catch (err) {
      console.error('Failed to download/install update:', err)
      return { success: false, error: err instanceof Error ? err.message : String(err) }
    }
  })
}

function wireAutoUpdaterEvents({ autoUpdater, getMainWindow }) {
  autoUpdater.on('checking-for-update', () => {
    const mainWindow = getMainWindow()
    if (mainWindow) {
      mainWindow.webContents.send('update-checking')
    }
  })

  autoUpdater.on('update-available', (info) => {
    console.log('Update available:', info.version)
    const mainWindow = getMainWindow()
    if (mainWindow) {
      mainWindow.webContents.send('update-available', { version: info.version })
    }
  })

  autoUpdater.on('update-not-available', () => {
    console.log('No update available')
  })

  autoUpdater.on('download-progress', (progress) => {
    const mainWindow = getMainWindow()
    if (mainWindow) {
      mainWindow.webContents.send('update-download-progress', Math.round(progress.percent))
    }
  })

  autoUpdater.on('update-downloaded', (info) => {
    console.log('Update downloaded:', info.version)
    const mainWindow = getMainWindow()
    if (mainWindow) {
      mainWindow.webContents.send('update-downloaded', { version: info.version })
    }
    console.log('Update ready to install; awaiting explicit user action')
  })

  autoUpdater.on('error', (err) => {
    console.error('Auto-updater error:', err)
    const mainWindow = getMainWindow()
    if (mainWindow) {
      mainWindow.webContents.send('update-error', err instanceof Error ? err.message : String(err))
    }
  })
}

module.exports = {
  setupAutoUpdater,
  registerUpdateIpcHandlers,
  wireAutoUpdaterEvents,
}
