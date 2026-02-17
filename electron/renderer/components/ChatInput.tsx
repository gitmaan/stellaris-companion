import { useState, useCallback, useLayoutEffect, useEffect, useRef, KeyboardEvent } from 'react'
import { motion } from 'framer-motion'
import Tooltip from './Tooltip'
import PersonIcon from './PersonIcon'

interface ChatInputProps {
  onSend: (message: string) => void
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
function ChatInput({ onSend, onOpenAdvisorPanel, disabled, loading }: ChatInputProps) {
  const [message, setMessage] = useState('')
  const [maxTextareaHeight, setMaxTextareaHeight] = useState(() => getViewportAwareMaxHeight())
  const textareaRef = useRef<HTMLTextAreaElement>(null)

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

  const handleSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault()
    if (message.trim() && !isDisabled) {
      onSend(message.trim())
      setMessage('')
    }
  }, [message, isDisabled, onSend])

  const handleKeyDown = useCallback((e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      if (message.trim() && !isDisabled) {
        onSend(message.trim())
        setMessage('')
      }
    }
  }, [message, isDisabled, onSend])

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
          placeholder={loading ? 'TRANSMITTING...' : 'HOW CAN WE HELP?'}
          disabled={isDisabled}
          autoFocus
          rows={1}
          className="w-full px-3 py-2.5 pr-44 bg-transparent text-text-primary font-mono text-sm leading-relaxed outline-none transition-[background-color] duration-200 disabled:opacity-50 placeholder:text-white/20 resize-none min-h-[48px] composer-scrollbar"
        />
      </div>

      <div className="absolute right-3 bottom-3 z-10 flex items-center gap-2">
        <Tooltip content="Advisor Info" position="top">
          <button
            type="button"
            onClick={onOpenAdvisorPanel}
            disabled={!onOpenAdvisorPanel}
            className={`h-9 w-9 rounded-sm border border-white/10 flex items-center justify-center text-accent-cyan/70 hover:text-accent-cyan hover:border-accent-cyan/50 hover:bg-accent-cyan/10 transition-all duration-200 ${
              !onOpenAdvisorPanel ? 'opacity-30 cursor-not-allowed' : ''
            }`}
          >
            <PersonIcon className="w-4 h-4" />
          </button>
        </Tooltip>

        <motion.button
          type="submit"
          disabled={!canSend}
          whileHover={canSend ? { scale: 1.03 } : undefined}
          whileTap={canSend ? { scale: 0.97 } : undefined}
          className={`h-9 px-4 rounded-sm border font-display text-xs tracking-[0.18em] uppercase transition-all duration-200 ${
            canSend
              ? 'border-accent-cyan/45 text-accent-cyan hover:bg-accent-cyan/12 hover:shadow-glow-sm'
              : 'border-white/10 text-white/25 cursor-not-allowed'
          }`}
        >
          {loading ? (
            <span className="animate-pulse">SENDING</span>
          ) : (
            <span>TRANSMIT</span>
          )}
        </motion.button>
      </div>
    </form>
  )
}

export default ChatInput
