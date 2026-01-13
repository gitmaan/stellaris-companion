#!/usr/bin/env python3
"""
Stellaris Companion - V2 Native Tools
======================================

Lean + Tools approach using native Gemini SDK function calling.
Automatic tool execution handled by the SDK.

Usage:
    python v2_native_tools.py <save_file.sav>
"""

import os
import sys
import time
import json
from pathlib import Path

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, rely on environment variables

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("Error: google-genai package not installed")
    print("Run: pip install google-genai")
    sys.exit(1)

from save_extractor import SaveExtractor
from personality import build_optimized_prompt, get_personality_summary


# Fallback system prompt (used if personality generation fails)
FALLBACK_SYSTEM_PROMPT = """You are a Stellaris strategic advisor. You have access to tools that can query the player's save file.

Your role:
- Answer questions about the game state using the tools provided
- Provide strategic analysis and advice
- Be conversational and helpful, like a trusted advisor
- Call tools to get the data you need before answering

IMPORTANT - Tool Selection Strategy:
- For BROAD questions (status reports, strategic briefings, "catch me up", overall analysis):
  → Use get_full_briefing() - it returns everything in ONE call (most efficient)
- For SPECIFIC questions (just leaders, just economy, specific empire):
  → Use the targeted tool (get_leaders, get_resources, etc.)

Always use tools to get current data rather than guessing."""


