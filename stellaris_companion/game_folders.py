"""Where Stellaris keeps things on this machine.

Two kinds of place matter, and everything that looks for saves, for the player's
settings or for the game itself starts from the lists here:

- A **user folder** holds what belongs to the player: ``settings.txt``, their
  mods and the ``save games`` folder. There is one per launcher (Steam and GOG
  share "Stellaris"; the Paradox launcher and Game Pass have their own).
- A **Steam library** holds installed games. Steam has one main library and the
  player can add more on other drives. On Linux a game run through Proton also
  keeps its Windows-style user folder inside the library it is installed in.

These are candidates in the order to try them; most do not exist on a given machine.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

STEAM_APP_ID = "281990"
SAVE_FOLDER = "save games"

_PARADOX = "Paradox Interactive"
_LIBRARY_PATH = re.compile(r'"path"\s+"((?:[^"\\]|\\.)*)"')
_FLATPAK_STEAM = (".var", "app", "com.valvesoftware.Steam")
# Inside a Steam library: the Documents folder of the Windows that Proton fakes for the game.
_PROTON_DOCUMENTS = (
    "steamapps",
    "compatdata",
    STEAM_APP_ID,
    "pfx",
    "drive_c",
    "users",
    "steamuser",
    "Documents",
)


def user_dirs() -> list[Path]:
    """Folders that may hold the player's settings, mods and saves."""
    if sys.platform.startswith("linux"):
        home = Path.home()
        share = Path(".local", "share", _PARADOX)
        return _distinct(
            [
                home / share / "Stellaris",
                home / share / "Stellaris Plaza",
                home.joinpath(*_FLATPAK_STEAM) / share / "Stellaris",
                *(
                    library.joinpath(*_PROTON_DOCUMENTS, _PARADOX, "Stellaris")
                    for library in steam_libraries()
                ),
            ]
        )
    launchers = ["Stellaris", "Stellaris Plaza"]
    if sys.platform == "win32":
        launchers.append("Stellaris GamePass")
    return _distinct(
        [
            documents / _PARADOX / launcher
            for documents in documents_dirs()
            for launcher in launchers
        ]
    )


def save_dirs() -> list[Path]:
    """The ``save games`` folder of each user folder."""
    return [user_dir / SAVE_FOLDER for user_dir in user_dirs()]


def documents_dirs() -> list[Path]:
    """The player's Documents folder, first where Windows says it is.

    Windows often moves Documents into OneDrive or onto another drive, and the
    game follows it there.
    """
    usual = Path.home() / "Documents"
    if sys.platform != "win32":
        return [usual]
    moved = _windows_registry_text(
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders", "Personal"
    )
    return _distinct([*([Path(os.path.expandvars(moved))] if moved else []), usual])


def steam_libraries() -> list[Path]:
    """Every folder Steam installs games into: its own, then the ones the player added."""
    libraries: list[Path] = []
    for root in _steam_roots():
        libraries.append(root)
        try:
            listing = (root / "steamapps" / "libraryfolders.vdf").read_text(
                encoding="utf-8-sig", errors="replace"
            )
        except OSError:
            continue
        libraries.extend(
            Path(path.replace("\\\\", "\\")) for path in _LIBRARY_PATH.findall(listing)
        )
    return _distinct(libraries)


def _steam_roots() -> list[Path]:
    home = Path.home()
    if sys.platform == "darwin":
        return [home / "Library" / "Application Support" / "Steam"]
    if sys.platform == "win32":
        registered = _windows_registry_text(r"Software\Valve\Steam", "SteamPath")
        program_files = [os.environ.get("PROGRAMFILES(X86)"), os.environ.get("PROGRAMFILES")]
        return [
            *([Path(registered)] if registered else []),
            *(Path(base) / "Steam" for base in program_files if base),
        ]
    flatpak = home.joinpath(*_FLATPAK_STEAM)
    return [
        home / ".steam" / "steam",
        home / ".local" / "share" / "Steam",
        flatpak / "data" / "Steam",
        flatpak / ".local" / "share" / "Steam",
        home / "snap" / "steam" / "common" / ".local" / "share" / "Steam",
    ]


def _windows_registry_text(key_path: str, name: str) -> str | None:
    """A text value from the current user's registry; None off Windows or when unset."""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, name)
    except (ImportError, OSError):
        return None
    return value if isinstance(value, str) and value.strip() else None


def _distinct(paths: list[Path]) -> list[Path]:
    return list(dict.fromkeys(paths))
