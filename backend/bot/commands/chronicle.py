"""
/chronicle Command
==================

Generate a full LLM-powered chronicle of empire history.
Produces dramatic, multi-chapter narratives in the style of Stellaris Invicta.
"""

import asyncio
import logging
from pathlib import Path

import discord
from discord import app_commands

from backend.core.database import get_default_db
from backend.core.history import (
    compute_save_id,
    extract_campaign_id_from_gamestate,
    extract_snapshot_metrics,
)

logger = logging.getLogger(__name__)


def setup(bot) -> None:
    """Register the /chronicle command with the bot."""

    @bot.tree.command(
        name="chronicle",
        description="Generate a dramatic chronicle of your empire's history",
    )
    @app_commands.describe(
        force_refresh="Generate a new chronicle even if one is cached"
    )
    async def chronicle_command(
        interaction: discord.Interaction, force_refresh: bool = False
    ) -> None:
        """Generate a full chronicle for the current session."""
        if not bot.companion.is_loaded:
            await interaction.response.send_message(
                "No save file is currently loaded. Please wait for a save to be detected.",
                ephemeral=True,
            )
            return

        # Defer response since LLM calls can take a while
        await interaction.response.defer(thinking=True)

        try:

            def _generate_chronicle():
                """Run chronicle generation in a thread."""
                from backend.core.chronicle import ChronicleGenerator

                db = get_default_db()

                # Get session ID for current campaign
                briefing = getattr(bot.companion, "_current_snapshot", None) or {}
                metrics = (
                    extract_snapshot_metrics(briefing)
                    if isinstance(briefing, dict)
                    else {}
                )

                campaign_id = None
                if bot.companion.extractor and getattr(
                    bot.companion.extractor, "gamestate", None
                ):
                    campaign_id = extract_campaign_id_from_gamestate(
                        bot.companion.extractor.gamestate
                    )

                save_id = compute_save_id(
                    campaign_id=campaign_id,
                    player_id=(
                        bot.companion.extractor.get_player_empire_id()
                        if bot.companion.extractor
                        else None
                    ),
                    empire_name=(
                        metrics.get("empire_name")
                        if isinstance(metrics, dict)
                        else None
                    ),
                    save_path=(
                        bot.companion.save_path
                        if isinstance(bot.companion.save_path, Path)
                        else None
                    ),
                )

                session_id = db.get_active_or_latest_session_id(save_id=save_id)
                if not session_id:
                    return None, "No session found for this campaign."

                generator = ChronicleGenerator(db=db)
                result = generator.generate_chronicle(
                    session_id=session_id,
                    force_refresh=force_refresh,
                )
                return result, None

            result, error = await asyncio.to_thread(_generate_chronicle)

            if error:
                await interaction.followup.send(error, ephemeral=True)
                return

            chronicle_text = result["chronicle"]
            cached = result.get("cached", False)
            event_count = result.get("event_count", 0)

            # Build footer
            cache_status = "cached" if cached else "newly generated"
            footer = f"\n\n*Chronicle {cache_status} from {event_count} events*"

            # Split long chronicles into multiple messages
            if len(chronicle_text) + len(footer) > 1900:
                chunks = _split_chronicle(chronicle_text)
                for i, chunk in enumerate(chunks):
                    if i == len(chunks) - 1:
                        # Add footer to last chunk
                        if len(chunk) + len(footer) <= 2000:
                            chunk += footer
                    await interaction.followup.send(chunk)
            else:
                await interaction.followup.send(chronicle_text + footer)

        except Exception as e:
            logger.error(f"Error in /chronicle command: {e}")
            await interaction.followup.send(
                f"An error occurred while generating the chronicle: {str(e)}",
                ephemeral=True,
            )

    logger.info("/chronicle command registered")


def _split_chronicle(text: str, max_length: int = 1900) -> list[str]:
    """Split chronicle into Discord-friendly chunks.

    Tries to split at chapter boundaries, then paragraphs, then sentences.
    """
    if len(text) <= max_length:
        return [text]

    chunks = []
    remaining = text

    while len(remaining) > max_length:
        break_at = max_length

        # Try to break at chapter boundary (### or ** header)
        for marker in ["\n### ", "\n**CHAPTER", "\n#### "]:
            idx = remaining.rfind(marker, 0, max_length)
            if idx > max_length * 0.3:
                break_at = idx
                break
        else:
            # Try paragraph break
            para_break = remaining.rfind("\n\n", 0, max_length)
            if para_break > max_length * 0.3:
                break_at = para_break
            else:
                # Try single newline
                line_break = remaining.rfind("\n", 0, max_length)
                if line_break > max_length * 0.3:
                    break_at = line_break
                else:
                    # Try sentence break
                    for punct in [". ", "! ", "? "]:
                        sent_break = remaining.rfind(punct, 0, max_length)
                        if sent_break > max_length * 0.3:
                            break_at = sent_break + 2
                            break

        chunks.append(remaining[:break_at].strip())
        remaining = remaining[break_at:].strip()

    if remaining:
        chunks.append(remaining)

    return chunks
