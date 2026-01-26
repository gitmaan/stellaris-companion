"""
Stellaris Companion Discord Commands
====================================

Slash command implementations for the Discord bot.
"""

from .ask import setup as setup_ask
from .briefing import setup as setup_briefing
from .chronicle import setup as setup_chronicle
from .end_session import setup as setup_end_session
from .history import setup as setup_history
from .recap import setup as setup_recap
from .status import setup as setup_status

__all__ = [
    "setup_ask",
    "setup_status",
    "setup_briefing",
    "setup_end_session",
    "setup_history",
    "setup_chronicle",
    "setup_recap",
]
