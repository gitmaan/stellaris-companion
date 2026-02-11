"""Platform path contract tests for save loader defaults."""

from __future__ import annotations

import sys

from stellaris_companion.save_loader import STELLARIS_SAVE_PATHS, get_platform_save_paths


def test_get_platform_save_paths_returns_copy() -> None:
    original_len = len(STELLARIS_SAVE_PATHS["darwin"])
    paths = get_platform_save_paths()

    paths.append(paths[0])

    assert len(STELLARIS_SAVE_PATHS["darwin"]) == original_len


def test_windows_defaults_include_gamepass_path(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")

    paths = get_platform_save_paths()
    rendered = [p.as_posix() for p in paths]

    assert any("Stellaris/save games" in p for p in rendered)
    assert any("Stellaris Plaza/save games" in p for p in rendered)
    assert any("Stellaris GamePass/save games" in p for p in rendered)


def test_linux_defaults_include_steam_and_flatpak_paths(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    paths = get_platform_save_paths()
    rendered = [p.as_posix() for p in paths]

    assert any(".local/share/Paradox Interactive/Stellaris/save games" in p for p in rendered)
    assert any(
        ".var/app/com.valvesoftware.Steam/.local/share/Paradox Interactive/Stellaris/save games"
        in p
        for p in rendered
    )


def test_unknown_platform_falls_back_to_darwin_defaults(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "mystery-os")

    paths = get_platform_save_paths()

    assert paths == STELLARIS_SAVE_PATHS["darwin"]
