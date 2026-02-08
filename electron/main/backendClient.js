class BackendApiError extends Error {
  constructor(message, { httpStatus, code, retryAfterMs, details } = {}) {
    super(message)
    this.name = 'BackendApiError'
    this.httpStatus = httpStatus
    this.code = code
    this.retryAfterMs = retryAfterMs
    this.details = details
  }
}

function extractBackendErrorFields(parsedBody, rawBody) {
  const detail = parsedBody?.detail
  const error =
    detail?.error ||
    (typeof detail === 'string' ? detail : null) ||
    parsedBody?.error ||
    (typeof parsedBody === 'string' ? parsedBody : null)

  const retryAfterMs = detail?.retry_after_ms ?? parsedBody?.retry_after_ms
  const code = detail?.code ?? parsedBody?.code

  const fallback = rawBody ? rawBody.slice(0, 500) : null
  const message = error || fallback || 'Request failed'

  return {
    message,
    code: typeof code === 'string' ? code : undefined,
    retryAfterMs: typeof retryAfterMs === 'number' ? retryAfterMs : undefined,
    details: detail ?? parsedBody ?? (fallback ? { raw: fallback } : undefined),
  }
}

/**
 * Creates a backend client bound to the current backend port/token.
 *
 * This keeps the "IPC envelope" logic centralized as the single source of truth.
 */
function createBackendClient({ host, getPort, getAuthToken }) {
  if (!host) throw new Error('createBackendClient: host is required')
  if (typeof getPort !== 'function') throw new Error('createBackendClient: getPort() is required')
  if (typeof getAuthToken !== 'function') throw new Error('createBackendClient: getAuthToken() is required')

  /**
   * Call the Python backend API and throw on failure.
   *
   * Prefer `callBackendApiEnvelope` for renderer IPC handlers so structured
   * errors (retry_after_ms, code, status) propagate to the UI.
   */
  async function callBackendApiOrThrow(endpoint, options = {}) {
    const url = `http://${host}:${getPort()}${endpoint}`

    const { timeoutMs, ...restOptions } = options
    const controller = timeoutMs ? new AbortController() : null
    const timer = timeoutMs
      ? setTimeout(() => {
        try {
          controller.abort()
        } catch {
          // ignore
        }
      }, timeoutMs)
      : null

    const fetchOptions = {
      ...restOptions,
      signal: controller ? controller.signal : undefined,
      headers: {
        ...restOptions.headers,
        Authorization: `Bearer ${getAuthToken()}`,
        'Content-Type': 'application/json',
      },
    }

    let response
    try {
      response = await fetch(url, fetchOptions)
    } finally {
      if (timer) clearTimeout(timer)
    }

    const rawBody = await response.text().catch(() => '')
    let parsedBody = null
    if (rawBody) {
      try {
        parsedBody = JSON.parse(rawBody)
      } catch {
        parsedBody = null
      }
    }

    if (!response.ok) {
      const { message, code, retryAfterMs, details } = extractBackendErrorFields(parsedBody, rawBody)
      throw new BackendApiError(message, {
        httpStatus: response.status,
        code,
        retryAfterMs,
        details,
      })
    }

    if (parsedBody === null) {
      throw new BackendApiError('Invalid JSON response from backend', {
        httpStatus: response.status,
      })
    }

    return parsedBody
  }

  /**
   * Call the Python backend API and return a structured envelope.
   *
   * This is the preferred API for renderer IPC handlers.
   */
  async function callBackendApiEnvelope(endpoint, options = {}) {
    try {
      const data = await callBackendApiOrThrow(endpoint, options)
      return { ok: true, data }
    } catch (e) {
      if (e instanceof BackendApiError) {
        return {
          ok: false,
          error: e.message,
          code: e.code,
          retry_after_ms: e.retryAfterMs,
          http_status: e.httpStatus,
          details: e.details,
        }
      }

      return {
        ok: false,
        error: e instanceof Error ? e.message : 'Request failed',
      }
    }
  }

  return {
    callBackendApiOrThrow,
    callBackendApiEnvelope,
  }
}

module.exports = {
  BackendApiError,
  extractBackendErrorFields,
  createBackendClient,
}

