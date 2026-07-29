const assert = require('node:assert/strict')
const { EventEmitter } = require('node:events')
const test = require('node:test')

const {
  isNewerVersion,
  registerUpdateIpcHandlers,
  wireAutoUpdaterEvents,
} = require('../main/updates')

test('compares update versions semantically', () => {
  assert.equal(isNewerVersion('0.9.1', '0.9.0'), true)
  assert.equal(isNewerVersion('0.10.0', '0.9.9'), true)
  assert.equal(isNewerVersion('0.8.4', '0.9.0'), false)
  assert.equal(isNewerVersion('0.9.0', '0.9.0'), false)
  assert.equal(isNewerVersion('not-a-version', '0.9.0'), false)
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
    app: { getVersion: () => '0.9.0' },
    getMainWindow: () => mainWindow,
  })

  autoUpdater.emit('update-available', { version: '0.8.4' })
  autoUpdater.emit('update-downloaded', { version: '0.8.4' })
  assert.deepEqual(sent, [])

  autoUpdater.emit('update-downloaded', {
    version: '0.9.1',
    releaseNotes: '- Safer updates.',
  })
  assert.deepEqual(sent, [{
    channel: 'update-downloaded',
    payload: {
      version: '0.9.1',
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
    app: { getVersion: () => '0.9.0' },
    isDev: false,
    getMainWindow: () => null,
    prepareForUpdateQuit: () => {},
  })

  const result = await handlers.get('check-for-update')()
  assert.deepEqual(result, { updateAvailable: false })
})
