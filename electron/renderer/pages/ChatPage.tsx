import { useMemo, useState, useCallback, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useTranslation } from 'react-i18next'
import ChatMessage from '../components/ChatMessage'
import ChatInput from '../components/ChatInput'
import VirtualChatList from '../components/VirtualChatList'
import AdvisorInfoPanel from '../components/AdvisorInfoPanel'
import { useBackend, ChatResponse, EmpireType } from '../hooks/useBackend'
import type { ModelRoutingMode } from '../hooks/useSettings'
import { HUDHeader } from '../components/hud/HUDText'
import { HUDPanel } from '../components/hud/HUDPanel'
import { FolderIconG } from '../components/icons/FolderIcon'

interface LoadingMessagePools {
  universal: string[]
  machine: string[]
  hiveMind: string[]
}

interface SuggestionPools {
  strategic: string[]
  tactical: string[]
  wildcards: string[]
}

function getLoadingMessage(empireType: EmpireType | null, messages: LoadingMessagePools): string {
  const pool = [...messages.universal]
  if (empireType === 'machine') {
    pool.push(...messages.machine)
  } else if (empireType === 'hive_mind') {
    pool.push(...messages.hiveMind)
  }
  return pool[Math.floor(Math.random() * pool.length)]
}

// Pick random items from an array
function pickRandom<T>(arr: T[], count: number): T[] {
  const shuffled = [...arr].sort(() => Math.random() - 0.5)
  return shuffled.slice(0, count)
}

