"""Applicability is about evidence and the requested subject, not answer wording."""

import json
import re

import pytest

from stellaris_companion.game_knowledge import (
    DEFAULT_PATCHES_DIR,
    build_game_knowledge_prompt,
    load_game_knowledge,
)
from stellaris_companion.knowledge_applicability import (
    APPLICABILITY_PATTERN,
    load_scope_registry,
    parse_scope_registry,
)


@pytest.mark.parametrize("identity", [{}, {"authority": "democratic"}, {"is_nomadic": False}])
@pytest.mark.parametrize("version", ["4.4.4", "4.4.5", "4.4.6", "4.5.2"])
def test_generic_economy_does_not_borrow_unobserved_special_systems(identity, version):
    prompt = build_game_knowledge_prompt(
        version,
        purpose="advisor",
        topics="When will my energy stockpile run out, and what should I investigate first?",
        campaign_identity=identity,
        campaign_metadata={"required_dlcs": ["Nomads"], "required_dlcs_status": "reported"},
    )
    assert "Operational Reserves track" not in prompt
    assert "Operational Reserves start" not in prompt
    assert "Conserve approach imposes" not in prompt
    assert "Arkship Capacity" not in prompt
    assert "the owner's entire Energy stockpile" not in prompt
    assert "Derived values are allowed" in prompt
    assert "does not establish a current unlock" in prompt


@pytest.mark.parametrize("identity", [{}, {"authority": "democratic", "is_nomadic": False}])
def test_comparisons_keep_special_rules_without_assigning_them_to_the_player(identity):
    prompt = build_game_knowledge_prompt(
        "4.4.6",
        purpose="advisor",
        topics="How do Nomad operational reserves compare with an ordinary energy stockpile?",
        campaign_identity=identity,
    )
    assert "Operational Reserves track Energy and Minerals one-to-one" in prompt
    assert "15,000" in prompt
    assert "Scope: Nomadic systems and interactions" in prompt
    assert "conditional reference" in prompt or "comparison or hypothetical reference" in prompt


def test_observed_mode_supports_generic_questions_without_dlc_or_authority_guessing():
    scopes = load_scope_registry(DEFAULT_PATCHES_DIR / "applicability.json")
    scope = scopes["nomadic"]
    assert scope.assess({"is_nomadic": True, "authority": "democratic"}) == "supported"
    assert scope.assess({"is_nomadic": False}) == "contradicted"
    for identity in (
        {},
        {"authority": "democratic"},
        {"origin": "default_nomads"},
        {"is_nomadic": "yes"},
    ):
        assert scope.assess(identity) == "unknown"
    prompt = build_game_knowledge_prompt(
        "4.4.6",
        purpose="advisor",
        topics="How should I interpret negative energy income?",
        campaign_identity={"is_nomadic": True},
    )
    assert "Operational Reserves track" in prompt
    assert "supported by the supplied identity" in prompt


def test_civic_rules_do_not_import_other_civics_but_comparisons_remain_answerable():
    identity = {
        "authority": "machine_intelligence",
        "civics": ["civic_machine_servitor", "machine_replication"],
    }
    prompt = build_game_knowledge_prompt(
        "4.4.6",
        purpose="advisor",
        topics="What do my civics imply for construction and growth?",
        campaign_identity=identity,
    )
    assert "20% Mechanical Pop Assembly Speed" in prompt
    assert "normal start includes 2,000" in prompt
    assert "+25% Ship Weapons Damage" not in prompt
    assert "Colossus Project and Construction" not in prompt
    comparison = build_game_knowledge_prompt(
        "4.4.6",
        purpose="advisor",
        topics="Compare my civics with Determined Exterminator.",
        campaign_identity=identity,
    )
    assert "+25% Ship Weapons Damage" in comparison
    assert "conditional reference" in comparison


def test_unknown_identifiers_do_not_become_applicability_evidence_by_name_similarity():
    scopes = load_scope_registry(DEFAULT_PATCHES_DIR / "applicability.json")
    assert scopes["rogue-servitor"].assess({"civics": ["modded_machine_servitor"]}) == "unknown"
    assert scopes["corporate"].assess({"authority": "modded_corporate"}) == "unknown"
    assert scopes["rogue-servitor"].assess({"civics": []}) == "unknown"
    prompt = build_game_knowledge_prompt(
        "4.4.6",
        purpose="advisor",
        topics="What should I prioritise for my economy?",
        campaign_identity={"civics": ["modded_machine_servitor"]},
    )
    assert "normal start includes 2,000" not in prompt


