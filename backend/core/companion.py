"""
Stellaris Companion Core
========================

Refactored companion class from v2_native_tools.py.
Provides a reusable interface for the Gemini-powered strategic advisor.
"""

import os
import sys
import time
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from google import genai
    from google.genai import types
except ImportError:
    raise ImportError("google-genai package not installed. Run: pip install google-genai")

from save_extractor import SaveExtractor
from personality import build_personality_prompt_v2, get_personality_summary


# Fallback system prompt (used if personality generation fails)
FALLBACK_SYSTEM_PROMPT = """You are a Stellaris strategic advisor. You have access to tools that can query the player's save file.

Your role:
- Answer questions about the game state using the tools provided
- Provide strategic analysis and advice
- Be conversational and helpful, like a trusted advisor
- Call tools to get the data you need before answering

IMPORTANT - Tool Selection Strategy:
- For BROAD questions (status reports, strategic briefings, "catch me up", overall analysis):
  -> Use get_full_briefing() - it returns everything in ONE call (most efficient)
- For SPECIFIC questions (just leaders, just economy, specific empire):
  -> Use the targeted tool (get_leaders, get_resources, etc.)

Always use tools to get current data rather than guessing."""


class Companion:
    """Stellaris companion using native Gemini SDK with automatic tool execution.

    This is a reusable class that can be used by the CLI, Discord bot, or other interfaces.
    """

    def __init__(self, save_path: str | Path | None = None, api_key: str | None = None):
        """Initialize the companion.

        Args:
            save_path: Path to the Stellaris .sav file. If None, will try to find most recent.
            api_key: Google API key. If None, reads from GOOGLE_API_KEY env var.
        """
        # Get API key
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY environment variable not set")

        self.client = genai.Client(api_key=self.api_key)
        self._chat_session = None
        self._thinking_level = 'dynamic'

        # Initialize save-related attributes
        self.save_path: Path | None = None
        self.last_modified: float | None = None
        self.extractor: SaveExtractor | None = None
        self.metadata: dict = {}
        self.identity: dict = {}
        self.situation: dict = {}
        self.system_prompt: str = FALLBACK_SYSTEM_PROMPT
        self.personality_summary: str = "No save loaded"

        # Load save if provided
        if save_path:
            self.load_save(save_path)

    def load_save(self, save_path: str | Path) -> None:
        """Load a save file and initialize the companion.

        Args:
            save_path: Path to the Stellaris .sav file
        """
        self.save_path = Path(save_path)
        if not self.save_path.exists():
            raise FileNotFoundError(f"Save file not found: {save_path}")

        self.last_modified = self.save_path.stat().st_mtime
        self.extractor = SaveExtractor(str(self.save_path))

        # Get basic metadata for context
        self.metadata = self.extractor.get_metadata()

        # Extract empire identity and situation for personality
        self.identity = self.extractor.get_empire_identity()
        self.situation = self.extractor.get_situation()

        # Build dynamic personality prompt
        self._build_personality()

        # Reset chat session for new save
        self._chat_session = None

    def _build_personality(self) -> None:
        """Build the dynamic personality prompt from empire data.

        Uses v2 Gemini-interpreted approach which passes raw empire data
        and lets Gemini's knowledge of Stellaris generate the personality.
        """
        if not self.identity or not self.situation:
            self.system_prompt = FALLBACK_SYSTEM_PROMPT
            self.personality_summary = "Fallback: Generic advisor"
            return

        try:
            self.system_prompt = build_personality_prompt_v2(self.identity, self.situation)
            self.personality_summary = get_personality_summary(self.identity, self.situation)
        except Exception as e:
            print(f"Warning: Failed to build personality ({e}), using fallback")
            self.system_prompt = FALLBACK_SYSTEM_PROMPT
            self.personality_summary = "Fallback: Generic advisor"

    @property
    def is_loaded(self) -> bool:
        """Check if a save file is loaded."""
        return self.extractor is not None

    def check_save_changed(self) -> bool:
        """Check if the save file has been modified.

        Returns:
            True if save file changed, False otherwise
        """
        if not self.save_path:
            return False
        current_mtime = self.save_path.stat().st_mtime
        return current_mtime != self.last_modified

    def reload_save(self) -> bool:
        """Reload the save file and rebuild personality.

        Returns:
            True if identity changed, False otherwise
        """
        if not self.save_path:
            return False

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

        # Reset chat session
        self._chat_session = None

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

    def set_thinking_level(self, level: str) -> None:
        """Set the thinking level for the model.

        Args:
            level: One of 'dynamic', 'minimal', 'low', 'medium', 'high'
        """
        valid_levels = ['dynamic', 'minimal', 'low', 'medium', 'high']
        if level not in valid_levels:
            raise ValueError(f"Invalid thinking level. Must be one of: {valid_levels}")
        self._thinking_level = level
        self._chat_session = None

    async def chat_async(self, user_message: str) -> tuple[str, float]:
        """Send a message and get a response asynchronously.

        Args:
            user_message: The user's question or message

        Returns:
            Tuple of (response_text, elapsed_time_seconds)
        """
        # For now, just wrap the sync version
        # In future, could use async SDK if available
        return self.chat(user_message)

    def chat(self, user_message: str) -> tuple[str, float]:
        """Send a message and get a response using automatic function calling.

        The SDK handles the tool execution loop automatically for gemini-3-flash-preview.

        Args:
            user_message: The user's question or message

        Returns:
            Tuple of (response_text, elapsed_time_seconds)
        """
        if not self.is_loaded:
            return "No save file loaded. Please load a save file first.", 0.0

        start_time = time.time()

        try:
            # Create chat session once (just for history management)
            if self._chat_session is None:
                self._chat_session = self.client.chats.create(
                    model="gemini-3-flash-preview",
                )

            # Build per-message config with tools (cookbook pattern)
            message_config = {
                'system_instruction': self.system_prompt,
                'tools': self._get_tools_list(),
                'temperature': 1.0,
                'max_output_tokens': 4096,
                # Increase AFC limit from default 10 to 20 for complex queries
                'automatic_function_calling': types.AutomaticFunctionCallingConfig(
                    maximum_remote_calls=20,
                ),
            }

            # Add thinking config if not dynamic
            if self._thinking_level != 'dynamic':
                message_config['thinking_config'] = types.ThinkingConfig(
                    thinking_level=self._thinking_level
                )

            # Send message with config - SDK handles automatic function calling
            response = self._chat_session.send_message(
                user_message,
                config=message_config,
            )

            # Extract text from response
            if response.text:
                response_text = response.text
            else:
                # Check if we hit AFC limit with pending function calls
                has_pending_calls = False
                if response.candidates and response.candidates[0].content:
                    for part in response.candidates[0].content.parts:
                        if hasattr(part, 'function_call') and part.function_call:
                            has_pending_calls = True
                            break

                if has_pending_calls:
                    response_text = (
                        "I gathered a lot of data but ran out of processing steps. "
                        "Try asking a more specific question, or use /status for a quick overview."
                    )
                else:
                    response_text = "I processed your request but couldn't generate a text response."

            elapsed = time.time() - start_time
            return response_text, elapsed

        except Exception as e:
            elapsed = time.time() - start_time
            return f"Error: {str(e)}", elapsed

    def clear_conversation(self) -> None:
        """Clear the conversation history by resetting the chat session."""
        self._chat_session = None

    def get_status_data(self) -> dict:
        """Get raw status data for embedding without LLM processing.

        Returns:
            Dictionary with all status data for the /status command
        """
        if not self.is_loaded:
            return {"error": "No save file loaded"}

        player = self.extractor.get_player_status()
        resources = self.extractor.get_resources()
        diplomacy = self.extractor.get_diplomacy()

        return {
            "empire_name": self.metadata.get("name", "Unknown"),
            "date": self.metadata.get("date", "Unknown"),
            "military_power": player.get("military_power", 0),
            "fleet_count": player.get("fleet_count", 0),
            "fleet_size": player.get("fleet_size", 0),
            "tech_power": player.get("tech_power", 0),
            "economy_power": player.get("economy_power", 0),
            "colonies": player.get("colonies", {}),
            "net_resources": resources.get("net_monthly", {}),
            "research_summary": resources.get("summary", {}).get("research_total", 0),
            "diplomacy_summary": diplomacy.get("summary", {}),
            "allies": diplomacy.get("allies", []),
            "federation": diplomacy.get("federation"),
        }

    def get_briefing(self) -> tuple[str, float]:
        """Get a strategic briefing from the advisor.

        This is a convenience method that asks the advisor for a full briefing.

        Returns:
            Tuple of (briefing_text, elapsed_time_seconds)
        """
        return self.chat("Give me a strategic briefing on the current state of my empire. "
                        "Cover military strength, economy, diplomacy, and any pressing concerns.")
