import json
import sqlite3

import pytest

from backend.core.database import GameDatabase


def _add_campaign(
    db: GameDatabase,
    *,
    save_id: str,
    empire_name: str,
    language: str = "en",
    legacy_cache: bool = False,
) -> str:
    session_id = db.create_session(
        save_id=save_id,
        empire_name=empire_name,
        last_game_date="2230.04.12",
    )
    db.insert_snapshot(
        session_id=session_id,
        game_date="2200.01.01",
        save_hash=f"{save_id}-start",
        military_power=100,
        colony_count=1,
        wars_count=0,
        energy_net=5.0,
        alloys_net=2.0,
        full_briefing_json="{}",
        event_state_json="{}",
    )
    db.insert_snapshot(
        session_id=session_id,
        game_date="2230.04.12",
        save_hash=f"{save_id}-latest",
        military_power=500,
        colony_count=4,
        wars_count=1,
        energy_net=12.0,
        alloys_net=8.0,
        full_briefing_json=None,
        event_state_json="{}",
    )
    db.execute(
        """
        INSERT INTO events (session_id, game_date, event_type, summary, data_json)
        VALUES (?, '2220.01.01', 'war_started', 'A war began', '{}');
        """,
        (session_id,),
    )
    chapters = {
        "chapters": [
            {
                "number": 1,
                "title": "First Light",
                "start_date": "2200.01.01",
                "end_date": "2230.04.12",
                "narrative": "The campaign endured.",
                "is_finalized": True,
            }
        ],
        "current_era_cache": {"current_era": {"title": "A New Era"}},
    }
    db.upsert_cached_chronicle(
        session_id,
        f"Chronicle for {empire_name}",
        1,
        2,
        json.dumps(chapters),
        None if legacy_cache else save_id,
        language,
    )
    return session_id


def _cache_rows(db: GameDatabase) -> list[dict[str, object]]:
    rows = db.execute("SELECT * FROM cached_chronicles ORDER BY id;").fetchall()
    return [dict(row) for row in rows]


def test_campaign_metadata_is_additive_and_trash_preserves_chronicles(tmp_path):
    db = GameDatabase(tmp_path / "history.db")
    _add_campaign(db, save_id="alpha", empire_name="Alpha Union")
    before = _cache_rows(db)

    db.set_playthrough_label("alpha", "The First Run")
    db.trash_playthrough("alpha")

    hidden = db.get_playthroughs(include_trashed=False)
    trashed = db.get_playthroughs(include_trashed=True)
    assert hidden == []
    assert trashed[0]["display_name"] == "The First Run"
    assert trashed[0]["is_trashed"] is True
    assert trashed[0]["session_count"] == 1
    assert trashed[0]["snapshot_count"] == 2
    assert trashed[0]["event_count"] == 1
    assert trashed[0]["has_chronicle"] is True
    assert trashed[0]["chapter_count"] == 1
    assert _cache_rows(db) == before

    db.restore_playthrough("alpha")
    assert db.get_playthrough("alpha")["is_trashed"] is False
    assert _cache_rows(db) == before
    db.close()


def test_legacy_session_scoped_chronicle_is_read_without_rewrite(tmp_path):
    db = GameDatabase(tmp_path / "history.db")
    session_id = _add_campaign(
        db,
        save_id="legacy",
        empire_name="Legacy League",
        legacy_cache=True,
    )
    before = _cache_rows(db)

    cached = db.get_cached_chronicle_for_save("legacy")
    campaigns = db.get_playthroughs()

    assert cached is not None
    assert cached["session_id"] == session_id
    assert cached["save_id"] is None
    assert campaigns[0]["has_chronicle"] is True
    assert campaigns[0]["cached_languages"] == ["en"]
    assert _cache_rows(db) == before
    db.close()


