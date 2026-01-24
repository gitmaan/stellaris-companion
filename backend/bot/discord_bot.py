"""
Stellaris Companion Discord Bot
===============================

Main Discord bot class with slash commands.
Uses discord.py with app_commands for slash command support.
"""

import asyncio
import sys
import logging
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.companion import Companion
from backend.core.save_watcher import SaveWatcher

logger = logging.getLogger(__name__)

# Discord message character limit
DISCORD_CHAR_LIMIT = 2000


def truncate_response(text: str, max_length: int = DISCORD_CHAR_LIMIT - 50) -> str:
    """Truncate a response to fit Discord's character limit.

    Args:
        text: The text to truncate
        max_length: Maximum length (default leaves room for truncation notice)

    Returns:
        Truncated text with indicator if needed
    """
    if len(text) <= max_length:
        return text

    # Find a good break point (end of sentence or paragraph)
    truncate_at = max_length - 30  # Leave room for truncation notice

    # Try to find a paragraph break
    para_break = text.rfind("\n\n", 0, truncate_at)
    if para_break > truncate_at * 0.5:  # Only use if we keep at least half
        truncate_at = para_break

    # Or try a sentence break
    else:
        for punct in [". ", "! ", "? "]:
            sent_break = text.rfind(punct, 0, truncate_at)
            if sent_break > truncate_at * 0.5:
                truncate_at = sent_break + 1
                break

    return text[:truncate_at] + "\n\n*[Response truncated due to length]*"


class StellarisBot(commands.Bot):
    """Discord bot for Stellaris Companion."""

    def __init__(
        self,
        companion: Companion,
        save_watcher: SaveWatcher | None = None,
        notification_channel_id: int | None = None,
        **kwargs,
    ):
        """Initialize the bot.

        Args:
            companion: The Stellaris companion instance
            save_watcher: Optional save watcher for auto-reload
            notification_channel_id: Optional channel ID for save notifications
            **kwargs: Additional arguments passed to commands.Bot
        """
        # Set up intents
        intents = discord.Intents.default()
        intents.message_content = True  # Needed for potential future on_message

        super().__init__(
            command_prefix="!",  # Fallback prefix (we use slash commands)
            intents=intents,
            **kwargs,
        )

        self.companion = companion
        self.save_watcher = save_watcher
        self.notification_channel_id = notification_channel_id

        # Track synced status
        self._synced = False

    async def setup_hook(self) -> None:
        """Called when the bot is starting up."""
        # Import and register commands
        from backend.bot.commands import (
            setup_ask,
            setup_status,
            setup_briefing,
            setup_end_session,
            setup_history,
            setup_chronicle,
            setup_recap,
        )

        setup_ask(self)
        setup_status(self)
        setup_briefing(self)
        setup_end_session(self)
        setup_history(self)
        setup_chronicle(self)
        setup_recap(self)

        logger.info("Commands registered")

    async def on_ready(self) -> None:
        """Called when the bot is connected and ready."""
        logger.info(f"Bot connected as {self.user}")
        logger.info(f"Bot ID: {self.user.id}")
        logger.info(f"Connected to {len(self.guilds)} guild(s)")

        # Sync commands on first ready
        if not self._synced:
            try:
                synced = await self.tree.sync()
                logger.info(f"Synced {len(synced)} command(s)")
                self._synced = True
            except Exception as e:
                logger.error(f"Failed to sync commands: {e}")

        # Start save watcher if configured
        if self.save_watcher and not self.save_watcher.is_running:
            self.save_watcher.on_save_detected_async = self._on_save_detected
            if self.save_watcher.start(loop=self.loop):
                logger.info("Save watcher started")
            else:
                logger.warning("Failed to start save watcher")

        # Log status
        if self.companion.is_loaded:
            logger.info(
                f"Loaded save: {self.companion.metadata.get('name', 'Unknown')}"
            )
        else:
            logger.warning("No save file loaded")

    async def _on_save_detected(self, save_path: Path) -> None:
        """Handle a new save file being detected.

        Args:
            save_path: Path to the new save file
        """
        logger.info(f"New save detected: {save_path.name}")

        try:
            # Reload quickly, then start background precompute (handled inside Companion).
            identity_changed = await asyncio.to_thread(
                self.companion.reload_save, new_path=save_path
            )

            message = f"Save file updated: **{save_path.name}**\n"
            message += f"Empire: {self.companion.metadata.get('name', 'Unknown')}\n"
            message += f"Date: {self.companion.metadata.get('date', 'Unknown')}"

            if identity_changed:
                message += "\n*Empire identity changed - personality updated*"

            # Send notification if channel configured
            if self.notification_channel_id:
                channel = self.get_channel(self.notification_channel_id)
                if channel and isinstance(channel, discord.TextChannel):
                    await channel.send(message)

        except Exception as e:
            logger.error(f"Error reloading save: {e}")

    async def on_disconnect(self) -> None:
        """Called when the bot disconnects."""
        logger.info("Bot disconnected")

    async def close(self) -> None:
        """Clean up when the bot is closing."""
        # Stop save watcher
        if self.save_watcher and self.save_watcher.is_running:
            self.save_watcher.stop()

        await super().close()


def create_bot(
    companion: Companion,
    save_watcher: SaveWatcher | None = None,
    notification_channel_id: int | None = None,
) -> StellarisBot:
    """Factory function to create a configured bot instance.

    Args:
        companion: The Stellaris companion instance
        save_watcher: Optional save watcher for auto-reload
        notification_channel_id: Optional channel ID for save notifications

    Returns:
        Configured StellarisBot instance
    """
    return StellarisBot(
        companion=companion,
        save_watcher=save_watcher,
        notification_channel_id=notification_channel_id,
    )
