import { useCallback, useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import type { ChronicleResponse } from '../hooks/useBackend'
import type {
  ChroniclePublicationReceipt,
  ChroniclePublicationVisibility,
} from '../global'

interface ChroniclePublishDialogProps {
  isOpen: boolean
  onClose: () => void
  saveId: string | null
  empireName: string
  chronicle: ChronicleResponse | null
}

function ChroniclePublishDialog({
  isOpen,
  onClose,
  saveId,
  empireName,
  chronicle,
}: ChroniclePublishDialogProps) {
  const { t, i18n } = useTranslation()
  const defaultTitle = useMemo(
    () => t('chronicle.publish.defaultTitle', { empireName }),
    [empireName, t],
  )
  const [title, setTitle] = useState(defaultTitle)
  const [visibility, setVisibility] = useState<ChroniclePublicationVisibility>('unlisted')
  const [receipt, setReceipt] = useState<ChroniclePublicationReceipt | null>(null)
  const [loadingStatus, setLoadingStatus] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [removing, setRemoving] = useState(false)
  const [confirmRemove, setConfirmRemove] = useState(false)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [syncWarning, setSyncWarning] = useState<string | null>(null)

  const loadStatus = useCallback(async () => {
    if (!saveId || !window.electronAPI?.chroniclePublishing) return
    setLoadingStatus(true)
    setError(null)
    try {
      const result = await window.electronAPI.chroniclePublishing.status(saveId)
      if (!result.ok) {
        setError(result.error.message)
        return
      }
      setSyncWarning(result.data.syncWarning || null)
      const nextReceipt = result.data.receipt || null
      setReceipt(nextReceipt)
      if (nextReceipt) {
        setTitle(nextReceipt.title || defaultTitle)
        setVisibility(nextReceipt.visibility)
      } else {
        setTitle(defaultTitle)
        setVisibility('unlisted')
      }
    } finally {
      setLoadingStatus(false)
    }
  }, [defaultTitle, saveId])

  useEffect(() => {
    if (!isOpen) return
    setConfirmRemove(false)
    setCopied(false)
    setError(null)
    setSyncWarning(null)
    void loadStatus()
  }, [isOpen, loadStatus])

  useEffect(() => {
    if (!isOpen) return
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !submitting && !removing) onClose()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose, removing, submitting])

  const handlePublish = async () => {
    if (!saveId || !chronicle || !window.electronAPI?.chroniclePublishing) {
      setError(t('chronicle.publish.unavailable'))
      return
    }

    setSubmitting(true)
    setError(null)
    setSyncWarning(null)
    try {
      const result = await window.electronAPI.chroniclePublishing.publish({
        saveId,
        title: title.trim(),
        empireName,
        language: i18n.resolvedLanguage || i18n.language || 'en',
        visibility,
        document: {
          chapters: chronicle.chapters,
          ...(chronicle.current_era ? { current_era: chronicle.current_era } : {}),
        },
      })
      if (!result.ok) {
        setError(result.error.message)
        if (result.error.code === 'revision_conflict') await loadStatus()
        return
      }
      setReceipt(result.data)
      setTitle(result.data.title || title)
      setVisibility(result.data.visibility)
      setCopied(false)
    } finally {
      setSubmitting(false)
    }
  }

  const handleCopy = async () => {
    if (!receipt) return
    const result = await window.electronAPI?.copyToClipboard(receipt.publicUrl)
    if (result?.success) {
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1800)
    }
  }

  const handleOpen = async () => {
    if (!receipt) return
    await window.electronAPI?.openExternal(receipt.publicUrl)
  }

  const handleRemove = async () => {
    if (!saveId || !window.electronAPI?.chroniclePublishing) return
    if (!confirmRemove) {
      setConfirmRemove(true)
      return
    }

    setRemoving(true)
    setError(null)
    try {
      const result = await window.electronAPI.chroniclePublishing.delete(saveId)
      if (!result.ok) {
        setError(result.error.message)
        return
      }
      setReceipt(null)
      setTitle(defaultTitle)
      setVisibility('unlisted')
      setConfirmRemove(false)
    } finally {
      setRemoving(false)
    }
  }

  const moderationMessage = receipt?.moderationStatus === 'pending'
    ? t('chronicle.publish.pendingReview')
    : receipt?.moderationStatus === 'approved'
      ? t('chronicle.publish.approved')
      : receipt
        ? t('chronicle.publish.unlistedStatus')
        : null

  return createPortal(
    <AnimatePresence>
      {isOpen && (
        <motion.div
          className="fixed inset-0 z-[9998] flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onMouseDown={(event) => {
            if (event.currentTarget === event.target && !submitting && !removing) onClose()
          }}
        >
          <motion.section
            role="dialog"
            aria-modal="true"
            aria-labelledby="chronicle-publish-title"
            className="w-full max-w-2xl max-h-[90vh] overflow-y-auto border border-accent-cyan/30 bg-bg-secondary shadow-[0_0_70px_rgba(0,212,255,0.14)] rounded-lg"
            initial={{ opacity: 0, y: 16, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.98 }}
            transition={{ duration: 0.18 }}
          >
            <header className="flex items-start gap-4 border-b border-border p-5">
              <div className="flex-1">
                <p className="text-[10px] uppercase tracking-[0.25em] text-accent-teal mb-1">{t('chronicle.publish.eyebrow')}</p>
                <h2 id="chronicle-publish-title" className="font-display text-xl uppercase tracking-wider text-text-primary">
                  {t('chronicle.publish.title')}
                </h2>
                <p className="mt-2 text-sm text-text-secondary leading-relaxed">{t('chronicle.publish.subtitle')}</p>
              </div>
              <button
                type="button"
                onClick={onClose}
                disabled={submitting || removing}
                className="w-8 h-8 rounded border border-border text-text-secondary hover:text-accent-cyan hover:border-accent-cyan/50 disabled:opacity-40 transition-colors"
                aria-label={t('chronicle.publish.close')}
              >
                ×
              </button>
            </header>

            <div className="p-5 space-y-5">
              {loadingStatus ? (
                <div className="h-40 flex items-center justify-center gap-3 text-sm text-text-secondary">
                  <span className="w-4 h-4 border border-accent-cyan border-t-transparent rounded-full animate-spin-loader" />
                  {t('chronicle.publish.checking')}
                </div>
              ) : (
                <>
                  {receipt && (
                    <div className="border border-accent-teal/30 bg-accent-teal/5 rounded-md p-4">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-accent-teal shadow-[0_0_8px_rgba(45,212,191,0.8)]" />
                        <strong className="text-sm text-accent-teal">{t('chronicle.publish.published')}</strong>
                        <span className="text-xs text-text-muted">{t('chronicle.publish.revision', { revision: receipt.revision })}</span>
                      </div>
                      {moderationMessage && <p className="mt-2 text-xs text-text-secondary">{moderationMessage}</p>}
                      <div className="mt-4 flex flex-wrap gap-2">
                        <button type="button" onClick={handleCopy} className="px-3 py-2 rounded border border-accent-teal/35 text-xs text-accent-teal hover:bg-accent-teal/10 transition-colors">
                          {copied ? t('chronicle.publish.copied') : t('chronicle.publish.copyLink')}
                        </button>
                        <button type="button" onClick={handleOpen} className="px-3 py-2 rounded border border-border text-xs text-text-secondary hover:text-text-primary hover:border-accent-cyan/40 transition-colors">
                          {t('chronicle.publish.openStory')}
                        </button>
                      </div>
                    </div>
                  )}

                  {syncWarning && (
                    <div className="border border-accent-yellow/25 bg-accent-yellow/5 rounded-md px-4 py-3 text-xs text-accent-yellow">
                      {t('chronicle.publish.syncWarning', { message: syncWarning })}
                    </div>
                  )}

                  <div>
                    <label htmlFor="chronicle-publication-title" className="block text-xs uppercase tracking-wider text-text-secondary mb-2">
                      {t('chronicle.publish.storyTitle')}
                    </label>
                    <input
                      id="chronicle-publication-title"
                      value={title}
                      onChange={(event) => setTitle(event.target.value.slice(0, 120))}
                      maxLength={120}
                      className="w-full rounded-md border border-border bg-bg-tertiary px-3 py-2.5 text-sm text-text-primary focus:outline-none focus:border-accent-cyan/60"
                    />
                    <p className="mt-1 text-right text-[10px] text-text-muted">{title.length}/120</p>
                  </div>

                  <fieldset>
                    <legend className="text-xs uppercase tracking-wider text-text-secondary mb-2">{t('chronicle.publish.visibility')}</legend>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <label className={`cursor-pointer rounded-md border p-4 transition-colors ${visibility === 'unlisted' ? 'border-accent-cyan/55 bg-accent-cyan/5' : 'border-border bg-bg-tertiary/40 hover:border-border-light'}`}>
                        <input className="sr-only" type="radio" name="chronicle-visibility" value="unlisted" checked={visibility === 'unlisted'} onChange={() => setVisibility('unlisted')} />
                        <span className="block text-sm font-semibold text-text-primary">{t('chronicle.publish.unlisted')}</span>
                        <span className="mt-1 block text-xs leading-relaxed text-text-secondary">{t('chronicle.publish.unlistedHelp')}</span>
                      </label>
                      <label className={`cursor-pointer rounded-md border p-4 transition-colors ${visibility === 'discoverable' ? 'border-accent-teal/55 bg-accent-teal/5' : 'border-border bg-bg-tertiary/40 hover:border-border-light'}`}>
                        <input className="sr-only" type="radio" name="chronicle-visibility" value="discoverable" checked={visibility === 'discoverable'} onChange={() => setVisibility('discoverable')} />
                        <span className="block text-sm font-semibold text-text-primary">{t('chronicle.publish.discoverable')}</span>
                        <span className="mt-1 block text-xs leading-relaxed text-text-secondary">{t('chronicle.publish.discoverableHelp')}</span>
                      </label>
                    </div>
                  </fieldset>

                  <div className="rounded-md border border-border bg-bg-primary/50 p-4">
                    <h3 className="text-xs uppercase tracking-wider text-text-primary">{t('chronicle.publish.privacyTitle')}</h3>
                    <ul className="mt-3 space-y-2 text-xs leading-relaxed text-text-secondary">
                      <li className="flex gap-2"><span className="text-accent-teal">✓</span>{t('chronicle.publish.privacyStoryOnly')}</li>
                      <li className="flex gap-2"><span className="text-accent-teal">✓</span>{t('chronicle.publish.privacyNoSave')}</li>
                      <li className="flex gap-2"><span className="text-accent-teal">✓</span>{t('chronicle.publish.privacyKey')}</li>
                    </ul>
                  </div>

                  {error && (
                    <div className="rounded-md border border-accent-red/30 bg-accent-red/10 px-4 py-3 text-sm text-accent-red">
                      {error}
                    </div>
                  )}

                  <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-5">
                    <div>
                      {receipt && (
                        <button
                          type="button"
                          onClick={handleRemove}
                          disabled={removing || submitting}
                          className={`px-3 py-2 text-xs rounded border transition-colors disabled:opacity-50 ${confirmRemove ? 'border-accent-red bg-accent-red/15 text-accent-red' : 'border-border text-text-muted hover:text-accent-red hover:border-accent-red/40'}`}
                        >
                          {removing
                            ? t('chronicle.publish.removing')
                            : confirmRemove
                              ? t('chronicle.publish.confirmRemove')
                              : t('chronicle.publish.remove')}
                        </button>
                      )}
                    </div>
                    <div className="flex gap-2">
                      <button type="button" onClick={onClose} disabled={submitting || removing} className="px-4 py-2.5 rounded border border-border text-xs text-text-secondary hover:text-text-primary transition-colors disabled:opacity-50">
                        {t('chronicle.publish.cancel')}
                      </button>
                      <button
                        type="button"
                        onClick={handlePublish}
                        disabled={submitting || removing || !title.trim() || !chronicle}
                        className="px-5 py-2.5 rounded border border-accent-cyan/50 bg-accent-cyan/10 text-xs font-semibold uppercase tracking-wider text-accent-cyan hover:bg-accent-cyan/20 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                      >
                        {submitting
                          ? t(receipt ? 'chronicle.publish.updating' : 'chronicle.publish.publishing')
                          : t(receipt ? 'chronicle.publish.update' : 'chronicle.publish.publish')}
                      </button>
                    </div>
                  </div>
                </>
              )}
            </div>
          </motion.section>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  )
}

export default ChroniclePublishDialog
