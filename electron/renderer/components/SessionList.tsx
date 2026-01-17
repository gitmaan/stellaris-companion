interface Session {
  id: string
  empire_name: string
  started_at: number
  ended_at: number | null
  first_game_date: string
  last_game_date: string
  snapshot_count: number
  is_active: boolean
}

interface SessionListProps {
  sessions: Session[]
  selectedId?: string
  onSelect: (session: Session) => void
}

function SessionList({ sessions, selectedId, onSelect }: SessionListProps) {
  return (
    <div className="session-list">
      {sessions.map((session) => (
        <div
          key={session.id}
          className={`session-item ${selectedId === session.id ? 'selected' : ''}`}
          onClick={() => onSelect(session)}
        >
          <div className="session-empire">{session.empire_name}</div>
          <div className="session-dates">
            {session.first_game_date} - {session.last_game_date}
          </div>
        </div>
      ))}
    </div>
  )
}

export default SessionList
