import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
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

const STAGE_LABELS: Record<string, string> = {
  waiting_for_stable_save: 'detecting save',
  parsing_t0: 'reading save',
  precomputing_t2: 'analyzing',
  persisting: 'saving',
}

function getStatusLabel(status: ConnectionStatus, stage: string | null): string {
  switch (status) {
    case 'ready':
      return 'Systems Online'
    case 'analyzing': {
      const label = stage ? STAGE_LABELS[stage] : null
      return label ? `Surveying (${label})…` : 'Surveying Empire…'
    }
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

// Status indicator colors with glow effects
const statusColors: Record<ConnectionStatus, { text: string; bg: string; glow: string }> = {
  ready: {
    text: 'text-accent-green',
    bg: 'bg-accent-green',
    glow: 'shadow-[0_0_8px_rgba(72,187,120,0.6)]',
  },
  analyzing: {
    text: 'text-accent-yellow',
    bg: 'bg-accent-yellow',
    glow: 'shadow-[0_0_8px_rgba(236,201,75,0.6)]',
  },
  connecting: {
    text: 'text-accent-yellow',
    bg: 'bg-accent-yellow',
    glow: 'shadow-[0_0_8px_rgba(236,201,75,0.6)]',
  },
  'no-save': {
    text: 'text-accent-cyan',
    bg: 'bg-accent-cyan',
    glow: 'shadow-[0_0_8px_rgba(0,212,255,0.6)]',
  },
  'not-configured': {
    text: 'text-accent-orange',
    bg: 'bg-accent-orange',
    glow: 'shadow-[0_0_8px_rgba(237,137,54,0.6)]',
  },
  disconnected: {
    text: 'text-accent-red',
    bg: 'bg-accent-red',
    glow: 'shadow-[0_0_8px_rgba(252,129,129,0.6)]',
  },
}

/**
 * StatusBar - Displays empire name, game date, and backend connection status
 * Stellaris-themed with energy glow effects
 */
function StatusBar() {
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
      if (typeof cleanup === 'function') {
        cleanup()
      }
    }
  }, [])

  const colors = statusColors[state.connectionStatus]
  const statusLabel = getStatusLabel(state.connectionStatus, state.stage)
  const isAnimating = state.connectionStatus === 'analyzing' || state.connectionStatus === 'connecting'

  return (
    <div className="status-bar flex justify-between items-center px-4 py-2.5 bg-bg-secondary/90 backdrop-blur-sm border-b border-border min-h-[44px] title-bar-drag-region relative">
      {/* Subtle top glow */}
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-border-glow/20 to-transparent" />

      <div className="flex items-center gap-4">
        {/* Empire indicator dot */}
        <div className="flex items-center gap-2">
          <span className="text-accent-cyan text-lg">◆</span>
          <AnimatePresence mode="wait">
            <motion.span
              key={state.empireName ?? 'no-save'}
              className="font-semibold text-text-primary tracking-wide"
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 8 }}
              transition={{ duration: 0.15 }}
            >
              {state.empireName ?? 'No save loaded'}
            </motion.span>
          </AnimatePresence>
        </div>

        <AnimatePresence>
          {state.gameDate && (
            <motion.span
              className="text-text-secondary text-sm font-mono px-2 py-0.5 rounded bg-bg-tertiary/50 border border-border/50"
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9 }}
              transition={{ duration: 0.15 }}
            >
              {state.gameDate}
            </motion.span>
          )}
        </AnimatePresence>
      </div>

      <div className="flex items-center">
        <span className={`flex items-center gap-2 text-[13px] font-medium ${colors.text}`}>
          {/* Status indicator with glow */}
          <motion.span
            className={`w-2 h-2 rounded-full ${colors.bg} ${colors.glow}`}
            animate={{
              scale: isAnimating ? [1, 1.3, 1] : 1,
              opacity: isAnimating ? [1, 0.7, 1] : 1,
            }}
            transition={{
              duration: 1.5,
              repeat: isAnimating ? Infinity : 0,
              ease: 'easeInOut',
            }}
          />
          <AnimatePresence mode="wait">
            <motion.span
              key={statusLabel}
              className="uppercase tracking-wider text-xs"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.1 }}
            >
              {statusLabel}
            </motion.span>
          </AnimatePresence>
        </span>
      </div>
    </div>
  )
}

export default StatusBar
