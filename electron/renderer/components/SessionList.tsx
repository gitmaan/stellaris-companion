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
      <div className="flex-1 overflow-y-auto p-2 flex items-center justify-center py-6 px-4">
        <p className="text-text-secondary text-sm text-center leading-relaxed">No sessions found. Play some Stellaris to create sessions!</p>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto p-2">
      {sessions.map((session) => (
        <div
          key={session.id}
          className={`p-3 mb-1 rounded-lg cursor-pointer transition-colors duration-200 border border-transparent ${
            selectedId === session.id
              ? 'bg-bg-tertiary border-accent-blue'
              : 'hover:bg-bg-tertiary'
          }`}
          onClick={() => onSelect(session)}
        >
          <div className="flex justify-between items-center mb-1">
            <span className="text-sm font-medium text-text-primary">{session.empire_name}</span>
            {session.is_active && (
              <span className="text-[11px] font-semibold uppercase text-accent-green bg-accent-green/15 py-0.5 px-1.5 rounded">Active</span>
            )}
          </div>
          <div className="text-xs text-text-secondary mb-1">
            {session.first_game_date} - {session.last_game_date}
          </div>
          <div className="text-[11px] text-text-secondary opacity-80">
            <span>{session.snapshot_count} snapshots</span>
          </div>
        </div>
      ))}
    </div>
  )
}

export default SessionList
