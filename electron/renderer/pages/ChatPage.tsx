import { useMemo, useState, useCallback, useRef, useEffect } from 'react'
import ChatMessage from '../components/ChatMessage'
import ChatInput from '../components/ChatInput'
import VirtualChatList from '../components/VirtualChatList'
import { useBackend, ChatResponse, isChatRetryResponse, EmpireType } from '../hooks/useBackend'

// Themed loading messages for different empire types
const LOADING_MESSAGES = {
  universal: [
    'Consulting the Curators',
    'Surveying the situation',
    'Analyzing sensor data',
    'Processing anomaly',
    'Compiling situation report',
    'Running simulations',
    'Accessing the archives',
    'Cross-referencing star charts',
    // Easter eggs
    'Waiting for end-game lag to clear',
    'Checking if the Fallen Empire noticed',
    'Consulting the Shroud',
    'What was, will be',
  ],
  machine: [
    'Processing directive',
    'The network ponders',
    'Calculating optimal outcome',
    'Querying subroutines',
  ],
  hive_mind: [
    'The collective considers',
    'Syncing with the overmind',
    'Assimilating information',
    'Consensus forming',
  ],
}

function getLoadingMessage(empireType: EmpireType | null): string {
  const pool = [...LOADING_MESSAGES.universal]
  if (empireType === 'machine') {
    pool.push(...LOADING_MESSAGES.machine)
  } else if (empireType === 'hive_mind') {
    pool.push(...LOADING_MESSAGES.hive_mind)
  }
  return pool[Math.floor(Math.random() * pool.length)]
}

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  responseTimeMs?: number
  toolsUsed?: string[]
  isError?: boolean
}

const MAX_CHAT_MESSAGES = 300

function capMessages(next: Message[]): Message[] {
  if (next.length <= MAX_CHAT_MESSAGES) return next
  return next.slice(next.length - MAX_CHAT_MESSAGES)
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
  const [empireType, setEmpireType] = useState<EmpireType | null>(null)
  const [loadingMessage, setLoadingMessage] = useState<string>('Consulting the Curators')

  // Track mounted state to prevent state updates after unmount
  const isMountedRef = useRef(true)

  // Cleanup on unmount
  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
    }
  }, [])

  // Subscribe to backend status to get empire type
  useEffect(() => {
    if (!window.electronAPI?.onBackendStatus) return

    const cleanup = window.electronAPI.onBackendStatus((status) => {
      if (status?.empire_type) {
        setEmpireType(status.empire_type)
      }
    })

    return () => {
      if (typeof cleanup === 'function') {
        cleanup()
      }
    }
  }, [])

  const handleSend = useCallback(async (text: string) => {
    // Add user message
    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: text,
      timestamp: new Date(),
    }
    setMessages(prev => capMessages([...prev, userMessage]))
    setLoadingMessage(getLoadingMessage(empireType))
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
        setMessages(prev => capMessages([...prev, errorMessage]))
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
          setMessages(prev => capMessages([...prev, retryMessage]))
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
          setMessages(prev => capMessages([...prev, assistantMessage]))
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
      setMessages(prev => capMessages([...prev, errorMessage]))
    } finally {
      if (isMountedRef.current) {
        setIsLoading(false)
      }
    }
  }, [backend, sessionKey, empireType])

  const items = useMemo(() => {
    const base = messages.map(message => ({
      key: message.id,
      render: (ref: (el: HTMLDivElement | null) => void) => (
        <ChatMessage
          key={message.id}
          ref={ref}
          role={message.role}
          content={message.content}
          timestamp={message.timestamp}
          responseTimeMs={message.responseTimeMs}
          toolsUsed={message.toolsUsed}
          isError={message.isError}
        />
      ),
    }))

    if (isLoading) {
      base.push({
        key: '__loading__',
        render: (ref: (el: HTMLDivElement | null) => void) => (
          <div key="__loading__" ref={ref} className="chat-loading">
            <div className="loading-indicator">
              <span className="loading-dot"></span>
              <span className="loading-dot"></span>
              <span className="loading-dot"></span>
            </div>
            <span className="loading-text">{loadingMessage}</span>
          </div>
        ),
      })
    }

    return base
  }, [messages, isLoading, loadingMessage])

  return (
    <div className="chat-page">
      {messages.length === 0 ? (
        <div className="chat-messages">
          <div className="chat-welcome">
            <h2>Stellaris Advisor</h2>
            <p>Your strategic advisor awaits.</p>
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
        </div>
      ) : (
        <VirtualChatList items={items} isLoading={isLoading} />
      )}
      <ChatInput
        onSend={handleSend}
        loading={isLoading}
      />
    </div>
  )
}

export default ChatPage
