const assert = require('node:assert/strict')
const test = require('node:test')

const {
  buildHistoryUpgradeFailureDialog,
  extractHistoryUpgradeError,
} = require('../main/historyUpgrade')

test('extracts the protected database-upgrade error from backend logs', () => {
  const stderr = [
    '2026-08-08 INFO Starting backend',
    '2026-08-08 ERROR HISTORY_DB_UPGRADE_FAILED: Could not create safety backup',
    '2026-08-08 INFO Backend stopped',
  ].join('\n')

  assert.equal(
    extractHistoryUpgradeError(stderr),
    'Could not create safety backup',
  )
  assert.equal(extractHistoryUpgradeError('ordinary backend error'), null)
})

test('upgrade failure dialog explains that existing Chronicles were protected', () => {
  const options = buildHistoryUpgradeFailureDialog('Disk is full')

  assert.equal(options.type, 'error')
  assert.match(options.title, /Upgrade Paused/)
  assert.match(options.message, /Chronicles were not changed/)
  assert.match(options.detail, /disk space/i)
  assert.match(options.detail, /Disk is full/)
})
