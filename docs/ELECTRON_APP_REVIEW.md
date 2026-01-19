# Electron App Review: Security, Performance, UX

This document reviews the Electron desktop app in this repo with a focus on:
- Security issues (Electron-specific threat model, IPC hardening, packaging)
- Performance issues (snappiness, CPU/RAM, memory leaks, long-session degradation)
- UX improvements (first-run, clarity, day-to-day usability)

Scope: the Electron app (`electron/`) + Electron-focused backend (`backend/api`, `backend/electron_main.py`) + save parsing pipeline (`stellaris_save_extractor/`).

---

## Implementation Progress

> **Last updated:** 2026-01-19

### ✅ Completed

| Item | Phase | Implementation |
|------|-------|----------------|
| **Navigation lockdown** | A.1 | `setWindowOpenHandler` + `will-navigate` in `main.js` - external links open in system browser |
| **IPC sender validation** | A.2 | `validateSender()` checks `event.senderFrame.url` on all sensitive IPC handlers |
| **Renderer sandboxing** | A.1 | `sandbox: true`, `webviewTag: false` in webPreferences |
| **Token logging removed** | A.1 | Replaced token substring log with `'Auth token configured'` |
| Health check timeouts | A.3 | `AbortController` with 4s timeout in `main.js` |
| No overlapping checks | A.3 | `healthCheckInFlight` flag prevents concurrent checks |
| Backend-status always emits | A.3 | Health checks run regardless of Python spawn state |
| Health check fail threshold | A.3 | Requires 2 consecutive failures before showing "Disconnected" |
| **Ingestion coordinator** | B.1 | `backend/core/ingestion.py` - latest-only scheduling with file stability wait |
| **Process-based cancellation** | B.2 | `backend/core/ingestion_worker.py` - workers run in separate process, killed on new save |
| **Tiered compute** | B.3 | T0 (meta ~5ms), T1 (status ~3s), T2 (full briefing ~20s) |
| Idle-only T2 scheduling | B.4 | 12s quiet period before T2; on-demand via `request_t2_on_demand()` |
| Lazy gamestate loading | C.1 | `stellaris_save_extractor/base.py` - property getter defers 70MB decode |
| Status labels in UI | E.2 | StatusBar shows "Analyzing (parsing_t1)…", "Ready", "No Save", etc. |
| Window dragging | — | CSS `-webkit-app-region: drag` on StatusBar |

### ❌ Not Started

| Item | Phase | Priority | Effort | Notes |
|------|-------|----------|--------|-------|
| mmap/streaming parser | C.1 | P1 | High | Replace full string load with mmap slices |
| DB compression/retention | C.3 | P1 | Medium | Limit snapshots per session, compress JSON |
| Save path edit/clear | E.1 | P2 | Low | Add "Clear" / "Auto-detect" buttons |
| Virtualize chat list | E.3 | P2 | Medium | Use `react-window` for long sessions |
| Tray onboarding hint | E.5 | P2 | Low | One-time toast on first minimize-to-tray |

### Recommended Next Steps (High ROI)

1. **DB retention policy** — ~2 hours, prevents unbounded growth over long campaigns
2. **Chat virtualization** — ~3 hours, keeps UI snappy in marathon sessions

---

## Quick TL;DR (Prioritized)

### P0 — Ship-stoppers / high-impact fixes

**Security hardening**
- ✅ Lock down navigation + new windows and route external links to the system browser.
- ✅ Validate IPC sender origin (`event.senderFrame.url`) for every `ipcMain.handle` (especially settings + backend proxy).
- ✅ Enable renderer sandboxing (`sandbox: true` / `app.enableSandbox()`), explicitly disable `webviewTag`.
- ✅ Stop logging secrets/token fragments in production logs.

**Snappiness**
- ✅ Fix `backend-status` updates: current logic is tied to whether Electron spawned Python, not whether the backend is reachable.
- ✅ Add request timeouts (AbortController) and prevent overlapping health checks.
- ✅ Stop doing "full precompute on every save update"; switch to tiered compute + latest-only scheduling.

