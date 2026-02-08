function createHealthCheckManager({
  checkBackendHealth,
  getMainWindow,
  getBackendConfigured,
  onStatusPayload,
  updateTrayMenu,
  intervalMs,
  failThreshold,
}) {
  if (typeof checkBackendHealth !== 'function') throw new Error('createHealthCheckManager: checkBackendHealth() is required')
  if (typeof getMainWindow !== 'function') throw new Error('createHealthCheckManager: getMainWindow() is required')
  if (typeof getBackendConfigured !== 'function') throw new Error('createHealthCheckManager: getBackendConfigured() is required')
  if (typeof onStatusPayload !== 'function') throw new Error('createHealthCheckManager: onStatusPayload() is required')
  if (typeof updateTrayMenu !== 'function') throw new Error('createHealthCheckManager: updateTrayMenu() is required')

  let timer = null
  let inFlight = false
  let failCount = 0
  let isQuitting = false

  function stop() {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }

  function setIsQuitting(next) {
    isQuitting = !!next
  }

  function start() {
    stop()
    failCount = 0

    const perform = async () => {
      if (isQuitting || inFlight) return
      inFlight = true
      try {
        const health = await checkBackendHealth()
        failCount = 0

        const payload = {
          connected: true,
          backend_configured: getBackendConfigured(),
          ...health,
        }

        onStatusPayload(payload)

        const mainWindow = getMainWindow()
        if (mainWindow) {
          mainWindow.webContents.send('backend-status', payload)
        }
      } catch (e) {
        failCount++

        if (failCount >= failThreshold) {
          const payload = {
            connected: false,
            backend_configured: getBackendConfigured(),
            error: e instanceof Error ? e.message : 'Backend health check failed',
          }

          onStatusPayload(payload)

          const mainWindow = getMainWindow()
          if (mainWindow) {
            mainWindow.webContents.send('backend-status', payload)
          }
        }
      } finally {
        inFlight = false
        updateTrayMenu()
      }
    }

    timer = setInterval(perform, intervalMs)
    perform().catch(() => {})
  }

  return {
    start,
    stop,
    setIsQuitting,
  }
}

module.exports = {
  createHealthCheckManager,
}

