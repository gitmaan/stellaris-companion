import { useMemo, useState, useCallback, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import ChatMessage from '../components/ChatMessage'
import ChatInput from '../components/ChatInput'
import VirtualChatList from '../components/VirtualChatList'
import AdvisorInfoPanel from '../components/AdvisorInfoPanel'
import { useBackend, ChatResponse, EmpireType } from '../hooks/useBackend'
import { HUDHeader } from '../components/hud/HUDText'
import { HUDPanel } from '../components/hud/HUDPanel'
import { FolderIconG } from '../components/icons/FolderIcon'

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
    // Galactic Filing Cabinet
    'Locating the correct folder...',
    'Filing this under "Urgent"...',
    'Pulling your file...',
    'Cross-referencing your records...',
    'Please hold...',
    'Transferring you now...',
    'Consulting a supervisor...',
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

// Suggestion pools for the welcome screen
const SUGGESTIONS = {
  strategic: [
    'What should I be researching?',
    'Am I falling behind?',
    'What am I probably neglecting?',
    'What should a ruler at this stage be thinking about?',
    'How does our empire compare to the competition?',
    "What's the biggest risk we're not preparing for?",
  ],
  tactical: [
    'Why is my economy in the red?',
    'What should I be building on my planets?',
    'Why does everyone hate us?',
    'Could we win a war right now?',
    'Can our navy hold its own?',
    'Where are we strategically vulnerable?',
  ],
  wildcards: [
    'Roast my empire',
    'Explain my empire like I just took the throne',
    'Give me a state of the galaxy address',
    'What would our rivals say about us?',
  ],
}

// Pick random items from an array
function pickRandom<T>(arr: T[], count: number): T[] {
  const shuffled = [...arr].sort(() => Math.random() - 0.5)
  return shuffled.slice(0, count)
}

// Generate a set of suggestions: 2 strategic, 2 tactical, 1 wildcard
function generateSuggestions(): string[] {
  const picks = [
    ...pickRandom(SUGGESTIONS.strategic, 2),
    ...pickRandom(SUGGESTIONS.tactical, 2),
    ...pickRandom(SUGGESTIONS.wildcards.filter(w => w !== 'Roast my empire'), 1),
  ].sort(() => Math.random() - 0.5) // Shuffle the final order
  picks.push('Roast my empire') // Always last
  return picks
}

function createSessionKey(): string {
  const nonce = Math.random().toString(36).slice(2, 8)
  return `chat-${Date.now()}-${nonce}`
}

// Animation variants for the welcome screen staggered reveal
const EASE_CURVE: [number, number, number, number] = [0.25, 0.46, 0.45, 0.94]
const welcomeContainer = {
  hidden: {},
  show: { transition: { staggerChildren: 0.15 } },
}
const welcomeItem = {
  hidden: { opacity: 0, y: 15 },
  show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: EASE_CURVE } },
}
const suggestionContainer = {
  hidden: {},
  show: { transition: { staggerChildren: 0.05, delayChildren: 0.1 } },
}
const suggestionItem = {
  hidden: { opacity: 0, y: 10 },
  show: { opacity: 1, y: 0, transition: { duration: 0.3, ease: EASE_CURVE } },
}

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  responseTimeMs?: number
  isError?: boolean
}

const MAX_CHAT_MESSAGES = 300
const MAX_REPORT_CONTEXT_MESSAGES = 8
const MAX_REPORT_MESSAGE_CHARS = 1200

function capMessages(next: Message[]): Message[] {
  if (next.length <= MAX_CHAT_MESSAGES) return next
  return next.slice(next.length - MAX_CHAT_MESSAGES)
}

function truncateForReport(text: string): string {
  const normalized = text.replace(/\s+/g, ' ').trim()
  if (normalized.length <= MAX_REPORT_MESSAGE_CHARS) return normalized
  return normalized.slice(0, MAX_REPORT_MESSAGE_CHARS).trimEnd() + '...'
}

function buildRecentTurnsForReport(messages: Message[], assistantIndex: number): Array<{ role: 'user' | 'assistant'; content: string }> {
  return messages
    .slice(0, assistantIndex + 1)
    .filter((m) => !m.isError)
    .map((m) => ({ role: m.role, content: truncateForReport(m.content) }))
    .slice(-MAX_REPORT_CONTEXT_MESSAGES)
}

