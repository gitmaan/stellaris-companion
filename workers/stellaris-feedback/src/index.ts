/**
 * Stellaris Companion Feedback Worker
 *
 * Handles user feedback submissions:
 * - Rate limits by IP (10/day)
 * - Deduplicates similar reports
 * - Creates or updates GitHub issues
 */

interface Env {
  RATE_LIMITS: KVNamespace
  DB: D1Database
  GITHUB_TOKEN: string
  GITHUB_OWNER: string
  GITHUB_REPO: string
}

interface ReportPayload {
  schema_version?: number
  submitted_at_ms?: number
  install_id?: string
  category: string
  description: string
  context: {
    appVersion: string
    platform: string
    electronVersion?: string
    diagnostics?: {
      stellarisVersion?: string
      dlcs?: string[]
      empireName?: string
      empireType?: string
      empireOrigin?: string
      empireEthics?: string[]
      empireCivics?: string[]
      gameYear?: string
      saveFileSizeMb?: number
      galaxySize?: string
      ingestionStage?: string
      ingestionStageDetail?: string
      ingestionLastError?: string
      precomputeReady?: boolean
      t2Ready?: boolean
    }
    error?: {
      message: string
      stack?: string
      source: string
    }
    llm?: {
      lastPrompt?: string
      lastResponse?: string
      recentTurns?: Array<{ role: 'user' | 'assistant'; content: string }>
      responseTimeMs?: number
      model?: string
    }
    backend_log_tail?: string
    screenshot?: string
  }
}

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url)

    if (request.method === 'GET' && url.pathname.startsWith('/screenshot/')) {
      return serveScreenshot(env, url.pathname)
    }

    // Handle CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: CORS_HEADERS })
    }

    // Only accept POST
    if (request.method !== 'POST') {
      return new Response('Method not allowed', { status: 405, headers: CORS_HEADERS })
    }

    try {
      const data = (await request.json()) as ReportPayload

      // Validate required fields
      if (!data.category || !data.description?.trim()) {
        return Response.json(
          { error: 'Missing required fields: category and description' },
          { status: 400, headers: CORS_HEADERS }
        )
      }

      // 1. Rate limit (10/day/IP)
      const ip = request.headers.get('cf-connecting-ip') || 'unknown'
      const today = new Date().toISOString().split('T')[0]
      const rateKey = `${ip}:${today}`
      const count = parseInt((await env.RATE_LIMITS.get(rateKey)) || '0')

      if (count >= 10) {
        return Response.json(
          { error: 'Rate limited. Maximum 10 reports per day.' },
          { status: 429, headers: CORS_HEADERS }
        )
      }
      await env.RATE_LIMITS.put(rateKey, String(count + 1), { expirationTtl: 86400 })

      // 2. Fingerprint for dedup
      const fingerprint = await hash(buildFingerprintInput(data))

      let screenshotUrl: string | undefined
      if (data.context.screenshot) {
        try {
          screenshotUrl = await persistScreenshot(env, data.context.screenshot, url)
        } catch (err) {
          console.warn('Failed to persist screenshot:', err)
        }
      }

      // 3. Check for duplicate (within 7 days)
      const existing = await env.DB.prepare(
        `
        SELECT github_issue_number, report_count FROM reports
        WHERE fingerprint = ? AND created_at > datetime('now', '-7 days')
      `
      )
        .bind(fingerprint)
        .first<{ github_issue_number: number; report_count: number }>()

      if (existing) {
        // Add comment to existing issue
        await addGitHubComment(env, existing.github_issue_number, data, screenshotUrl)
        await env.DB.prepare(
          `
          UPDATE reports SET report_count = report_count + 1, updated_at = CURRENT_TIMESTAMP
          WHERE fingerprint = ?
        `
        )
          .bind(fingerprint)
          .run()

        return Response.json(
          {
            issueUrl: `https://github.com/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/issues/${existing.github_issue_number}`,
            deduplicated: true,
            totalReports: existing.report_count + 1,
          },
          { headers: CORS_HEADERS }
        )
      }

      // 4. Create new issue
      const issue = await createGitHubIssue(env, data, screenshotUrl)
      await env.DB.prepare(
        `
        INSERT INTO reports (fingerprint, github_issue_number) VALUES (?, ?)
      `
      )
        .bind(fingerprint, issue.number)
        .run()

      return Response.json(
        {
          issueUrl: issue.html_url,
          deduplicated: false,
        },
        { headers: CORS_HEADERS }
      )
    } catch (e) {
      console.error('Worker error:', e)
      return Response.json({ error: 'Internal server error' }, { status: 500, headers: CORS_HEADERS })
    }
  },
}

// Helper: SHA-256 hash
async function hash(str: string): Promise<string> {
  const buffer = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(str))
  return Array.from(new Uint8Array(buffer))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('')
}

