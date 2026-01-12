"""
/briefing Command
=================

Slash command to get a full strategic briefing from the advisor.
This uses the Gemini LLM to provide comprehensive analysis.
"""

import asyncio
import logging
import discord
from discord import app_commands

logger = logging.getLogger(__name__)

# Import truncate function from parent
from backend.bot.discord_bot import truncate_response


def setup(bot) -> None:
    """Register the /briefing command with the bot.

    Args:
        bot: The StellarisBot instance
    """

    @bot.tree.command(
        name="briefing",
        description="Get a full strategic briefing from your advisor"
    )
    async def briefing_command(interaction: discord.Interaction) -> None:
        """Handle the /briefing command.

        Args:
            interaction: The Discord interaction
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
            # Get briefing from companion (run in thread to avoid blocking event loop)
            response_text, elapsed = await asyncio.to_thread(bot.companion.get_briefing)

            # Check if response is very long - might need to split
            if len(response_text) > 4000:
                # Split into multiple messages
                chunks = split_response(response_text)

                for i, chunk in enumerate(chunks):
                    if i == 0:
                        await interaction.followup.send(chunk)
                    else:
                        await interaction.followup.send(chunk)

                # Send timing as final message
                await interaction.followup.send(f"*Briefing completed in {elapsed:.1f}s*")

            else:
                # Truncate if necessary
                response_text = truncate_response(response_text)

                # Add timing info
                footer = f"\n\n*Briefing generated in {elapsed:.1f}s*"

                if len(response_text) + len(footer) > 2000:
                    response_text = truncate_response(response_text, 2000 - len(footer) - 10)

                await interaction.followup.send(response_text + footer)

        except Exception as e:
            logger.error(f"Error in /briefing command: {e}")
            await interaction.followup.send(
                f"An error occurred while generating the briefing: {str(e)}",
                ephemeral=True
            )

    logger.info("/briefing command registered")


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
        # Find a good break point
        break_at = max_length

        # Try paragraph break first
        para_break = remaining.rfind('\n\n', 0, max_length)
        if para_break > max_length * 0.3:
            break_at = para_break + 2  # Include the newlines

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

        # Add chunk
        chunks.append(remaining[:break_at].strip())
        remaining = remaining[break_at:].strip()

    # Add final chunk
    if remaining:
        chunks.append(remaining)

    return chunks
