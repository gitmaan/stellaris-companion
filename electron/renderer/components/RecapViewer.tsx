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
      <div className="flex-1 bg-bg-secondary border border-border rounded-lg p-5 overflow-y-auto flex flex-col items-center justify-center text-text-secondary gap-3">
        <div className="flex gap-1">
          <span className="w-2 h-2 rounded-full bg-accent-blue animate-bounce-dot animate-bounce-dot-1"></span>
          <span className="w-2 h-2 rounded-full bg-accent-blue animate-bounce-dot animate-bounce-dot-2"></span>
          <span className="w-2 h-2 rounded-full bg-accent-blue animate-bounce-dot animate-bounce-dot-3"></span>
        </div>
        <p>Generating recap...</p>
      </div>
    )
  }

  if (!recap) {
    return (
      <div className="flex-1 bg-bg-secondary border border-border rounded-lg p-5 overflow-y-auto flex items-center justify-center text-text-secondary text-sm">
        <p>Select a session and generate a recap to see the summary here.</p>
      </div>
    )
  }

  return (
    <div className="flex-1 bg-bg-secondary border border-border rounded-lg p-5 overflow-y-auto">
      {(dateRange || eventsSummarized !== undefined) && (
        <div className="flex gap-4 mb-4 pb-3 border-b border-border text-[13px] text-text-secondary">
          {dateRange && <span className="text-text-primary">{dateRange}</span>}
          {eventsSummarized !== undefined && (
            <span className="text-accent-blue">{eventsSummarized} events summarized</span>
          )}
        </div>
      )}
      <div className="text-sm leading-relaxed text-text-primary">
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
      elements.push(<ul key={`list-${elements.length}`} className="my-0 mb-2 pl-5 list-disc">{listItems}</ul>)
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
        <li key={`li-${i}`} className="mb-1 text-text-primary">{renderInline(content)}</li>
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
          <h3 key={`h-${i}`} className="text-lg font-semibold text-text-primary m-0 mb-2">{renderInline(line)}</h3>
        )
      } else if (line.endsWith(':')) {
        // Section header
        elements.push(
          <h4 key={`h-${i}`} className="text-[15px] font-semibold text-text-primary mt-4 mb-2">{renderInline(line)}</h4>
        )
      } else {
        elements.push(
          <p key={`p-${i}`} className="m-0 mb-1">{renderInline(line)}</p>
        )
      }
    } else {
      elements.push(
        <p key={`p-${i}`} className="m-0 mb-1">{renderInline(line)}</p>
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
        <code key={`code-${key++}`} className="font-mono text-[13px] bg-bg-tertiary py-0.5 px-1.5 rounded text-accent-blue">
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