function normalizeFingerprintPart(value: unknown, max = 220): string {
  const raw = typeof value === 'string' ? value : String(value || '')
  const collapsed = raw.replace(/\s+/g, ' ').trim().toLowerCase()
  if (!collapsed) return ''
  return collapsed.length > max ? collapsed.slice(0, max) : collapsed
}

function buildFingerprintInput(data: ReportPayload): string {
  const llmPrompt = normalizeFingerprintPart(data.context.llm?.lastPrompt, 140)
  const llmResponse = normalizeFingerprintPart(data.context.llm?.lastResponse, 140)
  const errMessage = normalizeFingerprintPart(data.context.error?.message, 140)
  const errSource = normalizeFingerprintPart(data.context.error?.source, 40)
  const desc = normalizeFingerprintPart(data.description, 180)
  const platform = normalizeFingerprintPart(data.context.platform, 60)
  const appVersion = normalizeFingerprintPart(data.context.appVersion, 40)
  const stage = normalizeFingerprintPart(data.context.diagnostics?.ingestionStage, 60)

  return [
    `category:${normalizeFingerprintPart(data.category, 80)}`,
    `version:${appVersion}`,
    `platform:${platform}`,
    `description:${desc}`,
    `error:${errSource}:${errMessage}`,
    `llm:${llmPrompt}:${llmResponse}`,
    `stage:${stage}`,
  ].join('|')
}

function slugLabel(value: string, max = 48): string {
  const normalized = value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
  if (!normalized) return 'unknown'
  return normalized.length > max ? normalized.slice(0, max) : normalized
}

function truncate(value: string, max: number): string {
  if (value.length <= max) return value
  return value.slice(0, max).trimEnd() + '...'
}

function inferContentType(ext: string): string {
  if (ext === 'jpg' || ext === 'jpeg') return 'image/jpeg'
  if (ext === 'webp') return 'image/webp'
  return 'image/png'
}

async function persistScreenshot(env: Env, dataUrl: string, requestUrl: URL): Promise<string | undefined> {
  const match = dataUrl.match(/^data:(image\/(?:png|jpeg|jpg|webp));base64,([A-Za-z0-9+/=]+)$/)
  if (!match) return undefined

  const mimeType = match[1] === 'image/jpg' ? 'image/jpeg' : match[1]
  const ext = mimeType === 'image/jpeg' ? 'jpg' : mimeType === 'image/webp' ? 'webp' : 'png'
  const base64 = match[2]

  const decoded = atob(base64)
  const bytes = new Uint8Array(decoded.length)
  for (let i = 0; i < decoded.length; i++) {
    bytes[i] = decoded.charCodeAt(i)
  }

  const id = crypto.randomUUID().replace(/-/g, '')
  const filename = `${id}.${ext}`
  const key = `screenshot:${filename}`

  await env.RATE_LIMITS.put(key, bytes.buffer, {
    expirationTtl: 60 * 60 * 24 * 30, // 30 days
  })

  return `${requestUrl.origin}/screenshot/${filename}`
}

async function serveScreenshot(env: Env, pathname: string): Promise<Response> {
  const name = pathname.slice('/screenshot/'.length)
  if (!/^[a-f0-9]{32}\.(png|jpg|webp)$/.test(name)) {
    return new Response('Not found', { status: 404 })
  }

  const ext = name.split('.').pop() || 'png'
  const stored = await env.RATE_LIMITS.get(`screenshot:${name}`, 'arrayBuffer')
  if (!stored) {
    return new Response('Not found', { status: 404 })
  }

  return new Response(stored, {
    headers: {
      'Content-Type': inferContentType(ext),
      'Cache-Control': 'public, max-age=86400, immutable',
    },
  })
}

