#!/usr/bin/env python3
"""
Stellaris LLM Companion - V2 ADK Tools
======================================

Lean + Tools approach using Google ADK (Agent Development Kit).
Framework handles tool execution and agent loop.

Usage:
    python v2_adk_tools.py <save_file.sav>
"""

import asyncio
import os
import sys
import time
from pathlib import Path

try:
    from google.adk.agents import Agent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types
except ImportError:
    print("Error: google-adk package not installed")
    print("Run: pip install google-adk")
    sys.exit(1)

from save_extractor import SaveExtractor


# Global extractor instance (tools need access)
_extractor: SaveExtractor = None


# === Tool Functions ===
# ADK wraps these automatically based on docstrings and type hints

def get_player_status() -> dict:
    """Get the player's current empire status including military power, economy, tech, planets, and fleet count.

    Returns:
        Dictionary with player empire metrics
    """
    return _extractor.get_player_status()


def get_empire_details(empire_name: str) -> dict:
    """Get detailed information about a specific empire by name.

    Args:
        empire_name: The name of the empire to look up (e.g., "Prikkiki-Ti", "Fallen Empire")

    Returns:
        Dictionary with empire details including military power and relations
    """
    return _extractor.get_empire(empire_name)


def get_active_wars() -> dict:
    """Get information about all active wars in the galaxy.

    Returns:
        Dictionary with war names and details
    """
    return _extractor.get_wars()


def get_fleet_info() -> dict:
    """Get information about the player's fleets.

    Returns:
        Dictionary with fleet names and count
    """
    return _extractor.get_fleets()


def search_save_file(query: str) -> dict:
    """Search the full save file for specific text. Use this to find detailed information not available through other tools.

    Args:
        query: Text to search for in the save file

    Returns:
        Dictionary with search results and surrounding context
    """
    return _extractor.search(query, max_results=3, context_chars=1500)


class StellarisAdvisorADK:
    """Stellaris advisor using Google ADK agent framework."""

    def __init__(self, save_path: str):
        """Initialize the advisor with a save file.

        Args:
            save_path: Path to the Stellaris .sav file
        """
        global _extractor

        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable not set")

        # Set API key for ADK
        os.environ["GOOGLE_API_KEY"] = api_key

        # Load save file
        _extractor = SaveExtractor(save_path)
        self.metadata = _extractor.get_metadata()

        # Create the agent
        self.agent = Agent(
            name="stellaris_advisor",
            model="gemini-3-flash-preview",
            description="Strategic advisor for Stellaris gameplay",
            instruction=f"""You are a Stellaris strategic advisor. You have access to tools that can query the player's save file.

Current save: {self.metadata.get('name', 'Unknown')}
Date: {self.metadata.get('date', 'Unknown')}
Version: {self.metadata.get('version', 'Unknown')}

Your role:
- Answer questions about the game state using the tools provided
- Provide strategic analysis and advice
- Be conversational and helpful, like a trusted advisor
- Call tools to get the data you need before answering

Always use tools to get current data rather than guessing. If you need specific information, search for it.""",
            tools=[
                get_player_status,
                get_empire_details,
                get_active_wars,
                get_fleet_info,
                search_save_file,
            ],
        )

        # Create session service and runner
        self.session_service = InMemorySessionService()
        self.runner = Runner(
            agent=self.agent,
            app_name="stellaris_companion",
            session_service=self.session_service,
        )

        # Session will be created async
        self.session = None

    async def _ensure_session(self):
        """Create session if not exists."""
        if self.session is None:
            self.session = await self.session_service.create_session(
                app_name="stellaris_companion",
                user_id="player",
            )

    async def chat_async(self, user_message: str) -> tuple[str, float]:
        """Send a message and get a response (async).

        Args:
            user_message: The user's question or message

        Returns:
            Tuple of (response_text, elapsed_time_seconds)
        """
        start_time = time.time()

        try:
            await self._ensure_session()

            # Run the agent - use run_async for async iteration
            # new_message must be a types.Content object
            content = types.Content(
                role="user",
                parts=[types.Part(text=user_message)]
            )
            response = self.runner.run_async(
                user_id="player",
                session_id=self.session.id,
                new_message=content,
            )

            # Extract the response text
            response_text = ""
            async for event in response:
                if hasattr(event, 'content') and event.content:
                    if hasattr(event.content, 'parts'):
                        for part in event.content.parts:
                            if hasattr(part, 'text') and part.text:
                                response_text += part.text

            elapsed = time.time() - start_time
            return response_text or "No response generated", elapsed

        except Exception as e:
            elapsed = time.time() - start_time
            return f"Error: {str(e)}", elapsed

    def chat(self, user_message: str) -> tuple[str, float]:
        """Send a message and get a response (sync wrapper).

        Args:
            user_message: The user's question or message

        Returns:
            Tuple of (response_text, elapsed_time_seconds)
        """
        return asyncio.run(self.chat_async(user_message))

    async def clear_session_async(self):
        """Clear the conversation history by creating a new session."""
        self.session = await self.session_service.create_session(
            app_name="stellaris_companion",
            user_id="player",
        )

    def clear_session(self):
        """Clear the conversation history (sync wrapper)."""
        asyncio.run(self.clear_session_async())


async def main_async():
    print("\n" + "=" * 60)
    print("STELLARIS ADVISOR - V2 ADK TOOLS")
    print("=" * 60)

    # Check for save file argument
    if len(sys.argv) < 2:
        print("\nUsage: python v2_adk_tools.py <save_file.sav>")
        sys.exit(1)

    save_path = sys.argv[1]
    if not Path(save_path).exists():
        print(f"Error: File not found: {save_path}")
        sys.exit(1)

    # Initialize advisor
    print(f"\nLoading save file: {save_path}")
    advisor = StellarisAdvisorADK(save_path)

    print(f"\nSave loaded:")
    print(f"  Empire: {advisor.metadata.get('name', 'Unknown')}")
    print(f"  Date: {advisor.metadata.get('date', 'Unknown')}")
    print(f"  Version: {advisor.metadata.get('version', 'Unknown')}")

    print("\n" + "=" * 60)
    print("Commands: /quit to exit, /clear to reset conversation")
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
            await advisor.clear_session_async()
            print("Conversation cleared.\n")
            continue

        # Get response
        response, elapsed = await advisor.chat_async(user_input)
        print(f"\nAdvisor ({elapsed:.2f}s): {response}\n")


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
