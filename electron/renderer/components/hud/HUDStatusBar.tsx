import React, { useState, useEffect } from 'react'
import { BackendStatusEvent } from '../../hooks/useBackend'
import { HUDLabel, HUDValue } from './HUDText'

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

  const healthy = payload.status === 'healthy' || payload.status === 'ok'
  if (!healthy) return 'disconnected'

  if (!payload.save_loaded) return 'no-save'
  return payload.precompute_ready ? 'ready' : 'analyzing'
}

const STAGE_LABELS: Record<string, string> = {
  waiting_for_stable_save: 'DETECTING SAVE',
  parsing_t0: 'READING SAVE',
  precomputing_t2: 'ANALYZING',
  persisting: 'SAVING',
}

function getStatusLabel(status: ConnectionStatus, stage: string | null): string {
  switch (status) {
    case 'ready': return 'SYSTEMS ONLINE'
    case 'analyzing': {
      const label = stage ? STAGE_LABELS[stage] : null
      return label ? `SURVEYING (${label})…` : 'SURVEYING EMPIRE…'
    }
    case 'connecting': return 'CONNECTING...'
    case 'no-save': return 'AWAITING LINK'
    case 'not-configured': return 'CONFIG REQUIRED'
    case 'disconnected': return 'OFFLINE'
  }
}

const statusColors: Record<ConnectionStatus, string> = {
  ready: 'text-accent-green',
  analyzing: 'text-accent-yellow',
  connecting: 'text-accent-yellow',
  'no-save': 'text-accent-cyan',
  'not-configured': 'text-accent-orange',
  disconnected: 'text-accent-red',
}

interface HUDStatusBarProps {
  transmissionsOpen?: boolean
  transmissionsTotal?: number
  transmissionsUnread?: number
  onToggleTransmissions?: () => void
}

export const HUDStatusBar: React.FC<HUDStatusBarProps> = ({
  transmissionsOpen = false,
  transmissionsTotal = 0,
  transmissionsUnread = 0,
  onToggleTransmissions,
}) => {
  const [state, setState] = useState<StatusState>({
    connectionStatus: 'connecting',
    empireName: null,
    gameDate: null,
    stage: null,
  })

  useEffect(() => {
    if (!window.electronAPI?.onBackendStatus) {
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

    return () => {
      if (typeof cleanup === 'function') cleanup()
    }
  }, [])

  const statusColor = statusColors[state.connectionStatus]
  const statusLabel = getStatusLabel(state.connectionStatus, state.stage)

  return (
    <div className="flex justify-between items-start px-6 pt-4 title-bar-drag-region status-bar z-50 pointer-events-none">
      {/* Left: Empire Info */}
      <div className="flex items-center gap-3 pointer-events-auto">
        <div className="w-2 h-2 bg-accent-cyan rounded-full shadow-glow-sm" />
        <h2 className="font-display font-bold text-sm tracking-wide text-text-primary uppercase">
          {state.empireName ?? 'UNKNOWN EMPIRE'}
        </h2>
        {state.gameDate && (
          <>
            <span className="w-4 h-px bg-white/30" />
            <HUDValue className="text-xs text-text-secondary">{state.gameDate}</HUDValue>
          </>
        )}
      </div>

      {/* Right: Status */}
      <div className="flex items-center gap-2 pointer-events-auto">
        {onToggleTransmissions && transmissionsTotal > 0 && (
          <button
            onClick={onToggleTransmissions}
            className={`mr-3 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-sm border transition-colors ${
              transmissionsOpen
                ? 'border-accent-cyan/50 bg-accent-cyan/10 text-accent-cyan'
                : 'border-white/15 bg-black/30 text-text-secondary hover:text-text-primary hover:border-white/35'
            }`}
            title="Transmissions"
          >
            <span className="text-[10px]">{'\u25C8'}</span>
            <span className="font-mono text-[10px] tracking-[0.14em] uppercase">
              Transmissions
            </span>
            {transmissionsUnread > 0 && (
              <span className="w-1.5 h-1.5 rounded-full bg-accent-cyan shadow-[0_0_6px_rgba(0,212,255,0.7)] animate-pulse" />
            )}
          </button>
        )}
        <HUDLabel className={`${statusColor} transition-colors duration-300`}>
          {statusLabel}
        </HUDLabel>
        <div className={`w-1.5 h-1.5 rounded-full ${statusColor.replace('text-', 'bg-')} shadow-glow-sm animate-pulse-slow`} />
      </div>
    </div>
  )
}
