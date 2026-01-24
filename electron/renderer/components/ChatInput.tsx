import { useState, useCallback, KeyboardEvent } from 'react'

interface ChatInputProps {
  onSend: (message: string) => void
  disabled?: boolean
  loading?: boolean
}

/**
 * ChatInput - Text input for sending chat messages
 *
 * Implements UI-003 criteria:
 * - Sends message on Enter key press
 * - Disabled during loading state
 */
function ChatInput({ onSend, disabled, loading }: ChatInputProps) {
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
    // Send on Enter, but not Shift+Enter (allows for potential multiline later)
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (message.trim() && !isDisabled) {
        onSend(message.trim())
        setMessage('')
      }
    }
  }, [message, isDisabled, onSend])

  return (
    <form className="chat-input" onSubmit={handleSubmit}>
      <input
        type="text"
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={loading ? 'Awaiting response...' : 'Hail the Curators...'}
        disabled={isDisabled}
        autoFocus
      />
      <button type="submit" disabled={isDisabled || !message.trim()}>
        {loading ? 'Sending...' : 'Send'}
      </button>
    </form>
  )
}

export default ChatInput
