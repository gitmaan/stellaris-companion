"""
/recap Command
==============

Generate a session recap - either a quick summary or a dramatic LLM narrative.
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
    """Register the /recap command with the bot."""

    @bot.tree.command(name="recap", description="Get a recap of your session's recent events")
    @app_commands.describe(
        style='Recap style: "summary" (fast) or "dramatic" (LLM-powered narrative)'
    )
    @app_commands.choices(
        style=[
            app_commands.Choice(name="Summary (fast)", value="summary"),
            app_commands.Choice(name="Dramatic (LLM narrative)", value="dramatic"),
        ]
    )
    async def recap_command(interaction: discord.Interaction, style: str = "summary") -> None:
        """Generate a recap for the current session."""
        if not bot.companion.is_loaded:
            await interaction.response.send_message(
                "No save file is currently loaded. Please wait for a save to be detected.",
                ephemeral=True,
            )
            return

        # Defer - dramatic style uses LLM which can take a while
        await interaction.response.defer(thinking=True)

        try:

            def _generate_recap():
                """Run recap generation in a thread."""
                from backend.core.chronicle import ChronicleGenerator

                db = get_default_db()

                # Get session ID for current campaign
                briefing = getattr(bot.companion, "_current_snapshot", None) or {}
                metrics = extract_snapshot_metrics(briefing) if isinstance(briefing, dict) else {}

                campaign_id = None
                if bot.companion.extractor and getattr(bot.companion.extractor, "gamestate", None):
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
                    empire_name=(metrics.get("empire_name") if isinstance(metrics, dict) else None),
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
                result = generator.generate_recap(
                    session_id=session_id,
                    style=style,
                )
                return result, None

            result, error = await asyncio.to_thread(_generate_recap)

            if error:
                await interaction.followup.send(error, ephemeral=True)
                return

            recap_text = result["recap"]
            recap_style = result.get("style", style)
            events_summarized = result.get("events_summarized", 0)

            # Build footer
            if recap_style == "dramatic":
                footer = f"\n\n*Dramatic recap of {events_summarized} events*"
            else:
                footer = ""

            # Truncate if needed
            full_text = recap_text + footer
            if len(full_text) > 2000:
                # Truncate the recap, preserving footer
                max_recap = 2000 - len(footer) - 20
                recap_text = recap_text[:max_recap] + "..."
                full_text = recap_text + footer

            await interaction.followup.send(full_text)

        except Exception as e:
            logger.error(f"Error in /recap command: {e}")
            await interaction.followup.send(
                f"An error occurred while generating the recap: {str(e)}",
                ephemeral=True,
            )

    logger.info("/recap command registered")
