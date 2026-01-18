# Electron App Implementation Plan

**Status:** Planning
**Last Updated:** 2026-01-16
**MVP Scope:** Medium (Settings + Chat + Recap Trigger)

---

## Executive Summary

Build a desktop app that:
1. Runs the Python backend in the background
2. Provides a native chat interface (alternative to Discord)
3. Lets users configure API keys and settings
4. Generates session recaps on demand
5. Optionally runs the Discord bot

Distribution: Bundled Python via PyInstaller + Electron; auto-updates via GitHub Releases (after signing/notarization).

---

## MVP Implementation Decisions (Recommended)

These decisions unblock implementation and avoid common Electron pitfalls.

1. **Renderer never calls Python directly**
   - Renderer → `preload.js` → `ipcMain` (main process)
   - Main process calls Python backend over `127.0.0.1` HTTP
   - Benefits: avoids CORS/`file://` origin issues, keeps the backend port private, reduces attack surface

2. **Secrets stored in OS keychain**
   - Store `GOOGLE_API_KEY` + `DISCORD_BOT_TOKEN` via `keytar`
   - Use `electron-store` only for non-secrets (save path, toggles)
   - Do **not** rely on a hardcoded `electron-store` encryption key

3. **Backend API requires a per-launch auth token**
   - Electron generates a random token at launch and passes it to Python via env/args
   - Python requires `Authorization: Bearer <token>` for all `/api/*` routes

4. **First-run behavior**
   - Do not spawn the Python backend until an API key is configured, **or**
   - Update the Python backend to run in “degraded mode” (no LLM calls until key is set)
   - Pick one explicitly; the current `Companion` raises if `GOOGLE_API_KEY` is missing.

5. **Writable paths**
   - Always set `STELLARIS_DB_PATH` to an app-writable location (`app.getPath('userData')`)
   - Avoid writing DB/logs into the install/resources directory

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ELECTRON APP                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         MAIN PROCESS (main.js)                       │    │
│  │                                                                      │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐ │    │
│  │  │   Tray      │  │  Settings   │  │  Subprocess │  │  Updater   │ │    │
│  │  │   Icon      │  │  Store      │  │  Manager    │  │            │ │    │
│  │  │             │  │             │  │             │  │            │ │    │
│  │  │ • Status    │  │ • API key   │  │ • Spawn     │  │ • Check    │ │    │
│  │  │ • Menu      │  │   (keychain)│  │   Python    │  │   GitHub   │ │    │
│  │  │ • Show/     │  │ • Save path │  │ • Health    │  │ • Download │ │    │
│  │  │   Hide      │  │ • Discord   │  │   check     │  │ • Install  │ │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └────────────┘ │    │
│  │                                                                      │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      RENDERER PROCESS (React)                        │    │
│  │                                                                      │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐ │    │
│  │  │  Settings   │  │    Chat     │  │   Recap     │  │  Status    │ │    │
│  │  │    Page     │  │    Page     │  │    Page     │  │   Bar      │ │    │
│  │  │             │  │             │  │             │  │            │ │    │
│  │  │ • API key   │  │ • Messages  │  │ • Session   │  │ • Empire   │ │    │
│  │  │ • Save dir  │  │ • Input     │  │   list      │  │ • Date     │ │    │
│  │  │ • Discord   │  │ • History   │  │ • Generate  │  │ • Backend  │ │    │
│  │  │   toggle    │  │             │  │   button    │  │   status   │ │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └────────────┘ │    │
│  │                                                                      │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│                              IPC Bridge                                      │
│                                  │                                           │
└──────────────────────────────────┼───────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      PYTHON BACKEND (Subprocess)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Entry point: backend/electron_main.py (NEW)                                │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         FastAPI Server                               │    │
│  │                                                                      │    │
│  │  (Main process calls these over localhost + token auth)              │    │
│  │                                                                      │    │
│  │  POST /api/chat           → companion.ask_precomputed()              │    │
│  │  GET  /api/status         → companion.get_status_data()              │    │
│  │  GET  /api/sessions       → db.get_sessions()                        │    │
│  │  POST /api/recap          → generate_recap(session_id)               │    │
│  │  POST /api/end-session    → db.end_session()                         │    │
│  │  GET  /api/health         → {"status": "ok", "game_date": "..."}     │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      Existing Components                             │    │
│  │                                                                      │    │
│  │  • Companion (companion.py)      - Gemini chat, precompute          │    │
│  │  • SaveWatcher (save_watcher.py) - File monitoring                  │    │
│  │  • Database (database.py)        - SQLite history                   │    │
│  │  • Discord Bot (optional)        - If token configured              │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## File Structure

