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
    assert "Every eligible Pop Group on a planet grows simultaneously" in content
    assert "Machine and Organic Assembly can occur simultaneously" in content
    assert "There is no current starbase collection-range" in content
    assert "Heavy Industry" in content
    assert "Focus progression unlocks permanent research options" in content
    assert "Sub-Species Integration" in content


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
    assert "Supplied save observations and recorded events are authoritative" in prompt
    assert "Mods can change baseline mechanics" in prompt
