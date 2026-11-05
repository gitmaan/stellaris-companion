const fs = require('node:fs')
const path = require('node:path')
const Store = require('electron-store')

const DEFAULT_MODEL_ROUTING_MODE = 'quality_first'

function normalizeModelRoutingMode(value, fallback = DEFAULT_MODEL_ROUTING_MODE) {
  if (typeof value !== 'string') return fallback
  const normalized = value.trim().toLowerCase().replace(/-/g, '_')
  if (['quality_first', 'quality', 'auto', 'flash_first'].includes(normalized)) return 'quality_first'
  if (['conserve', 'quota_saver', 'free_tier', 'lite_first', 'flash_lite_first'].includes(normalized)) return 'conserve'
  return fallback
}

function createSettingsStore({ cwd, defaults = {}, ...options }) {
  // electron-store merges and persists defaults during construction. Detect an
  // upgrade first, or a missing legacy preference would silently switch tiers.
  const routingDefault = fs.existsSync(path.join(cwd, 'settings.json'))
    ? 'conserve'
    : DEFAULT_MODEL_ROUTING_MODE
  const store = new Store({
    ...options,
    cwd,
    name: 'settings',
    defaults: { ...defaults, modelRoutingMode: routingDefault },
  })
  const saved = store.get('modelRoutingMode')
  const normalized = normalizeModelRoutingMode(saved, routingDefault)
  if (saved !== normalized) store.set('modelRoutingMode', normalized)
  return store
}

module.exports = { createSettingsStore, normalizeModelRoutingMode, DEFAULT_MODEL_ROUTING_MODE }
