import React, { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { BackendStatusEvent } from '../../hooks/useBackend'
import { HUDLabel, HUDValue } from './HUDText'

type ConnectionStatus = 'ready' | 'warning' | 'analyzing' | 'connecting' | 'no-save' | 'not-configured' | 'disconnected'

interface StatusState {
  connectionStatus: ConnectionStatus
  empireName: string | null
  gameDate: string | null
  stage: string | null
  error: string | null
}

function getConnectionStatus(payload: BackendStatusEvent | null): ConnectionStatus {
  if (!payload) return 'disconnected'

  if (payload.connected === false) {
    return payload.backend_configured ? 'disconnected' : 'not-configured'
  }

  const healthy = payload.status === 'healthy' || payload.status === 'ok'
  if (!healthy) return 'disconnected'

  if (!payload.save_loaded) return 'no-save'
  if (payload.precompute_ready && payload.ingestion?.last_error) return 'warning'
  return payload.precompute_ready ? 'ready' : 'analyzing'
}

function getStageLabel(
  stage: string | null,
  t: (key: string, options?: Record<string, unknown>) => string,
): string | null {
  if (!stage) return null
  const stageKey = stage.replace(/-/g, '_')
  return t(`status.stages.${stageKey}`, { defaultValue: '' }) || null
}

function getStatusLabel(status: ConnectionStatus, stage: string | null, t: (key: string, options?: Record<string, unknown>) => string): string {
  switch (status) {
    case 'ready': return t('status.ready')
    case 'warning': return t('status.historyNotSaved')
    case 'analyzing': {
      const label = getStageLabel(stage, t)
      return label ? t('status.analyzingWithStage', { stage: label }) : t('status.analyzing')
    }
    case 'connecting': return t('status.connecting')
    case 'no-save': return t('status.noSave')
    case 'not-configured': return t('status.notConfigured')
    case 'disconnected': return t('status.disconnected')
  }
}

const statusColors: Record<ConnectionStatus, string> = {
  ready: 'text-accent-green',
  warning: 'text-accent-yellow',
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
  const { t } = useTranslation()
  const [state, setState] = useState<StatusState>({
    connectionStatus: 'connecting',
    empireName: null,
    gameDate: null,
    stage: null,
    error: null,
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
        error: health?.ingestion?.last_error ?? null,
      })
    })

    return () => {
      if (typeof cleanup === 'function') cleanup()
    }
  }, [])

  const statusColor = statusColors[state.connectionStatus]
  const statusLabel = getStatusLabel(state.connectionStatus, state.stage, t)

  return (
    <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] items-center gap-4 px-6 h-12 title-bar-drag-region status-bar z-50 pointer-events-none">
      {/* Left: Empire Info */}
      <div className="flex min-w-0 items-center gap-3 pointer-events-auto">
        <div className="w-2 h-2 shrink-0 bg-accent-cyan rounded-full shadow-glow-sm" />
        <h2 title={state.empireName ?? t('status.unknownEmpire')} className="truncate font-display font-bold text-sm tracking-wide text-text-primary uppercase">
          {state.empireName ?? t('status.unknownEmpire')}
        </h2>
        {state.gameDate && (
          <>
            <span className="w-4 h-px shrink-0 bg-white/30" />
            <HUDValue className="text-xs text-text-secondary whitespace-nowrap tabular-nums">{state.gameDate}</HUDValue>
          </>
        )}
      </div>

      {/* Right: Status */}
      <div className="flex min-w-0 items-center justify-end gap-2 pointer-events-auto" title={state.error ?? statusLabel}>
        {onToggleTransmissions && transmissionsTotal > 0 && (
          <button
            onClick={onToggleTransmissions}
            className={`mr-3 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-sm border transition-colors ${
              transmissionsOpen
                ? 'border-accent-cyan/50 bg-accent-cyan/10 text-accent-cyan'
                : 'border-white/15 bg-black/30 text-text-secondary hover:text-text-primary hover:border-white/35'
            }`}
            title={t('announcements.title')}
            aria-label={t('announcements.title')}
            aria-expanded={transmissionsOpen}
          >
            <span className="text-[10px]">{'\u25C8'}</span>
            <span className="hidden xl:inline font-mono text-[10px] tracking-[0.14em] uppercase">
              {t('announcements.title')}
            </span>
            {transmissionsUnread > 0 && (
              <span className="w-1.5 h-1.5 rounded-full bg-accent-cyan shadow-glow-dot animate-pulse" />
            )}
          </button>
        )}
        <HUDLabel className={`${statusColor} truncate whitespace-nowrap transition-colors duration-150`}>
          {statusLabel}
        </HUDLabel>
        <div className={`w-1.5 h-1.5 shrink-0 rounded-full ${statusColor.replace('text-', 'bg-')} shadow-glow-sm`} />
      </div>
    </div>
  )
}