class StellarisCompanion:
    """Stellaris companion using native Gemini SDK with automatic tool execution."""

    def __init__(self, save_path: str):
        """Initialize the advisor with a save file.

        Args:
            save_path: Path to the Stellaris .sav file
        """
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable not set")

        self.client = genai.Client(api_key=api_key)
        self.save_path = Path(save_path)
        self.last_modified = self.save_path.stat().st_mtime
        self.extractor = SaveExtractor(save_path)
        self.conversation_history = []

        # Get basic metadata for context
        self.metadata = self.extractor.get_metadata()

        # Extract empire identity and situation for personality
        self.identity = self.extractor.get_empire_identity()
        self.situation = self.extractor.get_situation()

        # Build dynamic personality prompt
        self._build_personality()

    def _build_personality(self):
        """Build the dynamic personality prompt from empire data.

        Uses optimized prompt (625 chars) that trusts Gemini's Stellaris knowledge.
        Only hardcodes address style (model can't infer). Handles all empire types
        including gestalts, machines, and hive minds.
        """
        try:
            self.system_prompt = build_optimized_prompt(self.identity, self.situation)
            self.personality_summary = get_personality_summary(self.identity, self.situation)
        except Exception as e:
            print(f"Warning: Failed to build personality ({e}), using fallback")
            self.system_prompt = FALLBACK_SYSTEM_PROMPT
            self.personality_summary = "Fallback: Generic advisor"

    def check_save_changed(self) -> bool:
        """Check if the save file has been modified.

        Returns:
            True if save file changed, False otherwise
        """
        current_mtime = self.save_path.stat().st_mtime
        if current_mtime != self.last_modified:
            return True
        return False

    def reload_save(self):
        """Reload the save file and rebuild personality.

        Call this when the save file has changed.
        """
        old_identity = self.identity.copy() if self.identity else {}

        # Reload extractor
        self.extractor = SaveExtractor(str(self.save_path))
        self.last_modified = self.save_path.stat().st_mtime
        self.metadata = self.extractor.get_metadata()

        # Re-extract identity and situation
        self.identity = self.extractor.get_empire_identity()
        self.situation = self.extractor.get_situation()

        # Check if identity changed
        identity_changed = (
            old_identity.get('ethics') != self.identity.get('ethics') or
            old_identity.get('authority') != self.identity.get('authority') or
            old_identity.get('civics') != self.identity.get('civics')
        )

        # Rebuild personality
        self._build_personality()

        return identity_changed

    # === Tool Functions ===
    # These are passed directly to the SDK which auto-generates schemas from docstrings

    def get_player_status(self) -> dict:
        """Get the player's current empire status including military power, economy, tech, planets, and fleet count.

        Returns:
            Dictionary with player empire metrics
        """
        return self.extractor.get_player_status()

    def get_empire_details(self, empire_name: str) -> dict:
        """Get detailed information about a specific empire by name.

        Args:
            empire_name: The name of the empire to look up (e.g., "Prikkiki-Ti", "Fallen Empire")

        Returns:
            Dictionary with empire details including military power and relations
        """
        return self.extractor.get_empire(empire_name)

    def get_active_wars(self) -> dict:
        """Get information about all active wars in the galaxy.

        Returns:
            Dictionary with war names and details
        """
        return self.extractor.get_wars()

    def get_fleet_info(self) -> dict:
        """Get information about the player's fleets.

        Returns:
            Dictionary with fleet names and count
        """
        return self.extractor.get_fleets()

    def search_save_file(self, query: str) -> dict:
        """Search the full save file for specific text. Use this to find detailed information not available through other tools.

        Args:
            query: Text to search for in the save file

        Returns:
            Dictionary with search results and surrounding context
        """
        return self.extractor.search(query, max_results=3, context_chars=1500)

    def get_leaders(self) -> dict:
        """Get information about all the player's leaders including scientists, admirals, generals, governors, and envoys.

        Returns:
            Dictionary with leader names, classes, levels, ages, and traits
        """
        return self.extractor.get_leaders()

    def get_technology(self) -> dict:
        """Get the player's technology research status including completed technologies and current research projects.

        Returns:
            Dictionary with completed techs, current research in physics/society/engineering, and tech counts
        """
        return self.extractor.get_technology()

    def get_resources(self) -> dict:
        """Get the player's economy snapshot including resource income, expenses, and net monthly production.

        Returns:
            Dictionary with monthly income/expenses for energy, minerals, alloys, food, consumer goods, research, and strategic resources
        """
        return self.extractor.get_resources()

    def get_diplomacy(self) -> dict:
        """Get the player's diplomatic relations with other empires including opinion scores, treaties, and alliances.

        Returns:
            Dictionary with relations list, allies, federation membership, and opinion summaries
        """
        return self.extractor.get_diplomacy()

    def get_planets(self) -> dict:
        """Get information about the player's colonized planets including names, types, population, and stability.

        Returns:
            Dictionary with planet details, total population, and counts by planet type
        """
        return self.extractor.get_planets()

    def get_starbases(self) -> dict:
        """Get information about the player's starbases including levels, modules, and buildings.

        Returns:
            Dictionary with starbase details, counts by level, and module/building lists
        """
        return self.extractor.get_starbases()

    def get_full_briefing(self) -> dict:
        """Get comprehensive empire overview for strategic briefings.

        USE THIS TOOL when the user asks for:
        - A full status report or strategic briefing
        - Overall empire analysis or overview
        - Multiple pieces of information at once (military + economy + diplomacy)
        - "Catch me up" or "What's the situation?"
        - Any broad question requiring data from multiple sources

        This is MORE EFFICIENT than calling multiple individual tools because it
        returns all major data in a single call (~4k tokens).

        Returns:
            Dictionary with military status, economy, diplomacy, territory, defense, and leadership
        """
        return self.extractor.get_full_briefing()

    def _get_tools_list(self) -> list:
        """Get list of tool functions for the SDK."""
        return [
            self.get_full_briefing,
            self.get_player_status,
            self.get_empire_details,
            self.get_active_wars,
            self.get_fleet_info,
            self.search_save_file,
            self.get_leaders,
            self.get_technology,
            self.get_resources,
            self.get_diplomacy,
            self.get_planets,
            self.get_starbases,
        ]

    def set_thinking_level(self, level: str):
        """Set the thinking level for the model.

        Args:
            level: One of 'dynamic', 'minimal', 'low', 'medium', 'high'
                   - dynamic: Auto-scales based on query complexity (default, recommended)
                   - minimal: Almost no thinking, lowest latency
                   - low: Minimal reasoning, simple tasks
                   - medium: Balanced for most tasks
                   - high: Maximum depth, always deep reasoning
        """
        valid_levels = ['dynamic', 'minimal', 'low', 'medium', 'high']
        if level not in valid_levels:
            raise ValueError(f"Invalid thinking level. Must be one of: {valid_levels}")
        self._thinking_level = level
        # Reset chat session to apply new config
        self._chat_session = None

    def chat(self, user_message: str) -> tuple[str, float]:
        """Send a message and get a response using automatic function calling.

        The SDK handles the tool execution loop automatically for gemini-3-flash-preview.

        Args:
            user_message: The user's question or message

        Returns:
            Tuple of (response_text, elapsed_time_seconds)
        """
        start_time = time.time()

        try:
            thinking_level = getattr(self, '_thinking_level', 'dynamic')

            # Create chat session once (just for history management)
            if not hasattr(self, '_chat_session') or self._chat_session is None:
                self._chat_session = self.client.chats.create(
                    model="gemini-3-flash-preview",
                )

            # Build per-message config with tools (cookbook pattern)
            # This ensures automatic function calling works on every message
            message_config = {
                'system_instruction': self.system_prompt,
                'tools': self._get_tools_list(),
                'temperature': 1.0,
                'max_output_tokens': 4096,
            }

            # Add thinking config if not dynamic
            if thinking_level != 'dynamic':
                message_config['thinking_config'] = types.ThinkingConfig(thinking_level=thinking_level)

            # Send message with config - SDK handles automatic function calling
            response = self._chat_session.send_message(
                user_message,
                config=message_config,
            )

            # Extract text from response
            response_text = response.text if response.text else "I processed your request but couldn't generate a text response."

            elapsed = time.time() - start_time
            return response_text, elapsed

        except Exception as e:
            elapsed = time.time() - start_time
            return f"Error: {str(e)}", elapsed

    def clear_conversation(self):
        """Clear the conversation history by resetting the chat session."""
        self._chat_session = None
        self.conversation_history = []


