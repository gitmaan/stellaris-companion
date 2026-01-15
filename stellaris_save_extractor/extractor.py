"""Public `SaveExtractor` facade composed from smaller mixin modules.

This file exists to keep the primary class easy to find while keeping
implementation details split across domain-focused modules to fit typical
LLM context windows.
"""

from __future__ import annotations

from .armies import ArmiesMixin
from .base import SaveExtractorBase
from .briefing import BriefingMixin
from .diplomacy import DiplomacyMixin
from .economy import EconomyMixin
from .endgame import EndgameMixin
from .leaders import LeadersMixin
from .metadata import MetadataMixin
from .military import MilitaryMixin
from .planets import PlanetsMixin
from .player import PlayerMixin
from .politics import PoliticsMixin
from .projects import ProjectsMixin
from .species import SpeciesMixin
from .technology import TechnologyMixin


class SaveExtractor(
    SaveExtractorBase,
    MetadataMixin,
    PlayerMixin,
    MilitaryMixin,
    ArmiesMixin,
    EndgameMixin,
    ProjectsMixin,
    LeadersMixin,
    TechnologyMixin,
    EconomyMixin,
    DiplomacyMixin,
    PoliticsMixin,
    PlanetsMixin,
    SpeciesMixin,
    BriefingMixin,
):
    """Extract and query sections from a Stellaris save file."""