```
stellaris-companion/
├── electron/                          # NEW - Electron app
│   ├── main.js                        # Main process
│   ├── preload.js                     # IPC bridge
│   ├── package.json                   # Electron + React deps
│   ├── electron-builder.yml           # Build configuration
│   ├── assets/
│   │   ├── icon.icns                  # macOS icon
│   │   ├── icon.ico                   # Windows icon
│   │   └── icon.png                   # Linux icon
│   └── renderer/                      # React app
│       ├── index.html
│       ├── index.tsx                  # Entry point
│       ├── App.tsx                    # Main app component
│       ├── pages/
│       │   ├── ChatPage.tsx
│       │   ├── SettingsPage.tsx
│       │   └── RecapPage.tsx
│       ├── components/
│       │   ├── ChatMessage.tsx
│       │   ├── ChatInput.tsx
│       │   ├── SessionList.tsx
│       │   ├── RecapViewer.tsx
│       │   └── StatusBar.tsx
│       ├── hooks/
│       │   ├── useBackend.ts          # API client
│       │   └── useSettings.ts         # Settings store
│       └── styles/
│           └── global.css
│
├── backend/
│   ├── main.py                        # Discord bot entry (existing)
│   ├── electron_main.py               # NEW - FastAPI entry for Electron
│   ├── api/                           # NEW - FastAPI routes
│   │   ├── __init__.py
│   │   ├── server.py                  # FastAPI app
│   │   └── routes/
│   │       ├── chat.py
│   │       ├── status.py
│   │       ├── sessions.py
│   │       └── recap.py
│   └── core/                          # Existing
│       ├── companion.py
│       ├── database.py
│       ├── save_watcher.py
│       └── ...
│
├── scripts/                           # NEW - Build scripts
│   ├── build-python.sh               # PyInstaller bundle
│   └── build-electron.sh             # Full app build
│
└── .github/
    └── workflows/
        └── release.yml                # NEW - CI/CD for releases
```

---

## Implementation Phases

### Phase 0: Hard Decisions & Plumbing (~0.5 day)

**Goal:** Make the integration secure and predictable before building UI.

- Choose renderer → main → python flow (recommended: IPC to main; main calls python)
- Decide first-run strategy:
  - Gate backend startup until key is set (recommended), or
  - Implement backend “degraded mode” (no LLM until key exists)
- Decide how to pick backend port:
  - MVP: fixed port `8742` with “port-in-use” detection + retry/backoff
  - Recommended: dynamic port selected by Electron and passed to Python

### Phase 1: Python Backend API (~1-2 days)

**Goal:** FastAPI server that Electron can talk to.

**Dependencies to add (`requirements.txt`):**
- `fastapi`
- `uvicorn[standard]`

**New env vars (passed from Electron):**
- `STELLARIS_DB_PATH` (required in packaged builds)
- `STELLARIS_API_TOKEN` (required; per-launch bearer token)
- `STELLARIS_API_PORT` (optional; if using a non-default port)

**New file: `backend/electron_main.py`**
```python
"""
Entry point for Electron app - runs FastAPI server + save watcher.
Discord bot is optional based on config.
"""
import os
import sys
import uvicorn
from pathlib import Path

# ... imports ...

def main():
    # Load config from environment or electron-passed args
    api_key = os.environ.get("GOOGLE_API_KEY")
    discord_token = os.environ.get("DISCORD_BOT_TOKEN")  # Optional
    save_path = os.environ.get("STELLARIS_SAVE_PATH")
    db_path = os.environ.get("STELLARIS_DB_PATH")
    api_token = os.environ.get("STELLARIS_API_TOKEN")
    port = int(os.environ.get("STELLARIS_API_PORT", "8742"))

    # Initialize companion
    # NOTE: current Companion requires GOOGLE_API_KEY. For first-run, either:
    # - Gate backend startup until api_key is set, OR
    # - Update Companion/backend to support a degraded mode.
    companion = Companion(save_path=save_path, api_key=api_key)

    # Start save watcher
    def on_save_detected(path: Path) -> None:
        # SaveWatcher runs in its own thread; keep this handler lightweight.
        companion.reload_save(new_path=path)

    watcher = SaveWatcher(on_save_detected=on_save_detected)
    watcher.start()

    # Discord bot (optional): prefer spawning a separate process for MVP.
    # Mixing discord.py + FastAPI in one process adds event-loop complexity.

    # Run FastAPI server
    from backend.api.server import create_app
    app = create_app(companion, api_token=api_token, db_path=db_path)
    uvicorn.run(app, host="127.0.0.1", port=port)

if __name__ == "__main__":
    main()
```