// Helper: Create GitHub issue
async function createGitHubIssue(
  env: Env,
  data: ReportPayload,
  screenshotUrl?: string
): Promise<{ number: number; html_url: string }> {
  const { category, description, context } = data
  const diag = context.diagnostics

  // Build issue body
  const bodyParts = [
    `## ${category}`,
    '',
    `**App Version:** ${context.appVersion}`,
    `**Platform:** ${context.platform}`,
  ]

  if (context.electronVersion) {
    bodyParts.push(`**Electron:** ${context.electronVersion}`)
  }

  bodyParts.push('', '### Description', description)

  // Diagnostics (opt-in game context)
  if (diag) {
    bodyParts.push('', '### Game Context')
    if (diag.empireName) bodyParts.push(`**Empire:** ${diag.empireName}`)
    if (diag.empireType) bodyParts.push(`**Type:** ${diag.empireType}`)
    if (diag.empireOrigin) bodyParts.push(`**Origin:** ${diag.empireOrigin}`)
    if (diag.empireEthics?.length) bodyParts.push(`**Ethics:** ${diag.empireEthics.join(', ')}`)
    if (diag.empireCivics?.length) bodyParts.push(`**Civics:** ${diag.empireCivics.join(', ')}`)
    if (diag.gameYear) bodyParts.push(`**Game Year:** ${diag.gameYear}`)
    if (diag.stellarisVersion) bodyParts.push(`**Stellaris:** ${diag.stellarisVersion}`)
    if (diag.galaxySize) bodyParts.push(`**Galaxy:** ${diag.galaxySize}`)
    if (typeof diag.saveFileSizeMb === 'number') bodyParts.push(`**Save Size:** ${diag.saveFileSizeMb} MB`)
    if (diag.dlcs?.length) bodyParts.push(`**DLCs:** ${diag.dlcs.length} enabled`)
    if (diag.ingestionStage) bodyParts.push(`**Ingestion Stage:** ${diag.ingestionStage}`)
    if (diag.ingestionStageDetail) bodyParts.push(`**Ingestion Detail:** ${diag.ingestionStageDetail}`)
    if (typeof diag.precomputeReady === 'boolean') bodyParts.push(`**Precompute Ready:** ${diag.precomputeReady}`)
    if (typeof diag.t2Ready === 'boolean') bodyParts.push(`**Tier 2 Ready:** ${diag.t2Ready}`)
    if (diag.ingestionLastError) bodyParts.push(`**Ingestion Last Error:** ${diag.ingestionLastError}`)
  }

  if (context.error) {
    bodyParts.push(
      '',
      '### Error',
      '```',
      context.error.message,
      '```',
      `**Source:** ${context.error.source}`
    )
    if (context.error.stack) {
      bodyParts.push(
        '<details><summary>Stack trace</summary>',
        '',
        '```',
        context.error.stack,
        '```',
        '</details>'
      )
    }
  }

  if (context.llm && (context.llm.lastPrompt || context.llm.lastResponse || context.llm.recentTurns?.length)) {
    bodyParts.push('', '### LLM Context')
    if (context.llm.model) bodyParts.push(`**Model:** ${context.llm.model}`)
    if (typeof context.llm.responseTimeMs === 'number') {
      bodyParts.push(`**Response Time:** ${context.llm.responseTimeMs}ms`)
    }
    if (context.llm.lastPrompt) {
      bodyParts.push('', '<details><summary>Prompt (truncated)</summary>', '', '```')
      bodyParts.push(truncate(context.llm.lastPrompt, 2000))
      bodyParts.push('```', '</details>')
    }
    if (context.llm.lastResponse) {
      bodyParts.push('', '<details><summary>Response (truncated)</summary>', '', '```')
      bodyParts.push(truncate(context.llm.lastResponse, 2000))
      bodyParts.push('```', '</details>')
    }
    if (context.llm.recentTurns?.length) {
      bodyParts.push('', '<details><summary>Recent turns</summary>', '', '```')
      for (const turn of context.llm.recentTurns.slice(-8)) {
        const who = turn.role === 'user' ? 'User' : 'Advisor'
        bodyParts.push(`${who}: ${truncate(turn.content || '', 600)}`)
      }
      bodyParts.push('```', '</details>')
    }
  }

  if (context.backend_log_tail) {
    bodyParts.push(
      '',
      '<details><summary>Backend logs</summary>',
      '',
      '```',
      context.backend_log_tail.slice(0, 8000),
      '```',
      '</details>'
    )
  }

  if (screenshotUrl) {
    bodyParts.push('', '### Screenshot', `![User screenshot](${screenshotUrl})`, '', `Screenshot URL: ${screenshotUrl}`)
  } else if (context.screenshot) {
    bodyParts.push('', '*Screenshot was provided but could not be processed.*')
  }

  bodyParts.push('', '---', '*Submitted via in-app feedback*')

  const body = bodyParts.join('\n')

  // Create issue title
  const titleDesc = description.slice(0, 50) + (description.length > 50 ? '...' : '')
  const title = `[${category}] ${titleDesc}`

  // Create label slug
  const categoryLabel = category.toLowerCase().replace(/ /g, '-')
  const platformLabel = `platform-${slugLabel(context.platform)}`
  const versionLabel = `version-${slugLabel(context.appVersion)}`
  const labels = ['user-report', categoryLabel, platformLabel, versionLabel]

  const response = await fetch(`https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/issues`, {
    method: 'POST',
    headers: {
      Authorization: `token ${env.GITHUB_TOKEN}`,
      'Content-Type': 'application/json',
      'User-Agent': 'stellaris-feedback-worker',
    },
    body: JSON.stringify({
      title,
      body,
      labels,
    }),
  })

  if (!response.ok) {
    const error = await response.text()
    throw new Error(`GitHub API error: ${response.status} - ${error}`)
  }

  return response.json()
}

