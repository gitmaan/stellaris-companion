# IPC Contract (Backend ↔ Main ↔ Renderer)

This repo treats the IPC boundary between renderer and Electron main as a **stable API**.

For calls that proxy the Python backend (all `backend:*` IPC handlers), we use a single
response envelope so the renderer gets consistent data + structured errors.

## Canonical response envelope

Every `window.electronAPI.backend.*` method returns:

```ts
export type BackendIpcResponse<T> =
  | { ok: true; data: T }
  | {
      ok: false
      error: string
      code?: string
      retry_after_ms?: number
      http_status?: number
      details?: unknown
    }
```

- `error`: human-readable message (safe to show in UI).
- `code`: stable, machine-readable identifier for branching in UI.
- `retry_after_ms`: hint for backoff/retry UX (e.g. briefings not ready yet).
- `http_status`: backend HTTP status when relevant.
- `details`: diagnostic payload (useful for logs/debug, not necessarily UI).

Type source of truth:
- TS type: `electron/renderer/hooks/useBackend.ts`
- Global window API typing: `electron/renderer/global.d.ts`

## Backend error mapping

The backend should raise errors via `HTTPException(status_code=..., detail={...})`.

Main process mapping rules (implemented in `electron/main/backendClient.js`):

- On non-2xx responses, main attempts to parse JSON and extracts:
  - `detail.error` (preferred) or string `detail`
  - plus optional `detail.code` and `detail.retry_after_ms`
- Main returns `{ ok: false, error, code?, retry_after_ms?, http_status?, details? }`

Example (backend):

```py
raise HTTPException(
  status_code=409,
  detail={"error": "Chronicle generation already in progress", "code": "CHRONICLE_IN_PROGRESS", "retry_after_ms": 2000},
)
```

## Stable error codes

Prefer adding a `code` field whenever the UI needs predictable branching.

Examples currently used:
- `BRIEFING_NOT_READY`
- `CHRONICLE_IN_PROGRESS`

Add new codes in the backend where the condition is detected (not in the renderer).

## How to add a new backend IPC method

1. Backend: add/extend a route in `backend/api/server.py`.
2. Main: add an IPC handler in `electron/main/ipc/backend.js` that calls `callBackendApiEnvelope(...)`.
3. Preload: expose the method in `electron/preload.js` under `window.electronAPI.backend`.
4. Types: update `electron/renderer/global.d.ts` and the relevant response/request types in `electron/renderer/hooks/useBackend.ts`.
5. Renderer: consume through `useBackend` (avoid direct `ipcRenderer` usage).

## Non-backend IPC calls

Only backend-proxy calls (`window.electronAPI.backend.*`) use the envelope.

Other IPC surfaces (settings, updates, discord, announcements, onboarding) may return
domain-specific shapes and/or send push events (`backend-status`, `update-*`,
`discord-*`, `announcements-updated`).

