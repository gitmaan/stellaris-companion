"""Focused tests for player extraction helpers."""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stellaris_save_extractor.player import PlayerMixin


class DummyPlayerExtractor(PlayerMixin):
    """Minimal test double for naval-cap analysis."""

    def __init__(
        self,
        player_country,
        *,
        difficulty="cadet",
        researched_techs=None,
        starbases=None,
        megastructures=None,
        job_analysis=None,
        subject_analysis=None,
        resolution_types=None,
        federation_perks=None,
        relics=None,
        leader_trait_hits=None,
        timed_modifiers=None,
    ):
        self._player_country = player_country
        self._difficulty = difficulty
        self._researched_techs = researched_techs or []
        self._starbases = starbases or {"starbases": []}
        self._megastructures = megastructures or {"megastructures": []}
        self._job_analysis = job_analysis or {
            "flat_additions": {},
            "unresolved_source_families": set(),
        }
        self._subject_analysis = subject_analysis or {
            "modeled_terms": {},
            "unresolved_source_families": set(),
        }
        self._resolution_types = resolution_types or set()
        self._federation_perks = federation_perks or []
        self._relics = relics or {"relics": []}
        self._leader_trait_hits = leader_trait_hits or set()
        self._timed_modifiers = timed_modifiers or set()

    def get_player_empire_id(self) -> int:
        return 0

    def _get_player_country_entry(self, player_id: int):
        assert player_id == 0
        return self._player_country

    def _get_naval_cap_difficulty(self) -> str | None:
        return self._difficulty

    def _get_researched_technologies(self, player_id: int) -> list[str]:
        assert player_id == 0
        return list(self._researched_techs)

    def get_starbases(self) -> dict:
        return self._starbases

    def get_megastructures(self) -> dict:
        return self._megastructures

    def _get_naval_cap_job_analysis(self, **kwargs) -> dict:
        return self._job_analysis

    def _get_naval_cap_subject_analysis(self, player_id: int) -> dict:
        assert player_id == 0
        return self._subject_analysis

    def _get_naval_cap_resolution_types(self) -> set[str]:
        return set(self._resolution_types)

    def _get_naval_cap_federation_perk_types(self, player_country: dict) -> list[str]:
        assert player_country is self._player_country
        return list(self._federation_perks)

    def get_relics(self) -> dict:
        return self._relics

    def _get_naval_cap_leader_trait_hits(self) -> set[str]:
        return set(self._leader_trait_hits)

    def _get_relevant_timed_naval_modifiers(self, player_country: dict) -> set[str]:
        assert player_country is self._player_country
        return set(self._timed_modifiers)


def test_get_naval_capacity_high_confidence_on_clean_base_plus_difficulty():
    extractor = DummyPlayerExtractor(
        {
            "used_naval_capacity": "100",
            "fleet_size": "100",
            "starbase_capacity": "15",
            "used_starbase_capacity": "12",
            "government": {"civics": []},
            "traditions": [],
            "ascension_perks": [],
            "active_policies": [
                {"policy": "diplomatic_stance", "selected": "diplo_stance_expansionist"}
            ],
            "edicts": [],
            "flags": {},
            "owned_planets": [],
        }
    )

    naval_capacity = extractor.get_naval_capacity()
    analysis = naval_capacity["analysis"]

    assert naval_capacity["used"] == 100
    assert naval_capacity["max"] == 75
    assert naval_capacity["max_is_unknown"] is False
    assert analysis["confidence"] == "high_derived"
    assert analysis["limit"] == 75
    assert analysis["derived_limit"] == 75
    assert analysis["status"] == "over"
    assert analysis["over_by"] == 25
    assert analysis["safe_to_claim_over_cap"] is True
    assert analysis["safe_to_claim_penalty"] is True
    assert "Difficulty (cadet)" in analysis["breakdown"]["multiplier_additions"]


def test_get_naval_capacity_downgrades_to_estimated_when_unresolved_sources_exist():
    extractor = DummyPlayerExtractor(
        {
            "used_naval_capacity": "100",
            "fleet_size": "100",
            "government": {"civics": []},
            "traditions": [],
            "ascension_perks": [],
            "active_policies": [
                {"policy": "diplomatic_stance", "selected": "diplo_stance_expansionist"}
            ],
            "edicts": [],
            "flags": {},
            "owned_planets": [],
        },
        resolution_types={"resolution_mutualdefense_enemy_of_my_enemy"},
    )

    naval_capacity = extractor.get_naval_capacity()
    analysis = naval_capacity["analysis"]

    assert naval_capacity["max"] is None
    assert naval_capacity["max_is_unknown"] is True
    assert analysis["confidence"] == "estimated"
    assert analysis["limit"] is None
    assert analysis["derived_limit"] == 75
    assert analysis["status"] == "unknown"
    assert analysis["derived_status"] == "over"
    assert analysis["safe_to_claim_over_cap"] is False
    assert "galactic_community_resolutions" in analysis["unresolved_source_families"]


def test_get_naval_capacity_includes_modeled_job_and_starbase_bonuses():
    extractor = DummyPlayerExtractor(
        {
            "used_naval_capacity": "80",
            "fleet_size": "80",
            "government": {"civics": []},
            "traditions": ["tr_supremacy_adopt"],
            "ascension_perks": ["ap_galactic_force_projection"],
            "active_policies": [
                {"policy": "diplomatic_stance", "selected": "diplo_stance_belligerent"}
            ],
            "edicts": [{"edict": "grand_fleet"}],
            "flags": {},
            "owned_planets": [],
        },
        starbases={
            "starbases": [
                {
                    "modules": ["anchorage", "anchorage"],
                    "buildings": ["naval_logistics_office"],
                }
            ]
        },
        job_analysis={
            "flat_additions": {"Soldier jobs": 6.0},
            "unresolved_source_families": set(),
        },
    )

    naval_capacity = extractor.get_naval_capacity()
    analysis = naval_capacity["analysis"]

    assert analysis["confidence"] == "high_derived"
    assert naval_capacity["max"] == 436
    assert analysis["breakdown"]["flat_additions"]["Anchorages"] == 10.0
    assert analysis["breakdown"]["flat_additions"]["Naval Logistics Office bonus"] == 6.0
    assert analysis["breakdown"]["flat_additions"]["Soldier jobs"] == 6.0
    assert analysis["breakdown"]["flat_additions"]["Tradition (tr_supremacy_adopt)"] == 20.0
    assert (
        analysis["breakdown"]["flat_additions"]["Ascension perk (ap_galactic_force_projection)"]
        == 150.0
    )
    assert (
        analysis["breakdown"]["multiplier_additions"][
            "Diplomatic stance (diplo_stance_belligerent)"
        ]
        == 0.1
    )
    assert analysis["breakdown"]["multiplier_additions"]["Edict (grand_fleet)"] == 0.2
