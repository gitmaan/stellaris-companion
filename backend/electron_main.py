#!/usr/bin/env python3
"""
Stellaris Companion Electron Backend - Entry Point
===================================================

Starts the FastAPI server for the Electron app with save watcher.

Usage:
    python backend/electron_main.py
    python backend/electron_main.py --help
    python backend/electron_main.py --port 8742 --host 127.0.0.1

Environment Variables:
    GOOGLE_API_KEY: Your Google API key for Gemini (required)
    STELLARIS_API_TOKEN: Bearer token for API authentication (required)
    STELLARIS_DB_PATH: Path to SQLite history DB (optional)
    STELLARIS_SAVE_PATH: Path to a specific save file to load (optional)

The server listens on 127.0.0.1:8742 by default (localhost only for security).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
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


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Stellaris Companion Electron Backend",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables:
  GOOGLE_API_KEY        Google API key for Gemini (required)
  STELLARIS_API_TOKEN   Bearer token for API authentication (required)
  STELLARIS_DB_PATH     Path to SQLite history DB (optional)
  STELLARIS_SAVE_PATH   Path to a specific save file (optional)

Examples:
  python backend/electron_main.py
  python backend/electron_main.py --port 8742
  STELLARIS_SAVE_PATH=/path/to/save.sav python backend/electron_main.py
""",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8742,
        help="Port to bind to (default: 8742)",
    )
    parser.add_argument(
        "--save-path",
        type=str,
        default=None,
        help="Path to save file to load (overrides STELLARIS_SAVE_PATH)",
    )
    return parser.parse_args()


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


def validate_environment() -> None:
    """Validate required environment variables.

    Raises:
        ValueError: If required environment variables are missing.
    """
    if not os.environ.get("GOOGLE_API_KEY"):
        raise ValueError(
            "GOOGLE_API_KEY environment variable not set.\n"
            "The Electron app should set this from the user's settings."
        )

    if not os.environ.get("STELLARIS_API_TOKEN"):
        raise ValueError(
            "STELLARIS_API_TOKEN environment variable not set.\n"
            "The Electron app should generate a random token per launch."
        )


def main() -> None:
    """Main entry point for the Electron backend."""
    args = parse_args()

    logger.info("Stellaris Companion Electron Backend starting...")

    # Validate environment
    try:
        validate_environment()
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    # Determine save path from args or environment
    save_path: Path | None = None
    if args.save_path:
        save_path = Path(args.save_path)
        if not save_path.exists():
            logger.warning(f"Specified save file not found: {save_path}")
            save_path = None
    elif os.environ.get("STELLARIS_SAVE_PATH"):
        save_path = Path(os.environ["STELLARIS_SAVE_PATH"])
        if not save_path.exists():
            logger.warning(f"STELLARIS_SAVE_PATH not found: {save_path}")
            save_path = None

    # If no specific save, try to find the most recent one
    if save_path is None:
        save_path = find_initial_save()

    if save_path:
        logger.info(f"Using save: {save_path}")
    else:
        logger.info("No save file found - server will start without a save loaded")

    # Import heavy modules after validation
    from backend.api.server import create_app
    from backend.core.companion import Companion
    from backend.core.database import get_default_db
    from backend.core.ingestion import IngestionManager
    from backend.core.save_watcher import SaveWatcher

    # Initialize history database
    try:
        db = get_default_db()
        logger.info(f"History DB ready: {db.path}")
    except Exception as e:
        logger.error(f"Failed to initialize history DB: {e}")
        sys.exit(1)

    # Initialize companion (Electron ingestion manager owns save loading + precompute).
    try:
        companion = Companion(save_path=None, auto_precompute=False)
        logger.info("Companion initialized (precompute managed by ingestion coordinator)")
    except Exception as e:
        logger.error(f"Failed to initialize companion: {e}")
        sys.exit(1)

    # Initialize ingestion coordinator (latest-only + cancelable parsing).
    ingestion = IngestionManager(companion=companion, db=db)
    ingestion.start()

    if save_path:
        logger.info(f"Initial save scheduled: {save_path.name}")
        ingestion.notify_save(save_path)

    # Initialize save watcher with callback to ingestion.notify_save
    def on_save_detected(path: Path) -> None:
        logger.info(f"New save detected: {path.name}")
        try:
            ingestion.notify_save(path)
        except Exception as e:
            logger.error(f"Failed to schedule ingestion: {e}")

    save_watcher = SaveWatcher(on_save_detected=on_save_detected)
    valid_paths = save_watcher.get_valid_watch_paths()
    if valid_paths:
        logger.info(f"Watching {len(valid_paths)} path(s) for new saves")
        save_watcher.start()
    else:
        logger.warning("No valid save paths found to watch")

    # Create FastAPI app and attach state
    app = create_app()
    app.state.companion = companion
    app.state.db = db
    app.state.ingestion = ingestion

    # Start uvicorn server
    import uvicorn

    logger.info(f"Starting server on {args.host}:{args.port}")

    try:
        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            log_level="info",
        )
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        # Clean up save watcher
        if save_watcher.is_running:
            save_watcher.stop()
        logger.info("Server stopped")


if __name__ == "__main__":
    main()
