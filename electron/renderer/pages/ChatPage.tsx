import { useState, useCallback, useRef, useEffect } from 'react'
import ChatMessage from '../components/ChatMessage'
import ChatInput from '../components/ChatInput'
import { useBackend, ChatResponse, isChatRetryResponse } from '../hooks/useBackend'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  responseTimeMs?: number
  toolsUsed?: string[]
  isError?: boolean
}

/**
 * ChatPage - Main chat interface for interacting with the Stellaris advisor
 *
 * Implements UI-003 criteria:
 * - ChatInput sends message on Enter
 * - ChatMessage renders user and assistant messages differently
 * - Shows loading state during API call
 * - Shows error messages on failure
 * - Messages list scrolls to bottom on new message
 */
function ChatPage() {
  const backend = useBackend()
  const [messages, setMessages] = useState<Message[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [sessionKey] = useState(() => `chat-${Date.now()}`)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Track mounted state to prevent state updates after unmount
  const isMountedRef = useRef(true)

  // Cleanup on unmount
  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
    }
  }, [])

  // Scroll to bottom when messages change
  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, scrollToBottom])

  const handleSend = useCallback(async (text: string) => {
    // Add user message
    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: text,
      timestamp: new Date(),
    }
    setMessages(prev => [...prev, userMessage])
    setIsLoading(true)

    try {
      const result = await backend.chat(text, sessionKey)

      // Only update state if component is still mounted
      if (!isMountedRef.current) return

      if (result.error) {
        // API error (connection failure, etc.)
        const errorMessage: Message = {
          id: `error-${Date.now()}`,
          role: 'assistant',
          content: result.error,
          timestamp: new Date(),
          isError: true,
        }
        setMessages(prev => [...prev, errorMessage])
      } else if (result.data) {
        if (isChatRetryResponse(result.data)) {
          // Precompute not ready - show retry message
          const retryMessage: Message = {
            id: `retry-${Date.now()}`,
            role: 'assistant',
            content: `The advisor is still analyzing your save file. Please try again in ${Math.ceil(result.data.retry_after_ms / 1000)} seconds.`,
            timestamp: new Date(),
            isError: true,
          }
          setMessages(prev => [...prev, retryMessage])
        } else {
          // Success - add assistant response
          const chatResponse = result.data as ChatResponse
          const assistantMessage: Message = {
            id: `assistant-${Date.now()}`,
            role: 'assistant',
            content: chatResponse.text,
            timestamp: new Date(),
            responseTimeMs: chatResponse.response_time_ms,
            toolsUsed: chatResponse.tools_used,
          }
          setMessages(prev => [...prev, assistantMessage])
        }
      }
    } catch (err) {
      // Only update state if component is still mounted
      if (!isMountedRef.current) return

      // Unexpected error
      const errorMessage: Message = {
        id: `error-${Date.now()}`,
        role: 'assistant',
        content: err instanceof Error ? err.message : 'An unexpected error occurred',
        timestamp: new Date(),
        isError: true,
      }
      setMessages(prev => [...prev, errorMessage])
    } finally {
      if (isMountedRef.current) {
        setIsLoading(false)
      }
    }
  }, [backend, sessionKey])

  return (
    <div className="chat-page">
      <div className="chat-messages">
        {messages.length === 0 ? (
          <div className="chat-welcome">
            <h2>Stellaris Advisor</h2>
            <p>Ask questions about your empire, strategy, or game state.</p>
            <div className="chat-suggestions">
              <p className="suggestions-label">Try asking:</p>
              <ul>
                <li>"What is my empire status?"</li>
                <li>"What should I focus on next?"</li>
                <li>"Analyze my economy"</li>
                <li>"What threats should I be aware of?"</li>
              </ul>
            </div>
          </div>
        ) : (
          messages.map(message => (
            <ChatMessage
              key={message.id}
              role={message.role}
              content={message.content}
              timestamp={message.timestamp}
              responseTimeMs={message.responseTimeMs}
              toolsUsed={message.toolsUsed}
              isError={message.isError}
            />
          ))
        )}
        {isLoading && (
          <div className="chat-loading">
            <div className="loading-indicator">
              <span className="loading-dot"></span>
              <span className="loading-dot"></span>
              <span className="loading-dot"></span>
            </div>
            <span className="loading-text">Advisor is thinking...</span>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>
      <ChatInput
        onSend={handleSend}
        loading={isLoading}
      />
    </div>
  )
}

export default ChatPage
