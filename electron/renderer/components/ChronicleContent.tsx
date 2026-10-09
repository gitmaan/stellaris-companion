import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChronicleChapter, CurrentEra, NarrativeSection } from '../hooks/useBackend'
import Tooltip from './Tooltip'

interface ChronicleContentProps {
  hideHeader?: boolean
  revision?: string
  coverageDate?: string | null
  mutationBusy?: boolean
  onEdit?: (chapterNumber: number, revision: string, title: string, narrative: string) => Promise<boolean>
  onUndo?: (chapterNumber: number, revision: string) => void
  empireName: string
  chapters: ChronicleChapter[]
  currentEra: CurrentEra | null
  legacyChronicle?: string
  onRegenerate: (chapterNumber: number, regenerationInstructions?: string) => void
  confirmingRegen: number | null
  onCancelRegen: () => void
  regeneratingChapter: number | null
  justRegenerated: number | null
}

/**
 * ChronicleContent - Main content panel for the Galactic Archives
 * Renders all chapters in sequence with current era at the bottom
 */
function ChronicleContent({
  hideHeader = false,
  revision, coverageDate, mutationBusy, onEdit, onUndo,
  empireName,
  chapters,
  currentEra,
  legacyChronicle,
  onRegenerate,
  confirmingRegen,
  onCancelRegen,
  regeneratingChapter,
  justRegenerated,
}: ChronicleContentProps) {
  const { t } = useTranslation()
  return (
    <article className="max-w-[800px] mx-auto">
      {/* Empire header */}
      {!hideHeader && <header className="chronicle-header text-center mb-4 lg:mb-6 relative">
        <ChronicleHeading empireName={empireName} coverageDate={coverageDate} />
        <div className="energy-line mt-4 max-w-[200px] mx-auto" />
      </header>}

      {chapters.length === 0 && !currentEra && legacyChronicle?.trim() && (
        <section className="chronicle-narrative text-base leading-relaxed text-text-primary">
          {renderNarrative(legacyChronicle)}
        </section>
      )}

      {chapters.length === 0 && !currentEra && !legacyChronicle?.trim() && (
        <div className="flex flex-col items-center justify-center text-center text-text-secondary text-sm h-[200px] gap-3">
          <h2>{t('chronicle.page.emptyTitle')}</h2>
          <p>{t('chronicle.page.emptyBody')}</p>
        </div>
      )}

      {chapters.map(chapter => (
        <ChapterBlock
          key={chapter.number}
          chapter={chapter}
          revision={revision}
          mutationBusy={mutationBusy}
          onEdit={onEdit}
          onUndo={onUndo}
          onRegenerate={onRegenerate}
          confirmingRegen={confirmingRegen}
          onCancelRegen={onCancelRegen}
          regeneratingChapter={regeneratingChapter}
          justRegenerated={justRegenerated}
        />
      ))}

      {currentEra && <CurrentEraBlock currentEra={currentEra} />}
    </article>
  )
}

export function ChronicleHeading({ empireName, coverageDate, compact = false }: {
  empireName: string
  coverageDate?: string | null
  compact?: boolean
}) {
  const { t } = useTranslation()
  const title = t('chronicle.content.title', { empireName })
  return <div className="min-w-0">
    <h1 title={title} className={`chronicle-display-title font-display tracking-wide text-text-primary uppercase ${compact ? 'text-sm leading-snug line-clamp-2' : 'text-lg lg:text-2xl break-words'}`}>
      <span aria-hidden="true" className="text-accent-cyan mr-2">◈</span>
      {title}
    </h1>
    {coverageDate && <p className={`${compact ? 'mt-1 text-[11px]' : 'mt-3 text-xs'} text-text-secondary`}>{t('continuity.storyCoverage', { date: coverageDate })}</p>}
  </div>
}

/**
 * Single chapter block with its own memoized narrative
 */
