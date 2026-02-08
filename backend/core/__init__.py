"""
Stellaris Companion Core
========================

Core functionality: Companion AI and save file watching.
"""

# Lazy imports to avoid requiring all dependencies at import time
__all__ = ["Companion", "SaveWatcher"]


def __getattr__(name):
    """Lazy import to avoid dependency issues at module load time."""
    if name == "Companion":
        from .companion import Companion

        return Companion
    elif name == "SaveWatcher":
        from .save_watcher import SaveWatcher

        return SaveWatcher
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
