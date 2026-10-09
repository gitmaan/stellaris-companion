import { useEffect, useState } from 'react'
import Modal from './Modal'
import { useTranslation } from 'react-i18next'
import PersonIcon from './PersonIcon'

interface ChronicleInfoPanelProps {
  isOpen: boolean
  onClose: () => void
  selectedSaveId: string | null
}

const STYLE_EXAMPLE_KEYS = [
  'chronicle.narrator.examples.deadpan',
  'chronicle.narrator.examples.bureaucratic',
  'chronicle.narrator.examples.tabloid',
  'chronicle.narrator.examples.propaganda',
  'chronicle.narrator.examples.pr',
  'chronicle.narrator.examples.earnings',
]

export default function ChronicleInfoPanel({
  isOpen,
  onClose,
  selectedSaveId,
}: ChronicleInfoPanelProps) {
  const { t } = useTranslation()
  const [customInstructions, setCustomInstructions] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveResult, setSaveResult] = useState<{ ok: boolean; message: string } | null>(null)

  useEffect(() => {
    if (!isOpen) return

    setSaveResult(null)

  }, [isOpen, onClose])

  useEffect(() => {
    if (!isOpen || !selectedSaveId) return

    const load = async () => {
      try {
        const res = await window.electronAPI?.backend?.getChronicleCustom()
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
  }, [isOpen, selectedSaveId])

  const handleApply = async () => {
    if (!window.electronAPI?.backend?.setChronicleCustom) return
    setSaving(true)
    setSaveResult(null)
    try {
      const res = await window.electronAPI.backend.setChronicleCustom(customInstructions)
      if (res && typeof res === 'object' && 'ok' in res && res.ok) {
        setCustomInstructions((res.data.custom_instructions || '') as string)
        setSaveResult({ ok: true, message: t('chronicle.narrator.applySuccess') })
      } else {
        const message = (res as any)?.error || t('chronicle.narrator.applyError')
        setSaveResult({ ok: false, message })
      }
    } catch (e) {
      setSaveResult({ ok: false, message: e instanceof Error ? e.message : t('chronicle.narrator.applyError') })
    } finally {
      setSaving(false)
    }
  }

  const hasSave = !!selectedSaveId

  return (
    <Modal open={isOpen} onClose={onClose} placement="right" label={t('chronicle.narrator.title')} className="w-full">
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
                        {t('chronicle.narrator.title')}
                      </h2>
                      <p className="text-xs text-text-secondary">
                        {t('chronicle.narrator.subtitle')}
                      </p>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={onClose}
                    className="text-text-secondary hover:text-text-primary transition-colors text-lg leading-none px-2 py-1 rounded hover:bg-bg-tertiary/60"
                    aria-label={t('chronicle.narrator.close')}
                  >
                    x
                  </button>
                </div>
              </div>

              {/* Body */}
              <div className="flex-1 overflow-y-auto p-5 space-y-5">
                <div className="stellaris-panel rounded-lg p-4">
                  <p className="text-xs text-text-secondary uppercase tracking-wider font-semibold mb-3 flex items-center gap-2">
                    <span className="text-accent-cyan/60">◇</span>
                    {t('chronicle.narrator.instructions')}
                  </p>
                  <textarea
                    value={customInstructions}
                    onChange={(e) => setCustomInstructions(e.target.value)}
                    placeholder={t('chronicle.narrator.placeholder')}
                    maxLength={500}
                    rows={4}
                    disabled={!hasSave}
                    className="w-full px-4 py-3 border border-border rounded-md bg-bg-primary/50 text-text-primary text-sm font-sans outline-none transition-all duration-200 focus:border-accent-cyan/50 focus:shadow-glow-sm placeholder:text-text-secondary/60 resize-none disabled:opacity-60 disabled:cursor-not-allowed"
                  />

                  {!customInstructions && (
                    <div className="mt-3">
                      <p className="text-[11px] text-text-secondary uppercase tracking-wider mb-2">{t('chronicle.narrator.tryStyle')}</p>
                      <div className="flex flex-wrap gap-1.5">
                        {STYLE_EXAMPLE_KEYS.map((exampleKey) => {
                          const example = t(exampleKey)
                          return (
                            <button
                              key={exampleKey}
                              type="button"
                              disabled={!hasSave}
                              onClick={() => setCustomInstructions(example)}
                              className="px-2.5 py-1.5 text-xs text-text-secondary border border-border/60 rounded bg-bg-primary/30 hover:text-accent-cyan hover:border-accent-cyan/40 hover:bg-accent-cyan/5 transition-all duration-150 text-left disabled:opacity-40 disabled:cursor-not-allowed"
                            >
                              {example}
                            </button>
                          )
                        })}
                      </div>
                    </div>
                  )}
                  <div className="flex items-center justify-between mt-2">
                    <p className="text-xs text-text-secondary m-0">{customInstructions.length}/500</p>
                    <button
                      type="button"
                      onClick={handleApply}
                      disabled={!hasSave || saving}
                      className={`py-2 px-4 border rounded-md text-xs font-semibold uppercase tracking-wider cursor-pointer transition-all duration-200 ${
                        hasSave && !saving
                          ? 'bg-accent-cyan/20 border-accent-cyan/50 text-accent-cyan hover:bg-accent-cyan/30 hover:shadow-glow-sm'
                          : 'bg-bg-tertiary/50 border-border text-text-secondary opacity-50 cursor-not-allowed'
                      }`}
                    >
                      {saving ? t('chronicle.narrator.applying') : t('chronicle.narrator.apply')}
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

                  {!hasSave && (
                    <p className="text-xs text-text-secondary mt-3">
                      {t('chronicle.narrator.selectSave')}
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
