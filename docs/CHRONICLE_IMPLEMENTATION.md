# Chronicle System Implementation

> Implementation plan for LLM-generated empire storytelling.

**Related Documents**:
- [STORYTELLING_OPTIONS.md](./STORYTELLING_OPTIONS.md) - Design decisions and architecture
- [CHRONICLE_TESTING.md](./CHRONICLE_TESTING.md) - Prompt testing and validation results

---

## Overview

The chronicle system transforms raw game events into dramatic, Stellaris Invicta-style narratives. It integrates with both the Electron app (primary) and Discord bot (secondary).

### What We're Building

| Feature | Description |
|---------|-------------|
| **Chronicle** | Full 4-6 chapter narrative of empire history |
| **Recap** | LLM-enhanced "Previously on..." summary of recent events |
| **Voice Differentiation** | Ethics-based narrative voice (egalitarian, authoritarian, machine) |
| **Caching** | Store generated chronicles to avoid regeneration |

---

## Electron App Integration (Primary)

The Electron app uses IPC (Inter-Process Communication) to communicate with the Python backend. The renderer does NOT call `fetch()` directly—all requests go through the main process.

### IPC Chain Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  RENDERER (React)                                                    │
│                                                                     │
│  const { chronicle } = useBackend()                                 │
│  const result = await backend.chronicle(sessionId, forceRefresh)    │
│                          │                                          │
│                          ▼                                          │
│  window.electronAPI.backend.chronicle(sessionId, forceRefresh)      │
└─────────────────────────────────────────────────────────────────────┘
                           │
                           ▼ ipcRenderer.invoke('backend:chronicle', ...)
┌─────────────────────────────────────────────────────────────────────┐
│  MAIN PROCESS (main.js)                                             │
│                                                                     │
│  ipcMain.handle('backend:chronicle', async (event, args) => {       │
│      validateSender(event)                                          │
│      return await callBackendApi('/api/chronicle', {...})           │
│  })                                                                 │
│                          │                                          │
│                          ▼ HTTP fetch to localhost:8742             │
└─────────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PYTHON BACKEND (FastAPI)                                           │
│                                                                     │
│  POST /api/chronicle                                                │
│  - Check cached_chronicles table                                    │
│  - Generate via Gemini if cache miss/stale                          │
│  - Return chronicle JSON                                            │
└─────────────────────────────────────────────────────────────────────┘
```

### Required Electron Changes

#### 1. Preload Script (`electron/preload.js`)

Add chronicle method to the backend namespace:

```javascript
// Add to the backend object (around line 51-65)
backend: {
  health: () => ipcRenderer.invoke('backend:health'),
  chat: (message, sessionKey) =>
    ipcRenderer.invoke('backend:chat', { message, session_key: sessionKey }),
  status: () => ipcRenderer.invoke('backend:status'),
  sessions: () => ipcRenderer.invoke('backend:sessions'),
  sessionEvents: (sessionId, limit) =>
    ipcRenderer.invoke('backend:session-events', { session_id: sessionId, limit }),
  recap: (sessionId, style) =>
    ipcRenderer.invoke('backend:recap', { session_id: sessionId, style: style || 'summary' }),
  // NEW: Chronicle endpoint
  chronicle: (sessionId, forceRefresh) =>
    ipcRenderer.invoke('backend:chronicle', { session_id: sessionId, force_refresh: forceRefresh || false }),
  endSession: () => ipcRenderer.invoke('backend:end-session'),
}
```

#### 2. Main Process (`electron/main.js`)

Add IPC handler for chronicle:

```javascript
// Add after other backend handlers (around line 850)
ipcMain.handle('backend:chronicle', async (event, { session_id, force_refresh }) => {
  try {
    validateSender(event)
    return await callBackendApi('/api/chronicle', {
      method: 'POST',
      body: JSON.stringify({ session_id, force_refresh }),
    })
  } catch (e) {
    return { error: e.message }
  }
})

