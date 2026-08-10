// IPC wrapper for API calls - uses window.electronAPI.backend.* internally
// Implements UI-006: useBackend hook with loading states and error handling

import { useState, useCallback, useMemo, useRef } from 'react'
import type { ChronicleRefreshMode, ModelRoutingMode } from './useSettings'

// ============================================
// API Response Types (match backend/api/server.py)
// ============================================

export type BackendIpcResponse<T> =
  | { ok: true; data: T }
  | {
      ok: false
      error: string
      code?: string
      retry_after_ms?: number
      http_status?: number
      details?: unknown
    }

export type EmpireType = 'machine' | 'hive_mind' | 'standard'

export interface HealthResponse {
  status: string
  save_loaded: boolean
  empire_name: string | null
  game_date: string | null
  precompute_ready: boolean
  advisor_provider?: string | null
  advisor_configured?: boolean
  chronicle_provider?: string | null
  chronicle_configured?: boolean
  empire_type?: EmpireType
  empire_ethics?: string[]
  empire_civics?: string[]
  empire_authority?: string
  empire_origin?: string
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
  response_time_ms: number
  model?: string
  model_display?: string
  requested_model?: string
  requested_model_display?: string
  model_routing?: ModelRoutingEvent | null
  provider?: string
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
  save_id: string
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

export interface Playthrough {
  save_id: string
  empire_name: string | null
  display_name: string
  display_label: string | null
  latest_session_id: string
  first_game_date: string | null
  last_game_date: string | null
  first_seen_at: number
  last_played_at: number
  session_count: number
  snapshot_count: number
  event_count: number
  has_chronicle: boolean
  cached_languages: string[]
  chapter_count: number
  total_chapter_count: number
  has_current_era: boolean
  can_undo_reset: boolean
  is_current: boolean
  is_trashed: boolean
  trashed_at: number | null
}

export interface PlaythroughsResponse {
  playthroughs: Playthrough[]
  current_save_id: string | null
  language: string
}

export interface PlaythroughMutationResponse {
  save_id: string
  display_label?: string | null
  trashed?: boolean
  reset?: boolean
  restored?: boolean
  can_undo?: boolean
  rows_reset?: number
  counts?: Record<string, number>
}

export interface HistoryStorageResponse {
  path: string
  bytes: number | null
  files?: Record<string, number>
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
  provider?: string
  model?: string
  model_routing?: ModelRoutingSummary | null
}

export interface NarrativeSection {
  type: 'prose' | 'quote' | 'declaration'
  text: string
  attribution?: string
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
  epigraph?: string
  sections?: NarrativeSection[] | null
  provider?: string | null
  model?: string | null
}

export interface CurrentEra {
  start_date: string
  narrative: string
  events_covered: number
  sections?: NarrativeSection[] | null
  provider?: string | null
  model?: string | null
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
  model_routing?: ModelRoutingSummary | null
  cache_warning?: string
  language?: string
}

export interface ModelRoutingEvent {
  requested_model?: string
  requested_model_display?: string
  attempted_model?: string
  attempted_model_display?: string
  final_model?: string
  final_model_display?: string
  fallback?: boolean
  reason?: string | null
  notice?: string | null
  error?: string | null
}

export interface ModelRoutingSummary {
  mode?: string
  provider?: string
  provider_display?: string
  model?: string | null
  model_display?: string | null
  fallback?: boolean
  notice?: string | null
  events?: ModelRoutingEvent[]
}

export interface RegenerateChapterResponse {
  chapter: ChronicleChapter
  regenerated: boolean
  stale_chapters: number[]
  model_routing?: ModelRoutingSummary | null
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

export interface DiagnosticsResponse {
  stellarisVersion: string | null
  dlcs: string[]
  empireType: string | null
  empireName: string | null
  empireEthics: string[]
  empireCivics: string[]
  empireOrigin: string | null
  gameYear: string | null
  saveFileSizeMb: number | null
  galaxySize: string | null
  ingestionStage: string | null
  ingestionStageDetail: string | null
  ingestionLastError: string | null
  precomputeReady: boolean | null
  t2Ready: boolean | null
  warDiagnostics: WarDiagnostics | null
}

export interface WarBattleDiagnosticRecord {
  local_attacker_country_ids: string[]
  local_defender_country_ids: string[]
  raw_attacker_victory: unknown
  raw_attacker_losses: number
  raw_defender_losses: number
  battle_type: string
  system_id: string | null
  computed_result: 'our_side_victory' | 'opposing_side_victory' | 'unknown'
  computed_our_side_losses: number
  computed_opposing_side_losses: number
}

export interface WarDiagnostic {
  war_id: string
  our_side: 'attacker' | 'defender'
  attacker_country_ids: string[]
  defender_country_ids: string[]
  direct_battle_count: number
  battle_records: WarBattleDiagnosticRecord[]
  truncated: boolean
}

export interface WarDiagnostics {
  schema_version: number
  player_id: string
  result_orientation: 'parent_war_side'
  loss_orientation: 'parent_war_side'
  wars: WarDiagnostic[]
  included_battles: number
  truncated: boolean
}

// ============================================
// Global Window Type Declaration
// ============================================

// Discord connection types (DISC-015)
export interface DiscordStatus {
  connected: boolean
  needsRefresh?: boolean
  userId?: string
  username?: string
}

export interface DiscordRelayStatus {
  state: 'disconnected' | 'connecting' | 'connected' | 'reconnecting' | 'error' // DISC-016: Added 'error' state
  userId?: string
  retryCount?: number
  lastConnectedAt?: number // DISC-016: Timestamp for 'Last connected: X ago' display
  error?: string // DISC-016: Error message for error state
}

export interface DiscordConnectResult {
  success: boolean
  error?: string
  userId?: string
  username?: string
}

export interface AdvisorCustomResponse {
  custom_instructions: string | null
  persisted: boolean
  error?: string
}

export interface ChronicleCustomResponse {
  custom_instructions: string | null
  persisted: boolean
  error?: string
}

// Announcement types
export interface Announcement {
  id: string
  severity: 'info' | 'warning' | 'known_issue' | 'update' | 'tip'
  title: string
  body: string
  publishedAt: string
  expiresAt?: string | null
  minVersion?: string | null
  maxVersion?: string | null
  link?: { label: string; url: string } | null
}

// ============================================
// Hook Result Type
// ============================================

export interface UseBackendResult<T> {
  data: T | null
  loading: boolean
  error: string | null
  errorCode?: string | null
  retryAfterMs?: number | null
  httpStatus?: number | null
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
  const loadingStatesRef = useRef<Record<string, boolean>>({})
  loadingStatesRef.current = loadingStates

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
    apiCall: () => Promise<BackendIpcResponse<T>>
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

