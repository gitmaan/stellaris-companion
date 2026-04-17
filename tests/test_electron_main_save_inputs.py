from __future__ import annotations

import argparse
from pathlib import Path

from backend.electron_main import resolve_save_inputs


def test_resolve_save_inputs_accepts_directory_via_cli_save_path(tmp_path: Path) -> None:
    save_dir = tmp_path / "save games"
    empire_dir = save_dir / "Test Empire"
    empire_dir.mkdir(parents=True)
    newest_save = empire_dir / "latest.sav"
    newest_save.write_text("new", encoding="utf-8")

    older_save = empire_dir / "older.sav"
    older_save.write_text("old", encoding="utf-8")
    older_save.touch()
    newest_save.touch()

    args = argparse.Namespace(save_path=str(save_dir), host="127.0.0.1", port=8742, parent_pid=None)

    save_file, watch_paths = resolve_save_inputs(args)

    assert save_file == newest_save
    assert watch_paths == [save_dir]
