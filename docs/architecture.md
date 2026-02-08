# Architecture (Overview)

Stellaris Companion is a **3-process** desktop app:

1. **Python backend (FastAPI)**: reads saves, maintains session/history state, runs LLM calls.
2. **Electron main (Node)**: owns OS integrations, spawns/monitors the backend process, and proxies backend HTTP with an auth token.
3. **Renderer (React)**: UI only; never receives the backend auth token.

## Core data flow

Typical request flow (e.g. chat):

1. Renderer calls `window.electronAPI.backend.chat(...)`
2. Preload (`electron/preload.js`) forwards via `ipcRenderer.invoke('backend:chat', ...)`
3. Main IPC handler (`electron/main/ipc/backend.js`) calls the backend over HTTP using `electron/main/backendClient.js`
4. Backend route (e.g. `backend/api/server.py`) returns JSON (or an `HTTPException(detail={...})`)
5. Main returns a **standard IPC envelope** to the renderer
6. Renderer maps that envelope into UI-friendly state in `electron/renderer/hooks/useBackend.ts`

## Security boundaries

- The backend uses a **Bearer token** (`STELLARIS_API_TOKEN`) for all HTTP requests.
- Electron main generates/holds the token and attaches it to backend requests.
- The renderer never sees the token (context isolation + preload bridge only).

## Packaged vs development

- **Packaged app**: Electron main runs the bundled PyInstaller executable (`python-backend/stellaris-backend`).
- **Development**: Electron main starts the backend via `python3 -m backend.electron_main` and sets `PYTHONPATH` to repo root because Electron dev usually runs with `cwd = electron/`.

## Where things live

- Electron main entry/wiring: `electron/main.js`
- Backend HTTP + IPC envelope shaping: `electron/main/backendClient.js`
- Backend IPC handlers (`backend:*`): `electron/main/ipc/backend.js`
- Other IPC domains: `electron/main/ipc/*` (settings, discord, announcements, updates)
- Preload API surface: `electron/preload.js`
- Renderer API/state wrapper: `electron/renderer/hooks/useBackend.ts`
- Renderer global typings: `electron/renderer/global.d.ts`
- Backend routes: `backend/api/server.py`
- Shared Python runtime utilities: `stellaris_companion/`

## Discord integration (high level)

- OAuth/PKCE + token storage: `electron/main/discord/oauth.js`
- Relay (WebSocket) connection/reconnect: `electron/main/discord/relay.js`
- IPC surface (`discord:*`) and events (`discord-relay-status`, `discord-auth-required`): `electron/main/ipc/discord.js` + `electron/preload.js`

