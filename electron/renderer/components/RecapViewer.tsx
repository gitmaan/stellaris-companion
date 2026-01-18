interface RecapViewerProps {
  recap: string | null
  loading?: boolean
  dateRange?: string
  eventsSummarized?: number
}

/**
 * RecapViewer - Renders session recap with markdown-like formatting
 *
 * Supports basic markdown elements:
 * - Headers (lines without leading dash)
 * - List items (lines starting with -)
 * - Inline code (text in backticks)
 * - Bold (**text**)
 */
function RecapViewer({ recap, loading, dateRange, eventsSummarized }: RecapViewerProps) {
  if (loading) {
    return (
      <div className="recap-viewer loading">
        <div className="recap-loading-indicator">
          <span className="loading-dot"></span>
          <span className="loading-dot"></span>
          <span className="loading-dot"></span>
        </div>
        <p>Generating recap...</p>
      </div>
    )
  }

  if (!recap) {
    return (
      <div className="recap-viewer empty">
        <p>Select a session and generate a recap to see the summary here.</p>
      </div>
    )
  }

  return (
    <div className="recap-viewer">
      {(dateRange || eventsSummarized !== undefined) && (
        <div className="recap-meta">
          {dateRange && <span className="recap-date-range">{dateRange}</span>}
          {eventsSummarized !== undefined && (
            <span className="recap-events-count">{eventsSummarized} events summarized</span>
          )}
        </div>
      )}
      <div className="recap-content">
        {renderMarkdown(recap)}
      </div>
    </div>
  )
}

/**
 * Render markdown-like text to React elements
 * Handles: headers, list items, inline code, bold
 */
function renderMarkdown(text: string): React.ReactNode[] {
  const lines = text.split('\n')
  const elements: React.ReactNode[] = []
  let listItems: React.ReactNode[] = []

  const flushList = () => {
    if (listItems.length > 0) {
      elements.push(<ul key={`list-${elements.length}`}>{listItems}</ul>)
      listItems = []
    }
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]

    // Empty line - flush any pending list
    if (line.trim() === '') {
      flushList()
      continue
    }

    // List item
    if (line.startsWith('- ')) {
      const content = line.slice(2)
      listItems.push(
        <li key={`li-${i}`}>{renderInline(content)}</li>
      )
      continue
    }

    // Regular text - flush list first
    flushList()

    // Check if it's a header-like line (first line, or line following empty line with no dash)
    const isHeader = i === 0 ||
      (i > 0 && lines[i - 1].trim() === '') ||
      line.endsWith(':')

    if (isHeader && !line.startsWith(' ')) {
      // Main header (first line)
      if (i === 0 || line.includes('—')) {
        elements.push(
          <h3 key={`h-${i}`} className="recap-header">{renderInline(line)}</h3>
        )
      } else if (line.endsWith(':')) {
        // Section header
        elements.push(
          <h4 key={`h-${i}`} className="recap-section-header">{renderInline(line)}</h4>
        )
      } else {
        elements.push(
          <p key={`p-${i}`} className="recap-line">{renderInline(line)}</p>
        )
      }
    } else {
      elements.push(
        <p key={`p-${i}`} className="recap-line">{renderInline(line)}</p>
      )
    }
  }

  // Flush any remaining list items
  flushList()

  return elements
}

/**
 * Render inline markdown elements (code, bold)
 */
function renderInline(text: string): React.ReactNode {
  // Pattern to match `code` and **bold**
  const parts: React.ReactNode[] = []
  let remaining = text
  let key = 0

  while (remaining.length > 0) {
    // Find the next special marker
    const codeMatch = remaining.match(/`([^`]+)`/)
    const boldMatch = remaining.match(/\*\*([^*]+)\*\*/)

    // Determine which comes first
    const codeIndex = codeMatch ? remaining.indexOf(codeMatch[0]) : -1
    const boldIndex = boldMatch ? remaining.indexOf(boldMatch[0]) : -1

    let nextIndex = -1
    let nextMatch: RegExpMatchArray | null = null
    let isCode = false

    if (codeIndex >= 0 && (boldIndex < 0 || codeIndex < boldIndex)) {
      nextIndex = codeIndex
      nextMatch = codeMatch
      isCode = true
    } else if (boldIndex >= 0) {
      nextIndex = boldIndex
      nextMatch = boldMatch
      isCode = false
    }

    if (nextMatch === null) {
      // No more matches, add remaining text
      if (remaining) {
        parts.push(remaining)
      }
      break
    }

    // Add text before the match
    if (nextIndex > 0) {
      parts.push(remaining.slice(0, nextIndex))
    }

    // Add the formatted element
    if (isCode) {
      parts.push(
        <code key={`code-${key++}`} className="recap-inline-code">
          {nextMatch[1]}
        </code>
      )
    } else {
      parts.push(
        <strong key={`bold-${key++}`}>
          {nextMatch[1]}
        </strong>
      )
    }

    remaining = remaining.slice(nextIndex + nextMatch[0].length)
  }

  return parts.length === 1 && typeof parts[0] === 'string' ? parts[0] : <>{parts}</>
}

export default RecapViewer
