# CLAUDE.md - Stellaris LLM Companion

## Project Identity

An AI-powered strategic advisor for Stellaris using **Gemini 3 Flash**. Reads save files, provides strategic analysis, and adapts personality to match empire ethics/government. Privacy-first: saves stay local, BYOK model.

## Tech Stack

- **LLM**: Google Gemini 3 Flash (`gemini-3-flash-preview`)
- **Save Parser**: Rust (stellaris-parser) - **required**
- **Backend**: Python 3
- **Frontend**: Electron + React
- **Database**: SQLite for history tracking
- **File Watching**: watchdog library

## Architecture

```
Save File (50-100MB)
        ↓
Rust Parser (stellaris-parser) ← Session mode, streaming iteration
        ↓
Python Extractors (stellaris_save_extractor/) ← Domain-specific methods
        ↓
Signals (backend/core/signals.py) ← Normalized snapshots
        ↓
Events (backend/core/events.py) ← Diff detection, history
        ↓
Gemini 3 Flash ← Dynamic personality prompt
        ↓
Strategic Response
```

**Design principle**: Rust-first extraction. The Rust parser handles all gamestate parsing via session mode. Python extractors call Rust primitives (iter_section, get_entry, batch_ops) - no regex fallbacks.

## Key Files

| File | Purpose |
|------|---------|
| `stellaris-parser/` | Rust parser (required) |
| `rust_bridge.py` | Python↔Rust IPC bridge |
| `stellaris_save_extractor/` | Domain extractors (economy, military, etc.) |
| `backend/core/signals.py` | Snapshot normalization |
| `backend/core/events.py` | History diff detection |
| `backend/core/companion.py` | Main advisor engine |
| `backend/core/chronicle.py` | Narrative generation |
| `personality.py` | Dynamic personality from ethics/civics |
| `electron/` | Desktop app (React + Electron) |

## Project Structure

```
stellaris-companion/
├── stellaris-parser/        # Rust parser (cargo build --release)
│   └── src/commands/serve.rs
├── rust_bridge.py           # Python↔Rust session management
├── stellaris_save_extractor/
│   ├── base.py              # Core extraction primitives
│   ├── economy.py           # Resources, pops, budget
│   ├── military.py          # Fleets, wars, starbases
│   ├── diplomacy.py         # Relations, federations
│   └── ...                  # Other domain extractors
├── backend/
│   ├── core/
│   │   ├── companion.py     # Main advisor engine
│   │   ├── signals.py       # Snapshot normalization
│   │   ├── events.py        # History diff detection
│   │   ├── chronicle.py     # Narrative generation
│   │   └── ingestion_worker.py  # Save processing
│   └── electron_main.py     # Electron backend entry
├── electron/                # Desktop app
│   └── renderer/            # React components
├── personality.py           # Personality system
└── tests/                   # Test suite
```

## Core Constraints

1. **Rust Required**: The Rust parser must be built (`cargo build --release`) before running
2. **Universal Compatibility**: Must work with any Stellaris game at any stage - early/mid/late game, any empire type (organic, machine, hive mind), any ethics/civics, mods, multiplayer
3. **Model**: Use `gemini-3-flash-preview` (not gemini-2.0-flash)
4. **Save Size**: Gamestate can reach ~100MB late-game; Rust parser handles via streaming
5. **Privacy**: No uploads, no telemetry, saves stay local
6. **Session Mode**: All extraction uses Rust session mode - no regex fallbacks

## Current Status

- **Electron App**: Working (primary interface)
- **CLI**: Working
- **Chronicle**: Working (narrative history generation)
- **History Tracking**: Working (SQLite-backed)

## Environment

```bash
# .env (gitignored)
GOOGLE_API_KEY=your-gemini-key
```

## Commands

```bash
# First time setup - build Rust parser (REQUIRED)
cd stellaris-parser && ~/.cargo/bin/cargo build --release && cd ..

# Electron app (primary)
./dev.sh

# CLI
python v2_native_tools.py                    # Interactive
python v2_native_tools.py path/to/save.sav   # Specific save
```

## Design Principles

- **Rust-First Extraction**: All gamestate parsing via Rust session mode (iter_section, get_entry, batch_ops)
- **No Regex Fallbacks**: Python extractors require Rust - simpler code, better accuracy
- **Signals Pipeline**: Normalized snapshots built once per save, used by events/chronicle
- **Dynamic Personality**: Advisor tone derived from empire ethics/civics/government
- **Gemini for Cost**: Significantly cheaper than alternatives with large context

## Rust Bridge Patterns

```python
# Session mode (required for all extraction)
from rust_bridge import session, _get_active_session

with session(save_path):
    extractor = SaveExtractor(save_path)
    briefing = extractor.get_complete_briefing()

# Inside extractors - use session primitives
session = _get_active_session()
for entry_id, entry in session.iter_section('country'):
    if isinstance(entry, dict):  # P010: handle "none" strings
        name = entry.get('name')  # P011: use .get() with defaults
```

## Commit Style

- Imperative mood: "Add", "Fix", "Implement"
- Reference story IDs when applicable (MIG-XXX, GHR-XXX, UHE-XXX)
