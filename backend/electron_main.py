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
    STELLARIS_SAVE_DIR: Path to a Stellaris "save games" directory to search/watch (optional)

The server listens on 127.0.0.1:8742 by default (localhost only for security).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Add project root to path for imports when running as a script.
# When invoked as a module (`python -m backend.electron_main`), this is unnecessary.
PROJECT_ROOT = Path(__file__).parent.parent
if __package__ is None and str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables from .env file
try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass  # dotenv not installed, rely on environment variables


def configure_logging() -> None:
    """Configure console + rotating file logging (when STELLARIS_LOG_DIR is set)."""
    level_name = os.environ.get("STELLARIS_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    handlers = [logging.StreamHandler()]

    log_dir_raw = os.environ.get("STELLARIS_LOG_DIR")
    if log_dir_raw:
        log_dir = Path(log_dir_raw)
        log_dir.mkdir(parents=True, exist_ok=True)
        logfile = log_dir / "stellaris-companion-backend.log"
        handlers.append(
            RotatingFileHandler(
                logfile,
                maxBytes=5_000_000,
                backupCount=3,
                encoding="utf-8",
            )
        )

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )


configure_logging()
logger = logging.getLogger(__name__)

_WINDOWS_JOB_HANDLE: int | None = None


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
  STELLARIS_SAVE_DIR    Path to a Stellaris "save games" directory (optional)

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
    parser.add_argument(
        "--parent-pid",
        type=int,
        default=None,
        help="Parent process PID (when launched by Electron). If the parent exits, this backend will exit too.",
    )
    return parser.parse_args()


