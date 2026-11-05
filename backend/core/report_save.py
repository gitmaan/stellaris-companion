"""Bounded, local-only description of the active save for report consent."""

from __future__ import annotations

import re
import stat
import zipfile
from pathlib import Path
from typing import Any

MAX_SAVE_BYTES = 50 * 1024 * 1024


def describe_report_save(path: Path) -> dict[str, Any]:
    path = path.resolve(strict=True)
    before = path.stat()
    if path.suffix.lower() != ".sav" or not stat.S_ISREG(before.st_mode):
        raise ValueError("Select a Stellaris save first.")
    if not 4 <= before.st_size <= MAX_SAVE_BYTES:
        raise ValueError("Save attachments must be at most 50 MiB.")
    with zipfile.ZipFile(path) as archive:
        if archive.namelist().count("meta") != 1 or archive.namelist().count("gamestate") != 1:
            raise ValueError("The file is not a Stellaris save.")
        meta = archive.getinfo("meta")
        if meta.file_size > 1024 * 1024:
            raise ValueError("Save metadata is too large.")
        text = archive.read(meta).decode("utf-8", errors="replace")
    after = path.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ):
        raise ValueError("The save changed. Select it again after saving finishes.")
    values = dict(re.findall(r'^\s*(name|date|version)\s*=\s*"?([^"\r\n]+)', text, re.M))
    return {
        # This authenticated route is called only by Electron's main process.
        # The IPC service strips this path before returning the consent preview.
        "path": str(path),
        "fingerprint": ":".join(
            str(value)
            for value in (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
        ),
        "filename": path.name,
        "sizeBytes": before.st_size,
        "empireName": values.get("name", "")[:200],
        "gameDate": values.get("date", "")[:32],
        "gameVersion": values.get("version", "")[:80],
    }
