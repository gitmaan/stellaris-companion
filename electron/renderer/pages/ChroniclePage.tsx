import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import ChronicleChapterList from '../components/ChronicleChapterList'
import ChronicleContent from '../components/ChronicleContent'
import ChronicleInfoPanel from '../components/ChronicleInfoPanel'
import { useBackend, ChronicleResponse } from '../hooks/useBackend'
import { generateChronicleHtml } from '../lib/chronicleExport'

interface SaveInfo {
  save_id: string
  empire_name: string
  ethics?: string[]
  chapter_count: number
  last_date: string
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

/**
 * ChroniclePage - The hero feature: your empire's living history book
 * Galactic Archives aesthetic - document your empire's journey through the stars
 */
function ChroniclePage() {
  const backend = useBackend()
  const isMountedRef = useRef(true)

  // Cached sessions - fetched once, reused across operations
  const [cachedSessions, setCachedSessions] = useState<Session[]>([])
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

  // Chronicle data
  const [chronicle, setChronicle] = useState<ChronicleResponse | null>(null)
  const [savesLoading, setSavesLoading] = useState(true)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Selected chapter (null = show current era)
  const [selectedChapter, setSelectedChapter] = useState<number | null>(null)

  // Narrator panel state
  const [narratorPanelOpen, setNarratorPanelOpen] = useState(false)

  // Sidebar collapse state
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

  // Regeneration state - tracks which chapter is being regenerated
  const [regeneratingChapter, setRegeneratingChapter] = useState<number | null>(null)
  const [confirmRegen, setConfirmRegen] = useState<number | null>(null)
  const [justRegenerated, setJustRegenerated] = useState<number | null>(null)

  // Prevent concurrent chronicle requests and ignore stale results.
  const chronicleRequestTokenRef = useRef(0)
  const chronicleInFlightRef = useRef(false)
  const queuedForceRefreshRef = useRef(false)
  const chronicleRetryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastAutoSavesRefreshAtRef = useRef(0)
  const lastSeenIngestionUpdatedAtRef = useRef<number | null>(null)
  const didInitChapterSelectionRef = useRef(false)
  const pendingVisibleChronicleRefreshRef = useRef(false)
  const hiddenChapterFinalizeInFlightRef = useRef(false)
  const lastHiddenChapterFinalizeAtRef = useRef(0)
  const visibleCatchupInFlightRef = useRef(false)

  // Load available saves from sessions (fetches and caches sessions)
  const loadSaves = useCallback(async (opts?: { silent?: boolean }) => {
    const silent = opts?.silent ?? false
    if (!silent) setSavesLoading(true)
    const result = await backend.sessions()
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
      // Cache the sessions for reuse in other operations
      const incomingSessions = result.data.sessions
      setCachedSessions(prev => (
        areSessionsEquivalent(prev, incomingSessions) ? prev : incomingSessions
      ))

      // Group sessions by save_id to get unique saves
      const saveMap = new Map<string, SaveInfo>()

      for (const session of incomingSessions) {
        const saveId = session.save_id

        if (!saveMap.has(saveId)) {
          saveMap.set(saveId, {
            save_id: saveId,
            empire_name: session.empire_name,
            chapter_count: 0,
            last_date: session.last_game_date,
          })
        } else {
          // Update with latest date
          const existing = saveMap.get(saveId)!
          if (session.last_game_date > existing.last_date) {
            existing.last_date = session.last_game_date
          }
        }
      }

      const saveList = Array.from(saveMap.values())
      setSaves(saveList)

      // Auto-select first save if none selected
      if (saveList.length > 0) {
        setSelectedSaveId(prev => prev ?? saveList[0].save_id)
      }
    }
    if (!silent) setSavesLoading(false)
  }, [backend])

