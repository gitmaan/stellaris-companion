import { useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import { type Playthrough, useBackend } from '../hooks/useBackend'
import type { ChroniclePublicationSummary } from '../global'
import { useToast } from './Toast'

type HistoryAction = 'label' | 'trash' | 'restore' | 'reset' | 'undo-reset' | 'delete'

interface CampaignHistoryDialogProps {
  isOpen: boolean
  onClose: () => void
  playthroughs: Playthrough[]
  onChanged: (saveId: string, action: HistoryAction) => Promise<void>
}

function formatGameDate(value: string | null): string {
  return value?.trim() || '—'
}

function isEmptyStart(playthrough: Playthrough): boolean {
  return !playthrough.is_current
    && !playthrough.has_chronicle
    && playthrough.event_count === 0
    && playthrough.snapshot_count <= 1
}

function CampaignHistoryDialog({
  isOpen,
  onClose,
  playthroughs,
  onChanged,
}: CampaignHistoryDialogProps) {
  const { t } = useTranslation()
  const backend = useBackend()
  const { showToast } = useToast()
  const [tab, setTab] = useState<'active' | 'trash'>('active')
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [editingId, setEditingId] = useState<string | null>(null)
  const [label, setLabel] = useState('')
  const [workingId, setWorkingId] = useState<string | null>(null)
  const [confirmResetId, setConfirmResetId] = useState<string | null>(null)
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const [confirmRemovePublicationId, setConfirmRemovePublicationId] = useState<string | null>(null)
  const [publications, setPublications] = useState<ChroniclePublicationSummary[]>([])

  useEffect(() => {
    if (!isOpen) return
    setSelected(new Set())
    setEditingId(null)
    setConfirmResetId(null)
    setConfirmDeleteId(null)
    setConfirmRemovePublicationId(null)
    void window.electronAPI?.chroniclePublishing.list().then(result => {
      if (result.ok) setPublications(result.data)
    })
  }, [isOpen])

  useEffect(() => {
    if (!isOpen) return
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !workingId) onClose()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose, workingId])

  const publicationBySaveId = useMemo(
    () => new Map(publications.map(publication => [publication.saveId, publication])),
    [publications],
  )
  const visible = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase()
    return playthroughs.filter(playthrough => {
      if (tab === 'active' ? playthrough.is_trashed : !playthrough.is_trashed) return false
      if (!needle) return true
      return [playthrough.display_name, playthrough.empire_name, playthrough.save_id]
        .some(value => value?.toLocaleLowerCase().includes(needle))
    })
  }, [playthroughs, query, tab])
  const emptyStarts = useMemo(
    () => playthroughs.filter(playthrough => !playthrough.is_trashed && isEmptyStart(playthrough)),
    [playthroughs],
  )
  const orphanedPublications = useMemo(() => {
    const localSaveIds = new Set(playthroughs.map(playthrough => playthrough.save_id))
    return publications.filter(publication => (
      publication.state === 'published' && !localSaveIds.has(publication.saveId)
    ))
  }, [playthroughs, publications])

  const reportError = (message: string | null) => {
    showToast({
      type: 'error',
      message: message || t('chronicle.history.unknownError'),
      duration: 6000,
    })
  }

  const runMutation = async (
    playthrough: Playthrough,
    action: HistoryAction,
    operation: () => ReturnType<typeof backend.trashPlaythrough>,
  ) => {
    setWorkingId(playthrough.save_id)
    try {
      const result = await operation()
      if (result.error) {
        reportError(result.error)
        return false
      }
      await onChanged(playthrough.save_id, action)
      return true
    } finally {
      setWorkingId(null)
    }
  }

  const handleSaveLabel = async (playthrough: Playthrough) => {
    const succeeded = await runMutation(
      playthrough,
      'label',
      () => backend.setPlaythroughLabel(playthrough.save_id, label.trim() || null),
    )
    if (succeeded) {
      setEditingId(null)
      showToast({ type: 'success', message: t('chronicle.history.labelSaved') })
    }
  }

  const handleTrash = async (playthrough: Playthrough) => {
    const succeeded = await runMutation(
      playthrough,
      'trash',
      () => backend.trashPlaythrough(playthrough.save_id),
    )
    if (!succeeded) return
    setSelected(previous => {
      const next = new Set(previous)
      next.delete(playthrough.save_id)
      return next
    })
    showToast({
      type: 'info',
      message: t('chronicle.history.movedToTrash', { name: playthrough.display_name }),
      action: {
        label: t('chronicle.history.undo'),
        onClick: () => {
          void backend.restorePlaythrough(playthrough.save_id).then(async result => {
            if (result.error) return reportError(result.error)
            await onChanged(playthrough.save_id, 'restore')
          })
        },
      },
    })
  }

  const handleRestore = async (playthrough: Playthrough) => {
    const succeeded = await runMutation(
      playthrough,
      'restore',
      () => backend.restorePlaythrough(playthrough.save_id),
    )
    if (succeeded) {
      showToast({ type: 'success', message: t('chronicle.history.restored') })
    }
  }

  const handleReset = async (playthrough: Playthrough) => {
    if (confirmResetId !== playthrough.save_id) {
      setConfirmResetId(playthrough.save_id)
      return
    }
    setConfirmResetId(null)
    const succeeded = await runMutation(
      playthrough,
      'reset',
      () => backend.resetChronicle(playthrough.save_id),
    )
    if (!succeeded) return
    showToast({
      type: 'warning',
      message: t('chronicle.history.chronicleReset'),
      action: {
        label: t('chronicle.history.undo'),
        onClick: () => {
          void backend.undoChronicleReset(playthrough.save_id).then(async result => {
            if (result.error) return reportError(result.error)
            await onChanged(playthrough.save_id, 'undo-reset')
          })
        },
      },
    })
  }

  const handleUndoReset = async (playthrough: Playthrough) => {
    const succeeded = await runMutation(
      playthrough,
      'undo-reset',
      () => backend.undoChronicleReset(playthrough.save_id),
    )
    if (succeeded) showToast({ type: 'success', message: t('chronicle.history.chronicleRestored') })
  }

  const handleDelete = async (playthrough: Playthrough) => {
    if (confirmDeleteId !== playthrough.save_id) {
      setConfirmDeleteId(playthrough.save_id)
      return
    }
    setConfirmDeleteId(null)
    const succeeded = await runMutation(
      playthrough,
      'delete',
      () => backend.deletePlaythrough(playthrough.save_id),
    )
    if (succeeded) showToast({ type: 'success', message: t('chronicle.history.deleted') })
  }

  const handleBulkTrash = async () => {
    const targets = playthroughs.filter(playthrough => selected.has(playthrough.save_id))
    let moved = 0
    for (const playthrough of targets) {
      const result = await backend.trashPlaythrough(playthrough.save_id)
      if (result.error) {
        reportError(result.error)
        continue
      }
      await onChanged(playthrough.save_id, 'trash')
      moved += 1
    }
    setSelected(new Set())
    showToast({
      type: 'success',
      message: t('chronicle.history.bulkMoved', { count: moved }),
    })
  }

  const handleRemoveOrphanedPublication = async (publication: ChroniclePublicationSummary) => {
    if (confirmRemovePublicationId !== publication.saveId) {
      setConfirmRemovePublicationId(publication.saveId)
      return
    }
    setConfirmRemovePublicationId(null)
    const result = await window.electronAPI?.chroniclePublishing.delete(publication.saveId)
    if (!result?.ok) {
      reportError(result?.error.message || null)
      return
    }
    setPublications(previous => previous.filter(item => item.saveId !== publication.saveId))
    showToast({ type: 'success', message: t('chronicle.history.publishedRemoved') })
  }

  return createPortal(
    <AnimatePresence>
      {isOpen && (
        <motion.div
          className="fixed inset-0 z-[9998] flex items-center justify-center bg-black/75 p-3 backdrop-blur-sm sm:p-6"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onMouseDown={event => {
            if (event.currentTarget === event.target && !workingId) onClose()
          }}
        >
          <motion.section
            role="dialog"
            aria-modal="true"
            aria-labelledby="campaign-history-title"
            className="flex max-h-[92vh] w-full max-w-5xl flex-col overflow-hidden rounded-lg border border-accent-cyan/30 bg-bg-secondary shadow-[0_0_70px_rgba(0,212,255,0.14)]"
            initial={{ opacity: 0, y: 16, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.98 }}
          >
            <header className="flex items-start gap-4 border-b border-border p-5">
              <div className="flex-1">
                <p className="mb-1 text-[10px] uppercase tracking-[0.25em] text-accent-teal">
                  {t('chronicle.history.eyebrow')}
                </p>
                <h2 id="campaign-history-title" className="font-display text-xl uppercase tracking-wider text-text-primary">
                  {t('chronicle.history.title')}
                </h2>
                <p className="mt-2 max-w-3xl text-sm leading-relaxed text-text-secondary">
                  {t('chronicle.history.subtitle')}
                </p>
              </div>
              <button
                type="button"
                onClick={onClose}
                disabled={Boolean(workingId)}
                className="h-8 w-8 rounded border border-border text-text-secondary transition-colors hover:border-accent-cyan/50 hover:text-accent-cyan disabled:opacity-40"
                aria-label={t('chronicle.history.close')}
              >
                ×
              </button>
            </header>

            <div className="flex flex-wrap items-center gap-2 border-b border-border bg-bg-tertiary/30 px-5 py-3">
              <button
                type="button"
                onClick={() => { setTab('active'); setSelected(new Set()) }}
                className={`rounded border px-3 py-1.5 text-xs uppercase tracking-wider ${tab === 'active' ? 'border-accent-cyan/50 bg-accent-cyan/10 text-accent-cyan' : 'border-border text-text-secondary'}`}
              >
                {t('chronicle.history.active', { count: playthroughs.filter(item => !item.is_trashed).length })}
              </button>
              <button
                type="button"
                onClick={() => { setTab('trash'); setSelected(new Set()) }}
                className={`rounded border px-3 py-1.5 text-xs uppercase tracking-wider ${tab === 'trash' ? 'border-accent-yellow/50 bg-accent-yellow/10 text-accent-yellow' : 'border-border text-text-secondary'}`}
              >
                {t('chronicle.history.trash', { count: playthroughs.filter(item => item.is_trashed).length })}
              </button>
              <input
                value={query}
                onChange={event => setQuery(event.target.value)}
                placeholder={t('chronicle.history.search')}
                className="ml-auto min-w-48 rounded border border-border bg-bg-primary px-3 py-1.5 text-sm text-text-primary outline-none focus:border-accent-cyan/60"
              />
            </div>

            {tab === 'active' && (
              <div className="flex flex-wrap items-center gap-2 border-b border-border px-5 py-3">
                <button
                  type="button"
                  disabled={emptyStarts.length === 0}
                  onClick={() => setSelected(new Set(emptyStarts.map(item => item.save_id)))}
                  className="rounded border border-border px-3 py-1.5 text-xs text-text-secondary transition-colors hover:border-accent-cyan/40 hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {t('chronicle.history.selectEmpty', { count: emptyStarts.length })}
                </button>
                {selected.size > 0 && (
                  <button
                    type="button"
                    onClick={() => void handleBulkTrash()}
                    className="rounded border border-accent-yellow/40 bg-accent-yellow/5 px-3 py-1.5 text-xs text-accent-yellow hover:bg-accent-yellow/10"
                  >
                    {t('chronicle.history.trashSelected', { count: selected.size })}
                  </button>
                )}
                <p className="text-xs text-text-muted">{t('chronicle.history.emptyHelp')}</p>
              </div>
            )}

            <div className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-5">
              {visible.length === 0 ? (
                <div className="flex min-h-48 items-center justify-center text-sm text-text-muted">
                  {tab === 'trash' ? t('chronicle.history.trashEmpty') : t('chronicle.history.noMatches')}
                </div>
              ) : (
                <div className="space-y-3">
                  {visible.map(playthrough => {
                    const publication = publicationBySaveId.get(playthrough.save_id)
                    const isWorking = workingId === playthrough.save_id
                    return (
                      <article key={playthrough.save_id} className="rounded-md border border-border bg-bg-primary/40 p-4">
                        <div className="flex gap-3">
                          {tab === 'active' && !playthrough.is_current && (
                            <input
                              type="checkbox"
                              checked={selected.has(playthrough.save_id)}
                              onChange={event => setSelected(previous => {
                                const next = new Set(previous)
                                if (event.target.checked) next.add(playthrough.save_id)
                                else next.delete(playthrough.save_id)
                                return next
                              })}
                              className="mt-1 h-4 w-4 accent-cyan-400"
                              aria-label={t('chronicle.history.selectCampaign', { name: playthrough.display_name })}
                            />
                          )}
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <h3 className="truncate font-medium text-text-primary">{playthrough.display_name}</h3>
                              {playthrough.is_current && <Badge tone="cyan">{t('chronicle.history.current')}</Badge>}
                              {playthrough.has_chronicle && <Badge tone="teal">{t('chronicle.history.hasChronicle')}</Badge>}
                              {!playthrough.has_chronicle && <Badge tone="muted">{t('chronicle.history.noChronicle')}</Badge>}
                              {publication?.state === 'published' && <Badge tone="yellow">{t('chronicle.history.published')}</Badge>}
                            </div>
                            {playthrough.display_label && (
                              <p className="mt-1 text-xs text-text-muted">{playthrough.empire_name}</p>
                            )}
                            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-secondary">
                              <span>{t('chronicle.history.gameDates', { first: formatGameDate(playthrough.first_game_date), last: formatGameDate(playthrough.last_game_date) })}</span>
                              <span>{t('chronicle.history.sessions', { count: playthrough.session_count })}</span>
                              <span>{t('chronicle.history.snapshots', { count: playthrough.snapshot_count })}</span>
                              <span>{t('chronicle.history.events', { count: playthrough.event_count })}</span>
                              <span>{t('chronicle.history.chapters', { count: playthrough.total_chapter_count })}</span>
                            </div>

                            {editingId === playthrough.save_id && (
                              <div className="mt-3 flex max-w-lg gap-2">
                                <input
                                  autoFocus
                                  value={label}
                                  maxLength={80}
                                  onChange={event => setLabel(event.target.value)}
                                  onKeyDown={event => {
                                    if (event.key === 'Enter') void handleSaveLabel(playthrough)
                                    if (event.key === 'Escape') setEditingId(null)
                                  }}
                                  placeholder={playthrough.empire_name || t('chronicle.history.labelPlaceholder')}
                                  className="min-w-0 flex-1 rounded border border-accent-cyan/40 bg-bg-primary px-3 py-2 text-sm text-text-primary outline-none"
                                />
                                <button type="button" onClick={() => void handleSaveLabel(playthrough)} className="rounded border border-accent-cyan/40 px-3 text-xs text-accent-cyan">
                                  {t('chronicle.history.save')}
                                </button>
                                <button type="button" onClick={() => setEditingId(null)} className="rounded border border-border px-3 text-xs text-text-secondary">
                                  {t('chronicle.history.cancel')}
                                </button>
                              </div>
                            )}

                            {tab === 'trash' && publication?.state === 'published' && confirmDeleteId === playthrough.save_id && (
                              <p className="mt-3 rounded border border-accent-yellow/30 bg-accent-yellow/5 px-3 py-2 text-xs text-accent-yellow">
                                {t('chronicle.history.publishedDeleteWarning')}
                              </p>
                            )}
                          </div>

                          <div className="flex shrink-0 flex-wrap content-start justify-end gap-2 sm:max-w-72">
                            {tab === 'active' ? (
                              <>
                                <ActionButton onClick={() => { setEditingId(playthrough.save_id); setLabel(playthrough.display_label || '') }} disabled={isWorking}>
                                  {t('chronicle.history.rename')}
                                </ActionButton>
                                {playthrough.can_undo_reset ? (
                                  <ActionButton onClick={() => void handleUndoReset(playthrough)} disabled={isWorking}>
                                    {t('chronicle.history.undoReset')}
                                  </ActionButton>
                                ) : playthrough.has_chronicle ? (
                                  <ActionButton onClick={() => void handleReset(playthrough)} disabled={isWorking} tone="warning">
                                    {confirmResetId === playthrough.save_id ? t('chronicle.history.confirmReset') : t('chronicle.history.reset')}
                                  </ActionButton>
                                ) : null}
                                <ActionButton onClick={() => void handleTrash(playthrough)} disabled={isWorking || playthrough.is_current} tone="warning" title={playthrough.is_current ? t('chronicle.history.currentProtected') : undefined}>
                                  {t('chronicle.history.moveToTrash')}
                                </ActionButton>
                              </>
                            ) : (
                              <>
                                <ActionButton onClick={() => void handleRestore(playthrough)} disabled={isWorking}>
                                  {t('chronicle.history.restore')}
                                </ActionButton>
                                <ActionButton onClick={() => void handleDelete(playthrough)} disabled={isWorking} tone="danger">
                                  {confirmDeleteId === playthrough.save_id ? t('chronicle.history.confirmDelete') : t('chronicle.history.delete')}
                                </ActionButton>
                              </>
                            )}
                          </div>
                        </div>
                      </article>
                    )
                  })}
                </div>
              )}
              {tab === 'trash' && orphanedPublications.length > 0 && (
                <section className="mt-5 border-t border-border pt-5">
                  <h3 className="text-xs uppercase tracking-wider text-accent-yellow">
                    {t('chronicle.history.onlineOnlyTitle')}
                  </h3>
                  <p className="mt-1 text-xs leading-relaxed text-text-muted">
                    {t('chronicle.history.onlineOnlyHelp')}
                  </p>
                  <div className="mt-3 space-y-2">
                    {orphanedPublications.map(publication => (
                      <div key={publication.saveId} className="flex flex-wrap items-center gap-3 rounded border border-accent-yellow/25 bg-accent-yellow/5 px-4 py-3">
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm text-text-primary">{publication.title}</p>
                          <p className="mt-1 text-[10px] uppercase tracking-wider text-accent-yellow">
                            {t('chronicle.history.published')}
                          </p>
                        </div>
                        {publication.publicUrl && (
                          <ActionButton onClick={() => void window.electronAPI?.openExternal(publication.publicUrl!)}>
                            {t('chronicle.history.openStory')}
                          </ActionButton>
                        )}
                        <ActionButton onClick={() => void handleRemoveOrphanedPublication(publication)} tone="danger">
                          {confirmRemovePublicationId === publication.saveId
                            ? t('chronicle.history.confirmRemoveStory')
                            : t('chronicle.history.removeStory')}
                        </ActionButton>
                      </div>
                    ))}
                  </div>
                </section>
              )}
            </div>

            <footer className="border-t border-border bg-bg-tertiary/30 px-5 py-3 text-xs leading-relaxed text-text-muted">
              {t('chronicle.history.safetyNote')}
            </footer>
          </motion.section>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  )
}

function Badge({ children, tone }: { children: React.ReactNode; tone: 'cyan' | 'teal' | 'yellow' | 'muted' }) {
  const styles = {
    cyan: 'border-accent-cyan/40 bg-accent-cyan/5 text-accent-cyan',
    teal: 'border-accent-teal/40 bg-accent-teal/5 text-accent-teal',
    yellow: 'border-accent-yellow/40 bg-accent-yellow/5 text-accent-yellow',
    muted: 'border-border bg-bg-tertiary/50 text-text-muted',
  }
  return <span className={`rounded border px-2 py-0.5 text-[10px] uppercase tracking-wider ${styles[tone]}`}>{children}</span>
}

function ActionButton({
  children,
  onClick,
  disabled,
  tone = 'neutral',
  title,
}: {
  children: React.ReactNode
  onClick: () => void
  disabled?: boolean
  tone?: 'neutral' | 'warning' | 'danger'
  title?: string
}) {
  const styles = tone === 'danger'
    ? 'border-accent-red/40 text-accent-red hover:bg-accent-red/10'
    : tone === 'warning'
      ? 'border-accent-yellow/35 text-accent-yellow hover:bg-accent-yellow/10'
      : 'border-border text-text-secondary hover:border-accent-cyan/40 hover:text-text-primary'
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`rounded border px-2.5 py-1.5 text-xs transition-colors disabled:cursor-not-allowed disabled:opacity-35 ${styles}`}
    >
      {children}
    </button>
  )
}

export default CampaignHistoryDialog
