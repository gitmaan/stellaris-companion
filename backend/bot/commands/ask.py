"""
/ask Command
=============

Slash command to ask the Stellaris advisor a question.
Uses Gemini with tool access to provide intelligent responses.
"""

import asyncio
import logging
import discord
from discord import app_commands

from backend.core.database import get_default_db
from backend.core.history_context import build_history_context_for_companion, should_include_history

logger = logging.getLogger(__name__)


def split_response(text: str, max_length: int = 1900) -> list[str]:
    """Split a long response into chunks that fit Discord's limit.

    Tries to split at paragraph breaks, then sentence breaks.

    Args:
        text: The text to split
        max_length: Maximum length per chunk

    Returns:
        List of text chunks
    """
    if len(text) <= max_length:
        return [text]

    chunks = []
    remaining = text

    while len(remaining) > max_length:
        break_at = max_length

        # Try paragraph break first
        para_break = remaining.rfind('\n\n', 0, max_length)
        if para_break > max_length * 0.3:
            break_at = para_break + 2

        # Try single newline
        elif (line_break := remaining.rfind('\n', 0, max_length)) > max_length * 0.3:
            break_at = line_break + 1

        # Try sentence break
        else:
            for punct in ['. ', '! ', '? ']:
                sent_break = remaining.rfind(punct, 0, max_length)
                if sent_break > max_length * 0.3:
                    break_at = sent_break + 2
                    break

        chunks.append(remaining[:break_at].strip())
        remaining = remaining[break_at:].strip()

    if remaining:
        chunks.append(remaining)

    return chunks


def setup(bot) -> None:
    """Register the /ask command with the bot.

    Args:
        bot: The StellarisBot instance
    """

    @bot.tree.command(
        name="ask",
        description="Ask your strategic advisor a question about your empire"
    )
    @app_commands.describe(
        question="Your question for the advisor (e.g., 'How is my economy?' or 'Should I declare war?')"
    )
    async def ask_command(interaction: discord.Interaction, question: str) -> None:
        """Handle the /ask command.

        Args:
            interaction: The Discord interaction
            question: The user's question
        """
        # Check if save is loaded
        if not bot.companion.is_loaded:
            await interaction.response.send_message(
                "No save file is currently loaded. Please wait for a save to be detected "
                "or restart the bot with a valid save file.",
                ephemeral=True
            )
            return

        # Defer response since LLM calls can take a while
        await interaction.response.defer(thinking=True)

        try:
            session_key = f"{interaction.user.id}:{interaction.channel_id}"

            # Phase 4: /ask uses full precompute (no tools) with sliding-window history.
            # ALL blocking operations (history context + LLM call) must be in to_thread
            # to avoid blocking Discord's event loop and causing heartbeat timeouts.
            def _run_ask():
                history_context = None
                if should_include_history(question):
                    try:
                        db = get_default_db()
                        history_context = build_history_context_for_companion(db=db, companion=bot.companion)
                    except Exception:
                        history_context = None
                return bot.companion.ask_precomputed(
                    question,
                    session_key,
                    history_context,
                )

            response_text, elapsed = await asyncio.to_thread(_run_ask)

            # Split into multiple messages if needed
            chunks = split_response(response_text)

            # Send chunks
            for i, chunk in enumerate(chunks):
                if i == len(chunks) - 1:
                    # Last chunk - add timing footer
                    footer = f"\n\n*Response time: {elapsed:.1f}s*"
                    if len(chunk) + len(footer) <= 2000:
                        chunk = chunk + footer
                await interaction.followup.send(chunk)

        except Exception as e:
            logger.error(f"Error in /ask command: {e}")
            await interaction.followup.send(
                f"An error occurred while processing your question: {str(e)}",
                ephemeral=True
            )

    logger.info("/ask command registered")
