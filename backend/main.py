#!/usr/bin/env python3
"""
Stellaris Companion Discord Bot - Entry Point
==============================================

Starts the Discord bot with the save watcher.

Usage:
    python backend/main.py [save_file.sav]

Environment Variables:
    DISCORD_BOT_TOKEN: Your Discord bot token (required)
    GOOGLE_API_KEY: Your Google API key for Gemini (required)
    NOTIFICATION_CHANNEL_ID: Discord channel ID for save notifications (optional)
    STELLARIS_DB_PATH: Path to SQLite history DB (optional; Phase 3)

If no save file is specified, the bot will try to find the most recent save
in the standard Stellaris save locations.
"""

import os
import sys
import asyncio
import logging
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass  # dotenv not installed, rely on environment variables

from backend.core.companion import Companion
from backend.core.database import get_default_db
from backend.core.history import record_snapshot_from_companion
from backend.core.save_watcher import SaveWatcher
from backend.bot.discord_bot import create_bot

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def get_discord_token() -> str:
    """Get the Discord bot token from environment.

    Returns:
        The Discord bot token

    Raises:
        ValueError: If the token is not set
    """
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        raise ValueError(
            "DISCORD_BOT_TOKEN environment variable not set.\n"
            "Add it to your .env file:\n"
            "  DISCORD_BOT_TOKEN=your_token_here"
        )
    return token


def get_notification_channel() -> int | None:
    """Get the notification channel ID from environment.

    Returns:
        Channel ID or None if not set
    """
    channel_id = os.environ.get("NOTIFICATION_CHANNEL_ID")
    if channel_id:
        try:
            return int(channel_id)
        except ValueError:
            logger.warning(f"Invalid NOTIFICATION_CHANNEL_ID: {channel_id}")
    return None


def find_initial_save() -> Path | None:
    """Find an initial save file to load.

    Returns:
        Path to a save file, or None if not found
    """
    from save_loader import find_most_recent_save

    save = find_most_recent_save()
    if save:
        logger.info(f"Found save file: {save.name}")
    return save


def main():
    """Main entry point."""
    print("\n" + "=" * 60)
    print("STELLARIS COMPANION - DISCORD BOT")
    print("=" * 60 + "\n")

    # Check for save file argument
    save_path = None
    if len(sys.argv) >= 2:
        save_path = Path(sys.argv[1])
        if not save_path.exists():
            logger.error(f"Save file not found: {save_path}")
            sys.exit(1)
        logger.info(f"Using specified save: {save_path}")
    else:
        save_path = find_initial_save()
        if save_path:
            logger.info(f"Using most recent save: {save_path.name}")
        else:
            logger.warning("No save file found - bot will start without a save loaded")
            logger.info("The bot will load a save when one is detected by the watcher")

    # Get Discord token
    try:
        discord_token = get_discord_token()
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    # Check Google API key
    if not os.environ.get("GOOGLE_API_KEY"):
        logger.error(
            "GOOGLE_API_KEY environment variable not set.\n"
            "Add it to your .env file:\n"
            "  GOOGLE_API_KEY=your_key_here"
        )
        sys.exit(1)

    # Get notification channel
    notification_channel = get_notification_channel()
    if notification_channel:
        logger.info(f"Save notifications will be sent to channel: {notification_channel}")

    # Initialize history database (Phase 3 foundation)
    try:
        db = get_default_db()
        logger.info(f"History DB ready: {db.path}")
    except Exception as e:
        logger.error(f"Failed to initialize history DB: {e}")
        sys.exit(1)

    # Initialize companion
    try:
        companion = Companion(save_path=save_path)
        if companion.is_loaded:
            logger.info(f"Companion loaded: {companion.metadata.get('name', 'Unknown')}")
            logger.info(f"Personality: {companion.personality_summary}")
            try:
                inserted, snapshot_id, session_id = record_snapshot_from_companion(
                    db=db,
                    save_path=companion.save_path,
                    save_hash=getattr(companion, "_save_hash", None),
                    briefing=getattr(companion, "_current_snapshot", None) or companion.get_snapshot(),
                )
                if inserted:
                    logger.info(f"Recorded initial snapshot (session={session_id}, snapshot_id={snapshot_id})")
                else:
                    logger.info(f"Initial snapshot already recorded (session={session_id})")
            except Exception as e:
                logger.warning(f"Failed to record initial snapshot: {e}")
    except Exception as e:
        logger.error(f"Failed to initialize companion: {e}")
        sys.exit(1)

    # Initialize save watcher
    save_watcher = SaveWatcher()
    valid_paths = save_watcher.get_valid_watch_paths()
    if valid_paths:
        logger.info(f"Will watch {len(valid_paths)} path(s) for new saves")
    else:
        logger.warning("No valid save paths found to watch")

    # Create and run bot
    bot = create_bot(
        companion=companion,
        save_watcher=save_watcher,
        notification_channel_id=notification_channel,
    )

    print("\n" + "-" * 60)
    print("Starting Discord bot...")
    print("Press Ctrl+C to stop")
    print("-" * 60 + "\n")

    try:
        bot.run(discord_token, log_handler=None)  # Use our logging config
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Bot error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
