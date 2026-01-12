#!/usr/bin/env python3
"""
Stellaris LLM Companion - V1 Test
=================================

Minimal test to verify:
1. We can access Steam Cloud synced saves
2. We can extract and read the save data
3. LLM can understand and discuss the game state

Usage:
    python v1_test.py [path_to_save_file]

If no path provided, will search Steam Cloud sync locations.
"""

import zipfile
import os
import sys
from pathlib import Path
from datetime import datetime

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("Error: google-genai package not installed")
    print("Run: pip install google-genai")
    sys.exit(1)


def find_steam_userdata() -> Path | None:
    """Find the Steam userdata directory."""
    possible_paths = []

    if sys.platform == "darwin":  # Mac
        possible_paths = [
            Path.home() / "Library/Application Support/Steam/userdata",
        ]
    elif sys.platform == "win32":  # Windows
        possible_paths = [
            Path(os.environ.get('PROGRAMFILES(X86)', 'C:/Program Files (x86)')) / "Steam/userdata",
            Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / "Steam/userdata",
            Path.home() / "Steam/userdata",
        ]
    else:  # Linux
        possible_paths = [
            Path.home() / ".steam/steam/userdata",
            Path.home() / ".local/share/Steam/userdata",
        ]

    for path in possible_paths:
        if path.exists():
            return path

    return None


def find_stellaris_saves() -> list[Path]:
    """Find all Stellaris save files from Steam Cloud sync."""
    userdata = find_steam_userdata()

    if not userdata:
        return []

    saves = []

    # Look through all user IDs
    for user_dir in userdata.iterdir():
        if not user_dir.is_dir():
            continue

        # Stellaris app ID is 281990
        stellaris_saves = user_dir / "281990" / "remote" / "save games"

        if stellaris_saves.exists():
            # Find all .sav files recursively
            for save_file in stellaris_saves.glob("**/*.sav"):
                saves.append(save_file)

    # Sort by modification time, newest first
    saves.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    return saves


def extract_save(save_path: Path) -> dict:
    """Extract gamestate and meta from a Stellaris save file."""
    try:
        with zipfile.ZipFile(save_path, 'r') as z:
            # List contents
            file_list = z.namelist()

            result = {
                'path': str(save_path),
                'name': save_path.stem,
                'size': save_path.stat().st_size,
                'modified': datetime.fromtimestamp(save_path.stat().st_mtime),
                'files': file_list,
            }

            # Extract gamestate
            if 'gamestate' in file_list:
                gamestate_bytes = z.read('gamestate')
                result['gamestate'] = gamestate_bytes.decode('utf-8', errors='replace')
                result['gamestate_size'] = len(result['gamestate'])

            # Extract meta
            if 'meta' in file_list:
                meta_bytes = z.read('meta')
                result['meta'] = meta_bytes.decode('utf-8', errors='replace')

            return result

    except zipfile.BadZipFile:
        print(f"Error: {save_path} is not a valid zip file")
        return None
    except Exception as e:
        print(f"Error extracting save: {e}")
        return None


def get_save_summary(save_data: dict) -> str:
    """Generate a quick summary of the save for display."""
    lines = [
        f"Save: {save_data['name']}",
        f"Path: {save_data['path']}",
        f"Modified: {save_data['modified']}",
        f"Gamestate size: {save_data.get('gamestate_size', 0):,} characters",
    ]

    # Try to extract some basic info from meta
    if 'meta' in save_data:
        meta = save_data['meta']
        # Quick parse for common fields
        for line in meta.split('\n'):
            if 'name=' in line and 'flag' not in line:
                lines.append(f"Empire: {line.split('=')[1].strip().strip('\"')}")
            if 'date=' in line:
                lines.append(f"Date: {line.split('=')[1].strip().strip('\"')}")
            if 'version=' in line:
                lines.append(f"Version: {line.split('=')[1].strip().strip('\"')}")

    return '\n'.join(lines)


def prepare_context(save_data: dict, max_chars: int = 80000) -> str:
    """
    Prepare save data for LLM context.

    For V1, we'll send:
    1. Full meta file (small)
    2. Beginning of gamestate (captures structure, player empire, early empires)
    3. Optionally search for specific sections
    """
    parts = []

    # Meta is usually small, include all of it
    if 'meta' in save_data:
        parts.append("=== META FILE ===")
        parts.append(save_data['meta'])
        parts.append("")

    # For gamestate, we need to be strategic
    if 'gamestate' in save_data:
        gamestate = save_data['gamestate']
        remaining_chars = max_chars - sum(len(p) for p in parts)

        parts.append("=== GAMESTATE (truncated) ===")
        parts.append(f"(Full file is {len(gamestate):,} characters, showing first {remaining_chars:,})")
        parts.append("")
        parts.append(gamestate[:remaining_chars])

        if len(gamestate) > remaining_chars:
            parts.append("")
            parts.append(f"... [truncated, {len(gamestate) - remaining_chars:,} more characters] ...")

    return '\n'.join(parts)