### P1 — Big performance wins
- ✅ ~~Avoid loading/decoding the entire `gamestate` into a giant Python string for every parse~~ — Lazy loading implemented; full mmap optimization deferred.
- ✅ Cancel or coalesce background precompute work so frequent autosaves don't spawn multiple heavyweight parses.
- ❌ Reduce history DB growth (retain/compact/compress stored briefings).
- ✅ Prefer process-based cancellation for parsing (kill stale jobs) and add internal-only automatic backpressure (no user knobs).

### P2 — UX polish
- ❌ Make save-path editable/clearable (or add "Auto-detect" toggle).
- ✅ Surface "Analyzing save…" vs "Ready" using `precompute_ready`, with better first-run messaging and recovery paths.
- ❌ Bound/virtualize chat message list so long sessions stay fast.

---

## Architecture (What’s Running Where)

### Electron
- Main process: `electron/main.js`
  - Spawns Python backend (dev: `backend/electron_main.py`; prod: bundled `stellaris-backend`)
  - Maintains an in-memory per-launch auth token (`STELLARIS_API_TOKEN`) and proxies requests
  - Sends periodic `backend-status` events to renderer
  - Owns tray integration and window lifecycle
- Preload: `electron/preload.js`
  - Exposes `window.electronAPI` via `contextBridge`
  - Managed listener registry prevents listener accumulation for `backend-status`, etc.
- Renderer: `electron/renderer/*`
  - React UI for Chat / Recap / Settings

### Python backend
- Entry point: `backend/electron_main.py` (FastAPI + save watcher)
- HTTP API: `backend/api/server.py`
  - Auth is Bearer token via `STELLARIS_API_TOKEN`
- “Compute-heavy”: `backend/core/companion.py` + `stellaris_save_extractor/*`
  - Background precompute builds a “complete briefing” for fast /chat responses.

---

## Security Review

### What’s already good

- Renderer isolation is correctly configured:
  - `nodeIntegration: false` and `contextIsolation: true` in `electron/main.js` (`createWindow()` webPreferences).
  - Renderer interacts with main process only via `contextBridge` (`electron/preload.js`).
- Sensitive backend token is never exposed to renderer.
  - All backend calls are proxied via the main process, which injects the `Authorization: Bearer ...` header.
- Preload listener management is thoughtful.
  - `createManagedListener()` in `electron/preload.js` ensures a single `ipcRenderer.on` per channel and returns cleanup functions.

### High-risk gaps / footguns

#### 1) Navigation & new-window behavior is not locked down

Risk: any external link in the renderer (e.g., Google AI Studio link in Settings) can open a new Electron window. If a future change accidentally applies `preload.js` to that new window (or allows navigation in the main window), untrusted web content could reach your IPC surface (settings + backend proxy).

Evidence:
- Renderer includes external links such as `https://aistudio.google.com/app/apikey` in `electron/renderer/pages/SettingsPage.tsx`.
- Main process does not set:
  - `webContents.setWindowOpenHandler(...)`
  - `webContents.on('will-navigate', ...)`
  - `shell.openExternal(...)` routing

Recommendation (P0):
- In `createWindow()`:
  - `mainWindow.webContents.setWindowOpenHandler(({ url }) => { shell.openExternal(url); return { action: 'deny' } })`
  - `mainWindow.webContents.on('will-navigate', (e, url) => { if (!isAllowed(url)) e.preventDefault() })`
  - Define allowed origins: dev `http://localhost:5173`, prod `file://.../renderer/dist/index.html`.

#### 2) IPC handlers accept requests without validating the sender

Risk: IPC is the primary privilege boundary in Electron. If a renderer becomes compromised, it can invoke:
- `save-settings` (write secrets to keychain)
- backend proxy calls
- folder dialog

Evidence:
- `ipcMain.handle(...)` handlers in `electron/main.js` do not check `event.senderFrame.url` / `event.senderFrame.origin`.

Recommendation (P0):
- Add a shared guard:
  - Determine allowed origin(s) based on dev/prod
  - Reject IPC calls from any other origin (throw an error)
- Add payload validation (type/length) for `backend:chat` and `save-settings`.

#### 3) Renderer sandboxing is not enabled

Risk: sandboxing is a major defense-in-depth layer that limits the impact of renderer compromise.