// Update recap handler to support style parameter
ipcMain.handle('backend:recap', async (event, { session_id, style }) => {
  try {
    validateSender(event)
    return await callBackendApi('/api/recap', {
      method: 'POST',
      body: JSON.stringify({ session_id, style: style || 'summary' }),
    })
  } catch (e) {
    return { error: e.message }
  }
})
```

#### 3. useBackend Hook (`electron/renderer/hooks/useBackend.ts`)

Add TypeScript interface and method:

```typescript
// Add to ElectronAPI interface
interface ElectronAPI {
  backend: {
    // ... existing methods ...
    chronicle: (sessionId: string, forceRefresh?: boolean) => Promise<ChronicleResponse | ErrorResponse>
  }
}

interface ChronicleResponse {
  chronicle: string
  chapters?: ChapterInfo[]
  cached: boolean
  event_count: number
  generated_at: string
}

interface ChapterInfo {
  title: string
  date_range: string
  narrative: string
}

// Add to useBackend hook
const chronicle = useCallback(async (sessionId: string, forceRefresh = false) => {
  setLoading(prev => ({ ...prev, chronicle: true }))
  try {
    const result = await window.electronAPI?.backend.chronicle(sessionId, forceRefresh)
    if (isErrorResponse(result)) {
      setError(result.error)
      return null
    }
    return result
  } finally {
    setLoading(prev => ({ ...prev, chronicle: false }))
  }
}, [])
```

### RecapViewer Limitation

**Important**: The existing `RecapViewer` component uses a bespoke markdown-ish renderer that does NOT support standard markdown headers (`###`, `####`). It only detects:
- Lines with em-dashes (`—`) as main headers
- Lines ending with `:` as section headers
- Lines starting with `- ` as list items

**Options for Chronicle Rendering**:

1. **Option A: Constrain LLM output** - Modify the chronicler prompt to output in RecapViewer-compatible format:
   ```
   THE ARCHIVES OF LIBERTY—

   CHAPTER I: THE ARCHITECTURE OF ENLIGHTENMENT
   2475 – 2481:

   The dawn of 2475 found the United Nations...
   ```

2. **Option B: Use real markdown renderer** - Install `react-markdown` for chronicle display:
   ```typescript
   import ReactMarkdown from 'react-markdown'

   // In ChronicleViewer component
   <ReactMarkdown>{chronicle}</ReactMarkdown>
   ```

3. **Option C: Create ChronicleViewer component** - New component with proper markdown support for chronicles only.

**Recommendation**: Option B or C for chronicles, keep RecapViewer for quick summaries.

---

## API Endpoints

### `POST /api/chronicle`

Generate a full LLM-powered chronicle for a session.

**Request**:
```json
{
  "session_id": "abc-123",
  "force_refresh": false
}
```

**Response**:
```json
{
  "chronicle": "### THE ARCHIVES OF LIBERTY...",
  "chapters": [
    {
      "title": "THE ARCHITECTURE OF ENLIGHTENMENT",
      "date_range": "2475 – 2481",
      "narrative": "The dawn of 2475 found the United Nations..."
    }
  ],
  "generated_at": "2026-01-24T10:30:00Z",
  "cached": true,
  "event_count": 228
}
```

### `POST /api/recap` (Enhanced)

**Request**:
```json
{
  "session_id": "abc-123",
  "style": "dramatic"
}
```

**Response**:
```json
{
  "recap": "The stars themselves trembled...",
  "events_summarized": 15,
  "date_range": "2505.01.01 - 2509.07.01",
  "style": "dramatic"
}
```

---

## Discord Integration (Secondary)

### New Command Files

Discord commands are registered inside the bot cog. Create new command files:

