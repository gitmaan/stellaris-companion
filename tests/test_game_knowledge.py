from pathlib import Path

import pytest

from stellaris_companion.game_knowledge import (
    _find_default_patches_dir,
    build_game_knowledge_prompt,
    load_game_knowledge,
)


def test_patch_resources_resolve_from_pyinstaller_sibling_layout(tmp_path: Path):
    package_dir = tmp_path / "stellaris_companion"
    package_dir.mkdir()
    patches_dir = tmp_path / "patches"
    patches_dir.mkdir()

    assert _find_default_patches_dir(package_dir / "game_knowledge.py") == patches_dir


def test_pegasus_uses_exact_compiled_snapshot():
    knowledge = load_game_knowledge("Pegasus v4.4.6 (fdde)")

    assert knowledge.status == "exact"
    assert knowledge.loaded_through == "4.4.6"
    assert "A normal Anchorage adds 5 Naval Capacity" in (knowledge.content or "")
    assert "Typical mid-game empire" not in (knowledge.content or "")
    assert "3:1 rule" not in (knowledge.content or "")


def test_pegasus_snapshot_is_self_sufficient_for_foundational_4x_mechanics():
    knowledge = load_game_knowledge("Pegasus v4.4.6")
    content = knowledge.content or ""

    assert "Critical 4.x Baseline" in content
    assert "Humanoids Species Pack are integrated into the current base game" in content
    assert "Every eligible Pop Group on a planet grows simultaneously" in content
    assert "Machine and Organic Assembly can occur simultaneously" in content
    assert "There is no current starbase collection-range" in content
    assert "Heavy Industry" in content
    assert "Focus progression unlocks permanent research options" in content
    assert "does not by itself change the draw weights" in content
    assert "Sub-Species Integration" in content


def test_pegasus_snapshot_covers_material_mechanics_through_4_4_6():
    knowledge = load_game_knowledge("Pegasus v4.4.6")
    content = knowledge.content or ""

    assert "logistic pressure cannot reduce growth below 10%" in content
    assert "Research Restriction policies" in content
    assert "Psionic Ascension proceeds through an Ascension Situation" in content
    assert "Gaia Worlds provide +15% Pop Growth" in content
    assert "one pop-limited Assault Army per 100 pops" in content
    assert "non-primary participant can negotiate" in content
    assert "+5% after the first month, +10% after the second" in content
    assert "fully occupied secondary participant does not trigger" in content
    assert "Stellar Cannon is an offensive megastructure" in content
    assert "10,000 is not the minimum needed to fire" in content
    assert "Tier III Arkship can equip the Stellar Engine" in content
    assert "Arkships have inherent 40% habitability" in content
    assert "15,000 + 7,500 + 5,000 = 27,500 capacity" in content
    assert "Critical stage occupies the lowest 5%" in content
    assert "4 Energy upkeep per 100 automated Worker" in content


def test_new_hotfix_uses_honestly_labeled_partial_coverage():
    prompt = build_game_knowledge_prompt("Pegasus v4.4.7", purpose="advisor")

    assert "coverage is verified only through 4.4.6" in prompt
    assert "do not assume older details remained unchanged" in prompt
    assert "Treat these as the current baseline" not in prompt


def test_cygnus_uses_partial_release_notes_without_stale_pegasus_mechanics():
    for version in ("Cygnus v4.5.0", "Cygnus v4.5.1", "Cygnus v4.5.2"):
        knowledge = load_game_knowledge(version)
        prompt = build_game_knowledge_prompt(version, purpose="chronicle")

        assert knowledge.status == "partial"
        assert "rather than splitting into separate groups" in prompt
        assert "Cybernetic Pops gain 10% Job Efficiency" in prompt
        assert "Building a Branch Office costs 75 Influence" in prompt
        assert "The Stellar Cannon is a Tier 3 technology" in prompt
        assert "Temporary Purge Vassals are special subjects" in prompt
        assert "Eligible Deep Scans can reveal anomalies" in prompt
        assert "Only the listed mechanics changes are verified" in prompt
        assert "other mechanics remain unverified" in prompt
        assert "Do not carry forward older-version rules" in prompt
        assert "A normal Anchorage adds 5 Naval Capacity" not in prompt
        assert "grouped for calculation by Species" not in prompt
        assert "Treat these as the current baseline" not in prompt


