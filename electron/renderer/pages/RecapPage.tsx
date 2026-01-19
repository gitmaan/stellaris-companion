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
    <div className="recap-page">
      <div className="recap-layout">
        {/* Left panel: Session list */}
        <div className="recap-sidebar">
          <div className="sidebar-header">
            <h2>Sessions</h2>
            <button
              className="refresh-button"
              onClick={loadSessions}
              disabled={sessionsLoading}
              title="Refresh sessions"
            >
              {sessionsLoading ? '...' : '↻'}
            </button>
          </div>

          {sessionsError && (
            <div className="sessions-error">
              {sessionsError}
            </div>
          )}

          {sessionsLoading && sessions.length === 0 ? (
            <div className="sessions-loading">Loading sessions...</div>
          ) : (
            <SessionList
              sessions={sessions}
              selectedId={selectedSession?.id}
              onSelect={handleSelectSession}
            />
          )}

          {/* End session button */}
          {hasActiveSession && (
            <div className="end-session-section">
              <button
                className="end-session-button"
                onClick={handleEndSession}
                disabled={endingSession}
              >
                {endingSession ? 'Ending...' : 'End Current Session'}
              </button>
              {endSessionMessage && (
                <p className={`end-session-message ${endSessionMessage.startsWith('Error') ? 'error' : 'success'}`}>
                  {endSessionMessage}
                </p>
              )}
            </div>
          )}
        </div>

        {/* Right panel: Session details and recap */}
        <div className="recap-main">
          {selectedSession ? (
            <>
              {/* Session details header */}
              <div className="session-details">
                <div className="session-details-header">
                  <h2>{selectedSession.empire_name}</h2>
                  {selectedSession.is_active && (
                    <span className="session-active-indicator">Active</span>
                  )}
                </div>
                <div className="session-details-info">
                  <div className="detail-row">
                    <span className="detail-label">Date Range:</span>
                    <span className="detail-value">
                      {selectedSession.first_game_date} → {selectedSession.last_game_date}
                    </span>
                  </div>
                  <div className="detail-row">
                    <span className="detail-label">Snapshots:</span>
                    <span className="detail-value">{selectedSession.snapshot_count}</span>
                  </div>
                  <div className="detail-row">
                    <span className="detail-label">Session ID:</span>
                    <span className="detail-value session-id">{selectedSession.id}</span>
                  </div>
                </div>
                <button
                  className="generate-recap-button"
                  onClick={handleGenerateRecap}
                  disabled={recapLoading}
                >
                  {recapLoading ? 'Generating...' : 'Generate Recap'}
                </button>
              </div>

              {/* Recap content */}
              {recapError && (
                <div className="recap-error">
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
            <div className="no-session-selected">
              <h3>No Session Selected</h3>
              <p>Select a session from the list to view details and generate a recap.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default RecapPage
