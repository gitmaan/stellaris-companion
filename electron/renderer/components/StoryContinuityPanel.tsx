import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import ReactMarkdown from 'react-markdown'
import useBackend, { type StoryContinuationResponse } from '../hooks/useBackend'
import { HUDButton } from './hud/HUDButton'
import Modal from './Modal'

/** A shared, read-only earlier-story reader; choosing ancestry never moves empire data. */
export default function StoryContinuityPanel({ saveId, isActive = true, offerRelink = false }: {
  saveId: string | null
  isActive?: boolean
  /** Show a quiet way to link an earlier story after declining, disconnecting or rewinding. */
  offerRelink?: boolean
}) {
  const { t, i18n } = useTranslation()
  const backend = useBackend()
  const [story, setStory] = useState<StoryContinuationResponse | null>(null)
  const [predecessor, setPredecessor] = useState('')
  const [open, setOpen] = useState(false)
  const [choosing, setChoosing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(false)
  const generation = useRef(0)
  const savingRef = useRef(false)

  const refresh = useCallback(async () => {
    if (!saveId || !isActive || savingRef.current) return
    const token = ++generation.current
    const result = await backend.story(saveId)
    if (generation.current !== token) return
    setStory(result.data ?? null)
    setPredecessor(previous => result.data?.candidates.some(candidate => candidate.save_id === previous)
      ? previous : result.data?.candidates[0]?.save_id ?? '')
  }, [backend, saveId, isActive])

  useEffect(() => {
    setStory(null)
    setOpen(false)
    setChoosing(false)
    setSaving(false)
    savingRef.current = false
    setError(false)
    void refresh()
    return () => { generation.current += 1 }
  }, [refresh, i18n.resolvedLanguage])

  useEffect(() => {
    if (!isActive) return
    let lastObservation = ''
    const unsubscribe = window.electronAPI?.onBackendStatus(status => {
      const observation = `${status?.save_id}:${status?.game_date}`
      if (observation !== lastObservation) {
        lastObservation = observation
        void refresh()
      }
    })
    const changed = () => { void refresh() }
    window.addEventListener('story-continuation-changed', changed)
    return () => {
      unsubscribe?.()
      window.removeEventListener('story-continuation-changed', changed)
    }
  }, [isActive, refresh])

  const decide = async (parent: string | null) => {
    if (!saveId || !story || saving) return
    const token = ++generation.current
    savingRef.current = true
    setSaving(true)
    setError(false)
    const result = await backend.setStory(saveId, parent, story.offer_revision)
    if (token !== generation.current) return
    savingRef.current = false
    setSaving(false)
    if (!result.data) {
      setError(true)
      void refresh()
      return
    }
    setStory(result.data)
    setOpen(false)
    setChoosing(false)
    window.dispatchEvent(new CustomEvent('story-continuation-changed', { detail: { saveId } }))
  }

  if (!story || story.save_id !== saveId) return null
  const linkable = story.can_decide && story.candidates.length > 0
  const offered = linkable && !story.decision
  const linked = story.status === 'continued' && story.parts.length > 0
  const relinkable = offerRelink && linkable && !!story.decision && !linked
  if (!offered && !relinkable && !linked && story.status !== 'rewound' && !error) return null
  const chooser = (secondary: JSX.Element) => <div className="flex flex-wrap items-center gap-3">
    <div className="min-w-0 flex-1 basis-48">
      <p className="font-semibold text-text-primary">{t('story.offer')}</p>
      <p className="mt-1 leading-relaxed">{t('story.explanation')}</p>
    </div>
    <label className="min-w-0 flex-1 basis-48">
      <span className="sr-only">{t('story.predecessor')}</span>
      <select value={predecessor} onChange={event => setPredecessor(event.target.value)} disabled={saving}
        className="w-full rounded border border-border bg-bg-secondary p-2 text-text-primary">
        {story.candidates.map(candidate => <option key={candidate.save_id} value={candidate.save_id}>
          {candidate.empire_name} · {candidate.game_date}
        </option>)}
      </select>
    </label>
    <HUDButton type="button" disabled={saving || !predecessor} onClick={() => void decide(predecessor)}>{t('story.continue')}</HUDButton>
    {secondary}
  </div>

  return (
    <section aria-label={t('story.title')} className="shrink-0 my-2 rounded border border-accent-cyan/25 bg-accent-cyan/5 p-3 text-xs text-text-secondary">
      {offered && chooser(<HUDButton type="button" variant="secondary" disabled={saving} onClick={() => void decide(null)}>{t('story.separate')}</HUDButton>)}
      {relinkable && (choosing
        ? chooser(<HUDButton type="button" variant="secondary" disabled={saving} onClick={() => setChoosing(false)}>{t('common.cancel')}</HUDButton>)
        : <div className="flex flex-wrap items-center justify-between gap-2">
          <span>{t('story.keptSeparate')}</span>
          <HUDButton type="button" variant="secondary" onClick={() => setChoosing(true)}>{t('story.link')}</HUDButton>
        </div>)}
      {linked && <div className="flex flex-wrap items-center justify-between gap-2">
        <span>{t('story.connected', { empire: story.parts[story.parts.length - 1].empire_name })}</span>
        <HUDButton type="button" variant="secondary" onClick={() => setOpen(true)}>{t('story.readEarlier')}</HUDButton>
      </div>}
      {story.status === 'rewound' && <p role="status">{t('story.rewound')}</p>}
      {error && <p role="alert" className="mt-2 text-accent-yellow">{t('story.changed')}</p>}
      <Modal open={open && isActive} onClose={() => setOpen(false)} label={t('story.readEarlier')} className="w-full max-w-3xl flex flex-col">
        <header className="shrink-0 flex items-center justify-between gap-3 border-b border-border p-4">
          <h2 className="font-display text-accent-cyan">{t('story.readEarlier')}</h2>
          <HUDButton type="button" variant="secondary" onClick={() => setOpen(false)}>{t('common.close')}</HUDButton>
        </header>
        <div className="min-h-0 overflow-y-auto custom-scrollbar p-4 space-y-6">
          <p className="text-xs leading-relaxed">{t('story.archiveNote')}</p>
          {story.parts.map(part => <article key={part.save_id} className="space-y-3">
            <h3 className="font-display text-text-primary">{part.empire_name} · {part.game_date}</h3>
            {part.chronicle ? <div className="prose prose-invert prose-sm max-w-none text-text-secondary">
              <ReactMarkdown skipHtml components={{ a: ({ children }) => <span>{children}</span>, img: () => null }}>{part.chronicle}</ReactMarkdown>
            </div> : <p>{t('story.noEarlierProse')}</p>}
            {part.discussions.length > 0 && <details className="rounded border border-border p-3">
              <summary className="cursor-pointer text-text-primary">{t('story.discussions')}</summary>
              {part.discussions.map((turn, index) => <div key={index} className="mt-4 space-y-2 whitespace-pre-wrap break-words">
                <p className="text-text-muted">{turn.game_date}</p>
                <p className="text-accent-cyan">{turn.question}</p>
                <p>{turn.answer}</p>
              </div>)}
            </details>}
          </article>)}
          {story.can_decide && <HUDButton type="button" variant="secondary" disabled={saving} onClick={() => void decide(null)}>{t('story.disconnect')}</HUDButton>}
        </div>
      </Modal>
    </section>
  )
}
