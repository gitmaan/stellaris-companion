"""
Stellaris Companion Discord Commands
====================================

Slash command implementations for the Discord bot.
"""

from .ask import setup as setup_ask
from .status import setup as setup_status
from .briefing import setup as setup_briefing

__all__ = ["setup_ask", "setup_status", "setup_briefing"]
