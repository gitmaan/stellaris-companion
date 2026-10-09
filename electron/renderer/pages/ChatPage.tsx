import { useMemo, useState, useCallback, useRef, useEffect } from 'react'

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
  retryRequest?: { text: string; requestId: string }
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
  onOpenSaveSettings?: () => void
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
  modelRoutingMode,
  onOpenSettings,
  onOpenSaveSettings,
  onReportLlmIssue,
}: ChatPageProps) {
  const { t } = useTranslation()
  const backend = useBackend()
  const [messages, setMessages] = useState<Message[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [consumedDraft, setConsumedDraft] = useState<{ text: string } | null>(null)
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
  const [backendConnected, setBackendConnected] = useState<boolean | null>(null)
  const [backendConfigured, setBackendConfigured] = useState(true)
  const sendingRef = useRef(false)
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
  }, [empireType, loadingMessages, roastSuggestion, suggestionPools])

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
      setBackendConnected(status?.connected !== false && (status?.status === 'healthy' || status?.status === 'ok'))
      setBackendConfigured(status?.backend_configured !== false)
      const campaignId = status?.save_id
      if (campaignId && campaignId !== campaignIdRef.current) {
        if (campaignIdRef.current !== null) {
          chatGenerationRef.current += 1
          sendingRef.current = false
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
    setViewingEarlier(false)
    setHasEarlierMessages(false)
    setFirstTurnId(undefined)
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

  const handleSend = useCallback(async (text: string, retry?: { messageId: string; requestId: string }) => {
    if (sendingRef.current || isLoading || historyLoading || viewingEarlier || !precomputeReady || advisorConfigured === false) return false
    sendingRef.current = true
    const generation = chatGenerationRef.current
    const requestId = retry?.requestId ?? crypto.randomUUID()
    // Add user message
    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: text,
      timestamp: new Date(),
    }
    setMessages(prev => retry ? prev.filter(message => message.id !== retry.messageId) : capMessages([...prev, userMessage]))
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
            retryRequest: { text, requestId },
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
          retryRequest: { text, requestId },
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
        if (retry) setConsumedDraft({ text })
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
        retryRequest: { text, requestId },
      }
      setMessages(prev => capMessages([...prev, errorMessage]))
      return false
    } finally {
      if (isMountedRef.current && generation === chatGenerationRef.current) {
        sendingRef.current = false
        setIsLoading(false)
      }
    }
  }, [precomputeReady, advisorConfigured, advisorProvider, backend, sessionKey, empireType, modelRoutingMode, loadingMessages, t, activeCampaignId, conversationId, isLoading, historyLoading, historyError, viewingEarlier])

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
    setScrollToBottomSignal(v => v + 1)
  }, [isLoading, historyLoading, activeCampaignId, backend, roastSuggestion, suggestionPools])

  const items = useMemo(() => {
    const base = messages.map((message, idx) => ({
      key: message.id,
      render: (ref: (el: HTMLDivElement | null) => void, animateEntrance: boolean) => (
        <ChatMessage
          key={message.id}
          messageId={message.id}
          ref={ref}
          animateEntrance={animateEntrance}
          onRetry={message.retryRequest && !isLoading && !historyLoading && !viewingEarlier && advisorConfigured !== false ? () => void handleSend(message.retryRequest!.text, { messageId: message.id, requestId: message.retryRequest!.requestId }) : undefined}
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
        render: (ref: (el: HTMLDivElement | null) => void, _animateEntrance: boolean) => (
          <div key="__loading__" ref={ref} className="max-w-[92%] shrink-0 mb-3 self-start flex items-center gap-3 p-4 text-text-secondary text-sm" role="status">
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
  }, [messages, isLoading, historyLoading, viewingEarlier, advisorConfigured, handleSend, loadingMessage, onOpenSettings, onReportLlmIssue, t])

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

      <div className="relative shrink-0 flex h-12 items-center justify-end gap-3 mb-1">
          {(hasEarlierMessages || viewingEarlier) && <div className="mr-auto flex gap-3 text-xs text-text-secondary">
            {hasEarlierMessages && <button type="button" disabled={isLoading || historyLoading} onClick={() => activeCampaignId && void restoreConversation(activeCampaignId, conversationId, firstTurnId)}>{t('continuity.earlierMessages')}</button>}
            {viewingEarlier && <button type="button" disabled={historyLoading} onClick={() => activeCampaignId && void restoreConversation(activeCampaignId, conversationId)}>{t('continuity.latestMessages')}</button>}
          </div>}
          {historyError && <button type="button" disabled={isLoading || historyLoading} className="text-xs text-accent-yellow" onClick={() => activeCampaignId && void restoreConversation(activeCampaignId, historyTargetRef.current ?? conversationId)}>{t('continuity.historyRetry')}</button>}
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

      {messages.length === 0 ? (
        <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar px-3 pt-4 pb-6">
          <div className="w-full max-w-2xl mx-auto flex flex-col items-center gap-6">
            <header className="text-center space-y-3">
              <FolderIconG className="text-accent-cyan mx-auto" size={isWelcomeCompact ? 24 : 36} />
              <HUDHeader size={isWelcomeCompact ? 'lg' : 'xl'} className="tracking-wide text-accent-cyan text-glow">
                {t('chat.welcome.title')}
              </HUDHeader>
              <p className="min-h-10 text-text-secondary font-mono text-sm" role="status">
                {t(backendConnected === null ? 'status.connecting' : !backendConnected ? (backendConfigured ? 'visualQuality.offline' : 'status.notConfigured') : !saveLoaded ? 'visualQuality.noSave' : !precomputeReady ? 'chat.welcome.scanningShort' : advisorConfigured === false ? 'chat.providerSetup.title' : 'chat.welcome.ready')}
              </p>
            </header>
            <div className="w-full min-h-48">
              {backendConnected && saveLoaded && precomputeReady && advisorConfigured !== false ? (
                <HUDPanel title={t('chat.welcome.suggested')} variant="primary">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                    {visibleSuggestions.map((suggestion, idx) => (
                      <button key={suggestion} onClick={() => void handleSend(suggestion)} disabled={historyLoading}
                        className="flex items-start gap-3 p-3 text-left border border-transparent rounded hover:border-accent-cyan/20 hover:bg-accent-cyan/5 transition-colors disabled:opacity-50">
                        <span aria-hidden="true" className="font-mono text-xs text-accent-cyan/70">{String(idx + 1).padStart(2, '0')}</span>
                        <span className="font-mono text-xs text-text-primary">{suggestion}</span>
                      </button>
                    ))}
                  </div>
                </HUDPanel>
              ) : (
                <HUDPanel variant="secondary">
                  <div className="flex flex-col items-start gap-4 p-1">
                    <p className="text-sm leading-relaxed text-text-secondary">
                      {advisorConfigured === false
                        ? t('chat.providerSetup.description', { provider: getAdvisorProviderName(advisorProvider) })
                        : t(backendConnected === null ? 'visualQuality.connectingHelp' : !backendConnected ? 'visualQuality.offlineHelp' : !saveLoaded ? 'visualQuality.noSaveHelp' : 'visualQuality.analyzingHelp')}
                    </p>
                    {(advisorConfigured === false || backendConnected === false || (backendConnected && !saveLoaded)) && (
                      <HUDButton type="button" variant="secondary" onClick={advisorConfigured === false || !backendConfigured ? onOpenSettings : onOpenSaveSettings}>
                        {t(advisorConfigured === false || !backendConfigured ? 'chat.errors.openProviderSettings' : 'visualQuality.saveSettings')}
                      </HUDButton>
                    )}
                  </div>
                </HUDPanel>
              )}
            </div>
          </div>
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
        identityKey={sessionKey}
        consumedDraft={consumedDraft}
        onSend={handleSend}
        loading={isLoading}
        disabled={!backendConnected || !precomputeReady || advisorConfigured === false || historyLoading || viewingEarlier}
        onOpenAdvisorPanel={() => setAdvisorPanelOpen(true)}
      />
      <div className="h-12 shrink-0">{advisorProvider === 'chatgpt' && <ChatGPTUsage disabled={isLoading} />}</div>
    </div>
  )
}

export default ChatPage
