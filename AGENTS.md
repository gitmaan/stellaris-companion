# AGENTS.md - Stellaris LLM Companion

## Project Identity

An AI-powered strategic advisor for Stellaris using **Gemini 3 Flash**. Reads save files, provides strategic analysis, and adapts personality to match empire ethics/government. Privacy-first: saves stay local, BYOK model.

## Tech Stack

- **LLM**: Google Gemini 3 Flash (`gemini-3-flash-preview`)
- **Backend**: Python 3
- **Bot**: discord.py with slash commands
- **File Watching**: watchdog library
- **Database**: SQLite (planned for history tracking)

## Architecture

```
User Question → Gemini 3 Flash (dynamic personality prompt)
                    ↓
            Tool-based extraction from save file
                    ↓
            Strategic Response
```

**Design principle**: Lean + Tools approach. Save files are large (~70MB) and change frequently, so we extract on-demand rather than loading full context.

## Key Files

| File | Purpose |
|------|---------|
| `backend/main.py` | Discord bot entry point |
| `backend/core/companion.py` | Main advisor engine |
| `save_extractor.py` | Clausewitz save parser |
| `personality.py` | Dynamic personality from ethics/civics |
| `save_loader.py` | Cross-platform save discovery |
| `v2_native_tools.py` | CLI interface |

## Project Structure

```
stellaris-companion/
├── backend/
│   ├── main.py              # Discord bot entry
│   ├── core/
│   │   ├── companion.py     # Main engine
│   │   └── save_watcher.py  # File monitoring
│   └── bot/
│       └── commands/        # Slash commands
├── save_extractor.py        # Parser
├── personality.py           # Personality system
├── save_loader.py           # Save discovery
└── v2_native_tools.py       # CLI
```

## Core Constraints

1. **Universal Compatibility**: Must work with any Stellaris game at any stage - early/mid/late game, any empire type (organic, machine, hive mind), any ethics/civics, mods, multiplayer
2. **Model**: Use `gemini-3-flash-preview` (not gemini-2.0-flash)
3. **Save Size**: Gamestate can reach ~70MB late-game; use smart extraction, not full context
4. **Privacy**: No uploads, no telemetry, saves stay local
5. **Discord**: 2000 char message limit - split long responses

## Current Status

- **CLI**: Working
- **Discord Bot**: In progress
- **History/Dashboard**: Planned
- **Immersive Mode**: Not yet implemented

## Environment

```bash
# .env (gitignored)
GOOGLE_API_KEY=your-gemini-key
DISCORD_BOT_TOKEN=your-discord-token
```

## Commands

```bash
# CLI
python v2_native_tools.py                    # Interactive
python v2_native_tools.py path/to/save.sav   # Specific save

# Discord Bot
python backend/main.py
```

## Design Principles

- **Lean + Tools**: Extract data on-demand, don't pre-load full saves
- **Dynamic Personality**: Advisor tone derived from empire ethics/civics/government
- **Gemini for cost**: Significantly cheaper than alternatives with large context
- **Discord overlay**: Accessible while gaming

## Commit Style

- Imperative mood: "Add", "Fix", "Implement"
- Reference phases when applicable
