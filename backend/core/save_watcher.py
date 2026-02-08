"""
Save Watcher for Stellaris Companion
====================================

Watches the Stellaris save directory for new .sav files using watchdog.
Notifies callbacks when saves are created or modified.
"""

import asyncio
import logging
import sys
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stellaris_companion.save_loader import find_most_recent_save, get_platform_save_paths

logger = logging.getLogger(__name__)


class SaveFileHandler(FileSystemEventHandler):
    """Handler for save file system events."""

    def __init__(
        self,
        on_save_detected: Callable[[Path], None] | None = None,
        on_save_detected_async: Callable[[Path], Awaitable[None]] | None = None,
        loop: asyncio.AbstractEventLoop | None = None,
        debounce_seconds: float = 2.0,
    ):
        """Initialize the handler.

        Args:
            on_save_detected: Sync callback when a new save is detected
            on_save_detected_async: Async callback when a new save is detected
            loop: Event loop for async callbacks
            debounce_seconds: Minimum time between callbacks for same file
        """
        super().__init__()
        self.on_save_detected = on_save_detected
        self.on_save_detected_async = on_save_detected_async
        self.loop = loop
        self.debounce_seconds = debounce_seconds
        self._last_event: dict[str, float] = {}

    def _should_process(self, path: Path) -> bool:
        """Check if we should process this event (debouncing)."""
        path_str = str(path)
        now = datetime.now().timestamp()

        if path_str in self._last_event:
            elapsed = now - self._last_event[path_str]
            if elapsed < self.debounce_seconds:
                return False

        self._last_event[path_str] = now
        return True

    def _handle_save_event(self, path: Path) -> None:
        """Handle a detected save file event."""
        if not self._should_process(path):
            return

        logger.info(f"Save file detected: {path.name}")

        # Call sync callback if provided
        if self.on_save_detected:
            try:
                self.on_save_detected(path)
            except Exception as e:
                logger.error(f"Error in sync callback: {e}")

        # Call async callback if provided
        if self.on_save_detected_async and self.loop:
            try:
                asyncio.run_coroutine_threadsafe(self.on_save_detected_async(path), self.loop)
            except Exception as e:
                logger.error(f"Error scheduling async callback: {e}")

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file creation events."""
        if event.is_directory:
            return

        path = Path(event.src_path)
        if path.suffix.lower() == ".sav":
            self._handle_save_event(path)

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modification events."""
        if event.is_directory:
            return

        path = Path(event.src_path)
        if path.suffix.lower() == ".sav":
            self._handle_save_event(path)


class SaveWatcher:
    """Watches for Stellaris save files and notifies on changes."""

    def __init__(
        self,
        watch_paths: list[Path] | None = None,
        on_save_detected: Callable[[Path], None] | None = None,
        on_save_detected_async: Callable[[Path], Awaitable[None]] | None = None,
        debounce_seconds: float = 2.0,
    ):
        """Initialize the save watcher.

        Args:
            watch_paths: Paths to watch. If None, uses platform defaults.
            on_save_detected: Sync callback when a new save is detected
            on_save_detected_async: Async callback when a new save is detected
            debounce_seconds: Minimum time between callbacks for same file
        """
        self.watch_paths = watch_paths or get_platform_save_paths()
        self.on_save_detected = on_save_detected
        self.on_save_detected_async = on_save_detected_async
        self.debounce_seconds = debounce_seconds

        self._observer: Observer | None = None
        self._running = False
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def is_running(self) -> bool:
        """Check if the watcher is running."""
        return self._running

    def get_valid_watch_paths(self) -> list[Path]:
        """Get list of watch paths that actually exist."""
        return [p for p in self.watch_paths if p.exists()]

    def start(self, loop: asyncio.AbstractEventLoop | None = None) -> bool:
        """Start watching for save files.

        Args:
            loop: Event loop for async callbacks

        Returns:
            True if started successfully, False if no valid paths to watch
        """
        if self._running:
            logger.warning("Save watcher already running")
            return True

        valid_paths = self.get_valid_watch_paths()
        if not valid_paths:
            logger.warning("No valid save paths to watch")
            return False

        self._loop = loop

        # Create event handler
        handler = SaveFileHandler(
            on_save_detected=self.on_save_detected,
            on_save_detected_async=self.on_save_detected_async,
            loop=self._loop,
            debounce_seconds=self.debounce_seconds,
        )

        # Create and start observer
        self._observer = Observer()

        for path in valid_paths:
            logger.info(f"Watching for saves in: {path}")
            self._observer.schedule(handler, str(path), recursive=True)

        self._observer.start()
        self._running = True

        return True

    def stop(self) -> None:
        """Stop watching for save files."""
        if not self._running:
            return

        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5.0)
            self._observer = None

        self._running = False
        logger.info("Save watcher stopped")

    def find_latest_save(self) -> Path | None:
        """Find the most recent save file.

        Returns:
            Path to the most recent save, or None if not found
        """
        return find_most_recent_save(self.watch_paths)


# Example usage and testing
if __name__ == "__main__":
    import time

    logging.basicConfig(level=logging.INFO)

    def on_save(path: Path):
        print(f"New save detected: {path}")

    watcher = SaveWatcher(on_save_detected=on_save)

    print("Starting save watcher...")
    print(f"Valid paths: {watcher.get_valid_watch_paths()}")

    if watcher.start():
        print("Watching for saves. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping...")
            watcher.stop()
    else:
        print("No valid paths to watch")
