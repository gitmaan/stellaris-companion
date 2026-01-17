// Preload script - IPC bridge (contextBridge)
// Full implementation in ELEC-003

const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  // Settings
  getSettings: () => ipcRenderer.invoke('get-settings'),
  saveSettings: (settings) => ipcRenderer.invoke('save-settings', settings),
  showFolderDialog: () => ipcRenderer.invoke('show-folder-dialog'),

  // Backend (proxied through main)
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

  // Updates
  checkForUpdate: () => ipcRenderer.invoke('check-for-update'),
  installUpdate: () => ipcRenderer.invoke('install-update'),
  onUpdateAvailable: (callback) => ipcRenderer.on('update-available', callback),
  onUpdateDownloaded: (callback) =>
    ipcRenderer.on('update-downloaded', callback),
})
