import { Session } from '../hooks/useBackend'

interface SessionListProps {
  sessions: Session[]
  selectedId?: string
  onSelect: (session: Session) => void
}

/**
 * SessionList - Displays a list of game sessions with selection
 *
 * Shows empire name, date range, snapshot count, and active status for each session.
 * Selected session is visually highlighted.
 */
function SessionList({ sessions, selectedId, onSelect }: SessionListProps) {
  if (sessions.length === 0) {
    return (
      <div className="session-list empty">
        <p className="session-list-empty">No sessions found. Play some Stellaris to create sessions!</p>
      </div>
    )
  }

  return (
    <div className="session-list">
      {sessions.map((session) => (
        <div
          key={session.id}
          className={`session-item ${selectedId === session.id ? 'selected' : ''} ${session.is_active ? 'active' : ''}`}
          onClick={() => onSelect(session)}
        >
          <div className="session-item-header">
            <span className="session-empire">{session.empire_name}</span>
            {session.is_active && <span className="session-active-badge">Active</span>}
          </div>
          <div className="session-dates">
            {session.first_game_date} - {session.last_game_date}
          </div>
          <div className="session-meta">
            <span className="session-snapshots">{session.snapshot_count} snapshots</span>
          </div>
        </div>
      ))}
    </div>
  )
}

export default SessionList
