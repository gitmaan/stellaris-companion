# Stellaris LLM Companion - Comprehensive Plan

> **Status:** Phase 1 Complete (CLI), Phase 2 In Progress (Distribution)
> **Last Updated:** 2026-01-13
> **Related Docs:** [FINDINGS.md](./FINDINGS.md) | [Design Doc](../stellaris-llm-companion-design.md)

---

## Executive Summary

Building an AI-powered Stellaris companion that:
1. **Reads save files** and provides strategic analysis via Gemini 3 Flash
2. **Chats via Discord** (overlay-accessible while gaming)
3. **Shows dashboards** in a desktop app (for post-game review)
4. **Tracks history** with SQLite for timeline graphs

### Current State

| Component | Status | Notes |
|-----------|--------|-------|
| Save Parser | ✅ Complete | 12 tools, handles 70MB saves |
| CLI Interface | ✅ Complete | `v2_native_tools.py` with dynamic personality |
| Discord Bot | 🔄 Next | Primary in-game interface |
| Desktop App | 📋 Planned | Electron with web dashboard |
| Historical Data | 📋 Planned | SQLite for timeline tracking |

---

## Architecture Decision: Why This Stack

### The User Journey

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           USER EXPERIENCE FLOW                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. DOWNLOAD & SETUP (One-time)                                             │
│     ┌─────────────────────────────────────────────────────────────┐        │
│     │  • Download Stellaris Companion installer                    │        │
│     │  • Enter Gemini API key (BYOK - Bring Your Own Key)         │        │
│     │  • Enter Discord bot token (or use shared bot)              │        │
│     │  • App auto-detects Stellaris save location                 │        │
│     └─────────────────────────────────────────────────────────────┘        │
│                                                                             │
│  2. PLAYING STELLARIS (In-Game)                                             │
│     ┌─────────────────────────────────────────────────────────────┐        │
│     │  • Background service watches for save file changes         │        │
│     │  • Chat with advisor via Discord overlay (Ctrl+')           │        │
│     │  • Or use Discord on phone/second screen                    │        │
│     │  • Commands: /ask, /status, /briefing, /war                 │        │
│     └─────────────────────────────────────────────────────────────┘        │
│                                                                             │
│  3. AFTER GAMING SESSION (Post-Game)                                        │
│     ┌─────────────────────────────────────────────────────────────┐        │
│     │  • Desktop app auto-shows when Stellaris closes             │        │
│     │  • View timeline graphs (economy, military, tech over time) │        │
│     │  • Session summary: "What happened this session"            │        │
│     │  • Continue chatting in the app if desired                  │        │
│     └─────────────────────────────────────────────────────────────┘        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Why Discord for Chat?

| Consideration | Discord Bot | Steam Overlay Browser | Electron Overlay |
|---------------|-------------|----------------------|------------------|
| In-game access | ✅ Overlay works | ⚠️ Clunky (Shift+Tab) | ❌ Complex/fragile |
| Mobile/phone | ✅ Same bot | ❌ Desktop only | ❌ Desktop only |
| Second screen | ✅ Just works | ❌ Not applicable | ⚠️ Separate window |
| Setup complexity | Low | None | High |
| User familiarity | High (gamers use Discord) | Medium | Low |

**Decision:** Discord bot for primary chat interface.

### Why Electron for Desktop App?

| Framework | Overlay Compat | Package Size | Dev Speed | Ecosystem |
|-----------|----------------|--------------|-----------|-----------|
| **Electron** | ✅ Works | 150MB+ | Fast | Excellent |
| Tauri 2.0 | ❌ Broken* | 10MB | Medium | Growing |
| Python+PyInstaller | N/A | 50MB | Fast | Limited |

*Tauri uses WebView2 which cannot hook into DirectX for Steam overlay - confirmed unfixable (GitHub #6196).

**Decision:** Electron for desktop app (system tray, dashboard, settings UI).

### Why SQLite for History?

Learned from [Stellaris Dashboard](https://github.com/benreid24/stellaris-dashboard):
- They track empire data over time for graphs
- SQLite is fast, embedded, no setup required
- Can show "economy over 200 years" style charts

**Decision:** SQLite for historical snapshots (simple schema, not their full complexity).

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    STELLARIS COMPANION ARCHITECTURE                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                     ELECTRON APP (Desktop)                             │  │
│  │                                                                        │  │
│  │   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐             │  │
│  │   │  System Tray │   │   Settings   │   │  Dashboard   │             │  │
│  │   │              │   │     UI       │   │   (React)    │             │  │
│  │   │ • Status     │   │              │   │              │             │  │
│  │   │ • Quick menu │   │ • API keys   │   │ • Timeline   │             │  │
│  │   │ • Open app   │   │ • Save path  │   │ • Stats      │             │  │
│  │   │ • Quit       │   │ • Discord    │   │ • Chat       │             │  │
│  │   └──────────────┘   └──────────────┘   └──────────────┘             │  │
│  │                                                                        │  │
│  │   Spawns on app start ──────────────────────────────────────────┐     │  │
│  │                                                                  │     │  │
│  └──────────────────────────────────────────────────────────────────┼─────┘  │
│                                                                     │        │
│  ┌──────────────────────────────────────────────────────────────────┼─────┐  │
│  │                     PYTHON BACKEND (Subprocess)                  ▼     │  │
│  │                                                                        │  │
│  │   ┌──────────────────────────────────────────────────────────────────┐│  │
│  │   │                    CORE SERVICES                                 ││  │
│  │   │                                                                  ││  │
│  │   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             ││  │
│  │   │  │Save Watcher │  │  Discord    │  │   FastAPI   │             ││  │
│  │   │  │  (watchdog) │  │    Bot      │  │   Server    │             ││  │
│  │   │  │             │  │             │  │             │             ││  │
│  │   │  │ • Detect    │  │ • /ask      │  │ • REST API  │             ││  │
│  │   │  │   changes   │  │ • /status   │  │ • WebSocket │             ││  │
│  │   │  │ • Trigger   │  │ • /briefing │  │ • Dashboard │             ││  │
│  │   │  │   parse     │  │ • /war      │  │   data      │             ││  │
│  │   │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘             ││  │
│  │   │         │                │                │                     ││  │
│  │   │         └────────────────┴────────────────┘                     ││  │
│  │   │                          │                                      ││  │
│  │   │                          ▼                                      ││  │
│  │   │  ┌──────────────────────────────────────────────────────────┐  ││  │
│  │   │  │                 COMPANION CORE                            │  ││  │
│  │   │  │                                                           │  ││  │
│  │   │  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │  ││  │
│  │   │  │  │   Save      │  │   Gemini    │  │  Database   │      │  ││  │
│  │   │  │  │  Extractor  │  │   Client    │  │  (SQLite)   │      │  ││  │
│  │   │  │  │             │  │             │  │             │      │  ││  │
│  │   │  │  │ • 12 tools  │  │ • Chat API  │  │ • Sessions  │      │  ││  │
│  │   │  │  │ • Identity  │  │ • Function  │  │ • Snapshots │      │  ││  │
│  │   │  │  │ • Situation │  │   calling   │  │ • Events    │      │  ││  │
│  │   │  │  └─────────────┘  └─────────────┘  └─────────────┘      │  ││  │
│  │   │  │                                                           │  ││  │
│  │   │  └──────────────────────────────────────────────────────────┘  ││  │
│  │   │                                                                  ││  │
│  │   └──────────────────────────────────────────────────────────────────┘│  │
│  │                                                                        │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                         DATA FLOW                                       │  │
│  │                                                                         │  │
│  │   Stellaris ──autosave──▶ Save Watcher ──parse──▶ Extractor            │  │
│  │                                                       │                 │  │
│  │                                         ┌─────────────┴─────────────┐  │  │
│  │                                         ▼                           ▼  │  │
│  │                                    SQLite DB                   Gemini  │  │
│  │                                   (snapshot)                  (chat)   │  │
│  │                                         │                           │  │  │
│  │                                         └─────────────┬─────────────┘  │  │
│  │                                                       ▼                 │  │
│  │                               Discord Bot ◀────── Response             │  │
│  │                               Dashboard   ◀────── Data                 │  │
│  │                                                                         │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
stellaris-companion/
├── electron/                    # Electron app (Phase 3)
│   ├── main.js                  # Main process
│   ├── preload.js               # Preload scripts
│   ├── package.json             # Electron deps
│   └── renderer/                # React dashboard
│       ├── App.tsx
│       ├── components/
│       │   ├── Dashboard.tsx
│       │   ├── Timeline.tsx
│       │   ├── Chat.tsx
│       │   └── Settings.tsx
│       └── hooks/
│
├── backend/                     # Python backend
│   ├── main.py                  # Entry point (FastAPI + Discord)
│   ├── core/
│   │   ├── save_extractor.py    # ✅ EXISTS - 12 tools
│   │   ├── save_loader.py       # ✅ EXISTS - find saves
│   │   ├── save_watcher.py      # NEW - watchdog integration
│   │   ├── database.py          # NEW - SQLite history
│   │   ├── personality.py       # ✅ EXISTS - dynamic prompts
│   │   └── companion.py         # Refactored from v2_native_tools.py
│   │
│   ├── bot/
│   │   ├── discord_bot.py       # NEW - Discord.py bot
│   │   └── commands/
│   │       ├── ask.py           # /ask command
│   │       ├── status.py        # /status command
│   │       ├── briefing.py      # /briefing command
│   │       └── war.py           # /war command
│   │
│   ├── api/
│   │   ├── server.py            # FastAPI server
│   │   ├── routes/
│   │   │   ├── dashboard.py     # Dashboard data endpoints
│   │   │   ├── chat.py          # Chat API
│   │   │   └── history.py       # Historical data
│   │   └── websocket.py         # Real-time updates
│   │
│   └── requirements.txt
│
├── shared/                      # Shared types/configs
│   └── config.json              # User configuration
│
├── legacy/                      # Current working code (archive)
│   ├── v1_test.py
│   ├── v2_native_tools.py       # ✅ Current CLI
│   └── v2_adk_tools.py
│
├── PLAN.md                      # This document
├── FINDINGS.md                  # Development findings
└── README.md                    # User documentation
```

---

## Database Schema (SQLite)

Simplified from Stellaris Dashboard - only what we need:

```sql
-- Track game sessions
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    empire_name TEXT NOT NULL,
    empire_ethics TEXT,           -- JSON array
    empire_authority TEXT,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_save_date TEXT,          -- In-game date
    last_updated TIMESTAMP
);

-- Snapshots at each autosave
CREATE TABLE snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    game_date TEXT NOT NULL,      -- "2342.06.15"
    game_days INTEGER,            -- Days since 2200.01.01 for sorting

    -- Military
    military_power INTEGER,
    fleet_count INTEGER,
    army_count INTEGER,

    -- Economy
    energy_income REAL,
    energy_expense REAL,
    minerals_income REAL,
    alloys_income REAL,

    -- Empire
    colony_count INTEGER,
    total_pops INTEGER,
    system_count INTEGER,

    -- Tech
    tech_count INTEGER,

    -- Raw data (for detailed queries)
    full_briefing_json TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

-- Track significant events for the chronicle
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    game_date TEXT NOT NULL,
    event_type TEXT NOT NULL,     -- 'war_started', 'leader_died', 'tech_completed', etc.
    description TEXT,
    data_json TEXT,               -- Event-specific data
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

-- Event types
-- war_started, war_ended, leader_died, leader_hired, tech_completed,
-- colony_founded, colony_lost, first_contact, treaty_signed, crisis_started
```

---

## Discord Bot Commands

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          DISCORD BOT COMMANDS                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  /ask <question>                                                            │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Ask any question about your empire. Uses Gemini with full tool access.     │
│                                                                             │
│  Examples:                                                                   │
│  • /ask What's my military situation?                                       │
│  • /ask Who should I attack next?                                           │
│  • /ask Tell me about the Prikkiki-Ti                                       │
│                                                                             │
│                                                                             │
│  /status                                                                     │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Quick empire status - military, economy, diplomacy at a glance.            │
│                                                                             │
│  Response:                                                                   │
│  ┌─────────────────────────────────────────┐                               │
│  │ 🏛️ United Nations of Earth | 2342.06    │                               │
│  │ ⚔️ Military: 125,866 | 🚀 Fleets: 8     │                               │
│  │ 💰 Energy: +245/mo | ⚙️ Alloys: +89/mo  │                               │
│  │ 🌍 Colonies: 22 | 👥 Pops: 786          │                               │
│  │ 🔬 Techs: 211 | 📊 Phase: Late Game     │                               │
│  │ ⚠️ At War: No | 🤝 Federation: Yes      │                               │
│  └─────────────────────────────────────────┘                               │
│                                                                             │
│                                                                             │
│  /briefing                                                                   │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Full strategic briefing from your advisor. Personality-aware response.     │
│                                                                             │
│                                                                             │
│  /war [empire_name]                                                          │
│  ─────────────────────────────────────────────────────────────────────────  │
│  War room analysis. Compare forces, assess threats, get recommendations.    │
│                                                                             │
│                                                                             │
│  /leaders                                                                    │
│  ─────────────────────────────────────────────────────────────────────────  │
│  List your leaders with their traits and levels.                            │
│                                                                             │
│                                                                             │
│  /history                                                                    │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Show recent events and changes since last session.                         │
│                                                                             │
│                                                                             │
│  /settings                                                                   │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Configure bot settings (thinking level, verbosity, etc.)                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Phases

### Phase 1: CLI Foundation ✅ COMPLETE

**Status:** Done (2026-01-12)

| Task | Status |
|------|--------|
| Save file parsing | ✅ |
| Gemini integration | ✅ |
| 12 extraction tools | ✅ |
| Dynamic personality | ✅ |
| Save file finder | ✅ |
| CLI interface | ✅ |

**Files:** `v2_native_tools.py`, `save_extractor.py`, `save_loader.py`, `personality.py`

---

### Phase 2: Discord Bot 🔄 IN PROGRESS

**Goal:** Chat with your advisor while playing via Discord overlay.

| Task | Priority | Complexity | Dependencies |
|------|----------|------------|--------------|
| Basic Discord bot setup | P0 | Low | None |
| `/ask` command with Gemini | P0 | Low | Bot setup |
| `/status` quick summary | P0 | Low | Bot setup |
| `/briefing` full analysis | P1 | Low | Bot setup |
| Save watcher (watchdog) | P1 | Medium | None |
| Auto-notification on save change | P1 | Medium | Watcher |
| `/war` analysis command | P2 | Medium | Bot setup |
| `/leaders` command | P2 | Low | Bot setup |

**New Files:**
```
backend/
├── bot/
│   ├── discord_bot.py          # Main bot class
│   └── commands/
│       ├── ask.py
│       ├── status.py
│       └── briefing.py
└── core/
    └── save_watcher.py         # watchdog integration
```

**Discord Bot Implementation:**

```python
# discord_bot.py (simplified)
import discord
from discord import app_commands
from discord.ext import commands

class StellarisBot(commands.Bot):
    def __init__(self, companion):
        intents = discord.Intents.default()
        super().__init__(command_prefix='!', intents=intents)
        self.companion = companion

    async def setup_hook(self):
        await self.tree.sync()

@app_commands.command(name="ask", description="Ask your strategic advisor")
async def ask(interaction: discord.Interaction, question: str):
    await interaction.response.defer(thinking=True)
    response, elapsed = bot.companion.chat(question)
    await interaction.followup.send(response[:2000])  # Discord limit

@app_commands.command(name="status", description="Quick empire status")
async def status(interaction: discord.Interaction):
    data = bot.companion.extractor.get_player_status()
    embed = format_status_embed(data)
    await interaction.response.send_message(embed=embed)
```

---

### Phase 3: Historical Data & Dashboard

**Goal:** Track empire over time, show graphs, session summaries.

| Task | Priority | Complexity | Dependencies |
|------|----------|------------|--------------|
| SQLite database setup | P0 | Low | None |
| Snapshot on save detection | P0 | Medium | DB + Watcher |
| Event detection (war, leader death) | P1 | Medium | DB |
| FastAPI server | P1 | Medium | None |
| Timeline data endpoint | P1 | Low | FastAPI |
| Basic dashboard (Chart.js) | P1 | Medium | FastAPI |
| Session summary generation | P2 | Medium | Events |
| `/history` Discord command | P2 | Low | Events |

**New Files:**
```
backend/
├── core/
│   └── database.py             # SQLite wrapper
├── api/
│   ├── server.py               # FastAPI
│   └── routes/
│       ├── dashboard.py
│       └── history.py
```

**Database Integration:**

```python
# database.py (simplified)
import sqlite3
from pathlib import Path

class GameDatabase:
    def __init__(self, db_path: str = "stellaris_history.db"):
        self.conn = sqlite3.connect(db_path)
        self._init_schema()

    def record_snapshot(self, session_id: str, extractor):
        """Called when new save detected."""
        briefing = extractor.get_full_briefing()
        self.conn.execute("""
            INSERT INTO snapshots
            (session_id, game_date, military_power, colony_count, ...)
            VALUES (?, ?, ?, ?, ...)
        """, (session_id, briefing['date'], ...))
        self.conn.commit()

    def get_timeline(self, session_id: str) -> list[dict]:
        """For dashboard graphs."""
        cursor = self.conn.execute("""
            SELECT game_date, military_power, colony_count, energy_income
            FROM snapshots WHERE session_id = ?
            ORDER BY game_days
        """, (session_id,))
        return [dict(row) for row in cursor.fetchall()]
```

---

### Phase 4: Electron Desktop App

**Goal:** Polished desktop app with system tray, settings UI, and dashboard.

| Task | Priority | Complexity | Dependencies |
|------|----------|------------|--------------|
| Electron project setup | P0 | Medium | None |
| System tray integration | P0 | Low | Electron |
| Spawn Python backend | P0 | Medium | Electron |
| Settings UI (API keys) | P1 | Medium | Electron |
| Dashboard view (React) | P1 | High | FastAPI |
| Timeline charts (Chart.js) | P1 | Medium | Dashboard |
| Game detection (running/closed) | P2 | Medium | Electron |
| Auto-show on game exit | P2 | Medium | Detection |
| electron-builder packaging | P2 | Medium | All above |
| Auto-updates | P3 | High | Packaging |

**New Files:**
```
electron/
├── main.js                     # Main process
├── preload.js
├── package.json
└── renderer/
    ├── App.tsx
    ├── components/
    │   ├── Dashboard.tsx
    │   ├── Timeline.tsx
    │   ├── Chat.tsx
    │   └── Settings.tsx
    └── styles/
```

**Electron Main Process:**

```javascript
// main.js (simplified)
const { app, BrowserWindow, Tray, Menu } = require('electron');
const { spawn } = require('child_process');
const path = require('path');

let mainWindow;
let tray;
let pythonProcess;

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1200,
        height: 800,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            nodeIntegration: false,
            contextIsolation: true,
        }
    });
    mainWindow.loadFile('renderer/index.html');
}

