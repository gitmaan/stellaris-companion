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

  // Backend (proxied through main process which adds auth header)
  backend: {
    health: () => ipcRenderer.invoke('backend:health'),
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
    chronicle: (sessionId, forceRefresh) =>
      ipcRenderer.invoke('backend:chronicle', { session_id: sessionId, force_refresh: forceRefresh || false }),
    regenerateChapter: (sessionId, chapterNumber, confirm) =>
      ipcRenderer.invoke('backend:regenerate-chapter', {
        session_id: sessionId,
        chapter_number: chapterNumber,
        confirm: confirm || false,
      }),
    endSession: () => ipcRenderer.invoke('backend:end-session'),
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
  // Uses managed listener to prevent accumulation
  onUpdateDownloaded: (callback) => {
    return createManagedListener('update-downloaded', callback)
  },
})
