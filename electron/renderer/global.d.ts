import type {
  AdvisorCustomResponse,
  Announcement,
  BackendIpcResponse,
  BackendStatusEvent,
  ChatResponse,
  ChatContinuity,
  ConversationsResponse,
  ConversationResponse,
  CreatedConversationResponse,
  ChronicleCustomResponse,
  ChronicleResponse,
  DiagnosticsResponse,
  DiscordConnectResult,
  DiscordRelayStatus,
  DiscordStatus,
  EndSessionResponse,
  HealthResponse,
  HistoryStorageResponse,
  PlaythroughMutationResponse,
  PlaythroughsResponse,
  RecapResponse,
  RegenerateChapterResponse,
  SessionEventsResponse,
  SessionsResponse,
  StatusResponse,
} from './hooks/useBackend'
import type { ChronicleRefreshMode, ModelRoutingMode } from './hooks/useSettings'

export interface ChatGPTStatus {
  connected: boolean
  ready: boolean
  connecting: boolean
  welcomePending: boolean
  account: { id: string; email: string; name: string; model: string; modelName?: string } | null
  accounts: Array<{ id: string; email: string; name: string; model: string }>
  model: string
  recommendedModel?: string
  models: Array<{ id: string; name: string; contextLength?: number }>
  revocationConfirmed?: boolean
}
export interface ChatGPTResult { ok: boolean; status: ChatGPTStatus; code?: string }

export interface McpRelayHealthResult {
  ok: boolean
  serverHealthy?: boolean
  campaignReady?: boolean
  message: string
  durationMs?: number
  toolCount?: number
  toolNames?: string[]
  stderr?: string
  protocolVersion?: string | null
  serverVersion?: string | null
  campaign?: {
    save_loaded?: boolean
    campaign_ref?: string
    empire_name?: string
    game_date?: string
    snapshot_count?: number
    freshness?: { state?: string; seconds?: number; message?: string }
  }
}

export interface McpRelayClientStatus {
  available?: boolean
  executable?: string | null
  configPath?: string
  configExists?: boolean
  configured: boolean
  current?: boolean
  serverName?: string | null
  serverNames?: string[]
  error?: string | null
}

export interface McpRelayStatus {
  serverName: string
  dbPath: string
  settingsPath: string
  databaseExists: boolean
  logDir: string
  logPath: string
  mcpbPath?: string | null
  language: string
  command: string
  args: string[]
  env: Record<string, string>
  snippets: {
    claudeDesktop: string
    claudeCode: string
    codex: string
    genericJson: string
  }
  claudeDesktop: McpRelayClientStatus & {
    mcpb?: {
      settingsDir: string
      configPath: string | null
      configExists: boolean
      configured: boolean
      current?: boolean
      enabled?: boolean
      appPath?: string | null
      error?: string | null
    }
  }
  codex: McpRelayClientStatus
  cursor: McpRelayClientStatus
  clients: {
    claude: McpRelayClientStatus
    codex: McpRelayClientStatus
    cursor: McpRelayClientStatus
  }
}

export interface McpRelayInstallResult {
  success: boolean
  configPath?: string
  serverName?: string
  error?: string
  warning?: string
  status?: McpRelayStatus
}

export type ChroniclePublicationVisibility = 'unlisted' | 'discoverable'
export type ChronicleModerationStatus = 'not_required' | 'pending' | 'approved' | 'rejected'

export interface ChroniclePublicationReceipt {
  clientPublicationId: string
  storyId: string
  publicUrl: string
  title: string
  revision: number
  visibility: ChroniclePublicationVisibility
  moderationStatus: ChronicleModerationStatus
  publishedAt: string
  updatedAt: string
}

export interface ChroniclePublicationStatus {
  state: 'unpublished' | 'published'
  receipt?: ChroniclePublicationReceipt
  syncWarning?: string
}

export interface ChroniclePublicationError {
  code: string
  message: string
  status?: number
  currentRevision?: number
}

export type ChroniclePublicationResult<T> =
  | { ok: true; data: T }
  | { ok: false; error: ChroniclePublicationError }

export interface ChroniclePublicationPayload {
  saveId: string
  title: string
  empireName: string
  language: string
  visibility: ChroniclePublicationVisibility
  document: {
    chapters: ChronicleResponse['chapters']
    current_era?: NonNullable<ChronicleResponse['current_era']>
  }
}

export interface ChroniclePublicationSummary {
  saveId: string
  state: 'unpublished' | 'publishing' | 'published'
  title: string
  publicUrl: string | null
}