function ChapterBlock({
  chapter, revision, mutationBusy, onEdit, onUndo,
  onRegenerate,
  confirmingRegen,
  onCancelRegen,
  regeneratingChapter,
  justRegenerated,
}: {
  chapter: ChronicleChapter
  revision?: string
  mutationBusy?: boolean
  onEdit?: ChronicleContentProps['onEdit']
  onUndo?: ChronicleContentProps['onUndo']
  onRegenerate: (chapterNumber: number, regenerationInstructions?: string) => void
  confirmingRegen: number | null
  onCancelRegen: () => void
  regeneratingChapter: number | null
  justRegenerated: number | null
}) {
  const { t, i18n } = useTranslation()
  const isRegenerating = regeneratingChapter === chapter.number
  const wasJustRegenerated = justRegenerated === chapter.number
  const isConfirming = confirmingRegen === chapter.number
  const [regenInstructions, setRegenInstructions] = useState('')
  const [editing, setEditing] = useState(false)
  const [draftTitle, setDraftTitle] = useState('')
  const [draftNarrative, setDraftNarrative] = useState('')
  const [editRevision, setEditRevision] = useState('')
  const [saving, setSaving] = useState(false)
  const busy = Boolean(mutationBusy || saving || regeneratingChapter !== null)


  const renderedNarrative = useMemo(
    () => {
      if (chapter.sections?.length) {
        return renderSections(chapter.sections, chapter.epigraph)
      }
      return chapter.narrative ? renderNarrative(chapter.narrative) : []
    },
    [chapter.narrative, chapter.sections, chapter.epigraph]
  )

  return (
    <div id={`chapter-${chapter.number}`} data-reading-id={chapter.id || chapter.start_date} data-reading-version={readingVersion(chapter.narrative)} className={`chronicle-chapter stellaris-panel rounded-lg p-4 lg:p-8 relative mb-8 ${wasJustRegenerated ? 'animate-highlight-flash' : ''}`}>
      {/* Regenerating overlay */}
      {isRegenerating && (
        <div className="absolute inset-0 bg-bg-primary/90 backdrop-blur-sm rounded-lg flex flex-col items-center justify-center gap-4 z-10">
          <div className="w-12 h-12 border-2 border-accent-cyan border-t-transparent rounded-full animate-spin-loader shadow-glow" />
          <p className="text-text-secondary italic text-sm">{t('chronicle.content.rewriting')}</p>
        </div>
      )}

      {/* Chapter header */}
      <div className="chapter-header flex justify-between items-start gap-3 mb-3 pb-3 lg:mb-6 lg:pb-4 border-b border-border">
        <div className="chapter-heading flex flex-col gap-1 lg:gap-2 min-w-0 flex-1">
          <span className="text-xs font-semibold text-accent-cyan uppercase tracking-wider flex items-center gap-2">
            <span>◇</span>
            {t('chronicle.content.chapter', { number: /^(ja|zh)/.test(i18n.language) ? chapter.number : toRoman(chapter.number) })}
          </span>
          <h2 className="chapter-title text-xl font-semibold text-text-primary m-0">{cleanTitle(chapter.title)}</h2>
          <span className="chapter-dates text-sm text-text-secondary font-mono">{chapter.start_date} – {chapter.end_date}</span>
        </div>
        <div className="flex items-center gap-2 text-lg">
          {chapter.context_stale && (
            <Tooltip content={t('chronicle.content.staleTooltip')} position="left">
              <span className="text-accent-yellow ">⚠</span>
            </Tooltip>
          )}
          {chapter.is_finalized && (
            <Tooltip content={t('chronicle.content.finalizedTooltip')} position="left">
              <span className="text-accent-cyan/60 ">◆</span>
            </Tooltip>
          )}
        </div>
      </div>

      {editing && <div className="mb-6 space-y-3 rounded border border-accent-cyan/30 bg-black/20 p-4">
        <label className="block text-xs text-text-secondary">{t('continuity.chapterTitle')}
          <input aria-label={t('continuity.chapterTitle')} value={draftTitle} maxLength={200} onChange={event => setDraftTitle(event.target.value)} disabled={saving} className="mt-1 w-full rounded border border-border bg-bg-primary px-3 py-2 text-sm text-text-primary" />
        </label>
        <label className="block text-xs text-text-secondary">{t('continuity.chapterText')}
          <textarea aria-label={t('continuity.chapterText')} value={draftNarrative} maxLength={100000} rows={12} onChange={event => setDraftNarrative(event.target.value)} disabled={saving} className="mt-1 w-full rounded border border-border bg-bg-primary px-3 py-2 text-sm leading-relaxed text-text-primary" />
        </label>
        <p className="text-xs text-text-muted">{t('continuity.editProtection')}</p>
        <div className="flex gap-3">
          <button type="button" disabled={busy || !draftTitle.trim() || !draftNarrative.trim()} className="rounded bg-accent-cyan px-4 py-2 text-sm text-bg-primary disabled:opacity-40" onClick={async () => {
            if (!onEdit) return
            setSaving(true)
            try { if (await onEdit(chapter.number, editRevision, draftTitle.trim(), draftNarrative.trim())) setEditing(false) }
            finally { setSaving(false) }
          }}>{t('continuity.saveChanges')}</button>
          <button type="button" disabled={saving} className="px-3 py-2 text-sm text-text-secondary" onClick={() => setEditing(false)}>{t('chronicle.content.cancel')}</button>
        </div>
      </div>}

      {/* Chapter narrative */}
      <div className={`chronicle-narrative text-base leading-relaxed text-text-primary ${isRegenerating ? 'blur-sm' : ''} ${editing ? 'hidden' : ''}`}>
        {renderedNarrative}
      </div>

      {/* Regenerate controls */}
      {!editing && !isRegenerating && (chapter.can_regenerate || revision) && (
        <div className="mt-8 pt-4 border-t border-border">
          {isConfirming ? (
            <div className="bg-accent-yellow/10 border border-accent-yellow/30 rounded-lg p-4">
              <p className="text-sm text-text-secondary mb-3 leading-relaxed">
                {t('chronicle.content.regenerateWarning')}
              </p>
              <textarea
                value={regenInstructions}
                onChange={(e) => setRegenInstructions(e.target.value)}
                placeholder={t('chronicle.content.regenPlaceholder')}
                maxLength={300}
                rows={2}
                className="w-full px-3 py-2 mb-3 border border-accent-yellow/30 rounded-md bg-bg-primary/50 text-text-primary text-sm font-sans outline-none transition-all duration-200 focus:border-accent-yellow/60 placeholder:text-text-secondary/50 resize-none"
              />
              <div className="flex items-center gap-3">
                <button
                  className="py-2.5 px-5 border-none rounded-md bg-accent-yellow text-bg-primary text-sm font-semibold uppercase tracking-wider cursor-pointer transition-all duration-200 hover:shadow-glow-yellow-lg"
                  onClick={() => {
                    const instructions = regenInstructions.trim() || undefined
                    setRegenInstructions('')
                    onRegenerate(chapter.number, instructions)
                  }}
                >
                  {t('chronicle.content.confirmRegenerate')}
                </button>
                <button
                  className="py-2.5 px-5 border border-border rounded-md bg-bg-tertiary text-text-primary text-sm font-medium cursor-pointer transition-all duration-200 hover:bg-bg-elevated hover:border-accent-cyan/30"
                  onClick={() => { setRegenInstructions(''); onCancelRegen() }}
                >
                  {t('chronicle.content.cancel')}
                </button>
                {regenInstructions.length > 0 && (
                  <span className="text-xs text-text-secondary ml-auto">{regenInstructions.length}/300</span>
                )}
              </div>
            </div>
          ) : (
            <details className="relative group/actions">
              <summary className="inline-flex cursor-pointer list-none items-center gap-2 rounded border border-border bg-bg-tertiary/50 px-4 py-2 text-xs text-text-secondary hover:border-accent-cyan/30 hover:text-accent-cyan">{t('continuity.chapterActions')} ▾</summary>
              <div className="mt-2 flex flex-wrap gap-2">
                {revision && onEdit && <button type="button" disabled={busy} className="rounded px-3 py-2 text-sm text-text-secondary hover:bg-white/5 disabled:opacity-40" onClick={() => {
                  setDraftTitle(chapter.title); setDraftNarrative(chapter.narrative); setEditRevision(revision); setEditing(true)
                }}>{t('continuity.editText')}</button>}
                {chapter.can_regenerate && <button type="button" disabled={busy} className="rounded px-3 py-2 text-sm text-text-secondary hover:bg-white/5 disabled:opacity-40" onClick={() => onRegenerate(chapter.number)} title={t('chronicle.content.regenerateTitle')}>{t('chronicle.content.regenerateChapter')}</button>}
                {chapter.can_undo && revision && onUndo && <button type="button" disabled={busy} className="rounded px-3 py-2 text-sm text-text-secondary hover:bg-white/5 disabled:opacity-40" onClick={() => onUndo(chapter.number, revision)}>{t('continuity.undoChapter')}</button>}
              </div>
              {chapter.manual_edit_locked && <p className="mt-2 text-xs text-text-muted">{t('continuity.editedByYou')}</p>}
            </details>
          )}
        </div>
      )}

      {/* Chapter summary */}
      {chapter.summary && (
        <div className="mt-6 pt-4 border-t border-border">
          <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2 flex items-center gap-2">
            <span className="text-accent-cyan/60">◇</span>
            {t('chronicle.content.summary')}
          </h4>
          <p className="text-sm text-text-secondary leading-relaxed">{chapter.summary}</p>
        </div>
      )}
    </div>
  )
}