Evidence:
- `sandbox: true` is not set in `webPreferences`.
- `app.enableSandbox()` is not used.

Recommendation (P0):
- Enable sandboxing in BrowserWindow and verify preload compatibility.

#### 4) Production packaging hardening is disabled

Risk: shipping without hardened runtime and signing reduces OS-level guarantees and makes safe auto-updates harder.

Evidence:
- `hardenedRuntime: false` and signing disabled in `electron/electron-builder.yml`.

Recommendation:
- For production releases:
  - Enable hardened runtime and notarization (macOS).
  - Sign Windows builds.
  - Only enable auto-updates once signing is in place.

#### 5) Token fragments are logged

Risk: even partial secrets can end up in support logs, crash reports, etc.

Evidence:
- `console.log('Using auth token:', authToken.substring(0, 12) + '...')` in `electron/main.js`.

Recommendation:
- Avoid logging tokens in production; use structured “backend-auth-configured” logs without values.

---

## Performance & Memory Review (Primary Bottlenecks)

## How comprehensive is the current “compute”?

Right now, the “compute” path triggered by save load/reload is closer to a full ingestion pipeline than a minimal “answer a question” path.

- Baseline: the Python extractor reads the `.sav` zip and loads `meta` and the full `gamestate` into memory as decoded strings (high RAM + CPU cost late-game).
- Precompute: the backend precompute calls `get_complete_briefing()` and assembles a large JSON blob covering many domains (military, economy, territory, diplomacy, leaders, tech, species, endgame, etc.).
- Persistence/enrichment: after building the big briefing, additional gamestate-derived enrichments and event detection run, and `full_briefing_json` is stored in SQLite, which can grow quickly over long campaigns.

This is comprehensive and convenient for LLM answering, but it makes “autosave frequency” a critical performance variable.

### The biggest bottleneck: save parsing loads full gamestate into memory

The extractor loads and decodes the full `gamestate` into a Python string on every initialization:
- `stellaris_save_extractor/base.py` reads `gamestate` from the zip and `.decode('utf-8', errors='replace')`.

Why this matters:
- Late-game saves are large (~70MB). Decompression + decode allocates a huge string.
- Many extraction functions use regex scans and substring windows that create additional large temporary strings.
- Re-running this often (autosaves, UI interactions) will make the app feel “heavy” regardless of Electron UI optimizations.

Recommendation (P1):
- Reduce peak allocations and repeated scanning:
  - Extract `gamestate` to a temp file and use memory-mapped reads (`mmap`) to avoid repeated large copies.
  - Build an index of section offsets once, then parse only required slices.
  - Consider a streaming parser for Clausewitz text to avoid full materialization.

### Background precompute can cause CPU/RAM thrash

Current behavior:
- On load/reload, `Companion.start_background_precompute()` spawns a new daemon thread that calls `extractor.get_complete_briefing()`.
- “Latest wins” is enforced by generation checking, but earlier threads are not cancelled.

Problem:
- If saves update frequently, multiple heavy parses can run concurrently, increasing CPU usage and memory pressure.
- Even discarded results still cost time and can slow the system/UI.

Recommendation (P1):
- Coalesce work: run precompute in a single worker that always processes the latest requested save path.
- Add cancellation checks in long-running parse operations.
- Add backpressure: debounce save reload triggers before starting precompute.

### History DB bloat and expensive writes

Current behavior:
- Precompute stores `full_briefing_json` (potentially large) in SQLite per snapshot.
- Additional “history” enrichments are derived from raw gamestate and also stored.

Problem:
- DB can grow quickly and impact performance over time (WAL files, read latency).
- Writes can be expensive while the user is trying to interact.

Recommendation (P1):
- Store only deltas/metrics by default; make full briefing storage optional.
- Compress stored JSON (zstd/gzip) or implement retention (e.g., last N snapshots per session).
- Move expensive “event detection” extractions off the critical path if possible.

### Electron main-process health checks: no timeouts and misleading gating

Issues:
- `fetch` calls have no timeout; a stuck request can hang status updates.
- Health checks currently short-circuit if `pythonProcess` is not set, even if the backend is reachable (dev mode with external backend), and even if the backend should be considered “not configured” (no API key).