**New file: `backend/api/server.py`**
```python
from fastapi import FastAPI

def create_app(companion, *, api_token: str | None, db_path: str | None) -> FastAPI:
    app = FastAPI(title="Stellaris Companion API")

    # Renderer should NOT call this API directly. Main process calls it, so CORS is unnecessary.
    # If you *do* access it from a browser during development, configure CORS correctly and keep auth enabled.

    # Dependency injection
    app.state.companion = companion
    app.state.api_token = api_token
    app.state.db_path = db_path

    # Register routes
    from backend.api.routes import chat, status, sessions, recap
    app.include_router(chat.router, prefix="/api")
    app.include_router(status.router, prefix="/api")
    app.include_router(sessions.router, prefix="/api")
    app.include_router(recap.router, prefix="/api")

    return app
```

**Authentication requirement (all endpoints)**
- Require `Authorization: Bearer <STELLARIS_API_TOKEN>`
- Reject if token missing/mismatched

**API Routes:**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Backend status + current game date |
| `/api/chat` | POST | Send message, get response |
| `/api/status` | GET | Current empire status |
| `/api/sessions` | GET | List all sessions |
| `/api/sessions/{id}/events` | GET | Events for a session |
| `/api/recap` | POST | Generate recap for session |
| `/api/end-session` | POST | Manually end current session |

---

### Phase 2: Electron Scaffold (~2-3 days)

**Goal:** App shell that spawns Python and shows a window.

**IPC pattern (recommended)**
- Renderer calls `window.electronAPI.*` only
- Main process calls the Python API and attaches `Authorization: Bearer <token>`
- Renderer never sees the backend port or token

**`electron/package.json`**
```json
{
  "name": "stellaris-companion",
  "version": "1.0.0",
  "main": "main.js",
  "scripts": {
    "start": "electron .",
    "build": "electron-builder",
    "dev": "concurrently -k \"vite --port 5173\" \"wait-on tcp:5173 && electron .\""
  },
  "dependencies": {
    "electron-store": "^8.1.0",
    "keytar": "^7.9.0"
  },
  "devDependencies": {
    "electron": "^28.0.0",
    "electron-builder": "^24.9.0",
    "electron-updater": "^6.1.0",
    "concurrently": "^8.2.2",
    "wait-on": "^7.2.0",
    "vite": "^5.0.0",
    "@vitejs/plugin-react": "^4.2.0",
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "typescript": "^5.3.0"
  },
  "build": {
    "appId": "com.stellaris.companion",
    "productName": "Stellaris Companion",
    "directories": {
      "output": "dist"
    },
    "files": [
      "main.js",
      "preload.js",
      "renderer/dist/**/*"
    ],
    "extraResources": [
      {
        "from": "../dist-python",
        "to": "python-backend"
      }
    ],
    "mac": {
      "category": "public.app-category.games",
      "target": ["dmg", "zip"]
    },
    "win": {
      "target": ["nsis"]
    },
    "linux": {
      "target": ["AppImage"]
    },
    "publish": {
      "provider": "github",
      "owner": "YOUR_GITHUB_USERNAME",
      "repo": "stellaris-companion"
    }
  }
}
```