def test_cygnus_hotfix_only_applies_to_4_5_1_and_later():
    initial = load_game_knowledge("Cygnus v4.5.0")
    hotfix = load_game_knowledge("Cygnus v4.5.1")

    assert "Ships do not automatically disengage" not in (initial.content or "")
    assert "Ships do not automatically disengage" in (hotfix.content or "")
    assert hotfix.loaded_through == "4.5.1"


def test_cygnus_boundary_stays_safe_when_snapshot_resources_are_missing(tmp_path: Path):
    patches_dir = tmp_path / "patches"
    patches_dir.mkdir()
    (patches_dir / "4.4.md").write_text("obsolete Pegasus mechanic", encoding="utf-8")
    (patches_dir / "4.5.md").write_text("Cygnus pop groups", encoding="utf-8")

    knowledge = load_game_knowledge(
        "Cygnus v4.5.0",
        patches_dir=patches_dir,
        snapshots_dir=tmp_path / "missing_snapshots",
    )

    assert knowledge.status == "partial"
    assert knowledge.content == "Cygnus pop groups"


def test_unknown_newer_release_still_does_not_receive_old_mechanics():
    knowledge = load_game_knowledge("v4.6.0")
    prompt = build_game_knowledge_prompt("v4.6.0", purpose="advisor")

    assert knowledge.status == "unsupported_newer"
    assert knowledge.content is None
    assert "No verified mechanics pack covers v4.6.0" in prompt


def test_chronicle_prompt_keeps_mechanics_subordinate_to_recorded_evidence():
    prompt = build_game_knowledge_prompt("Pegasus v4.4.6", purpose="chronicle")

    assert "never as evidence that an event occurred" in prompt
    assert "Do not add a name, identity, participant, place, action" in prompt
    assert "Treat 'not recorded' as a limit of the supplied record" in prompt
    assert "Supplied save observations and recorded events are authoritative" in prompt
    assert "Mods can change baseline mechanics" in prompt


def test_advisor_prompt_does_not_extend_rules_into_unverified_outcomes():
    prompt = build_game_knowledge_prompt("Pegasus v4.4.6", purpose="advisor")

    assert "extend a listed rule into an unstated automatic outcome" in prompt
    assert "Verify arithmetic before using a calculated value" in prompt


def test_topic_focused_prompt_keeps_only_relevant_mechanics_and_guardrails():
    full_prompt = build_game_knowledge_prompt("Pegasus v4.4.6", purpose="advisor")
    focused_prompt = build_game_knowledge_prompt(
        "Pegasus v4.4.6",
        purpose="advisor",
        topics="Should I add anchorages before expanding my fleet and naval capacity?",
    )

    assert "A normal Anchorage adds 5 Naval Capacity" in focused_prompt
    assert "Critical 4.x Baseline" in focused_prompt
    assert "Interpretation Guardrails" in focused_prompt
    assert "Psionics & the Shroud" not in focused_prompt
    assert "Nomadic Empires & Arkships" not in focused_prompt
    assert len(focused_prompt) < len(full_prompt) / 2


def test_topic_focused_prompt_prefers_newer_overlay_sections():
    prompt = build_game_knowledge_prompt(
        "Pegasus v4.4.5",
        purpose="advisor",
        topics="operational reserves, resource abundance, and automation",
    )

    assert "Operational Reserves track Energy and Minerals one-to-one" in prompt
    assert "Resource Abundance slider" in prompt
    assert "uses a 3:1 rule rather than one-to-one conversion" not in prompt
    assert "Automated Science Ships return normally after exploring Astral Rifts" not in prompt


def test_topic_focused_prompt_does_not_misreport_available_older_coverage():
    prompt = build_game_knowledge_prompt(
        "Cetus v4.3.5",
        purpose="advisor",
        topics="What should I prioritize next?",
    )

    assert "Mechanics coverage is exact, through 4.3.5" in prompt
    assert "No topic-specific mechanics section matched" in prompt
    assert "not proof that no rule applies" in prompt
    assert "No verified mechanics pack covers" not in prompt


def test_topic_focused_cygnus_prompt_preserves_partial_coverage_and_filters_sections():
    prompt = build_game_knowledge_prompt(
        "Cygnus v4.5.1",
        purpose="advisor",
        topics="population and factions",
    )

    assert "Only the listed mechanics changes are verified through 4.5.1" in prompt
    assert "rather than splitting into separate groups" in prompt
    assert "Do not carry forward older-version rules" in prompt
    assert "A normal Anchorage adds 5 Naval Capacity" not in prompt
    assert "Building a Branch Office costs 75 Influence" not in prompt
    assert "Treat these as the current baseline" not in prompt


