// IPC wrapper for API calls - uses window.electronAPI.backend.* internally
// Will be fully implemented in UI-006

declare global {
  interface Window {
    electronAPI?: {
      backend: {
        health: () => Promise<unknown>
        chat: (message: string, sessionKey?: string) => Promise<unknown>
        status: () => Promise<unknown>
        sessions: () => Promise<unknown>
        sessionEvents: (sessionId: string, limit?: number) => Promise<unknown>
        recap: (sessionId: string) => Promise<unknown>
        endSession: () => Promise<unknown>
      }
      getSettings: () => Promise<unknown>
      saveSettings: (settings: unknown) => Promise<unknown>
      showFolderDialog: () => Promise<string | null>
    }
  }
}

export function useBackend() {
  const api = window.electronAPI?.backend

  return {
    health: api?.health,
    chat: api?.chat,
    status: api?.status,
    sessions: api?.sessions,
    sessionEvents: api?.sessionEvents,
    recap: api?.recap,
    endSession: api?.endSession,
  }
}

export default useBackend
