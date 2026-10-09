function normalizeIds(ids) {
  return Array.from(new Set(Array.isArray(ids)
    ? ids.filter((id) => typeof id === 'string' && id.trim() !== '')
    : []))
}

function getAnnouncementReadIds(store) {
  const stored = store.get('announcementsReadIds')
  if (Array.isArray(stored)) return normalizeIds(stored)

  // A legacy timestamp only proves that cached items were seen when that
  // cache already existed at the time. Never mark a later fetch as read.
  const lastRead = Number(store.get('announcementsLastRead', 0))
  const cached = store.get('announcementsCache')
  const fetchedAt = Number(cached?.fetchedAt)
  const wasAvailableWhenRead = Number.isFinite(fetchedAt) && fetchedAt > 0
    && Number.isFinite(lastRead) && fetchedAt <= lastRead
  const announcements = Array.isArray(cached?.data?.announcements) ? cached.data.announcements : []
  const ids = wasAvailableWhenRead
    ? normalizeIds(announcements.filter((item) => Date.parse(item?.publishedAt) <= lastRead).map((item) => item.id))
    : []
  store.set('announcementsReadIds', ids)
  return ids
}

function markAnnouncementIdsRead(store, ids) {
  const read = normalizeIds([...getAnnouncementReadIds(store), ...normalizeIds(ids)])
  store.set('announcementsReadIds', read)
  return read
}

module.exports = { getAnnouncementReadIds, markAnnouncementIdsRead }
