import { ChronicleChapter, CurrentEra } from '../hooks/useBackend'

interface ChronicleContentProps {
  empireName: string
  chapter: ChronicleChapter | null
  currentEra: CurrentEra | null
  onRegenerate: (chapterNumber: number) => void
  confirmingRegen: number | null
  onCancelRegen: () => void
  regenerating: boolean
}

/**
 * ChronicleContent - Right panel displaying chapter content
 *
 * Renders:
 * - Empire header
 * - Chapter title and date range
 * - Full narrative text (markdown rendered)
 * - Regenerate button for finalized chapters
 */
function ChronicleContent({
  empireName,
  chapter,
  currentEra,
  onRegenerate,
  confirmingRegen,
  onCancelRegen,
  regenerating,
}: ChronicleContentProps) {
  // Show current era if no chapter selected
  if (currentEra && !chapter) {
    return (
      <article className="chronicle-content">
        <header className="chronicle-header">
          <h1 className="empire-title">THE CHRONICLES OF {empireName.toUpperCase()}</h1>
        </header>

        <div className="chronicle-chapter current-era-content">
          <div className="chapter-header">
            <div className="chapter-title-block">
              <span className="chapter-label">THE CURRENT ERA</span>
              <h2 className="chapter-title">The Story Continues...</h2>
              <span className="chapter-dates">{currentEra.start_date} – Present</span>
            </div>
            <div className="chapter-status">
              <span className="status-current" title="In progress">⏳</span>
            </div>
          </div>

          <div className="chapter-divider" />

          <div className="chapter-narrative">
            {renderNarrative(currentEra.narrative)}
          </div>

          <div className="chapter-meta">
            <span className="meta-events">{currentEra.events_covered} events in this era</span>
          </div>
        </div>
      </article>
    )
  }

  // Show selected chapter
  if (chapter) {
    const isConfirming = confirmingRegen === chapter.number

    return (
      <article className="chronicle-content">
        <header className="chronicle-header">
          <h1 className="empire-title">THE CHRONICLES OF {empireName.toUpperCase()}</h1>
        </header>

        <div className="chronicle-chapter">
          <div className="chapter-header">
            <div className="chapter-title-block">
              <span className="chapter-label">CHAPTER {toRoman(chapter.number)}</span>
              <h2 className="chapter-title">{cleanTitle(chapter.title)}</h2>
              <span className="chapter-dates">{chapter.start_date} – {chapter.end_date}</span>
            </div>
            <div className="chapter-status">
              {chapter.context_stale && (
                <span className="status-stale" title="Earlier chapter was regenerated - context may be outdated">
                  ⚠️
                </span>
              )}
              {chapter.is_finalized && (
                <span className="status-finalized" title="Finalized chapter">🔒</span>
              )}
            </div>
          </div>

          <div className="chapter-divider" />

          <div className="chapter-narrative">
            {renderNarrative(chapter.narrative)}
          </div>

          {/* Regenerate controls */}
          {chapter.can_regenerate && (
            <div className="chapter-actions">
              {isConfirming ? (
                <div className="regen-confirm">
                  <p className="regen-warning">
                    Regenerating this chapter will mark later chapters as potentially stale.
                    This action uses an API call.
                  </p>
                  <div className="regen-buttons">
                    <button
                      className="regen-confirm-btn"
                      onClick={() => onRegenerate(chapter.number)}
                      disabled={regenerating}
                    >
                      {regenerating ? 'Regenerating...' : 'Confirm Regenerate'}
                    </button>
                    <button
                      className="regen-cancel-btn"
                      onClick={onCancelRegen}
                      disabled={regenerating}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  className="chapter-regenerate"
                  onClick={() => onRegenerate(chapter.number)}
                  title="Regenerate this chapter"
                >
                  ↻ Regenerate Chapter
                </button>
              )}
            </div>
          )}

          {chapter.summary && (
            <div className="chapter-summary">
              <h4>Summary</h4>
              <p>{chapter.summary}</p>
            </div>
          )}
        </div>
      </article>
    )
  }

  // No content to show
  return (
    <article className="chronicle-content">
      <header className="chronicle-header">
        <h1 className="empire-title">THE CHRONICLES OF {empireName.toUpperCase()}</h1>
      </header>
      <div className="chronicle-empty-content">
        <p>Select a chapter to view its content.</p>
      </div>
    </article>
  )
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
        <h4 key={i} className="narrative-h4">{para.slice(4)}</h4>
      )
    } else if (para.startsWith('## ')) {
      elements.push(
        <h3 key={i} className="narrative-h3">{para.slice(3)}</h3>
      )
    } else if (para.startsWith('# ')) {
      elements.push(
        <h2 key={i} className="narrative-h2">{para.slice(2)}</h2>
      )
    } else if (para.startsWith('===') || para.startsWith('---')) {
      // Divider
      elements.push(<hr key={i} className="narrative-divider" />)
    } else {
      // Regular paragraph with inline formatting
      elements.push(
        <p key={i} className="narrative-paragraph">
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
        parts.push(<strong key={key++}>{content}</strong>)
        break
      case 'italic':
        parts.push(<em key={key++}>{content}</em>)
        break
      case 'quote':
        parts.push(<q key={key++}>{content}</q>)
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