Recommendation (P0):
- Add `AbortController` timeouts (e.g., 2s per health call).
- Prevent overlapping health checks (skip if a check is already in flight).
- Drive connection status from “backend reachable” rather than “did we spawn python”.

### Renderer long-session degradation: unbounded chat state

Issue:
- Chat messages are kept in memory forever (`messages` array grows without limit).

Symptoms:
- RAM grows over time.
- Rendering and scrolling become slower in long sessions.

Recommendation (P2):
- Cap message history or virtualize the message list.
- Add “Clear chat” and/or “Export chat”.

---

## Stellaris autosaves (what to assume)

Stellaris autosave cadence is user-configurable and depends on game speed (in-game time vs wall time). In practice:
- Autosaves can arrive in bursts (fast speed, monthly autosaves, Ironman-like behavior, cloud-save patterns).
- You must assume “saves can arrive faster than we can fully parse”, especially late-game.

Design implication: the system needs backpressure by default (latest-only + cancellation), not “parse everything that arrives”.

---

## UX Review (Where Users Feel Pain)

### 1) StatusBar can get stuck on “Connecting…”

Root cause:
- Renderer initializes to “connecting”.
- Main only emits status updates via a periodic health check that currently requires `pythonProcess` to be set.
- If no API key is configured (backend not started), or if backend is already running externally, the renderer may never receive updates.

Impact:
- First impression: “is it broken?” even if the next action is simply “set API key”.

Recommendation (P0/P2):
- Emit an immediate status on startup (“Not configured: set API key”) when backend cannot start.
- In dev/external-backend scenarios, run health checks regardless of whether Electron spawned Python.
- Use backend’s `precompute_ready` to show “Analyzing…” vs “Ready”.

### 2) Save path field is read-only but implies it can be edited

Evidence:
- The input is `readOnly` but has an `onChange` and says “Leave empty to auto-detect”.

Impact:
- Users can’t paste or clear the path.
- “Auto-detect” becomes hard to return to once a path is chosen.

Recommendation (P2):
- Either:
  - Make it editable, or
  - Keep it read-only but add explicit controls: “Browse…”, “Clear”, “Use auto-detect”.

### 3) Precompute progress isn’t surfaced

Backend provides `precompute_ready` but UI doesn’t reflect “save loaded but analysis still running”.

Recommendation (P2):
- Add a clear state:
  - Connected + save_loaded + not precompute_ready → “Analyzing save…”
  - Connected + precompute_ready → “Ready”

### 4) Error messages can be unclear

Potential issue:
- Backend errors can come back as objects; error formatting may degrade into `[object Object]`.

Recommendation (P2):
- Normalize error handling in main process: extract `detail.error` consistently and stringify safely.

### 5) Tray behavior needs an onboarding hint

Current behavior:
- Closing the window hides it to tray (good), but without explanation.

Recommendation (P2):
- On first close, show a one-time toast/banner: “Stellaris Companion is still running in the tray.”
- Add a setting: “Close button quits app” (especially for Windows/Linux expectations).

---

## Recommended Implementation Plan

### Phase A (P0): Security + correctness + perceived snappiness — ✅ COMPLETE

1) ✅ Navigation lockdown in `electron/main.js` — COMPLETE
- `setWindowOpenHandler()` denies new windows, opens external URLs via `shell.openExternal()`
- `will-navigate` blocks navigation away from allowed origins (localhost:5173, file://)

2) ✅ IPC sender validation in `electron/main.js` — COMPLETE
- `validateSender()` helper validates `event.senderFrame.url`
- Applied to: `load-settings`, `save-settings`, `backend:chat`, `backend:health`, `select-folder`

3) ✅ Renderer sandboxing — COMPLETE
- `sandbox: true` and `webviewTag: false` in webPreferences

4) ✅ Token logging removed — COMPLETE
- Replaced `authToken.substring(0, 12)` with `'Auth token configured'`

5) ✅ Health check robustness in `electron/main.js` — COMPLETE
- Added `AbortController` timeout (4s)
- Added `healthCheckInFlight` flag to prevent overlapping checks
- Added `healthCheckFailCount` with threshold (2) to prevent status flickering
- Health checks run regardless of Python spawn state
- Immediate status emission on startup