  // Load chronicle for selected save (uses cached sessions)
  const loadChronicle = useCallback(async (forceRefresh = false) => {
    if (!selectedSaveId) return

    // Use cached sessions instead of fetching again
    const session = latestSessionBySaveId.get(selectedSaveId)

    if (!session) {
      setError('No session found for this save')
      return
    }

    // With <= 1 total snapshots for this save there are zero events
    // (events require diffs between snapshots). Skip the fetch entirely.
    const totalSnapshots = totalSnapshotsBySaveId.get(selectedSaveId) ?? 0
    if (totalSnapshots <= 1) {
      setChronicle(null)
      setLoading(false)
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

    chronicleInFlightRef.current = true
    const token = ++chronicleRequestTokenRef.current

    setLoading(true)
    setError(null)

    let shouldRetrySoon = false
    let retryAfterMs: number | null = null

    try {
      const chronicleResult = await backend.chronicle(session.id, forceRefresh)

      if (!isMountedRef.current) return
      if (token !== chronicleRequestTokenRef.current) return

      if (chronicleResult.error) {
        if (chronicleResult.errorCode === 'CHRONICLE_IN_PROGRESS' && chronicleResult.retryAfterMs) {
          shouldRetrySoon = true
          retryAfterMs = chronicleResult.retryAfterMs
        } else {
          setError(chronicleResult.error)
          setChronicle(null)
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
            void loadChronicle(false)
          }, delay)
          return
        }

        setLoading(false)

        if (queuedForceRefreshRef.current) {
          queuedForceRefreshRef.current = false
          void loadChronicle(true)
        }
      }
    }
  }, [backend, selectedSaveId, latestSessionBySaveId, totalSnapshotsBySaveId])

  const finalizePendingChaptersHidden = useCallback(async () => {
    if (isDocumentVisible()) return
    if (!selectedSaveId) return

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
      await backend.chronicle(session.id, false, true)
    } finally {
      hiddenChapterFinalizeInFlightRef.current = false
    }
  }, [backend, latestSessionBySaveId, selectedSaveId, totalSnapshotsBySaveId])

  const refreshVisibleChronicleAfterResume = useCallback(async () => {
    if (visibleCatchupInFlightRef.current) return
    if (!isDocumentVisible()) return
    if (!isMountedRef.current) return

    visibleCatchupInFlightRef.current = true

    try {
      await loadSaves({ silent: true })
      if (!isMountedRef.current) return
      await loadChronicle(false)
    } finally {
      visibleCatchupInFlightRef.current = false
    }
  }, [loadChronicle, loadSaves])

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
    }
  }, [loadSaves])

  // Refresh sessions when backend connects or ingestion advances so chronicle
  // updates while gameplay continues in the background.
  useEffect(() => {
    if (!window.electronAPI?.onBackendStatus) return

    const cleanup = window.electronAPI.onBackendStatus((status) => {
      if (!isMountedRef.current) return
      if (!status?.connected) return

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
      if (now - lastAutoSavesRefreshAtRef.current < 4000) return
      lastAutoSavesRefreshAtRef.current = now

      if (!isDocumentVisible()) {
        pendingVisibleChronicleRefreshRef.current = true
        void finalizePendingChaptersHidden()
        return
      }

      void loadSaves({ silent: true })
    })

    return () => {
      if (typeof cleanup === 'function') cleanup()
    }
  }, [cachedSessions.length, finalizePendingChaptersHidden, latestSessionBySaveId, loadSaves, selectedSaveId])

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
    if (selectedSaveId && cachedSessions.length > 0) {
      if (!isDocumentVisible()) {
        pendingVisibleChronicleRefreshRef.current = true
        void finalizePendingChaptersHidden()
        return
      }
      loadChronicle()
    }
  }, [cachedSessions.length, finalizePendingChaptersHidden, loadChronicle, selectedSaveId])

  // When the user returns to the app, run one full chronicle refresh to update
  // the current era narrative after hidden chapter-only catch-up.
  useEffect(() => {
    const handleVisible = () => {
      if (!isMountedRef.current) return
      if (!isDocumentVisible()) return
      if (!pendingVisibleChronicleRefreshRef.current) return

      pendingVisibleChronicleRefreshRef.current = false
      void refreshVisibleChronicleAfterResume()
    }

    document.addEventListener('visibilitychange', handleVisible)
    window.addEventListener('focus', handleVisible)
    return () => {
      document.removeEventListener('visibilitychange', handleVisible)
      window.removeEventListener('focus', handleVisible)
    }
  }, [refreshVisibleChronicleAfterResume])

  // Scroll spy: track which chapter is in view
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const isScrollingToRef = useRef(false)

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
      el.scrollIntoView({ behavior: 'smooth' })
      // Re-enable scroll spy after the smooth scroll completes
      setTimeout(() => { isScrollingToRef.current = false }, 800)
    }
  }, [regeneratingChapter])

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
    setError(null)
    setSelectedSaveId(saveId)
    setChronicle(null)
    setSelectedChapter(null)
  }, [])

  // Handle refresh (generate more chapters)
  const handleRefresh = useCallback(() => {
    loadChronicle(true)
  }, [loadChronicle])

  // Handle chapter regeneration (uses cached sessions)
  const handleRegenerateChapter = useCallback(async (chapterNumber: number, regenerationInstructions?: string) => {
    if (confirmRegen !== chapterNumber) {
      // First click - show confirmation
      setConfirmRegen(chapterNumber)
      return
    }

    // Second click - do the regeneration
    setConfirmRegen(null)
    setRegeneratingChapter(chapterNumber)
    setJustRegenerated(null)

    // Use cached sessions instead of fetching again
    const session = selectedSaveId ? latestSessionBySaveId.get(selectedSaveId) : undefined

    if (!session) {
      setError('Session not found')
      setRegeneratingChapter(null)
      return
    }

    const result = await backend.regenerateChapter(session.id, chapterNumber, true, regenerationInstructions)

    if (!isMountedRef.current) return

    if (result.error) {
      setError(result.error)
      setRegeneratingChapter(null)
      return
    }

    // Silently reload chronicle data without showing loading spinner
    const chronicleResult = await backend.chronicle(session.id, false)
    if (!isMountedRef.current) return

    if (chronicleResult.data) {
      setChronicle(chronicleResult.data)
      setJustRegenerated(chapterNumber)
      // Clear highlight after animation
      setTimeout(() => {
        if (isMountedRef.current) setJustRegenerated(null)
      }, 2000)
    }

    setRegeneratingChapter(null)
  }, [backend, selectedSaveId, confirmRegen, latestSessionBySaveId])

  // Cancel regeneration confirmation
  const handleCancelRegen = useCallback(() => {
    setConfirmRegen(null)
  }, [])

  // Get empire name for header
  const empireName = saves.find(s => s.save_id === selectedSaveId)?.empire_name || 'Unknown Empire'

  // Export chronicle as standalone HTML
  const handleExport = useCallback(async () => {
    if (!chronicle) return
    const html = generateChronicleHtml(empireName, chronicle.chapters, chronicle.current_era)
    const filename = `Chronicle - ${empireName}.html`
    await window.electronAPI?.exportChronicle(html, filename)
  }, [chronicle, empireName])

  return (
    <div className="h-full">
      <div className="flex h-full">
        {/* Left sidebar - Chapter navigation */}
        <ChronicleChapterList
          saves={saves}
          selectedSaveId={selectedSaveId}
          onSelectSave={handleSelectSave}
          chapters={chronicle?.chapters || []}
          currentEra={chronicle?.current_era || null}
          selectedChapter={selectedChapter}
          onSelectChapter={handleSelectChapter}
          pendingChapters={chronicle?.pending_chapters || 0}
          eventCount={chronicle?.event_count || 0}
          loading={savesLoading || loading}
          regeneratingChapter={regeneratingChapter}
          onRefresh={handleRefresh}
          onOpenNarratorPanel={() => setNarratorPanelOpen(true)}
          onExport={handleExport}
          collapsed={sidebarCollapsed}
          onToggleCollapse={() => setSidebarCollapsed(c => !c)}
        />

        {/* Right content panel - Chapter content */}
        <div className="flex-1 relative">
          {/* Expand sidebar button (visible when collapsed) - outside scroll area */}
          <AnimatePresence>
            {sidebarCollapsed && (
              <motion.button
                type="button"
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -8 }}
                transition={{ duration: 0.2 }}
                onClick={() => setSidebarCollapsed(false)}
                className="absolute top-3 left-3 z-10 w-7 h-7 flex items-center justify-center rounded text-text-secondary hover:text-accent-cyan transition-colors duration-150"
                title="Open sidebar"
              >
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="1.5" y="2.5" width="13" height="11" rx="1.5" />
                  <line x1="5.5" y1="2.5" x2="5.5" y2="13.5" />
                </svg>
              </motion.button>
            )}
          </AnimatePresence>
          <div ref={scrollContainerRef} className="absolute inset-0 overflow-y-auto p-6">
          <div className="relative">
            {error && (
              <div className="stellaris-panel bg-accent-red/10 border-accent-red/30 rounded-lg p-4 mb-4 flex justify-between items-center">
                <p className="text-accent-red text-sm m-0 flex items-center gap-2">
                  <span>⚠</span>
                  {error}
                </p>
                <button
                  onClick={() => setError(null)}
                  className="py-1.5 px-3 border border-accent-red/50 rounded-md bg-transparent text-accent-red text-xs font-medium cursor-pointer transition-colors duration-200 hover:bg-accent-red/20"
                >
                  Dismiss
                </button>
              </div>
            )}

            {savesLoading ? (
              <div className="flex flex-col items-center justify-center h-[300px] text-text-secondary gap-4">
                <div className="w-10 h-10 border-2 border-accent-cyan border-t-transparent rounded-full animate-spin-loader shadow-glow-sm" />
                <p className="text-sm uppercase tracking-wider">Loading Archives...</p>
              </div>
            ) : loading && !chronicle ? (
              <div className="flex flex-col items-center justify-center h-[300px] text-text-secondary gap-4">
                <div className="w-10 h-10 border-2 border-accent-cyan border-t-transparent rounded-full animate-spin-loader shadow-glow-sm" />
                <p className="text-sm uppercase tracking-wider">Retrieving Chronicle...</p>
              </div>
            ) : chronicle ? (
              <ChronicleContent
                empireName={empireName}
                chapters={chronicle.chapters}
                currentEra={chronicle.current_era}
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
                  No Chronicle Yet
                </h2>
                <p className="text-text-secondary max-w-md leading-relaxed text-sm">
                  Play your game and accumulate history. Chronicles are generated
                  automatically as your empire progresses through the ages.
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
    </div>
  )
}

export default ChroniclePage
