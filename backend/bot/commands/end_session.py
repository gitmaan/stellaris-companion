"""
/end_session Command
===================

Manually end the current history session (Phase 3 Milestone 2).

This avoids relying solely on "game closed" detection heuristics.
"""

import logging
from pathlib import Path

import discord

from backend.core.database import get_default_db
from backend.core.reporting import build_session_report_text
from backend.core.history import (
    compute_save_id,
    extract_campaign_id_from_gamestate,
    extract_snapshot_metrics,
    record_snapshot_from_companion,
)

logger = logging.getLogger(__name__)


def setup(bot) -> None:
    """Register the /end_session command with the bot.

    Args:
        bot: The StellarisBot instance
    """

    @bot.tree.command(
        name="end_session",
        description="Manually end the current session (for end-of-session report/history boundaries)"
    )
    async def end_session_command(interaction: discord.Interaction) -> None:
        # Check if save is loaded
        if not bot.companion.is_loaded:
            await interaction.response.send_message(
                "No save file is currently loaded, so there is no active session to end.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(thinking=True, ephemeral=True)

        try:
            db = get_default_db()

            # Ensure we have a latest snapshot recorded before ending the session.
            try:
                briefing = getattr(bot.companion, "_current_snapshot", None) or bot.companion.get_snapshot()
                record_snapshot_from_companion(
                    db=db,
                    save_path=bot.companion.save_path,
                    save_hash=getattr(bot.companion, "_save_hash", None),
                    gamestate=getattr(bot.companion.extractor, "gamestate", None) if bot.companion.extractor else None,
                    player_id=bot.companion.extractor.get_player_empire_id() if bot.companion.extractor else None,
                    briefing=briefing,
                )
            except Exception as e:
                logger.warning(f"/end_session: failed to record final snapshot: {e}")

            # Compute save_id to find active session(s)
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

            active_session_id = db.get_active_session_id(save_id)
            if not active_session_id:
                await interaction.followup.send(
                    "No active session found to end. (It may have already ended or history DB is empty.)",
                )
                return

            ended = db.end_active_sessions_for_save(save_id=save_id)
            stats = db.get_session_snapshot_stats(active_session_id)

            date_range = ""
            first_date = stats.get("first_game_date")
            last_date = stats.get("last_game_date")
            if first_date and last_date:
                date_range = f"{first_date} → {last_date}"

            msg = (
                f"Ended session `{active_session_id}`.\n"
                f"Snapshots: {stats.get('snapshot_count', 0)}"
                + (f"\nDate range: {date_range}" if date_range else "")
            )
            if len(ended) > 1:
                msg += f"\n(Ended {len(ended)} active sessions for this save source.)"

            await interaction.followup.send(msg)

            # Post deterministic session report (Phase 3 Milestone 4)
            try:
                report = build_session_report_text(db=db, session_id=active_session_id, max_events=20)
                if bot.notification_channel_id:
                    channel = bot.get_channel(bot.notification_channel_id)
                    if channel and isinstance(channel, discord.TextChannel):
                        # Keep it within Discord limits (split if needed)
                        for chunk in _split_chunks(report, max_len=1900):
                            await channel.send(chunk)
                else:
                    for chunk in _split_chunks(report, max_len=1900):
                        await interaction.followup.send(chunk)
            except Exception as e:
                logger.warning(f"/end_session: failed to build/post session report: {e}")

        except Exception as e:
            logger.error(f"Error in /end_session command: {e}")
            await interaction.followup.send(
                f"An error occurred while ending the session: {str(e)}",
            )

    logger.info("/end_session command registered")


def _split_chunks(text: str, max_len: int = 1900) -> list[str]:
    if len(text) <= max_len:
        return [text]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > max_len:
        cut = remaining.rfind("\n", 0, max_len)
        if cut < max_len * 0.5:
            cut = max_len
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks
