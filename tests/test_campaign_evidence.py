"""Campaign interpretation must distinguish observation, rules, and missing evidence."""

from __future__ import annotations

import json
from copy import deepcopy

import pytest

from backend.core.model_briefing import build_model_briefing
from stellaris_companion.campaign_evidence import (
    resolve_content_availability,
    resolve_empire_identity,
)
from stellaris_save_extractor.briefing import BriefingMixin
from stellaris_save_extractor.metadata import MetadataMixin


@pytest.mark.parametrize(
    ("version", "integrated"),
    [
        ("Cetus v4.3.5", False),
        ("Cetus v4.3.6 (6ccb)", True),
        ("4.3.7", True),
        ("Pegasus v4.4.6", True),
        ("Cygnus 4.5.2", True),
        ("4.3", False),
        ("unknown", False),
        (None, False),
    ],
)
def test_content_integration_uses_save_version(version, integrated: bool) -> None:
    result = resolve_content_availability({"version": version})
    assert result["base_game_dlcs"] == (
        ["Humanoids", "Synthetic Dawn", "Utopia"] if integrated else []
    )
    assert result["reported_dlcs"] == []
    assert result["unreported_dlc_status"] == "unknown"


@pytest.mark.parametrize(
    ("metadata", "status", "reported"),
    [
        ({}, "not_recorded", []),
        ({"required_dlcs": []}, "not_recorded", []),
        ({"required_dlcs": [], "required_dlcs_status": "reported"}, "reported", []),
        ({"required_dlcs": ["Overlord"]}, "reported", ["Overlord"]),
        ({"required_dlcs": "Overlord"}, "invalid", []),
        ({"required_dlcs": ["Overlord", 1]}, "invalid", []),
        ({"required_dlcs": [" "]}, "invalid", []),
        ({"required_dlcs_status": "reported"}, "invalid", []),
        ({"required_dlcs_status": []}, "invalid", []),
        ({"required_dlcs": [], "required_dlcs_status": "invalid"}, "invalid", []),
        ({"required_dlcs": [], "required_dlcs_status": "not_recorded"}, "not_recorded", []),
    ],
)
def test_missing_empty_and_invalid_dlc_evidence_are_distinct(metadata, status, reported) -> None:
    original = deepcopy(metadata)
    result = resolve_content_availability(metadata)
    assert result["dlc_evidence_status"] == status
    assert result["reported_dlcs"] == reported
    assert metadata == original


@pytest.mark.parametrize(
    ("authority", "civics", "expected_names"),
    [
        (
            "machine_intelligence",
            ["machine_servitor", "machine_replication"],
            ["Rogue Servitor", "Rapid Replicator"],
        ),
        (
            "auth_machine_intelligence",
            ["civic_machine_terminator", "machine_warbots"],
            ["Determined Exterminator", "Warbots"],
        ),
        (
            "machine_intelligence",
            ["machine_assimilator", "machine_builder"],
            ["Driven Assimilator", "Constructobot"],
        ),
        ("hive_mind", ["hive_devouring_swarm", "hive_ascetic"], ["Devouring Swarm", "Ascetic"]),
        ("democratic", ["technocracy", "meritocracy"], ["Technocracy", "Meritocracy"]),
    ],
)
def test_identity_names_preserve_authority_civic_distinction(
    authority, civics, expected_names
) -> None:
    raw = {"authority": authority, "civics": civics}
    original = deepcopy(raw)
    resolved = resolve_empire_identity(raw)
    assert resolved["authority"]["kind"] == "authority"
    assert [civic["name"] for civic in resolved["civics"]] == expected_names
    assert all(civic["kind"] == "civic" for civic in resolved["civics"])
    assert all(civic["source"] == "verified_catalog" for civic in resolved["civics"])
    assert raw == original


