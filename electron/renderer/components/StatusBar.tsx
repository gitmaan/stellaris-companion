import { useState, useEffect } from 'react'
import { BackendStatusEvent } from '../hooks/useBackend'

type ConnectionStatus = 'ready' | 'analyzing' | 'connecting' | 'no-save' | 'not-configured' | 'disconnected'

interface StatusState {
  connectionStatus: ConnectionStatus
  empireName: string | null
  gameDate: string | null
  stage: string | null
}

function getConnectionStatus(payload: BackendStatusEvent | null): ConnectionStatus {
  if (!payload) return 'disconnected'

  if (payload.connected === false) {
    return payload.backend_configured ? 'disconnected' : 'not-configured'
  }

  // If connected is not explicitly set, fall back to /api/health status fields.
  const healthy = payload.status === 'healthy' || payload.status === 'ok'
  if (!healthy) return 'disconnected'

  if (!payload.save_loaded) return 'no-save'
  return payload.precompute_ready ? 'ready' : 'analyzing'
}

function getStatusLabel(status: ConnectionStatus, stage: string | null): string {
  switch (status) {
    case 'ready':
      return 'Ready'
    case 'analyzing':
      return stage ? `Analyzing (${stage})…` : 'Analyzing save…'
    case 'connecting':
      return 'Connecting...'
    case 'no-save':
      return 'Awaiting First Contact'
    case 'not-configured':
      return 'Not configured'
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
    stage: null,
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
      const stage = health?.ingestion?.stage ?? null
      setState({
        connectionStatus: getConnectionStatus(health),
        empireName: health?.empire_name ?? null,
        gameDate: health?.game_date ?? null,
        stage,
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
  const statusLabel = getStatusLabel(state.connectionStatus, state.stage)

  return (
    <div className="status-bar title-bar-drag-region">
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
