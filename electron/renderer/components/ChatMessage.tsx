import { forwardRef, memo, useState, useEffect, useMemo } from 'react'
import type { MouseEvent } from 'react'
import { motion } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import type { Components } from 'react-markdown'
import { useTranslation } from 'react-i18next'
import { HUDMicro } from './hud/HUDText'
import type { ModelRoutingEvent } from '../hooks/useBackend'
import { motionTiming } from '../lib/motion'

interface ChatMessageProps {
  messageId: string
  role: 'user' | 'assistant'
  content: string
  timestamp?: Date
  gameDate?: string | null
  historySaved?: boolean
  responseTimeMs?: number
  modelDisplay?: string
  modelRouting?: ModelRoutingEvent | null
  isError?: boolean
  actionLabel?: string
  onAction?: () => void
  onReport?: () => void
  onRetry?: () => void
  animateEntrance?: boolean
}

const messageVariants = {
  initial: {
    opacity: 0,
    y: 4,
  },
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

function createMarkdownComponents(blockedLinkTitle: string): Components {
  return {
    a: ({ href, children }) => {
    const safeHref = typeof href === 'string' && isSafeHttpUrl(href) ? href : null

    if (!safeHref) {
      return (
        <span
          className="text-text-secondary/70 underline decoration-dotted cursor-not-allowed"
          title={blockedLinkTitle}
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
}

/**
 * ChatMessage - Data Log Style
 */
const MessageMarkdown = memo(function MessageMarkdown({ content, blockedLinkTitle }: { content: string; blockedLinkTitle: string }) {
  const components = useMemo(() => createMarkdownComponents(blockedLinkTitle), [blockedLinkTitle])
  return <ReactMarkdown skipHtml components={components}>{content}</ReactMarkdown>
})

const ChatMessage = forwardRef<HTMLDivElement, ChatMessageProps>(function ChatMessage(
  {
    messageId,
    role,
    content,
    timestamp,
    gameDate,
    historySaved,
    responseTimeMs,
    modelDisplay,
    modelRouting,
    isError,
    actionLabel,
    onAction,
    onReport,
    onRetry,
    animateEntrance = false,
  }: ChatMessageProps,
  ref,
) {
  const { t, i18n } = useTranslation()
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'failed'>('idle')
  useEffect(() => {
    if (copyState === 'idle') return
    const timer = setTimeout(() => setCopyState('idle'), 2000)
    return () => clearTimeout(timer)
  }, [copyState])
  const copy = async () => {
    try {
      const result = await window.electronAPI?.copyToClipboard(content)
      if (!result?.success) throw new Error('Copy failed')
      setCopyState('copied')
    } catch { setCopyState('failed') }
  }
  const formatTime = (date: Date) => {
    return date.toLocaleTimeString(i18n.language, { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
  }

  const isUser = role === 'user'

  const headerColor = isError ? 'text-accent-red' : isUser ? 'text-accent-cyan' : 'text-accent-teal'
  const bodyTextSize = role === 'assistant' ? 'text-base' : 'text-sm'
  const finalModelDisplay = modelRouting?.final_model_display || modelDisplay
  const routingNotice = modelRouting?.fallback
    ? modelRouting.notice || t('chat.message.routingNotice', { model: finalModelDisplay || 'Gemini Flash-Lite' })
    : null
  const modelReadout = routingNotice
    ? t('chat.message.routingVia', { model: finalModelDisplay || 'GEMINI FLASH-LITE' })
    : finalModelDisplay
      ? t('chat.message.modelReadout', { model: finalModelDisplay })
      : null

  return (
    <motion.div
      ref={ref}
      data-message-id={messageId}
      className={`max-w-[92%] min-w-0 shrink-0 mb-3 ${isUser ? 'self-end' : 'self-start'}`}
      custom={role}
      variants={messageVariants}
      initial={animateEntrance ? 'initial' : false}
      animate="animate"
      transition={{ duration: motionTiming.content }}
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
                <MessageMarkdown content={content} blockedLinkTitle={t('chat.message.blockedLink')} />
              </div>
            ) : (
              <div className="font-mono text-white/80 whitespace-pre-wrap">{content}</div>
            )}
        </div>

        {isError && actionLabel && onAction && (
          <button
            type="button"
            onClick={onAction}
            className="mt-3 border border-accent-red/50 px-3 py-1.5 font-display text-[10px] uppercase tracking-[0.16em] text-accent-red transition-colors hover:border-accent-cyan/70 hover:bg-accent-cyan/10 hover:text-accent-cyan"
          >
            {actionLabel}
          </button>
        )}
        {isError && onRetry && <button type="button" onClick={onRetry} className="mt-3 px-3 py-1.5 text-sm text-accent-cyan border border-accent-cyan/40 rounded">{t('visualQuality.retry')}</button>}

        {/* Response actions and optional technical details */}
        {!isUser && !isError && (
          <div className="mt-2 flex flex-wrap items-start gap-4 border-t border-white/5 pt-2">
              <button type="button" onClick={() => void copy()} className="grid text-left text-xs text-text-secondary hover:text-accent-cyan" aria-label={t('visualQuality.copy')}>
                {['copy', 'copied', 'copyFailed'].map(key => <span key={key} className="invisible col-start-1 row-start-1" aria-hidden="true">{t(`visualQuality.${key}`)}</span>)}
                <span className="col-start-1 row-start-1" aria-hidden="true">{t(copyState === 'copied' ? 'visualQuality.copied' : copyState === 'failed' ? 'visualQuality.copyFailed' : 'visualQuality.copy')}</span>
              </button>
              <span role="status" className="sr-only">{copyState === 'copied' ? t('visualQuality.copied') : copyState === 'failed' ? t('visualQuality.copyFailed') : ''}</span>
              <div className="flex flex-col gap-1">
                {gameDate && <span className="font-mono text-[10px] text-text-muted">{t('continuity.basedOnSave', { date: gameDate })}</span>}
                {historySaved === false && <span className="text-xs text-accent-yellow">{t('continuity.historyNotSaved')}</span>}
              </div>
              {onReport && (
                <button
                  type="button"
                  onClick={onReport}
                  className="font-mono text-[10px] uppercase tracking-wide text-text-muted transition-colors hover:text-accent-cyan"
                  title={t('chat.message.reportTitle')}
                >
                  {t('chat.message.report')}
                </button>
              )}
              {(responseTimeMs !== undefined || modelReadout) && (
                <details className="group/details ml-auto text-right">
                  <summary className="cursor-pointer list-none font-mono text-[10px] uppercase tracking-wide text-text-muted transition-colors hover:text-text-secondary">
                    {t('chat.message.details')}
                  </summary>
                  <div className="mt-2 flex max-w-sm flex-col items-end gap-1">
                    {responseTimeMs !== undefined && (
                      <HUDMicro>{t('chat.message.responseTime', { seconds: (responseTimeMs / 1000).toFixed(2) })}</HUDMicro>
                    )}
                    {modelReadout && (
                      <HUDMicro
                        className={routingNotice ? 'text-accent-yellow/80' : undefined}
                        title={routingNotice || undefined}
                      >
                        {modelReadout}
                      </HUDMicro>
                    )}
                  </div>
                </details>
              )}
          </div>
        )}
      </div>
    </motion.div>
  )
})

export default memo(ChatMessage)