### Phase B (P0/P1): "No-drama" performance architecture (no user knobs) — ✅ COMPLETE

Goal: keep the app fast without exposing lots of tuning options to users.

1) ✅ Add an ingestion coordinator (latest-only scheduling)
- Implemented in `backend/core/ingestion.py`
- Maintains single "latest save to process" slot
- Debounces until file is stable (0.6s unchanged) before starting

2) ✅ Add real cancellation by running parsing/extraction in a separate process
- Implemented in `backend/core/ingestion_worker.py`
- Workers run in separate process via `multiprocessing`
- Killed immediately via `terminate()`/`kill()` when newer save arrives

3) ✅ Split compute into tiers (cheap first, expensive later)
- Tier 0 (fast, ~5ms): metadata only from zip, no gamestate decode
- Tier 1 (medium, ~3s): status snapshot (military power, economy, wars)
- Tier 2 (heavy, ~20s): full complete briefing + history enrichment

Scheduling rule: Tier 2 runs only when save stream is idle (12s) or on-demand via `request_t2_on_demand()`.

4) ✅ Automatic backpressure (internal-only)
- Latest-only scheduling drops intermediate saves automatically
- Process-based cancellation ensures stale work doesn't burn resources
- Idle delay (12s) prevents T2 thrash during active gameplay

### Phase C (P1): Core performance work in Python extractor — PARTIAL

1) ✅ Reduce full-gamestate materialization — PARTIAL
- Implemented lazy loading: gamestate not decoded until first access
- ❌ Full mmap optimization deferred (would require parser rewrite)

2) ✅ Precompute coalescing / cancellation — COMPLETE
- Single worker via IngestionManager
- Debounce via file stability wait (0.6s)
- Process-based cancellation

3) ❌ DB size control — NOT STARTED
- Compress/retain stored briefings
- Consider storing only key metrics + derived events by default

### Phase D (P1+): Rust where it pays (optional, “no drama”)

If Phase B/C are still not enough, move only the parsing hot path to Rust:
- Prefer a standalone Rust worker binary (easy kill-to-cancel; avoids Python extension packaging friction).
- Start by implementing Tier 0/Tier 1 outputs in Rust (small JSON outputs), keep the rest in Python.
- Gradually port heavier extractors only if measured bottlenecks remain.

### Phase E (P2): UX polish — PARTIAL

- ❌ Save path controls (edit/clear/auto-detect)
- ✅ Better status labels and precompute progress — StatusBar shows "Analyzing (parsing_t1)…", "Ready", etc.
- ❌ Bound/virtualize chat history
- ✅ Window dragging — CSS `-webkit-app-region: drag` on StatusBar

---

## Suggested Metrics & How to Measure

If you want the app “snappier”, measure the real bottlenecks:
- **Time-to-interactive**: Electron launch → first usable UI render.
- **Backend readiness**: Electron launch → `/api/health` OK.
- **Precompute time**: save detected → `precompute_ready`.
- **Peak RSS memory** during precompute and during long chat sessions.
- **CPU usage** during autosave bursts.

Practical approach:
- Add structured timing logs around:
  - Save load / decode
  - Each major extraction stage in `get_complete_briefing`
  - DB write time
- Add a lightweight “Performance” panel in the UI showing:
  - backend connected
  - save loaded
  - precompute ready
  - last precompute duration

---

## Appendix: Key Code Locations

- Electron main process: `electron/main.js`
- Preload bridge: `electron/preload.js`
- Renderer pages:
  - `electron/renderer/pages/ChatPage.tsx`
  - `electron/renderer/pages/RecapPage.tsx`
  - `electron/renderer/pages/SettingsPage.tsx`
  - `electron/renderer/components/StatusBar.tsx`
- FastAPI server: `backend/api/server.py`
- Electron backend entry point: `backend/electron_main.py`
- Companion precompute: `backend/core/companion.py`
- Save parsing base: `stellaris_save_extractor/base.py`
- Complete briefing: `stellaris_save_extractor/briefing.py`