def test_identity_unknown_ids_and_separate_kinds_are_not_guessed() -> None:
    result = resolve_empire_identity(
        {
            "authority": "machine_servitor",  # A civic ID is not a known authority.
            "civics": ["civic_modded_servitor", "", None],
            "ethics": ["ethic_fanatic_materialist"],
            "origin": "origin_default",
        }
    )
    assert result["authority"]["name"] == "machine_servitor"
    assert result["authority"]["source"] == "raw_identifier"
    assert result["civics"] == [
        {
            "id": "modded_servitor",
            "name": "modded_servitor",
            "kind": "civic",
            "source": "raw_identifier",
        }
    ]
    assert result["ethics"][0]["name"] == "Fanatic Materialist"
    assert result["origin"]["name"] == "Prosperous Unification"


class MetadataFixture(MetadataMixin):
    def __init__(self, path, meta: str):
        self.save_path = path
        self._meta = meta

    @property
    def meta(self):
        return self._meta


@pytest.mark.parametrize(
    ("block", "expected", "status"),
    [
        ('required_dlcs={ "Overlord" "Nomads" }', ["Overlord", "Nomads"], "reported"),
        ("required_dlcs={} # base-game save", [], "reported"),
        ("# required_dlcs={}\nname=Example", [], "not_recorded"),
        ('required_dlcs={ "Overlord"', [], "invalid"),
        ('required_dlcs={ "Overlord" broken }', [], "invalid"),
        ('required_dlcs={ "" }', [], "invalid"),
        ('required_dlcs={\n# comment\n "Overlord"\n}', ["Overlord"], "reported"),
    ],
)
def test_metadata_records_dlc_parse_evidence(tmp_path, block, expected, status) -> None:
    path = tmp_path / "metadata.sav"
    path.touch()
    extractor = MetadataFixture(path, f'version="Cygnus v4.5.2"\n{block}')
    metadata = extractor.get_metadata()
    assert metadata["required_dlcs"] == expected
    assert metadata["required_dlcs_status"] == status
    assert extractor._parse_required_dlcs() == expected
    assert "Synthetic Dawn" not in extractor.get_missing_dlcs()
    if status != "reported":
        assert extractor.get_missing_dlcs() == []


def test_complete_briefing_persists_dlc_evidence_for_all_consumers(monkeypatch, tmp_path) -> None:
    """Use the real metadata/briefing pipeline with unrelated extraction stubbed out."""
    monkeypatch.setattr("stellaris_save_extractor.briefing._get_active_session", lambda: object())

    class MinimalExtractor(MetadataFixture, BriefingMixin):
        def __getattr__(self, name):
            if name.startswith("get_"):
                return lambda *args, **kwargs: {}
            raise AttributeError(name)

        def _extract_campaign_id(self):
            return "synthetic-campaign"

        def _strip_previews(self, value):
            return value

    path = tmp_path / "metadata.sav"
    path.touch()
    extractor = MinimalExtractor(path, 'version="Cygnus v4.5.2"\nrequired_dlcs={"Overlord"}')

    # Stored briefings and external clients round-trip through JSON, not the
    # worker's separate in-memory metadata payload.
    stored = json.loads(json.dumps(extractor.get_complete_briefing()))
    assert stored["meta"]["required_dlcs"] == ["Overlord"]
    assert stored["meta"]["required_dlcs_status"] == "reported"
    model = build_model_briefing(stored)
    assert model["model_context"]["content_availability"]["reported_dlcs"] == ["Overlord"]


def test_mods_are_told_to_the_advisor_only_when_the_save_names_some() -> None:
    plain = {"version": "Cygnus v4.5.3", "required_dlcs": [], "required_dlcs_status": "reported"}

    unmodded = resolve_content_availability({**plain, "mods": []})
    assert unmodded == resolve_content_availability(plain)
    assert "mods" not in unmodded and "mods_instruction" not in unmodded

    modded = resolve_content_availability({**plain, "mods": ["Gigastructural Engineering", " "]})
    assert modded["mods"] == ["Gigastructural Engineering"]
    assert "describes the unmodded game" in modded["mods_instruction"]
    # Malformed evidence is not turned into a claim.
    assert "mods" not in resolve_content_availability({**plain, "mods": "Gigastructural"})
