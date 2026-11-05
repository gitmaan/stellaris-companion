"""Contracts between save DLC evidence and version-aware content interpretation."""

from __future__ import annotations

import pytest

from stellaris_companion.campaign_evidence import (
    BASE_GAME_DLC_INTEGRATIONS,
    resolve_content_availability,
)
from stellaris_save_extractor.metadata import KNOWN_MAJOR_DLCS


def test_base_game_integrations_are_known_packs() -> None:
    assert set(BASE_GAME_DLC_INTEGRATIONS).issubset(KNOWN_MAJOR_DLCS)


@pytest.mark.parametrize("pack", sorted(KNOWN_MAJOR_DLCS))
def test_reported_pack_is_retained_without_negative_feature_inference(pack: str) -> None:
    result = resolve_content_availability({"version": "4.3.5", "required_dlcs": [pack]})
    assert result["reported_dlcs"] == [pack]
    assert result["base_game_dlcs"] == []
    assert result["unreported_dlc_status"] == "unknown"