@pytest.mark.parametrize("version", ["4.5.0", "4.5.1", "4.5.2", "4.5.3"])
def test_452_rules_are_version_gated_and_remain_partial(version):
    knowledge = load_game_knowledge(version)

    assert knowledge.status == "partial"
    assert knowledge.notes_only is True
    assert ("-50% Specialist Job Efficiency" in knowledge.content) == (version >= "4.5.2")
    assert (
        knowledge.loaded_through
        == {"4.5.0": "4.5", "4.5.1": "4.5.1", "4.5.2": "4.5.2", "4.5.3": "4.5.2"}[version]
    )
    assert "A normal Anchorage adds 5 Naval Capacity" not in knowledge.content


@pytest.mark.parametrize("version", ["4.5.1", "4.5.2"])
@pytest.mark.parametrize(
    "question",
    [
        "Why do ships disengage after 15 days?",
        "My fleets disappear from combat. What should I do?",
    ],
)
def test_ship_questions_receive_the_existing_disengagement_correction(version, question):
    prompt = build_game_knowledge_prompt(version, purpose="advisor", topics=question)

    assert "Ships do not automatically disengage" in prompt
    assert "15 days" in prompt


def test_question_matches_rule_label_and_body_without_a_matching_heading():
    prompt = build_game_knowledge_prompt(
        "4.5.2", purpose="advisor", topics="How does branch office influence cost work?"
    )

    assert "Building a Branch Office costs 75 Influence" in prompt
    assert "5 Influence per jump" in prompt
    assert "Do not carry forward older-version rules" in prompt


@pytest.mark.parametrize(
    "question,expected",
    [
        (
            "Does Conserve only reduce Bureaucrat and Researcher output?",
            "-50% Specialist Job Efficiency",
        ),
        ("Do armor components have twice the upkeep of shields?", "equal Energy and Alloy upkeep"),
        (
            "Do Fallen Empire buildings automate my Virtual jobs?",
            "provide no automation for Virtual empires",
        ),
        (
            "Can Franchising force another empire to become my subject?",
            "without guaranteeing acceptance",
        ),
        (
            "Can my nomadic Knights detoxify a Toxic Terraforming Candidate?",
            "Taming or slaying the Toxic God",
        ),
    ],
)
def test_452_advice_questions_receive_decision_relevant_rules(question, expected):
    prompt = build_game_knowledge_prompt("4.5.2", purpose="advisor", topics=question)

    assert expected in prompt
    assert "Only the listed mechanics changes are verified through 4.5.2" in prompt


def test_unmatched_cygnus_question_does_not_imply_complete_coverage():
    prompt = build_game_knowledge_prompt(
        "4.5.2", purpose="advisor", topics="What should I prioritize next?"
    )

    assert "Mechanics coverage is partial, through 4.5.2" in prompt
    assert "Do not assume unlisted or older-version mechanics are verified" in prompt
    assert "Treat these as the current baseline" not in prompt


@pytest.fixture
def breaking_boundary_pack(tmp_path):
    patches = tmp_path / "patches"
    snapshots = patches / "snapshots"
    snapshots.mkdir(parents=True)
    (snapshots / "4.4.6.md").write_text("# Pegasus\nobsolete pre-Cygnus rule")
    (patches / "4.5.md").write_text("# Cygnus\nverified Cygnus change")
    (patches / "4.5.1.md").write_text("# Cygnus hotfix\nhotfix correction")
    return {"patches_dir": patches, "snapshots_dir": snapshots}


@pytest.mark.parametrize("future_version", ["4.5.2", "4.6.0"])
@pytest.mark.parametrize("save_version", ["4.5.0", "4.5.1"])
def test_future_snapshot_cannot_reintroduce_pre_boundary_mechanics(
    breaking_boundary_pack, future_version, save_version
):
    paths = breaking_boundary_pack
    (paths["snapshots_dir"] / f"{future_version}.md").write_text("future snapshot")

    knowledge = load_game_knowledge(save_version, **paths)
    prompt = build_game_knowledge_prompt(save_version, purpose="advisor", **paths)

    assert knowledge.status == "partial"
    assert knowledge.notes_only
    assert "verified Cygnus change" in prompt
    assert "obsolete pre-Cygnus rule" not in prompt
    assert "future snapshot" not in prompt
    assert "Only the listed mechanics changes are verified" in prompt
    assert "Treat these as the current baseline" not in prompt
    assert load_game_knowledge("4.4.6", **paths).status == "exact"


