"""
SQLite database utilities for Stellaris Companion history (Phase 3).

Milestone 0: schema + migrations + safe initialization.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import json

from backend.core.events import compute_events


DEFAULT_DB_FILENAME = "stellaris_history.db"
ENV_DB_PATH = "STELLARIS_DB_PATH"

# Default DB retention (no user-facing knobs).
# Keep the earliest full briefing (baseline) plus the most recent N per session.
DEFAULT_KEEP_FULL_BRIEFINGS_RECENT = 20


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
            row = self._conn.execute(
                """
                SELECT full_briefing_json
                FROM snapshots
                WHERE full_briefing_json IS NOT NULL AND full_briefing_json != ''
                ORDER BY captured_at DESC, id DESC
                LIMIT 1;
                """
            ).fetchone()
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
                    full_briefing_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
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
    ) -> tuple[bool, int | None]:
        latest = self.get_latest_snapshot_identity(session_id)
        if latest:
            latest_hash = latest.get("save_hash")
            latest_date = latest.get("game_date")
            if save_hash and latest_hash == save_hash:
                return False, None
            if (save_hash is None) and game_date and latest_date == game_date:
                return False, None

        snapshot_id = self.insert_snapshot(
            session_id=session_id,
            game_date=game_date,
            save_hash=save_hash,
            military_power=military_power,
            colony_count=colony_count,
            wars_count=wars_count,
            energy_net=energy_net,
            alloys_net=alloys_net,
            full_briefing_json=full_briefing_json,
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

    def end_active_sessions_for_save(self, *, save_id: str, ended_at: int | None = None) -> list[str]:
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
                return {"snapshot_count": 0, "first_game_date": None, "last_game_date": None}
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
                       full_briefing_json
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
                    json.dumps(e.get("data") or {}, ensure_ascii=False, separators=(",", ":")),
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
        prev_id = self.get_previous_snapshot_id(session_id=session_id, before_snapshot_id=int(snapshot_id))
        if prev_id is None:
            return 0

        prev_row = self.get_snapshot_row(prev_id)
        curr_row = self.get_snapshot_row(int(snapshot_id))
        if not prev_row or not curr_row:
            return 0

        prev_json = prev_row.get("full_briefing_json")
        if not isinstance(prev_json, str) or not prev_json:
            return 0

        try:
            prev_briefing = json.loads(prev_json)
        except Exception:
            return 0

        detected = compute_events(
            prev=prev_briefing if isinstance(prev_briefing, dict) else {},
            curr=current_briefing if isinstance(current_briefing, dict) else {},
            from_snapshot_id=int(prev_id),
            to_snapshot_id=int(snapshot_id),
        )
        payloads = [{"event_type": e.event_type, "summary": e.summary, "data": e.data} for e in detected]

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

    def get_first_last_snapshot_rows(self, *, session_id: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        with self._lock:
            first = self._conn.execute(
                """
                SELECT id, captured_at, game_date, full_briefing_json
                FROM snapshots
                WHERE session_id = ?
                ORDER BY captured_at ASC, id ASC
                LIMIT 1;
                """,
                (session_id,),
            ).fetchone()
            last = self._conn.execute(
                """
                SELECT id, captured_at, game_date, full_briefing_json
                FROM snapshots
                WHERE session_id = ?
                ORDER BY captured_at DESC, id DESC
                LIMIT 1;
                """,
                (session_id,),
            ).fetchone()
            return (dict(first) if first else None, dict(last) if last else None)

    def get_recent_snapshot_points(self, *, session_id: str, limit: int = 8) -> list[dict[str, Any]]:
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
