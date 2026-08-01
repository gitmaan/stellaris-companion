from pathlib import Path

import pytest

from stellaris_companion import personality


def _write_patch(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture
def patch_dirs(tmp_path, monkeypatch):
    patches_dir = tmp_path / "patches"
    snapshots_dir = patches_dir / "snapshots"
    monkeypatch.setattr(personality, "PATCHES_DIR", patches_dir)
    monkeypatch.setattr(personality, "PATCH_SNAPSHOTS_DIR", snapshots_dir)
    return patches_dir, snapshots_dir


def test_get_available_patches_sorts_versions_numerically(patch_dirs):
    patches_dir, _ = patch_dirs
    _write_patch(patches_dir / "4.10.md", "ten")
    _write_patch(patches_dir / "4.2.md", "two")
    _write_patch(patches_dir / "4.9.6.md", "nine-six")
    _write_patch(patches_dir / "4.9.md", "nine")

    assert personality.get_available_patches() == ["4.2", "4.9", "4.9.6", "4.10"]


def test_load_patch_notes_prefers_snapshot_and_appends_newer_deltas(patch_dirs):
    patches_dir, snapshots_dir = patch_dirs
    _write_patch(patches_dir / "4.0.md", "# old\nlegacy-4-0")
    _write_patch(patches_dir / "4.1.md", "legacy-4-1")
    _write_patch(patches_dir / "4.2.md", "legacy-4-2")
    _write_patch(patches_dir / "4.3.md", "<!-- comment -->\ndelta-4-3")
    _write_patch(snapshots_dir / "4.2.md", "# snapshot\ncompiled-through-4-2")

    result = personality.load_patch_notes("Cetus v4.3.0", cumulative=True)

    assert result == "# snapshot\ncompiled-through-4-2\n\ndelta-4-3"
    assert "legacy-4-0" not in result
    assert "legacy-4-1" not in result
    assert "legacy-4-2" not in result


def test_load_patch_notes_appends_44_delta_after_43_snapshot(patch_dirs):
    patches_dir, snapshots_dir = patch_dirs
    _write_patch(patches_dir / "4.3.md", "stale-4-3-delta")
    _write_patch(patches_dir / "4.4.md", "stable-pegasus-delta")
    _write_patch(snapshots_dir / "4.3.md", "compiled-through-4-3")

    result = personality.load_patch_notes("Pegasus v4.4.3", cumulative=True)

    assert result == "compiled-through-4-3\n\nstable-pegasus-delta"
    assert "stale-4-3-delta" not in result


def test_exact_patch_overlays_apply_only_at_or_after_their_version(patch_dirs):
    patches_dir, snapshots_dir = patch_dirs
    _write_patch(snapshots_dir / "4.3.md", "compiled-through-4-3")
    _write_patch(patches_dir / "4.4.md", "base-4-4")
    _write_patch(patches_dir / "4.4.4.md", "overlay-4-4-4")
    _write_patch(patches_dir / "4.4.5.md", "overlay-4-4-5")
    _write_patch(patches_dir / "4.4.6.md", "overlay-4-4-6")

    result_443 = personality.load_patch_notes("Pegasus v4.4.3")
    result_444 = personality.load_patch_notes("Pegasus v4.4.4")
    result_445 = personality.load_patch_notes("Pegasus v4.4.5")
    result_446 = personality.load_patch_notes("Pegasus v4.4.6")

    assert result_443 == "compiled-through-4-3\n\nbase-4-4"
    assert result_444.endswith("base-4-4\n\noverlay-4-4-4")
    assert "overlay-4-4-5" not in result_444
    assert result_445.endswith("base-4-4\n\noverlay-4-4-4\n\noverlay-4-4-5")
    assert "overlay-4-4-6" not in result_445
    assert result_446.endswith("base-4-4\n\noverlay-4-4-4\n\noverlay-4-4-5\n\noverlay-4-4-6")


def test_non_cumulative_loading_keeps_base_and_same_line_overlays(patch_dirs):
    patches_dir, _ = patch_dirs
    _write_patch(patches_dir / "4.3.md", "other-minor")
    _write_patch(patches_dir / "4.4.md", "base-4-4")
    _write_patch(patches_dir / "4.4.4.md", "overlay-4-4-4")
    _write_patch(patches_dir / "4.4.5.md", "overlay-4-4-5")

    result = personality.load_patch_notes("Pegasus v4.4.4", cumulative=False)

    assert result == "base-4-4\n\noverlay-4-4-4"


def test_bundled_pegasus_overlays_distinguish_444_445_and_446():
    result_444 = personality.load_patch_notes("Pegasus v4.4.4", cumulative=False)
    result_445 = personality.load_patch_notes("Pegasus v4.4.5", cumulative=False)
    result_446 = personality.load_patch_notes("Pegasus v4.4.6", cumulative=False)

    assert "Arkships have inherent 40% habitability" in result_444
    assert "uses a 3:1 rule rather than one-to-one conversion" in result_444
    assert "Operational Reserves track Energy and Minerals one-to-one" not in result_444
    assert "Resource Abundance slider" not in result_444

    assert "Operational Reserves track Energy and Minerals one-to-one" in result_445
    assert "Resource Abundance slider" in result_445
    assert "Automated Science Ships return normally after exploring Astral Rifts" not in result_445

    assert "Automated Science Ships return normally after exploring Astral Rifts" in result_446


def test_load_patch_notes_handles_two_digit_minor_versions(patch_dirs):
    patches_dir, _ = patch_dirs
    _write_patch(patches_dir / "4.9.md", "delta-4-9")
    _write_patch(patches_dir / "4.10.md", "delta-4-10")

    result = personality.load_patch_notes("Hydra v4.10.1", cumulative=True)

    assert result == "delta-4-9\n\ndelta-4-10"


def test_load_patch_notes_non_cumulative_ignores_snapshots(patch_dirs):
    patches_dir, snapshots_dir = patch_dirs
    _write_patch(patches_dir / "4.3.md", "delta-only")
    _write_patch(snapshots_dir / "4.3.md", "snapshot-only")

    result = personality.load_patch_notes("Cetus v4.3.0", cumulative=False)

    assert result == "delta-only"


def test_cleaned_knowledge_preserves_headings_and_removes_comments(patch_dirs):
    patches_dir, _ = patch_dirs
    _write_patch(
        patches_dir / "4.4.md",
        "# Current mechanics\n<!-- maintainer note -->\n## Economy\n* Trade is currency.",
    )

    result = personality.load_patch_notes("Pegasus v4.4", cumulative=False)

    assert result == "# Current mechanics\n\n## Economy\n* Trade is currency."