// Helper: Add comment to existing issue
async function addGitHubComment(
  env: Env,
  issueNumber: number,
  data: ReportPayload,
  screenshotUrl?: string
): Promise<void> {
  const diag = data.context.diagnostics
  const bodyParts = [
    '### Additional report',
    '',
    `**Platform:** ${data.context.platform}`,
    `**Version:** ${data.context.appVersion}`,
  ]

  if (diag) {
    if (diag.empireName) bodyParts.push(`**Empire:** ${diag.empireName}`)
    if (diag.empireType) bodyParts.push(`**Type:** ${diag.empireType}`)
    if (diag.gameYear) bodyParts.push(`**Game Year:** ${diag.gameYear}`)
    if (diag.empireEthics?.length) bodyParts.push(`**Ethics:** ${diag.empireEthics.join(', ')}`)
    if (diag.empireCivics?.length) bodyParts.push(`**Civics:** ${diag.empireCivics.join(', ')}`)
    if (diag.stellarisVersion) bodyParts.push(`**Stellaris:** ${diag.stellarisVersion}`)
    if (diag.galaxySize) bodyParts.push(`**Galaxy:** ${diag.galaxySize}`)
    if (typeof diag.saveFileSizeMb === 'number') bodyParts.push(`**Save Size:** ${diag.saveFileSizeMb} MB`)
    if (diag.ingestionStage) bodyParts.push(`**Ingestion Stage:** ${diag.ingestionStage}`)
    if (diag.ingestionStageDetail) bodyParts.push(`**Ingestion Detail:** ${diag.ingestionStageDetail}`)
    if (typeof diag.precomputeReady === 'boolean') bodyParts.push(`**Precompute Ready:** ${diag.precomputeReady}`)
    if (typeof diag.t2Ready === 'boolean') bodyParts.push(`**Tier 2 Ready:** ${diag.t2Ready}`)
    if (diag.ingestionLastError) bodyParts.push(`**Ingestion Last Error:** ${diag.ingestionLastError}`)
  }

  bodyParts.push('', data.description)

  if (data.context.error) {
    bodyParts.push('', '```', data.context.error.message, '```')
    if (data.context.error.stack) {
      bodyParts.push('<details><summary>Stack trace</summary>', '', '```', data.context.error.stack, '```', '</details>')
    }
  }

  if (data.context.llm && (data.context.llm.lastPrompt || data.context.llm.lastResponse || data.context.llm.recentTurns?.length)) {
    bodyParts.push('', '#### LLM Context')
    if (data.context.llm.model) bodyParts.push(`**Model:** ${data.context.llm.model}`)
    if (typeof data.context.llm.responseTimeMs === 'number') {
      bodyParts.push(`**Response Time:** ${data.context.llm.responseTimeMs}ms`)
    }
    if (data.context.llm.lastPrompt) {
      bodyParts.push('', '<details><summary>Prompt (truncated)</summary>', '', '```')
      bodyParts.push(truncate(data.context.llm.lastPrompt, 2000))
      bodyParts.push('```', '</details>')
    }
    if (data.context.llm.lastResponse) {
      bodyParts.push('', '<details><summary>Response (truncated)</summary>', '', '```')
      bodyParts.push(truncate(data.context.llm.lastResponse, 2000))
      bodyParts.push('```', '</details>')
    }
    if (data.context.llm.recentTurns?.length) {
      bodyParts.push('', '<details><summary>Recent turns</summary>', '', '```')
      for (const turn of data.context.llm.recentTurns.slice(-8)) {
        const who = turn.role === 'user' ? 'User' : 'Advisor'
        bodyParts.push(`${who}: ${truncate(turn.content || '', 600)}`)
      }
      bodyParts.push('```', '</details>')
    }
  }

  if (data.context.backend_log_tail) {
    bodyParts.push(
      '',
      '<details><summary>Backend logs</summary>',
      '',
      '```',
      data.context.backend_log_tail.slice(0, 8000),
      '```',
      '</details>'
    )
  }

  if (screenshotUrl) {
    bodyParts.push('', `Screenshot: ${screenshotUrl}`)
  } else if (data.context.screenshot) {
    bodyParts.push('', 'Screenshot was provided but could not be processed.')
  }

  bodyParts.push('', '---', '*+1 report via in-app feedback*')

  const body = bodyParts.join('\n')

  await fetch(`https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/issues/${issueNumber}/comments`, {
    method: 'POST',
    headers: {
      Authorization: `token ${env.GITHUB_TOKEN}`,
      'Content-Type': 'application/json',
      'User-Agent': 'stellaris-feedback-worker',
    },
    body: JSON.stringify({ body }),
  })
}
