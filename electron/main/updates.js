const semver = require('semver')

const IS_E2E = process.env.E2E === '1'
const UPDATE_CHANNELS = ['stable', 'beta']
const DEFAULT_UPDATE_CHANNEL = 'stable'

const updaterState = {
  updateChannel: DEFAULT_UPDATE_CHANNEL,
  availableVersion: null,
  downloadedVersion: null,
  releaseName: null,
  releaseNotes: null,
  installing: false,
  installTimeout: null,
}

function inferUpdateChannelFromVersion(version) {
  const prerelease = semver.prerelease(version)
  return prerelease?.[0] === 'beta' ? 'beta' : DEFAULT_UPDATE_CHANNEL
}

function normalizeUpdateChannel(value, appVersion = '') {
  return UPDATE_CHANNELS.includes(value)
    ? value
    : inferUpdateChannelFromVersion(appVersion)
}

function getFeedChannel(updateChannel) {
  return updateChannel === 'beta' ? 'beta' : 'latest'
}

function resetCachedUpdate() {
  updaterState.availableVersion = null
  updaterState.downloadedVersion = null
  updaterState.releaseName = null
  updaterState.releaseNotes = null
  updaterState.installing = false
  if (updaterState.installTimeout) {
    clearTimeout(updaterState.installTimeout)
    updaterState.installTimeout = null
  }
}

function configureUpdateChannel({ autoUpdater, updateChannel, appVersion = '' }) {
  const normalized = normalizeUpdateChannel(updateChannel, appVersion)
  autoUpdater.channel = getFeedChannel(normalized)
  autoUpdater.allowPrerelease = normalized === 'beta'
  // Setting electron-updater's channel can enable downgrades. Never replace a
  // newer beta with an older stable build; Stable resumes at the next upgrade.
  autoUpdater.allowDowngrade = false
  resetCachedUpdate()
  updaterState.updateChannel = normalized
  return normalized
}

function canUseAutoUpdater({
  app,
  isDev,
  isE2E = IS_E2E,
  platform = process.platform,
  execPath = process.execPath,
  windowsStore = process.windowsStore,
}) {
  if (isE2E || isDev || !app?.isPackaged || windowsStore) return false
  return !(platform === 'darwin' && execPath.includes('/Volumes/'))
}

function checkForUpdatesSafely(autoUpdater, source) {
  try {
    const request = autoUpdater.checkForUpdates()
    if (request && typeof request.catch === 'function') {
      request.catch((error) => console.error(`Auto-updater error (${source}):`, error))
    }
  } catch (error) {
    console.error(`Auto-updater error (${source}):`, error)
  }
}

function applyUpdateChannel({
  autoUpdater,
  app,
  isDev,
  updateChannel,
  checkNow = false,
}) {
  const normalized = configureUpdateChannel({
    autoUpdater,
    updateChannel,
    appVersion: app?.getVersion?.() || '',
  })
  if (checkNow && canUseAutoUpdater({ app, isDev })) {
    checkForUpdatesSafely(autoUpdater, 'channel change')
  }
  return normalized
}

function setupAutoUpdater({ autoUpdater, app, isDev, updateChannel }) {
  applyUpdateChannel({ autoUpdater, app, isDev, updateChannel })
  if (!canUseAutoUpdater({ app, isDev })) return null

  // We use a custom in-app updater UX, so avoid native notifications.
  autoUpdater.autoDownload = true

  // On macOS, keep installs explicitly user-triggered to avoid "silent wait"
  // states where the app appears idle after pressing restart.
  if (process.platform === 'darwin') {
    autoUpdater.autoInstallOnAppQuit = false
  }

  checkForUpdatesSafely(autoUpdater, 'startup')
  const interval = setInterval(
    () => checkForUpdatesSafely(autoUpdater, 'interval'),
    3600000,
  )
  interval.unref?.()
  return interval
}

function decodeHtmlEntities(value) {
  return value
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>')
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'")
}

