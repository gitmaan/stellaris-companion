const DEFAULT_ANNOUNCEMENTS_URL = 'https://raw.githubusercontent.com/gitmaan/stellaris-companion/main/announcements.json'
const DEFAULT_FETCH_INTERVAL_MS = 1800000 // 30 minutes

/**
 * Compare two semver strings (e.g. "1.2.3" vs "1.3.0").
 * @param {string} a - First version
 * @param {string} b - Second version
 * @returns {number} -1 if a < b, 0 if equal, 1 if a > b
 */
function compareSemver(a, b) {
  const pa = a.split('.').map(Number)
  const pb = b.split('.').map(Number)
  for (let i = 0; i < 3; i++) {
    const na = pa[i] || 0
    const nb = pb[i] || 0
    if (na < nb) return -1
    if (na > nb) return 1
  }
  return 0
}

/**
 * Filter announcements by date range and app version.
 * @param {Object} data - Parsed announcements JSON
 * @param {string} appVersion - Current app version (semver)
 * @returns {Array} Filtered announcements
 */
function filterAnnouncements(data, appVersion) {
  if (!data || !Array.isArray(data.announcements)) return []
  const now = new Date()
  return data.announcements.filter((a) => {
    if (!a.publishedAt || new Date(a.publishedAt) > now) return false
    if (a.expiresAt && new Date(a.expiresAt) <= now) return false
    if (a.minVersion && compareSemver(appVersion, a.minVersion) < 0) return false
    if (a.maxVersion && compareSemver(appVersion, a.maxVersion) > 0) return false
    return true
  })
}

function createAnnouncementsService({ app, store, url = DEFAULT_ANNOUNCEMENTS_URL, fetchIntervalMs = DEFAULT_FETCH_INTERVAL_MS }) {
  let pollTimer = null

  async function fetchAnnouncements(forceRefresh = false) {
    const appVersion = app.getVersion()
    const cached = store.get('announcementsCache')

    if (!forceRefresh && cached && cached.fetchedAt && (Date.now() - cached.fetchedAt < fetchIntervalMs)) {
      return filterAnnouncements(cached.data, appVersion)
    }

    try {
      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 10000)
      const response = await fetch(url, { signal: controller.signal })
      clearTimeout(timeout)

      if (!response.ok) {
        console.error(`Announcements: fetch failed with HTTP ${response.status}`)
        return cached ? filterAnnouncements(cached.data, appVersion) : []
      }

      const data = await response.json()

      // Validate schema version (keep behavior aligned with prior inline implementation)
      if (!data || typeof data.version !== 'number' || data.version > 1) {
        console.log(`Announcements: unknown schema version ${data?.version}, ignoring`)
        return cached ? filterAnnouncements(cached.data, appVersion) : []
      }

      store.set('announcementsCache', { fetchedAt: Date.now(), data })
      console.log(`Announcements: fetched ${data.announcements?.length || 0} announcements`)
      return filterAnnouncements(data, appVersion)
    } catch (e) {
      if (e instanceof Error && e.name === 'AbortError') {
        console.error('Announcements: fetch timed out')
      } else {
        console.error('Announcements: fetch error:', e instanceof Error ? e.message : String(e))
      }
      return cached ? filterAnnouncements(cached.data, appVersion) : []
    }
  }

  function startPolling({ onAnnouncements }) {
    if (pollTimer) clearInterval(pollTimer)

    pollTimer = setInterval(() => {
      fetchAnnouncements().then((announcements) => onAnnouncements(announcements)).catch(() => {})
    }, fetchIntervalMs)
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  return {
    fetchAnnouncements,
    startPolling,
    stopPolling,
  }
}

module.exports = {
  createAnnouncementsService,
}