def _enable_windows_kill_on_close_job() -> None:
    """Ensure backend subprocess tree dies if this process is terminated on Windows.

    On Windows, terminating the parent process does not necessarily terminate its children.
    A Job Object with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE provides tree cleanup without
    shelling out to taskkill.
    """
    global _WINDOWS_JOB_HANDLE
    if os.name != "nt":
        return

    try:
        import ctypes
        import ctypes.wintypes as wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        CreateJobObjectW = kernel32.CreateJobObjectW
        CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        CreateJobObjectW.restype = wintypes.HANDLE

        SetInformationJobObject = kernel32.SetInformationJobObject
        SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            wintypes.INT,
            wintypes.LPVOID,
            wintypes.DWORD,
        ]
        SetInformationJobObject.restype = wintypes.BOOL

        AssignProcessToJobObject = kernel32.AssignProcessToJobObject
        AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        AssignProcessToJobObject.restype = wintypes.BOOL

        GetCurrentProcess = kernel32.GetCurrentProcess
        GetCurrentProcess.argtypes = []
        GetCurrentProcess.restype = wintypes.HANDLE

        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
        JobObjectExtendedLimitInformation = 9

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
                ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", wintypes.ULARGE_INTEGER),
                ("WriteOperationCount", wintypes.ULARGE_INTEGER),
                ("OtherOperationCount", wintypes.ULARGE_INTEGER),
                ("ReadTransferCount", wintypes.ULARGE_INTEGER),
                ("WriteTransferCount", wintypes.ULARGE_INTEGER),
                ("OtherTransferCount", wintypes.ULARGE_INTEGER),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

        job = CreateJobObjectW(None, None)
        if not job:
            return

        ok = SetInformationJobObject(
            job,
            JobObjectExtendedLimitInformation,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not ok:
            return

        ok = AssignProcessToJobObject(job, GetCurrentProcess())
        if not ok:
            # Likely already in a job that disallows nesting. Ignore.
            return

        _WINDOWS_JOB_HANDLE = int(job)
    except Exception:
        # Best-effort; running without a job object still works but may leak child processes on hard-kill.
        return


def _is_parent_alive(parent_pid: int) -> bool:
    if parent_pid <= 0:
        return False

    if os.name != "nt":
        try:
            os.kill(parent_pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    try:
        import ctypes
        import ctypes.wintypes as wintypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        OpenProcess = kernel32.OpenProcess
        OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        OpenProcess.restype = wintypes.HANDLE

        GetExitCodeProcess = kernel32.GetExitCodeProcess
        GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        GetExitCodeProcess.restype = wintypes.BOOL

        CloseHandle = kernel32.CloseHandle
        CloseHandle.argtypes = [wintypes.HANDLE]
        CloseHandle.restype = wintypes.BOOL

        handle = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, parent_pid)
        if not handle:
            return False

        try:
            exit_code = wintypes.DWORD()
            ok = GetExitCodeProcess(handle, ctypes.byref(exit_code))
            if not ok:
                return True
            return exit_code.value == STILL_ACTIVE
        finally:
            CloseHandle(handle)
    except Exception:
        return True


def _start_parent_watchdog(parent_pid: int | None) -> None:
    if not parent_pid:
        return
    if parent_pid == os.getpid():
        return

    def _watch() -> None:
        while True:
            time.sleep(1.0)
            if not _is_parent_alive(parent_pid):
                logger.info("Parent process %s exited; shutting down backend.", parent_pid)
                os._exit(0)

    t = threading.Thread(target=_watch, name="parent-watchdog", daemon=True)
    t.start()


def find_initial_save() -> Path | None:
    """Find an initial save file to load.

    Returns:
        Path to a save file, or None if not found
    """
    from stellaris_companion.save_loader import find_most_recent_save

    save = find_most_recent_save()
    if save:
        logger.info(f"Found save file: {save.name}")
    return save


def _normalize_input_path(raw_path: str) -> Path | None:
    """Normalize a user-provided path string for cross-platform consistency."""
    if not raw_path:
        return None
    try:
        expanded = os.path.expandvars(raw_path)
        return Path(expanded).expanduser().resolve(strict=False)
    except OSError:
        return None


def resolve_save_inputs(args: argparse.Namespace) -> tuple[Path | None, list[Path] | None]:
    """Resolve initial save file and watch paths from args/env.

    Precedence:
      1) CLI --save-path (file)
      2) STELLARIS_SAVE_PATH (file or directory)
      3) STELLARIS_SAVE_DIR (directory to search/watch)
      4) platform defaults (Python-side)
    """
    from stellaris_companion.save_loader import find_most_recent_save_in_directory

    # CLI args override everything.
    if args.save_path:
        candidate = _normalize_input_path(args.save_path)
        if candidate and candidate.exists() and candidate.is_file():
            return candidate, None
        logger.warning("Ignoring --save-path (not a readable file): %s", args.save_path)

    env_save_path = os.environ.get("STELLARIS_SAVE_PATH")
    env_save_dir = os.environ.get("STELLARIS_SAVE_DIR")

    save_dir: Path | None = None
    save_file: Path | None = None

    if env_save_path:
        p = _normalize_input_path(env_save_path)
        try:
            if p and p.exists() and p.is_file():
                save_file = p
            elif p and p.exists() and p.is_dir():
                save_dir = p
            else:
                logger.warning("Ignoring STELLARIS_SAVE_PATH (not found): %s", env_save_path)
        except OSError:
            logger.warning("Ignoring STELLARIS_SAVE_PATH (invalid): %s", env_save_path)

    if not save_dir and env_save_dir:
        p = _normalize_input_path(env_save_dir)
        try:
            if p and p.exists() and p.is_dir():
                save_dir = p
            else:
                logger.warning("Ignoring STELLARIS_SAVE_DIR (not found): %s", env_save_dir)
        except OSError:
            logger.warning("Ignoring STELLARIS_SAVE_DIR (invalid): %s", env_save_dir)

    watch_paths = [save_dir] if save_dir else None

    # If we have a directory but no explicit file, pick the latest within that directory.
    if save_dir and not save_file:
        save_file = find_most_recent_save_in_directory(save_dir)
        if save_file:
            logger.info(f"Found save file in configured directory: {save_file.name}")

    return save_file, watch_paths


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

    _enable_windows_kill_on_close_job()

    # Validate environment
    try:
        validate_environment()
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    _start_parent_watchdog(args.parent_pid)

    # Determine save path + watch paths (may be None to use defaults)
    save_path, watch_paths = resolve_save_inputs(args)

    # If no specific save, try to find the most recent one in defaults
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

    save_watcher = SaveWatcher(watch_paths=watch_paths, on_save_detected=on_save_detected)
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
    import multiprocessing

    multiprocessing.freeze_support()
    main()
