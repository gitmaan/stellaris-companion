"""The local real-save check: its own logic, plus a real run when a save is present."""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_local_saves.py"
_spec = importlib.util.spec_from_file_location("check_local_saves", _SCRIPT)
check = importlib.util.module_from_spec(_spec)
sys.modules["check_local_saves"] = check
_spec.loader.exec_module(check)


def _save(path: Path, mtime: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    os.utime(path, (mtime, mtime))
    return path


def test_saves_are_grouped_by_campaign_and_trimmed_to_the_newest(tmp_path):
    root = tmp_path / "save games"
    old = _save(root / "empire_a" / "2200.01.01.sav", 1)
    mid = _save(root / "empire_a" / "2201.01.01.sav", 2)
    new = _save(root / "empire_a" / "autosave.sav", 3)
    other = _save(root / "empire_b" / "2300.01.01.sav", 1)
    _save(root / "_live_feed" / "live.sav", 9)

    assert check.discover_saves([root], per_campaign=2) == {
        "empire_a": [mid, new],
        "empire_b": [other],
    }
    assert check.discover_saves([root], per_campaign=None)["empire_a"] == [old, mid, new]
    assert check.discover_saves([old], per_campaign=2) == {"empire_a": [old]}


def _briefing(**overrides):
    briefing = {
        "meta": {"date": "2250.01.01", "empire_name": "Union", "version": "Pegasus v4.4.6"},
        "identity": {"is_nomadic": False},
        "territory": {"colonies": {"total_count": 4}},
        "economy": {"net_monthly": {}},
        "military": {"military_power": 1},
        "diplomacy": {"relations": []},
        "technology": {"tech_count": 1},
        "history": {"leaders": []},
    }
    briefing.update(overrides)
    return briefing


def test_a_complete_briefing_passes():
    assert check.check_briefing(_briefing()) == ([], [])


def test_missing_core_values_are_errors_and_doubtful_ones_are_warnings():
    errors, warnings = check.check_briefing(
        _briefing(
            meta={"date": "", "empire_name": " "},
            identity={"is_nomadic": None},
            territory={"colonies": {"total_count": 0}},
            military={},
            history={},
        )
    )
    assert errors == [
        "Game date is missing.",
        "Empire name is blank.",
        "Briefing section 'military' is empty.",
    ]
    assert warnings == [
        "Game version is missing.",
        "Couldn't tell whether the empire is Nomadic.",
        "Colony count is 0.",
        "History enrichment is empty.",
    ]


def test_nomads_without_planets_are_not_flagged():
    _, warnings = check.check_briefing(
        _briefing(identity={"is_nomadic": True}, territory={"colonies": {"total_count": 0}})
    )
    assert warnings == []


def test_a_save_newer_than_the_name_catalogs_is_an_error():
    errors, warnings = check.check_name_catalogs(
        _briefing(meta={"date": "2250.01.01", "empire_name": "Union", "version": "Next v99.0.0"})
    )
    assert len(errors) == 1
    assert errors[0].startswith("Save is from Next v99.0.0, newer than the name catalogs (")
    assert "generate_identity_catalog.py" in errors[0]
    assert warnings == []
    # Same or older versions, and unreadable ones, are not flagged.
    assert check.check_name_catalogs(_briefing()) == ([], [])
    assert check.check_name_catalogs(_briefing(meta={"version": "modded build"})) == ([], [])


def test_technology_ids_without_a_catalog_name_are_listed_as_a_warning():
    errors, warnings = check.check_name_catalogs(
        _briefing(
            technology={
                "researched_techs": ["tech_colonization_1", "tech_my_mod_reactor"],
                "in_progress": {"physics": {"tech": "tech_lasers_2"}, "society": None},
                "available_techs": {"physics": ["tech_cryostasis_1", "tech_other_mod_thing"]},
            }
        )
    )
    assert errors == []
    assert warnings == [
        "2 technology IDs have no catalog name (modded, or newer than the catalog): "
        "tech_my_mod_reactor, tech_other_mod_thing"
    ]


def test_an_installed_game_newer_than_the_name_catalogs_is_reported(tmp_path):
    newer, same, broken = tmp_path / "newer", tmp_path / "same", tmp_path / "broken"
    for game_dir, version in ((newer, "Next v99.0.0 (abcd)"), (same, "Pegasus v4.4.6")):
        game_dir.mkdir()
        (game_dir / "launcher-settings.json").write_text(
            f'{{"version": "{version}"}}', encoding="utf-8"
        )
    broken.mkdir()
    (broken / "launcher-settings.json").write_text("not json", encoding="utf-8")

    problem = check.check_installed_game([tmp_path / "missing", broken, newer])
    assert problem.startswith("Installed game is Next v99.0.0 (abcd), but the name catalogs")
    assert check.check_installed_game([same]) is None
    assert check.check_installed_game([tmp_path / "missing", broken]) is None


def _record(level, message):
    return logging.LogRecord("stellaris", level, __file__, 1, message, None, None)


def test_swallowed_pipeline_failures_count_as_errors():
    assert check.is_swallowed_failure(_record(logging.WARNING, "History enrichment error: x"))
    assert check.is_swallowed_failure(_record(logging.ERROR, "anything"))
    assert not check.is_swallowed_failure(_record(logging.WARNING, "Save looks modded"))


def test_a_flood_of_one_event_type_is_flagged():
    events = [{"event_type": "leader_hired"}] * 201 + [{"event_type": "war_started"}]
    assert check.check_events(events) == [
        "201 'leader_hired' events between two saves looks spurious."
    ]


def test_a_real_save_passes_the_whole_pipeline(test_save_path, capsys):
    pytest.importorskip("stellaris_companion.rust_bridge")
    # No game install: this test is about the save, not this machine's catalogs.
    assert check.main([test_save_path, "--game-dir", str(Path(test_save_path).parent)]) == 0
    assert "All 1 saves passed." in capsys.readouterr().out
