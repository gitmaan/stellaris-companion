import type {
  AdvisorCustomResponse,
  Announcement,
  BackendIpcResponse,
  BackendStatusEvent,
  ChatResponse,
  ChronicleCustomResponse,
  ChronicleResponse,
  DiagnosticsResponse,
  DiscordConnectResult,
  DiscordRelayStatus,
  DiscordStatus,
  EndSessionResponse,
  HealthResponse,
  RecapResponse,
  RegenerateChapterResponse,
  SessionEventsResponse,
  SessionsResponse,
  StatusResponse,
} from './hooks/useBackend'

declare global {
  interface Window {
    electronAPI?: {
      backend: {
        health: () => Promise<BackendIpcResponse<HealthResponse>>
        diagnostics: () => Promise<BackendIpcResponse<DiagnosticsResponse>>
        chat: (message: string, sessionKey?: string) => Promise<BackendIpcResponse<ChatResponse>>
        status: () => Promise<BackendIpcResponse<StatusResponse>>
        sessions: () => Promise<BackendIpcResponse<SessionsResponse>>
        sessionEvents: (sessionId: string, limit?: number) => Promise<BackendIpcResponse<SessionEventsResponse>>
        recap: (sessionId: string, style?: string) => Promise<BackendIpcResponse<RecapResponse>>
        chronicle: (sessionId: string, forceRefresh?: boolean, chapterOnly?: boolean) => Promise<BackendIpcResponse<ChronicleResponse>>
        regenerateChapter: (sessionId: string, chapterNumber: number, confirm?: boolean, regenerationInstructions?: string) => Promise<BackendIpcResponse<RegenerateChapterResponse>>
        endSession: () => Promise<BackendIpcResponse<EndSessionResponse>>
        getChronicleCustom: () => Promise<BackendIpcResponse<ChronicleCustomResponse>>
        setChronicleCustom: (customInstructions: string) => Promise<BackendIpcResponse<ChronicleCustomResponse>>
        getSessionAdvisorCustom: () => Promise<BackendIpcResponse<AdvisorCustomResponse>>
        setSessionAdvisorCustom: (customInstructions: string) => Promise<BackendIpcResponse<AdvisorCustomResponse>>
      }
      // Settings
      getSettings: () => Promise<unknown>
      saveSettings: (settings: unknown) => Promise<unknown>
      showFolderDialog: () => Promise<string | null>
      // Feedback reporting
      getPlatformInfo: () => { platform: string; arch: string }
      captureScreenshot: () => Promise<string | null>
      getAppVersion: () => Promise<string>
      getInstallId: () => Promise<string>
      copyToClipboard: (text: string) => Promise<{ success: boolean }>
      openExternal: (url: string) => Promise<{ success: boolean }>
      exportChronicle: (html: string, defaultFilename: string) => Promise<{ success: boolean; filePath?: string; error?: string } | null>
      getBackendLogTail: (opts?: { maxBytes?: number }) => Promise<{ ok: true; data: string } | { ok: false; error: string }>
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
      // Announcements
      announcements: {
        fetch: (forceRefresh?: boolean) => Promise<Announcement[]>
        dismiss: (id: string) => Promise<{ success: boolean }>
        dismissMany: (ids: string[]) => Promise<{ success: boolean; dismissed?: string[]; error?: string }>
        undismiss: (id: string) => Promise<{ success: boolean; error?: string }>
        resetDismissed: () => Promise<{ success: boolean }>
        getDismissed: () => Promise<string[]>
        markRead: () => Promise<{ success: boolean }>
        getLastRead: () => Promise<number>
      }
      onAnnouncementsUpdated: (callback: (announcements: Announcement[]) => void) => () => void
    }
  }
}

export {}