**`electron/main.js`** (core logic)
```javascript
const { app, BrowserWindow, Tray, Menu, ipcMain, dialog } = require('electron');
const { spawn } = require('child_process');
const { autoUpdater } = require('electron-updater');
const Store = require('electron-store');
const keytar = require('keytar');
const path = require('path');
const crypto = require('crypto');

// Store non-secret settings only.
const store = new Store({
  schema: {
    savePath: { type: 'string', default: '' },
    discordEnabled: { type: 'boolean', default: false },
  }
});

const SERVICE = 'stellaris-companion';
const ACCOUNT_GOOGLE = 'GOOGLE_API_KEY';
const ACCOUNT_DISCORD = 'DISCORD_BOT_TOKEN';

let mainWindow;
let tray;
let pythonProcess;
let apiToken; // per-launch token
let apiPort = 8742; // MVP default; can be made dynamic

// === Python Backend Management ===

function getPythonPath() {
  if (app.isPackaged) {
    // Bundled PyInstaller executable
    const platform = process.platform;
    const ext = platform === 'win32' ? '.exe' : '';
    return path.join(process.resourcesPath, 'python-backend', `stellaris-backend${ext}`);
  } else {
    // Development: use system Python
    return 'python';
  }
}

async function startPythonBackend() {
  const pythonPath = getPythonPath();
  const args = app.isPackaged ? [] : ['backend/electron_main.py'];

  const googleApiKey = await keytar.getPassword(SERVICE, ACCOUNT_GOOGLE);
  if (!googleApiKey) {
    // First-run: keep UI up so user can set the key; do not start backend yet.
    return;
  }

  apiToken = crypto.randomBytes(32).toString('hex');

  const env = {
    ...process.env,
    GOOGLE_API_KEY: googleApiKey,
    STELLARIS_SAVE_PATH: store.get('savePath'),
    STELLARIS_DB_PATH: path.join(app.getPath('userData'), 'stellaris_history.db'),
    STELLARIS_API_TOKEN: apiToken,
    STELLARIS_API_PORT: String(apiPort),
  };

  if (store.get('discordEnabled')) {
    const discordToken = await keytar.getPassword(SERVICE, ACCOUNT_DISCORD);
    if (discordToken) env.DISCORD_BOT_TOKEN = discordToken;
  }

  pythonProcess = spawn(pythonPath, args, {
    env,
    cwd: app.isPackaged ? process.resourcesPath : path.join(__dirname, '..'),
  });

  pythonProcess.stdout.on('data', (data) => {
    console.log(`Python: ${data}`);
  });

  pythonProcess.stderr.on('data', (data) => {
    console.error(`Python Error: ${data}`);
  });

  pythonProcess.on('close', (code) => {
    console.log(`Python process exited with code ${code}`);
    // Optionally restart on crash
  });
}

function stopPythonBackend() {
  if (pythonProcess) {
    pythonProcess.kill();
    pythonProcess = null;
  }
}

// === Window Management ===

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1000,
    height: 700,
    minWidth: 800,
    minHeight: 600,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
    titleBarStyle: 'hiddenInset', // macOS native feel
    show: false, // Show when ready
  });

  // Load React app
  if (app.isPackaged) {
    mainWindow.loadFile(path.join(__dirname, 'renderer/dist/index.html'));
  } else {
    mainWindow.loadURL('http://localhost:5173'); // Vite dev server
  }

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  mainWindow.on('close', (event) => {
    // Minimize to tray instead of closing
    if (!app.isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
  });
}

// === System Tray ===

function createTray() {
  const iconPath = path.join(__dirname, 'assets',
    process.platform === 'darwin' ? 'trayTemplate.png' : 'icon.png');

  tray = new Tray(iconPath);

  const contextMenu = Menu.buildFromTemplate([
    { label: 'Open Stellaris Companion', click: () => mainWindow.show() },
    { type: 'separator' },
    { label: 'Status: Watching saves...', enabled: false, id: 'status' },
    { type: 'separator' },
    { label: 'Quit', click: () => {
      app.isQuitting = true;
      app.quit();
    }}
  ]);

  tray.setContextMenu(contextMenu);
  tray.setToolTip('Stellaris Companion');

  tray.on('click', () => {
    mainWindow.isVisible() ? mainWindow.hide() : mainWindow.show();
  });
}

// === Auto-Updater ===

function setupAutoUpdater() {
  if (!app.isPackaged) return;
  // In production, code signing/notarization is required for a good UX.
  autoUpdater.checkForUpdatesAndNotify();

  autoUpdater.on('update-available', () => {
    mainWindow.webContents.send('update-available');
  });

  autoUpdater.on('update-downloaded', () => {
    mainWindow.webContents.send('update-downloaded');
  });
}

// === IPC Handlers ===

ipcMain.handle('get-settings', async () => {
  const hasGoogleApiKey = Boolean(await keytar.getPassword(SERVICE, ACCOUNT_GOOGLE));
  const hasDiscordToken = Boolean(await keytar.getPassword(SERVICE, ACCOUNT_DISCORD));
  return {
    googleApiKey: hasGoogleApiKey ? '••••••••' : '',
    discordToken: hasDiscordToken ? '••••••••' : '',
    savePath: store.get('savePath'),
    discordEnabled: store.get('discordEnabled'),
  };
});

ipcMain.handle('save-settings', async (event, settings) => {
  if (settings.googleApiKey && !settings.googleApiKey.includes('•')) {
    await keytar.setPassword(SERVICE, ACCOUNT_GOOGLE, settings.googleApiKey);
  }
  if (settings.discordToken && !settings.discordToken.includes('•')) {
    await keytar.setPassword(SERVICE, ACCOUNT_DISCORD, settings.discordToken);
  }
  if (settings.savePath !== undefined) {
    store.set('savePath', settings.savePath);
  }
  if (settings.discordEnabled !== undefined) {
    store.set('discordEnabled', settings.discordEnabled);
  }

  // Restart Python backend with new settings
  stopPythonBackend();
  await startPythonBackend();

  return { success: true };
});

ipcMain.handle('show-folder-dialog', async () => {
  const result = await dialog.showOpenDialog({
    properties: ['openDirectory']
  });
  if (result.canceled) return null;
  return result.filePaths[0] || null;
});

ipcMain.handle('install-update', () => {
  autoUpdater.quitAndInstall();
});

// === App Lifecycle ===

app.whenReady().then(async () => {
  // First-run: if key is missing, show Settings first; backend starts after save.
  const hasGoogleApiKey = Boolean(await keytar.getPassword(SERVICE, ACCOUNT_GOOGLE));
  if (!hasGoogleApiKey) {
    // Show settings page on first launch
  }

  await startPythonBackend();
  createWindow();
  createTray();
  setupAutoUpdater();
});

app.on('before-quit', () => {
  stopPythonBackend();
});

app.on('window-all-closed', () => {
  // Keep running in tray on macOS
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
```

