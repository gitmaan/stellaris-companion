const assert = require('node:assert/strict')
const { EventEmitter } = require('node:events')
const test = require('node:test')

const {
  applyUpdateChannel,
  canUseAutoUpdater,
  configureUpdateChannel,
  inferUpdateChannelFromVersion,
  isVersionAllowedForChannel,
  isNewerVersion,
  normalizeUpdateChannel,
  registerUpdateIpcHandlers,
  wireAutoUpdaterEvents,
} = require('../main/updates')

test('infers update preferences from stable and beta app versions', () => {
  assert.equal(inferUpdateChannelFromVersion('0.8.5'), 'stable')
  assert.equal(inferUpdateChannelFromVersion('0.9.0-beta.1'), 'beta')
  assert.equal(inferUpdateChannelFromVersion('0.9.0-alpha.1'), 'stable')
  assert.equal(inferUpdateChannelFromVersion('invalid'), 'stable')
  assert.equal(normalizeUpdateChannel('beta', '0.8.5'), 'beta')
  assert.equal(normalizeUpdateChannel('invalid', '0.9.0-beta.2'), 'beta')
})

test('configures updater feeds without permitting downgrades', () => {
  const autoUpdater = {}

  assert.equal(configureUpdateChannel({
    autoUpdater,
    updateChannel: 'beta',
    appVersion: '0.8.5',
  }), 'beta')
  assert.equal(autoUpdater.channel, 'beta')
  assert.equal(autoUpdater.allowPrerelease, true)
  assert.equal(autoUpdater.allowDowngrade, false)

  assert.equal(configureUpdateChannel({
    autoUpdater,
    updateChannel: 'stable',
    appVersion: '0.9.0-beta.1',
  }), 'stable')
  assert.equal(autoUpdater.channel, 'latest')
  assert.equal(autoUpdater.allowPrerelease, false)
  assert.equal(autoUpdater.allowDowngrade, false)
})

test('checks immediately after a real packaged app changes channel', async () => {
  let checks = 0
  const autoUpdater = {
    checkForUpdates: async () => {
      checks += 1
    },
  }

  applyUpdateChannel({
    autoUpdater,
    app: { isPackaged: true, getVersion: () => '0.8.5' },
    isDev: false,
    updateChannel: 'beta',
    checkNow: true,
  })
  await new Promise(resolve => setImmediate(resolve))

  assert.equal(checks, 1)
  assert.equal(autoUpdater.channel, 'beta')
})

test('disables updater access in unsupported runtime contexts', () => {
  const packagedApp = { isPackaged: true }
  assert.equal(canUseAutoUpdater({ app: packagedApp, isDev: true }), false)
  assert.equal(canUseAutoUpdater({ app: packagedApp, isDev: false, isE2E: true }), false)
  assert.equal(canUseAutoUpdater({
    app: packagedApp,
    isDev: false,
    isE2E: false,
    windowsStore: true,
  }), false)
  assert.equal(canUseAutoUpdater({
    app: packagedApp,
    isDev: false,
    isE2E: false,
    platform: 'darwin',
    execPath: '/Volumes/Stellaris Companion/Stellaris Companion.app',
  }), false)
})

test('compares update versions semantically', () => {
  assert.equal(isNewerVersion('0.9.1', '0.9.0'), true)
  assert.equal(isNewerVersion('0.10.0', '0.9.9'), true)
  assert.equal(isNewerVersion('0.8.4', '0.9.0'), false)
  assert.equal(isNewerVersion('0.9.0', '0.9.0'), false)
  assert.equal(isNewerVersion('not-a-version', '0.9.0'), false)
})

test('allows only releases appropriate for the selected channel', () => {
  assert.equal(isVersionAllowedForChannel('0.8.6', 'stable'), true)
  assert.equal(isVersionAllowedForChannel('0.9.0-beta.1', 'stable'), false)
  assert.equal(isVersionAllowedForChannel('0.8.6', 'beta'), true)
  assert.equal(isVersionAllowedForChannel('0.9.0-beta.1', 'beta'), true)
  assert.equal(isVersionAllowedForChannel('0.9.0-alpha.1', 'beta'), false)
})

test('drops a late beta download after switching back to Stable', () => {
  const autoUpdater = new EventEmitter()
  const sent = []
  const mainWindow = {
    isDestroyed: () => false,
    webContents: {
      send: (channel, payload) => sent.push({ channel, payload }),
    },
  }

  wireAutoUpdaterEvents({
    autoUpdater,
    app: { getVersion: () => '0.8.5' },
    getMainWindow: () => mainWindow,
  })
  configureUpdateChannel({
    autoUpdater,
    updateChannel: 'stable',
    appVersion: '0.8.5',
  })
  autoUpdater.emit('update-downloaded', { version: '0.9.0-beta.1' })

  assert.deepEqual(sent, [])
})

test('ignores stale updater events and forwards a newer download', () => {
  const autoUpdater = new EventEmitter()
  const sent = []
  const mainWindow = {
    isDestroyed: () => false,
    webContents: {
      send: (channel, payload) => sent.push({ channel, payload }),
    },
  }

  wireAutoUpdaterEvents({
    autoUpdater,
    app: { isPackaged: true, getVersion: () => '0.8.5' },
    getMainWindow: () => mainWindow,
  })

  autoUpdater.emit('update-available', { version: '0.8.4' })
  autoUpdater.emit('update-downloaded', { version: '0.8.4' })
  assert.deepEqual(sent, [])

  autoUpdater.emit('update-downloaded', {
    version: '0.8.6',
    releaseNotes: '- Safer updates.',
  })
  assert.deepEqual(sent, [{
    channel: 'update-downloaded',
    payload: {
      version: '0.8.6',
      releaseName: undefined,
      releaseNotes: '- Safer updates.',
    },
  }])
})

test('manual checks do not offer an older published release', async () => {
  const handlers = new Map()
  const ipcMain = {
    handle: (channel, handler) => handlers.set(channel, handler),
  }
  const autoUpdater = {
    checkForUpdates: async () => ({
      updateInfo: {
        version: '0.8.4',
        releaseNotes: '- Older release.',
      },
    }),
  }

  registerUpdateIpcHandlers({
    ipcMain,
    autoUpdater,
    app: { getVersion: () => '0.8.5' },
    isDev: false,
    getMainWindow: () => null,
    prepareForUpdateQuit: () => {},
  })

  const result = await handlers.get('check-for-update')()
  assert.deepEqual(result, { updateAvailable: false })
})
