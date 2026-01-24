// IPC wrapper for API calls - uses window.electronAPI.backend.* internally
// Implements UI-006: useBackend hook with loading states and error handling

import { useState, useCallback, useMemo } from 'react'

// ============================================
// API Response Types (match backend/api/server.py)
// ============================================

export type EmpireType = 'machine' | 'hive_mind' | 'standard'

export interface HealthResponse {
  status: string
  save_loaded: boolean
  empire_name: string | null
  game_date: string | null
  precompute_ready: boolean
  empire_type?: EmpireType
  ingestion?: {
    stage?: string
    stage_detail?: string | null
    updated_at?: number
    last_error?: string | null
    current_save_path?: string | null
    pending_save_path?: string | null
    worker_pid?: number | null
    worker_tier?: string | null
    t2_game_date?: string | null
    t2_updated_at?: number | null
    t2_last_duration_ms?: number | null
    cancel_count?: number
  }
}

export type BackendStatusEvent = HealthResponse & {
  connected?: boolean
  backend_configured?: boolean
  error?: string
}

export interface ChatResponse {
  text: string
  game_date: string
  tools_used: string[]
  response_time_ms: number
}

export interface ChatRetryResponse {
  error: string
  retry_after_ms: number
}

export interface ResourceStats {
  income: number
  expense: number
  net: number
}

export interface StatusResponse {
  empire_name: string
  game_date: string
  military_power: number
  economy: {
    energy: ResourceStats
    minerals: ResourceStats
    alloys: ResourceStats
    [key: string]: ResourceStats  // Allow additional resources
  }
  colonies: number
  pops: number
  active_wars: number
}

export interface Session {
  id: string
  empire_name: string
  started_at: number
  ended_at: number | null
  first_game_date: string
  last_game_date: string
  snapshot_count: number
  is_active: boolean
}

export interface SessionsResponse {
  sessions: Session[]
}

export interface SessionEvent {
  id: number
  game_date: string
  event_type: string
  summary: string
  data: Record<string, unknown>
}

export interface SessionEventsResponse {
  events: SessionEvent[]
}

export interface RecapResponse {
  recap: string
  events_summarized: number
  date_range: string
  style?: string
}

export interface ChronicleChapter {
  number: number
  title: string
  start_date: string
  end_date: string
  narrative: string
  summary: string
  is_finalized: boolean
  context_stale: boolean
  can_regenerate: boolean
}

export interface CurrentEra {
  start_date: string
  narrative: string
  events_covered: number
}

export interface ChronicleResponse {
  // New structured format
  chapters: ChronicleChapter[]
  current_era: CurrentEra | null
  pending_chapters: number
  message: string | null
  // Backward compatible
  chronicle: string
  cached: boolean
  event_count: number
  generated_at: string
}

export interface RegenerateChapterResponse {
  chapter: ChronicleChapter
  regenerated: boolean
  stale_chapters: number[]
  error?: string
  confirm_required?: boolean
}

export interface EndSessionResponse {
  session_id: string
  ended_at: number
  snapshot_count: number
}

export interface ErrorResponse {
  error: string
  code?: string
  details?: Record<string, unknown>
}

// ============================================
// Global Window Type Declaration
// ============================================

declare global {
  interface Window {
    electronAPI?: {
      backend: {
        health: () => Promise<HealthResponse | ErrorResponse>
        chat: (message: string, sessionKey?: string) => Promise<ChatResponse | ChatRetryResponse | ErrorResponse>
        status: () => Promise<StatusResponse | ErrorResponse>
        sessions: () => Promise<SessionsResponse | ErrorResponse>
        sessionEvents: (sessionId: string, limit?: number) => Promise<SessionEventsResponse | ErrorResponse>
        recap: (sessionId: string, style?: string) => Promise<RecapResponse | ErrorResponse>
        chronicle: (sessionId: string, forceRefresh?: boolean) => Promise<ChronicleResponse | ErrorResponse>
        regenerateChapter: (sessionId: string, chapterNumber: number, confirm?: boolean) => Promise<RegenerateChapterResponse | ErrorResponse>
        endSession: () => Promise<EndSessionResponse | ErrorResponse>
      }
      getSettings: () => Promise<unknown>
      saveSettings: (settings: unknown) => Promise<unknown>
      showFolderDialog: () => Promise<string | null>
      onBackendStatus: (callback: (status: BackendStatusEvent) => void) => () => void
    }
  }
}

// ============================================
// Type Guards for Response Checking
// ============================================

export function isErrorResponse(response: unknown): response is ErrorResponse {
  return typeof response === 'object' && response !== null && 'error' in response
}

export function isChatRetryResponse(response: unknown): response is ChatRetryResponse {
  return isErrorResponse(response) && 'retry_after_ms' in response
}

// ============================================
// Hook Result Type
// ============================================

export interface UseBackendResult<T> {
  data: T | null
  loading: boolean
  error: string | null
}

// ============================================
// Main Hook
// ============================================

/**
 * useBackend - Hook for making backend API calls
 *
 * Returns methods for all backend API calls. Each method wraps the underlying
 * IPC call with consistent loading state and error handling.
 *
 * Usage:
 *   const backend = useBackend()
 *   const result = await backend.health()
 *   if (result.error) { handle error }
 *   else { use result.data }
 */
