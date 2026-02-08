import { useEffect, useMemo } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import type { Announcement } from '../hooks/useBackend'

const SEVERITY_PRIORITY: Record<Announcement['severity'], number> = {
  known_issue: 5,
  warning: 4,
  update: 3,
  tip: 2,
  info: 1,
}

const SEVERITY_CONFIG: Record<
  Announcement['severity'],
  { icon: string; label: string; text: string; bg: string; border: string }
> = {
  info: {
    icon: '\u25C7', // ◇
    label: 'INFO',
    text: 'text-accent-cyan',
    bg: 'bg-accent-cyan/10',
    border: 'border-accent-cyan/30',
  },
  warning: {
    icon: '\u26A0', // ⚠
    label: 'WARNING',
    text: 'text-accent-yellow',
    bg: 'bg-accent-yellow/10',
    border: 'border-accent-yellow/30',
  },
  known_issue: {
    icon: '\u25C8', // ◈
    label: 'KNOWN ISSUE',
    text: 'text-accent-orange',
    bg: 'bg-accent-orange/10',
    border: 'border-accent-orange/30',
  },
  update: {
    icon: '\u2191', // ↑
    label: 'UPDATE',
    text: 'text-accent-green',
    bg: 'bg-accent-green/10',
    border: 'border-accent-green/30',
  },
  tip: {
    icon: '\u2605', // ★
    label: 'TIP',
    text: 'text-accent-purple',
    bg: 'bg-accent-purple/10',
    border: 'border-accent-purple/30',
  },
}

function sortAnnouncements(items: Announcement[]): Announcement[] {
  return [...items].sort((a, b) => {
    const severityDelta = SEVERITY_PRIORITY[b.severity] - SEVERITY_PRIORITY[a.severity]
    if (severityDelta !== 0) return severityDelta

    const aPublished = new Date(a.publishedAt).getTime()
    const bPublished = new Date(b.publishedAt).getTime()
    return bPublished - aPublished
  })
}

function formatPublishedDate(dateValue: string): string {
  const ts = new Date(dateValue).getTime()
  if (!Number.isFinite(ts)) return 'Unknown date'
  return new Date(ts).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
  })
}

interface AnnouncementCardProps {
  announcement: Announcement
  onDismiss: (id: string) => void
}

function AnnouncementCard({
  announcement,
  onDismiss,
}: AnnouncementCardProps) {
  const config = SEVERITY_CONFIG[announcement.severity] || SEVERITY_CONFIG.info

  return (
    <div className={`relative p-3 border rounded-sm ${config.border} ${config.bg}`}>
      <div className="absolute top-0 left-0 w-2 h-2 border-t border-l border-white/20 pointer-events-none" />
      <div className="absolute top-0 right-0 w-2 h-2 border-t border-r border-white/20 pointer-events-none" />
      <div className="absolute bottom-0 left-0 w-2 h-2 border-b border-l border-white/20 pointer-events-none" />
      <div className="absolute bottom-0 right-0 w-2 h-2 border-b border-r border-white/20 pointer-events-none" />

      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="mb-1.5 flex items-center gap-2">
            <span className={`${config.text} text-xs`}>{config.icon}</span>
            <span className={`${config.text} font-mono text-[10px] tracking-[0.14em] uppercase`}>
              {config.label}
            </span>
            <span className="font-mono text-[10px] tracking-[0.12em] text-text-muted uppercase">
              {formatPublishedDate(announcement.publishedAt)}
            </span>
          </div>

          <h4 className="font-display text-sm text-text-primary tracking-wide mb-1">
            {announcement.title}
          </h4>
          <p className="font-mono text-xs text-text-secondary leading-relaxed">
            {announcement.body}
          </p>

          {announcement.link && (
            <a
              href={announcement.link.url}
              target="_blank"
              rel="noopener noreferrer"
              className={`inline-flex items-center gap-1 mt-2 font-mono text-xs ${config.text} hover:underline`}
            >
              {announcement.link.label}
              <span className="text-[10px]">&rarr;</span>
            </a>
          )}
        </div>

        <button
          onClick={() => onDismiss(announcement.id)}
          className="flex-none px-2 py-1 border border-white/20 rounded-sm font-mono text-[10px] tracking-[0.12em] uppercase text-text-secondary hover:text-text-primary hover:border-white/40 transition-colors"
        >
          Dismiss
        </button>
      </div>
    </div>
  )
}

