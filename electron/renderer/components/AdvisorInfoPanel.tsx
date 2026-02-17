import { useEffect, useMemo, useState } from 'react'
import PersonIcon from './PersonIcon'
import { createPortal } from 'react-dom'
import { motion, AnimatePresence } from 'framer-motion'

interface AdvisorInfoPanelProps {
  isOpen: boolean
  onClose: () => void
  saveLoaded: boolean
  empireName: string | null
  gameDate: string | null
  empireEthics: string[]
  empireCivics: string[]
  empireAuthority: string | null
  empireOrigin: string | null
}

function formatTraits(
  ethicsList: string[],
  civicsList: string[],
  authority: string | null,
): string {
  const ethics = ethicsList.length ? ethicsList.join(', ') : null
  const civics = civicsList.length ? civicsList.join(', ') : null

  const parts: string[] = []
  if (ethics) parts.push(`Ethics: ${ethics}`)
  if (authority) parts.push(`Authority: ${authority}`)
  if (civics) parts.push(`Civics: ${civics}`)
  if (parts.length === 0) return 'No empire traits available'
  return parts.join(' | ')
}

export default function AdvisorInfoPanel({
  isOpen,
  onClose,
  saveLoaded,
  empireName,
  gameDate,
  empireEthics,
  empireCivics,
  empireAuthority,
  empireOrigin,
}: AdvisorInfoPanelProps) {
  const panelTransition = {
    type: 'spring' as const,
    stiffness: 420,
    damping: 38,
  }

  const blurTransition = {
    duration: 0.42,
    ease: 'easeOut' as const,
    delay: 0.05,
  }

  const strongBlurTransition = {
    duration: 0.6,
    ease: 'easeOut' as const,
    delay: 0.22,
  }

  // Note: animating `backdrop-filter` is unreliable in Electron/Chromium (often snaps).
  // Use two overlays instead: a dim layer plus a blurred layer that crossfades via opacity.
  const dimVariants = {
    closed: { opacity: 0 },
    open: { opacity: 1 },
  }
  const blurVariants = {
    closed: { opacity: 0 },
    open: { opacity: 1 },
  }

  const panelVariants = {
    closed: { x: 28, opacity: 0 },
    open: { x: 0, opacity: 1 },
  }

  const [customInstructions, setCustomInstructions] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveResult, setSaveResult] = useState<{ ok: boolean; message: string } | null>(null)

  const traits = useMemo(
    () => formatTraits(empireEthics, empireCivics, empireAuthority),
    [empireEthics, empireCivics, empireAuthority],
  )

  useEffect(() => {
    if (!isOpen) return

    setSaveResult(null)

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [isOpen, onClose])

  useEffect(() => {
    if (!isOpen) return

    const load = async () => {
      // Custom instructions (persisted if session exists, otherwise in-memory).
      try {
        const res = await window.electronAPI?.backend?.getSessionAdvisorCustom()
        if (res && typeof res === 'object' && 'ok' in res && res.ok) {
          setCustomInstructions((res.data.custom_instructions || '') as string)
        } else {
          setCustomInstructions('')
        }
      } catch {
        setCustomInstructions('')
      }
    }

    load()
  }, [isOpen])

  const handleApply = async () => {
    if (!window.electronAPI?.backend?.setSessionAdvisorCustom) return
    setSaving(true)
    setSaveResult(null)
    try {
      const res = await window.electronAPI.backend.setSessionAdvisorCustom(customInstructions)
      if (res && typeof res === 'object' && 'ok' in res && res.ok) {
        const persisted = !!res.data.persisted
        setCustomInstructions((res.data.custom_instructions || '') as string)
        setSaveResult({
          ok: true,
          message: persisted ? 'Applied to this playthrough' : 'Applied (will persist when analysis completes)',
        })
      } else {
        const message = (res as any)?.error || 'Failed to apply customization'
        setSaveResult({ ok: false, message })
      }
    } catch (e) {
      setSaveResult({ ok: false, message: e instanceof Error ? e.message : 'Failed to apply customization' })
    } finally {
      setSaving(false)
    }
  }

  return createPortal(
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[9998]"
        >
          {/* Backdrop (dim layer) */}
          <motion.div
            variants={dimVariants}
            initial="closed"
            animate="open"
            exit="closed"
            transition={panelTransition}
            className="absolute inset-0 bg-gradient-to-l from-black/40 via-black/25 to-transparent backdrop-blur-[0px]"
            onClick={onClose}
          />

          {/* Backdrop (blur layer) - crossfaded for smoothness */}
          <motion.div
            variants={blurVariants}
            initial="closed"
            animate="open"
            exit="closed"
            transition={blurTransition}
            className="absolute inset-0 pointer-events-none bg-gradient-to-l from-black/12 via-black/6 to-transparent backdrop-blur-[1px]"
          />

          {/* Backdrop (strong blur layer) - delayed so compositor snap happens near-zero opacity */}
          <motion.div
            variants={blurVariants}
            initial="closed"
            animate="open"
            exit="closed"
            transition={strongBlurTransition}
            className="absolute inset-0 pointer-events-none bg-gradient-to-l from-black/6 via-black/3 to-transparent backdrop-blur-[3px]"
          />

          {/* Right-side panel */}
          <motion.div
            variants={panelVariants}
            initial="closed"
            animate="open"
            exit="closed"
            transition={panelTransition}
            className="absolute right-0 top-0 bottom-0 w-full max-w-[420px] bg-bg-secondary border-l border-border"
            style={{
              boxShadow:
                '0 0 30px rgb(var(--color-accent-cyan) / 0.18), inset 0 0 20px rgb(var(--color-accent-cyan) / 0.04)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="h-full flex flex-col">
              {/* Header */}
              <div className="relative px-5 py-4 border-b border-border">
                <div className="absolute top-0 left-0 w-3 h-3 border-l-2 border-t-2 border-accent-cyan/50" />
                <div className="absolute top-0 right-0 w-3 h-3 border-r-2 border-t-2 border-accent-cyan/50" />
                <div className="absolute bottom-0 left-0 w-3 h-3 border-l-2 border-b-2 border-accent-cyan/50" />
                <div className="absolute bottom-0 right-0 w-3 h-3 border-r-2 border-b-2 border-accent-cyan/50" />

                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <PersonIcon className="w-5 h-5 text-accent-cyan" />
                    <div>
                      <h2 className="font-display text-text-primary text-lg tracking-wider uppercase leading-tight">
                        Advisor
                      </h2>
                      <p className="text-xs text-text-secondary">
                        {empireName ?? 'No save loaded'}
                        {gameDate ? ` • ${gameDate}` : ''}
                      </p>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={onClose}
                    className="text-text-secondary hover:text-text-primary transition-colors text-lg leading-none px-2 py-1 rounded hover:bg-bg-tertiary/60"
                    aria-label="Close advisor panel"
                  >
                    ×
                  </button>
                </div>
              </div>

              {/* Body */}
              <div className="flex-1 overflow-y-auto p-5 space-y-5">
                <div className="stellaris-panel rounded-lg p-4">
                  <p className="text-xs text-text-secondary uppercase tracking-wider font-semibold mb-3 flex items-center gap-2">
                    <span className="text-accent-cyan/60">◇</span>
                    Empire Traits (Auto-Detected)
                  </p>
                  <div className="px-3 py-2 rounded bg-bg-primary/50 border border-border/50 text-sm text-text-secondary font-mono">
                    {saveLoaded ? traits : 'No save loaded'}
                  </div>
                  {empireOrigin && (
                    <p className="text-xs text-text-secondary mt-2">
                      Origin: <span className="text-text-primary">{empireOrigin}</span>
                    </p>
                  )}
                </div>

                <div className="stellaris-panel rounded-lg p-4">
                  <p className="text-xs text-text-secondary uppercase tracking-wider font-semibold mb-3 flex items-center gap-2">
                    <span className="text-accent-cyan/60">◇</span>
                    Personality Customization (Optional)
                  </p>
                  <textarea
                    value={customInstructions}
                    onChange={(e) => setCustomInstructions(e.target.value)}
                    placeholder="Describe the advisor's personality..."
                    maxLength={300}
                    rows={4}
                    disabled={!saveLoaded}
                    className="w-full px-4 py-3 border border-border rounded-md bg-bg-primary/50 text-text-primary text-sm font-sans outline-none transition-all duration-200 focus:border-accent-cyan/50 focus:shadow-glow-sm placeholder:text-text-secondary/60 resize-none disabled:opacity-60 disabled:cursor-not-allowed"
                  />

                  {!customInstructions && (
                    <div className="mt-3">
                      <p className="text-[11px] text-text-secondary uppercase tracking-wider mb-2">Try a personality</p>
                      <div className="flex flex-wrap gap-1.5">
                        {[
                          'Paranoid intelligence officer who trusts no one',
                          'Passive-aggressive about your decisions',
                          'Corporate middle manager using buzzwords for galactic conquest',
                          'Overly enthusiastic about everything, even catastrophes',
                        ].map((example) => (
                          <button
                            key={example}
                            type="button"
                            disabled={!saveLoaded}
                            onClick={() => setCustomInstructions(example)}
                            className="px-2.5 py-1.5 text-xs text-text-secondary border border-border/60 rounded bg-bg-primary/30 hover:text-accent-cyan hover:border-accent-cyan/40 hover:bg-accent-cyan/5 transition-all duration-150 text-left disabled:opacity-40 disabled:cursor-not-allowed"
                          >
                            {example}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                  <div className="flex items-center justify-between mt-2">
                    <p className="text-xs text-text-secondary m-0">{customInstructions.length}/300</p>
                    <button
                      type="button"
                      onClick={handleApply}
                      disabled={!saveLoaded || saving}
                      className={`py-2 px-4 border rounded-md text-xs font-semibold uppercase tracking-wider cursor-pointer transition-all duration-200 ${
                        saveLoaded && !saving
                          ? 'bg-accent-cyan/20 border-accent-cyan/50 text-accent-cyan hover:bg-accent-cyan/30 hover:shadow-glow-sm'
                          : 'bg-bg-tertiary/50 border-border text-text-secondary opacity-50 cursor-not-allowed'
                      }`}
                    >
                      {saving ? 'Applying…' : 'Apply'}
                    </button>
                  </div>

                  {saveResult && (
                    <div
                      className={`mt-3 text-xs px-3 py-2 rounded border ${
                        saveResult.ok
                          ? 'bg-accent-green/10 border-accent-green/30 text-accent-green'
                          : 'bg-accent-red/10 border-accent-red/30 text-accent-red'
                      }`}
                    >
                      {saveResult.message}
                    </div>
                  )}

                  {!saveLoaded && (
                    <p className="text-xs text-text-secondary mt-3">
                      Load a save to customize the advisor for this playthrough.
                    </p>
                  )}
                </div>
              </div>

              {/* Footer energy line */}
              <div className="energy-line" />
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  )
}
