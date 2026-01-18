# Electron App - Electron Specification

## Directory Structure

```
electron/
├── main.js                        # Main process entry
├── preload.js                     # IPC bridge (contextBridge)
├── package.json                   # Electron + React deps
├── electron-builder.yml           # Build configuration
├── vite.config.ts                 # Vite bundler config
├── tsconfig.json                  # TypeScript config
├── assets/
│   ├── icon.icns                  # macOS app icon
│   ├── icon.ico                   # Windows icon
│   ├── icon.png                   # Linux icon (512x512)
│   └── trayTemplate.png           # macOS tray (22x22, template image)
└── renderer/
    ├── index.html                 # HTML entry
    ├── index.tsx                  # React entry
    ├── App.tsx                    # Main app with routing
    ├── pages/
    │   ├── ChatPage.tsx
    │   ├── SettingsPage.tsx
    │   └── RecapPage.tsx
    ├── components/
    │   ├── ChatMessage.tsx
    │   ├── ChatInput.tsx
    │   ├── SessionList.tsx
    │   ├── RecapViewer.tsx
    │   └── StatusBar.tsx
    ├── hooks/
    │   ├── useBackend.ts          # IPC wrapper for API calls
    │   └── useSettings.ts         # Settings state
    └── styles/
        └── global.css
```

## Main Process (main.js)

### Responsibilities

1. **Window Management**
   - Create BrowserWindow with preload script
   - Minimize to tray on close (macOS: keep running)
   - Show/hide from tray

2. **System Tray**
   - Status indicator icon
   - Context menu: Open, Status, Quit
   - Click to show/hide window

3. **Python Backend Management**
   - Generate per-launch auth token
   - Spawn Python subprocess with environment
   - Health check on startup
   - Kill on quit

4. **Settings Storage**
   - `keytar` for secrets (GOOGLE_API_KEY, DISCORD_BOT_TOKEN)
   - `electron-store` for non-secrets (savePath, discordEnabled)

5. **IPC Handlers**
   - Proxy API calls to Python backend (add auth header)
   - Settings get/set
   - Folder picker dialog

6. **Auto-Updater** (future)
   - Check GitHub releases
   - Download and install

### IPC Channels

```typescript
// Settings
'get-settings' → { googleApiKey: string (masked), discordToken: string (masked), savePath: string, discordEnabled: boolean }
'save-settings' → { googleApiKey?, discordToken?, savePath?, discordEnabled? } → { success: boolean }
'show-folder-dialog' → string | null

// Backend proxy (main process calls Python, adds auth)
'backend:health' → HealthResponse
'backend:chat' → { message: string, session_key?: string } → ChatResponse
'backend:status' → StatusResponse
'backend:sessions' → SessionsResponse
'backend:session-events' → { session_id: string, limit?: number } → EventsResponse
'backend:recap' → { session_id: string } → RecapResponse
'backend:end-session' → EndSessionResponse

// Updates
'check-for-update' → void
'install-update' → void
'update-available' → (event from main)
'update-downloaded' → (event from main)
```

### Security

- `nodeIntegration: false`
- `contextIsolation: true`
- Preload script exposes only specific IPC methods
- Renderer never sees auth token or backend port
- No remote module

## Preload Script (preload.js)

Exposes safe API via contextBridge:

```typescript
window.electronAPI = {
  // Settings
  getSettings: () => ipcRenderer.invoke('get-settings'),
  saveSettings: (settings) => ipcRenderer.invoke('save-settings', settings),
  showFolderDialog: () => ipcRenderer.invoke('show-folder-dialog'),

  // Backend (proxied through main)
  backend: {
    health: () => ipcRenderer.invoke('backend:health'),
    chat: (message, sessionKey?) => ipcRenderer.invoke('backend:chat', { message, session_key: sessionKey }),
    status: () => ipcRenderer.invoke('backend:status'),
    sessions: () => ipcRenderer.invoke('backend:sessions'),
    sessionEvents: (sessionId, limit?) => ipcRenderer.invoke('backend:session-events', { session_id: sessionId, limit }),
    recap: (sessionId) => ipcRenderer.invoke('backend:recap', { session_id: sessionId }),
    endSession: () => ipcRenderer.invoke('backend:end-session'),
  },

  // Updates
  checkForUpdate: () => ipcRenderer.invoke('check-for-update'),
  installUpdate: () => ipcRenderer.invoke('install-update'),
  onUpdateAvailable: (callback) => ipcRenderer.on('update-available', callback),
  onUpdateDownloaded: (callback) => ipcRenderer.on('update-downloaded', callback),
}
```

## Renderer (React)

### App.tsx

Simple routing with tab navigation:
- Chat (default)
- Recap
- Settings

### ChatPage

- Message list with user/assistant distinction
- Input field with send button
- Loading spinner during API call
- Error display
- StatusBar at top (empire name, game date, backend status)

### SettingsPage

- Google API Key input (password field, shows masked if set)
- Save path with Browse button (folder dialog)
- Discord toggle checkbox
- Discord bot token (shown only if enabled)
- Save button (restarts backend with new settings)
- Link to Google AI Studio for getting API key

### RecapPage

- Session list sidebar
- Selected session details (empire, date range, snapshot count)
- Generate Recap button
- Recap viewer (markdown rendered)
- End Current Session button

## First-Run Experience

1. App launches, shows Settings page
2. "Welcome to Stellaris Companion" header
3. API key field highlighted, link to get key
4. Backend not started until key saved
5. After saving key → backend starts → redirect to Chat

## Window Configuration

```javascript
{
  width: 1000,
  height: 700,
  minWidth: 800,
  minHeight: 600,
  titleBarStyle: 'hiddenInset',  // macOS native
  webPreferences: {
    preload: path.join(__dirname, 'preload.js'),
    nodeIntegration: false,
    contextIsolation: true,
  }
}
```

## Build Configuration (electron-builder.yml)

```yaml
appId: com.stellaris.companion
productName: Stellaris Companion
directories:
  output: dist
files:
  - main.js
  - preload.js
  - renderer/dist/**/*
extraResources:
  - from: ../dist-python
    to: python-backend
mac:
  category: public.app-category.games
  target:
    - dmg
    - zip
  icon: assets/icon.icns
win:
  target: nsis
  icon: assets/icon.ico
linux:
  target: AppImage
  icon: assets/icon.png
```
