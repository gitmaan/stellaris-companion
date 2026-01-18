# Electron App - Overview

## Purpose

Build a desktop app that provides a native interface for the Stellaris Companion, eliminating the need for Discord while maintaining full functionality.

## Goals

1. **Native Chat Interface** - Alternative to Discord for asking questions
2. **Settings Management** - Configure API keys, save paths, Discord toggle
3. **Session Recaps** - View and generate chapter summaries
4. **Background Operation** - Runs Python backend as subprocess, sits in system tray

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ELECTRON APP                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  MAIN PROCESS (main.js)                                                     │
│  ├── Tray Icon (status, menu, show/hide)                                    │
│  ├── Settings Store (electron-store for non-secrets)                        │
│  ├── Keychain (keytar for API keys, tokens)                                 │
│  ├── Subprocess Manager (spawn/kill Python backend)                         │
│  ├── IPC Handlers (proxy API calls to Python)                               │
│  └── Auto-Updater (electron-updater)                                        │
│                                                                              │
│  RENDERER PROCESS (React + TypeScript)                                      │
│  ├── ChatPage - Messages, input, loading states                             │
│  ├── SettingsPage - API key, save path, Discord toggle                      │
│  ├── RecapPage - Session list, generate/view recaps                         │
│  └── StatusBar - Empire name, game date, backend status                     │
│                                                                              │
│                              IPC Bridge (preload.js)                         │
│                                  │                                           │
└──────────────────────────────────┼───────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      PYTHON BACKEND (Subprocess)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Entry: backend/electron_main.py                                            │
│  Server: FastAPI + Uvicorn on 127.0.0.1:8742                                │
│  Auth: Bearer token (generated per-launch by Electron)                      │
│                                                                              │
│  Endpoints:                                                                  │
│  ├── GET  /api/health         → Backend status + game date                  │
│  ├── POST /api/chat           → companion.ask_precomputed()                 │
│  ├── GET  /api/status         → companion.get_status_data()                 │
│  ├── GET  /api/sessions       → db.get_sessions()                           │
│  ├── GET  /api/sessions/{id}  → db.get_session_events()                     │
│  ├── POST /api/recap          → generate_recap(session_id)                  │
│  └── POST /api/end-session    → db.end_session()                            │
│                                                                              │
│  Existing Components (reused as-is):                                        │
│  ├── Companion (companion.py) - Gemini chat, precompute                     │
│  ├── SaveWatcher (save_watcher.py) - File monitoring                        │
│  ├── GameDatabase (database.py) - SQLite history                            │
│  └── ConversationManager (conversation.py) - Chat history                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Key Decisions (Pre-Made)

1. **Renderer → Main → Python** - Renderer never calls Python directly; all API calls go through IPC to main process, which adds auth header
2. **Secrets in OS Keychain** - Use `keytar` for GOOGLE_API_KEY and DISCORD_BOT_TOKEN; `electron-store` only for non-secrets
3. **Per-Launch Auth Token** - Electron generates random token, passes to Python via env; all /api/* routes require Bearer token
4. **First-Run: Gate Backend** - Don't spawn Python until API key is configured
5. **Writable Paths** - DB goes to `app.getPath('userData')`, not install directory
6. **Fixed Port MVP** - Use port 8742 with in-use detection; dynamic port is future enhancement

## Non-Goals (MVP)

- Process detection for auto-session-end (manual button only)
- Inactivity timeout for sessions
- Code signing / notarization (required for auto-updates, deferred)
- Windows/Linux builds (macOS first)

## Dependencies

**Electron (package.json):**
- electron ^28.0.0
- electron-store ^8.1.0
- keytar ^7.9.0
- electron-builder ^24.9.0
- electron-updater ^6.1.0
- react ^18.2.0, react-dom ^18.2.0
- vite ^5.0.0, @vitejs/plugin-react ^4.2.0
- typescript ^5.3.0

**Python (requirements.txt additions):**
- fastapi
- uvicorn[standard]
