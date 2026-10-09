const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const { EventEmitter } = require('node:events')
const test = require('node:test')

function setup() {
  const ipcRenderer = new EventEmitter()
  ipcRenderer.invoke = () => { throw new Error('Status replay must not issue an IPC request') }
  let api
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../preload.js'), 'utf8'), {
    require: name => {
      assert.equal(name, 'electron')
      return { ipcRenderer, contextBridge: { exposeInMainWorld: (name, value) => {
        assert.equal(name, 'electronAPI')
        api = value
      } } }
    },
    process: { platform: 'darwin', arch: 'arm64' },
  })
  return { api, ipcRenderer, status: payload => ipcRenderer.emit('backend-status', {}, payload) }
}

test('late subscribers receive the initial cached health result and subsequent updates', () => {
  const app = setup()
  const initial = { connected: true, save_loaded: true, precompute_ready: true }
  app.status(initial)
  const received = []
  const unsubscribe = app.api.onBackendStatus(status => received.push(status))
  assert.deepEqual(received, [initial])
  const offline = { connected: false }
  app.status(offline)
  assert.deepEqual(received, [initial, offline])
  unsubscribe()
  app.status({ connected: true })
  assert.equal(received.length, 2)
})

test('repeated view mounts share one IPC listener and replay the newest status', () => {
  const app = setup()
  for (let i = 0; i < 100; i++) {
    const latest = { connected: true, game_date: `2200.01.${i}` }
    app.status(latest)
    const received = []
    const unsubscribe = app.api.onBackendStatus(status => received.push(status))
    assert.deepEqual(received, [latest])
    assert.equal(app.ipcRenderer.listenerCount('backend-status'), 1)
    unsubscribe()
  }
  assert.equal(app.ipcRenderer.listenerCount('backend-status'), 1)
})

test('subscriptions before the first health result wait, and a failed replay is cleaned up', () => {
  const app = setup()
  const received = []
  const unsubscribe = app.api.onBackendStatus(status => received.push(status))
  assert.deepEqual(received, [])
  app.status({ connected: false })
  assert.equal(received.length, 1)
  unsubscribe()
  assert.throws(() => app.api.onBackendStatus(() => { throw new Error('View failed') }), /View failed/)
  assert.doesNotThrow(() => app.status({ connected: true }))
})
