import { useState, useEffect } from 'react'
import { HealthResponse } from '../hooks/useBackend'

type ConnectionStatus = 'connected' | 'connecting' | 'no-save' | 'disconnected'

interface StatusState {
  connectionStatus: ConnectionStatus
  empireName: string | null
  gameDate: string | null
}

function getConnectionStatus(health: HealthResponse | null, error: string | null): ConnectionStatus {
  if (error || !health) {
    return 'disconnected'
  }
  if (health.status === 'healthy' || health.status === 'ok') {
    return health.save_loaded ? 'connected' : 'no-save'
  }
  return 'disconnected'
}

function getStatusLabel(status: ConnectionStatus): string {
  switch (status) {
    case 'connected':
      return 'Connected'
    case 'connecting':
      return 'Connecting...'
    case 'no-save':
      return 'No Save'
    case 'disconnected':
      return 'Disconnected'
  }
}

/**
 * StatusBar - Displays empire name, game date, and backend connection status
 *
 * Implements UI-002:
 * - Shows empire name and game date when available
 * - Shows connection status (Connected, Connecting, No Save, Disconnected)
 * - Listens to backend-status events from main process (event-driven, no polling)
 */
function StatusBar() {
  const [state, setState] = useState<StatusState>({
    connectionStatus: 'connecting',
    empireName: null,
    gameDate: null,
  })

  // Listen to backend-status events from main process
  // Main process pushes updates when health changes - no polling needed
  // Empty dependency array to prevent listener re-subscription on re-renders
  useEffect(() => {
    if (!window.electronAPI?.onBackendStatus) {
      // Not running in Electron
      setState(prev => ({ ...prev, connectionStatus: 'disconnected' }))
      return
    }

    const cleanup = window.electronAPI.onBackendStatus((health) => {
      setState({
        connectionStatus: getConnectionStatus(health, null),
        empireName: health?.empire_name ?? null,
        gameDate: health?.game_date ?? null,
      })
    })

    // Ensure cleanup is always called
    return () => {
      if (typeof cleanup === 'function') {
        cleanup()
      }
    }
  }, []) // Empty deps - subscribe once on mount, cleanup on unmount

  const statusClass = `connection-status ${state.connectionStatus}`
  const statusLabel = getStatusLabel(state.connectionStatus)

  return (
    <div className="status-bar">
      <div className="status-bar-left">
        <span className="empire-name">
          {state.empireName ?? 'No save loaded'}
        </span>
        {state.gameDate && (
          <span className="game-date">{state.gameDate}</span>
        )}
      </div>
      <div className="status-bar-right">
        <span className={statusClass}>
          <span className="status-indicator" />
          {statusLabel}
        </span>
      </div>
    </div>
  )
}

export default StatusBar
