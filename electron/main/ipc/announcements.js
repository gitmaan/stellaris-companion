function getDismissedIds(store) {
  const stored = store.get('announcementsDismissed', [])
  return Array.isArray(stored) ? stored.filter((id) => typeof id === 'string') : []
}

function setDismissedIds(store, ids) {
  const uniqueIds = Array.from(new Set(ids.filter((id) => typeof id === 'string')))
  store.set('announcementsDismissed', uniqueIds)
  return uniqueIds
}

function registerAnnouncementsIpcHandlers({ ipcMain, validateSender, store, announcementsService }) {
  ipcMain.handle('announcements:fetch', async (event, payload = {}) => {
    validateSender(event)
    const forceRefresh = !!payload.forceRefresh
    return await announcementsService.fetchAnnouncements(forceRefresh)
  })

  ipcMain.handle('announcements:dismiss', async (event, payload = {}) => {
    validateSender(event)
    const { id } = payload
    if (typeof id !== 'string' || id.trim() === '') {
      return { success: false, error: 'Invalid announcement ID' }
    }
    const dismissed = getDismissedIds(store)
    if (!dismissed.includes(id)) {
      dismissed.push(id)
      setDismissedIds(store, dismissed)
    }
    return { success: true }
  })

  ipcMain.handle('announcements:dismiss-many', async (event, payload = {}) => {
    validateSender(event)
    const { ids } = payload
    const nextIds = Array.isArray(ids) ? ids : []
    const dismissed = getDismissedIds(store)
    const merged = setDismissedIds(store, [...dismissed, ...nextIds])
    return { success: true, dismissed: merged }
  })

  ipcMain.handle('announcements:undismiss', async (event, payload = {}) => {
    validateSender(event)
    const { id } = payload
    if (typeof id !== 'string' || id.trim() === '') {
      return { success: false, error: 'Invalid announcement ID' }
    }
    const dismissed = getDismissedIds(store)
    const nextDismissed = dismissed.filter((dismissedId) => dismissedId !== id)
    setDismissedIds(store, nextDismissed)
    return { success: true }
  })

  ipcMain.handle('announcements:reset-dismissed', async (event) => {
    validateSender(event)
    setDismissedIds(store, [])
    return { success: true }
  })

  ipcMain.handle('announcements:get-dismissed', async (event) => {
    validateSender(event)
    return getDismissedIds(store)
  })

  ipcMain.handle('announcements:mark-read', async (event) => {
    validateSender(event)
    store.set('announcementsLastRead', Date.now())
    return { success: true }
  })

  ipcMain.handle('announcements:get-last-read', async (event) => {
    validateSender(event)
    return store.get('announcementsLastRead', 0)
  })
}

module.exports = {
  registerAnnouncementsIpcHandlers,
}