def test_mixed_sections_retain_general_rules_and_explicit_foreign_mechanics():
    kwargs = {"purpose": "advisor", "campaign_identity": {"authority": "democratic"}}
    economy = build_game_knowledge_prompt("4.4.6", topics="Explain my trade economy.", **kwargs)
    assert "Trade is the Galactic Market currency" in economy
    assert "Branch Offices use Trade" not in economy
    comparison = build_game_knowledge_prompt(
        "4.4.6", topics="How do corporate Branch Offices work?", **kwargs
    )
    assert "Branch Offices use Trade" in comparison
    assert "comparison or hypothetical reference" in comparison


def test_full_reference_keeps_conditions_and_replacements_keep_metadata_attached(tmp_path):
    registry = {
        "format_version": 1,
        "scopes": {
            "test": {
                "label": "Special civic",
                "identity": {"civics": ["special"]},
                "topics": ["special civic"],
            }
        },
    }
    (tmp_path / "applicability.json").write_text(json.dumps(registry))
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    (snapshots / "4.4.4.md").write_text(
        "# Knowledge\n## Economy\n"
        "* **Conversion:** <!-- applies-to: test --> Old scoped rule.\n"
        "  Old continuation.\n"
        "* **Unchanged:** Unrelated general rule.\n"
    )
    (tmp_path / "4.4.5.md").write_text(
        "# Update\n## Economy\n<!-- supersedes-rule: Conversion -->\n"
        "* **Conversion:** New general rule.\n"
    )
    kwargs = {"patches_dir": tmp_path, "snapshots_dir": snapshots}
    old = build_game_knowledge_prompt("4.4.4", purpose="chronicle", **kwargs)
    assert "Old scoped rule" in old
    assert "conditional reference" in old
    for cumulative in (True, False):
        knowledge = load_game_knowledge("4.4.5", cumulative=cumulative, **kwargs)
        assert "New general rule" in knowledge.content
        assert "Old scoped rule" not in knowledge.content
        assert "Old continuation" not in knowledge.content
    current = build_game_knowledge_prompt("4.4.5", purpose="advisor", topics="economy", **kwargs)
    assert "New general rule" in current
    assert "Unrelated general rule" in current
    assert "Scope: Special civic" not in current
    assert "applies-to" not in old + current


def test_missing_registry_omits_scoped_rules_without_breaking_general_advice(tmp_path):
    (tmp_path / "4.4.md").write_text(
        "# Knowledge\n## Economy\n"
        "* **Special:** <!-- applies-to: missing --> Special rule.\n"
        "* **General:** A general economy rule.\n"
    )
    prompt = build_game_knowledge_prompt(
        "4.4",
        purpose="advisor",
        topics="economy",
        patches_dir=tmp_path,
        snapshots_dir=tmp_path / "snapshots",
    )
    assert "Special rule" not in prompt
    assert "general economy rule" in prompt


def test_all_shipped_annotations_reference_valid_scopes_and_never_leak_comments():
    registry = parse_scope_registry(
        json.loads((DEFAULT_PATCHES_DIR / "applicability.json").read_text())
    )
    for scope in registry.values():
        if scope.identity:
            assert scope.assess(scope.identity) == "supported"
    referenced = set()
    for path in [
        *DEFAULT_PATCHES_DIR.glob("*.md"),
        *(DEFAULT_PATCHES_DIR / "snapshots").glob("*.md"),
    ]:
        content = path.read_text()
        annotations = APPLICABILITY_PATTERN.findall(content)
        assert len(annotations) == len(re.findall(r"<!--\s*applies-to:", content)), path
        assert set(annotations) <= registry.keys(), path
        referenced.update(annotations)
    assert referenced == registry.keys()
    for version in ("4.4.4", "4.4.5", "4.4.6", "4.5.2"):
        prompt = build_game_knowledge_prompt(version, purpose="chronicle")
        assert "applies-to" not in prompt
        assert "<!--" not in prompt


@pytest.mark.parametrize(
    "identity,topics",
    [
        ({"unknown": True}, ["topic"]),
        ({"is_nomadic": "yes"}, ["topic"]),
        ({"civics": []}, ["topic"]),
        ({}, [""]),
    ],
)
def test_registry_rejects_ambiguous_or_unsupported_conditions(identity, topics):
    with pytest.raises(ValueError):
        parse_scope_registry(
            {
                "format_version": 1,
                "scopes": {"test": {"label": "Test", "identity": identity, "topics": topics}},
            }
        )