function stripReleaseNoteHtml(value) {
  return decodeHtmlEntities(
    value
      .replace(/\r\n/g, '\n')
      .replace(/<\s*li\b[^>]*>/gi, '\n- ')
      .replace(/<\s*\/li\s*>/gi, '')
      .replace(/<\s*br\s*\/?>/gi, '\n')
      .replace(/<\s*\/p\s*>/gi, '\n')
      .replace(/<\s*p\b[^>]*>/gi, '')
      .replace(/<\s*\/?(ul|ol|div|section|article|h[1-6])\b[^>]*>/gi, '\n')
      .replace(/<[^>]+>/g, ' ')
  )
}

function normalizeReleaseNotes(releaseNotes) {
  if (typeof releaseNotes === 'string') {
    const trimmed = stripReleaseNoteHtml(releaseNotes)
      .replace(/[ \t]+\n/g, '\n')
      .replace(/\n{3,}/g, '\n\n')
      .replace(/[ \t]{2,}/g, ' ')
      .trim()
    return trimmed.length > 0 ? trimmed : null
  }

  if (Array.isArray(releaseNotes)) {
    const merged = releaseNotes
      .map((entry) => {
        if (!entry || typeof entry.note !== 'string') return ''
        return stripReleaseNoteHtml(entry.note).trim()
      })
      .filter(Boolean)
      .join('\n\n')
      .trim()
    return merged.length > 0 ? merged : null
  }

  return null
}

function isNewerVersion(candidateVersion, currentVersion) {
  const candidate = semver.valid(candidateVersion)
  const current = semver.valid(currentVersion)
  return Boolean(candidate && current && semver.gt(candidate, current))
}

function isVersionAllowedForChannel(version, updateChannel) {
  const validVersion = semver.valid(version)
  if (!validVersion) return false
  const prerelease = semver.prerelease(validVersion)
  if (updateChannel === 'stable') return prerelease === null
  return prerelease === null || prerelease[0] === 'beta'
}

function isEligibleUpdate(candidateVersion, currentVersion) {
  return isNewerVersion(candidateVersion, currentVersion)
    && isVersionAllowedForChannel(candidateVersion, updaterState.updateChannel)
}

function cacheUpdateMetadata(info, { downloaded = false } = {}) {
  if (!info || typeof info !== 'object') return

  if (typeof info.version === 'string' && info.version.length > 0) {
    const isNewVersion = updaterState.availableVersion
      && updaterState.availableVersion !== info.version
    if (isNewVersion) {
      updaterState.releaseName = null
      updaterState.releaseNotes = null
      updaterState.downloadedVersion = null
    }
    updaterState.availableVersion = info.version
    if (downloaded) {
      updaterState.downloadedVersion = info.version
    }
  }

  if (Object.prototype.hasOwnProperty.call(info, 'releaseName')) {
    updaterState.releaseName = typeof info.releaseName === 'string' && info.releaseName.trim()
      ? info.releaseName.trim()
      : null
  }

  if (Object.prototype.hasOwnProperty.call(info, 'releaseNotes')) {
    updaterState.releaseNotes = normalizeReleaseNotes(info.releaseNotes)
  }
}

function buildUpdatePayload(info = {}) {
  const normalizedReleaseNotes = normalizeReleaseNotes(info?.releaseNotes)

  return {
    version: info?.version || updaterState.availableVersion || updaterState.downloadedVersion || undefined,
    releaseName: info?.releaseName || updaterState.releaseName || undefined,
    releaseNotes: normalizedReleaseNotes || updaterState.releaseNotes || undefined,
  }
}

function sendUpdateEvent(getMainWindow, channel, payload) {
  const mainWindow = getMainWindow()
  if (!mainWindow || mainWindow.isDestroyed()) return
  mainWindow.webContents.send(channel, payload)
}