// Generate a set of suggestions: 2 strategic, 2 tactical, 1 wildcard
function generateSuggestions(pools: SuggestionPools, roastSuggestion: string): string[] {
  const picks = [
    ...pickRandom(pools.strategic, 2),
    ...pickRandom(pools.tactical, 2),
    ...pickRandom(pools.wildcards.filter(w => w !== roastSuggestion), 1),
  ].sort(() => Math.random() - 0.5) // Shuffle the final order
  picks.push(roastSuggestion) // Always last
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

const COMPACT_WELCOME_HEIGHT = 760
const COMPACT_WELCOME_WIDTH = 1100

function isCompactWelcomeViewport(): boolean {
  if (typeof window === 'undefined') return false
  return window.innerHeight <= COMPACT_WELCOME_HEIGHT || window.innerWidth <= COMPACT_WELCOME_WIDTH
}

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  responseTimeMs?: number
  model?: string
  modelDisplay?: string
  modelRouting?: ChatResponse['model_routing']
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
  modelRoutingMode?: ModelRoutingMode
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
  modelRoutingMode,
  onReportLlmIssue,
}: ChatPageProps) {
  const { t } = useTranslation()
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
  const [loadingMessage, setLoadingMessage] = useState<string>('')
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [advisorPanelOpen, setAdvisorPanelOpen] = useState(false)
  const [isWelcomeCompact, setIsWelcomeCompact] = useState<boolean>(() => isCompactWelcomeViewport())
  const [suggestionKey, setSuggestionKey] = useState(0)

  const loadingMessages = useMemo<LoadingMessagePools>(() => ({
    universal: t('chat.loading.universal', { returnObjects: true }) as string[],
    machine: t('chat.loading.machine', { returnObjects: true }) as string[],
    hiveMind: t('chat.loading.hiveMind', { returnObjects: true }) as string[],
  }), [t])

  const suggestionPools = useMemo<SuggestionPools>(() => ({
    strategic: t('chat.suggestions.strategic', { returnObjects: true }) as string[],
    tactical: t('chat.suggestions.tactical', { returnObjects: true }) as string[],
    wildcards: t('chat.suggestions.wildcards', { returnObjects: true }) as string[],
  }), [t])

  const roastSuggestion = t('chat.suggestions.roast')

  useEffect(() => {
    setLoadingMessage(getLoadingMessage(empireType, loadingMessages))
    setSuggestions(generateSuggestions(suggestionPools, roastSuggestion))
    setSuggestionKey(k => k + 1)
  }, [empireType, loadingMessages, roastSuggestion, suggestionPools])

  // Re-animate suggestions when tab becomes active again
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

  useEffect(() => {
    const handleResize = () => {
      setIsWelcomeCompact(isCompactWelcomeViewport())
    }

    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  const visibleSuggestions = useMemo(() => {
    if (!isWelcomeCompact) return suggestions

    const roast = suggestions.find((s) => s === roastSuggestion)
    const base = suggestions.filter((s) => s !== roastSuggestion).slice(0, 3)
    return roast ? [...base, roast] : suggestions.slice(0, 4)
  }, [isWelcomeCompact, roastSuggestion, suggestions])

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
    setLoadingMessage(getLoadingMessage(empireType, loadingMessages))
    setIsLoading(true)

    try {
      const result = await backend.chat(text, sessionKey, undefined, modelRoutingMode)

      // Only update state if component is still mounted
      if (!isMountedRef.current) return

      if (result.error) {
        // Retryable backend state (precompute not ready)
        if (result.errorCode === 'BRIEFING_NOT_READY' && result.retryAfterMs) {
          const retryMessage: Message = {
            id: `retry-${Date.now()}`,
            role: 'assistant',
            content: t('chat.errors.briefingNotReady', {
              seconds: Math.ceil(result.retryAfterMs / 1000),
            }),
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
          model: chatResponse.model,
          modelDisplay: chatResponse.model_display,
          modelRouting: chatResponse.model_routing,
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
        content: err instanceof Error ? err.message : t('chat.errors.unexpected'),
        timestamp: new Date(),
        isError: true,
      }
      setMessages(prev => capMessages([...prev, errorMessage]))
    } finally {
      if (isMountedRef.current) {
        setIsLoading(false)
      }
    }
  }, [backend, sessionKey, empireType, modelRoutingMode, loadingMessages, t])

  const handleNewChat = useCallback(() => {
    if (isLoading) return
    setMessages([])
    setSessionKey(createSessionKey())
    setSuggestions(generateSuggestions(suggestionPools, roastSuggestion))
    setSuggestionKey(k => k + 1)
    setScrollToBottomSignal(v => v + 1)
  }, [isLoading, roastSuggestion, suggestionPools])

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
          modelDisplay={message.modelDisplay}
          modelRouting={message.modelRouting}
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
                  model: message.model,
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
              <span className="w-2 h-2 rounded-full bg-accent-cyan shadow-glow-dot animate-bounce-dot animate-bounce-dot-1"></span>
              <span className="w-2 h-2 rounded-full bg-accent-cyan shadow-glow-dot animate-bounce-dot animate-bounce-dot-2"></span>
              <span className="w-2 h-2 rounded-full bg-accent-cyan shadow-glow-dot animate-bounce-dot animate-bounce-dot-3"></span>
            </div>
            <span className="italic animate-pulse-text text-accent-cyan/80">{loadingMessage}</span>
          </div>
        ),
      })
    }

    return base
  }, [messages, isLoading, loadingMessage, onReportLlmIssue])

  return (
    <div className="flex flex-col h-full min-h-0 relative">
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
        <div
          className={`flex-1 overflow-y-auto flex flex-col items-center ${
            isWelcomeCompact ? 'justify-start p-4 pt-5' : 'justify-center p-6'
          }`}
        >
          <motion.div
            className={`w-full max-w-2xl flex flex-col items-center ${
              isWelcomeCompact ? 'gap-6' : 'gap-12'
            }`}
            variants={welcomeContainer}
            initial="hidden"
            animate="show"
          >

            {/* Header Section */}
            <div className={`text-center ${isWelcomeCompact ? 'space-y-2.5' : 'space-y-4'}`}>
              <motion.div
                className={`inline-flex justify-center items-center rounded-full border border-accent-cyan/30 bg-accent-cyan/5 shadow-glow-sm animate-pulse-glow ${
                  isWelcomeCompact ? 'w-10 h-10 mb-2' : 'w-16 h-16 mb-4'
                }`}
                variants={welcomeItem}
                style={{ scale: 0 }}
                animate={{ scale: 1, opacity: 1, y: 0 }}
                transition={{ duration: 0.5, ease: EASE_CURVE }}
              >
                 <FolderIconG className="text-accent-cyan" size={isWelcomeCompact ? 20 : 32} />
              </motion.div>

              <motion.div className="relative" variants={welcomeItem}>
                <HUDHeader
                  size={isWelcomeCompact ? 'lg' : 'xl'}
                  className={`${isWelcomeCompact ? 'tracking-[0.12em]' : 'tracking-[0.2em]'} text-accent-cyan text-glow`}
                >
                  {t('chat.welcome.title')}
                </HUDHeader>
                <motion.div
                  className="absolute -bottom-2 inset-x-0 mx-auto w-1/2 h-px bg-gradient-to-r from-transparent via-accent-cyan/50 to-transparent"
                  initial={{ scaleX: 0 }}
                  animate={{ scaleX: 1 }}
                  transition={{ duration: 0.6, delay: 0.4, ease: EASE_CURVE }}
                />
              </motion.div>

              <motion.p
                className={`text-text-secondary font-mono tracking-wide ${isWelcomeCompact ? 'text-xs' : 'text-sm'}`}
                variants={welcomeItem}
              >
                {precomputeReady
                  ? t('chat.welcome.ready', { defaultValue: 'YOUR FILE IS OPEN // SUBMIT YOUR REQUEST' })
                  : <>{t('chat.welcome.scanning', { defaultValue: 'INITIALIZING // SCANNING EMPIRE DATA' })}<span className="animate-pulse-text ml-1">▍</span></>}
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
                    <HUDPanel
                      className={`w-full ${isWelcomeCompact ? 'max-h-[42vh]' : ''}`}
                      title={t('chat.welcome.suggested', { defaultValue: 'Suggested Inquiries' })}
                      variant="primary"
                    >
                      <div className={isWelcomeCompact ? 'max-h-[30vh] overflow-y-auto custom-scrollbar pr-1' : ''}>
                        <motion.div
                          key={suggestionKey}
                          className={`grid grid-cols-1 md:grid-cols-2 ${isWelcomeCompact ? 'gap-2' : 'gap-3'}`}
                          variants={suggestionContainer}
                          initial="hidden"
                          animate="show"
                        >
                          {visibleSuggestions.map((suggestion, idx) => (
                            <motion.button
                              key={suggestion}
                              variants={suggestionItem}
                              onClick={() => handleSend(suggestion)}
                              className={`group relative flex items-start text-left transition-all duration-200 hover:bg-accent-cyan/5 border border-transparent hover:border-accent-cyan/20 rounded-sm ${
                                isWelcomeCompact ? 'p-2.5' : 'p-3'
                              }`}
                            >
                              <span className="font-mono text-xs text-accent-cyan/50 mr-3 opacity-50 group-hover:opacity-100 group-hover:text-accent-cyan transition-all">
                                {String(idx + 1).padStart(2, '0')}
                              </span>
                              <span className={`font-mono tracking-wide text-text-primary group-hover:text-accent-cyan transition-all ${isWelcomeCompact ? 'text-[11px]' : 'text-xs'}`}>
                                {suggestion}
                              </span>
                              <div className="absolute right-2 top-1/2 -translate-y-1/2 w-1 h-1 bg-accent-cyan/50 rounded-full opacity-0 group-hover:opacity-100 shadow-glow-sm transition-opacity" />
                            </motion.button>
                          ))}
                        </motion.div>
                      </div>
                    </HUDPanel>
                  </motion.div>
                ) : (
                  <motion.div
                    key="scanning"
                    className={`flex items-center justify-center gap-3 ${isWelcomeCompact ? 'py-5' : 'py-8'}`}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0, y: -10 }}
                    transition={{ duration: 0.3 }}
                  >
                    <span className="relative flex h-2.5 w-2.5">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent-cyan/60" />
                      <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-accent-cyan shadow-glow-indicator" />
                    </span>
                    <span className="font-mono text-xs text-accent-cyan/70 tracking-wider animate-pulse-text">
                      {t('chat.welcome.scanningShort', { defaultValue: 'Scanning empire data...' })}
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
              {t('chat.newChat', { defaultValue: 'New Chat' })}
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
