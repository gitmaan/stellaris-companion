# Stellaris LLM Companion

AI-powered strategic advisor for Stellaris using Gemini 3 Flash. Chat with an intelligent advisor that understands your empire's situation, provides strategic analysis, and adapts its personality to your empire's ethics and civics.

## Features

- **Fast /ask (Consolidated Tools)** - Snapshot + drill-down tools to minimize tool-chaining and latency
- **Deep Extraction Coverage** - Detailed categories for military, economy, diplomacy, leaders, planets, starbases, technology
- **Dynamic Personality** - Advisor tone adapts to your empire's ethics, government, and civics
- **Efficient Architecture** - Lean + Tools approach minimizes token usage (~85% cheaper than full-context)
- **Auto Save Detection** - Automatically finds your most recent Stellaris save
- **Discord Bot** - In-game friendly interface via Discord overlay

## Quick Start

### CLI (local terminal)

```bash
# Clone and setup
cd ~/stellaris-companion
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Set your API key
export GOOGLE_API_KEY="your-gemini-api-key"

# Run the companion
python v2_native_tools.py
```

### Discord Bot (recommended for in-game use)

Create a Discord bot token and set:
- `DISCORD_BOT_TOKEN` (required)
- `GOOGLE_API_KEY` (required)
- `NOTIFICATION_CHANNEL_ID` (optional, for save change notifications)

```bash
source venv/bin/activate
export DISCORD_BOT_TOKEN="your-discord-bot-token"
export GOOGLE_API_KEY="your-gemini-api-key"

# Start the bot (optionally provide a .sav path)
python backend/main.py
```

## Getting a Gemini API Key

1. Go to [Google AI Studio](https://aistudio.google.com/)
2. Sign in with your Google account
3. Click "Get API Key" and create a new key
4. Set it as an environment variable or add to `.env` file:
   ```bash
   echo 'GOOGLE_API_KEY="your-key-here"' > .env
   ```

## Getting Your Save Files

### Option A: Local Stellaris Install

Save files are automatically detected from:
- **macOS:** `~/Documents/Paradox Interactive/Stellaris/save games/`
- **Linux:** `~/.local/share/Paradox Interactive/Stellaris/save games/`
- **Windows:** `Documents\Paradox Interactive\Stellaris\save games\`

### Option B: GeForce Now / Cloud Gaming

1. Go to https://store.steampowered.com/account/remotestorage
2. Log into Steam
3. Find **Stellaris** in the list
4. Download your `.sav` file
5. Run: `python v2_native_tools.py ~/Downloads/your_save.sav`

## Usage

### CLI

```bash
# Auto-detect most recent save
python v2_native_tools.py

# Specific save file
python v2_native_tools.py /path/to/save.sav
```

### Commands

| Command | Description |
|---------|-------------|
| `/quit` | Exit the companion |
| `/clear` | Clear conversation history |
| `/reload` | Reload save file (after new autosave) |
| `/personality` | Show current advisor personality |
| `/prompt` | Display full system prompt |
| `/thinking <level>` | Set thinking depth (dynamic/minimal/low/medium/high) |

### Example Questions

- "Give me a strategic briefing"
- "What's my military situation?"
- "Who should I be worried about?"
- "Tell me about my admirals"
- "What's wrong with my economy?"
- "What tech should I research next?"

## Architecture

The project supports two main interfaces:
- **CLI**: direct tool calling (more granular tools)
- **Discord bot**: `/ask` optimized around a consolidated tool interface (snapshot + drill-down)

```
User Question
     │
     ▼
┌─────────────────┐
│  Gemini 3 Flash │ ◄── Dynamic personality prompt
│  + Tool Calling │     based on empire identity
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Snapshot +      │ ◄── Query save file on demand
│ Drill-down      │     (consolidated tool surface)
│  (on-demand)    │     (not pre-loaded into context)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Strategic       │
│ Response        │
└─────────────────┘
```

## Available Tools

### Discord `/ask` tool surface (consolidated)

The Discord bot’s `/ask` is optimized to answer most questions from a single snapshot, only drilling down when needed:

| Tool | Description |
|------|-------------|
| `get_snapshot()` | One-call overview of your current empire state (backed by `get_full_briefing()`) |
| `get_details(categories, limit)` | Batched drill-down for specific categories (leaders, planets, starbases, technology, wars, fleets, resources, diplomacy) |
| `get_empire_details(name)` | Lookup another empire by name |
| `search_save_file(query)` | Raw text search escape hatch |

### CLI tools (more granular)

| Tool | Description |
|------|-------------|
| `get_full_briefing()` | Comprehensive overview (use for broad questions) |
| `get_player_status()` | Military power, economy, tech |
| `get_leaders()` | Scientists, admirals, generals, governors |
| `get_technology()` | Completed techs and current research |
| `get_resources()` | Income, expenses, net monthly |
| `get_diplomacy()` | Relations, treaties, alliances |
| `get_planets()` | Colonies, population, stability |
| `get_starbases()` | Starbases, modules, buildings |
| `get_fleet_info()` | Fleet names and counts |
| `get_active_wars()` | Current conflicts |
| `get_empire_details(name)` | Info about a specific empire |
| `search_save_file(query)` | Raw text search in save |

## Modes

Currently operates in **Omniscient Mode** - the advisor can see all data in your save file. This is ideal for post-game analysis and learning.

**Immersive Mode** (fog-of-war filtering) is planned for a future release.

## Project Structure

```
stellaris-companion/
├── v2_native_tools.py   # Main CLI interface
├── backend/main.py      # Discord bot entry point
├── backend/             # Discord bot + shared core
├── save_extractor.py    # Save file parser with tools
├── save_loader.py       # Save file discovery
├── personality.py       # Dynamic advisor personality
├── rust_bridge.py       # Python-Rust binary interface
├── stellaris-parser/    # Rust CLI for fast save parsing
├── bin/                 # Pre-built binaries for distribution
├── FINDINGS.md          # Development notes
├── PLAN.md              # Implementation roadmap
└── requirements.txt     # Python dependencies
```

## Rust Parser (stellaris-parser)

The project uses a Rust-based parser (`stellaris-parser`) for fast, reliable parsing of Stellaris save files. The parser is built on the [jomini](https://crates.io/crates/jomini) library which handles all Clausewitz format edge cases.

### Binary Distribution

Pre-built binaries are available in the `bin/` directory or from [GitHub Releases](https://github.com/your-repo/stellaris-companion/releases).

### Building from Source

```bash
cd stellaris-parser
cargo build --release
# Binary: stellaris-parser/target/release/stellaris-parser
```

### CLI Usage

```bash
# Extract sections from a save file
./stellaris-parser/target/release/stellaris-parser extract-save test_save.sav --sections meta,galaxy --output -

# Stream entries from large sections (JSONL format)
./stellaris-parser/target/release/stellaris-parser iter-save test_save.sav --section country --format jsonl
```

The Python code uses the Rust parser automatically via `rust_bridge.py`. See `docs/RUST_PARSER_ARCHITECTURE.md` for the full architecture decision record.

## Development

See [FINDINGS.md](./FINDINGS.md) for technical decisions and [PLAN.md](./PLAN.md) for the roadmap.

### Running Legacy V1 (Claude)

The original Claude-based prototype is preserved:
```bash
export ANTHROPIC_API_KEY="your-key"
python v1_test.py /path/to/save.sav
```

## License

MIT
