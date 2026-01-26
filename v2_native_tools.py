#!/usr/bin/env python3
"""
Stellaris Companion - CLI Interface
====================================

Interactive CLI for the Stellaris strategic advisor.
Uses the unified Companion class from backend/core/.

Usage:
    python v2_native_tools.py [save_file.sav]
"""

import sys
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables from .env file
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # dotenv not installed, rely on environment variables

from backend.core.companion import Companion


def main():
    print("\n" + "=" * 60)
    print("STELLARIS COMPANION - CLI (Unified)")
    print("=" * 60)

    # Check for save file argument or find most recent
    if len(sys.argv) >= 2:
        save_path = sys.argv[1]
        if not Path(save_path).exists():
            print(f"Error: File not found: {save_path}")
            sys.exit(1)
    else:
        # Try to find most recent save
        from save_loader import find_most_recent_save

        save_path = find_most_recent_save()
        if save_path is None:
            print("\nNo save file specified and no saves found.")
            print("Usage: python v2_native_tools.py <save_file.sav>")
            print("\nOr place a .sav file in this directory.")
            sys.exit(1)
        print(f"\nNo save specified, using most recent: {save_path.name}")

    # Initialize companion
    print(f"\nLoading save file: {save_path}")
    companion = Companion(save_path)

    print("\nSave loaded:")
    print(f"  Empire: {companion.metadata.get('name', 'Unknown')}")
    print(f"  Date: {companion.metadata.get('date', 'Unknown')}")
    print(f"  Version: {companion.metadata.get('version', 'Unknown')}")

    # Display personality info
    print("\nCompanion Personality:")
    print(f"  {companion.personality_summary}")

    print("\n" + "=" * 60)
    print("Commands: /quit, /clear, /reload, /personality, /prompt, /thinking <level>")
    print("Thinking levels: dynamic (default), minimal, low, medium, high")
    print("=" * 60 + "\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        if user_input.lower() == "/quit":
            print("Goodbye!")
            break

        if user_input.lower() == "/clear":
            companion.clear_conversation()
            print("Conversation cleared.\n")
            continue

        if user_input.lower() == "/reload":
            print("Reloading save file...")
            identity_changed = companion.reload_save()
            companion.clear_conversation()  # Reset chat session on reload
            print(
                f"Save reloaded: {companion.metadata.get('name')} | {companion.metadata.get('date')}"
            )
            print(f"Personality: {companion.personality_summary}")
            if identity_changed:
                print("Note: Empire identity has changed! Personality updated.")
            print()
            continue

        if user_input.lower() == "/personality":
            print("\nCurrent Personality:")
            print(f"  {companion.personality_summary}")
            print("\nIdentity:")
            print(f"  Ethics: {companion.identity.get('ethics', [])}")
            print(f"  Authority: {companion.identity.get('authority', 'Unknown')}")
            print(f"  Civics: {companion.identity.get('civics', [])}")
            print(f"  Species: {companion.identity.get('species_class', 'Unknown')}")
            if companion.identity.get("is_gestalt"):
                gestalt_type = (
                    "Machine Intelligence" if companion.identity.get("is_machine") else "Hive Mind"
                )
                print(f"  Gestalt: {gestalt_type}")
            print("\nSituation:")
            print(f"  Game Phase: {companion.situation.get('game_phase', 'Unknown')}")
            print(f"  Year: {companion.situation.get('year', 'Unknown')}")
            print(f"  At War: {companion.situation.get('at_war', False)}")
            economy = companion.situation.get("economy", {})
            deficits = economy.get("resources_in_deficit", 0)
            print(f"  Economy: {deficits} resources in deficit")
            print(f"  Contacts: {companion.situation.get('contact_count', 0)}")
            print()
            continue

        if user_input.lower() == "/prompt":
            print("\n" + "=" * 40)
            print("SYSTEM PROMPT")
            print("=" * 40)
            print(companion.system_prompt)
            print("=" * 40 + "\n")
            continue

        if user_input.lower().startswith("/thinking"):
            parts = user_input.split()
            if len(parts) < 2:
                current = getattr(companion, "_thinking_level", "dynamic")
                print(f"\nCurrent thinking level: {current}")
                print("Usage: /thinking <level>")
                print("Levels: dynamic, minimal, low, medium, high")
                print("  dynamic - Auto-scales based on query complexity (default, recommended)")
                print("  minimal - Lowest latency, almost no thinking (~10s)")
                print("  low     - Minimal reasoning, simple tasks")
                print("  medium  - Balanced for most tasks")
                print("  high    - Maximum depth, always deep reasoning (~25s)\n")
            else:
                level = parts[1].lower()
                try:
                    companion.set_thinking_level(level)
                    print(f"Thinking level set to: {level}\n")
                except ValueError as e:
                    print(f"Error: {e}\n")
            continue

        # Get response using full tool mode for CLI (more granular tools)
        response, elapsed = companion.chat(user_input, tool_mode="full")
        print(f"\nCompanion ({elapsed:.2f}s): {response}\n")


if __name__ == "__main__":
    main()
