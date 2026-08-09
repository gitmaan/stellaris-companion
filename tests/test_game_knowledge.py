from pathlib import Path

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


def test_current_stable_uses_exact_compiled_snapshot():
    knowledge = load_game_knowledge("Pegasus v4.4.6 (fdde)")

    assert knowledge.status == "exact"
    assert knowledge.loaded_through == "4.4.6"
    assert "A normal Anchorage adds 5 Naval Capacity" in (knowledge.content or "")
    assert "Typical mid-game empire" not in (knowledge.content or "")
    assert "3:1 rule" not in (knowledge.content or "")


def test_current_snapshot_is_self_sufficient_for_foundational_4x_mechanics():
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


def test_current_snapshot_covers_material_mechanics_from_each_stable_4x_release():
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


def test_new_minor_version_does_not_receive_stale_mechanics():
    knowledge = load_game_knowledge("Cygnus v4.5.0")
    prompt = build_game_knowledge_prompt("Cygnus v4.5.0", purpose="chronicle")

    assert knowledge.status == "unsupported_newer"
    assert knowledge.content is None
    assert "No verified mechanics pack covers Cygnus v4.5.0" in prompt
    assert "A normal Anchorage adds 5 Naval Capacity" not in prompt


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

    assert "Verified mechanics are available through 4.3.5" in prompt
    assert "no topic-specific mechanics section was needed" in prompt
    assert "No verified mechanics pack covers" not in prompt
