import { useMemo, useState, useCallback, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import ChatMessage from '../components/ChatMessage'
import ChatInput from '../components/ChatInput'
import ChatGPTUsage from '../components/ChatGPTUsage'
import { manageChatGPTUsage } from '../hooks/useChatGPT'
import VirtualChatList from '../components/VirtualChatList'
import AdvisorInfoPanel from '../components/AdvisorInfoPanel'
import { useBackend, ChatResponse, EmpireType, type AdvisorConversation, type AdvisorTurn } from '../hooks/useBackend'
import type { ModelRoutingMode } from '../hooks/useSettings'
import { HUDHeader } from '../components/hud/HUDText'
import { HUDPanel } from '../components/hud/HUDPanel'
import { HUDButton } from '../components/hud/HUDButton'
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
  gameDate?: string | null
  historySaved?: boolean
  responseTimeMs?: number
  model?: string
  modelDisplay?: string
  modelRouting?: ChatResponse['model_routing']
  isError?: boolean
  action?: 'settings' | 'usage'
}

function restoreMessages(turns: AdvisorTurn[]): Message[] {
  return capMessages(turns.flatMap(turn => [
    { id: `${turn.id}-question`, role: 'user' as const, content: turn.question, timestamp: new Date(turn.created_at * 1000) },
    { id: turn.id, role: 'assistant' as const, content: turn.answer, timestamp: new Date(turn.created_at * 1000), gameDate: turn.game_date, historySaved: true, responseTimeMs: turn.response_time_ms, model: turn.model, modelDisplay: turn.model_display, modelRouting: turn.model_routing },
  ]))
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

function getAdvisorProviderName(provider: string | null): string {
  switch (provider) {
    case 'chatgpt':
      return 'ChatGPT'
    case 'ollama':
      return 'Ollama'
    case 'lm_studio':
      return 'LM Studio'
    case 'openrouter':
      return 'OpenRouter'
    case 'custom':
      return 'Custom provider'
    default:
      return 'Gemini'
  }
}

function getProviderErrorMessage({
  code,
  fallback,
  provider,
  t,
}: {
  code?: string | null
  fallback: string
  provider: string | null
  t: TFunction
}): { content: string; action?: 'settings' | 'usage' } {
  if (code?.startsWith('CHATGPT_')) return {
    content: String(t(`chatgpt.errors.${code}`, { defaultValue: t('chatgpt.errors.CHATGPT_UNAVAILABLE') })),
    action: code === 'CHATGPT_LIMIT' ? 'usage' : ['CHATGPT_RECONNECT', 'CHATGPT_PERMISSION', 'CHATGPT_MODEL', 'CHATGPT_INELIGIBLE'].includes(code) ? 'settings' : undefined,
  }
  const providerName = getAdvisorProviderName(provider)
  const providerErrorKeys: Record<string, string> = {
    ADVISOR_PROVIDER_NOT_CONFIGURED: 'providerNotConfigured',
    PROVIDER_UNAVAILABLE: 'providerUnavailable',
    PROVIDER_AUTH_FAILED: 'providerAuthFailed',
    PROVIDER_MODEL_NOT_FOUND: 'providerModelNotFound',
    PROVIDER_RATE_LIMITED: 'providerRateLimited',
    PROVIDER_BILLING_FAILED: 'providerBillingFailed',
    PROVIDER_TIMEOUT: 'providerTimeout',
    PROVIDER_CONTEXT_LIMIT: 'providerContextLimit',
    PROVIDER_INVALID_RESPONSE: 'providerInvalidResponse',
    PROVIDER_EMPTY_RESPONSE: 'providerEmptyResponse',
    PROVIDER_REQUEST_FAILED: 'providerRequestFailed',
  }
  const errorKey = code ? providerErrorKeys[code] : null
  if (!errorKey) return { content: fallback }
  return {
    content: String(t(`chat.errors.${errorKey}`, { provider: providerName })),
    action: 'settings',
  }
}

/**
 * ChatPage - Main chat interface for interacting with the Stellaris advisor
 * Galactic Command Terminal aesthetic
 */
interface ChatPageProps {
  isActive?: boolean
  modelRoutingMode?: ModelRoutingMode
  onOpenSettings?: () => void
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
  onOpenSettings,
  onReportLlmIssue,
}: ChatPageProps) {
  const { t } = useTranslation()
  const backend = useBackend()
  const [messages, setMessages] = useState<Message[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [sessionKey, setSessionKey] = useState(() => createSessionKey())
  const [activeCampaignId, setActiveCampaignId] = useState<string | null>(null)
  const [conversationId, setConversationId] = useState<string | undefined>()
  const [conversations, setConversations] = useState<AdvisorConversation[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyError, setHistoryError] = useState(false)
  const [hasEarlierMessages, setHasEarlierMessages] = useState(false)
  const [firstTurnId, setFirstTurnId] = useState<string>()
  const [viewingEarlier, setViewingEarlier] = useState(false)
  const historyTargetRef = useRef<string>()
  const [historyOpen, setHistoryOpen] = useState(false)
  const campaignIdRef = useRef<string | null>(null)
  const chatGenerationRef = useRef(0)
  const [scrollToBottomSignal, setScrollToBottomSignal] = useState(0)
  const [empireType, setEmpireType] = useState<EmpireType | null>(null)
  const [saveLoaded, setSaveLoaded] = useState(false)
  const [precomputeReady, setPrecomputeReady] = useState(false)
  const [empireName, setEmpireName] = useState<string | null>(null)
  const [gameDate, setGameDate] = useState<string | null>(null)
  const [advisorConfigured, setAdvisorConfigured] = useState<boolean | null>(null)
  const [advisorProvider, setAdvisorProvider] = useState<string | null>(null)
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
      const campaignId = status?.save_id
      if (campaignId && campaignId !== campaignIdRef.current) {
        if (campaignIdRef.current !== null) {
          chatGenerationRef.current += 1
          setMessages([])
          setSessionKey(createSessionKey())
          setIsLoading(false)
          setAdvisorPanelOpen(false)
        }
        campaignIdRef.current = campaignId
        setActiveCampaignId(campaignId)
      }
      if (status?.empire_type) {
        setEmpireType(status.empire_type)
      }
      if (typeof status?.save_loaded === 'boolean') {
        setSaveLoaded(status.save_loaded)
      }
      setPrecomputeReady(!!status?.precompute_ready)
      setEmpireName(status?.empire_name ?? null)
      setGameDate(status?.game_date ?? null)
      if (typeof status?.advisor_configured === 'boolean') {
        setAdvisorConfigured(status.advisor_configured)
      }
      if (typeof status?.advisor_provider === 'string') {
        setAdvisorProvider(status.advisor_provider)
      }
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

  const restoreConversation = useCallback(async (saveId: string, id?: string, beforeTurnId?: string) => {
    const generation = ++chatGenerationRef.current
    historyTargetRef.current = id
    setHistoryLoading(true)
    setHistoryError(false)
    setHistoryOpen(false)
    setIsLoading(false)
    try {
      const list = await backend.conversations(saveId)
      if (!isMountedRef.current || generation !== chatGenerationRef.current) return
      if (!list.data) { setHistoryError(true); return }
      setConversations(list.data.conversations)
      const selectedId = id ?? list.data.conversations[0]?.id
      if (selectedId) {
        const saved = await backend.conversation(saveId, selectedId, beforeTurnId)
        if (!isMountedRef.current || generation !== chatGenerationRef.current) return
        if (!saved.data) { setHistoryError(true); return }
        setMessages(restoreMessages(saved.data.turns))
        setHasEarlierMessages(saved.data.has_more)
        setFirstTurnId(saved.data.turns[0]?.id)
        setViewingEarlier(Boolean(beforeTurnId))
      } else { setMessages([]); setHasEarlierMessages(false); setViewingEarlier(false) }
      setConversationId(selectedId)
      setSessionKey(selectedId ?? createSessionKey())
      setScrollToBottomSignal(v => v + 1)
    } finally {
      if (isMountedRef.current && generation === chatGenerationRef.current) setHistoryLoading(false)
    }
  }, [backend])

  useEffect(() => {
    setConversationId(undefined)
    setConversations([])
    if (activeCampaignId) void restoreConversation(activeCampaignId)
  }, [activeCampaignId, restoreConversation])

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
    if (isLoading || historyLoading || viewingEarlier) return false
    const generation = chatGenerationRef.current
    const requestId = crypto.randomUUID()
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
      const result = await backend.chat(text, sessionKey, undefined, modelRoutingMode, { save_id: activeCampaignId ?? undefined, conversation_id: conversationId, request_id: requestId })

      // Only update state if component is still mounted
      if (!isMountedRef.current || generation !== chatGenerationRef.current) return

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
          return false
        }

        const providerError = getProviderErrorMessage({
          code: result.errorCode,
          fallback: result.error,
          provider: advisorProvider,
          t,
        })
        if (result.errorCode === 'ADVISOR_PROVIDER_NOT_CONFIGURED') {
          setAdvisorConfigured(false)
        }
        const errorMessage: Message = {
          id: `error-${Date.now()}`,
          role: 'assistant',
          content: providerError.content,
          timestamp: new Date(),
          isError: true,
          action: providerError.action,
        }
        setMessages(prev => capMessages([...prev, errorMessage]))
        return false
      } else if (result.data) {
        setAdvisorConfigured(true)
        // Success - add assistant response
        const chatResponse = result.data as ChatResponse
        if (chatResponse.conversation_id && chatResponse.history_saved !== false) setConversationId(chatResponse.conversation_id)
        if (activeCampaignId && chatResponse.history_saved !== false) {
          void backend.conversations(activeCampaignId).then(list => {
            if (isMountedRef.current && generation === chatGenerationRef.current && list.data) { setConversations(list.data.conversations); setHistoryError(false) }
          })
        }
        const assistantMessage: Message = {
          id: `assistant-${Date.now()}`,
          role: 'assistant',
          content: chatResponse.text,
          timestamp: new Date(),
          gameDate: chatResponse.game_date,
          historySaved: chatResponse.history_saved,
          responseTimeMs: chatResponse.response_time_ms,
          model: chatResponse.model,
          modelDisplay: chatResponse.model_display,
          modelRouting: chatResponse.model_routing,
        }
        setMessages(prev => capMessages([...prev, assistantMessage]))
        return true
      }
    } catch (err) {
      // Only update state if component is still mounted
      if (!isMountedRef.current || generation !== chatGenerationRef.current) return

      // Unexpected error
      const errorMessage: Message = {
        id: `error-${Date.now()}`,
        role: 'assistant',
        content: err instanceof Error ? err.message : t('chat.errors.unexpected'),
        timestamp: new Date(),
        isError: true,
      }
      setMessages(prev => capMessages([...prev, errorMessage]))
      return false
    } finally {
      if (isMountedRef.current && generation === chatGenerationRef.current) {
        setIsLoading(false)
      }
    }
  }, [advisorProvider, backend, sessionKey, empireType, modelRoutingMode, loadingMessages, t, activeCampaignId, conversationId, isLoading, historyLoading, historyError, viewingEarlier])

  const handleNewChat = useCallback(async () => {
    if (isLoading || historyLoading) return
    const generation = chatGenerationRef.current
    if (activeCampaignId) {
      setHistoryLoading(true)
      const result = await backend.createConversation(activeCampaignId)
      if (!isMountedRef.current || generation !== chatGenerationRef.current) return
      setHistoryLoading(false)
      if (!result.data) { setHistoryError(true); return }
      setConversationId(result.data.conversation.id)
      setConversations(previous => [result.data!.conversation, ...previous])
      setSessionKey(result.data.conversation.id)
    } else {
      setConversationId(undefined)
      setSessionKey(createSessionKey())
    }
    chatGenerationRef.current += 1
    setHistoryError(false)
    setHasEarlierMessages(false)
    setViewingEarlier(false)
    setHistoryOpen(false)
    setMessages([])
    setSuggestions(generateSuggestions(suggestionPools, roastSuggestion))
    setSuggestionKey(k => k + 1)
    setScrollToBottomSignal(v => v + 1)
  }, [isLoading, historyLoading, activeCampaignId, backend, roastSuggestion, suggestionPools])

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
          gameDate={message.gameDate}
          historySaved={message.historySaved}
          responseTimeMs={message.responseTimeMs}
          modelDisplay={message.modelDisplay}
          modelRouting={message.modelRouting}
          isError={message.isError}
          actionLabel={
            message.action === 'settings'
              ? t('chat.errors.openProviderSettings')
              : message.action === 'usage' ? t('chatgpt.manageUsage') : undefined
          }
          onAction={message.action === 'settings' ? onOpenSettings : message.action === 'usage' ? () => void manageChatGPTUsage() : undefined}
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
  }, [messages, isLoading, loadingMessage, onOpenSettings, onReportLlmIssue, t])

  return (
    <div className="flex flex-col h-full min-h-0 relative">
      <AdvisorInfoPanel
        key={campaignIdRef.current}
        isOpen={advisorPanelOpen}
        onClose={() => setAdvisorPanelOpen(false)}
        saveLoaded={saveLoaded && precomputeReady}
        empireName={empireName}
        gameDate={gameDate}
        empireEthics={empireEthics}
        empireCivics={empireCivics}
        empireAuthority={empireAuthority}
        empireOrigin={empireOrigin}
      />

      {(messages.length > 0 || conversations.length > 0 || historyLoading || historyError) && (
        <div className="relative flex items-center justify-end gap-3 mb-3">
          {(hasEarlierMessages || viewingEarlier) && <div className="mr-auto flex gap-3 text-xs text-text-secondary">
            {hasEarlierMessages && <button type="button" disabled={isLoading || historyLoading} onClick={() => activeCampaignId && void restoreConversation(activeCampaignId, conversationId, firstTurnId)}>{t('continuity.earlierMessages')}</button>}
            {viewingEarlier && <button type="button" disabled={historyLoading} onClick={() => activeCampaignId && void restoreConversation(activeCampaignId, conversationId)}>{t('continuity.latestMessages')}</button>}
          </div>}
          {historyError && <button type="button" className="text-xs text-accent-yellow" onClick={() => activeCampaignId && void restoreConversation(activeCampaignId, historyTargetRef.current ?? conversationId)}>{t('continuity.historyRetry')}</button>}
          {historyLoading && <span className="text-xs text-text-muted" role="status">{t('continuity.restoring')}</span>}
          {conversations.length > 0 && (
            <div className="relative" onBlur={event => {
              if (!event.currentTarget.contains(event.relatedTarget)) setHistoryOpen(false)
            }} onKeyDown={event => { if (event.key === 'Escape' && !event.nativeEvent.isComposing) { setHistoryOpen(false); event.currentTarget.querySelector<HTMLButtonElement>('[aria-expanded]')?.focus() } }}>
              <button type="button" aria-haspopup="menu" disabled={isLoading || historyLoading} aria-expanded={historyOpen} onClick={() => setHistoryOpen(open => !open)} className="px-3 py-2 font-display text-[10px] uppercase tracking-[0.12em] text-text-secondary hover:text-accent-cyan disabled:opacity-40">{t('continuity.chats')} ▾</button>
              {historyOpen && <div className="absolute right-0 top-full z-30 mt-1 w-72 max-h-64 overflow-y-auto rounded border border-border bg-bg-secondary p-1 shadow-xl" role="menu">
                {conversations.map(item => <button key={item.id} type="button" role="menuitem" title={item.title} onClick={() => activeCampaignId && void restoreConversation(activeCampaignId, item.id)} className={`block w-full truncate rounded px-3 py-2 text-left text-xs hover:bg-white/5 ${item.id === conversationId ? 'text-accent-cyan' : 'text-text-secondary'}`}>
                  {item.title || t('chat.newChat')}<span className="block text-[10px] text-text-muted">{item.last_game_date ?? new Date(item.created_at * 1000).toLocaleDateString()}</span>
                </button>)}
              </div>}
            </div>
          )}
          <button type="button" onClick={() => void handleNewChat()} disabled={isLoading || historyLoading} className="px-4 py-2 border border-white/20 font-display text-[10px] tracking-[0.18em] uppercase text-accent-cyan/80 hover:border-accent-cyan/60 hover:bg-accent-cyan/10 disabled:opacity-40">{t('chat.newChat')}</button>
        </div>
      )}

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
                  advisorConfigured === false ? (
                    <motion.div
                      key="provider-setup"
                      initial={{ opacity: 0, y: 15 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -10 }}
                      transition={{ duration: 0.4, ease: EASE_CURVE }}
                    >
                      <HUDPanel title={t('chat.providerSetup.title')} variant="secondary">
                        <div className="flex flex-col items-start gap-4 p-1">
                          <p className="font-mono text-sm leading-relaxed text-text-secondary">
                            {t('chat.providerSetup.description', {
                              provider: getAdvisorProviderName(advisorProvider),
                            })}
                          </p>
                          <HUDButton
                            type="button"
                            variant="primary"
                            onClick={onOpenSettings}
                            disabled={!onOpenSettings}
                            className="px-4"
                          >
                            {t('chat.errors.openProviderSettings')}
                          </HUDButton>
                        </div>
                      </HUDPanel>
                    </motion.div>
                  ) : (
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
                  )
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

      {advisorConfigured === false && messages.length > 0 && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3 border border-accent-yellow/40 bg-accent-yellow/5 px-4 py-3">
          <span className="font-mono text-xs leading-relaxed text-accent-yellow/85">
            {t('chat.providerSetup.description', {
              provider: getAdvisorProviderName(advisorProvider),
            })}
          </span>
          <HUDButton
            type="button"
            variant="secondary"
            onClick={onOpenSettings}
            disabled={!onOpenSettings}
            className="px-3 py-1.5 text-[10px]"
          >
            {t('chat.errors.openProviderSettings')}
          </HUDButton>
        </div>
      )}

      <ChatInput
        onSend={handleSend}
        loading={isLoading}
        disabled={!precomputeReady || advisorConfigured === false || historyLoading || viewingEarlier}
        onOpenAdvisorPanel={() => setAdvisorPanelOpen(true)}
      />
      {advisorProvider === 'chatgpt' && <ChatGPTUsage disabled={isLoading} />}
    </div>
  )
}

export default ChatPage
