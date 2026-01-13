"""
/history Command
===============

Show recent derived events for the current campaign/session.
"""

import logging
from pathlib import Path

import discord
from discord import app_commands

from backend.core.database import get_default_db
from backend.core.history import compute_save_id, extract_campaign_id_from_gamestate, extract_snapshot_metrics

logger = logging.getLogger(__name__)


def _format_event_line(game_date: str | None, summary: str) -> str:
    date = game_date or "Unknown date"
    return f"- `{date}` {summary}"


def setup(bot) -> None:
    """Register the /history command with the bot."""

    @bot.tree.command(
        name="history",
        description="Show recent changes (derived events) for the current campaign/session"
    )
    @app_commands.describe(limit="How many events to show (default 10, max 25)")
    async def history_command(interaction: discord.Interaction, limit: int = 10) -> None:
        if not bot.companion.is_loaded:
            await interaction.response.send_message(
                "No save file is currently loaded, so there is no history to show yet.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(thinking=True, ephemeral=True)

        try:
            db = get_default_db()

            briefing = getattr(bot.companion, "_current_snapshot", None) or {}
            metrics = extract_snapshot_metrics(briefing) if isinstance(briefing, dict) else {}

            campaign_id = None
            if bot.companion.extractor and getattr(bot.companion.extractor, "gamestate", None):
                campaign_id = extract_campaign_id_from_gamestate(bot.companion.extractor.gamestate)

            save_id = compute_save_id(
                campaign_id=campaign_id,
                player_id=bot.companion.extractor.get_player_empire_id() if bot.companion.extractor else None,
                empire_name=metrics.get("empire_name") if isinstance(metrics, dict) else None,
                save_path=bot.companion.save_path if isinstance(bot.companion.save_path, Path) else None,
            )

            session_id = db.get_active_or_latest_session_id(save_id=save_id)
            if not session_id:
                await interaction.followup.send("No sessions found yet for this campaign.")
                return

            events = db.get_recent_events(session_id=session_id, limit=min(max(limit, 1), 25))
            stats = db.get_session_snapshot_stats(session_id)

            header = (
                f"Session `{session_id}`\n"
                f"Snapshots: {stats.get('snapshot_count', 0)}"
            )
            first_date = stats.get("first_game_date")
            last_date = stats.get("last_game_date")
            if first_date and last_date:
                header += f"\nDate range: {first_date} → {last_date}"

            if not events:
                await interaction.followup.send(header + "\n\nNo derived events yet. (Play a bit longer or wait for more autosaves.)")
                return

            # Events are returned newest-first; display oldest-first for readability.
            lines = [_format_event_line(e.get("game_date"), e.get("summary", "")) for e in reversed(events)]
            body = "\n".join(lines)
            text = header + "\n\nRecent events:\n" + body

            # Discord message limit; trim if needed.
            if len(text) > 1900:
                # Keep header and last N lines that fit.
                kept = []
                base = header + "\n\nRecent events:\n"
                for line in reversed(lines):
                    candidate = base + "\n".join(reversed(kept + [line]))
                    if len(candidate) > 1900:
                        break
                    kept.append(line)
                kept.reverse()
                text = base + "\n".join(kept) + "\n\n*(Truncated)*"

            await interaction.followup.send(text)

        except Exception as e:
            logger.error(f"Error in /history command: {e}")
            await interaction.followup.send(f"An error occurred while retrieving history: {str(e)}")

    logger.info("/history command registered")

