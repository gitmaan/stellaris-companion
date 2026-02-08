// Preload script - IPC bridge (contextBridge)
// Implements ELEC-003: Expose window.electronAPI with IPC methods
// Security: contextIsolation enabled in main.js, renderer never sees auth token

const { contextBridge, ipcRenderer } = require('electron')

// Track active listeners to prevent accumulation
// Each channel can have multiple callbacks, but only one IPC listener
const listenerRegistry = new Map()

/**
 * Create a managed event listener that prevents accumulation.
 * Uses a single IPC listener per channel that dispatches to registered callbacks.
 * @param {string} channel - The IPC channel name
 * @param {Function} callback - The callback to register
 * @returns {Function} Cleanup function to unregister the callback
 */
function createManagedListener(channel, callback) {
  if (!listenerRegistry.has(channel)) {
    // First listener for this channel - create the IPC listener
    const callbacks = new Set()
    const ipcHandler = (event, ...args) => {
      callbacks.forEach(cb => cb(...args))
    }
    ipcRenderer.on(channel, ipcHandler)
    listenerRegistry.set(channel, { callbacks, ipcHandler })
  }

  const { callbacks } = listenerRegistry.get(channel)
  callbacks.add(callback)

  // Return cleanup function
  return () => {
    callbacks.delete(callback)
    // If no more callbacks, remove the IPC listener entirely
    if (callbacks.size === 0) {
      const { ipcHandler } = listenerRegistry.get(channel)
      ipcRenderer.removeListener(channel, ipcHandler)
      listenerRegistry.delete(channel)
    }
  }
}

contextBridge.exposeInMainWorld('electronAPI', {
  // Settings
  getSettings: () => ipcRenderer.invoke('load-settings'),
  saveSettings: (settings) => ipcRenderer.invoke('save-settings', settings),
  showFolderDialog: () => ipcRenderer.invoke('select-folder'),

  // Feedback reporting
  getPlatformInfo: () => ({ platform: process.platform, arch: process.arch }),
  captureScreenshot: () => ipcRenderer.invoke('capture-screenshot'),
  getAppVersion: () => ipcRenderer.invoke('get-app-version'),
  getInstallId: () => ipcRenderer.invoke('get-install-id'),
  copyToClipboard: (text) => ipcRenderer.invoke('copy-to-clipboard', { text }),
  openExternal: (url) => ipcRenderer.invoke('open-external', { url }),
  exportChronicle: (html, defaultFilename) => ipcRenderer.invoke('export-chronicle', { html, defaultFilename }),
  getBackendLogTail: (opts) => ipcRenderer.invoke('get-backend-log-tail', opts || {}),

  // Backend (proxied through main process which adds auth header)
  backend: {
    health: () => ipcRenderer.invoke('backend:health'),
    diagnostics: () => ipcRenderer.invoke('backend:diagnostics'),
    chat: (message, sessionKey) =>
      ipcRenderer.invoke('backend:chat', { message, session_key: sessionKey }),
    status: () => ipcRenderer.invoke('backend:status'),
    sessions: () => ipcRenderer.invoke('backend:sessions'),
    sessionEvents: (sessionId, limit) =>
      ipcRenderer.invoke('backend:session-events', {
        session_id: sessionId,
        limit,
      }),
    recap: (sessionId, style) =>
      ipcRenderer.invoke('backend:recap', { session_id: sessionId, style: style || 'summary' }),
    chronicle: (sessionId, forceRefresh, chapterOnly) =>
      ipcRenderer.invoke('backend:chronicle', {
        session_id: sessionId,
        force_refresh: forceRefresh || false,
        chapter_only: chapterOnly || false,
      }),
    regenerateChapter: (sessionId, chapterNumber, confirm, regenerationInstructions) =>
      ipcRenderer.invoke('backend:regenerate-chapter', {
        session_id: sessionId,
        chapter_number: chapterNumber,
        confirm: confirm || false,
        regeneration_instructions: regenerationInstructions || null,
      }),
    endSession: () => ipcRenderer.invoke('backend:end-session'),
    getChronicleCustom: () => ipcRenderer.invoke('backend:get-chronicle-custom'),
    setChronicleCustom: (customInstructions) =>
      ipcRenderer.invoke('backend:set-chronicle-custom', {
        custom_instructions: customInstructions,
      }),
    getSessionAdvisorCustom: () => ipcRenderer.invoke('backend:get-session-advisor-custom'),
    setSessionAdvisorCustom: (customInstructions) =>
      ipcRenderer.invoke('backend:set-session-advisor-custom', {
        custom_instructions: customInstructions,
      }),
  },

  // Backend status events (sent from main process health checks)
  // Uses managed listener to prevent accumulation
  onBackendStatus: (callback) => {
    return createManagedListener('backend-status', callback)
  },

  // Updates
  checkForUpdate: () => ipcRenderer.invoke('check-for-update'),
  installUpdate: () => ipcRenderer.invoke('install-update'),
  // Uses managed listener to prevent accumulation
  onUpdateAvailable: (callback) => {
    return createManagedListener('update-available', callback)
  },
  onUpdateDownloaded: (callback) => {
    return createManagedListener('update-downloaded', callback)
  },
  onUpdateDownloadProgress: (callback) => {
    return createManagedListener('update-download-progress', callback)
  },
  onUpdateError: (callback) => {
    return createManagedListener('update-error', callback)
  },

  // Discord OAuth (DISC-015: Settings UI for Discord integration)
  discord: {
    // Start OAuth PKCE flow - opens browser for user authorization
    connect: () => ipcRenderer.invoke('discord:connect'),
    // Disconnect from Discord - clears tokens and relay connection
    disconnect: () => ipcRenderer.invoke('discord:disconnect'),
    // Get current Discord connection status (connected, username, etc.)
    status: () => ipcRenderer.invoke('discord:status'),
    // Relay connection management
    relayConnect: () => ipcRenderer.invoke('discord:relay-connect'),
    relayDisconnect: () => ipcRenderer.invoke('discord:relay-disconnect'),
    relayStatus: () => ipcRenderer.invoke('discord:relay-status'),
  },
  // Discord relay status events (WebSocket connection state changes)
  onDiscordRelayStatus: (callback) => {
    return createManagedListener('discord-relay-status', callback)
  },
  // Discord auth required event (when token expires and re-auth needed)
  onDiscordAuthRequired: (callback) => {
    return createManagedListener('discord-auth-required', callback)
  },

  // Onboarding
  onboarding: {
    getStatus: () => ipcRenderer.invoke('onboarding:status'),
    complete: () => ipcRenderer.invoke('onboarding:complete'),
    detectSaves: () => ipcRenderer.invoke('onboarding:detect-saves'),
  },

  // Announcements
  announcements: {
    fetch: (forceRefresh = false) => ipcRenderer.invoke('announcements:fetch', { forceRefresh }),
    dismiss: (id) => ipcRenderer.invoke('announcements:dismiss', { id }),
    dismissMany: (ids) => ipcRenderer.invoke('announcements:dismiss-many', { ids }),
    undismiss: (id) => ipcRenderer.invoke('announcements:undismiss', { id }),
    resetDismissed: () => ipcRenderer.invoke('announcements:reset-dismissed'),
    getDismissed: () => ipcRenderer.invoke('announcements:get-dismissed'),
    markRead: () => ipcRenderer.invoke('announcements:mark-read'),
    getLastRead: () => ipcRenderer.invoke('announcements:get-last-read'),
  },
  onAnnouncementsUpdated: (callback) => {
    return createManagedListener('announcements-updated', callback)
  },
})