---

### Phase 3: React UI (~2-3 days)

**Goal:** Chat interface, settings page, recap trigger.

**Important:** `useBackend` should call `window.electronAPI.*` (IPC) instead of calling `fetch('http://127.0.0.1:...')` from the renderer.

**Key Components:**

**`ChatPage.tsx`**
```tsx
import { useState, useEffect, useRef } from 'react';
import { useBackend } from '../hooks/useBackend';
import ChatMessage from '../components/ChatMessage';
import ChatInput from '../components/ChatInput';
import StatusBar from '../components/StatusBar';

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const { sendChat, getStatus } = useBackend();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const handleSend = async (text: string) => {
    // Add user message
    setMessages(prev => [...prev, { role: 'user', content: text }]);
    setIsLoading(true);

    try {
      const response = await sendChat(text);
      setMessages(prev => [...prev, { role: 'assistant', content: response.text }]);
    } catch (error) {
      setMessages(prev => [...prev, {
        role: 'error',
        content: `Error: ${error.message}`
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="chat-page">
      <StatusBar />
      <div className="messages">
        {messages.map((msg, i) => (
          <ChatMessage key={i} message={msg} />
        ))}
        {isLoading && <ChatMessage message={{ role: 'loading' }} />}
        <div ref={messagesEndRef} />
      </div>
      <ChatInput onSend={handleSend} disabled={isLoading} />
    </div>
  );
}
```

