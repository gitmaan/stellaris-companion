import { forwardRef, memo } from 'react'
import type { MouseEvent } from 'react'
import { motion } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import type { Components } from 'react-markdown'
import { HUDMicro } from './hud/HUDText'

interface ChatMessageProps {
  role: 'user' | 'assistant'
  content: string
  timestamp?: Date
  responseTimeMs?: number
  isError?: boolean
  onReport?: () => void
}

const messageVariants = {
  initial: (role: 'user' | 'assistant') => ({
    opacity: 0,
    x: role === 'user' ? 20 : -20,
    y: 10,
  }),
  animate: {
    opacity: 1,
    x: 0,
    y: 0,
  },
}

function isSafeHttpUrl(href: string): boolean {
  try {
    const parsed = new URL(href)
    return parsed.protocol === 'http:' || parsed.protocol === 'https:'
  } catch {
    return false
  }
}

const markdownComponents: Components = {
  a: ({ href, children }) => {
    const safeHref = typeof href === 'string' && isSafeHttpUrl(href) ? href : null

    if (!safeHref) {
      return (
        <span
          className="text-text-secondary/70 underline decoration-dotted cursor-not-allowed"
          title="Blocked non-http(s) link"
        >
          {children}
        </span>
      )
    }

    const onClick = async (event: MouseEvent<HTMLAnchorElement>) => {
      event.preventDefault()
      try {
        const result = await window.electronAPI?.openExternal(safeHref)
        if (!result?.success) {
          console.warn(`Failed to open external link: ${safeHref}`)
        }
      } catch (err) {
        console.warn(`Failed to open external link: ${safeHref}`, err)
      }
    }

    return (
      <a
        href={safeHref}
        target="_blank"
        rel="noopener noreferrer"
        onClick={onClick}
        className="text-accent-cyan underline decoration-accent-cyan/60 hover:text-accent-cyan/90"
      >
        {children}
      </a>
    )
  },
}

/**
 * ChatMessage - Data Log Style
 */
const ChatMessage = forwardRef<HTMLDivElement, ChatMessageProps>(function ChatMessage(
  { role, content, timestamp, responseTimeMs, isError, onReport }: ChatMessageProps,
  ref,
) {
  const formatTime = (date: Date) => {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
  }

  const isUser = role === 'user'

  const headerColor = isError ? 'text-accent-red' : isUser ? 'text-accent-cyan' : 'text-accent-teal'
  const bodyTextSize = role === 'assistant' ? 'text-base' : 'text-sm'

  return (
    <motion.div
      ref={ref}
      className={`max-w-[85%] mb-2 ${isUser ? 'self-end' : 'self-start'}`}
      custom={role}
      variants={messageVariants}
      initial="initial"
      animate="animate"
      transition={{ duration: 0.2 }}
    >
      <div className={`relative px-4 py-3 rounded-lg border transition-all duration-200 group ${
        isError
          ? 'bg-accent-red/10 border-accent-red/50'
          : isUser
            ? 'bg-accent-cyan/10 border-accent-cyan/30 rounded-br-sm hover:bg-accent-cyan/15'
            : 'stellaris-panel rounded-bl-sm'
      }`}>
        {/* Header Line */}
        <div className="flex items-baseline gap-3 mb-1">
          <span className={`font-mono text-[13px] font-bold tracking-wide ${headerColor}`}>
             {isUser ? 'CMD_INPUT' : 'SYS_RESPONSE'}
          </span>
          {timestamp && (
             <span className="font-mono text-[10px] text-white/30">
                 T-{formatTime(timestamp)}
             </span>
          )}
          {/* Decorative filler line */}
          <div className="flex-1 h-px bg-white/5 group-hover:bg-white/10 transition-colors" />
        </div>

        {/* Content */}
        <div className={`${bodyTextSize} leading-relaxed ${isError ? 'text-accent-red' : 'advisor-body-copy text-text-primary/90'}`}>
            {role === 'assistant' ? (
              <div className="markdown-content font-sans">
                <ReactMarkdown skipHtml components={markdownComponents}>{content}</ReactMarkdown>
              </div>
            ) : (
              <div className="font-mono text-white/80 whitespace-pre-wrap">{content}</div>
            )}
        </div>

        {/* Footer Metadata (Tech Readout) */}
        {!isUser && !isError && (responseTimeMs !== undefined || !!onReport) && (
          <div className="flex items-center gap-4 mt-2 pt-1 border-t border-white/5 opacity-50 group-hover:opacity-100 transition-opacity">
              {responseTimeMs !== undefined && (
                <HUDMicro>LATENCY: {(responseTimeMs / 1000).toFixed(3)}s</HUDMicro>
              )}
              {onReport && (
                <button
                  type="button"
                  onClick={onReport}
                  className="font-mono text-[10px] uppercase tracking-wide text-accent-cyan/80 hover:text-accent-cyan transition-colors"
                  title="Report this response"
                >
                  Report
                </button>
              )}
          </div>
        )}
      </div>
    </motion.div>
  )
})

export default memo(ChatMessage)
