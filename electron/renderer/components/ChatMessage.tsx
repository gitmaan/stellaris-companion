import { forwardRef } from 'react'
import ReactMarkdown from 'react-markdown'

interface ChatMessageProps {
  role: 'user' | 'assistant'
  content: string
  timestamp?: Date
  responseTimeMs?: number
  toolsUsed?: string[]
  isError?: boolean
}

/**
 * ChatMessage - Renders a single chat message
 *
 * Implements UI-003 criteria:
 * - Renders user and assistant messages differently via CSS classes
 * - Shows error messages with distinct styling (isError prop)
 * - Displays optional metadata (response time, tools used)
 */
const ChatMessage = forwardRef<HTMLDivElement, ChatMessageProps>(function ChatMessage(
  { role, content, timestamp, responseTimeMs, toolsUsed, isError }: ChatMessageProps,
  ref,
) {
  const formatTime = (date: Date) => {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  const roleLabel = role === 'user' ? 'You' : 'Advisor'

  return (
    <div ref={ref} className={`chat-message ${role}${isError ? ' error' : ''}`}>
      <div className="message-header">
        <span className="message-role">{roleLabel}</span>
        {timestamp && (
          <span className="message-time">{formatTime(timestamp)}</span>
        )}
      </div>
      <div className="message-content">
        {role === 'assistant' ? (
          <ReactMarkdown>{content}</ReactMarkdown>
        ) : (
          content
        )}
      </div>
      {role === 'assistant' && !isError && (responseTimeMs !== undefined || toolsUsed?.length) && (
        <div className="message-meta">
          {responseTimeMs !== undefined && (
            <span className="response-time">{(responseTimeMs / 1000).toFixed(1)}s</span>
          )}
          {toolsUsed && toolsUsed.length > 0 && (
            <span className="tools-used">Tools: {toolsUsed.join(', ')}</span>
          )}
        </div>
      )}
    </div>
  )
})

export default ChatMessage
