const assert = require('node:assert/strict')
const test = require('node:test')
const { createAnnouncementsService } = require('../main/announcements')
const { getAnnouncementReadIds } = require('../main/announcementsState')
const { registerAnnouncementsIpcHandlers } = require('../main/ipc/announcements')

function createStore(initial = {}) {
  const state = new Map(Object.entries(initial))
  return {
    get: (key, fallback) => state.has(key) ? state.get(key) : fallback,
    set: (key, value) => state.set(key, value),
  }
}

function announcement(id, overrides = {}) {
  return { id, title: id, body: 'Fictional transmission', severity: 'info', publishedAt: '2020-01-01T00:00:00Z', ...overrides }
}

function feed(...announcements) {
  return { version: 1, announcements }
}

function service(store) {
  return createAnnouncementsService({ app: { getVersion: () => '1.1.0' }, store })
}

test('legacy migration preserves IDs available when the panel was read', () => {
  const lastRead = Date.parse('2020-02-01T00:00:00Z')
  const store = createStore({
    announcementsLastRead: lastRead,
    announcementsCache: {
      fetchedAt: lastRead - 1000,
      data: feed(announcement('already-seen'), announcement('not-published-yet', { publishedAt: '2020-03-01T00:00:00Z' })),
    },
  })
  assert.deepEqual(getAnnouncementReadIds(store), ['already-seen'])
  assert.deepEqual(store.get('announcementsReadIds'), ['already-seen'])
})

test('a feed fetched after the legacy read time does not hide unseen IDs', () => {
  const lastRead = Date.parse('2020-02-01T00:00:00Z')
  const store = createStore({
    announcementsLastRead: lastRead,
    announcementsCache: { fetchedAt: lastRead + 1000, data: feed(announcement('arrived-late')) },
  })
  assert.deepEqual(getAnnouncementReadIds(store), [])
})

test('startup refresh migrates the old cache first and leaves new IDs unread', async (t) => {
  const lastRead = Date.now() - 1000
  const store = createStore({
    announcementsLastRead: lastRead,
    announcementsCache: { fetchedAt: lastRead - 1000, data: feed(announcement('seen')) },
  })
  const latest = feed(announcement('seen'), announcement('new-but-published-before-last-read'))
  t.mock.method(global, 'fetch', async () => ({ ok: true, json: async () => latest }))
  assert.deepEqual(await service(store).fetchAnnouncements(true), latest.announcements)
  assert.deepEqual(getAnnouncementReadIds(store), ['seen'])
  assert.deepEqual(store.get('announcementsCache').data, latest)
})

test('forced launch refresh bypasses a recent cache and concurrent callers share it', async (t) => {
  const store = createStore({ announcementsCache: { fetchedAt: Date.now(), data: feed(announcement('old')) } })
  let finishFetch
  const latest = feed(announcement('new'))
  const fetchMock = t.mock.method(global, 'fetch', () => new Promise((resolve) => { finishFetch = resolve }))
  const announcements = service(store)
  assert.deepEqual((await announcements.fetchAnnouncements()).map((item) => item.id), ['old'])
  assert.equal(fetchMock.mock.callCount(), 0)
  const startup = announcements.fetchAnnouncements(true)
  const renderer = announcements.fetchAnnouncements(true)
  const cachedCaller = announcements.fetchAnnouncements()
  assert.equal(fetchMock.mock.callCount(), 1)
  finishFetch({ ok: true, json: async () => latest })
  for (const result of await Promise.all([startup, renderer, cachedCaller])) {
    assert.deepEqual(result, latest.announcements)
  }
  assert.deepEqual(getAnnouncementReadIds(store), [])
})

test('offline refresh retains eligible cached items and retries successfully', async (t) => {
  const cached = feed(
    announcement('still-current'),
    announcement('expired', { expiresAt: '2020-02-01T00:00:00Z' }),
    announcement('future', { publishedAt: '2999-01-01T00:00:00Z' }),
    announcement('newer-app-only', { minVersion: '99.0.0' }),
  )
  const store = createStore({ announcementsCache: { fetchedAt: Date.now(), data: cached } })
  const fetchMock = t.mock.method(global, 'fetch', async () => { throw new Error('offline fixture') })
  const announcements = service(store)
  assert.deepEqual((await announcements.fetchAnnouncements(true)).map((item) => item.id), ['still-current'])
  assert.deepEqual(getAnnouncementReadIds(store), [])
  fetchMock.mock.mockImplementation(async () => ({ ok: true, json: async () => feed() }))
  assert.deepEqual(await announcements.fetchAnnouncements(true), [])
  assert.deepEqual(store.get('announcementsCache').data, feed())
})

test('mark-read acknowledges only displayed IDs and validates its sender', async () => {
  const store = createStore({ announcementsReadIds: ['seen'], announcementsDismissed: ['dismissed'] })
  const handlers = new Map()
  registerAnnouncementsIpcHandlers({
    ipcMain: { handle: (channel, handler) => handlers.set(channel, handler) },
    validateSender: (event) => { if (event !== 'trusted') throw new Error('Untrusted sender') },
    store,
    announcementsService: service(store),
  })
  const invoke = (channel, payload, sender = 'trusted') => handlers.get(channel)(sender, payload)
  await assert.rejects(invoke('announcements:mark-read', { ids: ['unseen'] }, 'untrusted'), /Untrusted/)
  await assert.rejects(invoke('announcements:get-read-ids', {}, 'untrusted'), /Untrusted/)
  assert.deepEqual(await invoke('announcements:mark-read', { ids: ['displayed', 'displayed', '', null, 3] }), {
    success: true, readIds: ['seen', 'displayed'],
  })
  store.set('announcementsCache', { fetchedAt: Date.now(), data: feed(announcement('unseen')) })
  assert.deepEqual(await invoke('announcements:get-read-ids'), ['seen', 'displayed'])
  assert.deepEqual(await invoke('announcements:get-dismissed'), ['dismissed'])
  assert.deepEqual((await invoke('announcements:mark-read')).readIds, ['seen', 'displayed'])
})
