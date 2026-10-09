import { lazy, Suspense, useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { useReducedMotion } from 'framer-motion'
import Modal from '../components/Modal'
import { useMediaQuery } from '../hooks/useMediaQuery'
import { useReadingAnchor } from '../hooks/useReadingAnchor'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import ChronicleChapterList from '../components/ChronicleChapterList'
import ChatGPTUsage from '../components/ChatGPTUsage'
import { manageChatGPTUsage } from '../hooks/useChatGPT'
import ChronicleContent from '../components/ChronicleContent'
import ChronicleInfoPanel from '../components/ChronicleInfoPanel'
import ChroniclePublishDialog from '../components/ChroniclePublishDialog'
import { useBackend, ChronicleResponse, type Playthrough } from '../hooks/useBackend'
import { generateChronicleHtml } from '../lib/chronicleExport'
import { normalizeResolvedLanguage } from '../hooks/useSettings'
import { useToast } from '../components/Toast'
import {
  DEFAULT_CHRONICLE_REFRESH_MODE,
  type ChronicleRefreshMode,
  type ModelRoutingMode,
} from '../hooks/useSettings'
import { HUDMicro } from '../components/hud/HUDText'
import { HUDButton } from '../components/hud/HUDButton'

const CampaignHistoryDialog = lazy(() => import('../components/CampaignHistoryDialog'))

interface SaveInfo {
  save_id: string
  empire_name: string
  display_name: string
  ethics?: string[]
  chapter_count: number
  last_date: string
  is_current: boolean
  has_chronicle: boolean
}

// Session type from backend
interface Session {
  id: string
  save_id: string
  empire_name: string
  last_game_date: string
  snapshot_count: number
}

function areSessionsEquivalent(a: Session[], b: Session[]): boolean {
  if (a.length !== b.length) return false
  for (let i = 0; i < a.length; i += 1) {
    const left = a[i]
    const right = b[i]
    if (
      left.id !== right.id ||
      left.save_id !== right.save_id ||
      left.last_game_date !== right.last_game_date ||
      left.snapshot_count !== right.snapshot_count
    ) {
      return false
    }
  }
  return true
}

function isDocumentVisible(): boolean {
  return typeof document === 'undefined' || document.visibilityState === 'visible'
}

function getProviderName(provider: string | null): string {
  if (provider === 'chatgpt') return 'ChatGPT'
  switch (provider) {
    case 'ollama':
      return 'Ollama'
    case 'lm_studio':
      return 'LM Studio'
    case 'openrouter':
      return 'OpenRouter'
    case 'custom':
      return 'Custom provider'
    default:
      return 'Gemini'
  }
}

function getChronicleProviderErrorMessage({
  code,
  fallback,
  provider,
  t,
}: {
  code?: string | null
  fallback: string
  provider: string | null
  t: TFunction
}): string {
  if (code?.startsWith('CHATGPT_')) return String(t(`chatgpt.errors.${code}`, { defaultValue: t('chatgpt.errors.CHATGPT_UNAVAILABLE') }))
  const providerErrorKeys: Record<string, string> = {
    PROVIDER_UNAVAILABLE: 'providerUnavailable',
    PROVIDER_AUTH_FAILED: 'providerAuthFailed',
    PROVIDER_MODEL_NOT_FOUND: 'providerModelNotFound',
    PROVIDER_RATE_LIMITED: 'providerRateLimited',
    PROVIDER_BILLING_FAILED: 'providerBillingFailed',
    PROVIDER_TIMEOUT: 'providerTimeout',
    PROVIDER_CONTEXT_LIMIT: 'providerContextLimit',
    PROVIDER_INVALID_RESPONSE: 'providerInvalidResponse',
    PROVIDER_EMPTY_RESPONSE: 'providerEmptyResponse',
    PROVIDER_REQUEST_FAILED: 'providerRequestFailed',
  }
  const errorKey = code ? providerErrorKeys[code] : null
  if (!errorKey) return fallback
  return String(t(`chat.errors.${errorKey}`, { provider: getProviderName(provider) }))
}

function isProviderError(code?: string | null): boolean {
  return Boolean(code?.startsWith('PROVIDER_') || ['CHATGPT_RECONNECT', 'CHATGPT_PERMISSION', 'CHATGPT_MODEL', 'CHATGPT_INELIGIBLE'].includes(code || ''))
}

function gameDateOrder(value: string): number | null {
  const parts = value.split('.').map(Number)
  if (parts.length !== 3 || parts.some(part => !Number.isInteger(part)) || parts[0] < 0 || parts[1] < 1 || parts[1] > 12 || parts[2] < 1 || parts[2] > 31) return null
  return parts[0] * 372 + (parts[1] - 1) * 31 + parts[2]
}

/**
 * ChroniclePage - The hero feature: your empire's living history book
 * Galactic Archives aesthetic - document your empire's journey through the stars
 */
interface ChroniclePageProps {
  isActive?: boolean
  refreshMode?: ChronicleRefreshMode
  modelRoutingMode?: ModelRoutingMode
  onOpenSettings?: () => void
  historyOpenRequest?: number
}

function ChroniclePage({
  isActive = true,
  refreshMode = DEFAULT_CHRONICLE_REFRESH_MODE,
  modelRoutingMode,
  onOpenSettings,
  historyOpenRequest = 0,
}: ChroniclePageProps) {
  const { t, i18n } = useTranslation()
  const { showToast } = useToast()
  const backend = useBackend()
  const isMountedRef = useRef(true)

  // Cached sessions - fetched once, reused across operations
  const [cachedSessions, setCachedSessions] = useState<Session[]>([])
  const [playthroughs, setPlaythroughs] = useState<Playthrough[]>([])
  const latestSessionBySaveId = useMemo(() => {
    const map = new Map<string, Session>()
    for (const session of cachedSessions) {
      const existing = map.get(session.save_id)
      if (!existing || session.last_game_date > existing.last_game_date) {
        map.set(session.save_id, session)
      }
    }
    return map
  }, [cachedSessions])

  // Total snapshots per save (across all sessions). Events require diffs
  // between 2+ snapshots, so <= 1 means zero events and no chronicle.
  const totalSnapshotsBySaveId = useMemo(() => {
    const map = new Map<string, number>()
    for (const session of cachedSessions) {
      map.set(session.save_id, (map.get(session.save_id) ?? 0) + (session.snapshot_count ?? 0))
    }
    return map
  }, [cachedSessions])

  // Available saves/games
  const [saves, setSaves] = useState<SaveInfo[]>([])
  const [selectedSaveId, setSelectedSaveId] = useState<string | null>(null)
  const selectedSaveIdRef = useRef(selectedSaveId)
  selectedSaveIdRef.current = selectedSaveId
  const selectedPlaythrough = useMemo(
    () => playthroughs.find(item => item.save_id === selectedSaveId) || null,
    [playthroughs, selectedSaveId],
  )

  // Chronicle data
  const [mutationBusy, setMutationBusy] = useState(false)
  const mutationBusyRef = useRef(false)
  const [chronicle, setChronicle] = useState<ChronicleResponse | null>(null)
  const [savesLoading, setSavesLoading] = useState(true)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [errorNeedsSettings, setErrorNeedsSettings] = useState(false)
  const [usageLimited, setUsageLimited] = useState(false)
  const [chronicleProvider, setChronicleProvider] = useState<string | null>(null)
  const [chronicleConfigured, setChronicleConfigured] = useState<boolean | null>(null)
  const [liveSource, setLiveSource] = useState<{ saveId: string; date: string } | null>(null)

  // Selected chapter (null = show current era)
  const [selectedChapter, setSelectedChapter] = useState<number | null>(null)

  // Narrator panel state
  const [narratorPanelOpen, setNarratorPanelOpen] = useState(false)
  const [publishDialogOpen, setPublishDialogOpen] = useState(false)
  const [historyDialogOpen, setHistoryDialogOpen] = useState(false)

  useEffect(() => {
    if (historyOpenRequest > 0) setHistoryDialogOpen(true)
  }, [historyOpenRequest])

  // Sidebar collapse state
  const compactReader = useMediaQuery('(max-width: 1100px)')
  const reduceMotion = useReducedMotion()
  const [chapterDrawerOpen, setChapterDrawerOpen] = useState(false)
  useEffect(() => { if (!compactReader || !isActive) setChapterDrawerOpen(false) }, [compactReader, isActive])

  // Regeneration state - tracks which chapter is being regenerated
  const [regeneratingChapter, setRegeneratingChapter] = useState<number | null>(null)
  const regeneratingChapterRef = useRef<number | null>(null)
  regeneratingChapterRef.current = regeneratingChapter
  const confirmRevisionRef = useRef<string>()
  const [confirmRegen, setConfirmRegen] = useState<number | null>(null)
  const [justRegenerated, setJustRegenerated] = useState<number | null>(null)

  // Prevent concurrent chronicle requests and ignore stale results.
  const chronicleRequestTokenRef = useRef(0)
  const chronicleInFlightRef = useRef(false)
  // A provider failure pauses automatic spending for this campaign until Retry.
  const failedAutoRefreshSavesRef = useRef(new Set<string>())
  const queuedForceRefreshRef = useRef(false)
  const chronicleRetryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastAutoSavesRefreshAtRef = useRef(0)
  const autoSavesRefreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastFocusChronicleRefreshAtRef = useRef(0)
  const lastChronicleLoadStartedAtRef = useRef(0)
  const lastSeenIngestionUpdatedAtRef = useRef<number | null>(null)
  const didInitChapterSelectionRef = useRef(false)
  const pendingVisibleChronicleRefreshRef = useRef(false)
  const hiddenChapterFinalizeInFlightRef = useRef(false)
  const lastHiddenChapterFinalizeAtRef = useRef(0)
  const visibleCatchupInFlightRef = useRef(false)

  // A locale or automatically selected campaign can change without the picker.
  // Invalidate responses from the previous reader scope just as picker changes do.
  const readerScope = `${selectedSaveId || ''}:${normalizeResolvedLanguage(i18n.resolvedLanguage || i18n.language)}`
  const readerScopeRef = useRef(readerScope)
  useEffect(() => {
    if (readerScopeRef.current === readerScope) return
    readerScopeRef.current = readerScope
    chronicleRequestTokenRef.current += 1
    chronicleInFlightRef.current = false
    queuedForceRefreshRef.current = false
    didInitChapterSelectionRef.current = false
    if (chronicleRetryTimerRef.current) {
      clearTimeout(chronicleRetryTimerRef.current)
      chronicleRetryTimerRef.current = null
    }
    setChronicle(null)
    setLoading(false)
    setSelectedChapter(null)
    setConfirmRegen(null)
    setRegeneratingChapter(null)
    regeneratingChapterRef.current = null
  }, [readerScope])

  // Load save-scoped campaign summaries. This is metadata-only and never generates
  // or rewrites Chronicle content.
  const loadSaves = useCallback(async (opts?: { silent?: boolean }) => {
    const silent = opts?.silent ?? false
    if (!silent) setSavesLoading(true)
    const result = await backend.playthroughs(true)
    if (!isMountedRef.current) return

    if (result.error) {
      // Don't show error banner — the "No Chronicle Yet" empty state is
      // the correct display when sessions can't be loaded (backend starting,
      // no data yet, etc.). The onBackendStatus listener will retry once
      // the backend connects.
      if (!silent) setSavesLoading(false)
      return
    }

    if (result.data) {
      const allPlaythroughs = result.data.playthroughs
      const activePlaythroughs = allPlaythroughs.filter(item => !item.is_trashed)
      setPlaythroughs(allPlaythroughs)

      // Existing generation APIs remain session-scoped. The campaign summary
      // supplies the latest session without collapsing or rewriting old sessions.
      const incomingSessions: Session[] = activePlaythroughs.map(item => ({
        id: item.latest_session_id,
        save_id: item.save_id,
        empire_name: item.empire_name || item.display_name,
        last_game_date: item.last_game_date || '',
        snapshot_count: item.snapshot_count,
      }))
      setCachedSessions(prev => (
        areSessionsEquivalent(prev, incomingSessions) ? prev : incomingSessions
      ))
      const saveList: SaveInfo[] = activePlaythroughs.map(item => ({
        save_id: item.save_id,
        empire_name: item.empire_name || item.display_name,
        display_name: item.display_name,
        chapter_count: item.total_chapter_count,
        last_date: item.last_game_date || '—',
        is_current: item.is_current,
        has_chronicle: item.has_chronicle,
      }))
      setSaves(saveList)

      setSelectedSaveId(previous => {
        if (previous && saveList.some(item => item.save_id === previous)) return previous
        const remembered = window.localStorage.getItem('chronicle.lastSelectedSaveId')
        const next = activePlaythroughs.find(item => item.is_current)?.save_id
          || (remembered && saveList.some(item => item.save_id === remembered) ? remembered : null)
          || saveList[0]?.save_id
          || null
        return next
      })
    }
    if (!silent) setSavesLoading(false)
  }, [backend])

  // Load chronicle for selected save (uses cached sessions)
  const loadChronicle = useCallback(async (
    forceRefresh = false,
    chapterOnly = false,
  ) => {
    if (!selectedSaveId || mutationBusyRef.current || regeneratingChapterRef.current !== null) return
    if (!forceRefresh && chapterOnly && refreshMode === 'manual') return
    const autoRefreshPaused = !forceRefresh && failedAutoRefreshSavesRef.current.has(selectedSaveId)
    if (autoRefreshPaused && chapterOnly) return
    if (forceRefresh) failedAutoRefreshSavesRef.current.delete(selectedSaveId)

    // Use cached sessions instead of fetching again
    const session = latestSessionBySaveId.get(selectedSaveId)

    if (!session) {
      setError(t('chronicle.page.noSession'))
      return
    }

    if (chronicleRetryTimerRef.current) {
      clearTimeout(chronicleRetryTimerRef.current)
      chronicleRetryTimerRef.current = null
    }

    if (chronicleInFlightRef.current) {
      if (forceRefresh) queuedForceRefreshRef.current = true
      return
    }

    if (!chapterOnly) lastChronicleLoadStartedAtRef.current = Date.now()
    chronicleInFlightRef.current = true
    const token = ++chronicleRequestTokenRef.current

    setLoading(true)
    if (!autoRefreshPaused) setError(null)
    setErrorNeedsSettings(false)

    let shouldRetrySoon = false
    let retryAfterMs: number | null = null

    try {
      // Browsing history first performs a pure cache read. Historical campaigns
      // stop here, so opening them never spends model quota or rewrites content.
      if (!forceRefresh && !chapterOnly) {
        const cachedResult = await backend.cachedChronicle(selectedSaveId)
        if (!isMountedRef.current || token !== chronicleRequestTokenRef.current) return
        if (cachedResult.data) {
          const cached = cachedResult.data
          const hasCachedContent = cached.cached && Boolean(
            cached.chronicle.trim() || cached.chapters.length || cached.current_era,
          )
          setChronicle(hasCachedContent ? cached : null)
          if (cached.chapters.length > 0) {
            didInitChapterSelectionRef.current = true
            setSelectedChapter(previous => previous ?? 1)
          } else {
            didInitChapterSelectionRef.current = false
            setSelectedChapter(null)
          }
        }

        const totalSnapshots = totalSnapshotsBySaveId.get(selectedSaveId) ?? 0
        if (!selectedPlaythrough?.is_current || chronicleConfigured === false || totalSnapshots <= 1) {
          return
        }
      }

      if (autoRefreshPaused || (!forceRefresh && refreshMode === 'manual')) return

      const chronicleResult = await backend.chronicle(
        session.id,
        forceRefresh,
        chapterOnly,
        refreshMode,
        modelRoutingMode,
      )

      if (!isMountedRef.current) return
      if (token !== chronicleRequestTokenRef.current) return

      if (chronicleResult.error) {
        if (chronicleResult.errorCode === 'CHRONICLE_IN_PROGRESS' && chronicleResult.retryAfterMs) {
          shouldRetrySoon = true
          retryAfterMs = chronicleResult.retryAfterMs
        } else if (chronicleResult.errorCode === 'CHRONICLE_PROVIDER_NOT_CONFIGURED') {
          setChronicleConfigured(false)
          setError(null)
        } else {
          if (isProviderError(chronicleResult.errorCode)) {
            failedAutoRefreshSavesRef.current.add(selectedSaveId)
          }
          setError(getChronicleProviderErrorMessage({
            code: chronicleResult.errorCode,
            fallback: chronicleResult.error,
            provider: chronicleProvider,
            t,
          }))
          setErrorNeedsSettings(isProviderError(chronicleResult.errorCode))
          setUsageLimited(chronicleResult.errorCode === 'CHATGPT_LIMIT')
        }
      } else if (chronicleResult.data) {
        setChronicle(chronicleResult.data)
        if (chronicleResult.data.chapters.length === 0) {
          didInitChapterSelectionRef.current = false
          setSelectedChapter(null)
        } else {
          // Only auto-select on first load for a save. Keep the user's
          // navigation target on background refreshes.
          setSelectedChapter(prev => {
            if (!didInitChapterSelectionRef.current && prev === null) {
              didInitChapterSelectionRef.current = true
              return 1
            }
            if (typeof prev === 'number' && prev > chronicleResult.data!.chapters.length) {
              return chronicleResult.data!.chapters.length
            }
            return prev
          })
        }
      }
    } finally {
      if (token === chronicleRequestTokenRef.current) {
        chronicleInFlightRef.current = false
        if (!isMountedRef.current) return

        if (shouldRetrySoon) {
          const delay = typeof retryAfterMs === 'number' && retryAfterMs > 0 ? retryAfterMs : 2000
          chronicleRetryTimerRef.current = setTimeout(() => {
            if (!isMountedRef.current) return
            void loadChronicle(false, chapterOnly)
          }, delay)
          return
        }

        setLoading(false)

        if (queuedForceRefreshRef.current) {
          queuedForceRefreshRef.current = false
          void loadChronicle(true, false)
        }
      }
    }
  }, [
    backend,
    latestSessionBySaveId,
    modelRoutingMode,
    refreshMode,
    chronicleProvider,
    chronicleConfigured,
    selectedSaveId,
    selectedPlaythrough,
    t,
    totalSnapshotsBySaveId,
  ])

  const finalizePendingChaptersHidden = useCallback(async () => {
    if (isDocumentVisible()) return
    if (chronicleConfigured === false) return
    if (!selectedSaveId) return
    if (!selectedPlaythrough?.is_current) return

    const session = latestSessionBySaveId.get(selectedSaveId)
    if (!session) return

    const totalSnapshots = totalSnapshotsBySaveId.get(selectedSaveId) ?? 0
    if (totalSnapshots <= 1) return

    const now = Date.now()
    if (hiddenChapterFinalizeInFlightRef.current) return
    if (now - lastHiddenChapterFinalizeAtRef.current < 4000) return

    hiddenChapterFinalizeInFlightRef.current = true
    lastHiddenChapterFinalizeAtRef.current = now

    try {
      await loadChronicle(false, true)
    } finally {
      hiddenChapterFinalizeInFlightRef.current = false
    }
  }, [
    chronicleConfigured,
    latestSessionBySaveId,
    loadChronicle,
    selectedSaveId,
    selectedPlaythrough,
    totalSnapshotsBySaveId,
  ])

  const refreshVisibleChronicleAfterResume = useCallback(async () => {
    if (visibleCatchupInFlightRef.current) return
    if (!isActive) return
    if (!isDocumentVisible()) return
    if (!isMountedRef.current) return

    const catchupStartedAt = Date.now()
    if (catchupStartedAt - lastChronicleLoadStartedAtRef.current < 2000) return
    const requestTokenAtStart = chronicleRequestTokenRef.current
    visibleCatchupInFlightRef.current = true

    try {
      await loadSaves({ silent: true })
      if (!isMountedRef.current) return
      // Campaign selection invalidates a refresh that was queued for the
      // previously visible campaign while metadata was loading.
      if (requestTokenAtStart !== chronicleRequestTokenRef.current) return
      // Initial activation may have loaded the Chronicle while this focus
      // catch-up was refreshing metadata. Do not immediately load it again.
      if (lastChronicleLoadStartedAtRef.current >= catchupStartedAt) return
      await loadChronicle(false, false)
    } finally {
      visibleCatchupInFlightRef.current = false
    }
  }, [isActive, loadChronicle, loadSaves])

  // Initial load
  useEffect(() => {
    isMountedRef.current = true
    loadSaves()
    return () => {
      isMountedRef.current = false
      if (chronicleRetryTimerRef.current) {
        clearTimeout(chronicleRetryTimerRef.current)
        chronicleRetryTimerRef.current = null
      }
      if (autoSavesRefreshTimerRef.current) {
        clearTimeout(autoSavesRefreshTimerRef.current)
        autoSavesRefreshTimerRef.current = null
      }
    }
  }, [loadSaves])

  const refreshSessionsAfterIngestion = useCallback(() => {
    autoSavesRefreshTimerRef.current = null
    if (!isMountedRef.current) return

    lastAutoSavesRefreshAtRef.current = Date.now()
    if (!isDocumentVisible()) {
      pendingVisibleChronicleRefreshRef.current = true
      void finalizePendingChaptersHidden()
      return
    }

    void loadSaves({ silent: true })
  }, [finalizePendingChaptersHidden, loadSaves])

  // Refresh sessions when backend connects or ingestion advances so chronicle
  // updates while gameplay continues in the background.
  useEffect(() => {
    if (!window.electronAPI?.onBackendStatus) return

    const cleanup = window.electronAPI.onBackendStatus((status) => {
      if (!isMountedRef.current) return
      if (!status?.connected) return
      if (status.save_loaded && status.save_id && status.game_date) {
        const saveId = status.save_id, date = status.game_date
        setLiveSource(previous => previous?.saveId === saveId && previous.date === date ? previous : { saveId, date })
      } else if (status.save_loaded === false) setLiveSource(null)
      if (typeof status.chronicle_configured === 'boolean') {
        setChronicleConfigured(status.chronicle_configured)
      }
      if (typeof status.chronicle_provider === 'string') {
        setChronicleProvider(status.chronicle_provider)
      } else if (typeof status.advisor_provider === 'string') {
        setChronicleProvider(status.advisor_provider)
      }

      const selectedSession = selectedSaveId ? latestSessionBySaveId.get(selectedSaveId) : null
      const backendGameDate = status.game_date || null
      const gameDateAdvanced = Boolean(
        backendGameDate &&
          (!selectedSession?.last_game_date || backendGameDate > selectedSession.last_game_date)
      )

      let ingestionAdvanced = false
      const ingestionUpdatedAt = status.ingestion?.updated_at
      if (typeof ingestionUpdatedAt === 'number' && Number.isFinite(ingestionUpdatedAt)) {
        if (
          lastSeenIngestionUpdatedAtRef.current !== null &&
          ingestionUpdatedAt > lastSeenIngestionUpdatedAtRef.current
        ) {
          ingestionAdvanced = true
        }
        lastSeenIngestionUpdatedAtRef.current = ingestionUpdatedAt
      }

      const shouldRefresh = cachedSessions.length === 0 || gameDateAdvanced || ingestionAdvanced
      if (!shouldRefresh) return

      const now = Date.now()
      const throttleRemainingMs = 4000 - (now - lastAutoSavesRefreshAtRef.current)
      if (throttleRemainingMs > 0) {
        if (!autoSavesRefreshTimerRef.current) {
          autoSavesRefreshTimerRef.current = setTimeout(
            refreshSessionsAfterIngestion,
            throttleRemainingMs,
          )
        }
        return
      }

      refreshSessionsAfterIngestion()
    })

    return () => {
      if (typeof cleanup === 'function') cleanup()
    }
  }, [
    cachedSessions.length,
    finalizePendingChaptersHidden,
    latestSessionBySaveId,
    loadSaves,
    refreshSessionsAfterIngestion,
    selectedSaveId,
  ])

  // Periodic backstop refresh in case backend status metadata misses an edge case.
  useEffect(() => {
    const timer = setInterval(() => {
      if (!isMountedRef.current) return
      if (!isDocumentVisible()) {
        pendingVisibleChronicleRefreshRef.current = true
        void finalizePendingChaptersHidden()
        return
      }
      void loadSaves({ silent: true })
    }, 30000)

    return () => clearInterval(timer)
  }, [finalizePendingChaptersHidden, loadSaves])

  // Load chronicle when save changes (only after sessions are cached)
  useEffect(() => {
    // A campaign switch can occur while Edit or Undo is saving. Resume the
    // selected reader when it settles, using the usual visibility/refresh policy.
    if (mutationBusy) return
    if (selectedSaveId && cachedSessions.length > 0) {
      if (!isActive) {
        pendingVisibleChronicleRefreshRef.current = true
        return
      }
      if (!isDocumentVisible()) {
        pendingVisibleChronicleRefreshRef.current = true
        void finalizePendingChaptersHidden()
        return
      }
      if (pendingVisibleChronicleRefreshRef.current) {
        return
      }
      loadChronicle(false, false)
    }
  }, [
    cachedSessions.length,
    finalizePendingChaptersHidden,
    isActive,
    loadChronicle,
    mutationBusy,
    selectedSaveId,
  ])

  const processPendingVisibleChronicleRefresh = useCallback(() => {
    if (!isMountedRef.current) return
    if (!isActive) return
    if (!isDocumentVisible()) return
    if (!pendingVisibleChronicleRefreshRef.current) return

    pendingVisibleChronicleRefreshRef.current = false
    void refreshVisibleChronicleAfterResume()
  }, [isActive, refreshVisibleChronicleAfterResume])

  // When the user returns to the app, run one visible refresh so current era
  // can advance and external Chronicle edits saved through MCP are picked up.
  useEffect(() => {
    const handleVisible = () => {
      const hadPendingRefresh = pendingVisibleChronicleRefreshRef.current
      processPendingVisibleChronicleRefresh()
      if (hadPendingRefresh) return
      if (!isActive) return
      if (!isDocumentVisible()) return

      const now = Date.now()
      if (now - lastFocusChronicleRefreshAtRef.current < 2000) return
      lastFocusChronicleRefreshAtRef.current = now
      void refreshVisibleChronicleAfterResume()
    }

    document.addEventListener('visibilitychange', handleVisible)
    window.addEventListener('focus', handleVisible)
    return () => {
      document.removeEventListener('visibilitychange', handleVisible)
      window.removeEventListener('focus', handleVisible)
    }
  }, [isActive, processPendingVisibleChronicleRefresh, refreshVisibleChronicleAfterResume])

  useEffect(() => {
    processPendingVisibleChronicleRefresh()
  }, [processPendingVisibleChronicleRefresh])

  const changeChapter = useCallback(async (chapterNumber: number, revision: string, edit?: { title: string; narrative: string }): Promise<boolean> => {
    if (!selectedSaveId || mutationBusyRef.current) return false
    const token = chronicleRequestTokenRef.current
    mutationBusyRef.current = true
    setMutationBusy(true)
    try {
      const result = edit
        ? await backend.editChapter(selectedSaveId, chapterNumber, revision, edit.title, edit.narrative)
        : await backend.undoChapter(selectedSaveId, chapterNumber, revision)
      if (!isMountedRef.current || token !== chronicleRequestTokenRef.current) return false
      if (!result.data) {
        showToast({ type: 'error', message: result.errorCode === 'CHRONICLE_CONFLICT' ? t('continuity.editConflict') : result.error || t('continuity.editFailed') })
        if (result.errorCode === 'CHRONICLE_CONFLICT') {
          const cached = await backend.cachedChronicle(selectedSaveId)
          if (isMountedRef.current && token === chronicleRequestTokenRef.current && cached.data) setChronicle(cached.data)
        }
        return false
      }
      setChronicle(result.data)
      return true
    } finally {
      mutationBusyRef.current = false
      if (isMountedRef.current) setMutationBusy(false)
    }
  }, [backend, selectedSaveId, showToast, t])

  // Scroll spy: track which chapter is in view
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const isScrollingToRef = useRef(false)
  const scrollSpyTimer = useRef<ReturnType<typeof setTimeout>>()
  useEffect(() => () => clearTimeout(scrollSpyTimer.current), [])
  useReadingAnchor(scrollContainerRef, selectedSaveId)

  const restoredReadingKeyRef = useRef<string | null>(null)
  useEffect(() => { restoredReadingKeyRef.current = null }, [selectedSaveId, i18n.language])
  useEffect(() => {
    if (!isActive || !chronicle || !selectedSaveId) return
    const container = scrollContainerRef.current
    if (!container) return
    const language = normalizeResolvedLanguage(i18n.resolvedLanguage || i18n.language)
    if (chronicle.language && normalizeResolvedLanguage(chronicle.language) !== language) return
    const key = `chronicle-reading:${selectedSaveId}:${language}`
    let frame = 0
    let timer: ReturnType<typeof setTimeout> | undefined
    let disposed = false
    const blocks = () => Array.from(container.querySelectorAll<HTMLElement>('[data-reading-id]'))
    const storePosition = () => {
      if (disposed || restoredReadingKeyRef.current !== key || container.clientHeight === 0) return
      // The opening title is part of the reading position. Mapping the top of the
      // page to paragraph zero would skip the entire header when reopening it.
      if (container.scrollTop <= 1) {
        try { localStorage.setItem(key, JSON.stringify({ atStart: true })) } catch { /* Reading preferences are optional. */ }
        return
      }
      const top = container.getBoundingClientRect().top + 12
      const all = blocks()
      const block = all.find(item => item.getBoundingClientRect().bottom > top) || all[all.length - 1]
      if (!block) return
      const paragraphs = Array.from(block.querySelectorAll<HTMLElement>('.chronicle-narrative > p, .chronicle-narrative > blockquote, .chronicle-narrative > div'))
      const paragraph = paragraphs.find(item => item.getBoundingClientRect().bottom > top)
      const target = paragraph || block
      const offset = Math.max(0, Math.min(1, (top - target.getBoundingClientRect().top) / Math.max(1, target.offsetHeight)))
      try { localStorage.setItem(key, JSON.stringify({ id: block.dataset.readingId, anchor: block.id, version: block.dataset.readingVersion, paragraph: paragraph ? paragraphs.indexOf(paragraph) : -1, offset })) } catch { /* Reader preferences must never interrupt reading. */ }
    }
    if (restoredReadingKeyRef.current !== key) {
      const restorePosition = () => {
        if (disposed) return
        frame = requestAnimationFrame(() => {
          if (disposed) return
          try {
            const raw = localStorage.getItem(key)
            const saved = raw ? JSON.parse(raw) : null
            if (saved?.atStart === true) {
              container.scrollTop = 0
            } else if (saved) {
              const all = blocks()
              const block = all.find(item => item.dataset.readingId === saved.id && item.id === saved.anchor)
                || all.find(item => item.id === saved.anchor) || all[0]
              if (block) {
                const paragraphs = Array.from(block.querySelectorAll<HTMLElement>('.chronicle-narrative > p, .chronicle-narrative > blockquote, .chronicle-narrative > div'))
                const unchanged = block.dataset.readingVersion === saved.version
                const target = unchanged && Number.isInteger(saved.paragraph) && saved.paragraph >= 0 ? paragraphs[saved.paragraph] || block : block
                const offset = unchanged && Number.isFinite(saved.offset) ? Math.max(0, Math.min(1, saved.offset)) * target.offsetHeight : 0
                container.scrollTop += target.getBoundingClientRect().top - container.getBoundingClientRect().top + offset - 12
                setSelectedChapter(block.id === 'current-era' ? null : Number(block.id.replace('chapter-', '')))
              }
            }
          } catch { /* Ignore invalid or unavailable local preferences. */ }
          restoredReadingKeyRef.current = key
        })
      }
      // Font metrics affect paragraph positions during the first file load.
      void document.fonts.ready.then(restorePosition, restorePosition)
    }
    const onScroll = () => { if (timer) clearTimeout(timer); timer = setTimeout(storePosition, 180) }
    container.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('beforeunload', storePosition)
    return () => {
      storePosition()
      disposed = true
      cancelAnimationFrame(frame)
      if (timer) clearTimeout(timer)
      container.removeEventListener('scroll', onScroll)
      window.removeEventListener('beforeunload', storePosition)
    }
  }, [chronicle, selectedSaveId, i18n.language, i18n.resolvedLanguage, isActive])

  useEffect(() => {
    if (!chronicle) return
    const container = scrollContainerRef.current
    if (!container) return

    const observer = new IntersectionObserver(
      (entries) => {
        if (isScrollingToRef.current) return
        const visible = entries.filter(entry => entry.isIntersecting)
        if (visible.length === 0) return

        // Pick a single best candidate to avoid oscillation when multiple
        // sections overlap the observer band.
        visible.sort((a, b) => (
          Math.abs(a.boundingClientRect.top) - Math.abs(b.boundingClientRect.top)
        ))

        const id = visible[0].target.id
        if (id === 'current-era') {
          setSelectedChapter(prev => (prev === null ? prev : null))
        } else if (id.startsWith('chapter-')) {
          const nextChapter = Number(id.replace('chapter-', ''))
          setSelectedChapter(prev => (prev === nextChapter ? prev : nextChapter))
        }
      },
      {
        root: container,
        rootMargin: '-10% 0px -80% 0px',
      }
    )

    // Observe after a tick so elements are rendered
    const timer = setTimeout(() => {
      container.querySelectorAll('[id^="chapter-"], #current-era').forEach(el => {
        observer.observe(el)
      })
    }, 100)

    return () => {
      clearTimeout(timer)
      observer.disconnect()
    }
  }, [chronicle])

  // Handle chapter selection - scroll to chapter, disabled during regeneration
  const handleSelectChapter = useCallback((chapterNumber: number | null) => {
    if (regeneratingChapter !== null) return // Prevent navigation during regen
    setSelectedChapter(chapterNumber)
    setJustRegenerated(null) // Clear highlight when navigating

    // Scroll to the target element
    const targetId = chapterNumber === null ? 'current-era' : `chapter-${chapterNumber}`
    const el = document.getElementById(targetId)
    if (el) {
      isScrollingToRef.current = true
      el.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' })
      // Re-enable scroll spy after the smooth scroll completes
      clearTimeout(scrollSpyTimer.current)
      scrollSpyTimer.current = setTimeout(() => { isScrollingToRef.current = false }, reduceMotion ? 0 : 800)
    }
  }, [regeneratingChapter, reduceMotion])

  // Handle save/game change
  const handleSelectSave = useCallback((saveId: string) => {
    chronicleRequestTokenRef.current += 1
    chronicleInFlightRef.current = false
    queuedForceRefreshRef.current = false
    pendingVisibleChronicleRefreshRef.current = false
    didInitChapterSelectionRef.current = false
    if (chronicleRetryTimerRef.current) {
      clearTimeout(chronicleRetryTimerRef.current)
      chronicleRetryTimerRef.current = null
    }
    setLoading(false)
    setRegeneratingChapter(null)
    regeneratingChapterRef.current = null
    setConfirmRegen(null)
    setJustRegenerated(null)
    setError(null)
    setErrorNeedsSettings(false)
    window.localStorage.setItem('chronicle.lastSelectedSaveId', saveId)
    setSelectedSaveId(saveId)
    setChronicle(null)
    setSelectedChapter(null)
  }, [])

  const handleHistoryChanged = useCallback(async (
    saveId: string,
    action: 'label' | 'trash' | 'restore' | 'reset' | 'undo-reset' | 'delete',
  ) => {
    const affectsSelectedChronicle = saveId === selectedSaveIdRef.current
      && ['trash', 'reset', 'delete'].includes(action)
    if (affectsSelectedChronicle) {
      chronicleRequestTokenRef.current += 1
      chronicleInFlightRef.current = false
      queuedForceRefreshRef.current = false
      setLoading(false)
      setRegeneratingChapter(null)
      regeneratingChapterRef.current = null
      setConfirmRegen(null)
      if (chronicleRetryTimerRef.current) {
        clearTimeout(chronicleRetryTimerRef.current)
        chronicleRetryTimerRef.current = null
      }
      setChronicle(null)
      setSelectedChapter(null)
      didInitChapterSelectionRef.current = false
    }
    await loadSaves({ silent: true })
    if (!isMountedRef.current) return
    if (saveId === selectedSaveIdRef.current && action === 'undo-reset') {
      const token = chronicleRequestTokenRef.current
      const restored = await backend.cachedChronicle(saveId)
      if (isMountedRef.current && token === chronicleRequestTokenRef.current && saveId === selectedSaveIdRef.current && restored.data?.cached) setChronicle(restored.data)
    }
  }, [backend, loadSaves, selectedSaveId])

  // Handle refresh (generate more chapters)
  const handleRefresh = useCallback(() => {
    loadChronicle(true, false)
  }, [loadChronicle])

  // Handle chapter regeneration (uses cached sessions)
  const handleRegenerateChapter = useCallback(async (chapterNumber: number, regenerationInstructions?: string) => {
    if (confirmRegen !== chapterNumber) {
      // First click - show confirmation
      confirmRevisionRef.current = chronicle?.chronicle_revision
      setConfirmRegen(chapterNumber)
      return
    }

    const token = chronicleRequestTokenRef.current
    // Second click - do the regeneration
    setConfirmRegen(null)
    regeneratingChapterRef.current = chapterNumber
    setRegeneratingChapter(chapterNumber)
    setJustRegenerated(null)

    // Use cached sessions instead of fetching again
    const session = selectedSaveId ? latestSessionBySaveId.get(selectedSaveId) : undefined

    if (!session) {
      setError('Session not found')
      setRegeneratingChapter(null)
      return
    }

    const result = await backend.regenerateChapter(
      session.id,
      chapterNumber,
      true,
      regenerationInstructions,
      modelRoutingMode,
      confirmRevisionRef.current,
    )

    if (!isMountedRef.current || token !== chronicleRequestTokenRef.current) return

    if (result.error) {
      if (result.errorCode === 'CHRONICLE_PROVIDER_NOT_CONFIGURED') {
        setChronicleConfigured(false)
        setError(null)
        setErrorNeedsSettings(false)
        setRegeneratingChapter(null)
        return
      }
      setError(getChronicleProviderErrorMessage({
        code: result.errorCode,
        fallback: result.error,
        provider: chronicleProvider,
        t,
      }))
      setErrorNeedsSettings(isProviderError(result.errorCode))
      setUsageLimited(result.errorCode === 'CHATGPT_LIMIT')
      setRegeneratingChapter(null)
      return
    }

    // Reading the updated archive never triggers another generation.
    const chronicleResult = await backend.cachedChronicle(session.save_id)
    if (!isMountedRef.current || token !== chronicleRequestTokenRef.current) return

    if (chronicleResult.data) {
      setChronicle(chronicleResult.data)
      setJustRegenerated(chapterNumber)
      // Clear highlight after animation
      setTimeout(() => {
        if (isMountedRef.current) setJustRegenerated(null)
      }, 2000)
    }

    setRegeneratingChapter(null)
  }, [
    backend,
    selectedSaveId,
    confirmRegen,
    chronicle?.chronicle_revision,
    latestSessionBySaveId,
    modelRoutingMode,
    refreshMode,
    chronicleProvider,
    t,
  ])

  // Cancel regeneration confirmation
  const handleCancelRegen = useCallback(() => {
    setConfirmRegen(null)
  }, [])

  const storyAfterLoadedSave = Boolean(
    liveSource?.saveId === selectedSaveId && chronicle?.coverage_date
    && gameDateOrder(chronicle.coverage_date) !== null && gameDateOrder(liveSource.date) !== null
    && gameDateOrder(chronicle.coverage_date)! > gameDateOrder(liveSource.date)!,
  )

  // Get empire name for header
  const empireName = saves.find(s => s.save_id === selectedSaveId)?.display_name || 'Unknown Empire'

  // Export chronicle as standalone HTML
  const handleExport = useCallback(async () => {
    if (!chronicle) return
    const exportLocale = chronicle.language ? normalizeResolvedLanguage(chronicle.language) : normalizeResolvedLanguage(i18n.language)
    const translate = i18n.getFixedT(exportLocale)
    const activeTheme = document.documentElement.getAttribute('data-theme')
    const html = generateChronicleHtml(
      empireName,
      chronicle.chapters,
      chronicle.current_era,
      {
        locale: exportLocale,
        theme: activeTheme || undefined,
        legacyChronicle: chronicle.chronicle,
        labels: {
          title: translate('chronicle.exportHtml.title', { empire: '{empire}' }),
          chapter: translate('chronicle.exportHtml.chapter'),
          summary: translate('chronicle.exportHtml.summary'),
          currentEra: translate('chronicle.exportHtml.currentEra'),
          storyContinues: translate('chronicle.exportHtml.storyContinues'),
          present: translate('chronicle.exportHtml.present'),
          events: translate('chronicle.exportHtml.events', { count: chronicle.current_era?.events_covered ?? 0 }).replace(String(chronicle.current_era?.events_covered ?? 0), '{count}'),
          footer: translate('chronicle.exportHtml.footer'),
        },
      },
    )
    const filename = `${translate('chronicle.exportHtml.filename')} - ${empireName.replace(/[<>:"/\\|?*\x00-\x1f]/g, '_')}.html`
    try {
      const result = await window.electronAPI?.exportChronicle(html, filename)
      if (result?.success === false) showToast({ type: 'error', message: t('chronicle.exportHtml.failure', { detail: result.error || '' }) })
      else if (result?.success) showToast({ type: 'success', message: t('chronicle.exportHtml.success') })
    } catch (error) {
      showToast({ type: 'error', message: t('chronicle.exportHtml.failure', { detail: error instanceof Error ? error.message : String(error) }) })
    }
  }, [chronicle, empireName, i18n, showToast, t])

  const chapterNavigation = (
    <ChronicleChapterList
          compact={compactReader}
          saves={saves}
          selectedSaveId={selectedSaveId}
          onSelectSave={saveId => { handleSelectSave(saveId); setChapterDrawerOpen(false) }}
          chapters={chronicle?.chapters || []}
          currentEra={chronicle?.current_era || null}
          selectedChapter={selectedChapter}
          onSelectChapter={chapter => { handleSelectChapter(chapter); setChapterDrawerOpen(false) }}
          pendingChapters={chronicle?.pending_chapters || 0}
          eventCount={chronicle?.event_count || 0}
          loading={savesLoading || loading}
          regeneratingChapter={regeneratingChapter}
          onRefresh={handleRefresh}
          onManageCampaigns={() => setHistoryDialogOpen(true)}
          onOpenNarratorPanel={() => setNarratorPanelOpen(true)}
          onPublish={() => setPublishDialogOpen(true)}
          onExport={handleExport}
          onToggleCollapse={compactReader ? () => setChapterDrawerOpen(false) : undefined}
        />
  )

  return (
    <div className="h-full">
      <div className="flex h-full">
        {/* Left sidebar - Chapter navigation */}
        {compactReader ? (
          <Modal open={chapterDrawerOpen} onClose={() => setChapterDrawerOpen(false)} label={t('chronicle.sidebar.chapters')} placement="left" className="w-[280px] flex">
            {chapterNavigation}
          </Modal>
        ) : chapterNavigation}


        {/* Right content panel - Chapter content */}
        <div className="flex-1 min-w-0 min-h-0 relative flex flex-col">
          {compactReader && <div className="chronicle-toolbar shrink-0 flex justify-end px-3 pt-2">
            <HUDButton type="button" variant="secondary" aria-haspopup="dialog" aria-controls="chronicle-navigation" aria-expanded={chapterDrawerOpen} onClick={() => setChapterDrawerOpen(true)} className="shrink-0 px-3 py-2">
              {t('chronicle.sidebar.chapters')}
            </HUDButton>
          </div>}
          <div ref={scrollContainerRef} data-chronicle-scroll className="chronicle-reader flex-1 min-h-0 overflow-y-auto p-3 lg:p-6" style={{ overflowAnchor: 'none' }}>
          <div className="relative">
            {storyAfterLoadedSave && <p role="status" className="mb-4 rounded border border-accent-yellow/20 bg-accent-yellow/5 px-4 py-3 text-xs text-text-secondary">{t('continuity.earlierSave')}</p>}
            {chronicleConfigured === false && (
              <div className="mb-4 flex flex-wrap items-center justify-between gap-4 border border-accent-yellow/40 bg-accent-yellow/5 px-4 py-3">
                <div className="min-w-0">
                  <HUDMicro className="text-accent-yellow">
                    {t('chronicle.providerSetup.title')}
                  </HUDMicro>
                  <p className="mt-1 max-w-2xl text-sm leading-relaxed text-text-secondary">
                    {t('chronicle.providerSetup.description')}
                  </p>
                </div>
                <HUDButton
                  type="button"
                  variant="secondary"
                  onClick={onOpenSettings}
                  disabled={!onOpenSettings}
                  className="px-3 py-1.5 text-[10px]"
                >
                  {t('chronicle.providerSetup.action')}
                </HUDButton>
              </div>
            )}

            {selectedSaveId && failedAutoRefreshSavesRef.current.has(selectedSaveId) && (
              <div className="flex items-center gap-3 text-text-secondary text-sm mb-4">
                <p role="status">{t('chronicle.page.autoRefreshPaused')}</p>
                <HUDButton type="button" variant="secondary" onClick={handleRefresh} disabled={loading}>
                  {t('common.retry')}
                </HUDButton>
              </div>
            )}

            {chronicleProvider === 'chatgpt' && <ChatGPTUsage disabled={loading || regeneratingChapter !== null} />}
            {error && (
              <div className="stellaris-panel bg-accent-red/10 border-accent-red/30 rounded-lg p-4 mb-4 flex flex-wrap justify-between items-center gap-3">
                <p className="text-accent-red text-sm m-0 flex items-center gap-2">
                  <span>⚠</span>
                  {error}
                </p>
                <div className="flex items-center gap-2">
                  {usageLimited && <HUDButton type="button" onClick={() => void manageChatGPTUsage()}>{t('chatgpt.manageUsage')}</HUDButton>}
                  {errorNeedsSettings && onOpenSettings && (
                    <HUDButton
                      type="button"
                      variant="secondary"
                      onClick={onOpenSettings}
                      className="px-3 py-1.5 text-[10px]"
                    >
                      {t('chronicle.providerSetup.action')}
                    </HUDButton>
                  )}
                  <button
                    onClick={() => {
                      setError(null)
                      setErrorNeedsSettings(false)
                    }}
                    className="py-1.5 px-3 border border-accent-red/50 rounded-md bg-transparent text-accent-red text-xs font-medium cursor-pointer transition-colors duration-200 hover:bg-accent-red/20"
                  >
                    {t('chronicle.page.dismiss')}
                  </button>
                </div>
              </div>
            )}

            {chronicle?.model_routing?.fallback && chronicle.model_routing.notice && (
              <div className="stellaris-panel bg-accent-yellow/10 border-accent-yellow/30 rounded-lg p-3 mb-4">
                <HUDMicro className="text-accent-yellow">
                  {chronicle.model_routing.notice}
                </HUDMicro>
              </div>
            )}

            {savesLoading ? (
              <div className="flex flex-col items-center justify-center h-[300px] text-text-secondary gap-4">
                <div className="w-10 h-10 border-2 border-accent-cyan border-t-transparent rounded-full animate-spin-loader shadow-glow-sm" />
                <p className="text-sm uppercase tracking-wider">{t('chronicle.page.loadingArchives')}</p>
              </div>
            ) : loading && !chronicle ? (
              <div className="flex flex-col items-center justify-center h-[300px] text-text-secondary gap-4">
                <div className="w-10 h-10 border-2 border-accent-cyan border-t-transparent rounded-full animate-spin-loader shadow-glow-sm" />
                <p className="text-sm uppercase tracking-wider">{t('chronicle.page.retrieving')}</p>
              </div>
            ) : chronicle ? (
              <ChronicleContent
                revision={chronicle.chronicle_revision}
                coverageDate={chronicle.coverage_date}
                mutationBusy={mutationBusy || loading}
                onEdit={(number, revision, title, narrative) => changeChapter(number, revision, { title, narrative })}
                onUndo={(number, revision) => void changeChapter(number, revision)}
                empireName={empireName}
                chapters={chronicle.chapters}
                currentEra={chronicle.current_era}
                legacyChronicle={chronicle.chronicle}
                onRegenerate={handleRegenerateChapter}
                confirmingRegen={confirmRegen}
                onCancelRegen={handleCancelRegen}
                regeneratingChapter={regeneratingChapter}
                justRegenerated={justRegenerated}
              />
            ) : (
              <div className="flex flex-col items-center justify-center text-center h-[400px]">
                <div className="text-accent-cyan text-5xl mb-6">◇</div>
                <h2 className="font-display text-text-primary text-2xl tracking-wider uppercase mb-3">
                  {t('chronicle.page.emptyTitle')}
                </h2>
                <p className="text-text-secondary max-w-md leading-relaxed text-sm">
                  {t('chronicle.page.emptyBody')}
                </p>
              </div>
            )}
          </div>
          </div>
        </div>
      </div>

      <ChronicleInfoPanel
        isOpen={narratorPanelOpen}
        onClose={() => setNarratorPanelOpen(false)}
        selectedSaveId={selectedSaveId}
      />
      <ChroniclePublishDialog
        isOpen={publishDialogOpen}
        onClose={() => setPublishDialogOpen(false)}
        saveId={selectedSaveId}
        empireName={empireName}
        chronicle={chronicle}
      />
      {historyDialogOpen && (
        <Suspense fallback={null}>
          <CampaignHistoryDialog
            isOpen
            onClose={() => setHistoryDialogOpen(false)}
            playthroughs={playthroughs}
            onChanged={handleHistoryChanged}
          />
        </Suspense>
      )}
    </div>
  )
}

export default ChroniclePage
