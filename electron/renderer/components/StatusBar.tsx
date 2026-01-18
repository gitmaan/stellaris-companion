import { useState, useEffect, useCallback } from 'react'
import { useBackend, HealthResponse } from '../hooks/useBackend'

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
 * - Polls backend health every 5 seconds
 * - Listens to backend-status events from main process
 */
function StatusBar() {
  const backend = useBackend()
  const [state, setState] = useState<StatusState>({
    connectionStatus: 'connecting',
    empireName: null,
    gameDate: null,
  })

  const updateFromHealth = useCallback((health: HealthResponse | null, error: string | null) => {
    setState({
      connectionStatus: getConnectionStatus(health, error),
      empireName: health?.empire_name ?? null,
      gameDate: health?.game_date ?? null,
    })
  }, [])

  // Poll backend health every 5 seconds
  useEffect(() => {
    let mounted = true
    let timeoutId: ReturnType<typeof setTimeout> | null = null

    const checkHealth = async () => {
      const result = await backend.health()
      if (mounted) {
        updateFromHealth(result.data, result.error)
        // Schedule next check
        timeoutId = setTimeout(checkHealth, 5000)
      }
    }

    // Initial check
    checkHealth()

    return () => {
      mounted = false
      if (timeoutId) {
        clearTimeout(timeoutId)
      }
    }
  }, [backend, updateFromHealth])

  // Also listen to backend-status events from main process
  useEffect(() => {
    if (!window.electronAPI?.onBackendStatus) {
      return
    }

    const cleanup = window.electronAPI.onBackendStatus((health) => {
      updateFromHealth(health, null)
    })

    return cleanup
  }, [updateFromHealth])

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
