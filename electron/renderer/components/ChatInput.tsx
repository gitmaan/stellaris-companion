import { useState, useCallback, useLayoutEffect, useEffect, useRef, KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import Tooltip from './Tooltip'
import PersonIcon from './PersonIcon'
import { isCompositionKey } from '../lib/compositionKey'

interface ChatInputProps {
  identityKey?: string
  consumedDraft?: { text: string } | null
  onSend: (message: string) => void | Promise<boolean | void>
  onOpenAdvisorPanel?: () => void
  disabled?: boolean
  loading?: boolean
}

const MIN_TEXTAREA_HEIGHT = 48
const BASE_MAX_TEXTAREA_HEIGHT = 220
const MIN_MAX_TEXTAREA_HEIGHT = 120

function getViewportAwareMaxHeight() {
  if (typeof window === 'undefined') return BASE_MAX_TEXTAREA_HEIGHT
  const viewportCap = Math.floor(window.innerHeight * 0.32)
  return Math.max(MIN_MAX_TEXTAREA_HEIGHT, Math.min(BASE_MAX_TEXTAREA_HEIGHT, viewportCap))
}

/**
 * ChatInput - Text input with Cinematic HUD design
 */
function ChatInput({ identityKey, consumedDraft, onSend, onOpenAdvisorPanel, disabled, loading }: ChatInputProps) {
  const { t } = useTranslation()
  const [message, setMessage] = useState('')
  const [maxTextareaHeight, setMaxTextareaHeight] = useState(() => getViewportAwareMaxHeight())
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const sendingRef = useRef<symbol | null>(null)
  useLayoutEffect(() => { sendingRef.current = null }, [identityKey])
  useLayoutEffect(() => {
    if (consumedDraft) setMessage(current => current.trim() === consumedDraft.text ? '' : current)
  }, [consumedDraft])

  const isDisabled = disabled || loading

  const resizeTextarea = useCallback(() => {
    const textarea = textareaRef.current
    if (!textarea) return

    textarea.style.height = 'auto'
    const nextHeight = Math.min(Math.max(textarea.scrollHeight, MIN_TEXTAREA_HEIGHT), maxTextareaHeight)
    textarea.style.height = `${nextHeight}px`
    textarea.style.overflowY = textarea.scrollHeight > maxTextareaHeight ? 'auto' : 'hidden'
  }, [maxTextareaHeight])

  useEffect(() => {
    const handleResize = () => {
      setMaxTextareaHeight(getViewportAwareMaxHeight())
    }

    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  useLayoutEffect(() => {
    resizeTextarea()
  }, [message, maxTextareaHeight, resizeTextarea])

  const send = useCallback(async () => {
    if (message.trim() && !isDisabled && !sendingRef.current) {
      const submission = Symbol()
      sendingRef.current = submission
      const sent = message.trim()
      setMessage('')
      // Return focus after clicking Send, without stealing it when a reply arrives.
      textareaRef.current?.focus({ preventScroll: true })
      try {
        if (await onSend(sent) === false && sendingRef.current === submission) {
          setMessage(current => current || sent)
        }
      } catch { if (sendingRef.current === submission) setMessage(current => current || sent) }
      finally { if (sendingRef.current === submission) sendingRef.current = null }
    }
  }, [message, isDisabled, onSend])

  const handleSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault(); void send()
  }, [send])

  const handleKeyDown = useCallback((e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !isCompositionKey(e)) {
      e.preventDefault()
      void send()
    }
  }, [send])

  const canSend = !isDisabled && message.trim()

  return (
    <form
      className="relative rounded-lg border border-white/10 bg-black/35 backdrop-blur-sm px-2 py-1.5 flex items-end gap-2 transition-colors duration-200 focus-within:border-accent-cyan/45 focus-within:shadow-focus-cyan"
      onSubmit={handleSubmit}
    >
      <div className="relative group flex-1 min-w-0">
        <textarea
          ref={textareaRef}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={loading ? t('visualQuality.nextQuestion') : t('chat.input.placeholder')}
          aria-label={t('chat.input.placeholder')}
          disabled={disabled}
          autoFocus
          rows={1}
          className="w-full px-3 py-2.5 bg-transparent text-text-primary font-mono text-sm leading-relaxed outline-none transition-[background-color] duration-150 disabled:opacity-50 placeholder:text-text-secondary resize-none min-h-[48px] composer-scrollbar"
        />
      </div>

      <div className="shrink-0 pb-2 flex items-center gap-2">
        <Tooltip content={t('chat.input.advisorInfo')} position="top">
          <button
            type="button"
            onClick={onOpenAdvisorPanel}
            disabled={!onOpenAdvisorPanel}
            aria-label={t('chat.input.advisorInfo')}
            className={`h-9 w-9 rounded-sm border border-white/10 flex items-center justify-center text-accent-cyan/70 hover:text-accent-cyan hover:border-accent-cyan/50 hover:bg-accent-cyan/10 transition-all duration-200 ${
              !onOpenAdvisorPanel ? 'opacity-30 cursor-not-allowed' : ''
            }`}
          >
            <PersonIcon className="w-4 h-4" />
          </button>
        </Tooltip>

        <button
          type="submit"
          disabled={!canSend}
          className={`h-9 px-3 grid rounded-sm border font-display text-xs tracking-wide uppercase transition-colors duration-150 ${
            canSend
              ? 'border-accent-cyan/45 text-accent-cyan hover:bg-accent-cyan/12 hover:shadow-glow-sm'
              : 'border-white/10 text-white/25 cursor-not-allowed'
          }`}
        >
          <span className="invisible col-start-1 row-start-1" aria-hidden="true">{t('chat.input.sending')}</span>
          <span className="invisible col-start-1 row-start-1" aria-hidden="true">{t('chat.input.send')}</span>
          <span className="col-start-1 row-start-1 self-center">{loading ? (
            <span className="animate-pulse">{t('chat.input.sending')}</span>
          ) : (
            <span>{t('chat.input.send')}</span>
          )}</span>
        </button>
      </div>
    </form>
  )
}

export default ChatInput