interface AnnouncementPanelProps {
  announcements: Announcement[]
  unreadCount: number
  isOpen: boolean
  onClose: () => void
  onDismiss: (id: string) => void
  onDismissAll: (ids: string[]) => void
  onMarkRead: () => void
}

export function AnnouncementPanel({
  announcements,
  unreadCount,
  isOpen,
  onClose,
  onDismiss,
  onDismissAll,
  onMarkRead,
}: AnnouncementPanelProps) {
  const reduceMotion = useReducedMotion()

  const activeItems = useMemo(() => sortAnnouncements(announcements), [announcements])
  if (activeItems.length === 0) return null

  useEffect(() => {
    if (!isOpen) return

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }

    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [isOpen, onClose])

  const panelTransition = reduceMotion
    ? { duration: 0 }
    : { duration: 0.2, ease: [0.25, 0.46, 0.45, 0.94] as const }

  const cardReveal = (idx: number) => {
    if (reduceMotion || idx > 2) {
      return {
        initial: { opacity: 1, y: 0 },
        animate: { opacity: 1, y: 0 },
        transition: { duration: 0 },
      }
    }
    return {
      initial: { opacity: 0, y: -4 },
      animate: { opacity: 1, y: 0 },
      transition: { duration: 0.16, delay: idx * 0.045, ease: [0.25, 0.46, 0.45, 0.94] as const },
    }
  }

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={reduceMotion ? { opacity: 1, y: 0, scale: 1 } : { opacity: 0, y: -8, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={reduceMotion ? { opacity: 1, y: 0, scale: 1 } : { opacity: 0, y: -8, scale: 0.98 }}
          transition={panelTransition}
          className="origin-top-right will-change-transform w-full rounded-sm border border-white/15 bg-black/80 backdrop-blur-md shadow-[0_0_24px_rgba(0,0,0,0.6)]"
        >
          <div className="flex items-center justify-between border-b border-white/10 px-3 py-2">
            <div className="flex items-center gap-2">
              <span className="text-accent-cyan text-xs">{'\u25C8'}</span>
              <span className="font-mono text-[11px] tracking-[0.16em] text-text-secondary uppercase">
                Transmissions
              </span>
              {unreadCount > 0 && (
                <span className="px-1.5 py-0.5 bg-accent-cyan/20 border border-accent-cyan/30 rounded-sm font-mono text-[10px] text-accent-cyan tracking-wider">
                  {unreadCount} NEW
                </span>
              )}
            </div>

            <button
              onClick={onClose}
              className="px-2 py-1 border border-white/20 rounded-sm font-mono text-[10px] tracking-[0.12em] uppercase text-text-secondary hover:text-text-primary hover:border-white/40 transition-colors"
            >
              Close
            </button>
          </div>

          <div className="flex flex-wrap items-center gap-2 border-b border-white/10 px-3 py-2">
            {unreadCount > 0 && (
              <button
                onClick={onMarkRead}
                className="px-2.5 py-1 border border-white/20 rounded-sm font-mono text-[10px] tracking-[0.12em] uppercase text-text-secondary hover:text-text-primary hover:border-white/40 transition-colors"
              >
                Mark all read
              </button>
            )}
            {activeItems.length > 0 && (
              <button
                onClick={() => onDismissAll(activeItems.map((item) => item.id))}
                className="px-2.5 py-1 border border-white/20 rounded-sm font-mono text-[10px] tracking-[0.12em] uppercase text-text-secondary hover:text-text-primary hover:border-white/40 transition-colors"
              >
                Dismiss all
              </button>
            )}
          </div>

          <div className="max-h-[60vh] overflow-y-auto custom-scrollbar p-3 space-y-3">
            <div className="space-y-2">
              <div className="font-mono text-[10px] text-text-muted tracking-[0.14em] uppercase">
                Active transmissions ({activeItems.length})
              </div>
              {activeItems.length > 0 ? (
                activeItems.map((announcement, idx) => (
                  <motion.div
                    key={announcement.id}
                    initial={cardReveal(idx).initial}
                    animate={cardReveal(idx).animate}
                    transition={cardReveal(idx).transition}
                  >
                    <AnnouncementCard
                      announcement={announcement}
                      onDismiss={onDismiss}
                    />
                  </motion.div>
                ))
              ) : (
                <div className="p-3 border border-white/10 rounded-sm bg-black/30">
                  <p className="font-mono text-xs text-text-muted uppercase tracking-[0.12em]">
                    No active transmissions.
                  </p>
                </div>
              )}
            </div>

          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