export function useBackend() {
  // Track loading states per-method
  const [loadingStates, setLoadingStates] = useState<Record<string, boolean>>({})

  // Set loading state, removing key when done to prevent object growth
  const setLoading = useCallback((key: string, loading: boolean) => {
    setLoadingStates(prev => {
      if (loading) {
        return { ...prev, [key]: true }
      } else {
        // Remove key when not loading to prevent unbounded object growth
        const next = { ...prev }
        delete next[key]
        return next
      }
    })
  }, [])

  /**
   * Generic wrapper for API calls with loading/error handling
   */
  const callApi = useCallback(async <T>(
    key: string,
    apiCall: () => Promise<T | ErrorResponse>
  ): Promise<UseBackendResult<T>> => {
    // Check if electronAPI is available
    if (!window.electronAPI?.backend) {
      return {
        data: null,
        loading: false,
        error: 'Backend API not available (not running in Electron)',
      }
    }

    setLoading(key, true)

    try {
      const response = await apiCall()

      if (isErrorResponse(response)) {
        return {
          data: null,
          loading: false,
          error: response.error,
        }
      }

      return {
        data: response as T,
        loading: false,
        error: null,
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error occurred'
      return {
        data: null,
        loading: false,
        error: errorMessage,
      }
    } finally {
      setLoading(key, false)
    }
  }, [setLoading])

  // ============================================
  // API Methods
  // ============================================

  /**
   * Check backend health status
   */
  const health = useCallback(async (): Promise<UseBackendResult<HealthResponse>> => {
    return callApi<HealthResponse>('health', () =>
      window.electronAPI!.backend.health()
    )
  }, [callApi])

  /**
   * Send a chat message and get a response
   * Returns ChatRetryResponse if precompute not ready
   */
  const chat = useCallback(async (
    message: string,
    sessionKey?: string
  ): Promise<UseBackendResult<ChatResponse | ChatRetryResponse>> => {
    return callApi<ChatResponse | ChatRetryResponse>('chat', () =>
      window.electronAPI!.backend.chat(message, sessionKey)
    )
  }, [callApi])

  /**
   * Get current empire status
   */
  const status = useCallback(async (): Promise<UseBackendResult<StatusResponse>> => {
    return callApi<StatusResponse>('status', () =>
      window.electronAPI!.backend.status()
    )
  }, [callApi])

  /**
   * Get all sessions
   */
  const sessions = useCallback(async (): Promise<UseBackendResult<SessionsResponse>> => {
    return callApi<SessionsResponse>('sessions', () =>
      window.electronAPI!.backend.sessions()
    )
  }, [callApi])

  /**
   * Get events for a specific session
   */
  const sessionEvents = useCallback(async (
    sessionId: string,
    limit?: number
  ): Promise<UseBackendResult<SessionEventsResponse>> => {
    return callApi<SessionEventsResponse>('sessionEvents', () =>
      window.electronAPI!.backend.sessionEvents(sessionId, limit)
    )
  }, [callApi])

  /**
   * Generate a recap for a session
   * @param style - "summary" (deterministic) or "dramatic" (LLM-powered)
   */
  const recap = useCallback(async (
    sessionId: string,
    style?: string
  ): Promise<UseBackendResult<RecapResponse>> => {
    return callApi<RecapResponse>('recap', () =>
      window.electronAPI!.backend.recap(sessionId, style)
    )
  }, [callApi])

  /**
   * Generate a full chronicle for a session
   * @param forceRefresh - If true, regenerate even if cached
   */
  const chronicle = useCallback(async (
    sessionId: string,
    forceRefresh?: boolean
  ): Promise<UseBackendResult<ChronicleResponse>> => {
    return callApi<ChronicleResponse>('chronicle', () =>
      window.electronAPI!.backend.chronicle(sessionId, forceRefresh)
    )
  }, [callApi])

  /**
   * Regenerate a specific chapter of the chronicle
   * @param chapterNumber - The chapter number to regenerate
   * @param confirm - Must be true to proceed (safety check)
   */
  const regenerateChapter = useCallback(async (
    sessionId: string,
    chapterNumber: number,
    confirm?: boolean
  ): Promise<UseBackendResult<RegenerateChapterResponse>> => {
    return callApi<RegenerateChapterResponse>('regenerateChapter', () =>
      window.electronAPI!.backend.regenerateChapter(sessionId, chapterNumber, confirm)
    )
  }, [callApi])

  /**
   * End the current active session
   */
  const endSession = useCallback(async (): Promise<UseBackendResult<EndSessionResponse>> => {
    return callApi<EndSessionResponse>('endSession', () =>
      window.electronAPI!.backend.endSession()
    )
  }, [callApi])

  // ============================================
  // Return API (memoized to prevent infinite re-renders)
  // ============================================

  return useMemo(() => ({
    // Methods
    health,
    chat,
    status,
    sessions,
    sessionEvents,
    recap,
    chronicle,
    regenerateChapter,
    endSession,

    // Loading states (for UI components that need to track multiple calls)
    isLoading: (key: string) => loadingStates[key] ?? false,
    loadingStates,

    // Type guards for consumers
    isErrorResponse,
    isChatRetryResponse,
  }), [health, chat, status, sessions, sessionEvents, recap, chronicle, regenerateChapter, endSession, loadingStates])
}

export default useBackend