**`SettingsPage.tsx`**
```tsx
import { useState, useEffect } from 'react';

export default function SettingsPage() {
  const [settings, setSettings] = useState({
    googleApiKey: '',
    discordToken: '',
    savePath: '',
    discordEnabled: false,
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    window.electronAPI.getSettings().then(setSettings);
  }, []);

  const handleSave = async () => {
    setSaving(true);
    await window.electronAPI.saveSettings(settings);
    setSaving(false);
  };

  const handleBrowseSavePath = async () => {
    const path = await window.electronAPI.showFolderDialog();
    if (path) {
      setSettings(s => ({ ...s, savePath: path }));
    }
  };

  return (
    <div className="settings-page">
      <h1>Settings</h1>

      <section>
        <h2>API Configuration</h2>
        <label>
          Google API Key (Gemini)
          <input
            type="password"
            value={settings.googleApiKey}
            onChange={e => setSettings(s => ({ ...s, googleApiKey: e.target.value }))}
            placeholder="Enter your Gemini API key"
          />
        </label>
        <p className="hint">
          Get a key at <a href="https://aistudio.google.com/">Google AI Studio</a>
        </p>
      </section>

      <section>
        <h2>Save File Location</h2>
        <div className="path-input">
          <input
            type="text"
            value={settings.savePath}
            onChange={e => setSettings(s => ({ ...s, savePath: e.target.value }))}
            placeholder="Auto-detect"
          />
          <button onClick={handleBrowseSavePath}>Browse...</button>
        </div>
      </section>

      <section>
        <h2>Discord Bot (Optional)</h2>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={settings.discordEnabled}
            onChange={e => setSettings(s => ({ ...s, discordEnabled: e.target.checked }))}
          />
          Enable Discord bot
        </label>
        {settings.discordEnabled && (
          <label>
            Discord Bot Token
            <input
              type="password"
              value={settings.discordToken}
              onChange={e => setSettings(s => ({ ...s, discordToken: e.target.value }))}
              placeholder="Enter your Discord bot token"
            />
          </label>
        )}
      </section>

      <button onClick={handleSave} disabled={saving}>
        {saving ? 'Saving...' : 'Save Settings'}
      </button>
    </div>
  );
}
```

**`RecapPage.tsx`**
```tsx
import { useState, useEffect } from 'react';
import { useBackend } from '../hooks/useBackend';
import SessionList from '../components/SessionList';
import RecapViewer from '../components/RecapViewer';

export default function RecapPage() {
  const [sessions, setSessions] = useState([]);
  const [selectedSession, setSelectedSession] = useState(null);
  const [recap, setRecap] = useState(null);
  const [generating, setGenerating] = useState(false);
  const { getSessions, generateRecap, endSession } = useBackend();

  useEffect(() => {
    getSessions().then(setSessions);
  }, []);

  const handleGenerateRecap = async () => {
    if (!selectedSession) return;
    setGenerating(true);
    try {
      const result = await generateRecap(selectedSession.id);
      setRecap(result);
    } catch (error) {
      alert(`Failed to generate recap: ${error.message}`);
    } finally {
      setGenerating(false);
    }
  };

  const handleEndSession = async () => {
    if (!confirm('End the current session? This will mark it as complete.')) return;
    await endSession();
    getSessions().then(setSessions);
  };

  return (
    <div className="recap-page">
      <div className="sidebar">
        <h2>Sessions</h2>
        <SessionList
          sessions={sessions}
          selected={selectedSession}
          onSelect={setSelectedSession}
        />
        <button onClick={handleEndSession} className="end-session-btn">
          End Current Session
        </button>
      </div>

      <div className="main">
        {selectedSession ? (
          <>
            <h1>{selectedSession.empire_name}</h1>
            <p>
              {selectedSession.first_date} → {selectedSession.last_date}
              ({selectedSession.snapshot_count} snapshots)
            </p>

            <button
              onClick={handleGenerateRecap}
              disabled={generating}
              className="generate-btn"
            >
              {generating ? 'Generating...' : 'Generate Chapter Recap'}
            </button>

            {recap && <RecapViewer recap={recap} />}
          </>
        ) : (
          <p className="placeholder">Select a session to view or generate a recap</p>
        )}
      </div>
    </div>
  );
}
```

---

### Phase 4: Build & Distribution (~1-2 days)

**Goal:** Bundled app that auto-updates from GitHub Releases.

**Packaging notes**
- Ensure the backend writes DB/cache to `STELLARIS_DB_PATH` (userData), not the install directory.
- If the backend needs bundled data files, include them in the PyInstaller spec `datas`.
- Consider leaving auto-updates disabled until signing/notarization is in place.

