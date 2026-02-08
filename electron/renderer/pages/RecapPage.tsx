import { useState, useEffect, useCallback, useRef } from 'react'
import SessionList from '../components/SessionList'
import RecapViewer from '../components/RecapViewer'
import { useBackend, Session, RecapResponse } from '../hooks/useBackend'

/**
 * RecapPage - Session history and recap generation interface
 *
 * Implements UI-005 criteria:
 * - SessionList shows all sessions with selection
 * - Selected session shows details (dates, snapshot count)
 * - Generate Recap button calls API and shows result
 * - RecapViewer renders markdown
 * - End Current Session button works
 */
function RecapPage() {
  const backend = useBackend()

  // Track mounted state to prevent state updates after unmount
  const isMountedRef = useRef(true)

  // Session list state
  const [sessions, setSessions] = useState<Session[]>([])
  const [sessionsLoading, setSessionsLoading] = useState(true)
  const [sessionsError, setSessionsError] = useState<string | null>(null)

  // Selection state
  const [selectedSession, setSelectedSession] = useState<Session | null>(null)

  // Recap state
  const [recapData, setRecapData] = useState<RecapResponse | null>(null)
  const [recapLoading, setRecapLoading] = useState(false)
  const [recapError, setRecapError] = useState<string | null>(null)

  // End session state
  const [endingSession, setEndingSession] = useState(false)
  const [endSessionMessage, setEndSessionMessage] = useState<string | null>(null)

  // Load sessions with unmount guard
  const loadSessions = useCallback(async () => {
    setSessionsLoading(true)
    setSessionsError(null)

    const result = await backend.sessions()

    // Only update state if component is still mounted
    if (!isMountedRef.current) return

    if (result.error) {
      setSessionsError(result.error)
      setSessions([])
    } else if (result.data) {
      setSessions(result.data.sessions)
    }

    setSessionsLoading(false)
  }, [backend])

  // Load sessions on mount, cleanup on unmount
  useEffect(() => {
    isMountedRef.current = true
    loadSessions()

    return () => {
      isMountedRef.current = false
    }
  }, [loadSessions])

  // Handle session selection
  const handleSelectSession = useCallback((session: Session) => {
    setSelectedSession(session)
    // Clear previous recap when selecting new session
    setRecapData(null)
    setRecapError(null)
  }, [])

  // Generate recap for selected session with unmount guard
  const handleGenerateRecap = useCallback(async () => {
    if (!selectedSession) return

    setRecapLoading(true)
    setRecapError(null)

    const result = await backend.recap(selectedSession.id)

    // Only update state if component is still mounted
    if (!isMountedRef.current) return

    if (result.error) {
      setRecapError(result.error)
      setRecapData(null)
    } else if (result.data) {
      setRecapData(result.data)
    }

    setRecapLoading(false)
  }, [backend, selectedSession])

  // End current session with unmount guard
  const handleEndSession = useCallback(async () => {
    setEndingSession(true)
    setEndSessionMessage(null)

    const result = await backend.endSession()

    // Only update state if component is still mounted
    if (!isMountedRef.current) return

    if (result.error) {
      setEndSessionMessage(`Error: ${result.error}`)
    } else if (result.data) {
      setEndSessionMessage(`Session ended successfully (${result.data.snapshot_count} snapshots saved)`)
      // Refresh the sessions list
      await loadSessions()
      // Clear selection if the ended session was selected
      if (selectedSession?.is_active) {
        setSelectedSession(null)
        setRecapData(null)
      }
    }

    setEndingSession(false)
  }, [backend, loadSessions, selectedSession])

  // Check if there's an active session
  const hasActiveSession = sessions.some(s => s.is_active)

  return (
    <div className="h-full bg-bg-primary">
      <div className="flex h-full">
        {/* Left panel: Session list */}
        <div className="w-[280px] flex-shrink-0 flex flex-col bg-bg-secondary border-r border-border">
          <div className="flex justify-between items-center p-4 border-b border-border">
            <h2 className="text-base font-semibold text-text-primary m-0">Sessions</h2>
            <button
              className="w-8 h-8 border border-border rounded-md bg-bg-tertiary text-text-primary text-base cursor-pointer flex items-center justify-center transition-all duration-200 hover:bg-bg-primary hover:border-accent-blue disabled:opacity-50 disabled:cursor-not-allowed"
              onClick={loadSessions}
              disabled={sessionsLoading}
              title="Refresh sessions"
            >
              {sessionsLoading ? '...' : '↻'}
            </button>
          </div>

          {sessionsError && (
            <div className="mx-4 my-4 p-3 bg-accent-red/15 border border-accent-red rounded-md text-accent-red text-[13px]">
              {sessionsError}
            </div>
          )}

          {sessionsLoading && sessions.length === 0 ? (
            <div className="py-6 px-4 text-center text-text-secondary text-sm">Loading sessions...</div>
          ) : (
            <SessionList
              sessions={sessions}
              selectedId={selectedSession?.id}
              onSelect={handleSelectSession}
            />
          )}

          {/* End session button */}
          {hasActiveSession && (
            <div className="p-4 border-t border-border">
              <button
                className="w-full py-2.5 px-4 border border-accent-yellow rounded-md bg-accent-yellow/10 text-accent-yellow text-[13px] font-medium cursor-pointer transition-colors duration-200 hover:bg-accent-yellow/20 disabled:opacity-50 disabled:cursor-not-allowed"
                onClick={handleEndSession}
                disabled={endingSession}
              >
                {endingSession ? 'Ending...' : 'End Current Session'}
              </button>
              {endSessionMessage && (
                <p className={`mt-2 text-xs text-center ${endSessionMessage.startsWith('Error') ? 'text-accent-red' : 'text-accent-green'}`}>
                  {endSessionMessage}
                </p>
              )}
            </div>
          )}
        </div>

        {/* Right panel: Session details and recap */}
        <div className="flex-1 flex flex-col overflow-hidden p-6">
          {selectedSession ? (
            <>
              {/* Session details header */}
              <div className="bg-bg-secondary border border-border rounded-lg p-5 mb-4">
                <div className="flex items-center gap-3 mb-4">
                  <h2 className="text-xl font-semibold text-text-primary m-0">{selectedSession.empire_name}</h2>
                  {selectedSession.is_active && (
                    <span className="text-xs font-semibold uppercase text-accent-green bg-accent-green/15 py-1 px-2 rounded">Active</span>
                  )}
                </div>
                <div className="flex flex-col gap-2 mb-4">
                  <div className="flex text-sm">
                    <span className="text-text-secondary w-[100px] flex-shrink-0">Date Range:</span>
                    <span className="text-text-primary">
                      {selectedSession.first_game_date} → {selectedSession.last_game_date}
                    </span>
                  </div>
                  <div className="flex text-sm">
                    <span className="text-text-secondary w-[100px] flex-shrink-0">Snapshots:</span>
                    <span className="text-text-primary">{selectedSession.snapshot_count}</span>
                  </div>
                  <div className="flex text-sm">
                    <span className="text-text-secondary w-[100px] flex-shrink-0">Session ID:</span>
                    <span className="text-text-secondary font-mono text-xs">{selectedSession.id}</span>
                  </div>
                </div>
                <button
                  className="py-2.5 px-5 border-none rounded-md bg-accent-blue text-white text-sm font-medium cursor-pointer transition-all duration-200 hover:bg-accent-blue-hover disabled:opacity-50 disabled:cursor-not-allowed"
                  onClick={handleGenerateRecap}
                  disabled={recapLoading}
                >
                  {recapLoading ? 'Generating...' : 'Generate Recap'}
                </button>
              </div>

              {/* Recap content */}
              {recapError && (
                <div className="bg-accent-red/15 border border-accent-red rounded-lg px-4 py-3 mb-4 text-accent-red text-sm">
                  {recapError}
                </div>
              )}

              <RecapViewer
                recap={recapData?.recap ?? null}
                loading={recapLoading}
                dateRange={recapData?.date_range}
                eventsSummarized={recapData?.events_summarized}
              />
            </>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-center text-text-secondary">
              <h3 className="text-text-primary text-lg mb-2">No Session Selected</h3>
              <p className="text-sm">Select a session from the list to view details and generate a recap.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default RecapPage
