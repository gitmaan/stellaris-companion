const http = require('http')

function buildChronicleText(narrative) {
  return `### THE CURRENT ERA\n**2200.01.01 - Present**\n\n${narrative}`
}

function buildChronicleResponse({ narrative, eventsCovered, cached }) {
  return {
    chapters: [],
    current_era: {
      start_date: '2200.01.01',
      narrative,
      events_covered: eventsCovered,
      sections: [
        {
          type: 'prose',
          text: narrative,
          attribution: '',
        },
      ],
    },
    pending_chapters: 0,
    message: null,
    chronicle: buildChronicleText(narrative),
    cached,
    event_count: eventsCovered,
    generated_at: '2026-03-06T00:00:00Z',
  }
}

function readJsonBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = []
    req.on('data', (chunk) => chunks.push(chunk))
    req.on('end', () => {
      if (chunks.length === 0) {
        resolve({})
        return
      }
      try {
        resolve(JSON.parse(Buffer.concat(chunks).toString('utf8')))
      } catch (error) {
        reject(error)
      }
    })
    req.on('error', reject)
  })
}

function sendJson(res, statusCode, payload) {
  res.writeHead(statusCode, { 'Content-Type': 'application/json' })
  res.end(JSON.stringify(payload))
}

function createMockChronicleBackend(options = {}) {
  let server = null
  let phase = 'initial'
  let healthUpdatedAt = 1_000
  let publication = null
  const chronicleRequests = []
  const publicationRequests = []
  const publishedStoryId = options.publishedStoryId ?? '84b66f39-ccab-4d60-8d50-82b34537cb5d'
  const initialEventsCovered = options.initialEventsCovered ?? 2
  const advancedEventsCovered = options.advancedEventsCovered ?? 5
  const initialNarrative = options.initialNarrative ?? 'Old teaser.'
  const updatedNarrative = options.updatedNarrative ?? 'Updated after visible refresh.'
  const balancedThreshold = options.balancedThreshold ?? 3
  const enhancedThreshold = options.enhancedThreshold ?? 1

  const healthPayload = () => ({
    status: 'ok',
    save_loaded: true,
    empire_name: 'United Nations of Earth',
    game_date: phase === 'initial' ? '2205.01.01' : '2208.01.01',
    precompute_ready: true,
    empire_type: 'standard',
    empire_ethics: ['egalitarian', 'xenophile'],
    empire_civics: ['idealistic_foundation'],
    empire_authority: 'democratic',
    empire_origin: 'prosperous_unification',
    ingestion: {
      updated_at: healthUpdatedAt,
      current_save_path: 'C:\\\\mock\\\\save.sav',
    },
  })

  const sessionsPayload = () => ({
    sessions: [
      {
        id: 'session-1',
        save_id: 'save-1',
        empire_name: 'United Nations of Earth',
        started_at: 1,
        ended_at: null,
        first_game_date: '2200.01.01',
        last_game_date: phase === 'initial' ? '2205.01.01' : '2208.01.01',
        snapshot_count: phase === 'initial' ? 3 : 4,
        is_active: true,
      },
    ],
  })

  const statusPayload = () => ({
    empire_name: 'United Nations of Earth',
    game_date: phase === 'initial' ? '2205.01.01' : '2208.01.01',
    military_power: 1200,
    economy: {
      energy: { income: 50, expense: 30, net: 20 },
      minerals: { income: 40, expense: 25, net: 15 },
      alloys: { income: 15, expense: 10, net: 5 },
    },
    colonies: 4,
    pops: 120,
    active_wars: 0,
  })

  const chroniclePayload = (body) => {
    if (phase === 'initial') {
      return buildChronicleResponse({
        narrative: initialNarrative,
        eventsCovered: initialEventsCovered,
        cached: false,
      })
    }

    if (body.chapter_only) {
      return buildChronicleResponse({
        narrative: initialNarrative,
        eventsCovered: initialEventsCovered,
        cached: true,
      })
    }

    const refreshMode = body.refresh_mode === 'enhanced' ? 'enhanced' : 'balanced'
    const eventGrowth = Math.max(0, advancedEventsCovered - initialEventsCovered)
    const threshold = refreshMode === 'enhanced' ? enhancedThreshold : balancedThreshold
    if (eventGrowth < threshold) {
      return buildChronicleResponse({
        narrative: initialNarrative,
        eventsCovered: initialEventsCovered,
        cached: true,
      })
    }

    return buildChronicleResponse({
      narrative: updatedNarrative,
      eventsCovered: advancedEventsCovered,
      cached: false,
    })
  }

  const publicationPayload = () => ({
    story_id: publishedStoryId,
    public_url: `https://galacticfilingcabinet.com/chronicles/${publishedStoryId}`,
    revision: publication.revision,
    visibility: publication.visibility,
    moderation_status: publication.visibility === 'discoverable' ? 'pending' : 'not_required',
    published_at: publication.publishedAt,
    updated_at: publication.updatedAt,
  })

  async function handler(req, res) {
    const url = new URL(req.url, 'http://127.0.0.1')

    if (req.method === 'GET' && url.pathname === '/api/health') {
      sendJson(res, 200, healthPayload())
      return
    }

    if (req.method === 'GET' && url.pathname === '/api/status') {
      sendJson(res, 200, statusPayload())
      return
    }

    if (req.method === 'GET' && url.pathname === '/api/sessions') {
      sendJson(res, 200, sessionsPayload())
      return
    }

    if (req.method === 'POST' && url.pathname === '/api/chronicle') {
      const body = await readJsonBody(req)
      chronicleRequests.push({
        session_id: body.session_id,
        force_refresh: !!body.force_refresh,
        chapter_only: !!body.chapter_only,
        refresh_mode: body.refresh_mode || 'balanced',
      })
      sendJson(res, 200, chroniclePayload(body))
      return
    }

    if (req.method === 'POST' && url.pathname === '/api/chronicles') {
      const body = await readJsonBody(req)
      publicationRequests.push({ method: req.method, headers: req.headers, body })
      publication = {
        ...body,
        revision: 1,
        publishedAt: '2026-07-21T00:00:00.000Z',
        updatedAt: '2026-07-21T00:00:00.000Z',
      }
      sendJson(res, 201, publicationPayload())
      return
    }

    if (url.pathname === `/api/chronicles/${publishedStoryId}`) {
      if (!publication) {
        sendJson(res, 404, { error: { code: 'not_found', message: 'Story not found.' } })
        return
      }

      if (req.method === 'GET') {
        publicationRequests.push({ method: req.method, headers: req.headers, body: null })
        sendJson(res, 200, publicationPayload())
        return
      }

      if (req.method === 'PUT') {
        const body = await readJsonBody(req)
        publicationRequests.push({ method: req.method, headers: req.headers, body })
        publication = {
          ...publication,
          ...body,
          revision: publication.revision + 1,
          updatedAt: '2026-07-21T00:01:00.000Z',
        }
        sendJson(res, 200, publicationPayload())
        return
      }

      if (req.method === 'DELETE') {
        const body = await readJsonBody(req)
        publicationRequests.push({ method: req.method, headers: req.headers, body })
        publication = null
        res.writeHead(204)
        res.end()
        return
      }
    }

    sendJson(res, 404, { error: `Unhandled ${req.method} ${url.pathname}` })
  }

  function start(port = 0) {
    return new Promise((resolve, reject) => {
      server = http.createServer((req, res) => {
        Promise.resolve(handler(req, res)).catch((error) => {
          sendJson(res, 500, { error: error instanceof Error ? error.message : 'Mock backend failed' })
        })
      })
      server.once('error', reject)
      server.listen(port, '127.0.0.1', () => {
        const address = server.address()
        resolve(typeof address === 'object' && address ? address.port : port)
      })
    })
  }

  function stop() {
    return new Promise((resolve) => {
      if (!server) {
        resolve()
        return
      }
      server.close(() => {
        server = null
        resolve()
      })
    })
  }

  function advanceCampaign() {
    phase = 'advanced'
    healthUpdatedAt += 1_000
  }

  async function waitForChronicleRequest(predicate, timeoutMs = 10_000) {
    const start = Date.now()
    while (Date.now() - start < timeoutMs) {
      for (const request of chronicleRequests) {
        if (predicate(request, chronicleRequests)) {
          return request
        }
      }
      await new Promise((resolve) => setTimeout(resolve, 50))
    }
    throw new Error('Timed out waiting for chronicle request')
  }

  async function waitForPublicationRequest(predicate, timeoutMs = 10_000) {
    const start = Date.now()
    while (Date.now() - start < timeoutMs) {
      for (const request of publicationRequests) {
        if (predicate(request, publicationRequests)) {
          return request
        }
      }
      await new Promise((resolve) => setTimeout(resolve, 50))
    }
    throw new Error('Timed out waiting for publication request')
  }

  return {
    start,
    stop,
    advanceCampaign,
    waitForChronicleRequest,
    waitForPublicationRequest,
    getChronicleRequests: () => [...chronicleRequests],
    getPublicationRequests: () => [...publicationRequests],
  }
}

module.exports = {
  createMockChronicleBackend,
}
