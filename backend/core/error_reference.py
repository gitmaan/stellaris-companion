"""Privacy-safe references for unexpected local failures.

A reference names the exception type, errno and the innermost application frame
(file basename, line and function). It never includes the exception message or
any path, because those can contain usernames, save names or credentials. Users
can copy it into a report without opting into backend logs.
"""

from __future__ import annotations

import os
import traceback

_APP_PACKAGES = ("backend", "stellaris_companion", "stellaris_save_extractor")


def _is_app_frame(filename: str) -> bool:
    parts = os.path.normpath(filename).replace("\\", "/").split("/")
    return any(package in parts for package in _APP_PACKAGES)


def error_reference(exc: BaseException) -> str:
    """Return a short fingerprint such as ``FileNotFoundError errno=2 @ x.py:12 f``."""
    parts = [type(exc).__name__]
    errno = getattr(exc, "errno", None) if isinstance(exc, OSError) else None
    if isinstance(errno, int):
        parts.append(f"errno={errno}")

    frames = traceback.extract_tb(exc.__traceback__) if exc.__traceback__ else []
    app_frames = [frame for frame in frames if _is_app_frame(frame.filename)]
    frame = (app_frames or frames or [None])[-1]
    if frame is not None:
        name = os.path.basename(frame.filename.replace("\\", "/"))
        parts.append(f"@ {name}:{frame.lineno} {frame.name}")
    return " ".join(parts)[:160]


def local_failure_cause(exc: BaseException) -> BaseException | None:
    """Return the local OS-level cause of a provider error, if there is one.

    Network/HTTP failures are expected provider conditions with their own codes;
    an OSError such as a missing certificate file is a local fault worth naming.
    """
    seen: set[int] = set()
    current = exc.__cause__ or exc.__context__
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, OSError):
            return current
        current = current.__cause__ or current.__context__
    return None