@pytest.mark.parametrize("snapshot_kind", ["empty", "comment_only", "unreadable"])
def test_unusable_snapshot_does_not_relax_the_boundary(breaking_boundary_pack, snapshot_kind):
    paths = breaking_boundary_pack
    snapshot = paths["snapshots_dir"] / "4.5.1.md"
    if snapshot_kind == "unreadable":
        snapshot.mkdir()  # Reading a directory raises OSError on every supported platform.
    else:
        snapshot.write_text("" if snapshot_kind == "empty" else "<!-- not audited yet -->")

    knowledge = load_game_knowledge("4.5.1", **paths)
    prompt = build_game_knowledge_prompt("4.5.1", purpose="advisor", **paths)

    assert knowledge.status == "partial"
    assert knowledge.notes_only
    assert "obsolete pre-Cygnus rule" not in prompt
    assert "Only the listed mechanics changes are verified" in prompt


def test_eligible_snapshot_covers_only_that_version_and_later(breaking_boundary_pack):
    paths = breaking_boundary_pack
    (paths["snapshots_dir"] / "4.5.2.md").write_text("complete Cygnus baseline")

    exact = load_game_knowledge("4.5.2", **paths)
    newer = load_game_knowledge("4.5.3", **paths)
    assert exact.status == "exact"
    assert not exact.notes_only
    assert exact.content == "complete Cygnus baseline"
    assert newer.status == "partial"
    assert newer.loaded_through == "4.5.2"
    assert newer.content == exact.content


def test_no_notes_before_future_snapshot_means_no_legacy_fallback(breaking_boundary_pack):
    paths = breaking_boundary_pack
    (paths["patches_dir"] / "4.5.md").unlink()
    (paths["patches_dir"] / "4.5.1.md").unlink()
    (paths["snapshots_dir"] / "4.5.2.md").write_text("future snapshot")

    knowledge = load_game_knowledge("4.5.1", **paths)

    assert knowledge.status == "unavailable"
    assert knowledge.content is None


def test_unknown_release_line_stays_unsupported_even_with_a_later_snapshot(breaking_boundary_pack):
    paths = breaking_boundary_pack
    (paths["snapshots_dir"] / "4.7.md").write_text("future snapshot")

    knowledge = load_game_knowledge("4.6.0", **paths)

    assert knowledge.status == "unsupported_newer"
    assert knowledge.loaded_through == "4.5.1"
    assert knowledge.content is None


def test_explicit_rule_replacement_keeps_unaffected_older_mechanics(tmp_path):
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    (tmp_path / "4.4.4.md").write_text(
        "# Old notes\n### Economy and Reserves\n"
        "* **Conversion:** Energy uses three-to-one conversion.\n"
        "  This continuation is also obsolete.\n"
        "* **Capacity:** Base reserve capacity is 15,000.\n"
    )
    (tmp_path / "4.4.5.md").write_text(
        "# New notes\n### Economy and Reserve Conversion\n"
        "<!-- supersedes-rule: Conversion -->\n"
        "* **Conversion:** Energy uses one-to-one conversion.\n"
    )
    paths = {"patches_dir": tmp_path, "snapshots_dir": snapshots}

    old = load_game_knowledge("4.4.4", **paths)
    prompt = build_game_knowledge_prompt(
        "4.4.5", purpose="advisor", topics="economy reserve conversion and capacity", **paths
    )
    chronicle = build_game_knowledge_prompt("4.4.5", purpose="chronicle", **paths)

    assert "three-to-one" in old.content
    for content in (prompt, chronicle):
        assert "one-to-one" in content
        assert "15,000" in content
        assert "three-to-one" not in content
        assert "continuation is also obsolete" not in content
        assert "supersedes-rule" not in content


def test_headingless_hotfix_body_is_searchable(tmp_path):
    (tmp_path / "4.4.md").write_text(
        "# Release notes\n* **Combat Disengagement:** Ships stay engaged after 15 days."
    )
    prompt = build_game_knowledge_prompt(
        "4.4",
        purpose="advisor",
        topics="Why do ships disengage?",
        patches_dir=tmp_path,
        snapshots_dir=tmp_path / "snapshots",
    )

    assert "Ships stay engaged" in prompt
