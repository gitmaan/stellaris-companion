"""
Save Loader for Stellaris Companion
===================================

Utilities for finding and loading Stellaris save files.
Supports both local project saves and standard Stellaris save locations.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .paths import get_repo_root

# Standard Stellaris save locations by platform
STELLARIS_SAVE_PATHS = {
    "darwin": [  # macOS
        Path.home() / "Documents" / "Paradox Interactive" / "Stellaris" / "save games",
        Path.home() / "Documents" / "Paradox Interactive" / "Stellaris Plaza" / "save games",
    ],
    "linux": [
        Path.home() / ".local" / "share" / "Paradox Interactive" / "Stellaris" / "save games",
        Path.home() / ".local" / "share" / "Paradox Interactive" / "Stellaris Plaza" / "save games",
        # Flatpak Steam
        Path.home()
        / ".var"
        / "app"
        / "com.valvesoftware.Steam"
        / ".local"
        / "share"
        / "Paradox Interactive"
        / "Stellaris"
        / "save games",
    ],
    "win32": [
        Path.home() / "Documents" / "Paradox Interactive" / "Stellaris" / "save games",
        Path.home() / "Documents" / "Paradox Interactive" / "Stellaris Plaza" / "save games",
        Path.home() / "Documents" / "Paradox Interactive" / "Stellaris GamePass" / "save games",
    ],
}


def get_platform_save_paths() -> list[Path]:
    """Get save paths for current platform."""
    import sys

    platform = sys.platform
    # Return a copy to prevent accidental mutation of module-level defaults.
    return list(STELLARIS_SAVE_PATHS.get(platform, STELLARIS_SAVE_PATHS["darwin"]))


def _is_packaged() -> bool:
    """True when running as a PyInstaller-frozen app."""
    import sys

    return bool(getattr(sys, "frozen", False))


def find_most_recent_save_in_directory(save_dir: Path) -> Path | None:
    """Find the most recent .sav within a Stellaris 'save games' directory.

    Optimized for the Stellaris layout:
      save games/<empire>/<save>.sav

    This scans at most two levels deep to avoid the cost of an unbounded rglob.
    """
    try:
        if not save_dir.exists() or not save_dir.is_dir():
            return None
    except OSError:
        return None

    latest: Path | None = None
    latest_mtime = -1.0

    def consider(path: Path) -> None:
        nonlocal latest, latest_mtime
        try:
            st = path.stat()
        except (OSError, PermissionError):
            return
        if st.st_mtime > latest_mtime:
            latest_mtime = st.st_mtime
            latest = path

    try:
        for entry in save_dir.iterdir():
            try:
                if entry.is_dir():
                    for child in entry.iterdir():
                        if child.suffix.lower() == ".sav":
                            consider(child)
                elif entry.suffix.lower() == ".sav":
                    consider(entry)
            except (OSError, PermissionError):
                continue
    except (OSError, PermissionError):
        return None

    return latest


def find_all_saves(search_paths: list[Path] = None) -> list[dict]:
    """Find all Stellaris save files in search paths.

    Args:
        search_paths: List of paths to search. If None, uses platform defaults
                      plus the project directory.

    Returns:
        List of dicts with save file info, sorted by modification time (newest first)
    """
    if search_paths is None:
        search_paths = get_platform_save_paths()
        # Also check project directory (dev only). In packaged builds this points
        # into the app bundle / PyInstaller _internal, which we do not want.
        if not _is_packaged():
            project_dir = get_repo_root(Path(__file__))
            search_paths.append(project_dir)

    saves = []

    for base_path in search_paths:
        if not base_path.exists():
            continue

        # Find all .sav files recursively
        for sav_file in base_path.rglob("*.sav"):
            try:
                stat = sav_file.stat()
                saves.append(
                    {
                        "path": sav_file,
                        "name": sav_file.stem,
                        "size_mb": stat.st_size / (1024 * 1024),
                        "modified": datetime.fromtimestamp(stat.st_mtime),
                        "modified_timestamp": stat.st_mtime,
                    }
                )
            except (OSError, PermissionError):
                continue

    # Sort by modification time, newest first
    saves.sort(key=lambda x: x["modified_timestamp"], reverse=True)

    return saves


def find_most_recent_save(search_paths: list[Path] = None) -> Path | None:
    """Find the most recently modified save file.

    Args:
        search_paths: List of paths to search. If None, uses defaults.

    Returns:
        Path to most recent save, or None if no saves found
    """
    saves = find_all_saves(search_paths)
    if saves:
        return saves[0]["path"]
    return None


def find_saves_for_empire(empire_name: str, search_paths: list[Path] = None) -> list[dict]:
    """Find saves that match an empire name (in folder or filename).

    Args:
        empire_name: Empire name to search for (case-insensitive)
        search_paths: List of paths to search. If None, uses defaults.

    Returns:
        List of matching saves, sorted by modification time
    """
    all_saves = find_all_saves(search_paths)
    empire_lower = empire_name.lower()

    matching = []
    for save in all_saves:
        # Check if empire name is in the path (folder or filename)
        path_str = str(save["path"]).lower()
        if empire_lower in path_str:
            matching.append(save)

    return matching


def list_saves(limit: int = 10) -> None:
    """Print a list of available saves.

    Args:
        limit: Maximum number of saves to show
    """
    saves = find_all_saves()

    if not saves:
        print("No save files found.")
        return

    print(f"\nFound {len(saves)} save file(s):\n")
    print(f"{'#':<3} {'Modified':<20} {'Size':<10} {'Name/Path'}")
    print("-" * 80)

    for i, save in enumerate(saves[:limit]):
        mod_str = save["modified"].strftime("%Y-%m-%d %H:%M")
        size_str = f"{save['size_mb']:.1f} MB"
        # Show relative path if in project, full path otherwise
        path = save["path"]
        project_dir = get_repo_root(Path(__file__))
        try:
            rel_path = path.relative_to(project_dir)
            path_str = str(rel_path)
        except ValueError:
            path_str = str(path)

        print(f"{i + 1:<3} {mod_str:<20} {size_str:<10} {path_str}")

    if len(saves) > limit:
        print(f"\n... and {len(saves) - limit} more")


def load_save_interactive() -> Path | None:
    """Interactive save selection.

    Returns:
        Selected save path, or None if cancelled
    """
    saves = find_all_saves()

    if not saves:
        print("No save files found.")
        return None

    list_saves(limit=10)

    print("\nEnter number to select, or 'q' to quit:")

    while True:
        try:
            choice = input("> ").strip()

            if choice.lower() == "q":
                return None

            idx = int(choice) - 1
            if 0 <= idx < len(saves):
                return saves[idx]["path"]
            else:
                print(f"Invalid choice. Enter 1-{min(10, len(saves))}")
        except ValueError:
            print("Enter a number or 'q' to quit")
        except (EOFError, KeyboardInterrupt):
            return None


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "--list":
            list_saves(limit=20)
        elif sys.argv[1] == "--recent":
            recent = find_most_recent_save()
            if recent:
                print(recent)
            else:
                print("No saves found", file=sys.stderr)
                sys.exit(1)
        elif sys.argv[1] == "--interactive":
            selected = load_save_interactive()
            if selected:
                print(f"\nSelected: {selected}")
            else:
                print("No save selected")
        else:
            print(f"Unknown option: {sys.argv[1]}")
            print(
                "Usage: python -m stellaris_companion.save_loader [--list|--recent|--interactive]"
            )
    else:
        # Default: show most recent
        recent = find_most_recent_save()
        if recent:
            print(f"Most recent save: {recent}")
            print(f"Modified: {datetime.fromtimestamp(recent.stat().st_mtime)}")
        else:
            print("No saves found")