def search_gamestate(gamestate: str, search_term: str, context_chars: int = 2000) -> str:
    """Search for a term in gamestate and return surrounding context."""
    results = []
    search_lower = search_term.lower()
    gamestate_lower = gamestate.lower()

    start = 0
    while True:
        pos = gamestate_lower.find(search_lower, start)
        if pos == -1:
            break

        # Get context around the match
        context_start = max(0, pos - context_chars // 2)
        context_end = min(len(gamestate), pos + len(search_term) + context_chars // 2)

        snippet = gamestate[context_start:context_end]
        results.append(f"[Found at position {pos}]\n{snippet}")

        start = pos + 1

        # Limit results
        if len(results) >= 5:
            break

    if results:
        return f"Found {len(results)} matches for '{search_term}':\n\n" + "\n\n---\n\n".join(results)
    else:
        return f"No matches found for '{search_term}'"


def chat_with_save(save_data: dict):
    """Interactive CLI chat about the save file."""
    # Initialize Gemini client
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("Error: GOOGLE_API_KEY environment variable not set")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    # Prepare initial context
    context = prepare_context(save_data)

    system_prompt = f"""You are a Stellaris strategic advisor analyzing a save file.

The user has shared their save file data with you. Here it is:

{context}

---

IMPORTANT NOTES:
1. The gamestate is truncated - you're seeing the first ~80k characters of what could be a 10-50MB file
2. The Clausewitz format uses nested braces {{ }} for structure
3. Key data includes: player info, countries, fleets, planets, leaders, wars, etc.
4. If you need to find specific information that might be later in the file, tell the user and they can search for it

Your role:
- Answer questions about the game state
- Provide strategic analysis and advice
- Help the user understand their empire's situation
- Be conversational and helpful, like a trusted advisor

You can see actual game data, so give specific answers based on what you observe.
If something isn't visible in the truncated data, say so and suggest what to search for.
"""

    # Build conversation history for Gemini format
    conversation_history = []

    print("\n" + "="*60)
    print("STELLARIS SAVE ANALYZER - V1 TEST (Gemini 3 Flash)")
    print("="*60)
    print(get_save_summary(save_data))
    print("="*60)
    print("\nCommands:")
    print("  /search <term>  - Search gamestate for specific text")
    print("  /info           - Show save summary again")
    print("  /quit           - Exit")
    print("\nOr just type questions to chat with the advisor.")
    print("="*60 + "\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        # Handle commands
        if user_input.lower() == '/quit':
            print("Goodbye!")
            break

        if user_input.lower() == '/info':
            print("\n" + get_save_summary(save_data) + "\n")
            continue

        if user_input.lower().startswith('/search '):
            search_term = user_input[8:].strip()
            if search_term and 'gamestate' in save_data:
                print("\nSearching...")
                result = search_gamestate(save_data['gamestate'], search_term)
                print(f"\n{result}\n")
            continue

        # Regular chat - send to Gemini
        conversation_history.append(types.Content(
            role="user",
            parts=[types.Part(text=user_input)]
        ))

        try:
            response = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=conversation_history,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    max_output_tokens=4096,
                )
            )

            assistant_message = response.text
            conversation_history.append(types.Content(
                role="model",
                parts=[types.Part(text=assistant_message)]
            ))

            print(f"\nAdvisor: {assistant_message}\n")

        except Exception as e:
            print(f"\nError calling Gemini API: {e}\n")
            conversation_history.pop()  # Remove the failed user message


def main():
    print("\n" + "="*60)
    print("STELLARIS LLM COMPANION - V1 TEST")
    print("="*60 + "\n")

    # Check for command line argument
    if len(sys.argv) > 1:
        save_path = Path(sys.argv[1])
        if not save_path.exists():
            print(f"Error: File not found: {save_path}")
            sys.exit(1)
        saves = [save_path]
    else:
        # Search for saves
        print("Searching for Stellaris saves in Steam Cloud sync location...")
        saves = find_stellaris_saves()

    if not saves:
        print("\nNo Stellaris saves found automatically.")
        print("\nPossible reasons:")
        print("  1. Steam is not installed locally")
        print("  2. Stellaris saves haven't synced yet")
        print("  3. Saves are in a non-standard location")
        print("\nYou can specify a save file path directly:")
        print(f"  python {sys.argv[0]} /path/to/save.sav")
        print("\nOr enter a path now:")

        manual_path = input("Save file path (or 'quit'): ").strip()
        if manual_path.lower() == 'quit' or not manual_path:
            return

        save_path = Path(manual_path)
        if not save_path.exists():
            print(f"Error: File not found: {save_path}")
            return
        saves = [save_path]

    # Display found saves
    print(f"\nFound {len(saves)} save(s):\n")
    for i, save in enumerate(saves[:10]):  # Show max 10
        modified = datetime.fromtimestamp(save.stat().st_mtime)
        size_mb = save.stat().st_size / (1024 * 1024)
        print(f"  {i+1}. {save.parent.name}/{save.name}")
        print(f"      Modified: {modified.strftime('%Y-%m-%d %H:%M')} | Size: {size_mb:.1f} MB")

    if len(saves) > 10:
        print(f"  ... and {len(saves) - 10} more")

    # Select save
    print()
    if len(saves) == 1:
        choice = 1
        print(f"Using only available save: {saves[0].name}")
    else:
        try:
            choice = int(input("Select save number: "))
        except ValueError:
            print("Invalid selection")
            return

    if choice < 1 or choice > len(saves):
        print("Invalid selection")
        return

    save_path = saves[choice - 1]

    # Extract save
    print(f"\nLoading {save_path.name}...")
    save_data = extract_save(save_path)

    if not save_data:
        print("Failed to load save file")
        return

    print(f"Extracted {save_data.get('gamestate_size', 0):,} characters of gamestate")

    # Start chat
    chat_with_save(save_data)


if __name__ == "__main__":
    main()
