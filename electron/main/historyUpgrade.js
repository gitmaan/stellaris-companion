const HISTORY_UPGRADE_ERROR_MARKER = 'HISTORY_DB_UPGRADE_FAILED:'

function extractHistoryUpgradeError(stderr) {
  const text = String(stderr || '')
  const markerIndex = text.lastIndexOf(HISTORY_UPGRADE_ERROR_MARKER)
  if (markerIndex < 0) return null
  const detail = text
    .slice(markerIndex + HISTORY_UPGRADE_ERROR_MARKER.length)
    .split(/\r?\n/, 1)[0]
    .trim()
  return detail || 'The campaign-history database could not be upgraded safely.'
}

function buildHistoryUpgradeFailureDialog(detail) {
  return {
    type: 'error',
    title: 'Campaign History Upgrade Paused',
    message: 'Your existing Chronicles were not changed.',
    detail: [
      'Stellaris Companion stopped the upgrade because it could not create or verify a safety backup.',
      'Check available disk space and app-data folder permissions, then reopen the app.',
      detail ? `Details: ${detail}` : '',
    ].filter(Boolean).join('\n\n'),
    buttons: ['OK'],
    defaultId: 0,
  }
}

module.exports = {
  HISTORY_UPGRADE_ERROR_MARKER,
  buildHistoryUpgradeFailureDialog,
  extractHistoryUpgradeError,
}