def test_chronicle_reset_is_language_scoped_and_exactly_reversible(tmp_path):
    db = GameDatabase(tmp_path / "history.db")
    session_id = _add_campaign(db, save_id="alpha", empire_name="Alpha Union")
    db.upsert_cached_chronicle(
        session_id,
        "Deutsche Chronik",
        3,
        4,
        json.dumps({"chapters": [{"number": 1, "title": "Anfang"}]}),
        "alpha",
        "de",
    )
    before = _cache_rows(db)

    assert db.reset_chronicle("alpha", language="en") == 1
    reset_en = db.get_cached_chronicle_for_save("alpha", language="en")
    untouched_de = db.get_cached_chronicle_for_save("alpha", language="de")
    assert reset_en is not None and reset_en["chronicle_text"] == ""
    assert reset_en["chapters_json"] is None
    assert untouched_de is not None and untouched_de["chronicle_text"] == "Deutsche Chronik"
    assert db.get_playthrough("alpha", language="en")["can_undo_reset"] is True

    assert db.undo_chronicle_reset("alpha", language="en") is True
    assert _cache_rows(db) == before
    assert db.undo_chronicle_reset("alpha", language="en") is False
    db.close()


def test_undo_reset_never_overwrites_newly_generated_content(tmp_path):
    db = GameDatabase(tmp_path / "history.db")
    session_id = _add_campaign(db, save_id="alpha", empire_name="Alpha Union")
    db.reset_chronicle("alpha", language="en")
    db.upsert_cached_chronicle(
        session_id,
        "A newly generated Chronicle",
        4,
        5,
        json.dumps({"chapters": [{"number": 1, "title": "A New History"}]}),
        "alpha",
        "en",
    )

    assert db.get_playthrough("alpha")["can_undo_reset"] is False
    assert db.undo_chronicle_reset("alpha", language="en") is False
    assert db.get_cached_chronicle_for_save("alpha")["chronicle_text"] == (
        "A newly generated Chronicle"
    )
    db.close()


def test_permanent_delete_is_isolated_to_one_campaign(tmp_path):
    db = GameDatabase(tmp_path / "history.db")
    _add_campaign(db, save_id="alpha", empire_name="Alpha Union")
    _add_campaign(db, save_id="beta", empire_name="Beta Combine")
    beta_before = db.get_cached_chronicle_for_save("beta")
    db.execute(
        """
        INSERT INTO advisor_memory (save_id, language, summary_text)
        VALUES ('alpha', 'en', 'Remember Alpha');
        """
    )

    deleted = db.delete_playthrough("alpha")

    assert deleted == {
        "sessions": 1,
        "snapshots": 2,
        "events": 1,
        "chronicle_caches": 1,
    }
    assert db.get_playthrough("alpha") is None
    assert db.get_cached_chronicle_for_save("alpha") is None
    assert db.get_playthrough("beta") is not None
    assert db.get_cached_chronicle_for_save("beta") == beta_before
    assert db.execute("PRAGMA foreign_key_check;").fetchall() == []
    db.close()


def test_upgrade_from_v085_schema_creates_backup_and_preserves_cache_bytes(tmp_path):
    path = tmp_path / "history.db"
    db = GameDatabase(path)
    _add_campaign(db, save_id="alpha", empire_name="Alpha Union")
    before = _cache_rows(db)
    db.execute("DROP TABLE chronicle_revisions;")
    db.execute("DROP TABLE playthrough_metadata;")
    # v0.8.5 shipped schema 9. Recreate that exact boundary before opening the
    # database with the campaign-history release.
    db.execute("UPDATE schema_version SET version = 9;")
    db.execute("PRAGMA user_version = 9;")
    db.close()

    upgraded = GameDatabase(path)
    backup_path = tmp_path / "history.db.pre-v10.backup"

    assert upgraded.get_schema_version() == 10
    assert backup_path.exists()
    assert _cache_rows(upgraded) == before
    with sqlite3.connect(backup_path) as backup:
        backup.row_factory = sqlite3.Row
        backup_rows = [
            dict(row)
            for row in backup.execute("SELECT * FROM cached_chronicles ORDER BY id;").fetchall()
        ]
        assert backup_rows == before
        assert backup.execute("SELECT version FROM schema_version;").fetchone()[0] == 9
    upgraded.close()