      if (!response.ok) {
        return {
          data: null,
          loading: false,
          error: response.error,
          errorCode: response.code ?? null,
          retryAfterMs: response.retry_after_ms ?? null,
          httpStatus: response.http_status ?? null,
        }
      }

      return {
        data: response.data as T,
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

  const isLoading = useCallback((key: string) => {
    return loadingStatesRef.current[key] ?? false
  }, [])

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
   *
   * Retry/backoff details are returned via UseBackendResult fields
   * (retryAfterMs/errorCode/httpStatus).
   */
  const chat = useCallback(async (
    message: string,
    sessionKey?: string,
    model?: string,
    modelRoutingMode?: ModelRoutingMode,
  ): Promise<UseBackendResult<ChatResponse>> => {
    return callApi<ChatResponse>('chat', () =>
      window.electronAPI!.backend.chat(message, sessionKey, model, modelRoutingMode)
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

  const playthroughs = useCallback(async (
    includeTrashed = true,
  ): Promise<UseBackendResult<PlaythroughsResponse>> => {
    return callApi<PlaythroughsResponse>('playthroughs', () =>
      window.electronAPI!.backend.playthroughs(includeTrashed)
    )
  }, [callApi])

  const cachedChronicle = useCallback(async (
    saveId: string,
  ): Promise<UseBackendResult<ChronicleResponse>> => {
    return callApi<ChronicleResponse>('cachedChronicle', () =>
      window.electronAPI!.backend.cachedChronicle(saveId)
    )
  }, [callApi])

  const setPlaythroughLabel = useCallback(async (
    saveId: string,
    displayLabel: string | null,
  ): Promise<UseBackendResult<PlaythroughMutationResponse>> => {
    return callApi<PlaythroughMutationResponse>('setPlaythroughLabel', () =>
      window.electronAPI!.backend.setPlaythroughLabel(saveId, displayLabel)
    )
  }, [callApi])

  const trashPlaythrough = useCallback(async (
    saveId: string,
  ): Promise<UseBackendResult<PlaythroughMutationResponse>> => {
    return callApi<PlaythroughMutationResponse>('trashPlaythrough', () =>
      window.electronAPI!.backend.trashPlaythrough(saveId)
    )
  }, [callApi])

  const restorePlaythrough = useCallback(async (
    saveId: string,
  ): Promise<UseBackendResult<PlaythroughMutationResponse>> => {
    return callApi<PlaythroughMutationResponse>('restorePlaythrough', () =>
      window.electronAPI!.backend.restorePlaythrough(saveId)
    )
  }, [callApi])

  const resetChronicle = useCallback(async (
    saveId: string,
  ): Promise<UseBackendResult<PlaythroughMutationResponse>> => {
    return callApi<PlaythroughMutationResponse>('resetChronicle', () =>
      window.electronAPI!.backend.resetChronicle(saveId)
    )
  }, [callApi])

  const undoChronicleReset = useCallback(async (
    saveId: string,
  ): Promise<UseBackendResult<PlaythroughMutationResponse>> => {
    return callApi<PlaythroughMutationResponse>('undoChronicleReset', () =>
      window.electronAPI!.backend.undoChronicleReset(saveId)
    )
  }, [callApi])

  const deletePlaythrough = useCallback(async (
    saveId: string,
  ): Promise<UseBackendResult<PlaythroughMutationResponse>> => {
    return callApi<PlaythroughMutationResponse>('deletePlaythrough', () =>
      window.electronAPI!.backend.deletePlaythrough(saveId)
    )
  }, [callApi])

  const historyStorage = useCallback(async (): Promise<UseBackendResult<HistoryStorageResponse>> => {
    return callApi<HistoryStorageResponse>('historyStorage', () =>
      window.electronAPI!.backend.historyStorage()
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
    style?: string,
    modelRoutingMode?: ModelRoutingMode,
  ): Promise<UseBackendResult<RecapResponse>> => {
    return callApi<RecapResponse>('recap', () =>
      window.electronAPI!.backend.recap(sessionId, style, modelRoutingMode)
    )
  }, [callApi])

  /**
   * Generate a full chronicle for a session
   * @param forceRefresh - If true, regenerate even if cached
   * @param chapterOnly - If true, finalize pending chapters without regenerating current era
   */
  const chronicle = useCallback(async (
    sessionId: string,
    forceRefresh?: boolean,
    chapterOnly?: boolean,
    refreshMode?: ChronicleRefreshMode,
    modelRoutingMode?: ModelRoutingMode,
  ): Promise<UseBackendResult<ChronicleResponse>> => {
    return callApi<ChronicleResponse>('chronicle', () =>
      window.electronAPI!.backend.chronicle(
        sessionId,
        forceRefresh,
        chapterOnly,
        refreshMode,
        modelRoutingMode,
      )
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
    confirm?: boolean,
    regenerationInstructions?: string,
    modelRoutingMode?: ModelRoutingMode,
  ): Promise<UseBackendResult<RegenerateChapterResponse>> => {
    return callApi<RegenerateChapterResponse>('regenerateChapter', () =>
      window.electronAPI!.backend.regenerateChapter(
        sessionId,
        chapterNumber,
        confirm,
        regenerationInstructions,
        modelRoutingMode,
      )
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

  /**
   * Get chronicle custom instructions for the current playthrough
   */
  const getChronicleCustom = useCallback(async (): Promise<UseBackendResult<ChronicleCustomResponse>> => {
    return callApi<ChronicleCustomResponse>('getChronicleCustom', () =>
      window.electronAPI!.backend.getChronicleCustom()
    )
  }, [callApi])

  /**
   * Set chronicle custom instructions for the current playthrough
   */
  const setChronicleCustom = useCallback(async (
    customInstructions: string
  ): Promise<UseBackendResult<ChronicleCustomResponse>> => {
    return callApi<ChronicleCustomResponse>('setChronicleCustom', () =>
      window.electronAPI!.backend.setChronicleCustom(customInstructions)
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
    playthroughs,
    cachedChronicle,
    setPlaythroughLabel,
    trashPlaythrough,
    restorePlaythrough,
    resetChronicle,
    undoChronicleReset,
    deletePlaythrough,
    historyStorage,
    sessionEvents,
    recap,
    chronicle,
    regenerateChapter,
    endSession,
    getChronicleCustom,
    setChronicleCustom,

    // Loading states (for UI components that need to track multiple calls)
    isLoading,
    get loadingStates() {
      return loadingStatesRef.current
    },
  }), [health, chat, status, sessions, playthroughs, cachedChronicle, setPlaythroughLabel, trashPlaythrough, restorePlaythrough, resetChronicle, undoChronicleReset, deletePlaythrough, historyStorage, sessionEvents, recap, chronicle, regenerateChapter, endSession, getChronicleCustom, setChronicleCustom, isLoading])
}

export default useBackend