**PyInstaller spec (`stellaris-backend.spec`):**
```python
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['backend/electron_main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('stellaris_save_extractor', 'stellaris_save_extractor'),
        ('personality.py', '.'),
        ('save_extractor.py', '.'),
        ('save_loader.py', '.'),
    ],
    hiddenimports=[
        'uvicorn.logging',
        'uvicorn.loops.auto',
        'uvicorn.protocols.http.auto',
        'uvicorn.lifespan.on',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='stellaris-backend',
    debug=False,
    strip=False,
    upx=True,
    console=False,  # No console window
)
```

**GitHub Actions workflow (`.github/workflows/release.yml`):**
```yaml
name: Build and Release

on:
  push:
    tags:
      - 'v*'

jobs:
  build-python:
    strategy:
      matrix:
        os: [macos-latest, windows-latest, ubuntu-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pyinstaller

      - name: Build Python backend
        run: pyinstaller stellaris-backend.spec

      - name: Upload Python artifact
        uses: actions/upload-artifact@v4
        with:
          name: python-backend-${{ matrix.os }}
          path: dist/stellaris-backend*

  build-electron:
    needs: build-python
    strategy:
      matrix:
        os: [macos-latest, windows-latest, ubuntu-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4

      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Download Python backend
        uses: actions/download-artifact@v4
        with:
          name: python-backend-${{ matrix.os }}
          path: dist-python/

      - name: Install Electron deps
        working-directory: electron
        run: npm ci

      - name: Build React app
        working-directory: electron/renderer
        run: npm run build

      - name: Build Electron app
        working-directory: electron
        run: npm run build
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}

      - name: Upload to GitHub Release
        uses: softprops/action-gh-release@v1
        with:
          files: electron/dist/*
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

---

## Session End Detection (Future)

### Option A: Manual Button (MVP - Implemented above)
- "End Current Session" button in Recap page
- User clicks when done playing

### Option B: Process Detection (Future)
```javascript
// In main.js - poll for Stellaris process
const { exec } = require('child_process');

function checkStellarisRunning() {
  const cmd = process.platform === 'win32'
    ? 'tasklist /FI "IMAGENAME eq stellaris.exe"'
    : 'pgrep -x stellaris';

  exec(cmd, (err, stdout) => {
    const isRunning = stdout.includes('stellaris');
    if (wasRunning && !isRunning) {
      // Game just closed - trigger session end
      notifyGameClosed();
    }
    wasRunning = isRunning;
  });
}

setInterval(checkStellarisRunning, 5000); // Check every 5 seconds
```

### Option C: Inactivity Timeout (Future)
```python
# In Python backend
SESSION_TIMEOUT_MINUTES = 15

def check_session_timeout():
    last_snapshot = db.get_latest_snapshot_timestamp()
    if last_snapshot:
        minutes_since = (time.time() - last_snapshot) / 60
        if minutes_since > SESSION_TIMEOUT_MINUTES:
            auto_end_session()
```

---

## Timeline Estimate

| Phase | Effort | Dependencies |
|-------|--------|--------------|
| Phase 0: Decisions + plumbing | ~0.5 day | None |
| Phase 1: Python API | 1-2 days | Phase 0 |
| Phase 2: Electron scaffold | 2-3 days | Phase 1 |
| Phase 3: React UI | 2-3 days | Phase 2 |
| Phase 4: Build pipeline | 1-2 days | Phase 3 |
| **Total** | **6.5-10.5 days** | |

---

## Open Items

- [ ] App icon design
- [ ] First-run wizard flow
- [ ] Missing API key strategy (gate vs degraded mode)
- [ ] Backend auth token enforcement on `/api/*`
- [ ] Keychain storage via `keytar`
- [ ] Telemetry / crash reporting (opt-in)
- [ ] Windows code signing certificate
- [ ] macOS notarization

---

## Next Steps

1. Create `electron/` directory structure
2. Implement Phase 0 decisions (IPC + secrets + auth token + DB path)
3. Implement Phase 1 (FastAPI server + auth)
4. Test API endpoints with curl/Postman
5. Proceed to Electron scaffold
