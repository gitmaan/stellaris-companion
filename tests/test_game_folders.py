"""Where the app looks for saves, the player's settings and Steam's game libraries."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from stellaris_companion import game_folders
from stellaris_companion.game_folders import documents_dirs, save_dirs, steam_libraries
from stellaris_companion.save_loader import get_platform_save_paths

PARADOX = "Paradox Interactive"
PROTON = (
    "steamapps/compatdata/281990/pfx/drive_c/users/steamuser/Documents/"
    "Paradox Interactive/Stellaris/save games"
)


def test_linux_saves_are_looked_for_natively_in_flatpak_and_under_proton(
    empty_home, monkeypatch
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    assert [path.relative_to(empty_home).as_posix() for path in save_dirs()] == [
        ".local/share/Paradox Interactive/Stellaris/save games",
        ".local/share/Paradox Interactive/Stellaris Plaza/save games",
        ".var/app/com.valvesoftware.Steam/.local/share/Paradox Interactive/Stellaris/save games",
        f".steam/steam/{PROTON}",
        f".local/share/Steam/{PROTON}",
        f".var/app/com.valvesoftware.Steam/data/Steam/{PROTON}",
        f".var/app/com.valvesoftware.Steam/.local/share/Steam/{PROTON}",
        f"snap/steam/common/.local/share/Steam/{PROTON}",
    ]


def test_proton_saves_in_a_steam_library_on_another_drive_are_looked_for(
    empty_home, tmp_path, monkeypatch, add_steam_library
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    library = tmp_path / "Games Drive" / "SteamLibrary"
    add_steam_library(empty_home / ".steam" / "steam", library)

    assert library in steam_libraries()
    assert library.joinpath(*PROTON.split("/")) in save_dirs()


def test_windows_saves_follow_a_documents_folder_moved_into_onedrive(
    empty_home, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    moved = tmp_path / "OneDrive" / "Documents"
    monkeypatch.setattr(
        game_folders,
        "_windows_registry_text",
        lambda key, name: str(moved) if name == "Personal" else None,
    )

    folders = save_dirs()

    assert folders[:3] == [
        moved / PARADOX / "Stellaris" / "save games",
        moved / PARADOX / "Stellaris Plaza" / "save games",
        moved / PARADOX / "Stellaris GamePass" / "save games",
    ]
    # Saves from before the move may still be in the usual place.
    assert empty_home / "Documents" / PARADOX / "Stellaris" / "save games" in folders


@pytest.mark.skipif(sys.platform != "win32", reason="asks Windows itself")
def test_the_documents_folder_is_the_one_windows_reports() -> None:
    import ctypes

    reported = ctypes.create_unicode_buffer(260)
    personal_documents = 5  # CSIDL_PERSONAL
    ctypes.windll.shell32.SHGetFolderPathW(None, personal_documents, None, 0, reported)

    assert documents_dirs()[0] == Path(reported.value)


@pytest.mark.parametrize("platform", ["darwin", "mystery-os"])
def test_other_platforms_keep_saves_under_documents(empty_home, monkeypatch, platform) -> None:
    monkeypatch.setattr(sys, "platform", platform)

    assert save_dirs() == [
        empty_home / "Documents" / PARADOX / "Stellaris" / "save games",
        empty_home / "Documents" / PARADOX / "Stellaris Plaza" / "save games",
    ]


def test_the_save_loader_uses_the_same_folders(empty_home) -> None:
    paths = get_platform_save_paths()
    assert paths == save_dirs()

    paths.clear()  # a caller changing its list changes nobody else's

    assert get_platform_save_paths() == save_dirs() != []
