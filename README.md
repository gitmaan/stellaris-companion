# Stellaris LLM Companion - V1 Test

Quick test to verify we can access Stellaris saves and chat with Claude about them.

## Setup

```bash
cd ~/stellaris-companion
pip install -r requirements.txt
```

Make sure you have `ANTHROPIC_API_KEY` set in your environment.

## Getting Your Save Files

### Option A: Manual Download (Quick Test)

1. Go to https://store.steampowered.com/account/remotestorage
2. Log into Steam
3. Find **Stellaris** in the list
4. Click to expand and download a `.sav` file
5. Run: `python v1_test.py ~/Downloads/your_save.sav`

### Option B: Automatic Steam Sync (Ongoing Use)

If you have Steam installed locally but play on GeForce Now:

1. Open Steam client
2. Go to Library → Find Stellaris
3. Right-click → Properties → Cloud
4. Ensure "Steam Cloud" is enabled
5. Steam should sync your GFN saves to: `~/Library/Application Support/Steam/userdata/<id>/281990/remote/save games/`

Then just run `python v1_test.py` and it will find saves automatically.

## Usage

```bash
# With automatic save detection
python v1_test.py

# With specific save file
python v1_test.py /path/to/save.sav
```

### Commands in Chat

- `/search <term>` - Search the full gamestate for specific text
- `/info` - Show save file summary
- `/quit` - Exit

### Example Questions

- "What's the state of my empire?"
- "Who are my neighbors and what do I know about them?"
- "Am I at war with anyone?"
- "What's my fleet strength?"
- "Tell me about my leaders"

## How It Works

1. Stellaris saves are ZIP files containing:
   - `meta` - Basic save info (name, date, version)
   - `gamestate` - Full game state in Clausewitz format (can be 10-50MB)

2. We extract the save and send the first ~80k characters to Claude
   - This captures metadata, player empire, and early game data
   - Use `/search` to find specific info in the rest of the file

3. Claude reads the Clausewitz format directly - no parsing needed for V1

## Limitations (V1)

- Only sees first ~80k chars of gamestate (full file too big for context)
- No automatic file watching yet
- No fancy parsing - raw Clausewitz format
- No intel filtering yet (Claude sees everything in the save)

These will be addressed in future versions.
