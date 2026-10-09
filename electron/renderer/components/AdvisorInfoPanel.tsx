import { useEffect, useMemo, useRef, useState } from 'react'
import PersonIcon from './PersonIcon'
import Modal from './Modal'
import { useTranslation } from 'react-i18next'

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

function humanizeIdentifier(value: string): string {
  return value
    .replace(/^(ethic|civic|authority|origin)_/i, '')
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, character => character.toUpperCase())
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
  const { t } = useTranslation()
  const [customInstructions, setCustomInstructions] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveResult, setSaveResult] = useState<{ ok: boolean; message: string } | null>(null)
  const editedSinceOpen = useRef(false)

  const editInstructions = (value: string) => {
    editedSinceOpen.current = true
    setCustomInstructions(value)
    setSaveResult(null)
  }

  const traitGroups = useMemo(() => [
    {
      label: t('advisorPanel.ethics'),
      values: empireEthics.map(humanizeIdentifier),
    },
    {
      label: t('advisorPanel.authority'),
      values: empireAuthority ? [humanizeIdentifier(empireAuthority)] : [],
    },
    {
      label: t('advisorPanel.civics'),
      values: empireCivics.map(humanizeIdentifier),
    },
    {
      label: t('advisorPanel.origin'),
      values: empireOrigin ? [humanizeIdentifier(empireOrigin)] : [],
    },
  ].filter(group => group.values.length > 0), [empireAuthority, empireCivics, empireEthics, empireOrigin, t])

  useEffect(() => {
    if (!isOpen) return
    setSaveResult(null)
    editedSinceOpen.current = false
    let cancelled = false

    const load = async () => {
      // Custom instructions (persisted if session exists, otherwise in-memory).
      try {
        const res = await window.electronAPI?.backend?.getSessionAdvisorCustom()
        // A late load must not replace instructions already being edited.
        if (cancelled || editedSinceOpen.current) return
        if (res && typeof res === 'object' && 'ok' in res && res.ok) {
          setCustomInstructions((res.data.custom_instructions || '') as string)
        } else {
          setCustomInstructions('')
        }
      } catch {
        if (!cancelled && !editedSinceOpen.current) setCustomInstructions('')
      }
    }

    void load()
    return () => { cancelled = true }
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
          message: persisted ? t('advisorPanel.saved') : t('advisorPanel.savedWhenReady'),
        })
      } else {
        const message = (res as any)?.error || t('advisorPanel.saveError')
        setSaveResult({ ok: false, message })
      }
    } catch (e) {
      setSaveResult({ ok: false, message: e instanceof Error ? e.message : t('advisorPanel.saveError') })
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal open={isOpen} onClose={onClose} placement="right" label={t('advisorPanel.title')} className="w-full">
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
                      <h2 id="advisor-style-title" className="font-display text-text-primary text-lg tracking-wider uppercase leading-tight">
                        {t('advisorPanel.title')}
                      </h2>
                      <p className="text-xs text-text-secondary">
                        {empireName ?? t('advisorPanel.noSave')}
                        {gameDate ? ` • ${gameDate}` : ''}
                      </p>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={onClose}
                    className="text-text-secondary hover:text-text-primary transition-colors text-lg leading-none px-2 py-1 rounded hover:bg-bg-tertiary/60"
                    aria-label={t('advisorPanel.close')}
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
                    {t('advisorPanel.empireDetails')}
                  </p>
                  <p className="mb-3 text-xs leading-relaxed text-text-muted">
                    {t('advisorPanel.empireDetailsHelp')}
                  </p>
                  {saveLoaded && traitGroups.length > 0 ? (
                    <div className="space-y-3">
                      {traitGroups.map(group => (
                        <div key={group.label}>
                          <p className="mb-1.5 text-[10px] uppercase tracking-wider text-text-muted">{group.label}</p>
                          <div className="flex flex-wrap gap-1.5">
                            {group.values.map(value => (
                              <span key={value} className="rounded border border-border/70 bg-bg-primary/50 px-2.5 py-1 text-xs text-text-secondary">
                                {value}
                              </span>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="rounded border border-border/50 bg-bg-primary/50 px-3 py-2 text-sm text-text-secondary">
                      {saveLoaded ? t('advisorPanel.noTraits') : t('advisorPanel.noSave')}
                    </p>
                  )}
                </div>

                <div className="stellaris-panel rounded-lg p-4">
                  <p className="text-xs text-text-secondary uppercase tracking-wider font-semibold mb-3 flex items-center gap-2">
                    <span className="text-accent-cyan/60">◇</span>
                    {t('advisorPanel.personality')}
                  </p>
                  <p className="mb-3 text-xs leading-relaxed text-text-muted">
                    {t('advisorPanel.personalityHelp')}
                  </p>
                  <textarea
                    value={customInstructions}
                    onChange={(e) => editInstructions(e.target.value)}
                    placeholder={t('advisorPanel.placeholder')}
                    aria-label={t('advisorPanel.personalityInstructions')}
                    maxLength={300}
                    rows={4}
                    disabled={!saveLoaded || saving}
                    className="w-full px-4 py-3 border border-border rounded-md bg-bg-primary/50 text-text-primary text-sm font-sans outline-none transition-all duration-200 focus:border-accent-cyan/50 focus:shadow-glow-sm placeholder:text-text-secondary/60 resize-none disabled:opacity-60 disabled:cursor-not-allowed"
                  />

                  {!customInstructions && (
                    <div className="mt-3">
                      <p className="text-[11px] text-text-secondary uppercase tracking-wider mb-2">{t('advisorPanel.tryStyle')}</p>
                      <div className="flex flex-wrap gap-1.5">
                        {[
                          t('advisorPanel.styles.intelligence'),
                          t('advisorPanel.styles.passiveAggressive'),
                          t('advisorPanel.styles.corporate'),
                          t('advisorPanel.styles.enthusiastic'),
                        ].map((example) => (
                          <button
                            key={example}
                            type="button"
                            disabled={!saveLoaded || saving}
                            onClick={() => editInstructions(example)}
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
                      {saving ? t('advisorPanel.saving') : t('advisorPanel.saveStyle')}
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
                      {t('advisorPanel.loadSaveHelp')}
                    </p>
                  )}
                </div>
              </div>

              {/* Footer energy line */}
              <div className="energy-line" />
            </div>
    </Modal>
  )
}
