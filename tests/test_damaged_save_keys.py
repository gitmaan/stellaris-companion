"""No key in a save may stop the save from loading, however it is written.

Issue #135: one Fallen Empire's relation entry had no ``relation_current``, a
reader took the key for granted, and the whole save failed to load. Readers are
written by hand, one key at a time, so this test damages every key instead of
trusting each reader: in every synthetic save the other tests build, each key
in turn is removed, written twice, or replaced by the bare value ``none``. The
briefing and the history signals must still be built.

A damaged key may lose the fact it carried. It must not lose the save.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import traceback
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from backend.core.signals import build_snapshot_signals
from stellaris_companion import rust_bridge
from stellaris_save_extractor import SaveExtractor
from tests.report_regressions._synthetic import (
    RECORD_SAVES_ENV,
    SyntheticSession,
    synthetic_meta,
    write_meta_only_save,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS = REPO_ROOT / "tests"
# These run child pytests themselves.
NOT_COLLECTED = {Path(__file__).name, "test_registry.py"}

DAMAGE = ("missing", "written twice", "bare value")


def _modules_that_build_synthetic_saves() -> list[str]:
    return sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in TESTS.rglob("test_*.py")
        if path.name not in NOT_COLLECTED and "_synthetic import" in path.read_text("utf-8")
    )


@pytest.fixture(scope="module")
def saves(tmp_path_factory) -> list[dict[str, Any]]:
    """Every distinct synthetic save the other tests build."""
    recorded = tmp_path_factory.mktemp("synthetic-saves") / "saves.jsonl"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q"]
        + _modules_that_build_synthetic_saves(),
        cwd=REPO_ROOT,
        env={**os.environ, RECORD_SAVES_ENV: str(recorded), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, (result.stdout + result.stderr)[-4000:]
    distinct = dict.fromkeys(recorded.read_text("utf-8").splitlines())
    return [json.loads(line) for line in distinct]


def _keys(value: Any, path: tuple = ()) -> Iterator[tuple]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield (*path, key)
            yield from _keys(child, (*path, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _keys(child, (*path, index))


def _damaged(save: dict[str, Any], path: tuple, damage: str) -> dict[str, Any]:
    save = copy.deepcopy(save)
    parent = save
    for step in path[:-1]:
        parent = parent[step]
    if damage == "missing":
        del parent[path[-1]]
    elif damage == "written twice":
        parent[path[-1]] = [parent[path[-1]], copy.deepcopy(parent[path[-1]])]
    else:
        parent[path[-1]] = "none"
    return save


def _read(save_path: Path, sections: dict[str, Any]) -> str | None:
    """Build the briefing and signals; the line that raised, or None."""
    previous = getattr(rust_bridge._tls, "session", None)
    rust_bridge._tls.session = SyntheticSession(sections)
    try:
        extractor = SaveExtractor(str(save_path))
        briefing = extractor.get_complete_briefing()
        signals = build_snapshot_signals(extractor=extractor, briefing=briefing)
    except Exception as error:
        frame = traceback.extract_tb(error.__traceback__)[-1]
        where = f"{Path(frame.filename).name}:{frame.lineno}"
        return f"{where}  {type(error).__name__}: {error}  |  {frame.line}"
    finally:
        rust_bridge._tls.session = previous
    unread = signals.get("unread")
    return f"history signals not built: {unread}" if unread else None


def test_the_saves_to_damage_were_collected(saves):
    """Guard the guard: an empty collection would pass the test below."""
    assert len(saves) >= 15
    assert sum(1 for save in saves for _ in _keys(save)) >= 1000
    assert {"country", "war", "fleet", "megastructures", "starbase_mgr"} <= {
        section for save in saves for section in save
    }


def test_no_damaged_key_stops_a_save_from_loading(saves, tmp_path, caplog):
    caplog.set_level("CRITICAL")
    save_path = write_meta_only_save(tmp_path / "synthetic.sav", synthetic_meta())

    failures: dict[str, str] = {}
    runs = 0
    for save in saves:
        assert _read(save_path, save) is None, "an undamaged synthetic save must load"
        for path in _keys(save):
            for damage in DAMAGE:
                runs += 1
                problem = _read(save_path, _damaged(save, path, damage))
                if problem:
                    key = "/".join(str(step) for step in path)
                    failures.setdefault(problem, f"{key} {damage}")

    report = "\n".join(
        f"  {problem}\n      first seen with: {case}" for problem, case in failures.items()
    )
    assert not failures, (
        f"{len(failures)} reader(s) failed on a damaged key ({runs} runs):\n{report}"
    )
