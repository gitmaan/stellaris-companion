import { useState, useEffect, useCallback, useRef } from 'react'
import ChronicleChapterList from '../components/ChronicleChapterList'
import ChronicleContent from '../components/ChronicleContent'
import { useBackend, ChronicleResponse, ChronicleChapter, CurrentEra } from '../hooks/useBackend'
import './ChroniclePage.css'

interface SaveInfo {
  save_id: string
  empire_name: string
  ethics?: string[]
  chapter_count: number
  last_date: string
}

/**
 * ChroniclePage - The hero feature: your empire's living history book
 *
 * Layout:
 * - Left sidebar: Game selector, chapter navigation, stats
 * - Right panel: Full chapter content (markdown rendered)
 */
function ChroniclePage() {
  const backend = useBackend()
  const isMountedRef = useRef(true)

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

  // Regeneration state
  const [regenerating, setRegenerating] = useState(false)
  const [confirmRegen, setConfirmRegen] = useState<number | null>(null)

  // Load available saves from sessions
  const loadSaves = useCallback(async () => {
    setSavesLoading(true)
    const result = await backend.sessions()
    if (!isMountedRef.current) return

    if (result.error) {
      setError(result.error)
      setSavesLoading(false)
      return
    }

    if (result.data) {
      // Group sessions by save_id to get unique saves
      const saveMap = new Map<string, SaveInfo>()

      for (const session of result.data.sessions) {
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
      if (!selectedSaveId && saveList.length > 0) {
        setSelectedSaveId(saveList[0].save_id)
      }
    }
    setSavesLoading(false)
  }, [backend, selectedSaveId])

  // Load chronicle for selected save
  const loadChronicle = useCallback(async (forceRefresh = false) => {
    if (!selectedSaveId) return

    // Find a session for this save to use as session_id
    const result = await backend.sessions()
    if (!isMountedRef.current) return

    if (!result.data) {
      setError('Failed to load sessions')
      return
    }

    // Find session matching this save_id
    const session = result.data.sessions.find(
      s => s.save_id === selectedSaveId
    )

    if (!session) {
      setError('No session found for this save')
      return
    }

    setLoading(true)
    setError(null)

    const chronicleResult = await backend.chronicle(session.id, forceRefresh)

    if (!isMountedRef.current) return

    if (chronicleResult.error) {
      setError(chronicleResult.error)
      setChronicle(null)
    } else if (chronicleResult.data) {
      setChronicle(chronicleResult.data)
      // Select most recent chapter by default, or current era if no chapters
      if (chronicleResult.data.chapters.length > 0) {
        setSelectedChapter(chronicleResult.data.chapters.length)
      } else {
        setSelectedChapter(null)
      }
    }

    setLoading(false)
  }, [backend, selectedSaveId])

  // Initial load
  useEffect(() => {
    isMountedRef.current = true
    loadSaves()
    return () => {
      isMountedRef.current = false
    }
  }, [loadSaves])

  // Load chronicle when save changes
  useEffect(() => {
    if (selectedSaveId) {
      loadChronicle()
    }
  }, [selectedSaveId, loadChronicle])

  // Handle chapter selection
  const handleSelectChapter = useCallback((chapterNumber: number | null) => {
    setSelectedChapter(chapterNumber)
  }, [])

  // Handle save/game change
  const handleSelectSave = useCallback((saveId: string) => {
    setSelectedSaveId(saveId)
    setChronicle(null)
    setSelectedChapter(null)
  }, [])

  // Handle refresh (generate more chapters)
  const handleRefresh = useCallback(() => {
    loadChronicle(true)
  }, [loadChronicle])

  // Handle chapter regeneration
  const handleRegenerateChapter = useCallback(async (chapterNumber: number) => {
    if (confirmRegen !== chapterNumber) {
      // First click - show confirmation
      setConfirmRegen(chapterNumber)
      return
    }

    // Second click - do the regeneration
    setConfirmRegen(null)
    setRegenerating(true)

    // Find session for this save
    const sessionsResult = await backend.sessions()
    if (!isMountedRef.current) return

    const session = sessionsResult.data?.sessions.find(
      s => s.save_id === selectedSaveId
    )

    if (!session) {
      setError('Session not found')
      setRegenerating(false)
      return
    }

    const result = await backend.regenerateChapter(session.id, chapterNumber, true)

    if (!isMountedRef.current) return

    if (result.error) {
      setError(result.error)
    } else {
      // Reload chronicle to get updated chapters
      await loadChronicle()
    }

    setRegenerating(false)
  }, [backend, selectedSaveId, confirmRegen, loadChronicle])

  // Cancel regeneration confirmation
  const handleCancelRegen = useCallback(() => {
    setConfirmRegen(null)
  }, [])

  // Get current display content
  const getDisplayContent = (): { chapter: ChronicleChapter | null; currentEra: CurrentEra | null } => {
    if (!chronicle) return { chapter: null, currentEra: null }

    if (selectedChapter === null || selectedChapter === 0) {
      // Show current era
      return { chapter: null, currentEra: chronicle.current_era }
    }

    const chapter = chronicle.chapters.find(c => c.number === selectedChapter)
    return { chapter: chapter || null, currentEra: null }
  }

  const { chapter, currentEra } = getDisplayContent()

  // Get empire name for header
  const empireName = saves.find(s => s.save_id === selectedSaveId)?.empire_name || 'Unknown Empire'

  return (
    <div className="chronicle-page">
      <div className="chronicle-layout">
        {/* Left sidebar */}
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
          onRefresh={handleRefresh}
        />

        {/* Right content panel */}
        <div className="chronicle-main">
          {error && (
            <div className="chronicle-error">
              <p>{error}</p>
              <button onClick={() => setError(null)}>Dismiss</button>
            </div>
          )}

          {savesLoading ? (
            <div className="chronicle-loading">
              <div className="loading-spinner" />
              <p>Loading saves...</p>
            </div>
          ) : loading && !chronicle ? (
            <div className="chronicle-loading">
              <div className="loading-spinner" />
              <p>Loading chronicle...</p>
            </div>
          ) : chronicle ? (
            <ChronicleContent
              empireName={empireName}
              chapter={chapter}
              currentEra={currentEra}
              onRegenerate={handleRegenerateChapter}
              confirmingRegen={confirmRegen}
              onCancelRegen={handleCancelRegen}
              regenerating={regenerating}
            />
          ) : (
            <div className="chronicle-empty">
              <h2>No Chronicle Yet</h2>
              <p>
                Play your game and accumulate history. Chronicles are generated
                automatically as your empire progresses through the ages.
              </p>
              {saves.length === 0 && (
                <p className="chronicle-empty-hint">
                  Start by loading a save file in Stellaris.
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default ChroniclePage
