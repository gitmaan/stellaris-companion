# Stellaris LLM Companion

AI-powered strategic advisor for Stellaris using Gemini 3 Flash. Chat with an intelligent advisor that understands your empire's situation, provides strategic analysis, and adapts its personality to your empire's ethics and civics.

## Features

- **12 Data Extraction Tools** - Military, economy, diplomacy, leaders, planets, starbases, technology
- **Dynamic Personality** - Advisor tone adapts to your empire's ethics, government, and civics
- **Efficient Architecture** - Lean + Tools approach minimizes token usage (~85% cheaper than full-context)
- **Auto Save Detection** - Automatically finds your most recent Stellaris save

## Quick Start

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
│  12 Data Tools  │ ◄── Query save file on demand
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
├── save_extractor.py    # Save file parser with tools
├── save_loader.py       # Save file discovery
├── personality.py       # Dynamic advisor personality
├── FINDINGS.md          # Development notes
├── PLAN.md              # Implementation roadmap
└── requirements.txt     # Python dependencies
```

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
