"""
Stellaris Companion Discord Bot
===============================

Discord integration for the Stellaris strategic advisor.
"""

# Lazy imports to avoid requiring discord.py at import time
__all__ = ["StellarisBot"]


def __getattr__(name):
    """Lazy import to avoid dependency issues at module load time."""
    if name == "StellarisBot":
        from .discord_bot import StellarisBot
        return StellarisBot
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
