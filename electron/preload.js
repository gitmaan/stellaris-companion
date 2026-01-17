// Preload script - IPC bridge (contextBridge)
// Implements ELEC-003: Expose window.electronAPI with IPC methods
// Security: contextIsolation enabled in main.js, renderer never sees auth token

const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  // Settings
  getSettings: () => ipcRenderer.invoke('get-settings'),
  saveSettings: (settings) => ipcRenderer.invoke('save-settings', settings),
  showFolderDialog: () => ipcRenderer.invoke('show-folder-dialog'),

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
    recap: (sessionId) =>
      ipcRenderer.invoke('backend:recap', { session_id: sessionId }),
    endSession: () => ipcRenderer.invoke('backend:end-session'),
  },

  // Backend status events (sent from main process health checks)
  onBackendStatus: (callback) => {
    const handler = (event, status) => callback(status)
    ipcRenderer.on('backend-status', handler)
    // Return cleanup function
    return () => ipcRenderer.removeListener('backend-status', handler)
  },

  // Updates
  checkForUpdate: () => ipcRenderer.invoke('check-for-update'),
  installUpdate: () => ipcRenderer.invoke('install-update'),
  onUpdateAvailable: (callback) => {
    const handler = (event, info) => callback(info)
    ipcRenderer.on('update-available', handler)
    return () => ipcRenderer.removeListener('update-available', handler)
  },
  onUpdateDownloaded: (callback) => {
    const handler = (event, info) => callback(info)
    ipcRenderer.on('update-downloaded', handler)
    return () => ipcRenderer.removeListener('update-downloaded', handler)
  },
})
