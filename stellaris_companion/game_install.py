"""Find the player's own Stellaris install and how it is set up.

The game on this machine is the authority on what things are called: it has the
names for the installed version, in the language the player plays in, including
any mods they have enabled. This module only locates it and reads three small
settings files; nothing is copied and nothing leaves the machine.

``STELLARIS_GAME_DIR`` points at an install the search does not find. When it is
set, only that folder is used; set it to an empty string to use no install at all.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from .save_loader import get_platform_save_paths

GAME_DIR_ENV = "STELLARIS_GAME_DIR"
DEFAULT_LANGUAGE = "english"

_STEAM_GAME = ("steamapps", "common", "Stellaris")
_LIBRARY_PATH = re.compile(r'"path"\s+"((?:[^"\\]|\\.)*)"')
_LANGUAGE = re.compile(r'^\s*language\s*=\s*"?l_(\w+)"?', re.M)
_MOD_PATH = re.compile(r'^\s*path\s*=\s*"([^"]+)"', re.M)


@dataclass(frozen=True)
class GameInstall:
    """An installed game: its folder, version, language and enabled mods."""

    game_dir: Path
    version: str | None = None
    language: str = DEFAULT_LANGUAGE
    mod_dirs: tuple[Path, ...] = ()

    @property
    def content_dirs(self) -> tuple[Path, ...]:
        """The game folder, then each enabled mod in load order."""
        return (self.game_dir, *self.mod_dirs)


def find_game_install() -> GameInstall | None:
    """The Stellaris install on this machine, or None when there is none to read."""
    override = os.environ.get(GAME_DIR_ENV)
    if override is None:
        candidates = _candidate_game_dirs()
    else:
        candidates = [Path(override).expanduser()] if override.strip() else []
    game_dir = next((path for path in candidates if is_game_dir(path)), None)
    if game_dir is None:
        return None
    user_dir = _find_user_dir()
    return GameInstall(
        game_dir=game_dir,
        version=read_game_version(game_dir),
        language=_read_language(user_dir),
        mod_dirs=_enabled_mod_dirs(user_dir),
    )


def is_game_dir(path: Path) -> bool:
    try:
        return (path / "localisation").is_dir() and (path / "common").is_dir()
    except OSError:
        return False


def read_game_version(game_dir: Path) -> str | None:
    """The version the launcher shows, such as ``Cygnus v4.5.3 (4e91)``."""
    try:
        settings = json.loads(_read(game_dir / "launcher-settings.json"))
    except (OSError, ValueError):
        return None
    version = settings.get("version") if isinstance(settings, dict) else None
    return version.strip() if isinstance(version, str) and version.strip() else None


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def _save_dirs() -> list[Path]:
    chosen = os.environ.get("STELLARIS_SAVE_DIR")
    return [*([Path(chosen).expanduser()] if chosen else []), *get_platform_save_paths()]


def _candidate_game_dirs() -> list[Path]:
    candidates: list[Path] = []
    for root in _steam_roots():
        candidates.append(root.joinpath(*_STEAM_GAME))
        for library in _steam_libraries(root):
            candidates.append(library.joinpath(*_STEAM_GAME))
    # Saves kept inside a Steam library (Proton, Steam Cloud) sit next to the game.
    for save_dir in _save_dirs():
        for parent in save_dir.parents:
            if parent.name == "steamapps":
                candidates.append(parent / "common" / "Stellaris")
    if sys.platform == "win32":
        for variable in ("PROGRAMFILES(X86)", "PROGRAMFILES"):
            base = os.environ.get(variable)
            if base:
                candidates.append(Path(base) / "GOG Galaxy" / "Games" / "Stellaris")
        candidates.append(Path("C:/GOG Games/Stellaris"))
    return list(dict.fromkeys(candidates))


def _steam_roots() -> list[Path]:
    home = Path.home()
    if sys.platform == "darwin":
        return [home / "Library" / "Application Support" / "Steam"]
    if sys.platform == "win32":
        roots = []
        registered = _windows_steam_path()
        if registered:
            roots.append(Path(registered))
        for variable in ("PROGRAMFILES(X86)", "PROGRAMFILES"):
            base = os.environ.get(variable)
            if base:
                roots.append(Path(base) / "Steam")
        return roots
    flatpak = home / ".var" / "app" / "com.valvesoftware.Steam"
    return [
        home / ".steam" / "steam",
        home / ".local" / "share" / "Steam",
        flatpak / ".local" / "share" / "Steam",
        flatpak / "data" / "Steam",
        home / "snap" / "steam" / "common" / ".local" / "share" / "Steam",
    ]


def _windows_steam_path() -> str | None:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            value, _ = winreg.QueryValueEx(key, "SteamPath")
    except (ImportError, OSError):
        return None
    return value if isinstance(value, str) and value else None


def _steam_libraries(steam_root: Path) -> list[Path]:
    """Other drives and folders the player has told Steam to install games into."""
    try:
        text = _read(steam_root / "steamapps" / "libraryfolders.vdf")
    except OSError:
        return []
    return [Path(path.replace("\\\\", "\\")) for path in _LIBRARY_PATH.findall(text)]


def _find_user_dir() -> Path | None:
    """The folder holding the player's settings, saves and mods."""
    for save_dir in _save_dirs():
        user_dir = save_dir.parent
        try:
            if (user_dir / "settings.txt").is_file():
                return user_dir
        except OSError:
            continue
    return None


def _read_language(user_dir: Path | None) -> str:
    if user_dir is None:
        return DEFAULT_LANGUAGE
    try:
        match = _LANGUAGE.search(_read(user_dir / "settings.txt"))
    except OSError:
        return DEFAULT_LANGUAGE
    return match.group(1).lower() if match else DEFAULT_LANGUAGE


def _enabled_mod_dirs(user_dir: Path | None) -> tuple[Path, ...]:
    """Folders of the mods in the playset the launcher last started the game with."""
    if user_dir is None:
        return ()
    try:
        playset = json.loads(_read(user_dir / "dlc_load.json"))
    except (OSError, ValueError):
        return ()
    enabled = playset.get("enabled_mods") if isinstance(playset, dict) else None
    mod_dirs: list[Path] = []
    for descriptor in enabled if isinstance(enabled, list) else []:
        if not isinstance(descriptor, str):
            continue
        try:
            match = _MOD_PATH.search(_read(user_dir / descriptor))
        except OSError:
            continue
        if not match:
            continue
        mod_dir = Path(match.group(1)).expanduser()
        if not mod_dir.is_absolute():
            mod_dir = user_dir / mod_dir
        try:
            if mod_dir.is_dir() and mod_dir not in mod_dirs:
                mod_dirs.append(mod_dir)
        except OSError:
            continue
    return tuple(mod_dirs)