def test_upgrade_stops_before_schema_changes_when_safety_backup_fails(tmp_path, monkeypatch):
    path = tmp_path / "history.db"
    db = GameDatabase(path)
    _add_campaign(db, save_id="alpha", empire_name="Alpha Union")
    before = _cache_rows(db)
    db.execute("DROP TABLE chronicle_revisions;")
    db.execute("DROP TABLE playthrough_metadata;")
    db.execute("UPDATE schema_version SET version = 9;")
    db.execute("PRAGMA user_version = 9;")
    db.close()

    def fail_backup(_self, _target_version):
        raise RuntimeError("simulated safety backup failure")

    monkeypatch.setattr(GameDatabase, "_create_pre_migration_backup", fail_backup)
    with pytest.raises(RuntimeError, match="simulated safety backup failure"):
        GameDatabase(path)

    with sqlite3.connect(path) as unchanged:
        unchanged.row_factory = sqlite3.Row
        assert unchanged.execute("SELECT version FROM schema_version;").fetchone()[0] == 9
        assert (
            unchanged.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'playthrough_metadata';"
            ).fetchone()
            is None
        )
        after = [
            dict(row)
            for row in unchanged.execute("SELECT * FROM cached_chronicles ORDER BY id;").fetchall()
        ]
        assert after == before


def test_failed_campaign_history_migration_rolls_back_partial_schema(tmp_path):
    path = tmp_path / "history.db"
    db = GameDatabase(path)
    _add_campaign(db, save_id="alpha", empire_name="Alpha Union")
    before = _cache_rows(db)
    db.execute("DROP TABLE chronicle_revisions;")
    db.execute("DROP TABLE playthrough_metadata;")
    db.execute("UPDATE schema_version SET version = 9;")
    db.execute("PRAGMA user_version = 9;")
    # Migration 10 creates playthrough_metadata first. A conflicting view at the
    # second table name proves that the earlier DDL is rolled back on failure.
    db.execute("CREATE VIEW chronicle_revisions AS SELECT 'blocked' AS value;")
    db.close()

    with pytest.raises(sqlite3.OperationalError):
        GameDatabase(path)

    with sqlite3.connect(path) as unchanged:
        unchanged.row_factory = sqlite3.Row
        assert unchanged.execute("SELECT version FROM schema_version;").fetchone()[0] == 9
        assert (
            unchanged.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'playthrough_metadata';"
            ).fetchone()
            is None
        )
        after = [
            dict(row)
            for row in unchanged.execute("SELECT * FROM cached_chronicles ORDER BY id;").fetchall()
        ]
        assert after == before


def test_backup_is_consistent_and_cannot_replace_live_database(tmp_path):
    path = tmp_path / "history.db"
    db = GameDatabase(path)
    _add_campaign(db, save_id="alpha", empire_name="Alpha Union")
    backup_path = tmp_path / "manual-backup.db"

    result = db.create_backup(backup_path)

    assert result["path"] == str(backup_path)
    assert result["bytes"] > 0
    with sqlite3.connect(backup_path) as backup:
        assert backup.execute("PRAGMA integrity_check;").fetchone()[0] == "ok"
        assert backup.execute("SELECT COUNT(*) FROM sessions;").fetchone()[0] == 1
    with pytest.raises(ValueError, match="must differ"):
        db.create_backup(path)
    db.close()


def test_campaign_manager_handles_hundreds_of_restart_entries(tmp_path):
    db = GameDatabase(tmp_path / "history.db")
    for index in range(600):
        db.create_session(
            save_id=f"restart-{index:04d}",
            empire_name=f"Restart Empire {index:04d}",
            last_game_date="2200.01.01",
        )

    campaigns = db.get_playthroughs(include_trashed=True)
    assert len(campaigns) == 600
    assert all(item["snapshot_count"] == 0 for item in campaigns)
    assert all(item["has_chronicle"] is False for item in campaigns)

    for index in range(0, 600, 2):
        db.trash_playthrough(f"restart-{index:04d}")
    assert len(db.get_playthroughs(include_trashed=False)) == 300
    assert len(db.get_playthroughs(include_trashed=True)) == 600
    assert db.execute("PRAGMA integrity_check;").fetchone()[0] == "ok"
    db.close()


def test_malformed_legacy_chapters_do_not_break_campaign_listing(tmp_path):
    db = GameDatabase(tmp_path / "history.db")
    _add_campaign(db, save_id="legacy", empire_name="Legacy League")
    db.execute(
        "UPDATE cached_chronicles SET chapters_json = '{not valid json' WHERE save_id = 'legacy';"
    )

    campaign = db.get_playthrough("legacy")

    assert campaign is not None
    assert campaign["has_chronicle"] is True
    assert campaign["chapter_count"] == 0
    assert db.get_cached_chronicle_for_save("legacy")["chronicle_text"] == (
        "Chronicle for Legacy League"
    )
    db.close()
