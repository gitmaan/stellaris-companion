// useDiscord hook - DISC-015: Discord OAuth + relay state management
// Provides React hook for Discord connection status, OAuth flow, and relay state

import { useState, useEffect, useCallback } from 'react'
// Import types from useBackend where global Window interface is declared
import type { DiscordStatus, DiscordRelayStatus, DiscordConnectResult } from './useBackend'

// Re-export for consumers who just want the types
export type { DiscordStatus, DiscordRelayStatus, DiscordConnectResult }

export interface UseDiscordResult {
  // OAuth status
  status: DiscordStatus | null
  loading: boolean
  connecting: boolean
  error: string | null

  // Relay status
  relayStatus: DiscordRelayStatus | null

  // Actions
  connectDiscord: () => Promise<DiscordConnectResult>
  disconnectDiscord: () => Promise<void>
  refreshStatus: () => Promise<void>
}

/**
 * Hook for managing Discord OAuth connection and relay status.
 *
 * Usage:
 * ```tsx
 * const { status, relayStatus, connecting, connectDiscord, disconnectDiscord } = useDiscord()
 *
 * if (status?.connected) {
 *   // Show connected UI with username
 * } else {
 *   // Show "Connect with Discord" button
 * }
 * ```
 */
export function useDiscord(): UseDiscordResult {
  const [status, setStatus] = useState<DiscordStatus | null>(null)
  const [relayStatus, setRelayStatus] = useState<DiscordRelayStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [connecting, setConnecting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Fetch initial Discord status
  const fetchStatus = useCallback(async () => {
    if (!window.electronAPI?.discord) {
      setError('Discord API not available')
      setLoading(false)
      return
    }

    try {
      const discordStatus = await window.electronAPI.discord.status() as DiscordStatus
      setStatus(discordStatus)
      setError(null)

      // Also fetch relay status if connected
      if (discordStatus.connected) {
        try {
          const relay = await window.electronAPI.discord.relayStatus() as DiscordRelayStatus
          setRelayStatus(relay)
        } catch (e) {
          // Relay status fetch failure is non-critical
          console.warn('Failed to fetch relay status:', e)
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to get Discord status')
    } finally {
      setLoading(false)
    }
  }, [])

  // Initial load
  useEffect(() => {
    fetchStatus()
  }, [fetchStatus])

  // Listen for relay status updates from main process
  useEffect(() => {
    if (!window.electronAPI?.onDiscordRelayStatus) {
      return
    }

    const cleanup = window.electronAPI.onDiscordRelayStatus((newStatus: DiscordRelayStatus) => {
      setRelayStatus(newStatus)
    })

    return cleanup
  }, [])

  // Listen for auth required events (token expired)
  useEffect(() => {
    if (!window.electronAPI?.onDiscordAuthRequired) {
      return
    }

    const cleanup = window.electronAPI.onDiscordAuthRequired((_data: { reason: string }) => {
      // Token expired - update status to disconnected
      setStatus({ connected: false })
      setRelayStatus(null)
      setError('Discord session expired. Please reconnect.')
    })

    return cleanup
  }, [])

  // Connect to Discord via OAuth
  const connectDiscord = useCallback(async (): Promise<DiscordConnectResult> => {
    if (!window.electronAPI?.discord) {
      return { success: false, error: 'Discord API not available' }
    }

    setConnecting(true)
    setError(null)

    try {
      const result = await window.electronAPI.discord.connect() as DiscordConnectResult

      if (result.success) {
        // Update local status immediately
        setStatus({
          connected: true,
          userId: result.userId,
          username: result.username,
        })

        // Fetch full status (may include relay info now)
        await fetchStatus()
      } else {
        setError(result.error || 'Failed to connect to Discord')
      }

      return result
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : 'Failed to connect to Discord'
      setError(errorMsg)
      return { success: false, error: errorMsg }
    } finally {
      setConnecting(false)
    }
  }, [fetchStatus])

  // Disconnect from Discord
  const disconnectDiscord = useCallback(async (): Promise<void> => {
    if (!window.electronAPI?.discord) {
      return
    }

    try {
      await window.electronAPI.discord.disconnect()
      setStatus({ connected: false })
      setRelayStatus(null)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to disconnect from Discord')
    }
  }, [])

  return {
    status,
    loading,
    connecting,
    error,
    relayStatus,
    connectDiscord,
    disconnectDiscord,
    refreshStatus: fetchStatus,
  }
}

export default useDiscord
