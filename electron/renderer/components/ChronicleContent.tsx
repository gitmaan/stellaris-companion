import { useMemo, useState } from 'react'
import { ChronicleChapter, CurrentEra, NarrativeSection } from '../hooks/useBackend'
import Tooltip from './Tooltip'

interface ChronicleContentProps {
  empireName: string
  chapters: ChronicleChapter[]
  currentEra: CurrentEra | null
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
  empireName,
  chapters,
  currentEra,
  onRegenerate,
  confirmingRegen,
  onCancelRegen,
  regeneratingChapter,
  justRegenerated,
}: ChronicleContentProps) {
  return (
    <article className="max-w-[800px] mx-auto">
      {/* Empire header */}
      <header className="text-center mb-10 relative">
        <div className="text-accent-cyan text-3xl mb-3">◈</div>
        <h1 className="font-display text-2xl tracking-[0.2em] text-text-primary uppercase">
          The Chronicles of {empireName}
        </h1>
        <div className="energy-line mt-4 max-w-[200px] mx-auto" />
      </header>

      {chapters.length === 0 && !currentEra && (
        <div className="flex items-center justify-center text-text-secondary text-sm h-[200px]">
          <p>Select a chapter to view its content.</p>
        </div>
      )}

      {chapters.map(chapter => (
        <ChapterBlock
          key={chapter.number}
          chapter={chapter}
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

/**
 * Single chapter block with its own memoized narrative
 */
function ChapterBlock({
  chapter,
  onRegenerate,
  confirmingRegen,
  onCancelRegen,
  regeneratingChapter,
  justRegenerated,
}: {
  chapter: ChronicleChapter
  onRegenerate: (chapterNumber: number, regenerationInstructions?: string) => void
  confirmingRegen: number | null
  onCancelRegen: () => void
  regeneratingChapter: number | null
  justRegenerated: number | null
}) {
  const isRegenerating = regeneratingChapter === chapter.number
  const wasJustRegenerated = justRegenerated === chapter.number
  const isConfirming = confirmingRegen === chapter.number
  const [regenInstructions, setRegenInstructions] = useState('')

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
    <div id={`chapter-${chapter.number}`} className={`stellaris-panel rounded-lg p-8 relative mb-8 ${wasJustRegenerated ? 'animate-highlight-flash' : ''}`}>
      {/* Regenerating overlay */}
      {isRegenerating && (
        <div className="absolute inset-0 bg-bg-primary/90 backdrop-blur-sm rounded-lg flex flex-col items-center justify-center gap-4 z-10">
          <div className="w-12 h-12 border-2 border-accent-cyan border-t-transparent rounded-full animate-spin-loader shadow-glow" />
          <p className="text-text-secondary italic text-sm">Rewriting history...</p>
        </div>
      )}

      {/* Chapter header */}
      <div className="flex justify-between items-start mb-6 pb-4 border-b border-border">
        <div className="flex flex-col gap-2">
          <span className="text-xs font-semibold text-accent-cyan uppercase tracking-wider flex items-center gap-2">
            <span>◇</span>
            Chapter {toRoman(chapter.number)}
          </span>
          <h2 className="text-xl font-semibold text-text-primary m-0">{cleanTitle(chapter.title)}</h2>
          <span className="text-sm text-text-secondary font-mono">{chapter.start_date} – {chapter.end_date}</span>
        </div>
        <div className="flex items-center gap-2 text-lg">
          {chapter.context_stale && (
            <Tooltip content="Earlier chapter was regenerated — context may be outdated" position="left">
              <span className="text-accent-yellow ">⚠</span>
            </Tooltip>
          )}
          {chapter.is_finalized && (
            <Tooltip content="Finalized chapter" position="left">
              <span className="text-accent-cyan/60 ">◆</span>
            </Tooltip>
          )}
        </div>
      </div>

      {/* Chapter narrative */}
      <div className={`chronicle-narrative text-base leading-relaxed text-text-primary ${isRegenerating ? 'blur-sm' : ''}`}>
        {renderedNarrative}
      </div>

      {/* Regenerate controls */}
      {chapter.can_regenerate && !isRegenerating && (
        <div className="mt-8 pt-4 border-t border-border">
          {isConfirming ? (
            <div className="bg-accent-yellow/10 border border-accent-yellow/30 rounded-lg p-4">
              <p className="text-sm text-text-secondary mb-3 leading-relaxed">
                Regenerating this chapter will mark later chapters as potentially stale.
                This action uses an API call.
              </p>
              <textarea
                value={regenInstructions}
                onChange={(e) => setRegenInstructions(e.target.value)}
                placeholder="What should change? (optional)"
                maxLength={300}
                rows={2}
                className="w-full px-3 py-2 mb-3 border border-accent-yellow/30 rounded-md bg-bg-primary/50 text-text-primary text-sm font-sans outline-none transition-all duration-200 focus:border-accent-yellow/60 placeholder:text-text-secondary/50 resize-none"
              />
              <div className="flex items-center gap-3">
                <button
                  className="py-2.5 px-5 border-none rounded-md bg-accent-yellow text-bg-primary text-sm font-semibold uppercase tracking-wider cursor-pointer transition-all duration-200 hover:shadow-[0_0_15px_rgba(236,201,75,0.4)]"
                  onClick={() => {
                    const instructions = regenInstructions.trim() || undefined
                    setRegenInstructions('')
                    onRegenerate(chapter.number, instructions)
                  }}
                >
                  Confirm Regenerate
                </button>
                <button
                  className="py-2.5 px-5 border border-border rounded-md bg-bg-tertiary text-text-primary text-sm font-medium cursor-pointer transition-all duration-200 hover:bg-bg-elevated hover:border-accent-cyan/30"
                  onClick={() => { setRegenInstructions(''); onCancelRegen() }}
                >
                  Cancel
                </button>
                {regenInstructions.length > 0 && (
                  <span className="text-xs text-text-secondary ml-auto">{regenInstructions.length}/300</span>
                )}
              </div>
            </div>
          ) : (
            <button
              className="py-2.5 px-5 border border-border rounded-md bg-bg-tertiary/50 text-text-secondary text-sm font-medium cursor-pointer transition-all duration-200 hover:bg-bg-tertiary hover:border-accent-cyan/30 hover:text-accent-cyan flex items-center gap-2"
              onClick={() => onRegenerate(chapter.number)}
              title="Regenerate this chapter"
            >
              <span>↻</span>
              Regenerate Chapter
            </button>
          )}
        </div>
      )}

      {/* Chapter summary */}
      {chapter.summary && (
        <div className="mt-6 pt-4 border-t border-border">
          <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2 flex items-center gap-2">
            <span className="text-accent-cyan/60">◇</span>
            Summary
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
    <div id="current-era" className="stellaris-panel rounded-lg p-8 mb-8">
      <div className="flex justify-between items-start mb-6 pb-4 border-b border-border">
        <div className="flex flex-col gap-2">
          <span className="text-xs font-semibold text-accent-yellow uppercase tracking-wider flex items-center gap-2">
            <span>⏳</span>
            The Current Era
          </span>
          <h2 className="text-xl font-semibold text-text-primary m-0">The Story Continues...</h2>
          <span className="text-sm text-text-secondary font-mono">{currentEra.start_date} – Present</span>
        </div>
      </div>

      <div className="chronicle-narrative text-base leading-relaxed text-text-primary">
        {renderedNarrative}
      </div>

      <div className="mt-6 pt-4 border-t border-border text-xs text-text-secondary flex items-center gap-2">
        <span className="text-accent-cyan">◇</span>
        <span>{currentEra.events_covered} events in this era</span>
      </div>
    </div>
  )
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