/**
 * Current era block at the bottom
 */
function CurrentEraBlock({ currentEra }: { currentEra: CurrentEra }) {
  const { t } = useTranslation()
  const renderedNarrative = useMemo(
    () => {
      if (currentEra.sections?.length) {
        return renderSections(currentEra.sections)
      }
      return currentEra.narrative ? renderNarrative(currentEra.narrative) : []
    },
    [currentEra.narrative, currentEra.sections]
  )

  return (
    <div id="current-era" data-reading-id={currentEra.start_date} data-reading-version={readingVersion(currentEra.narrative)} className="chronicle-chapter stellaris-panel rounded-lg p-4 lg:p-8 mb-8">
      <div className="chapter-header flex justify-between items-start gap-3 mb-3 pb-3 lg:mb-6 lg:pb-4 border-b border-border">
        <div className="chapter-heading flex flex-col gap-1 lg:gap-2 min-w-0 flex-1">
          <span className="text-xs font-semibold text-accent-yellow uppercase tracking-wider flex items-center gap-2">
            <span>⏳</span>
            {t('chronicle.content.currentEra')}
          </span>
          <h2 className="chapter-title text-xl font-semibold text-text-primary m-0">{t('chronicle.content.storyContinues')}</h2>
          <span className="chapter-dates text-sm text-text-secondary font-mono">{currentEra.start_date} – {currentEra.coverage_date || t('continuity.coverageUnknown')}</span>
        </div>
      </div>

      <div className="chronicle-narrative text-base leading-relaxed text-text-primary">
        {renderedNarrative}
      </div>

      <div className="mt-6 pt-4 border-t border-border text-xs text-text-secondary flex items-center gap-2">
        <span className="text-accent-cyan">◇</span>
        <span>{t('chronicle.content.eventsInEra', { count: currentEra.events_covered })}</span>
      </div>
    </div>
  )
}

