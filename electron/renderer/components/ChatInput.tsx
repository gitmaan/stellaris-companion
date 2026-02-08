import { useState, useCallback, KeyboardEvent } from 'react'
import { motion } from 'framer-motion'
import Tooltip from './Tooltip'
import PersonIcon from './PersonIcon'

interface ChatInputProps {
  onSend: (message: string) => void
  onOpenAdvisorPanel?: () => void
  disabled?: boolean
  loading?: boolean
}

/**
 * ChatInput - Text input with Cinematic HUD design
 */
function ChatInput({ onSend, onOpenAdvisorPanel, disabled, loading }: ChatInputProps) {
  const [message, setMessage] = useState('')

  const isDisabled = disabled || loading

  const handleSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault()
    if (message.trim() && !isDisabled) {
      onSend(message.trim())
      setMessage('')
    }
  }, [message, isDisabled, onSend])

  const handleKeyDown = useCallback((e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
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
      className="relative flex gap-3 pt-2 pb-1"
      onSubmit={handleSubmit}
    >
      <div className="flex-1 relative group">
        <input
          type="text"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={loading ? 'TRANSMITTING...' : 'HOW CAN WE HELP?'}
          disabled={isDisabled}
          autoFocus
          className="w-full px-4 py-3 border-b border-white/20 bg-black/20 text-text-primary font-mono text-sm outline-none transition-all duration-200 focus:border-accent-cyan focus:bg-accent-cyan/5 disabled:opacity-50 placeholder:text-white/20"
        />
        {/* Animated bottom line on focus */}
        <div className="absolute bottom-0 left-0 w-0 h-px bg-accent-cyan transition-all duration-500 group-focus-within:w-full shadow-[0_0_10px_rgba(0,212,255,0.5)]" />
      </div>

      <Tooltip content="Advisor Info" position="top">
        <button
          type="button"
          onClick={onOpenAdvisorPanel}
          disabled={!onOpenAdvisorPanel}
          className={`h-full aspect-square border-b border-white/20 flex items-center justify-center text-accent-cyan/70 hover:text-accent-cyan hover:border-accent-cyan hover:bg-accent-cyan/5 transition-all duration-200 ${
             !onOpenAdvisorPanel ? 'opacity-30 cursor-not-allowed' : ''
          }`}
        >
          <PersonIcon className="w-4 h-4" />
        </button>
      </Tooltip>

      <motion.button
        type="submit"
        disabled={!canSend}
        whileHover={canSend ? { scale: 1.05 } : undefined}
        whileTap={canSend ? { scale: 0.95 } : undefined}
        className={`px-6 border-b border-white/20 font-display text-xs tracking-widest uppercase transition-all duration-200 ${
          canSend
            ? 'text-accent-cyan hover:border-accent-cyan hover:bg-accent-cyan/10 hover:shadow-glow-sm'
            : 'text-white/20 cursor-not-allowed'
        }`}
      >
        {loading ? (
            <span className="animate-pulse">SENDING</span>
        ) : (
            <span>TRANSMIT</span>
        )}
      </motion.button>
    </form>
  )
}

export default ChatInput
