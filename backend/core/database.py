"""
SQLite database utilities for Stellaris Companion history (Phase 3).

Milestone 0: schema + migrations + safe initialization.
"""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import threading
import time
import uuid
from collections.abc import Iterable
from contextlib import nullcontext
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.core.chronicle_store import (
    ChronicleConflict,
    assemble_chronicle,
    chronicle_revision,
    load_chapters_data,
)
from backend.core.events import compute_events
from backend.core.json_utils import json_dumps

DEFAULT_DB_FILENAME = "stellaris_history.db"
ENV_DB_PATH = "STELLARIS_DB_PATH"
PRE_CAMPAIGN_HISTORY_SCHEMA_VERSION = 10

# Default DB retention (no user-facing knobs).
# Keep the earliest full briefing (baseline). The latest briefing is stored on the session row
# (see `sessions.latest_briefing_json`) to avoid writing a large JSON blob per snapshot.
DEFAULT_KEEP_FULL_BRIEFINGS_RECENT = 0


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

    @contextlib.contextmanager
    def transaction(self, *, immediate: bool = False) -> Iterable[GameDatabase]:
        """Hold the connection lock for one explicit atomic transaction.

        ``BEGIN IMMEDIATE`` is useful for read-modify-write operations that must
        compare a revision and persist a replacement without another writer
        slipping in between those steps.
        """
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE;" if immediate else "BEGIN;")
            try:
                yield self
            except BaseException:
                self._conn.rollback()
                raise
            else:
                self._conn.commit()

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
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                """)
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
            ],
            2: [
                # Store the latest full briefing JSON on the session row (one per session),
                # so we don't write a large blob per snapshot.
                "ALTER TABLE sessions ADD COLUMN latest_briefing_json TEXT;",
                # Store a compact per-snapshot state used for event generation/reporting, even if
                # full_briefing_json is not retained.
                "ALTER TABLE snapshots ADD COLUMN event_state_json TEXT;",
            ],
            3: [
                # Chronicle cache table for LLM-generated narratives
                """
                CREATE TABLE IF NOT EXISTS cached_chronicles (
                    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
                    session_id TEXT NOT NULL,
                    chronicle_text TEXT NOT NULL,
                    chapters_json TEXT,
                    event_count INTEGER NOT NULL,
                    snapshot_count INTEGER NOT NULL,
                    generated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(session_id),
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                );
                """,
                "CREATE INDEX IF NOT EXISTS idx_cached_chronicles_session ON cached_chronicles(session_id);",
            ],
            4: [
                # Add save_id for cross-session chronicle continuity
                "ALTER TABLE cached_chronicles ADD COLUMN save_id TEXT;",
                "CREATE INDEX IF NOT EXISTS idx_cached_chronicles_save ON cached_chronicles(save_id);",
            ],
            5: [
                # Per-playthrough advisor customization (player-provided prompt layer).
                "ALTER TABLE sessions ADD COLUMN advisor_custom_instructions TEXT;",
            ],
            6: [
                # Per-playthrough chronicle narrator customization (player-provided prompt layer).
                "ALTER TABLE cached_chronicles ADD COLUMN chronicle_custom_instructions TEXT;",
            ],
            7: [
                # Save-scoped compact advisor memory for cross-restart continuity.
                """
                CREATE TABLE IF NOT EXISTS advisor_memory (
                    save_id TEXT PRIMARY KEY,
                    summary_text TEXT,
                    last_game_date TEXT,
                    updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
                );
                """,
                "CREATE INDEX IF NOT EXISTS idx_advisor_memory_updated ON advisor_memory(updated_at);",
            ],
            8: [
                # Language-scope chronicle caches so changing UI language does not
                # reuse prose generated in a different language.
                """
                CREATE TABLE cached_chronicles_new (
                    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
                    session_id TEXT NOT NULL DEFAULT '',
                    save_id TEXT,
                    language TEXT NOT NULL DEFAULT 'en',
                    chronicle_text TEXT NOT NULL,
                    chapters_json TEXT,
                    event_count INTEGER NOT NULL,
                    snapshot_count INTEGER NOT NULL,
                    generated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    chronicle_custom_instructions TEXT
                );
                """,
                """
                INSERT INTO cached_chronicles_new
                    (id, session_id, save_id, language, chronicle_text, chapters_json,
                     event_count, snapshot_count, generated_at, chronicle_custom_instructions)
                SELECT
                    id, session_id, save_id, 'en', chronicle_text, chapters_json,
                    event_count, snapshot_count, generated_at, chronicle_custom_instructions
                FROM cached_chronicles;
                """,
                "DROP TABLE cached_chronicles;",
                "ALTER TABLE cached_chronicles_new RENAME TO cached_chronicles;",
                "CREATE INDEX IF NOT EXISTS idx_cached_chronicles_session ON cached_chronicles(session_id);",
                "CREATE INDEX IF NOT EXISTS idx_cached_chronicles_save ON cached_chronicles(save_id);",
                "CREATE INDEX IF NOT EXISTS idx_cached_chronicles_save_language ON cached_chronicles(save_id, language);",
            ],
            9: [
                # Language-scope advisor memory so prior generated advice does not
                # leak into prompts for another output language.
                """
                CREATE TABLE advisor_memory_new (
                    save_id TEXT NOT NULL,
                    language TEXT NOT NULL DEFAULT 'en',
                    summary_text TEXT,
                    last_game_date TEXT,
                    updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                    PRIMARY KEY (save_id, language)
                );
                """,
                """
                INSERT INTO advisor_memory_new
                    (save_id, language, summary_text, last_game_date, updated_at)
                SELECT save_id, 'en', summary_text, last_game_date, updated_at
                FROM advisor_memory;
                """,
                "DROP TABLE advisor_memory;",
                "ALTER TABLE advisor_memory_new RENAME TO advisor_memory;",
                "CREATE INDEX IF NOT EXISTS idx_advisor_memory_updated ON advisor_memory(updated_at);",
            ],
            10: [
                # Additive playthrough management state. Existing Chronicle/history rows are
                # deliberately left untouched so upgrading cannot rewrite user prose.
                """
                CREATE TABLE IF NOT EXISTS playthrough_metadata (
                    save_id TEXT PRIMARY KEY,
                    display_label TEXT,
                    trashed_at INTEGER,
                    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                    updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
                );
                """,
                "CREATE INDEX IF NOT EXISTS idx_playthrough_metadata_trashed ON playthrough_metadata(trashed_at);",
                # Reversible backups for explicit Chronicle resets. Trash/restore never touches
                # Chronicle rows and therefore does not need a content backup.
                """
                CREATE TABLE IF NOT EXISTS chronicle_revisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    save_id TEXT NOT NULL,
                    language TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
                );
                """,
                "CREATE INDEX IF NOT EXISTS idx_chronicle_revisions_save_language ON chronicle_revisions(save_id, language, created_at DESC);",
            ],
            11: [
                # Completed Advisor exchanges are an archive, separate from bounded prompt memory.
                """
                CREATE TABLE advisor_conversations (
                    id TEXT PRIMARY KEY,
                    save_id TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                """,
                "CREATE INDEX idx_advisor_conversations_save ON advisor_conversations(save_id, updated_at DESC);",
                """
                CREATE TABLE advisor_turns (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES advisor_conversations(id) ON DELETE CASCADE,
                    save_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    language TEXT NOT NULL,
                    game_date TEXT,
                    source_hash TEXT,
                    snapshot_id INTEGER,
                    created_at REAL NOT NULL,
                    response_json TEXT NOT NULL,
                    UNIQUE(save_id, request_id)
                );
                """,
                "CREATE INDEX idx_advisor_turns_conversation ON advisor_turns(conversation_id, created_at);",
            ],
        }

        current = self.get_schema_version()
        target = max(migrations.keys(), default=0)
        if current >= target:
            return

        if 0 < current < PRE_CAMPAIGN_HISTORY_SCHEMA_VERSION <= target:
            self._create_pre_migration_backup(PRE_CAMPAIGN_HISTORY_SCHEMA_VERSION)

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

    def _create_pre_migration_backup(self, target_version: int) -> Path | None:
        """Create and verify a WAL-safe backup before campaign-history migration.

        A failed safety backup must stop the migration. Continuing would make the
        nominally additive upgrade harder to recover from if the host is already
        experiencing a full disk, permissions issue, or SQLite corruption.
        """
        if self.path == Path(":memory:"):
            return None
        backup_path = self.path.with_name(f"{self.path.name}.pre-v{int(target_version)}.backup")
        pending_path = backup_path.with_name(f".{backup_path.name}.{uuid.uuid4().hex}.tmp")
        try:
            backup_conn = sqlite3.connect(str(pending_path))
            try:
                with self._lock:
                    self._conn.backup(backup_conn)
                integrity = backup_conn.execute("PRAGMA integrity_check;").fetchone()
                if integrity is None or str(integrity[0]).lower() != "ok":
                    detail = str(integrity[0]) if integrity else "no integrity result"
                    raise sqlite3.DatabaseError(f"backup integrity check failed: {detail}")
            finally:
                backup_conn.close()
            os.replace(pending_path, backup_path)
            return backup_path
        except Exception as exc:
            with contextlib.suppress(OSError):
                pending_path.unlink()
            raise RuntimeError(
                "Could not create and verify the campaign-history safety backup. "
                "The database upgrade was stopped before changing existing campaign data. "
                "Check available disk space and app-data folder permissions, then reopen the app."
            ) from exc

    # --- Phase 3 Milestone 1: sessions + snapshot writes ---

    def get_active_session_id(self, save_id: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT id
                FROM sessions
                WHERE save_id = ? AND ended_at IS NULL
                ORDER BY started_at DESC
                LIMIT 1;
                """,
                (save_id,),
            ).fetchone()
            return str(row["id"]) if row else None

    def create_session(
        self,
        *,
        save_id: str,
        save_path: str | None = None,
        empire_name: str | None = None,
        last_game_date: str | None = None,
    ) -> str:
        session_id = uuid.uuid4().hex
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO sessions (id, save_id, save_path, empire_name, last_game_date, last_updated_at)
                VALUES (?, ?, ?, ?, ?, strftime('%s','now'));
                """,
                (session_id, save_id, save_path, empire_name, last_game_date),
            )
        return session_id

    def get_or_create_active_session(
        self,
        *,
        save_id: str,
        save_path: str | None = None,
        empire_name: str | None = None,
        last_game_date: str | None = None,
    ) -> str:
        existing = self.get_active_session_id(save_id)
        if existing:
            self.update_session(
                session_id=existing,
                save_path=save_path,
                empire_name=empire_name,
                last_game_date=last_game_date,
            )
            return existing
        return self.create_session(
            save_id=save_id,
            save_path=save_path,
            empire_name=empire_name,
            last_game_date=last_game_date,
        )

    def update_session(
        self,
        *,
        session_id: str,
        save_path: str | None = None,
        empire_name: str | None = None,
        last_game_date: str | None = None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE sessions
                SET
                    save_path = COALESCE(?, save_path),
                    empire_name = COALESCE(?, empire_name),
                    last_game_date = COALESCE(?, last_game_date),
                    last_updated_at = strftime('%s','now')
                WHERE id = ?;
                """,
                (save_path, empire_name, last_game_date, session_id),
            )

    def update_session_latest_briefing(
        self,
        *,
        session_id: str,
        latest_briefing_json: str,
        last_game_date: str | None = None,
    ) -> None:
        """Persist the latest full briefing JSON for a session (single row overwrite).

        This is used as the primary persistence mechanism for precomputed ask mode
        across restarts, without storing a large blob on every snapshot row.
        """
        with self._lock:
            self._conn.execute(
                """
                UPDATE sessions
                SET
                    latest_briefing_json = ?,
                    last_game_date = COALESCE(?, last_game_date),
                    last_updated_at = strftime('%s','now')
                WHERE id = ?;
                """,
                (latest_briefing_json, last_game_date, session_id),
            )

    def get_session_advisor_custom(self, *, session_id: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT advisor_custom_instructions
                FROM sessions
                WHERE id = ?
                LIMIT 1;
                """,
                (session_id,),
            ).fetchone()
            if not row:
                return None
            value = row["advisor_custom_instructions"]
            return str(value) if isinstance(value, str) and value.strip() else None

    def update_session_advisor_custom(self, *, session_id: str, text: str | None) -> None:
        value = (text or "").strip()
        value = value[:300]
        with self._lock:
            self._conn.execute(
                """
                UPDATE sessions
                SET
                    advisor_custom_instructions = ?,
                    last_updated_at = strftime('%s','now')
                WHERE id = ?;
                """,
                (value if value else None, session_id),
            )

    def backfill_session_latest_briefing_from_snapshots(self, *, session_id: str) -> bool:
        """Populate sessions.latest_briefing_json from the newest snapshot full briefing (best-effort).

        This is used when upgrading older DBs that stored full_briefing_json on snapshot rows.
        """
        with self._lock:
            row = self._conn.execute(
                """
                SELECT full_briefing_json, game_date
                FROM snapshots
                WHERE session_id = ?
                  AND full_briefing_json IS NOT NULL
                  AND full_briefing_json != ''
                ORDER BY captured_at DESC, id DESC
                LIMIT 1;
                """,
                (session_id,),
            ).fetchone()
            if not row:
                return False
            latest_json = row["full_briefing_json"]
            if not latest_json:
                return False
            self._conn.execute(
                """
                UPDATE sessions
                SET
                    latest_briefing_json = ?,
                    last_game_date = COALESCE(?, last_game_date),
                    last_updated_at = strftime('%s','now')
                WHERE id = ?;
                """,
                (str(latest_json), row["game_date"], session_id),
            )
            return True

    def backfill_latest_briefings_all_sessions(self, *, limit_sessions: int = 500) -> int:
        """Backfill sessions.latest_briefing_json for many sessions (best-effort)."""
        lim = max(1, min(int(limit_sessions), 5000))
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id
                FROM sessions
                WHERE latest_briefing_json IS NULL OR latest_briefing_json = ''
                ORDER BY COALESCE(last_updated_at, started_at) DESC
                LIMIT ?;
                """,
                (lim,),
            ).fetchall()
        updated = 0
        for r in rows:
            sid = str(r["id"])
            try:
                if self.backfill_session_latest_briefing_from_snapshots(session_id=sid):
                    updated += 1
            except Exception:
                continue
        return updated

    def get_latest_session_briefing_json(self, *, session_id: str) -> str | None:
        """Return the latest full briefing JSON stored on the session row."""
        with self._lock:
            row = self._conn.execute(
                """
                SELECT latest_briefing_json
                FROM sessions
                WHERE id = ?
                LIMIT 1;
                """,
                (session_id,),
            ).fetchone()
            if not row:
                return None
            value = row["latest_briefing_json"]
            return str(value) if value else None

    def get_latest_session_briefing_json_any(self) -> str | None:
        """Return the latest full briefing JSON across all sessions (best-effort)."""
        with self._lock:
            row = self._conn.execute("""
                SELECT latest_briefing_json
                FROM sessions
                WHERE latest_briefing_json IS NOT NULL AND latest_briefing_json != ''
                ORDER BY COALESCE(last_updated_at, started_at) DESC
                LIMIT 1;
                """).fetchone()
            if not row:
                return None
            value = row["latest_briefing_json"]
            return str(value) if value else None

    def get_latest_snapshot_identity(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT id, captured_at, game_date, save_hash
                FROM snapshots
                WHERE session_id = ?
                ORDER BY captured_at DESC, id DESC
                LIMIT 1;
                """,
                (session_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_latest_snapshot_full_briefing_json(self, *, session_id: str) -> str | None:
        """Return the most recent snapshot JSON for a session (newest-first)."""
        with self._lock:
            row = self._conn.execute(
                """
                SELECT full_briefing_json
                FROM snapshots
                WHERE session_id = ?
                ORDER BY captured_at DESC, id DESC
                LIMIT 1;
                """,
                (session_id,),
            ).fetchone()
            if not row:
                return None
            value = row["full_briefing_json"]
            return str(value) if value else None

    def get_latest_snapshot_full_briefing_json_any(self) -> str | None:
        """Return the most recent snapshot JSON across all sessions."""
        with self._lock:
            row = self._conn.execute("""
                SELECT full_briefing_json
                FROM snapshots
                WHERE full_briefing_json IS NOT NULL AND full_briefing_json != ''
                ORDER BY captured_at DESC, id DESC
                LIMIT 1;
                """).fetchone()
            if not row:
                return None
            value = row["full_briefing_json"]
            return str(value) if value else None

    def insert_snapshot(
        self,
        *,
        session_id: str,
        game_date: str | None,
        save_hash: str | None,
        military_power: int | None,
        colony_count: int | None,
        wars_count: int | None,
        energy_net: float | None,
        alloys_net: float | None,
        full_briefing_json: str | None,
        event_state_json: str | None,
    ) -> int:
        with self._lock:
            cur = self._conn.execute(
                """
                INSERT INTO snapshots (
                    session_id,
                    game_date,
                    save_hash,
                    military_power,
                    colony_count,
                    wars_count,
                    energy_net,
                    alloys_net,
                    full_briefing_json,
                    event_state_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    session_id,
                    game_date,
                    save_hash,
                    military_power,
                    colony_count,
                    wars_count,
                    energy_net,
                    alloys_net,
                    full_briefing_json,
                    event_state_json,
                ),
            )
            return int(cur.lastrowid)

    def insert_snapshot_if_new(
        self,
        *,
        session_id: str,
        game_date: str | None,
        save_hash: str | None,
        military_power: int | None,
        colony_count: int | None,
        wars_count: int | None,
        energy_net: float | None,
        alloys_net: float | None,
        full_briefing_json: str | None,
        event_state_json: str | None,
    ) -> tuple[bool, int | None]:
        latest = self.get_latest_snapshot_identity(session_id)
        if latest:
            latest_hash = latest.get("save_hash")
            latest_date = latest.get("game_date")
            if save_hash and latest_hash == save_hash:
                # Keep session recency metadata moving forward even when
                # dedupe drops a duplicate snapshot row.
                if game_date:
                    self.update_session(session_id=session_id, last_game_date=game_date)
                return False, None
            if (save_hash is None) and game_date and latest_date == game_date:
                self.update_session(session_id=session_id, last_game_date=game_date)
                return False, None

        # Retain the small Chronicle context at every dated snapshot. Full briefings
        # remain baseline-only; legacy rows without this context are not backfilled.
        if full_briefing_json:
            from backend.core.chronicle_store import compact_chronicle_context

            try:
                state = json.loads(event_state_json or "{}")
                briefing = json.loads(full_briefing_json)
                if isinstance(state, dict) and isinstance(briefing, dict):
                    state["chronicle_context"] = compact_chronicle_context(briefing)
                    event_state_json = json_dumps(state)
            except (ValueError, TypeError):
                pass

        # Only keep a full per-snapshot briefing for the baseline snapshot (first one in session).
        baseline_full = full_briefing_json if latest is None else None

        snapshot_id = self.insert_snapshot(
            session_id=session_id,
            game_date=game_date,
            save_hash=save_hash,
            military_power=military_power,
            colony_count=colony_count,
            wars_count=wars_count,
            energy_net=energy_net,
            alloys_net=alloys_net,
            full_briefing_json=baseline_full,
            event_state_json=event_state_json,
        )
        self.update_session(session_id=session_id, last_game_date=game_date)
        return True, snapshot_id

    def enforce_full_briefing_retention(
        self,
        *,
        session_id: str,
        keep_recent: int = DEFAULT_KEEP_FULL_BRIEFINGS_RECENT,
        keep_first: bool = True,
    ) -> int:
        """Keep disk bounded by clearing full briefing JSON on older snapshots.

        This preserves lightweight metric rows and derived events, but removes large
        per-snapshot JSON blobs except for:
          - the earliest snapshot (baseline), if keep_first=True
          - the most recent `keep_recent` snapshots
        """
        keep_n = max(0, min(int(keep_recent), 500))

        ids_to_keep: set[int] = set()
        with self._lock:
            if keep_first:
                first = self._conn.execute(
                    """
                    SELECT id
                    FROM snapshots
                    WHERE session_id = ?
                      AND full_briefing_json IS NOT NULL
                      AND full_briefing_json != ''
                    ORDER BY captured_at ASC, id ASC
                    LIMIT 1;
                    """,
                    (session_id,),
                ).fetchone()
                if first:
                    ids_to_keep.add(int(first["id"]))

            if keep_n > 0:
                rows = self._conn.execute(
                    """
                    SELECT id
                    FROM snapshots
                    WHERE session_id = ?
                      AND full_briefing_json IS NOT NULL
                      AND full_briefing_json != ''
                    ORDER BY captured_at DESC, id DESC
                    LIMIT ?;
                    """,
                    (session_id, keep_n),
                ).fetchall()
                ids_to_keep.update(int(r["id"]) for r in rows)

            if not ids_to_keep:
                cur = self._conn.execute(
                    """
                    UPDATE snapshots
                    SET full_briefing_json = NULL
                    WHERE session_id = ?
                      AND full_briefing_json IS NOT NULL
                      AND full_briefing_json != '';
                    """,
                    (session_id,),
                )
                return int(cur.rowcount or 0)

            placeholders = ",".join(["?"] * len(ids_to_keep))
            params: list[Any] = [session_id, *sorted(ids_to_keep)]
            cur = self._conn.execute(
                f"""
                UPDATE snapshots
                SET full_briefing_json = NULL
                WHERE session_id = ?
                  AND full_briefing_json IS NOT NULL
                  AND full_briefing_json != ''
                  AND id NOT IN ({placeholders});
                """,
                tuple(params),
            )
            return int(cur.rowcount or 0)

    def enforce_full_briefing_retention_all_sessions(
        self,
        *,
        keep_recent: int = DEFAULT_KEEP_FULL_BRIEFINGS_RECENT,
        keep_first: bool = True,
        limit_sessions: int = 500,
    ) -> int:
        """Best-effort maintenance: apply full-briefing retention to many sessions.

        This helps older DBs that accumulated per-snapshot full JSON before retention rules
        were tightened.
        """
        lim = max(1, min(int(limit_sessions), 5000))
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id
                FROM sessions
                ORDER BY COALESCE(last_updated_at, started_at) DESC
                LIMIT ?;
                """,
                (lim,),
            ).fetchall()
        total_cleared = 0
        for r in rows:
            sid = str(r["id"])
            try:
                total_cleared += self.enforce_full_briefing_retention(
                    session_id=sid,
                    keep_recent=keep_recent,
                    keep_first=keep_first,
                )
            except Exception:
                continue
        return total_cleared

    def maybe_checkpoint_wal(self, *, threshold_bytes: int = 64 * 1024 * 1024) -> bool:
        """Checkpoint+truncate WAL when it grows too large (best-effort)."""
        if self.path == Path(":memory:"):
            return False
        try:
            wal_path = Path(str(self.path) + "-wal")
            if not wal_path.exists():
                return False
            if wal_path.stat().st_size < int(threshold_bytes):
                return False
        except Exception:
            return False

        try:
            with self._lock:
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            return True
        except Exception:
            return False

    def get_db_stats(self) -> dict[str, Any]:
        """Return small DB stats for status reporting."""
        if self.path == Path(":memory:"):
            return {"path": ":memory:", "bytes": 0}
        try:
            db_path = self.path
            sizes: dict[str, int] = {}
            total = 0
            for suffix in ("", "-wal", "-shm"):
                p = Path(str(db_path) + suffix)
                try:
                    st = os.stat(p)
                except FileNotFoundError:
                    continue
                sizes[suffix or "db"] = int(st.st_size)
                total += int(st.st_size)
            return {"path": str(db_path), "bytes": total, "files": sizes}
        except Exception:
            return {"path": str(self.path), "bytes": None}

    def end_session(self, *, session_id: str, ended_at: int | None = None) -> None:
        """Mark a session as ended."""
        with self._lock:
            self._conn.execute(
                """
                UPDATE sessions
                SET
                    ended_at = COALESCE(?, strftime('%s','now')),
                    last_updated_at = strftime('%s','now')
                WHERE id = ? AND ended_at IS NULL;
                """,
                (ended_at, session_id),
            )

    def end_active_sessions_for_save(
        self, *, save_id: str, ended_at: int | None = None
    ) -> list[str]:
        """End any active sessions for a given save_id (should normally be 0 or 1)."""
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id
                FROM sessions
                WHERE save_id = ? AND ended_at IS NULL
                ORDER BY started_at DESC;
                """,
                (save_id,),
            ).fetchall()
            session_ids = [str(r["id"]) for r in rows]
            for sid in session_ids:
                self._conn.execute(
                    """
                    UPDATE sessions
                    SET
                        ended_at = COALESCE(?, strftime('%s','now')),
                        last_updated_at = strftime('%s','now')
                    WHERE id = ? AND ended_at IS NULL;
                    """,
                    (ended_at, sid),
                )
            return session_ids

    def get_session_snapshot_stats(self, session_id: str) -> dict[str, Any]:
        """Get basic snapshot stats for a session (count and date range)."""
        with self._lock:
            row = self._conn.execute(
                """
                SELECT
                    COUNT(*) AS snapshot_count,
                    MIN(game_date) AS first_game_date,
                    MAX(game_date) AS last_game_date
                FROM snapshots
                WHERE session_id = ?;
                """,
                (session_id,),
            ).fetchone()
            if not row:
                return {
                    "snapshot_count": 0,
                    "first_game_date": None,
                    "last_game_date": None,
                }
            return {
                "snapshot_count": int(row["snapshot_count"]),
                "first_game_date": row["first_game_date"],
                "last_game_date": row["last_game_date"],
            }

    # --- Phase 3 Milestone 3: events ---

    def get_snapshot_row(self, snapshot_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT id, session_id, captured_at, game_date, save_hash,
                       military_power, colony_count, wars_count, energy_net, alloys_net,
                       full_briefing_json, event_state_json
                FROM snapshots
                WHERE id = ?;
                """,
                (int(snapshot_id),),
            ).fetchone()
            return dict(row) if row else None

    def get_previous_snapshot_id(self, *, session_id: str, before_snapshot_id: int) -> int | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT id
                FROM snapshots
                WHERE session_id = ? AND id < ?
                ORDER BY id DESC
                LIMIT 1;
                """,
                (session_id, int(before_snapshot_id)),
            ).fetchone()
            return int(row["id"]) if row else None

    def insert_events(
        self,
        *,
        session_id: str,
        captured_at: int | None,
        game_date: str | None,
        events: list[dict[str, Any]],
    ) -> int:
        if not events:
            return 0
        rows = []
        for e in events:
            rows.append(
                (
                    session_id,
                    int(captured_at) if captured_at is not None else None,
                    game_date,
                    e["event_type"],
                    e["summary"],
                    json_dumps(e.get("data") or {}),
                )
            )
        with self._lock:
            self._conn.executemany(
                """
                INSERT INTO events (session_id, captured_at, game_date, event_type, summary, data_json)
                VALUES (?, COALESCE(?, strftime('%s','now')), ?, ?, ?, ?);
                """,
                rows,
            )
        return len(rows)

    def record_events_for_new_snapshot(
        self,
        *,
        session_id: str,
        snapshot_id: int,
        current_briefing: dict[str, Any],
    ) -> int:
        """Compute and store events for a newly inserted snapshot.

        Uses the previous snapshot in the same session as the baseline.
        """
        prev_id = self.get_previous_snapshot_id(
            session_id=session_id, before_snapshot_id=int(snapshot_id)
        )
        if prev_id is None:
            return 0

        prev_row = self.get_snapshot_row(prev_id)
        curr_row = self.get_snapshot_row(int(snapshot_id))
        if not prev_row or not curr_row:
            return 0

        prev_state_json = prev_row.get("event_state_json") or prev_row.get("full_briefing_json")
        if not isinstance(prev_state_json, str) or not prev_state_json:
            return 0
        try:
            prev_briefing = json.loads(prev_state_json)
        except Exception:
            return 0

        # Compute current state from the live briefing (avoid depending on persisted JSON).
        try:
            from backend.core.history import build_event_state_from_briefing

            curr_state = build_event_state_from_briefing(current_briefing)
        except Exception:
            curr_state = current_briefing

        detected = compute_events(
            prev=prev_briefing if isinstance(prev_briefing, dict) else {},
            curr=curr_state if isinstance(curr_state, dict) else {},
            from_snapshot_id=int(prev_id),
            to_snapshot_id=int(snapshot_id),
        )
        payloads = [
            {"event_type": e.event_type, "summary": e.summary, "data": e.data} for e in detected
        ]

        return self.insert_events(
            session_id=session_id,
            captured_at=curr_row.get("captured_at"),
            game_date=curr_row.get("game_date"),
            events=payloads,
        )

    # --- Queries for Milestone 4 (/history + reports) ---

    def get_active_or_latest_session_id(self, *, save_id: str) -> str | None:
        """Return the active session id for this save_id, else the most recent ended session."""
        with self._lock:
            row = self._conn.execute(
                """
                SELECT id
                FROM sessions
                WHERE save_id = ?
                ORDER BY (ended_at IS NULL) DESC, started_at DESC
                LIMIT 1;
                """,
                (save_id,),
            ).fetchone()
            return str(row["id"]) if row else None

    def get_active_or_latest_session_id_for_save_path(self, *, save_path: str) -> str | None:
        """Best-effort lookup by last known save_path (useful on startup without parsing gamestate)."""
        if not save_path:
            return None
        with self._lock:
            row = self._conn.execute(
                """
                SELECT id
                FROM sessions
                WHERE save_path = ?
                ORDER BY (ended_at IS NULL) DESC, COALESCE(last_updated_at, started_at) DESC
                LIMIT 1;
                """,
                (str(save_path),),
            ).fetchone()
            return str(row["id"]) if row else None

    def get_recent_events(self, *, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        lim = max(1, min(int(limit), 100))
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, captured_at, game_date, event_type, summary, data_json
                FROM events
                WHERE session_id = ?
                ORDER BY captured_at DESC, id DESC
                LIMIT ?;
                """,
                (session_id, lim),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_first_last_snapshot_rows(
        self, *, session_id: str
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        with self._lock:
            first = self._conn.execute(
                """
                SELECT id, captured_at, game_date, full_briefing_json, event_state_json
                FROM snapshots
                WHERE session_id = ?
                ORDER BY captured_at ASC, id ASC
                LIMIT 1;
                """,
                (session_id,),
            ).fetchone()
            last = self._conn.execute(
                """
                SELECT id, captured_at, game_date, full_briefing_json, event_state_json
                FROM snapshots
                WHERE session_id = ?
                ORDER BY captured_at DESC, id DESC
                LIMIT 1;
                """,
                (session_id,),
            ).fetchone()
            return (dict(first) if first else None, dict(last) if last else None)

    def get_recent_snapshot_points(
        self, *, session_id: str, limit: int = 8
    ) -> list[dict[str, Any]]:
        """Return a small set of snapshot metric points for trend questions."""
        lim = max(1, min(int(limit), 50))
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, captured_at, game_date, military_power, colony_count, wars_count, energy_net, alloys_net
                FROM snapshots
                WHERE session_id = ?
                ORDER BY captured_at DESC, id DESC
                LIMIT ?;
                """,
                (session_id, lim),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_sessions(self, *, limit: int = 50) -> list[dict[str, Any]]:
        """Return all sessions with snapshot stats, ordered by started_at DESC."""
        lim = max(1, min(int(limit), 100))
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT
                    s.id,
                    s.save_id,
                    s.save_path,
                    s.empire_name,
                    s.started_at,
                    s.ended_at,
                    s.last_game_date,
                    s.last_updated_at,
                    COUNT(snap.id) AS snapshot_count,
                    MIN(snap.game_date) AS first_game_date,
                    MAX(snap.game_date) AS last_game_date_computed
                FROM sessions s
                LEFT JOIN snapshots snap ON snap.session_id = s.id
                GROUP BY s.id
                ORDER BY s.started_at DESC
                LIMIT ?;
                """,
                (lim,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_playthroughs(
        self,
        *,
        language: str = "en",
        include_trashed: bool = False,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Return save-scoped campaign summaries without mutating Chronicle caches."""
        lim = max(1, min(int(limit), 1000))
        with self._lock:
            rows = self._conn.execute(
                """
                WITH session_rollup AS (
                    SELECT
                        save_id,
                        COUNT(*) AS session_count,
                        MIN(started_at) AS first_seen_at,
                        MAX(COALESCE(last_updated_at, started_at)) AS last_played_at,
                        MIN(last_game_date) AS first_session_game_date,
                        MAX(last_game_date) AS last_session_game_date
                    FROM sessions
                    GROUP BY save_id
                ),
                snapshot_rollup AS (
                    SELECT
                        s.save_id,
                        COUNT(snap.id) AS snapshot_count,
                        MIN(snap.game_date) AS first_snapshot_game_date,
                        MAX(snap.game_date) AS last_snapshot_game_date
                    FROM sessions s
                    LEFT JOIN snapshots snap ON snap.session_id = s.id
                    GROUP BY s.save_id
                ),
                event_rollup AS (
                    SELECT s.save_id, COUNT(e.id) AS event_count
                    FROM sessions s
                    LEFT JOIN events e ON e.session_id = s.id
                    GROUP BY s.save_id
                )
                SELECT
                    sr.save_id,
                    (
                        SELECT s2.empire_name
                        FROM sessions s2
                        WHERE s2.save_id = sr.save_id
                        ORDER BY COALESCE(s2.last_updated_at, s2.started_at) DESC, s2.started_at DESC
                        LIMIT 1
                    ) AS empire_name,
                    (
                        SELECT s2.id
                        FROM sessions s2
                        WHERE s2.save_id = sr.save_id
                        ORDER BY COALESCE(s2.last_updated_at, s2.started_at) DESC, s2.started_at DESC
                        LIMIT 1
                    ) AS latest_session_id,
                    sr.session_count,
                    sr.first_seen_at,
                    sr.last_played_at,
                    COALESCE(sn.first_snapshot_game_date, sr.first_session_game_date) AS first_game_date,
                    CASE
                        WHEN sn.last_snapshot_game_date > sr.last_session_game_date
                            THEN sn.last_snapshot_game_date
                        ELSE COALESCE(sr.last_session_game_date, sn.last_snapshot_game_date)
                    END AS last_game_date,
                    COALESCE(sn.snapshot_count, 0) AS snapshot_count,
                    COALESCE(er.event_count, 0) AS event_count,
                    pm.display_label,
                    pm.trashed_at
                FROM session_rollup sr
                LEFT JOIN snapshot_rollup sn ON sn.save_id = sr.save_id
                LEFT JOIN event_rollup er ON er.save_id = sr.save_id
                LEFT JOIN playthrough_metadata pm ON pm.save_id = sr.save_id
                WHERE (? = 1 OR pm.trashed_at IS NULL)
                ORDER BY sr.last_played_at DESC
                LIMIT ?;
                """,
                (1 if include_trashed else 0, lim),
            ).fetchall()

            cache_rows = self._conn.execute(
                """
                SELECT
                    c.*,
                    COALESCE(NULLIF(c.save_id, ''), s.save_id) AS resolved_save_id
                FROM cached_chronicles c
                LEFT JOIN sessions s ON s.id = c.session_id;
                """
            ).fetchall()
            revision_rows = self._conn.execute(
                """
                SELECT save_id, language, COUNT(*) AS revision_count
                FROM chronicle_revisions
                GROUP BY save_id, language;
                """
            ).fetchall()

        cache_summary: dict[str, dict[str, Any]] = {}
        for raw_row in cache_rows:
            cache = dict(raw_row)
            save_id = str(cache.get("resolved_save_id") or "")
            if not save_id:
                continue
            cache_language = str(cache.get("language") or "en")
            chapters_data: dict[str, Any] = {}
            chapters_json = cache.get("chapters_json")
            if isinstance(chapters_json, str) and chapters_json:
                with contextlib.suppress(json.JSONDecodeError):
                    parsed = json.loads(chapters_json)
                    if isinstance(parsed, dict):
                        chapters_data = parsed
            chapters = chapters_data.get("chapters")
            chapter_count = len(chapters) if isinstance(chapters, list) else 0
            era_cache = chapters_data.get("current_era_cache")
            has_current_era = bool(
                isinstance(era_cache, dict) and isinstance(era_cache.get("current_era"), dict)
            )
            has_content = bool(
                (isinstance(cache.get("chronicle_text"), str) and cache["chronicle_text"].strip())
                or chapter_count
                or has_current_era
            )
            summary = cache_summary.setdefault(
                save_id,
                {
                    "has_chronicle": False,
                    "cached_languages": set(),
                    "chapter_count_by_language": {},
                    "has_content_by_language": {},
                    "has_current_era": False,
                },
            )
            if has_content:
                summary["has_chronicle"] = True
                summary["cached_languages"].add(cache_language)
                summary["has_content_by_language"][cache_language] = True
                summary["chapter_count_by_language"][cache_language] = max(
                    int(summary["chapter_count_by_language"].get(cache_language, 0)),
                    chapter_count,
                )
                summary["has_current_era"] = bool(summary["has_current_era"] or has_current_era)

        revision_counts = {
            (str(row["save_id"]), str(row["language"])): int(row["revision_count"])
            for row in revision_rows
        }

        result: list[dict[str, Any]] = []
        for raw_row in rows:
            item = dict(raw_row)
            save_id = str(item["save_id"])
            summary = cache_summary.get(save_id, {})
            languages = sorted(summary.get("cached_languages", set()))
            chapter_counts = summary.get("chapter_count_by_language", {})
            has_content_by_language = summary.get("has_content_by_language", {})
            item.update(
                {
                    "display_name": item.get("display_label")
                    or item.get("empire_name")
                    or "Unknown Empire",
                    "is_trashed": item.get("trashed_at") is not None,
                    "has_chronicle": bool(summary.get("has_chronicle")),
                    "cached_languages": languages,
                    "chapter_count": int(chapter_counts.get(language, 0)),
                    "total_chapter_count": max(chapter_counts.values(), default=0),
                    "has_current_era": bool(summary.get("has_current_era")),
                    "can_undo_reset": (
                        revision_counts.get((save_id, language), 0) > 0
                        and not bool(has_content_by_language.get(language))
                    ),
                }
            )
            result.append(item)
        return result

    def get_playthrough(self, save_id: str, *, language: str = "en") -> dict[str, Any] | None:
        for item in self.get_playthroughs(
            language=language,
            include_trashed=True,
            limit=1000,
        ):
            if item.get("save_id") == save_id:
                return item
        return None

    def set_playthrough_label(self, save_id: str, display_label: str | None) -> None:
        value = (display_label or "").strip()[:80]
        with self._lock:
            exists = self._conn.execute(
                "SELECT 1 FROM sessions WHERE save_id = ? LIMIT 1", (save_id,)
            ).fetchone()
            if not exists:
                raise ValueError(f"Playthrough not found: {save_id}")
            self._conn.execute(
                """
                INSERT INTO playthrough_metadata (save_id, display_label, updated_at)
                VALUES (?, ?, strftime('%s','now'))
                ON CONFLICT(save_id) DO UPDATE SET
                    display_label = excluded.display_label,
                    updated_at = excluded.updated_at;
                """,
                (save_id, value or None),
            )

    def trash_playthrough(self, save_id: str) -> None:
        with self._lock:
            exists = self._conn.execute(
                "SELECT 1 FROM sessions WHERE save_id = ? LIMIT 1", (save_id,)
            ).fetchone()
            if not exists:
                raise ValueError(f"Playthrough not found: {save_id}")
            self._conn.execute(
                """
                INSERT INTO playthrough_metadata (save_id, trashed_at, updated_at)
                VALUES (?, strftime('%s','now'), strftime('%s','now'))
                ON CONFLICT(save_id) DO UPDATE SET
                    trashed_at = excluded.trashed_at,
                    updated_at = excluded.updated_at;
                """,
                (save_id,),
            )

    def restore_playthrough(self, save_id: str) -> None:
        with self._lock:
            exists = self._conn.execute(
                "SELECT 1 FROM sessions WHERE save_id = ? LIMIT 1", (save_id,)
            ).fetchone()
            if not exists:
                raise ValueError(f"Playthrough not found: {save_id}")
            self._conn.execute(
                """
                UPDATE playthrough_metadata
                SET trashed_at = NULL, updated_at = strftime('%s','now')
                WHERE save_id = ?;
                """,
                (save_id,),
            )

    def get_cached_chronicle_for_save(
        self,
        save_id: str,
        *,
        language: str = "en",
    ) -> dict[str, Any] | None:
        """Read a save-scoped cache with a non-mutating legacy session fallback."""
        with self._lock:
            row = self._conn.execute(
                """
                SELECT c.*
                FROM cached_chronicles c
                LEFT JOIN sessions s ON s.id = c.session_id
                WHERE c.language = ?
                  AND (c.save_id = ? OR ((c.save_id IS NULL OR c.save_id = '') AND s.save_id = ?))
                ORDER BY CASE WHEN c.save_id = ? THEN 0 ELSE 1 END, c.generated_at DESC
                LIMIT 1;
                """,
                (language, save_id, save_id, save_id),
            ).fetchone()
            return dict(row) if row else None

    def reset_chronicle(
        self, save_id: str, *, language: str = "en", expected_revision: str | None = None
    ) -> int:
        """Save reset backups and invalidate in-flight drafts in the same transaction."""
        with self.transaction(immediate=True):
            current = self.get_cached_chronicle_for_save(save_id, language=language)
            if (
                expected_revision is not None
                and chronicle_revision(load_chapters_data(current)) != expected_revision
            ):
                raise ChronicleConflict(
                    "The Chronicle changed. Read the newer version before resetting."
                )
            rows = self._conn.execute(
                """SELECT c.* FROM cached_chronicles c LEFT JOIN sessions s ON s.id=c.session_id
                   WHERE c.language=? AND (c.save_id=? OR ((c.save_id IS NULL OR c.save_id='') AND s.save_id=?))""",
                (language, save_id, save_id),
            ).fetchall()
            payload = [dict(row) for row in rows]
            meaningful = any(
                str(row.get("chronicle_text") or "").strip()
                or (row.get("chapters_json") and not load_chapters_data(row).get("reset_tombstone"))
                for row in payload
            )
            if not meaningful:
                raise ValueError(f"No cached Chronicle found for save: {save_id}")
            self._conn.execute(
                "INSERT INTO chronicle_revisions(save_id,language,reason,payload_json) VALUES(?,?,'reset',?)",
                (save_id, language, json_dumps(payload)),
            )
            for row in payload:
                self._conn.execute(
                    """UPDATE cached_chronicles SET chronicle_text='',chapters_json=?,event_count=0,
                       snapshot_count=0,generated_at=datetime('now') WHERE id=?""",
                    (
                        json_dumps({"revision_id": uuid.uuid4().hex, "reset_tombstone": True}),
                        row["id"],
                    ),
                )
            self._conn.execute(
                """DELETE FROM chronicle_revisions WHERE id IN (SELECT id FROM chronicle_revisions
                   WHERE save_id=? AND language=? ORDER BY created_at DESC,id DESC LIMIT -1 OFFSET 5)""",
                (save_id, language),
            )
            return len(payload)

    def undo_chronicle_reset(
        self, save_id: str, *, language: str = "en", expected_revision: str | None = None
    ) -> bool:
        with self.transaction(immediate=True):
            current = self.get_cached_chronicle_for_save(save_id, language=language)
            if (
                expected_revision is not None
                and chronicle_revision(load_chapters_data(current)) != expected_revision
            ):
                raise ChronicleConflict(
                    "The Chronicle changed. Read the newer version before undoing its reset."
                )
            revision = self._conn.execute(
                """SELECT id,payload_json FROM chronicle_revisions WHERE save_id=? AND language=?
                   AND reason='reset' ORDER BY created_at DESC,id DESC LIMIT 1""",
                (save_id, language),
            ).fetchone()
            if not revision:
                return False
            rows = self._conn.execute(
                """SELECT c.* FROM cached_chronicles c LEFT JOIN sessions s ON s.id=c.session_id
                   WHERE c.language=? AND (c.save_id=? OR ((c.save_id IS NULL OR c.save_id='') AND s.save_id=?))""",
                (language, save_id, save_id),
            ).fetchall()
            if any(
                str(row["chronicle_text"] or "").strip()
                or (
                    row["chapters_json"]
                    and not load_chapters_data(dict(row)).get("reset_tombstone")
                )
                for row in rows
            ):
                self._conn.execute("DELETE FROM chronicle_revisions WHERE id=?", (revision["id"],))
                return False
            payload = json.loads(revision["payload_json"])
            if not isinstance(payload, list):
                return False
            columns = (
                "id",
                "session_id",
                "save_id",
                "language",
                "chronicle_text",
                "chapters_json",
                "event_count",
                "snapshot_count",
                "generated_at",
                "chronicle_custom_instructions",
            )
            self._conn.execute(
                """DELETE FROM cached_chronicles WHERE language=? AND (save_id=? OR session_id IN
                   (SELECT id FROM sessions WHERE save_id=?))""",
                (language, save_id, save_id),
            )
            for raw in payload:
                if not isinstance(raw, dict):
                    continue
                restored = load_chapters_data(raw)
                restored["revision_id"] = uuid.uuid4().hex
                raw["chapters_json"] = json_dumps(restored)
                self._conn.execute(
                    f"INSERT INTO cached_chronicles({', '.join(columns)}) VALUES({', '.join('?' for _ in columns)})",
                    tuple(raw.get(column) for column in columns),
                )
            self._conn.execute("DELETE FROM chronicle_revisions WHERE id=?", (revision["id"],))
            return True

    def delete_playthrough(self, save_id: str) -> dict[str, int]:
        """Permanently delete all local data for one playthrough transactionally."""
        with self._lock:
            session_count = int(
                self._conn.execute(
                    "SELECT COUNT(*) AS count FROM sessions WHERE save_id = ?", (save_id,)
                ).fetchone()["count"]
            )
            if session_count == 0:
                raise ValueError(f"Playthrough not found: {save_id}")
            snapshot_count = int(
                self._conn.execute(
                    """
                    SELECT COUNT(*) AS count FROM snapshots
                    WHERE session_id IN (SELECT id FROM sessions WHERE save_id = ?)
                    """,
                    (save_id,),
                ).fetchone()["count"]
            )
            event_count = int(
                self._conn.execute(
                    """
                    SELECT COUNT(*) AS count FROM events
                    WHERE session_id IN (SELECT id FROM sessions WHERE save_id = ?)
                    """,
                    (save_id,),
                ).fetchone()["count"]
            )
            cache_count = int(
                self._conn.execute(
                    """
                    SELECT COUNT(*) AS count FROM cached_chronicles
                    WHERE save_id = ? OR session_id IN (SELECT id FROM sessions WHERE save_id = ?)
                    """,
                    (save_id, save_id),
                ).fetchone()["count"]
            )
            self._conn.execute("BEGIN IMMEDIATE;")
            try:
                self._conn.execute(
                    """
                    DELETE FROM cached_chronicles
                    WHERE save_id = ? OR session_id IN (SELECT id FROM sessions WHERE save_id = ?)
                    """,
                    (save_id, save_id),
                )
                self._conn.execute("DELETE FROM advisor_memory WHERE save_id = ?", (save_id,))
                self._conn.execute(
                    "DELETE FROM advisor_conversations WHERE save_id = ?", (save_id,)
                )
                self._conn.execute("DELETE FROM chronicle_revisions WHERE save_id = ?", (save_id,))
                self._conn.execute("DELETE FROM sessions WHERE save_id = ?", (save_id,))
                self._conn.execute("DELETE FROM playthrough_metadata WHERE save_id = ?", (save_id,))
                self._conn.execute("COMMIT;")
            except Exception:
                self._conn.execute("ROLLBACK;")
                raise
            return {
                "sessions": session_count,
                "snapshots": snapshot_count,
                "events": event_count,
                "chronicle_caches": cache_count,
            }

    def create_backup(self, destination: str | Path) -> dict[str, Any]:
        """Create a consistent SQLite backup while the app remains online."""
        target = Path(destination).expanduser().resolve()
        if target == self.path.resolve():
            raise ValueError("Backup destination must differ from the active database")
        target.parent.mkdir(parents=True, exist_ok=True)
        backup_conn = sqlite3.connect(str(target))
        try:
            with self._lock:
                self._conn.backup(backup_conn)
        finally:
            backup_conn.close()
        return {"path": str(target), "bytes": target.stat().st_size}

    def get_session_by_id(self, session_id: str) -> dict[str, Any] | None:
        """Get a single session by ID with snapshot stats."""
        with self._lock:
            row = self._conn.execute(
                """
                SELECT
                    s.id,
                    s.save_id,
                    s.save_path,
                    s.empire_name,
                    s.started_at,
                    s.ended_at,
                    s.last_game_date,
                    s.last_updated_at,
                    COUNT(snap.id) AS snapshot_count,
                    MIN(snap.game_date) AS first_game_date,
                    MAX(snap.game_date) AS last_game_date_computed
                FROM sessions s
                LEFT JOIN snapshots snap ON snap.session_id = s.id
                WHERE s.id = ?
                GROUP BY s.id;
                """,
                (session_id,),
            ).fetchone()
            return dict(row) if row else None

    # --- Chronicle generation support ---

    def get_all_events(self, *, session_id: str) -> list[dict[str, Any]]:
        """Get ALL events for a session (no limit cap).

        Used by chronicle generation which needs full history.
        Note: get_recent_events() has a hard 100-event cap.
        """
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, captured_at, game_date, event_type, summary, data_json
                FROM events
                WHERE session_id = ?
                ORDER BY game_date ASC, captured_at ASC, id ASC;
                """,
                (session_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_cached_chronicle(
        self, session_id: str, *, language: str = "en"
    ) -> dict[str, Any] | None:
        """Get cached chronicle if it exists."""
        with self._lock:
            row = self._conn.execute(
                """
                SELECT * FROM cached_chronicles
                WHERE session_id = ? AND language = ?
                ORDER BY generated_at DESC LIMIT 1
                """,
                (session_id, language),
            ).fetchone()
            return dict(row) if row else None

    def get_event_count(self, session_id: str) -> int:
        """Get total event count for a session."""
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM events WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            return row["cnt"] if row else 0

    def get_snapshot_count(self, session_id: str) -> int:
        """Get total snapshot count for a session."""
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM snapshots WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            return row["cnt"] if row else 0

    def upsert_cached_chronicle(
        self,
        session_id: str,
        chronicle_text: str,
        event_count: int,
        snapshot_count: int,
        chapters_json: str | None = None,
        save_id: str | None = None,
        language: str = "en",
    ) -> None:
        """Insert or update cached chronicle."""
        with self._lock:
            if save_id:
                existing = self._conn.execute(
                    "SELECT id FROM cached_chronicles WHERE save_id = ? AND language = ?",
                    (save_id, language),
                ).fetchone()
            else:
                existing = self._conn.execute(
                    "SELECT id FROM cached_chronicles WHERE session_id = ? AND language = ?",
                    (session_id, language),
                ).fetchone()

            if existing:
                self._conn.execute(
                    """
                    UPDATE cached_chronicles
                    SET chronicle_text = ?,
                        chapters_json = ?,
                        event_count = ?,
                        snapshot_count = ?,
                        save_id = COALESCE(?, save_id),
                        generated_at = datetime('now')
                    WHERE id = ?
                    """,
                    (
                        chronicle_text,
                        chapters_json,
                        event_count,
                        snapshot_count,
                        save_id,
                        existing["id"],
                    ),
                )
            else:
                self._conn.execute(
                    """
                    INSERT INTO cached_chronicles
                        (id, session_id, chronicle_text, chapters_json, event_count,
                         snapshot_count, save_id, language)
                    VALUES (lower(hex(randomblob(16))), ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        chronicle_text,
                        chapters_json,
                        event_count,
                        snapshot_count,
                        save_id,
                        language,
                    ),
                )

    # --- Incremental Chronicle Support ---

    def get_save_id_for_session(self, session_id: str) -> str | None:
        """Get the save_id for a session."""
        with self._lock:
            row = self._conn.execute(
                "SELECT save_id FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            return row["save_id"] if row else None

    def get_chronicle_by_save_id(
        self,
        save_id: str,
        *,
        language: str = "en",
    ) -> dict[str, Any] | None:
        """Get cached Chronicle by save_id, including legacy session-scoped rows."""
        return self.get_cached_chronicle_for_save(save_id, language=language)

    def get_chronicle_custom_instructions(self, save_id: str) -> str | None:
        """Get chronicle custom instructions for a save_id."""
        with self._lock:
            row = self._conn.execute(
                """
                SELECT chronicle_custom_instructions
                FROM cached_chronicles
                WHERE save_id = ? AND chronicle_custom_instructions IS NOT NULL
                ORDER BY generated_at DESC LIMIT 1;
                """,
                (save_id,),
            ).fetchone()
            if not row:
                return None
            value = row["chronicle_custom_instructions"]
            return str(value) if isinstance(value, str) and value.strip() else None

    def update_chronicle_custom_instructions(self, save_id: str, text: str | None) -> None:
        """A style change invalidates drafts prepared with the old instructions."""
        value = (text or "").strip()[:500] or None
        with self.transaction(immediate=True):
            rows = self._conn.execute(
                "SELECT * FROM cached_chronicles WHERE save_id=?", (save_id,)
            ).fetchall()
            if rows:
                for raw in rows:
                    if raw["chronicle_custom_instructions"] == value:
                        continue
                    data = load_chapters_data(dict(raw))
                    data["revision_id"] = uuid.uuid4().hex
                    self._conn.execute(
                        "UPDATE cached_chronicles SET chronicle_custom_instructions=?,chapters_json=? WHERE id=?",
                        (value, json_dumps(data), raw["id"]),
                    )
            else:
                self._conn.execute(
                    """INSERT INTO cached_chronicles(id,session_id,save_id,chronicle_text,event_count,snapshot_count,
                       chronicle_custom_instructions,chapters_json) VALUES(lower(hex(randomblob(16))),'',?,'',0,0,?,?)""",
                    (save_id, value, json_dumps({"revision_id": uuid.uuid4().hex})),
                )

    def get_advisor_conversation(self, save_id: str, conversation_id: str) -> dict[str, Any] | None:
        """Read one campaign-scoped conversation, including empty new conversations."""
        with self._lock:
            row = self._conn.execute(
                """
                SELECT c.*, COUNT(t.id) AS turn_count,
                    (SELECT game_date FROM advisor_turns WHERE conversation_id = c.id
                     ORDER BY rowid DESC LIMIT 1) AS last_game_date
                FROM advisor_conversations c LEFT JOIN advisor_turns t ON t.conversation_id = c.id
                WHERE c.save_id = ? AND c.id = ? GROUP BY c.id
                """,
                (save_id, conversation_id),
            ).fetchone()
            return dict(row) if row else None

    def list_advisor_conversations(self, save_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT c.*, COUNT(t.id) AS turn_count,
                    (SELECT game_date FROM advisor_turns WHERE conversation_id = c.id
                     ORDER BY rowid DESC LIMIT 1) AS last_game_date
                FROM advisor_conversations c LEFT JOIN advisor_turns t ON t.conversation_id = c.id
                WHERE c.save_id = ? GROUP BY c.id
                ORDER BY c.updated_at DESC, c.created_at DESC, c.rowid DESC LIMIT ?
                """,
                (save_id, max(1, min(500, int(limit)))),
            ).fetchall()
            return [dict(row) for row in rows]

    def create_advisor_conversation(
        self, save_id: str, *, conversation_id: str | None = None, title: str = ""
    ) -> dict[str, Any]:
        """Create a stable thread without changing or removing earlier conversations."""
        identifier = conversation_id or uuid.uuid4().hex
        now = time.time()
        with self.transaction(immediate=True):
            if self.get_active_or_latest_session_id(save_id=save_id) is None:
                raise ValueError("Playthrough not found")
            existing = self.get_advisor_conversation(save_id, identifier)
            if existing:
                return existing
            self._conn.execute(
                "INSERT INTO advisor_conversations (id, save_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (identifier, save_id, str(title).strip()[:100], now, now),
            )
            return self.get_advisor_conversation(save_id, identifier) or {}

    @staticmethod
    def _advisor_turn_payload(row: sqlite3.Row) -> dict[str, Any]:
        turn = dict(row)
        # Only a fixed public response envelope is stored, never prompts or credentials.
        response = json.loads(turn.pop("response_json"))
        turn.update(response)
        return turn

    def get_advisor_turn_by_request(self, save_id: str, request_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM advisor_turns WHERE save_id = ? AND request_id = ?",
                (save_id, request_id),
            ).fetchone()
            return self._advisor_turn_payload(row) if row else None

    def get_advisor_turns(
        self,
        save_id: str,
        conversation_id: str,
        *,
        limit: int = 300,
        before_turn_id: str | None = None,
        language: str | None = None,
    ) -> list[dict[str, Any]]:
        """Read a bounded archive page, oldest first, without modifying prompt memory."""
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM advisor_turns
                WHERE save_id = ? AND conversation_id = ?
                  AND (? IS NULL OR language = ?)
                  AND (? IS NULL OR rowid < (SELECT rowid FROM advisor_turns
                      WHERE id = ? AND save_id = ? AND conversation_id = ?))
                ORDER BY rowid DESC LIMIT ?
                """,
                (
                    save_id,
                    conversation_id,
                    language,
                    language,
                    before_turn_id,
                    before_turn_id,
                    save_id,
                    conversation_id,
                    max(1, min(501, int(limit))),
                ),
            ).fetchall()
            return [self._advisor_turn_payload(row) for row in reversed(rows)]

    def save_advisor_turn(
        self,
        *,
        save_id: str,
        conversation_id: str,
        request_id: str,
        question: str,
        answer: str,
        language: str,
        game_date: str | None,
        source_hash: str | None,
        response: dict[str, Any],
        snapshot_id: int | None = None,
    ) -> dict[str, Any]:
        """Atomically save only a completed exchange; a request ID cannot create duplicates."""
        now = time.time()
        with self.transaction(immediate=True):
            conversation = self.get_advisor_conversation(save_id, conversation_id)
            if conversation is None:
                raise ValueError("Conversation not found")
            existing = self.get_advisor_turn_by_request(save_id, request_id)
            if existing:
                if (
                    existing["conversation_id"] != conversation_id
                    or existing["question"] != question
                ):
                    raise ValueError("Request ID already belongs to a different exchange")
                return existing
            identifier = uuid.uuid4().hex
            self._conn.execute(
                """
                INSERT INTO advisor_turns
                    (id, conversation_id, save_id, request_id, question, answer, language,
                     game_date, source_hash, snapshot_id, created_at, response_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    identifier,
                    conversation_id,
                    save_id,
                    request_id,
                    question,
                    answer,
                    language,
                    game_date,
                    source_hash,
                    snapshot_id,
                    now,
                    json_dumps(response),
                ),
            )
            title = conversation["title"] or " ".join(question.split())[:100]
            self._conn.execute(
                "UPDATE advisor_conversations SET title = ?, updated_at = ? WHERE id = ? AND save_id = ?",
                (title, now, conversation_id, save_id),
            )
            return self.get_advisor_turn_by_request(save_id, request_id) or {}

    def get_advisor_memory_summary(self, save_id: str, *, language: str = "en") -> str | None:
        """Get persisted save-scoped advisor memory summary."""
        if not save_id:
            return None
        with self._lock:
            row = self._conn.execute(
                """
                SELECT summary_text
                FROM advisor_memory
                WHERE save_id = ? AND language = ?
                LIMIT 1;
                """,
                (save_id, language),
            ).fetchone()
            if not row:
                return None
            value = row["summary_text"]
            return str(value) if isinstance(value, str) and value.strip() else None

    def upsert_advisor_memory_summary(
        self,
        *,
        save_id: str,
        language: str = "en",
        summary_text: str | None,
        last_game_date: str | None = None,
    ) -> None:
        """Persist compact save-scoped advisor memory summary."""
        if not save_id:
            return
        cleaned = (summary_text or "").strip()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO advisor_memory (save_id, language, summary_text, last_game_date, updated_at)
                VALUES (?, ?, ?, ?, strftime('%s','now'))
                ON CONFLICT(save_id, language) DO UPDATE SET
                    summary_text = excluded.summary_text,
                    last_game_date = COALESCE(excluded.last_game_date, advisor_memory.last_game_date),
                    updated_at = strftime('%s','now');
                """,
                (save_id, language, cleaned if cleaned else None, last_game_date),
            )

    def get_all_events_by_save_id(self, *, save_id: str) -> list[dict[str, Any]]:
        """Get ALL events across all sessions for a save_id (no limit cap).

        Used by incremental chronicle generation which needs full cross-session history.
        """
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT e.id, e.captured_at, e.game_date, e.event_type, e.summary, e.data_json
                FROM events e
                JOIN sessions s ON e.session_id = s.id
                WHERE s.save_id = ?
                ORDER BY e.game_date ASC, e.captured_at ASC, e.id ASC;
                """,
                (save_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_events_in_snapshot_range(
        self,
        *,
        save_id: str,
        from_snapshot_id: int | None = None,
        to_snapshot_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get events within a snapshot ID range for a save_id.

        Events are primarily linked to snapshots via `data_json.to_snapshot_id`
        (recorded by event computation). For backwards compatibility with older
        rows missing snapshot linkage, fall back to `captured_at` bounds derived
        from the snapshot rows.
        """
        with self._lock:
            if from_snapshot_id is None and to_snapshot_id is None:
                return self.get_all_events_by_save_id(save_id=save_id)

            from_captured_at: int | None = None
            to_captured_at: int | None = None
            if from_snapshot_id is not None:
                from_row = self._conn.execute(
                    "SELECT captured_at FROM snapshots WHERE id = ?",
                    (int(from_snapshot_id),),
                ).fetchone()
                if from_row and from_row["captured_at"] is not None:
                    from_captured_at = int(from_row["captured_at"])
            if to_snapshot_id is not None:
                to_row = self._conn.execute(
                    "SELECT captured_at FROM snapshots WHERE id = ?",
                    (int(to_snapshot_id),),
                ).fetchone()
                if to_row and to_row["captured_at"] is not None:
                    to_captured_at = int(to_row["captured_at"])

            # Build query based on provided bounds
            conditions = ["s.save_id = ?"]
            params: list[Any] = [save_id]

            if from_snapshot_id is not None:
                if from_captured_at is not None:
                    conditions.append(
                        """
                        (
                            CAST(json_extract(e.data_json, '$.to_snapshot_id') AS INTEGER) > ?
                            OR (
                                json_extract(e.data_json, '$.to_snapshot_id') IS NULL
                                AND e.captured_at > ?
                            )
                        )
                        """
                    )
                    params.extend([int(from_snapshot_id), from_captured_at])
                else:
                    conditions.append(
                        "CAST(json_extract(e.data_json, '$.to_snapshot_id') AS INTEGER) > ?"
                    )
                    params.append(int(from_snapshot_id))
            if to_snapshot_id is not None:
                if to_captured_at is not None:
                    conditions.append(
                        """
                        (
                            CAST(json_extract(e.data_json, '$.to_snapshot_id') AS INTEGER) <= ?
                            OR (
                                json_extract(e.data_json, '$.to_snapshot_id') IS NULL
                                AND e.captured_at <= ?
                            )
                        )
                        """
                    )
                    params.extend([int(to_snapshot_id), to_captured_at])
                else:
                    conditions.append(
                        "CAST(json_extract(e.data_json, '$.to_snapshot_id') AS INTEGER) <= ?"
                    )
                    params.append(int(to_snapshot_id))

            query = f"""
                SELECT e.id, e.captured_at, e.game_date, e.event_type, e.summary, e.data_json
                FROM events e
                JOIN sessions s ON e.session_id = s.id
                WHERE {" AND ".join(conditions)}
                ORDER BY e.game_date ASC, e.captured_at ASC, e.id ASC;
            """
            rows = self._conn.execute(query, tuple(params)).fetchall()
            return [dict(r) for r in rows]

    def get_latest_snapshot_at_or_before(
        self,
        *,
        save_id: str,
        game_date: str,
        upper_snapshot_id: int | None = None,
    ) -> dict[str, Any] | None:
        """Get the latest snapshot for save_id with game_date <= target."""
        with self._lock:
            row = self._conn.execute(
                """
                SELECT snap.id, snap.game_date, snap.captured_at
                FROM snapshots snap
                JOIN sessions s ON snap.session_id = s.id
                WHERE s.save_id = ?
                  AND snap.game_date IS NOT NULL
                  AND snap.game_date <= ?
                  AND (? IS NULL OR snap.id <= ?)
                ORDER BY snap.game_date DESC, snap.captured_at DESC, snap.id DESC
                LIMIT 1;
                """,
                (save_id, game_date, upper_snapshot_id, upper_snapshot_id),
            ).fetchone()
            return dict(row) if row else None

    def get_snapshot_range_for_save(self, save_id: str) -> dict[str, Any]:
        """Get captured snapshot boundaries, including a save loaded at an older date."""
        return self.get_chronicle_snapshot_range(save_id)

    def get_all_sessions_for_save(self, save_id: str) -> list[dict[str, Any]]:
        """Get all sessions (active and ended) for a save_id."""
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, save_id, empire_name, started_at, ended_at, last_game_date
                FROM sessions
                WHERE save_id = ?
                ORDER BY started_at ASC;
                """,
                (save_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def commit_legacy_chronicle(
        self,
        *,
        session_id: str,
        expected_revision: str,
        chronicle_text: str,
        event_count: int,
        snapshot_count: int,
        coverage_date: str | None,
    ) -> dict[str, Any]:
        """Apply the same revision/lifecycle guarantee to old session-scoped prose."""
        with self.transaction(immediate=True):
            session = self.get_session_by_id(session_id)
            if not session:
                raise ChronicleConflict(
                    "The session was deleted while this Chronicle was prepared."
                )
            playthrough = (
                self.get_playthrough(session["save_id"]) if session.get("save_id") else None
            )
            if playthrough and playthrough.get("is_trashed"):
                raise ChronicleConflict(
                    "The campaign was archived while this Chronicle was prepared."
                )
            cached = self.get_cached_chronicle(session_id)
            data = load_chapters_data(cached)
            if chronicle_revision(data) != expected_revision:
                raise ChronicleConflict("The Chronicle changed while this update was prepared.")
            data.update(
                revision_id=uuid.uuid4().hex,
                content_generated_at=datetime.now(timezone.utc).isoformat(),
                coverage_date=coverage_date,
            )
            self.upsert_cached_chronicle(
                session_id=session_id,
                chronicle_text=chronicle_text,
                chapters_json=json_dumps(data),
                event_count=event_count,
                snapshot_count=snapshot_count,
            )
            return self.get_cached_chronicle(session_id) or {}

    def commit_chronicle(
        self,
        *,
        save_id: str,
        session_id: str,
        language: str,
        expected_revision: str,
        chapters_data: dict[str, Any],
        event_count: int,
        snapshot_count: int,
        record_undo: bool = True,
        external_write: bool = False,
    ) -> dict[str, Any]:
        """Commit one prepared replacement only while its source archive still exists.

        Provider calls happen before this short transaction. All mutation surfaces
        use the same revision comparison, including edits in another process.
        """
        # MCP already holds the same lock and a short transaction. Native API and
        # generation enter here without one; neither path nests BEGIN statements.
        with (
            self._lock,
            nullcontext() if self._conn.in_transaction else self.transaction(immediate=True),
        ):
            session = self._conn.execute(
                """SELECT s.id FROM sessions s LEFT JOIN playthrough_metadata p
                   ON p.save_id=s.save_id WHERE s.id=? AND s.save_id=?
                   AND p.trashed_at IS NULL""",
                (session_id, save_id),
            ).fetchone()
            if not session:
                raise ChronicleConflict(
                    "The campaign was removed or archived while this Chronicle was prepared."
                )
            cached = self.get_cached_chronicle_for_save(save_id, language=language)
            before = load_chapters_data(cached)
            if chronicle_revision(before) != expected_revision:
                raise ChronicleConflict(
                    "The Chronicle changed while this update was prepared. Read the newer version before retrying."
                )
            candidate = load_chapters_data({"chapters_json": json_dumps(chapters_data)})
            candidate.pop("reset_tombstone", None)
            if record_undo:
                undo = deepcopy(before.get("chapter_undo") or {})
                previous = {
                    str(ch.get("id")): ch
                    for ch in before.get("chapters", [])
                    if isinstance(ch, dict)
                }
                for chapter in candidate.get("chapters", []):
                    if not isinstance(chapter, dict):
                        continue
                    old = previous.get(str(chapter.get("id")))
                    if old and any(
                        old.get(k) != chapter.get(k)
                        for k in ("title", "narrative", "sections", "summary", "epigraph")
                    ):
                        key = str(chapter["id"])
                        backup = deepcopy(old)
                        backup["_archive_written_at"] = before.get("content_generated_at") or (
                            cached or {}
                        ).get("generated_at")
                        undo[key] = [*(undo.get(key) or []), backup][-5:]
                candidate["chapter_undo"] = undo
            # A fresh nonce prevents reset/undo ABA and distinguishes accepted writes.
            candidate["revision_id"] = uuid.uuid4().hex
            history = candidate.get("external_edit_history") or []
            if history and external_write:
                history[-1]["resulting_revision"] = chronicle_revision(candidate)
            self.upsert_chronicle_by_save_id(
                save_id=save_id,
                session_id=session_id,
                language=language,
                chronicle_text=assemble_chronicle(candidate),
                chapters_json=json_dumps(candidate),
                event_count=event_count,
                snapshot_count=snapshot_count,
            )
            return self.get_cached_chronicle_for_save(save_id, language=language) or {}

    def edit_chronicle_chapter(
        self,
        *,
        save_id: str,
        chapter_number: int,
        language: str,
        expected_revision: str,
        narrative: str = "",
        title: str | None = None,
        undo: bool = False,
    ) -> dict[str, Any]:
        """Edit or undo one chapter without replacing unrelated chapter revisions."""
        cached = self.get_cached_chronicle_for_save(save_id, language=language)
        if not cached:
            raise KeyError("Chronicle not found")
        data = load_chapters_data(cached)
        if chronicle_revision(data) != expected_revision:
            raise ChronicleConflict("The Chronicle changed. Read the newer version before editing.")
        chapters = data.get("chapters", [])
        chapter = next((ch for ch in chapters if ch.get("number") == chapter_number), None)
        if chapter is None:
            raise KeyError("Chapter not found")
        if undo:
            history = (data.get("chapter_undo") or {}).get(str(chapter["id"])) or []
            if not history:
                raise ValueError("This chapter has no previous revision to restore")
            restored = deepcopy(history[-1])
            previous_written_at = restored.pop("_archive_written_at", None)
            chapters[chapters.index(chapter)] = restored
            data["chapter_undo"][str(chapter["id"])] = history[:-1]
            dates = [previous_written_at]
            for item in chapters:
                dates.extend(
                    [
                        item.get("generated_at"),
                        item.get("edited_at"),
                        (item.get("external_edit") or {}).get("updated_at"),
                    ]
                )
            era_cache = data.get("current_era_cache") or {}
            dates.append(era_cache.get("generated_at"))
            data["content_generated_at"] = max(
                (date for date in dates if isinstance(date, str) and date), default=""
            )
        else:
            normalized = narrative.replace("\r\n", "\n").strip()
            if not normalized or len(normalized) > 100_000:
                raise ValueError("Chapter narrative must contain 1–100000 characters")
            if title is not None:
                normalized_title = title.strip()
                if not normalized_title or len(normalized_title) > 200:
                    raise ValueError("Chapter title must contain 1–200 characters")
                chapter["title"] = normalized_title
            chapter.update(
                narrative=normalized,
                sections=None,
                epigraph="",
                manual_edit_locked=True,
                source="player_edit",
            )
            # A generated summary can now contradict the player's correction.
            chapter["summary"] = ""
            chapter["edited_at"] = datetime.now(timezone.utc).isoformat()
            data["content_generated_at"] = chapter["edited_at"]
        for later in chapters:
            if later.get("number", 0) > chapter_number:
                later["context_stale"] = True
        era = (data.get("current_era_cache") or {}).get("current_era")
        if isinstance(era, dict):
            era["context_stale"] = True
        return self.commit_chronicle(
            save_id=save_id,
            session_id=str(cached["session_id"]),
            language=language,
            expected_revision=expected_revision,
            chapters_data=data,
            event_count=int(cached.get("event_count") or 0),
            snapshot_count=int(cached.get("snapshot_count") or 0),
            record_undo=not undo,
        )

    def get_chronicle_snapshot_range(
        self, save_id: str, upper_snapshot_id: int | None = None
    ) -> dict[str, Any]:
        """Dates belong to the boundary rows, including when a player rewinds time."""
        with self._lock:
            bounds = self._conn.execute(
                """SELECT MIN(sn.id) first_id, MAX(sn.id) last_id, COUNT(*) n
                   FROM snapshots sn JOIN sessions s ON s.id=sn.session_id
                   WHERE s.save_id=? AND (? IS NULL OR sn.id<=?)""",
                (save_id, upper_snapshot_id, upper_snapshot_id),
            ).fetchone()
            if not bounds or not bounds["n"]:
                return {"snapshot_count": 0}
            dates = {
                row["id"]: row["game_date"]
                for row in self._conn.execute(
                    "SELECT id, game_date FROM snapshots WHERE id IN (?,?)",
                    (bounds["first_id"], bounds["last_id"]),
                ).fetchall()
            }
            return {
                "first_snapshot_id": bounds["first_id"],
                "last_snapshot_id": bounds["last_id"],
                "first_game_date": dates.get(bounds["first_id"]),
                "last_game_date": dates.get(bounds["last_id"]),
                "snapshot_count": bounds["n"],
            }

    def get_historical_chronicle_briefing(self, save_id: str, snapshot_id: int) -> dict[str, Any]:
        """Use verified context at the chapter boundary, never the mutable latest state."""
        with self._lock:
            row = self._conn.execute(
                """SELECT sn.game_date,sn.full_briefing_json,sn.event_state_json FROM snapshots sn
                   JOIN sessions s ON s.id=sn.session_id WHERE s.save_id=? AND sn.id=?""",
                (save_id, snapshot_id),
            ).fetchone()
            if not row:
                return {}
            from backend.core.chronicle_store import compact_chronicle_context

            for raw in (row["full_briefing_json"], row["event_state_json"]):
                try:
                    data = json.loads(raw or "{}")
                    if data.get("chronicle_context"):
                        context = deepcopy(data["chronicle_context"])
                        context.setdefault("meta", {})["date"] = row["game_date"]
                        return context
                    if data.get("identity"):
                        context = compact_chronicle_context(data)
                        context["meta"]["date"] = row["game_date"]
                        return context
                except (ValueError, AttributeError):
                    continue
            # Legacy rows lack historical politics. Only date/version and the founding
            # empire name may be supplied; latest politics would be imagined backfill.
            baseline = self._conn.execute(
                """SELECT sn.full_briefing_json FROM snapshots sn JOIN sessions s ON s.id=sn.session_id
                   WHERE s.save_id=? AND sn.id<=? AND sn.full_briefing_json IS NOT NULL
                   ORDER BY sn.id ASC LIMIT 1""",
                (save_id, snapshot_id),
            ).fetchone()
            try:
                initial = json.loads(baseline[0]) if baseline else {}
            except ValueError:
                initial = {}
            meta = initial.get("meta") or {}
            return {
                "meta": {"date": row["game_date"]},
                "identity": {"empire_name": meta.get("empire_name")},
                "historical_context_limited": True,
            }

    def upsert_chronicle_by_save_id(
        self,
        *,
        save_id: str,
        session_id: str,
        chronicle_text: str,
        chapters_json: str,
        event_count: int,
        snapshot_count: int,
        language: str = "en",
    ) -> None:
        """Insert or update chronicle keyed by save_id."""
        with self._lock:
            # Check if chronicle exists for this save_id
            existing_by_save = self._conn.execute(
                "SELECT id FROM cached_chronicles WHERE save_id = ? AND language = ?",
                (save_id, language),
            ).fetchone()

            if existing_by_save:
                self._conn.execute(
                    """
                    UPDATE cached_chronicles
                    SET chronicle_text = ?,
                        chapters_json = ?,
                        event_count = ?,
                        snapshot_count = ?,
                        session_id = ?,
                        generated_at = datetime('now')
                    WHERE save_id = ? AND language = ?
                    """,
                    (
                        chronicle_text,
                        chapters_json,
                        event_count,
                        snapshot_count,
                        session_id,
                        save_id,
                        language,
                    ),
                )
            else:
                # Check if there's a legacy record for this session_id (without save_id)
                existing_by_session = self._conn.execute(
                    """
                    SELECT id FROM cached_chronicles
                    WHERE session_id = ? AND language = ? AND (save_id IS NULL OR save_id = '')
                    """,
                    (session_id, language),
                ).fetchone()

                if existing_by_session:
                    # Migrate existing record to use save_id
                    self._conn.execute(
                        """
                        UPDATE cached_chronicles
                        SET save_id = ?,
                            language = ?,
                            chronicle_text = ?,
                            chapters_json = ?,
                            event_count = ?,
                            snapshot_count = ?,
                            generated_at = datetime('now')
                        WHERE session_id = ? AND language = ?
                        """,
                        (
                            save_id,
                            language,
                            chronicle_text,
                            chapters_json,
                            event_count,
                            snapshot_count,
                            session_id,
                            language,
                        ),
                    )
                else:
                    # Insert new record
                    self._conn.execute(
                        """
                        INSERT INTO cached_chronicles
                            (id, session_id, save_id, language, chronicle_text, chapters_json, event_count, snapshot_count)
                        VALUES (lower(hex(randomblob(16))), ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            session_id,
                            save_id,
                            language,
                            chronicle_text,
                            chapters_json,
                            event_count,
                            snapshot_count,
                        ),
                    )


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

        # Best-effort background maintenance for older DBs.
        # Keeps startup fast while preventing unbounded full JSON accumulation.
        def _maintenance(db: GameDatabase) -> None:
            with contextlib.suppress(Exception):
                db.backfill_latest_briefings_all_sessions(limit_sessions=500)
            with contextlib.suppress(Exception):
                db.enforce_full_briefing_retention_all_sessions(
                    keep_recent=DEFAULT_KEEP_FULL_BRIEFINGS_RECENT, keep_first=True
                )
            with contextlib.suppress(Exception):
                db.maybe_checkpoint_wal()

        with contextlib.suppress(Exception):
            threading.Thread(
                target=_maintenance,
                args=(_default_db,),
                daemon=True,
                name="db-maintenance",
            ).start()
    return _default_db
