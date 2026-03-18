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
    _write_patch(patches_dir / "4.9.md", "nine")

    assert personality.get_available_patches() == ["4.2", "4.9", "4.10"]


def test_load_patch_notes_prefers_snapshot_and_appends_newer_deltas(patch_dirs):
    patches_dir, snapshots_dir = patch_dirs
    _write_patch(patches_dir / "4.0.md", "# old\nlegacy-4-0")
    _write_patch(patches_dir / "4.1.md", "legacy-4-1")
    _write_patch(patches_dir / "4.2.md", "legacy-4-2")
    _write_patch(patches_dir / "4.3.md", "<!-- comment -->\ndelta-4-3")
    _write_patch(snapshots_dir / "4.2.md", "# snapshot\ncompiled-through-4-2")

    result = personality.load_patch_notes("Cetus v4.3.0", cumulative=True)

    assert result == "compiled-through-4-2\n\ndelta-4-3"
    assert "legacy-4-0" not in result
    assert "legacy-4-1" not in result
    assert "legacy-4-2" not in result


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