| File | Command | Notes |
|------|---------|-------|
| `backend/bot/commands/chronicle.py` | `/chronicle` | NEW file |
| `backend/bot/commands/recap.py` | `/recap` | NEW file (doesn't exist currently) |

**Note**: `recap.py` does not currently exist. Existing commands are: `ask.py`, `briefing.py`, `end_session.py`, `history.py`, `status.py`.

### Command Output

```
═══════════════════════════════════════════════════════════
        THE ARCHIVES OF LIBERTY
        A Chronicle of the United Nations of Earth 2
═══════════════════════════════════════════════════════════

**CHAPTER I: THE ARCHITECTURE OF ENLIGHTENMENT**
*2475 – 2481*

The dawn of 2475 found the United Nations of Earth 2 at
the zenith of its civilizational reach...
```

---

## Backend Implementation

### New Files

| File | Purpose |
|------|---------|
| `backend/core/chronicle.py` | Chronicle generation engine |
| `backend/bot/commands/chronicle.py` | Discord `/chronicle` command |
| `backend/bot/commands/recap.py` | Discord `/recap` command |

### Modified Files

| File | Changes |
|------|---------|
| `backend/core/database.py` | Add `cached_chronicles` table, `get_all_events()` method |
| `backend/api/server.py` | Add `/api/chronicle` endpoint inside `create_app()`, enhance `/api/recap` |

### Database Schema

```sql
-- Add to schema version 3
CREATE TABLE cached_chronicles (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    session_id TEXT NOT NULL,
    chronicle_text TEXT NOT NULL,
    chapters_json TEXT,
    event_count INTEGER NOT NULL,
    snapshot_count INTEGER NOT NULL,  -- Also track snapshots for staleness
    generated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(session_id),  -- One chronicle per session (for now)
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE INDEX idx_cached_chronicles_session ON cached_chronicles(session_id);
```

**Note on cache key**: Current schema uses `session_id` as unique key. If we add styles/models/versions later, expand to `UNIQUE(session_id, style, prompt_version)`.

### Database Methods to Add

```python
# Add to backend/core/database.py

def get_all_events(self, *, session_id: str) -> list[dict[str, Any]]:
    """Get ALL events for a session (no limit cap).

    Used by chronicle generation which needs full history.
    Note: get_recent_events() has a hard 100-event cap.
    """
    with self._lock:
        rows = self._conn.execute(
            """
            SELECT id, captured_at, game_date, event_type, summary, data_json
            FROM events
            WHERE session_id = ?
            ORDER BY game_date ASC, captured_at ASC;
            """,
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

def get_cached_chronicle(self, session_id: str) -> dict[str, Any] | None:
    """Get cached chronicle if it exists."""
    with self._lock:
        row = self._conn.execute(
            "SELECT * FROM cached_chronicles WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return dict(row) if row else None

def get_event_count(self, session_id: str) -> int:
    """Get total event count for a session."""
    with self._lock:
        row = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM events WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return row["cnt"] if row else 0

def get_snapshot_count(self, session_id: str) -> int:
    """Get total snapshot count for a session."""
    with self._lock:
        row = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM snapshots WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return row["cnt"] if row else 0

def upsert_cached_chronicle(
    self,
    session_id: str,
    chronicle_text: str,
    event_count: int,
    snapshot_count: int,
    chapters_json: str | None = None,
) -> None:
    """Insert or update cached chronicle."""
    with self._lock:
        self._conn.execute(
            """
            INSERT INTO cached_chronicles
                (session_id, chronicle_text, chapters_json, event_count, snapshot_count)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                chronicle_text = excluded.chronicle_text,
                chapters_json = excluded.chapters_json,
                event_count = excluded.event_count,
                snapshot_count = excluded.snapshot_count,
                generated_at = datetime('now')
            """,
            (session_id, chronicle_text, chapters_json, event_count, snapshot_count),
        )
```

### Chronicle Generator

```python
# backend/core/chronicle.py

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from google import genai

from backend.core.database import GameDatabase


class ChronicleGenerator:
    """Generate LLM-powered chronicles for empire sessions."""

    # Staleness thresholds
    STALE_EVENT_THRESHOLD = 10
    STALE_SNAPSHOT_THRESHOLD = 5

    def __init__(self, db: GameDatabase, api_key: str | None = None):
        self.db = db
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY")
        self._client: genai.Client | None = None

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            if not self.api_key:
                raise ValueError("GOOGLE_API_KEY not configured")
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def generate_chronicle(
        self,
        session_id: str,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        """Generate a full chronicle for the session.

        Returns cached version if available and recent.
        """
        # Check cache (unless force refresh)
        if not force_refresh:
            cached = self._get_cached_if_valid(session_id)
            if cached:
                return cached

        # Gather data (uses get_all_events - no 100 cap)
        data = self._gather_session_data(session_id)

        # Build prompt with ethics-based voice
        prompt = self._build_chronicler_prompt(data)

        # Call Gemini (blocking - endpoint should be sync def)
        response = self.client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt,
            config={"temperature": 1.0, "max_output_tokens": 4096},
        )

        chronicle_text = response.text
        event_count = len(data["events"])
        snapshot_count = self.db.get_snapshot_count(session_id)

        # Cache result
        self.db.upsert_cached_chronicle(
            session_id=session_id,
            chronicle_text=chronicle_text,
            event_count=event_count,
            snapshot_count=snapshot_count,
        )

        return {
            "chronicle": chronicle_text,
            "cached": False,
            "event_count": event_count,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def generate_recap(
        self,
        session_id: str,
        *,
        style: str = "summary",
        max_events: int = 30,
    ) -> dict[str, Any]:
        """Generate a recap for the session.

        Args:
            style: "summary" (deterministic) or "dramatic" (LLM-powered)
        """
        if style == "summary":
            from backend.core.reporting import build_session_report_text
            recap = build_session_report_text(db=self.db, session_id=session_id)
            return {"recap": recap, "style": "summary"}

        # Dramatic LLM-powered recap (uses limited events - OK for recap)
        data = self._gather_session_data(session_id, max_events=max_events)
        prompt = self._build_recap_prompt(data)

        response = self.client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt,
            config={"temperature": 1.0, "max_output_tokens": 2048},
        )

        return {
            "recap": response.text,
            "style": "dramatic",
            "events_summarized": len(data["events"]),
        }

    def _get_cached_if_valid(self, session_id: str) -> dict[str, Any] | None:
        """Get cached chronicle if still valid (not stale)."""
        cached = self.db.get_cached_chronicle(session_id)
        if not cached:
            return None

        # Check staleness by both event count AND snapshot count
        current_events = self.db.get_event_count(session_id)
        current_snapshots = self.db.get_snapshot_count(session_id)

        event_delta = current_events - cached["event_count"]
        snapshot_delta = current_snapshots - cached["snapshot_count"]

        if event_delta >= self.STALE_EVENT_THRESHOLD:
            return None  # Too many new events
        if snapshot_delta >= self.STALE_SNAPSHOT_THRESHOLD:
            return None  # Too many new snapshots (catches quiet periods)

        return {
            "chronicle": cached["chronicle_text"],
            "cached": True,
            "event_count": cached["event_count"],
            "generated_at": cached["generated_at"],
        }

    def _gather_session_data(
        self, session_id: str, max_events: int | None = None
    ) -> dict[str, Any]:
        """Gather all data needed for chronicle/recap generation."""
        session = self.db.get_session_by_id(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        # Get events - use get_all_events for chronicles (no cap)
        if max_events is None:
            events = self.db.get_all_events(session_id=session_id)
        else:
            events = self.db.get_recent_events(session_id=session_id, limit=max_events)

        # Get briefing for identity/personality
        briefing_json = self.db.get_latest_session_briefing_json(session_id)
        briefing = json.loads(briefing_json) if briefing_json else {}

        # Get date range
        stats = self.db.get_session_snapshot_stats(session_id)

        return {
            "session": dict(session),
            "events": events,
            "briefing": briefing,
            "first_date": stats.get("first_game_date"),
            "last_date": stats.get("last_game_date"),
        }

    def _build_chronicler_prompt(self, data: dict[str, Any]) -> str:
        """Build the full chronicler prompt with ethics-based voice.

        See CHRONICLE_TESTING.md for validated prompt structure.
        """
        briefing = data["briefing"]
        identity = briefing.get("identity", {})

        empire_name = identity.get("empire_name", "Unknown Empire")
        ethics = ", ".join(identity.get("ethics", []))
        authority = identity.get("authority", "unknown")
        civics = ", ".join(identity.get("civics", []))

        # Ethics-based voice selection
        if identity.get("is_machine"):
            voice = (
                "Write with cold, logical precision. No emotion, only analysis of "
                "historical patterns. Use technical terminology. Frame the chronicle "
                "as a data log for future processing units."
            )
        elif identity.get("is_hive_mind"):
            voice = "Write as the collective memory. Use 'we' and 'the swarm'. Frame history as the growth of the whole."
        elif "fanatic_authoritarian" in ethics or "authoritarian" in ethics:
            voice = (
                "Write with imperial grandeur. Emphasize the glory of the state, "
                "the wisdom of the throne, and the order that hierarchy brings."
            )
        elif "fanatic_egalitarian" in ethics or "egalitarian" in ethics:
            voice = "Write celebrating the triumph of the people. Emphasize collective achievement and democratic ideals."
        elif "fanatic_militarist" in ethics or "militarist" in ethics:
            voice = "Write with martial pride. Emphasize battles, conquests, and military honor."
        elif "fanatic_spiritualist" in ethics or "spiritualist" in ethics:
            voice = "Write with religious reverence. Frame history as divine providence."
        else:
            voice = "Write with epic gravitas befitting a galactic chronicle."

        events_text = self._format_events(data["events"])
        state_text = self._summarize_state(briefing)

        return f"""You are the Royal Chronicler of {empire_name}. Your task is to write the official historical chronicle of this empire.

=== EMPIRE IDENTITY ===
Name: {empire_name}
Ethics: {ethics}
Authority: {authority}
Civics: {civics}

=== CHRONICLER'S VOICE ===
{voice}

You are NOT an advisor. You do NOT give recommendations or strategic advice. You are a HISTORIAN writing for future generations.

=== STYLE GUIDE ===
- Write as an epic galactic chronicle: dramatic, cinematic, larger-than-life
- Each chapter should read like the opening crawl of a space opera
- Use vivid, evocative language: "The stars themselves trembled" not "There was a big war"
- Employ narrative techniques: foreshadowing, dramatic irony, rising tension
- Name specific dates when dramatic (e.g., "On the first day of 2350, the sky burned")
- When leader names are missing or show as placeholders, use titles instead
- DO NOT fabricate events - only reference what appears in the event log
- DO NOT give advice or recommendations - you are a chronicler, not an advisor

{state_text}

=== COMPLETE EVENT HISTORY ===
(From {data['first_date']} to {data['last_date']})
{events_text}

=== YOUR TASK ===

Write a chronicle divided into 4-6 chapters. For each chapter:
1. **Chapter Title**: A dramatic, thematic name
2. **Date Range**: The years this chapter covers (use actual dates from events)
3. **Narrative**: 2-4 paragraphs of dramatic prose

End with "The Story Continues..." about the current situation.
"""

    def _build_recap_prompt(self, data: dict[str, Any]) -> str:
        """Build a shorter recap prompt for recent events."""
        briefing = data["briefing"]
        identity = briefing.get("identity", {})
        empire_name = identity.get("empire_name", "Unknown Empire")

        events_text = self._format_events(data["events"])
        state_text = self._summarize_state(briefing)

        return f"""You are the Royal Chronicler of {empire_name}. Write a dramatic "Previously on..." recap.

{state_text}

=== RECENT EVENTS ===
{events_text}

Write a 2-3 paragraph dramatic recap of recent events, ending with the current stakes.
Do NOT give advice. Write as a historian, not an advisor.
"""

    def _format_events(self, events: list[dict]) -> str:
        """Format events for the LLM prompt."""
        # Group by year for readability
        by_year: dict[str, list[dict]] = {}
        for e in events:
            year = e.get("game_date", "")[:4] or "Unknown"
            if year not in by_year:
                by_year[year] = []
            by_year[year].append(e)

        lines = []
        for year in sorted(by_year.keys()):
            year_events = by_year[year]
            lines.append(f"\n=== {year} ===")
            for e in year_events:
                lines.append(f"  * {e.get('summary', e.get('event_type', 'Unknown event'))}")

        return "\n".join(lines)

    def _summarize_state(self, briefing: dict) -> str:
        """Summarize current empire state for context."""
        identity = briefing.get("identity", {})
        situation = briefing.get("situation", {})
        military = briefing.get("military", {})
        territory = briefing.get("territory", {})
        endgame = briefing.get("endgame", {})

        lines = [
            "=== CURRENT STATE ===",
            f"Empire: {identity.get('empire_name', 'Unknown')}",
            f"Year: {situation.get('year', '?')}",
            f"Military Power: {military.get('military_power', 0):,.0f}",
            f"Colonies: {territory.get('colonies', {}).get('total_count', 0)}",
        ]

        crisis = endgame.get("crisis", {})
        if crisis.get("crisis_active"):
            lines.append(
                f"CRISIS: {crisis.get('crisis_type', 'Unknown').title()} "
                f"({crisis.get('crisis_systems_count', 0)} systems)"
            )

        fe = situation.get("fallen_empires", {})
        if fe.get("awakened_count", 0) > 0:
            lines.append(f"Awakened Empires: {fe.get('awakened_count', 0)}")

        return "\n".join(lines)
```

### API Endpoint

Routes must be registered **inside** `create_app()` function (not at module scope):

```python
# Add inside create_app() in backend/api/server.py

# Request models (add near top of file)
class ChronicleRequest(BaseModel):
    """Request body for /api/chronicle endpoint."""
    session_id: str
    force_refresh: bool = False

# Inside create_app(), after other route definitions:

@app.post("/api/chronicle", dependencies=[Depends(verify_token)])
def generate_chronicle_endpoint(request: Request, body: ChronicleRequest) -> dict[str, Any]:
    """Generate a full LLM-powered chronicle for a session.

    Note: This is a sync endpoint (def, not async def) because the
    Gemini client is synchronous. FastAPI runs sync endpoints in a
    threadpool, avoiding event loop blocking.
    """
    db = getattr(request.app.state, "db", None)
    if db is None:
        raise HTTPException(status_code=503, detail={"error": "Database not initialized"})

    session = db.get_session_by_id(body.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail={"error": "Session not found"})

    from backend.core.chronicle import ChronicleGenerator
    generator = ChronicleGenerator(db=db)

    try:
        result = generator.generate_chronicle(
            session_id=body.session_id,
            force_refresh=body.force_refresh,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": f"Chronicle generation failed: {str(e)}"},
        )

# Enhance existing /api/recap endpoint to support style parameter
# Update the RecapRequest model and handler
```

**Important**: The endpoint uses `def` (synchronous) not `async def`. This is intentional because the Gemini client is synchronous. FastAPI automatically runs sync endpoints in a threadpool, preventing event loop blocking.

---

## Ethics Voice Reference

From testing (see [CHRONICLE_TESTING.md](./CHRONICLE_TESTING.md)):

| Ethics | Voice Characteristics |
|--------|----------------------|
| **Egalitarian** | "beacon of hope", "collective labor", "every voice", "People's Assembly" |
| **Authoritarian** | "chains of cold iron", "Emperor's justice", "submissive worlds", "fist of mail" |
| **Machine** | "DATA-LOG", "processing units", "Great Optimization", "mathematically irrelevant" |
| **Militarist** | Martial pride, battle focus, conquest emphasis |
| **Spiritualist** | Religious reverence, providence framing |
| **Hive Mind** | Collective "we", swarm references |

---

## Implementation Phases

### Phase 1: Core Chronicle (This PR)

| Task | File | Status |
|------|------|--------|
| Add `cached_chronicles` table + migration | `database.py` | ⏳ |
| Add `get_all_events()` method (no 100 cap) | `database.py` | ⏳ |
| Add cache helper methods | `database.py` | ⏳ |
| Create `ChronicleGenerator` class | `chronicle.py` | ⏳ |
| Add `/api/chronicle` endpoint (inside `create_app()`) | `server.py` | ⏳ |
| Enhance `/api/recap` with `style` param | `server.py` | ⏳ |
| Add IPC handler for chronicle | `main.js` | ⏳ |
| Add preload bridge method | `preload.js` | ⏳ |
| Add `useBackend` chronicle method | `useBackend.ts` | ⏳ |
| Create `/chronicle` Discord command | `commands/chronicle.py` | ⏳ |
| Create `/recap` Discord command | `commands/recap.py` | ⏳ |

### Phase 2: Electron UI

| Task | File | Status |
|------|------|--------|
| Create `ChronicleViewer` component (with react-markdown) | `electron/renderer/components/` | ⏳ |
| Add chronicle toggle to RecapPage | `electron/renderer/pages/` | ⏳ |
| Add "View Chronicle" button to sessions | `electron/renderer/pages/` | ⏳ |

### Phase 3: Enrichment (Future)

| Task | Notes |
|------|-------|
| `leader_records` table | Track leader careers for richer narratives |
| `war_records` table | Track war context and outcomes |
| `rulers` table | Track succession for generational sagas |
| Response modes | Advisor / Chronicle / Immersive toggle |

---

## Key Technical Decisions

| Issue | Decision | Rationale |
|-------|----------|-----------|
| **Route registration** | Inside `create_app()` | Matches existing pattern in `server.py` |
| **Electron API calls** | IPC chain, not fetch | Matches existing `useBackend` pattern |
| **Event retrieval** | New `get_all_events()` method | Existing `get_recent_events()` has 100 cap |
| **Async/sync endpoint** | Sync `def` | Gemini client is sync; FastAPI threadpools it |
| **Cache invalidation** | Events + snapshots | Catches both event-heavy and quiet periods |
| **Markdown rendering** | New component with react-markdown | RecapViewer doesn't support `#` headers |
| **Datetime** | `datetime.now(timezone.utc)` | Portable across Python versions |

---

## Testing Checklist

- [ ] Chronicle generates for Session 1 (628 events, 145 years)
- [ ] Chronicle generates for Session 2 (228 events, War in Heaven + Prethoryn)
- [ ] `get_all_events()` returns all events (no 100 cap)
- [ ] Egalitarian voice is distinct from authoritarian
- [ ] Machine intelligence voice is clearly different
- [ ] Caching works (second call returns cached)
- [ ] Cache invalidates after 10+ new events OR 5+ new snapshots
- [ ] Force refresh regenerates chronicle
- [ ] IPC chain works: renderer → preload → main → backend
- [ ] Discord message splitting works for long chronicles
- [ ] ChronicleViewer renders markdown headers correctly

---

## Cost Estimate

| Operation | Input Tokens | Output Tokens | Cost |
|-----------|--------------|---------------|------|
| Chronicle (full) | ~3,000-5,000 | ~1,500-2,500 | ~$0.002 |
| Recap (dramatic) | ~1,000-2,000 | ~500-1,000 | ~$0.001 |

Cost is negligible. Caching ensures we don't regenerate unnecessarily.