/**
 * ChatPage - Main chat interface for interacting with the Stellaris advisor
 * Galactic Command Terminal aesthetic
 */
interface ChatPageProps {
  isActive?: boolean
  onReportLlmIssue?: (llm: {
    lastPrompt?: string
    lastResponse?: string
    recentTurns?: Array<{ role: 'user' | 'assistant'; content: string }>
    responseTimeMs?: number
    model?: string
  }) => void
}

function ChatPage({
  isActive = true,
  onReportLlmIssue,
}: ChatPageProps) {
  const backend = useBackend()
  const [messages, setMessages] = useState<Message[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [sessionKey, setSessionKey] = useState(() => createSessionKey())
  const [scrollToBottomSignal, setScrollToBottomSignal] = useState(0)
  const [empireType, setEmpireType] = useState<EmpireType | null>(null)
  const [saveLoaded, setSaveLoaded] = useState(false)
  const [precomputeReady, setPrecomputeReady] = useState(false)
  const [empireName, setEmpireName] = useState<string | null>(null)
  const [gameDate, setGameDate] = useState<string | null>(null)
  const [empireEthics, setEmpireEthics] = useState<string[]>([])
  const [empireCivics, setEmpireCivics] = useState<string[]>([])
  const [empireAuthority, setEmpireAuthority] = useState<string | null>(null)
  const [empireOrigin, setEmpireOrigin] = useState<string | null>(null)
  const [loadingMessage, setLoadingMessage] = useState<string>('Consulting the Curators')
  const [suggestions, setSuggestions] = useState<string[]>(() => generateSuggestions())
  const [advisorPanelOpen, setAdvisorPanelOpen] = useState(false)

  // Re-animate suggestions when tab becomes active again
  const [suggestionKey, setSuggestionKey] = useState(0)
  const wasActiveRef = useRef(isActive)
  useEffect(() => {
    if (isActive && !wasActiveRef.current) {
      setSuggestionKey(k => k + 1)
    }
    wasActiveRef.current = isActive
  }, [isActive])

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
      if (typeof status?.save_loaded === 'boolean') {
        setSaveLoaded(status.save_loaded)
      }
      setPrecomputeReady(!!status?.precompute_ready)
      setEmpireName(status?.empire_name ?? null)
      setGameDate(status?.game_date ?? null)
      setEmpireEthics(Array.isArray(status?.empire_ethics) ? status.empire_ethics : [])
      setEmpireCivics(Array.isArray(status?.empire_civics) ? status.empire_civics : [])
      setEmpireAuthority(typeof status?.empire_authority === 'string' ? status.empire_authority : null)
      setEmpireOrigin(typeof status?.empire_origin === 'string' ? status.empire_origin : null)
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
    setScrollToBottomSignal(v => v + 1)
    setLoadingMessage(getLoadingMessage(empireType))
    setIsLoading(true)

    try {
      const result = await backend.chat(text, sessionKey)

      // Only update state if component is still mounted
      if (!isMountedRef.current) return

      if (result.error) {
        // Retryable backend state (precompute not ready)
        if (result.errorCode === 'BRIEFING_NOT_READY' && result.retryAfterMs) {
          const retryMessage: Message = {
            id: `retry-${Date.now()}`,
            role: 'assistant',
            content: `The advisor is still analyzing your save file. Please try again in ${Math.ceil(result.retryAfterMs / 1000)} seconds.`,
            timestamp: new Date(),
            isError: true,
          }
          setMessages(prev => capMessages([...prev, retryMessage]))
          return
        }

        const errorMessage: Message = {
          id: `error-${Date.now()}`,
          role: 'assistant',
          content: result.error,
          timestamp: new Date(),
          isError: true,
        }
        setMessages(prev => capMessages([...prev, errorMessage]))
      } else if (result.data) {
        // Success - add assistant response
        const chatResponse = result.data as ChatResponse
        const assistantMessage: Message = {
          id: `assistant-${Date.now()}`,
          role: 'assistant',
          content: chatResponse.text,
          timestamp: new Date(),
          responseTimeMs: chatResponse.response_time_ms,
        }
        setMessages(prev => capMessages([...prev, assistantMessage]))
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

  const handleNewChat = useCallback(() => {
    if (isLoading) return
    setMessages([])
    setSessionKey(createSessionKey())
    setSuggestions(generateSuggestions())
    setSuggestionKey(k => k + 1)
    setScrollToBottomSignal(v => v + 1)
  }, [isLoading])

  const items = useMemo(() => {
    const base = messages.map((message, idx) => ({
      key: message.id,
      render: (ref: (el: HTMLDivElement | null) => void) => (
        <ChatMessage
          key={message.id}
          ref={ref}
          role={message.role}
          content={message.content}
          timestamp={message.timestamp}
          responseTimeMs={message.responseTimeMs}
          isError={message.isError}
          onReport={
            onReportLlmIssue && message.role === 'assistant' && !message.isError
              ? () => {
                const lastPrompt = [...messages.slice(0, idx)].reverse().find((m) => m.role === 'user')?.content
                onReportLlmIssue({
                  lastPrompt: lastPrompt ? truncateForReport(lastPrompt) : undefined,
                  lastResponse: truncateForReport(message.content),
                  recentTurns: buildRecentTurnsForReport(messages, idx),
                  responseTimeMs: message.responseTimeMs,
                  model: 'gemini-3-flash-preview',
                })
              }
              : undefined
          }
        />
      ),
    }))

    if (isLoading) {
      base.push({
        key: '__loading__',
        render: (ref: (el: HTMLDivElement | null) => void) => (
          <div key="__loading__" ref={ref} className="max-w-[85%] self-start flex items-center gap-3 p-4 text-text-secondary text-sm mb-2">
            <div className="flex gap-1.5">
              <span className="w-2 h-2 rounded-full bg-accent-cyan shadow-[0_0_6px_rgba(0,212,255,0.6)] animate-bounce-dot animate-bounce-dot-1"></span>
              <span className="w-2 h-2 rounded-full bg-accent-cyan shadow-[0_0_6px_rgba(0,212,255,0.6)] animate-bounce-dot animate-bounce-dot-2"></span>
              <span className="w-2 h-2 rounded-full bg-accent-cyan shadow-[0_0_6px_rgba(0,212,255,0.6)] animate-bounce-dot animate-bounce-dot-3"></span>
            </div>
            <span className="italic animate-pulse-text text-accent-cyan/80">{loadingMessage}</span>
          </div>
        ),
      })
    }

    return base
  }, [messages, isLoading, loadingMessage, onReportLlmIssue])

  return (
    <div className="flex flex-col h-full relative">
      <AdvisorInfoPanel
        isOpen={advisorPanelOpen}
        onClose={() => setAdvisorPanelOpen(false)}
        saveLoaded={saveLoaded}
        empireName={empireName}
        gameDate={gameDate}
        empireEthics={empireEthics}
        empireCivics={empireCivics}
        empireAuthority={empireAuthority}
        empireOrigin={empireOrigin}
      />

      {messages.length === 0 ? (
        <div className="flex-1 overflow-y-auto flex flex-col items-center justify-center p-6">
          <motion.div
            className="w-full max-w-2xl flex flex-col items-center gap-12"
            variants={welcomeContainer}
            initial="hidden"
            animate="show"
          >

            {/* Header Section */}
            <div className="text-center space-y-4">
              <motion.div
                className="inline-flex justify-center items-center w-16 h-16 rounded-full border border-accent-cyan/30 bg-accent-cyan/5 mb-4 shadow-glow-sm animate-pulse-glow"
                variants={welcomeItem}
                style={{ scale: 0 }}
                animate={{ scale: 1, opacity: 1, y: 0 }}
                transition={{ duration: 0.5, ease: EASE_CURVE }}
              >
                 <FolderIconG className="text-accent-cyan" size={32} />
              </motion.div>

              <motion.div className="relative" variants={welcomeItem}>
                <HUDHeader size="xl" className="tracking-[0.2em] text-accent-cyan drop-shadow-[0_0_10px_rgba(0,212,255,0.5)]">
                  Galactic Helpdesk
                </HUDHeader>
                <motion.div
                  className="absolute -bottom-2 inset-x-0 mx-auto w-1/2 h-px bg-gradient-to-r from-transparent via-accent-cyan/50 to-transparent"
                  initial={{ scaleX: 0 }}
                  animate={{ scaleX: 1 }}
                  transition={{ duration: 0.6, delay: 0.4, ease: EASE_CURVE }}
                />
              </motion.div>

              <motion.p className="text-text-secondary font-mono text-sm tracking-wide" variants={welcomeItem}>
                {precomputeReady
                  ? 'YOUR FILE IS OPEN // SUBMIT YOUR REQUEST'
                  : <>INITIALIZING // SCANNING EMPIRE DATA<span className="animate-pulse-text ml-1">▍</span></>}
              </motion.p>
            </div>

            {/* Suggestions Panel / Scanning Indicator */}
            <motion.div className="w-full" variants={welcomeItem}>
              <AnimatePresence mode="wait">
                {precomputeReady ? (
                  <motion.div
                    key="suggestions"
                    initial={{ opacity: 0, y: 15 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }}
                    transition={{ duration: 0.4, ease: EASE_CURVE }}
                  >
                    <HUDPanel className="w-full" title="Suggested Inquiries" variant="primary">
                      <motion.div
                        key={suggestionKey}
                        className="grid grid-cols-1 md:grid-cols-2 gap-3"
                        variants={suggestionContainer}
                        initial="hidden"
                        animate="show"
                      >
                        {suggestions.map((suggestion, idx) => (
                          <motion.button
                            key={suggestion}
                            variants={suggestionItem}
                            onClick={() => handleSend(suggestion)}
                            className="group relative flex items-start p-3 text-left transition-all duration-200 hover:bg-accent-cyan/5 border border-transparent hover:border-accent-cyan/20 rounded-sm"
                          >
                            <span className="font-mono text-xs text-accent-cyan/50 mr-3 opacity-50 group-hover:opacity-100 group-hover:text-accent-cyan transition-all">
                              {String(idx + 1).padStart(2, '0')}
                            </span>
                            <span className="font-mono text-xs tracking-wide text-text-primary group-hover:text-accent-cyan group-hover:drop-shadow-[0_0_5px_rgba(0,212,255,0.5)] transition-all">
                              {suggestion}
                            </span>
                            <div className="absolute right-2 top-1/2 -translate-y-1/2 w-1 h-1 bg-accent-cyan/50 rounded-full opacity-0 group-hover:opacity-100 shadow-glow-sm transition-opacity" />
                          </motion.button>
                        ))}
                      </motion.div>
                    </HUDPanel>
                  </motion.div>
                ) : (
                  <motion.div
                    key="scanning"
                    className="flex items-center justify-center gap-3 py-8"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0, y: -10 }}
                    transition={{ duration: 0.3 }}
                  >
                    <span className="relative flex h-2.5 w-2.5">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent-cyan/60" />
                      <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-accent-cyan shadow-[0_0_8px_rgba(0,212,255,0.6)]" />
                    </span>
                    <span className="font-mono text-xs text-accent-cyan/70 tracking-wider animate-pulse-text">
                      Scanning empire data...
                    </span>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          </motion.div>
        </div>
      ) : (
        <>
          <div className="flex items-center justify-end mb-3">
            <button
              type="button"
              onClick={handleNewChat}
              disabled={isLoading}
              className={`px-4 py-2 border border-white/20 font-display text-[10px] tracking-[0.18em] uppercase transition-all duration-200 ${
                isLoading
                  ? 'text-white/25 border-white/10 cursor-not-allowed'
                  : 'text-accent-cyan/80 hover:text-accent-cyan hover:border-accent-cyan/60 hover:bg-accent-cyan/10'
              }`}
            >
              New Chat
            </button>
          </div>

          <div className="flex-1 flex flex-col overflow-hidden relative rounded-lg bg-black/20 backdrop-blur-sm border border-white/5 mb-4">
             {/* Decorative lines for chat container */}
             <div className="absolute top-0 left-0 w-4 h-4 border-t border-l border-white/10 pointer-events-none" />
             <div className="absolute top-0 right-0 w-4 h-4 border-t border-r border-white/10 pointer-events-none" />

             <VirtualChatList
              items={items}
              identityKey={sessionKey}
              scrollToBottomSignal={scrollToBottomSignal}
              isLoading={isLoading}
            />
          </div>
        </>
      )}
      
      <ChatInput
        onSend={handleSend}
        loading={isLoading}
        disabled={!precomputeReady}
        onOpenAdvisorPanel={() => setAdvisorPanelOpen(true)}
      />
    </div>
  )
}

export default ChatPage