function readingVersion(text: string): string {
  // A small content fingerprint prevents restoring into a rewritten paragraph.
  let hash = 0
  for (let i = 0; i < text.length; i += 1) hash = ((hash << 5) - hash + text.charCodeAt(i)) | 0
  return String(hash)
}

/**
 * Render structured sections with distinct visual treatment per type
 */
function renderSections(sections: NarrativeSection[], epigraph?: string): React.ReactNode[] {
  const elements: React.ReactNode[] = []
  let key = 0

  if (epigraph) {
    elements.push(
      <div key={key++} className="chronicle-epigraph text-center italic text-text-secondary mb-8 pb-6 border-b border-border/50">
        <p className="text-base leading-relaxed">{epigraph}</p>
      </div>
    )
  }

  let isFirstProse = true

  sections.forEach((section, i) => {
    if (i > 0) {
      elements.push(
        <div key={key++} className="chronicle-scene-break text-center text-text-secondary/40 my-6 text-sm tracking-[0.5em]">
          *
        </div>
      )
    }

    switch (section.type) {
      case 'prose': {
        const cls = isFirstProse ? 'chronicle-drop-cap mb-4' : 'mb-4'
        elements.push(
          <p key={key++} className={cls}>
            {renderInlineFormatting(section.text)}
          </p>
        )
        isFirstProse = false
        break
      }
      case 'quote':
        elements.push(
          <blockquote key={key++} className="chronicle-quote border-l-[3px] border-accent-cyan/40 pl-4 my-4 italic text-text-secondary">
            <p className="mb-2">{renderInlineFormatting(section.text)}</p>
            {section.attribution && (
              <footer className="text-sm text-text-secondary/70 not-italic">
                — {section.attribution}
              </footer>
            )}
          </blockquote>
        )
        break
      case 'declaration':
        elements.push(
          <div key={key++} className="chronicle-declaration text-center my-6 py-4 border-y border-accent-yellow/30">
            <p className="text-sm uppercase tracking-[0.2em] text-accent-yellow font-semibold">
              {section.text}
            </p>
          </div>
        )
        break
    }
  })

  return elements
}

/**
 * Render narrative text with basic markdown support
 */
