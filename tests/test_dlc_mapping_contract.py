"""Contract tests to keep DLC metadata and prompt mapping in sync."""

from __future__ import annotations

from stellaris_companion.personality import _DLC_KEY_FEATURES
from stellaris_save_extractor.metadata import KNOWN_MAJOR_DLCS

# Free/non-mechanics entries we intentionally track as "known" but do not
# need negative-feature prompt mappings for strategic advice.
UNMAPPED_ALLOWED_DLCS = {
    "Anniversary Portraits",
    "Horizon Signal",
}


def test_all_mapped_dlcs_exist_in_known_set() -> None:
    assert set(_DLC_KEY_FEATURES).issubset(KNOWN_MAJOR_DLCS)


def test_known_mechanics_dlcs_have_prompt_mappings() -> None:
    expected_mapped = set(KNOWN_MAJOR_DLCS) - UNMAPPED_ALLOWED_DLCS
    actual_mapped = set(_DLC_KEY_FEATURES)

    assert actual_mapped == expected_mapped, (
        f"Missing mappings: {sorted(expected_mapped - actual_mapped)}; "
        f"Unexpected mappings: {sorted(actual_mapped - expected_mapped)}"
    )


def test_mapped_dlc_feature_descriptions_are_non_empty() -> None:
    for dlc_name, features in _DLC_KEY_FEATURES.items():
        assert isinstance(features, str)
        assert features.strip(), f"{dlc_name} has an empty feature mapping"
