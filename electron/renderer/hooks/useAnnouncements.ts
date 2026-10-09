import { useState, useEffect, useMemo, useCallback } from 'react'
import type { Announcement } from './useBackend'

function mergeUniqueIds(prev: string[], next: string[]): string[] {
  if (next.length === 0) return prev
  return Array.from(new Set([...prev, ...next]))
}

export interface UseAnnouncementsResult {
  announcements: Announcement[]
  dismissedAnnouncements: Announcement[]
  unreadCount: number
  dismissAnnouncement: (id: string) => void
  dismissAllAnnouncements: (ids?: string[]) => void
  restoreAnnouncement: (id: string) => void
  resetDismissedAnnouncements: () => void
  markAllRead: () => void
  refresh: () => void
  loading: boolean
}

export function useAnnouncements(): UseAnnouncementsResult {
  const [allAnnouncements, setAllAnnouncements] = useState<Announcement[]>([])
  const [dismissedIds, setDismissedIds] = useState<string[]>([])
  const [readIds, setReadIds] = useState<string[]>([])
  const [loading, setLoading] = useState(true)

  // Load initial state
  useEffect(() => {
    let cancelled = false
    const api = window.electronAPI
    if (!api?.announcements) {
      setLoading(false)
      return
    }

    const loadInitialState = async () => {
      try {
        const [dismissed, read] = await Promise.all([
          api.announcements.getDismissed(),
          api.announcements.getReadIds(),
        ])
        if (cancelled) return
        // Merge instead of replace to avoid race with local dismisses.
        setDismissedIds((prev) => mergeUniqueIds(prev, dismissed))
        setReadIds((prev) => mergeUniqueIds(prev, read))

        const announcements = await api.announcements.fetch(true)
        if (cancelled) return
        setAllAnnouncements(announcements)
      } catch {
        // Graceful degradation for IPC/network failures.
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    loadInitialState()

    return () => {
      cancelled = true
    }
  }, [])

  // Subscribe to push updates from main process
  useEffect(() => {
    const api = window.electronAPI
    if (!api?.onAnnouncementsUpdated) return

    const cleanup = api.onAnnouncementsUpdated((announcements) => {
      setAllAnnouncements(announcements)
    })

    return () => {
      if (typeof cleanup === 'function') cleanup()
    }
  }, [])

  // Filter out dismissed announcements
  const announcements = useMemo(() => {
    return allAnnouncements.filter((a) => !dismissedIds.includes(a.id))
  }, [allAnnouncements, dismissedIds])

  const dismissedAnnouncements = useMemo(() => {
    return allAnnouncements.filter((a) => dismissedIds.includes(a.id))
  }, [allAnnouncements, dismissedIds])

  // Publication time cannot tell us whether a delayed or cached item was seen.
  const unreadCount = useMemo(() => {
    const read = new Set(readIds)
    return announcements.filter((a) => !read.has(a.id)).length
  }, [announcements, readIds])

  const dismissAnnouncement = useCallback((id: string) => {
    setDismissedIds((prev) => mergeUniqueIds(prev, [id]))
    window.electronAPI?.announcements?.dismiss(id).catch(() => {})
  }, [])

  const dismissAllAnnouncements = useCallback((ids?: string[]) => {
    const targetIds = Array.isArray(ids) && ids.length > 0
      ? ids
      : announcements.map((a) => a.id)

    if (targetIds.length === 0) return

    setDismissedIds((prev) => mergeUniqueIds(prev, targetIds))

    const api = window.electronAPI?.announcements
    if (!api) return

    if (typeof api.dismissMany === 'function') {
      api.dismissMany(targetIds).catch(() => {})
      return
    }
    Promise.all(targetIds.map((id) => api.dismiss(id))).catch(() => {})
  }, [announcements])

  const restoreAnnouncement = useCallback((id: string) => {
    setDismissedIds((prev) => prev.filter((dismissedId) => dismissedId !== id))
    window.electronAPI?.announcements?.undismiss?.(id).catch(() => {})
  }, [])

  const resetDismissedAnnouncements = useCallback(() => {
    setDismissedIds([])
    window.electronAPI?.announcements?.resetDismissed?.().catch(() => {})
  }, [])

  const markAllRead = useCallback(() => {
    const ids = announcements.map((announcement) => announcement.id)
    window.electronAPI?.announcements?.markRead(ids).then((result) => {
      if (result.success) setReadIds((prev) => mergeUniqueIds(prev, result.readIds))
    }).catch(() => {})
  }, [announcements])

  const refresh = useCallback(() => {
    window.electronAPI?.announcements?.fetch(true).then((result) => {
      setAllAnnouncements(result)
    }).catch(() => {})
  }, [])

  return {
    announcements,
    dismissedAnnouncements,
    unreadCount,
    dismissAnnouncement,
    dismissAllAnnouncements,
    restoreAnnouncement,
    resetDismissedAnnouncements,
    markAllRead,
    refresh,
    loading,
  }
}