function renderNarrative(text: string): React.ReactNode[] {
  if (!text) return []

  const paragraphs = text.split(/\n\n+/)
  const elements: React.ReactNode[] = []

  for (let i = 0; i < paragraphs.length; i++) {
    const para = paragraphs[i].trim()
    if (!para) continue

    // Check for headers (lines starting with # or ##)
    if (para.startsWith('### ')) {
      elements.push(
        <h4 key={i} className="text-base font-semibold text-text-primary mt-6 mb-3 flex items-center gap-2">
          <span className="text-accent-cyan/40 text-sm">›</span>
          {para.slice(4)}
        </h4>
      )
    } else if (para.startsWith('## ')) {
      elements.push(
        <h3 key={i} className="text-lg font-semibold text-text-primary mt-8 mb-3">{para.slice(3)}</h3>
      )
    } else if (para.startsWith('# ')) {
      elements.push(
        <h2 key={i} className="text-xl font-semibold text-text-primary mt-8 mb-4">{para.slice(2)}</h2>
      )
    } else if (para.startsWith('===') || para.startsWith('---')) {
      // Divider
      elements.push(<div key={i} className="energy-line my-8" />)
    } else {
      // Regular paragraph with inline formatting
      elements.push(
        <p key={i} className="mb-4 first:mt-0">
          {renderInlineFormatting(para)}
        </p>
      )
    }
  }

  return elements
}

/**
 * Render inline markdown formatting (bold, italic, quotes)
 */
function renderInlineFormatting(text: string): React.ReactNode {
  // Handle bold (**text**) and italic (*text*)
  const parts: React.ReactNode[] = []
  let remaining = text
  let key = 0

  // Replace line breaks with spaces for continuous paragraphs
  remaining = remaining.replace(/\n/g, ' ')

  while (remaining.length > 0) {
    // Find bold
    const boldMatch = remaining.match(/\*\*([^*]+)\*\*/)
    // Find italic (single asterisk, not double)
    const italicMatch = remaining.match(/(?<!\*)\*([^*]+)\*(?!\*)/)
    // Find quoted text
    const quoteMatch = remaining.match(/"([^"]+)"/)

    // Find which comes first
    let nextMatch: { match: RegExpMatchArray; type: 'bold' | 'italic' | 'quote' } | null = null
    let nextIndex = Infinity

    if (boldMatch) {
      const idx = remaining.indexOf(boldMatch[0])
      if (idx < nextIndex) {
        nextIndex = idx
        nextMatch = { match: boldMatch, type: 'bold' }
      }
    }
    if (italicMatch) {
      const idx = remaining.indexOf(italicMatch[0])
      if (idx < nextIndex) {
        nextIndex = idx
        nextMatch = { match: italicMatch, type: 'italic' }
      }
    }
    if (quoteMatch) {
      const idx = remaining.indexOf(quoteMatch[0])
      if (idx < nextIndex) {
        nextIndex = idx
        nextMatch = { match: quoteMatch, type: 'quote' }
      }
    }

    if (!nextMatch || nextIndex === Infinity) {
      // No more matches
      if (remaining) parts.push(remaining)
      break
    }

    // Add text before match
    if (nextIndex > 0) {
      parts.push(remaining.slice(0, nextIndex))
    }

    // Add formatted element
    const content = nextMatch.match[1]
    switch (nextMatch.type) {
      case 'bold':
        parts.push(<strong key={key++} className="text-accent-cyan font-semibold">{content}</strong>)
        break
      case 'italic':
        parts.push(<em key={key++}>{content}</em>)
        break
      case 'quote':
        parts.push(<q key={key++} className="italic text-text-secondary">{content}</q>)
        break
    }

    remaining = remaining.slice(nextIndex + nextMatch.match[0].length)
  }

  return parts.length === 1 && typeof parts[0] === 'string' ? parts[0] : <>{parts}</>
}

/**
 * Convert number to Roman numerals
 */
function toRoman(num: number): string {
  const romanNumerals: [number, string][] = [
    [10, 'X'],
    [9, 'IX'],
    [5, 'V'],
    [4, 'IV'],
    [1, 'I'],
  ]

  let result = ''
  let remaining = num

  for (const [value, numeral] of romanNumerals) {
    while (remaining >= value) {
      result += numeral
      remaining -= value
    }
  }

  return result
}

/**
 * Clean up chapter title (remove redundant "Chapter X:" prefix)
 */
function cleanTitle(title: string): string {
  return title.replace(/^Chapter\s+\w+:\s*/i, '')
}

export default ChronicleContent