function startPythonBackend() {
    pythonProcess = spawn('python', ['backend/main.py'], {
        cwd: path.join(__dirname, '..'),
    });
    pythonProcess.stdout.on('data', (data) => {
        console.log(`Python: ${data}`);
    });
}

function createTray() {
    tray = new Tray(path.join(__dirname, 'icon.png'));
    const contextMenu = Menu.buildFromTemplate([
        { label: 'Open Dashboard', click: () => mainWindow.show() },
        { label: 'Status: Watching saves...', enabled: false },
        { type: 'separator' },
        { label: 'Quit', click: () => app.quit() }
    ]);
    tray.setContextMenu(contextMenu);
}

app.whenReady().then(() => {
    startPythonBackend();
    createWindow();
    createTray();
});
```

---

### Phase 5: Advanced Features

**Goal:** Full design document vision.

| Feature | Priority | Complexity | Notes |
|---------|----------|------------|-------|
| Intel filtering (fog of war) | P2 | High | Parse intel_manager |
| Delta detection ("what changed") | P2 | Medium | Compare snapshots |
| Analysis queue (pre-gen insights) | P2 | Medium | Background processing |
| Chronicle generation | P3 | High | Narrative from events |
| War room mode | P3 | Medium | Deep military analysis |
| Leader biographies | P3 | Medium | Generated backstories |
| Three modes (Immersive/Learning/Post-game) | P3 | Medium | Different prompts |
| Rust parser (performance) | P4 | High | PyO3 integration |

---

## Stellaris Dashboard Learnings

Key insights from analyzing [stellaris-dashboard](https://github.com/benreid24/stellaris-dashboard):

### What to Adopt

| Feature | Their Approach | Our Approach |
|---------|----------------|--------------|
| **Historical tracking** | SQLite with comprehensive schema | Simplified schema (snapshots + events) |
| **Save watching** | File system watcher | Same (watchdog library) |
| **Timeline graphs** | Dash/Plotly | Chart.js in Electron |
| **Name localization** | game_info.py for Stellaris 3.4+ | Add to save_extractor if needed |

### What NOT to Adopt

| Feature | Why Not |
|---------|---------|
| Full pop tracking by species/faction/job | Overkill for LLM advisor |
| Rust parser | Start with Python, add later if needed |
| Their mod system | We're not injecting into Stellaris |
| Dash/Plotly | Using Electron with Chart.js instead |

### Key Patterns Learned

1. **Session tracking** - Their `GameState` model for snapshots at each autosave
2. **Event detection** - `HistoricalEventType` enum for categorizing changes
3. **Date conversion** - `date_to_days()` / `days_to_date()` for sorting
4. **Name resolution** - Stellaris 3.4+ uses templated names that need lookup

---

## Configuration

```json
// shared/config.json
{
    "gemini_api_key": "user-provided",
    "discord_bot_token": "user-provided",
    "discord_channel_id": "optional",

    "stellaris_save_path": "auto-detected",
    "polling_interval_seconds": 60,

    "personality": {
        "thinking_level": "dynamic",
        "verbosity": "normal"
    },

    "dashboard": {
        "port": 8765,
        "auto_open_on_game_exit": true
    }
}
```

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Discord overlay doesn't work for some users | Medium | High | Document Steam overlay browser as fallback |
| Large saves cause slow parsing | Low | Medium | Add caching, consider Rust parser |
| Gemini rate limits during gameplay | Low | Medium | Implement request queuing, backoff |
| Electron bundle too large | Medium | Low | Accept it, or switch to Tauri if overlay not needed |
| Steam Cloud sync issues for GFN users | Medium | Medium | Manual save upload option |

---

## Success Metrics

| Metric | Phase 2 Target | Phase 4 Target |
|--------|----------------|----------------|
| Time from question to answer | <10s | <8s |
| Discord bot uptime | 95% | 99% |
| Save detection latency | <5s | <2s |
| Dashboard load time | N/A | <3s |
| User can set up in | 10 min | 5 min |

---

## Open Questions

1. **Shared Discord bot vs BYOB?**
   - Shared: Easier setup, we pay for hosting
   - BYOB: User creates own bot, more control, no hosting cost
   - **Leaning:** BYOB with detailed setup guide

2. **GeForce Now save sync?**
   - Steam Cloud polling works but adds latency
   - Could add manual upload option
   - **Leaning:** Start with local saves, add GFN support later

3. **Multi-empire support?**
   - Current: One active save at a time
   - Future: Switch between empires/saves
   - **Leaning:** Defer to Phase 5

---

## Next Steps

1. **Immediate (This Week):**
   - [ ] Create Discord bot with /ask, /status commands
   - [ ] Add save watcher with watchdog
   - [ ] Test Discord overlay while gaming

2. **Short Term (2 Weeks):**
   - [ ] Add SQLite database
   - [ ] Implement snapshot recording
   - [ ] Create FastAPI server
   - [ ] Basic dashboard with timeline

3. **Medium Term (1 Month):**
   - [ ] Electron app scaffold
   - [ ] System tray integration
   - [ ] Settings UI
   - [ ] Package with electron-builder

---

## References

- [Stellaris Dashboard](https://github.com/benreid24/stellaris-dashboard) - Historical tracking patterns
- [Discord.py](https://discordpy.readthedocs.io/) - Python Discord library
- [Electron](https://www.electronjs.org/) - Desktop app framework
- [Watchdog](https://python-watchdog.readthedocs.io/) - File system events
- [Chart.js](https://www.chartjs.org/) - JavaScript charting
