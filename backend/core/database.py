"""
SQLite database utilities for Stellaris Companion history (Phase 3).

Milestone 0: schema + migrations + safe initialization.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


DEFAULT_DB_FILENAME = "stellaris_history.db"
ENV_DB_PATH = "STELLARIS_DB_PATH"


@dataclass(frozen=True)
class DatabaseConfig:
    path: Path


def resolve_db_path(db_path: str | Path | None = None) -> Path:
    """Resolve the DB path from explicit arg or environment default."""
    if db_path is None:
        env = os.environ.get(ENV_DB_PATH)
        if env:
            return Path(env).expanduser()
        return Path(DEFAULT_DB_FILENAME)
    return Path(db_path).expanduser()


class GameDatabase:
    """SQLite wrapper for game history storage (sessions/snapshots/events)."""

    def __init__(self, db_path: str | Path | None = None):
        self.path = resolve_db_path(db_path)
        if self.path != Path(":memory:"):
            self.path.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            str(self.path),
            check_same_thread=False,
            isolation_level=None,  # autocommit; we manage explicit transactions
        )
        self._conn.row_factory = sqlite3.Row
        self._configure_connection()
        self.init_schema()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _configure_connection(self) -> None:
        with self._lock:
            self._conn.execute("PRAGMA foreign_keys = ON;")
            self._conn.execute("PRAGMA journal_mode = WAL;")
            self._conn.execute("PRAGMA synchronous = NORMAL;")
            self._conn.execute("PRAGMA busy_timeout = 5000;")

    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, tuple(params))

    def executemany(self, sql: str, rows: Iterable[Iterable[Any]]) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.executemany(sql, rows)

    def commit(self) -> None:
        with self._lock:
            self._conn.commit()

    def get_schema_version(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT version FROM schema_version LIMIT 1;").fetchone()
            return int(row["version"]) if row else 0

    def _set_schema_version(self, version: int) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM schema_version;")
            self._conn.execute(
                "INSERT INTO schema_version (version, updated_at) VALUES (?, strftime('%s','now'));",
                (int(version),),
            )
            self._conn.execute(f"PRAGMA user_version = {int(version)};")

    def init_schema(self) -> None:
        """Create schema and apply migrations (idempotent)."""
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                """
            )
            # Ensure schema_version has a row (version 0) before migrations.
            row = self._conn.execute("SELECT version FROM schema_version LIMIT 1;").fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO schema_version (version, updated_at) VALUES (0, strftime('%s','now'));"
                )
                self._conn.execute("PRAGMA user_version = 0;")

        self.apply_migrations()

    def apply_migrations(self) -> None:
        migrations: dict[int, list[str]] = {
            1: [
                # Sessions: coarse-grained play sessions for an empire/save.
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    save_id TEXT NOT NULL,
                    save_path TEXT,
                    empire_name TEXT,
                    started_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                    ended_at INTEGER,
                    last_game_date TEXT,
                    last_updated_at INTEGER
                );
                """,
                "CREATE INDEX IF NOT EXISTS idx_sessions_save_id ON sessions(save_id);",
                "CREATE INDEX IF NOT EXISTS idx_sessions_started_at ON sessions(started_at);",
                # Snapshots: one row per autosave (or load event).
                """
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    captured_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                    game_date TEXT,
                    save_hash TEXT,

                    -- Timeline metrics (minimal; expand in later milestones)
                    military_power INTEGER,
                    colony_count INTEGER,
                    wars_count INTEGER,
                    energy_net REAL,
                    alloys_net REAL,

                    full_briefing_json TEXT,

                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                );
                """,
                "CREATE INDEX IF NOT EXISTS idx_snapshots_session_captured ON snapshots(session_id, captured_at);",
                "CREATE INDEX IF NOT EXISTS idx_snapshots_session_game_date ON snapshots(session_id, game_date);",
                "CREATE INDEX IF NOT EXISTS idx_snapshots_session_save_hash ON snapshots(session_id, save_hash);",
                # Events: derived deltas for readable history and reports.
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    captured_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                    game_date TEXT,
                    event_type TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    data_json TEXT,

                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                );
                """,
                "CREATE INDEX IF NOT EXISTS idx_events_session_captured ON events(session_id, captured_at);",
                "CREATE INDEX IF NOT EXISTS idx_events_session_type ON events(session_id, event_type);",
            ]
        }

        current = self.get_schema_version()
        target = max(migrations.keys(), default=0)
        if current >= target:
            return

        for next_version in range(current + 1, target + 1):
            statements = migrations.get(next_version)
            if not statements:
                continue
            with self._lock:
                self._conn.execute("BEGIN;")
                try:
                    for stmt in statements:
                        self._conn.execute(stmt)
                    self._set_schema_version(next_version)
                    self._conn.execute("COMMIT;")
                except Exception:
                    self._conn.execute("ROLLBACK;")
                    raise


_default_db: GameDatabase | None = None


def get_default_db(db_path: str | Path | None = None) -> GameDatabase:
    """Get (and initialize) the singleton DB instance.

    If db_path is provided, a separate instance is returned (not cached).
    """
    global _default_db
    if db_path is not None:
        return GameDatabase(db_path=db_path)

    if _default_db is None:
        _default_db = GameDatabase()
    return _default_db