def main():
    print("\n" + "=" * 60)
    print("STELLARIS COMPANION - V2 NATIVE TOOLS (Dynamic Personality)")
    print("=" * 60)

    # Check for save file argument or find most recent
    if len(sys.argv) >= 2:
        save_path = sys.argv[1]
        if not Path(save_path).exists():
            print(f"Error: File not found: {save_path}")
            sys.exit(1)
    else:
        # Try to find most recent save
        from save_loader import find_most_recent_save, list_saves
        save_path = find_most_recent_save()
        if save_path is None:
            print("\nNo save file specified and no saves found.")
            print("Usage: python v2_native_tools.py <save_file.sav>")
            print("\nOr place a .sav file in this directory.")
            sys.exit(1)
        print(f"\nNo save specified, using most recent: {save_path.name}")

    # Initialize companion
    print(f"\nLoading save file: {save_path}")
    companion = StellarisCompanion(save_path)

    print(f"\nSave loaded:")
    print(f"  Empire: {companion.metadata.get('name', 'Unknown')}")
    print(f"  Date: {companion.metadata.get('date', 'Unknown')}")
    print(f"  Version: {companion.metadata.get('version', 'Unknown')}")

    # Display personality info
    print(f"\nCompanion Personality:")
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

        if user_input.lower() == '/quit':
            print("Goodbye!")
            break

        if user_input.lower() == '/clear':
            companion.clear_conversation()
            print("Conversation cleared.\n")
            continue

        if user_input.lower() == '/reload':
            print("Reloading save file...")
            identity_changed = companion.reload_save()
            companion.clear_conversation()  # Reset chat session on reload
            print(f"Save reloaded: {companion.metadata.get('name')} | {companion.metadata.get('date')}")
            print(f"Personality: {companion.personality_summary}")
            if identity_changed:
                print("Note: Empire identity has changed! Personality updated.")
            print()
            continue

        if user_input.lower() == '/personality':
            print(f"\nCurrent Personality:")
            print(f"  {companion.personality_summary}")
            print(f"\nIdentity:")
            print(f"  Ethics: {companion.identity.get('ethics', [])}")
            print(f"  Authority: {companion.identity.get('authority', 'Unknown')}")
            print(f"  Civics: {companion.identity.get('civics', [])}")
            print(f"  Species: {companion.identity.get('species_class', 'Unknown')}")
            if companion.identity.get('is_gestalt'):
                gestalt_type = 'Machine Intelligence' if companion.identity.get('is_machine') else 'Hive Mind'
                print(f"  Gestalt: {gestalt_type}")
            print(f"\nSituation:")
            print(f"  Game Phase: {companion.situation.get('game_phase', 'Unknown')}")
            print(f"  Year: {companion.situation.get('year', 'Unknown')}")
            print(f"  At War: {companion.situation.get('at_war', False)}")
            economy = companion.situation.get('economy', {})
            deficits = economy.get('resources_in_deficit', 0)
            print(f"  Economy: {deficits} resources in deficit")
            print(f"  Contacts: {companion.situation.get('contact_count', 0)}")
            print()
            continue

        if user_input.lower() == '/prompt':
            print("\n" + "=" * 40)
            print("SYSTEM PROMPT")
            print("=" * 40)
            print(companion.system_prompt)
            print("=" * 40 + "\n")
            continue

        if user_input.lower().startswith('/thinking'):
            parts = user_input.split()
            if len(parts) < 2:
                current = getattr(companion, '_thinking_level', 'dynamic')
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

        # Get response
        response, elapsed = companion.chat(user_input)
        print(f"\nCompanion ({elapsed:.2f}s): {response}\n")


if __name__ == "__main__":
    main()