declare global {
  interface Window {
    electronAPI?: {
      backend: {
        health: () => Promise<BackendIpcResponse<HealthResponse>>
        diagnostics: () => Promise<BackendIpcResponse<DiagnosticsResponse>>
        chat: (
          message: string,
          sessionKey?: string,
          model?: string,
          modelRoutingMode?: ModelRoutingMode,
          continuity?: ChatContinuity,
        ) => Promise<BackendIpcResponse<ChatResponse>>
        status: () => Promise<BackendIpcResponse<StatusResponse>>
        sessions: () => Promise<BackendIpcResponse<SessionsResponse>>
        playthroughs: (includeTrashed?: boolean) => Promise<BackendIpcResponse<PlaythroughsResponse>>
        conversations: (saveId: string) => Promise<BackendIpcResponse<ConversationsResponse>>
        createConversation: (saveId: string) => Promise<BackendIpcResponse<CreatedConversationResponse>>
        conversation: (saveId: string, conversationId: string, beforeTurnId?: string) => Promise<BackendIpcResponse<ConversationResponse>>
        editChapter: (saveId: string, chapterNumber: number, expectedRevision: string, title: string, narrative: string) => Promise<BackendIpcResponse<ChronicleResponse>>
        undoChapter: (saveId: string, chapterNumber: number, expectedRevision: string) => Promise<BackendIpcResponse<ChronicleResponse>>
        cachedChronicle: (saveId: string) => Promise<BackendIpcResponse<ChronicleResponse>>
        setPlaythroughLabel: (saveId: string, displayLabel: string | null) => Promise<BackendIpcResponse<PlaythroughMutationResponse>>
        trashPlaythrough: (saveId: string) => Promise<BackendIpcResponse<PlaythroughMutationResponse>>
        restorePlaythrough: (saveId: string) => Promise<BackendIpcResponse<PlaythroughMutationResponse>>
        resetChronicle: (saveId: string, expectedRevision?: string) => Promise<BackendIpcResponse<PlaythroughMutationResponse>>
        undoChronicleReset: (saveId: string) => Promise<BackendIpcResponse<PlaythroughMutationResponse>>
        deletePlaythrough: (saveId: string) => Promise<BackendIpcResponse<PlaythroughMutationResponse>>
        historyStorage: () => Promise<BackendIpcResponse<HistoryStorageResponse>>
        sessionEvents: (sessionId: string, limit?: number) => Promise<BackendIpcResponse<SessionEventsResponse>>
        recap: (
          sessionId: string,
          style?: string,
          modelRoutingMode?: ModelRoutingMode,
        ) => Promise<BackendIpcResponse<RecapResponse>>
        chronicle: (
          sessionId: string,
          forceRefresh?: boolean,
          chapterOnly?: boolean,
          refreshMode?: ChronicleRefreshMode,
          modelRoutingMode?: ModelRoutingMode,
        ) => Promise<BackendIpcResponse<ChronicleResponse>>
        regenerateChapter: (
          sessionId: string,
          chapterNumber: number,
          confirm?: boolean,
          regenerationInstructions?: string,
          modelRoutingMode?: ModelRoutingMode,
          expectedRevision?: string,
        ) => Promise<BackendIpcResponse<RegenerateChapterResponse>>
        endSession: () => Promise<BackendIpcResponse<EndSessionResponse>>
        getChronicleCustom: () => Promise<BackendIpcResponse<ChronicleCustomResponse>>
        setChronicleCustom: (customInstructions: string) => Promise<BackendIpcResponse<ChronicleCustomResponse>>
        getSessionAdvisorCustom: () => Promise<BackendIpcResponse<AdvisorCustomResponse>>
        setSessionAdvisorCustom: (customInstructions: string) => Promise<BackendIpcResponse<AdvisorCustomResponse>>
      }
      // Settings
      chatgpt: {
        status: () => Promise<ChatGPTResult>
        connect: (options?: { profileId?: string; newAccount?: boolean }) => Promise<ChatGPTResult>
        cancel: () => Promise<ChatGPTResult>
        reopen: () => Promise<ChatGPTResult>
        selectAccount: (id: string) => Promise<ChatGPTResult>
        selectModel: (model: string) => Promise<ChatGPTResult>
        disconnect: () => Promise<ChatGPTResult>
        check: () => Promise<ChatGPTResult>
        models: () => Promise<ChatGPTResult>
        acknowledgeWelcome: () => Promise<ChatGPTResult>
        onChanged: (callback: (status: ChatGPTStatus) => void) => () => void
      }
      getSettings: () => Promise<unknown>
      saveSettings: (settings: unknown) => Promise<{ success: boolean; language?: string; resolvedLanguage?: string }>
      showFolderDialog: () => Promise<string | null>
      advisorProviders: {
        connectOpenRouter: () => Promise<{ ok: boolean; credentialId?: string; errorCode?: string }>
        cancelOpenRouter: () => Promise<{ ok: boolean }>
        listModels: (config: {
          provider: string
          baseUrl?: string
          apiKey?: string
          credentialId?: string
        }) => Promise<{
          ok: boolean
          models?: Array<{
            id: string
            name: string
            contextLength?: number
            supportedParameters?: string[]
            outputModalities?: string[]
            recommended?: boolean
            pricing?: { inputPerMillion: number; outputPerMillion: number }
          }>
          baseUrl?: string
          provider?: string
          error?: string
          errorCode?: string
          status?: number
        }>
        testModel: (config: {
          provider: string
          baseUrl?: string
          apiKey?: string
          credentialId?: string
          model: string
        }) => Promise<{
          ok: boolean
          model?: string
          baseUrl?: string
          provider?: string
          structuredOutput?: boolean
          advisorReady?: boolean
          chronicleReady?: boolean
          errorCode?: string
          status?: number
          error?: string
        }>
      }
      // Feedback reporting
      getPlatformInfo: () => { platform: string; arch: string }
      captureScreenshot: () => Promise<string | null>
      getAppVersion: () => Promise<string>
      getInstallId: () => Promise<string>
      copyToClipboard: (text: string) => Promise<{ success: boolean }>
      openExternal: (url: string) => Promise<{ success: boolean }>
      exportChronicle: (html: string, defaultFilename: string) => Promise<{ success: boolean; filePath?: string; error?: string } | null>
      revealHistoryData: () => Promise<{ success: boolean; path?: string; error?: string }>
      backupHistory: () => Promise<BackendIpcResponse<{ path: string; bytes: number }> | null>
      chroniclePublishing: {
        publish: (publication: ChroniclePublicationPayload) => Promise<ChroniclePublicationResult<ChroniclePublicationReceipt>>
        status: (saveId: string) => Promise<ChroniclePublicationResult<ChroniclePublicationStatus>>
        delete: (saveId: string) => Promise<ChroniclePublicationResult<{ removed: true }>>
        list: () => Promise<ChroniclePublicationResult<ChroniclePublicationSummary[]>>
      }
      getBackendLogTail: (opts?: { maxBytes?: number }) => Promise<{ ok: true; data: string } | { ok: false; error: string }>
      mcpRelay: {
        status: () => Promise<McpRelayStatus>
        healthCheck: () => Promise<McpRelayHealthResult>
        installClaudeDesktop: () => Promise<McpRelayInstallResult>
        connectClient: (client: 'claude' | 'codex' | 'cursor') => Promise<McpRelayInstallResult>
        disconnectClient: (client: 'claude' | 'codex' | 'cursor') => Promise<McpRelayInstallResult>
        openClaudeExtension: () => Promise<{ success: boolean; error?: string }>
        revealPath: (filePath: string) => Promise<{ success: boolean }>
        openClaudeConfigFolder: () => Promise<{ success: boolean }>
      }
      // Backend status events
      onBackendStatus: (callback: (status: BackendStatusEvent) => void) => () => void
      // Updates
      checkForUpdate: () => Promise<{
        updateAvailable: boolean
        version?: string
        releaseName?: string
        releaseNotes?: string
        error?: string
      }>
      installUpdate: () => Promise<{ success: boolean; alreadyInProgress?: boolean; error?: string }>
      onUpdateAvailable: (callback: (payload: {
        version?: string
        releaseName?: string
        releaseNotes?: string
      }) => void) => () => void
      onUpdateDownloaded: (callback: (payload: {
        version?: string
        releaseName?: string
        releaseNotes?: string
      }) => void) => () => void
      onUpdateDownloadProgress: (callback: (progress: number) => void) => () => void
      onUpdateInstalling: (callback: (payload: {
        version?: string
        releaseName?: string
        releaseNotes?: string
      }) => void) => () => void
      onUpdateError: (callback: (message: string) => void) => () => void
      // Onboarding
      onboarding: {
        getStatus: () => Promise<boolean>
        complete: () => Promise<{ success: boolean }>
        detectSaves: () => Promise<{
          found: boolean
          directory: string | null
          saveCount: number
          latest: { name: string; modified: string } | null
        }>
        detectSavesInDir: (directory: string) => Promise<{
          found: boolean
          directory: string | null
          saveCount: number
          latest: { name: string; modified: string } | null
        }>
      }
      // Discord OAuth (DISC-015)
      discord: {
        connect: () => Promise<DiscordConnectResult>
        disconnect: () => Promise<{ success: boolean }>
        status: () => Promise<DiscordStatus>
        relayConnect: () => Promise<{ success: boolean; error?: string }>
        relayDisconnect: () => Promise<{ success: boolean }>
        relayStatus: () => Promise<DiscordRelayStatus>
      }
      onDiscordRelayStatus: (callback: (status: DiscordRelayStatus) => void) => () => void
      onDiscordAuthRequired: (callback: (data: { reason: string }) => void) => () => void
      // Native window visibility
      getWindowVisible: () => Promise<boolean>
      onWindowVisibilityChanged: (callback: (visible: boolean) => void) => () => void
      // Announcements
      announcements: {
        fetch: (forceRefresh?: boolean) => Promise<Announcement[]>
        dismiss: (id: string) => Promise<{ success: boolean }>
        dismissMany: (ids: string[]) => Promise<{ success: boolean; dismissed?: string[]; error?: string }>
        undismiss: (id: string) => Promise<{ success: boolean; error?: string }>
        resetDismissed: () => Promise<{ success: boolean }>
        getDismissed: () => Promise<string[]>
        getReadIds: () => Promise<string[]>
        markRead: (ids: string[]) => Promise<{ success: boolean; readIds: string[] }>
        getLastRead: () => Promise<number>
      }
      onAnnouncementsUpdated: (callback: (announcements: Announcement[]) => void) => () => void
    }
  }
}

export {}
