"""What the player's own game calls things.

A save records technologies, buildings, traditions and the rest by internal ID,
and an ID often says nothing about the name on screen: ``building_factory_3`` is
"Civilian Repli-Complexes". The installed game has the real name of every ID, for
the version the player runs, in the language they play in, with their mods. This
module reads those names from the game's own text files, the way the game loads
them, and answers "what is this ID called?".

Without an install (a save opened on another machine) there are no names here and
callers fall back to the catalogs shipped with the app, or keep the ID.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from pathlib import Path

from .game_install import DEFAULT_LANGUAGE, GameInstall, find_game_install

logger = logging.getLogger(__name__)

# A name longer than this is a description or event text that shares a key shape.
MAX_NAME_LENGTH = 80
# The game can be patched, or its language or mods changed, while the app is open.
RECHECK_SECONDS = 60.0

_HEADER = re.compile(r"^l_(\w+):[ \t]*(?:#.*)?$", re.M)
_ENTRY = re.compile(r'^[ \t]*([^\s:#"]+):\d*[ \t]*"(.*?)"[ \t]*(?:#.*)?$', re.M)
_REFERENCE = re.compile(r"\$([^$|\s]+)(?:\|[^$]*)?\$")
_COLOUR = re.compile(r"§.")
_ICON = re.compile(r"£[^£\s]+£")

_LANGUAGE_NAMES = {
    "braz_por": "Brazilian Portuguese",
    "simp_chinese": "Simplified Chinese",
}


def read_localisation(content_dir: Path, language: str) -> dict[str, str]:
    """Every ``key: "text"`` entry one game or mod folder defines for a language.

    The game reads a file when its name ends in ``l_<language>`` and its first
    line is ``l_<language>:``; folders are only for tidiness. Files in a
    ``replace`` folder load last, which is how a mod renames something.
    """
    root = content_dir / "localisation"
    suffix = f"l_{language}"

    def load_order(path: Path) -> tuple[bool, str, str]:
        return ("replace" in path.relative_to(root).parts[:-1], path.name.lower(), str(path))

    entries: dict[str, str] = {}
    files = (path for path in root.rglob("*.yml") if path.stem.lower().endswith(suffix))
    for path in sorted(files, key=load_order):
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            logger.warning("Could not read game text file %s", path)
            continue
        sections = _HEADER.split(text)
        for header, body in zip(sections[1::2], sections[2::2], strict=True):
            if header.lower() == language:
                entries.update(_ENTRY.findall(body))
    return entries


class GameNames:
    """Display names by game text key, with references and formatting resolved."""

    def __init__(
        self,
        entries: dict[str, str],
        *,
        language: str = DEFAULT_LANGUAGE,
        version: str | None = None,
    ) -> None:
        self.language = language
        self.version = version
        self._entries = entries
        self._names: dict[str, str | None] = {}

    @classmethod
    def from_install(cls, install: GameInstall) -> GameNames:
        entries: dict[str, str] = {}
        for content_dir in install.content_dirs:
            entries.update(read_localisation(content_dir, install.language))
        # Names and what they refer to are short; dropping long text keeps memory small.
        entries = {key: text for key, text in entries.items() if len(text) <= 2 * MAX_NAME_LENGTH}
        return cls(entries, language=install.language, version=install.version)

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def source(self) -> str:
        """Where these names come from, for telling a model how far to trust them."""
        language = _LANGUAGE_NAMES.get(self.language, self.language.replace("_", " ").title())
        version = f", {self.version}" if self.version else ""
        return f"{language} text of the installed game{version}"

    def name(self, key: str) -> str | None:
        """The name shown for ``key``, or None when the game has no plain name for it."""
        try:
            return self._names[key]
        except KeyError:
            name = self._names[key] = self._resolve(key, ())
            return name

    def _resolve(self, key: str, seen: tuple[str, ...]) -> str | None:
        text = self._entries.get(key)
        if text is None or key in seen:
            return None
        unresolved = False

        def substitute(match: re.Match[str]) -> str:
            nonlocal unresolved
            value = self._resolve(match.group(1), (*seen, key))
            unresolved = unresolved or value is None
            return value or ""

        text = _REFERENCE.sub(substitute, text)
        text = _COLOUR.sub("", _ICON.sub("", text))
        text = " ".join(text.replace('\\"', '"').replace("\\n", " ").split())
        # "[Root.GetName]" is filled in by the running game; it is not a fixed name.
        if unresolved or not text or "[" in text or len(text) > MAX_NAME_LENGTH:
            return None
        return text


_lock = threading.Lock()
_names: GameNames | None = None
_install: GameInstall | None = None
_checked_at: float | None = None
_pinned = False


def installed_names() -> GameNames | None:
    """Names from the game installed on this machine, read on first use."""
    global _names, _install, _checked_at
    if _pinned or (_checked_at is not None and time.monotonic() - _checked_at < RECHECK_SECONDS):
        return _names
    with _lock:
        if _checked_at is None or time.monotonic() - _checked_at >= RECHECK_SECONDS:
            install = find_game_install()
            if install != _install or _checked_at is None:
                _names = _load(install)
                _install = install
            _checked_at = time.monotonic()
    return _names


def _load(install: GameInstall | None) -> GameNames | None:
    if install is None:
        logger.info("No Stellaris install found; using the name catalogs shipped with the app")
        return None
    started = time.monotonic()
    try:
        names = GameNames.from_install(install)
    except OSError:
        logger.exception("Could not read game text from %s", install.game_dir)
        return None
    if not names:
        logger.warning("No %s game text under %s", install.language, install.game_dir)
        return None
    logger.info(
        "Read %d game text entries (%s, %d mods) in %.1fs",
        len(names),
        names.source,
        len(install.mod_dirs),
        time.monotonic() - started,
    )
    return names


def use_names(names: GameNames | None) -> None:
    """Answer from ``names`` (or from no install) instead of searching this machine."""
    global _names, _pinned
    with _lock:
        _names, _pinned = names, True


def use_installed_game() -> None:
    """Undo :func:`use_names`: look for the installed game again."""
    global _names, _install, _checked_at, _pinned
    with _lock:
        _names, _install, _checked_at, _pinned = None, None, None, False


def game_name(*keys: object) -> str | None:
    """The installed game's name for the first of ``keys`` that has one."""
    names = installed_names()
    if names is None:
        return None
    for key in keys:
        if isinstance(key, str) and key.strip():
            name = names.name(key.strip())
            if name:
                return name
    return None


def names_source() -> str | None:
    """A short description of the installed game's names, or None without an install."""
    names = installed_names()
    return names.source if names else None