function registerUpdateIpcHandlers({
  ipcMain,
  autoUpdater,
  app,
  isDev,
  getMainWindow,
  prepareForUpdateQuit,
}) {
  ipcMain.handle('check-for-update', async () => {
    if (!canUseAutoUpdater({ app, isDev })) {
      return { updateAvailable: false }
    }

    try {
      const result = await autoUpdater.checkForUpdates()
      const updateInfo = result?.updateInfo
      const updateAvailable = isEligibleUpdate(updateInfo?.version, app.getVersion())
      if (updateAvailable) {
        cacheUpdateMetadata(updateInfo)
      }
      return {
        updateAvailable,
        ...(updateAvailable ? buildUpdatePayload(updateInfo) : {}),
      }
    } catch (error) {
      console.error('Failed to check for updates:', error)
      return {
        updateAvailable: false,
        error: error instanceof Error ? error.message : String(error),
      }
    }
  })

  ipcMain.handle('install-update', async () => {
    if (IS_E2E) {
      return { success: false, error: 'Updates disabled in E2E mode' }
    }
    if (isDev) {
      return { success: false, error: 'Updates disabled in development' }
    }
    if (process.windowsStore) {
      return { success: false, error: 'Updates are managed by Microsoft Store builds' }
    }
    if (!isEligibleUpdate(updaterState.availableVersion, app.getVersion())) {
      return { success: false, error: 'No newer update is ready to install' }
    }
    if (updaterState.installing) {
      return { success: true, alreadyInProgress: true }
    }

    try {
      updaterState.installing = true
      sendUpdateEvent(getMainWindow, 'update-installing', buildUpdatePayload())

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

      if (!isEligibleUpdate(updaterState.downloadedVersion, app.getVersion())) {
        await autoUpdater.downloadUpdate()
      }
      if (!isEligibleUpdate(updaterState.downloadedVersion, app.getVersion())) {
        throw new Error('The update has not finished downloading')
      }

      if (typeof prepareForUpdateQuit === 'function') {
        prepareForUpdateQuit()
      }
      autoUpdater.quitAndInstall()
      return { success: true }
    } catch (error) {
      updaterState.installing = false
      if (updaterState.installTimeout) {
        clearTimeout(updaterState.installTimeout)
        updaterState.installTimeout = null
      }
      console.error('Failed to download/install update:', error)
      return { success: false, error: error instanceof Error ? error.message : String(error) }
    }
  })
}

function wireAutoUpdaterEvents({ autoUpdater, app, getMainWindow }) {
  autoUpdater.on('checking-for-update', () => {
    sendUpdateEvent(getMainWindow, 'update-checking')
  })

  autoUpdater.on('update-available', (info) => {
    if (!isEligibleUpdate(info?.version, app.getVersion())) {
      console.log('Ignoring ineligible update:', info?.version)
      return
    }
    cacheUpdateMetadata(info)
    console.log('Update available:', info.version)
    sendUpdateEvent(getMainWindow, 'update-available', buildUpdatePayload(info))
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
    if (!isEligibleUpdate(info?.version, app.getVersion())) {
      console.log('Ignoring ineligible downloaded update:', info?.version)
      return
    }
    cacheUpdateMetadata(info, { downloaded: true })
    console.log('Update downloaded:', info.version)
    sendUpdateEvent(getMainWindow, 'update-downloaded', buildUpdatePayload(info))
    console.log('Update ready to install; awaiting explicit user action')
  })

  autoUpdater.on('error', (error) => {
    updaterState.installing = false
    if (updaterState.installTimeout) {
      clearTimeout(updaterState.installTimeout)
      updaterState.installTimeout = null
    }
    console.error('Auto-updater error:', error)
    sendUpdateEvent(
      getMainWindow,
      'update-error',
      error instanceof Error ? error.message : String(error),
    )
  })
}

module.exports = {
  DEFAULT_UPDATE_CHANNEL,
  UPDATE_CHANNELS,
  applyUpdateChannel,
  canUseAutoUpdater,
  configureUpdateChannel,
  getFeedChannel,
  inferUpdateChannelFromVersion,
  isEligibleUpdate,
  isNewerVersion,
  isVersionAllowedForChannel,
  normalizeUpdateChannel,
  registerUpdateIpcHandlers,
  setupAutoUpdater,
  wireAutoUpdaterEvents,
}
