#!/usr/bin/env python3
"""
Phase 3 Integration Test
========================

Tests the full history tracking pipeline using real autosaves:
1. Load saves chronologically
2. Record snapshots to database
3. Verify event detection between saves
4. Test /history query logic
"""

import os
import sys
from pathlib import Path

# Setup path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env
env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text().split('\n'):
        if '=' in line and not line.startswith('#'):
            key, val = line.split('=', 1)
            os.environ.setdefault(key.strip(), val.strip())

from backend.core.database import GameDatabase
from backend.core.companion import Companion
from backend.core.history import (
    record_snapshot_from_companion,
    compute_save_id,
    extract_campaign_id_from_gamestate,
    extract_snapshot_metrics,
)

# Test configuration
SAVE_DIR = Path.home() / "Documents/Paradox Interactive/Stellaris/save games/unitednationsofearth2_-629118313"
TEST_DB_PATH = PROJECT_ROOT / "test_phase3.db"

SAVE_FILES = [
    "autosave_2448.07.01.sav",
    "autosave_2449.01.01.sav",
    "autosave_2449.07.01.sav",
    "autosave_2450.01.01.sav",
    "autosave_2450.07.01.sav",
]


def print_header(text: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {text}")
    print('='*60)


def print_section(text: str) -> None:
    print(f"\n--- {text} ---")


def test_phase3():
    """Run the full Phase 3 integration test."""

    print_header("PHASE 3 INTEGRATION TEST")
    print(f"Save directory: {SAVE_DIR}")
    print(f"Test database: {TEST_DB_PATH}")

    # Verify saves exist
    missing = [f for f in SAVE_FILES if not (SAVE_DIR / f).exists()]
    if missing:
        print(f"\nERROR: Missing save files: {missing}")
        return False
    print(f"\nFound {len(SAVE_FILES)} save files to process")

    # Clean up old test database
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
        print("Removed old test database")

    # Initialize database
    print_section("Initializing Database")
    db = GameDatabase(str(TEST_DB_PATH))
    print(f"Database initialized at {TEST_DB_PATH}")

    # Track results
    results = {
        "saves_processed": 0,
        "snapshots_inserted": 0,
        "snapshots_skipped": 0,
        "sessions_created": set(),
        "events_generated": 0,
        "errors": [],
    }

    # Process each save chronologically
    print_section("Processing Saves Chronologically")

    for i, save_file in enumerate(SAVE_FILES):
        save_path = SAVE_DIR / save_file
        print(f"\n[{i+1}/{len(SAVE_FILES)}] Loading: {save_file}")

        try:
            # Load save with Companion
            companion = Companion(save_path=save_path)

            if not companion.is_loaded:
                results["errors"].append(f"Failed to load {save_file}")
                continue

            # Get metadata
            meta = companion.metadata
            print(f"    Empire: {meta.get('name', 'Unknown')}")
            print(f"    Date: {meta.get('date', 'Unknown')}")

            # Record snapshot
            inserted, snapshot_id, session_id = record_snapshot_from_companion(
                db=db,
                save_path=save_path,
                save_hash=getattr(companion, "_save_hash", None),
                gamestate=getattr(companion.extractor, "gamestate", None) if companion.extractor else None,
                player_id=companion.extractor.get_player_empire_id() if companion.extractor else None,
                briefing=getattr(companion, "_current_snapshot", None) or companion.get_snapshot(),
            )

            results["saves_processed"] += 1
            results["sessions_created"].add(session_id)

            if inserted:
                results["snapshots_inserted"] += 1
                print(f"    -> Snapshot #{snapshot_id} recorded (session: {session_id[:8]}...)")
            else:
                results["snapshots_skipped"] += 1
                print(f"    -> Snapshot skipped (duplicate)")

        except Exception as e:
            results["errors"].append(f"{save_file}: {str(e)}")
            print(f"    ERROR: {e}")

    # Verify database contents
    print_section("Verifying Database Contents")

    # Count records
    cursor = db._conn.execute("SELECT COUNT(*) FROM sessions")
    session_count = cursor.fetchone()[0]

    cursor = db._conn.execute("SELECT COUNT(*) FROM snapshots")
    snapshot_count = cursor.fetchone()[0]

    cursor = db._conn.execute("SELECT COUNT(*) FROM events")
    event_count = cursor.fetchone()[0]
    results["events_generated"] = event_count

    print(f"Sessions: {session_count}")
    print(f"Snapshots: {snapshot_count}")
    print(f"Events: {event_count}")

    # Show session details
    print_section("Session Details")
    cursor = db._conn.execute("""
        SELECT id, empire_name, started_at, last_game_date, ended_at
        FROM sessions
    """)
    for row in cursor.fetchall():
        sid, empire, started, last_date, ended = row
        status = "ENDED" if ended else "ACTIVE"
        print(f"  {sid[:12]}... | {empire} | {last_date} | {status}")

    # Show snapshots timeline
    print_section("Snapshots Timeline")
    cursor = db._conn.execute("""
        SELECT game_date, military_power, colony_count, energy_net, alloys_net, wars_count
        FROM snapshots
        ORDER BY id
    """)
    print(f"  {'Date':<12} {'Military':>10} {'Colonies':>10} {'Energy':>10} {'Alloys':>10} {'Wars':>6}")
    print(f"  {'-'*12} {'-'*10} {'-'*10} {'-'*10} {'-'*10} {'-'*6}")
    for row in cursor.fetchall():
        date, mil, col, energy, alloys, wars = row
        mil_str = f"{mil:,}" if mil else "n/a"
        col_str = str(col) if col else "n/a"
        energy_str = f"{energy:+.1f}" if energy is not None else "n/a"
        alloys_str = f"{alloys:+.1f}" if alloys is not None else "n/a"
        wars_str = str(wars) if wars is not None else "n/a"
        print(f"  {date:<12} {mil_str:>10} {col_str:>10} {energy_str:>10} {alloys_str:>10} {wars_str:>6}")

    # Show events
    print_section("Generated Events")
    cursor = db._conn.execute("""
        SELECT game_date, event_type, summary
        FROM events
        ORDER BY id
    """)
    events = cursor.fetchall()
    if events:
        for date, etype, summary in events:
            print(f"  [{date}] {etype}: {summary}")
    else:
        print("  (No events generated - this may indicate a problem with event detection)")

    # Test history query functions
    print_section("Testing History Query Functions")

    # Get session ID for testing
    cursor = db._conn.execute("SELECT id FROM sessions LIMIT 1")
    row = cursor.fetchone()
    if row:
        test_session_id = row[0]

        # Test get_session_snapshot_stats
        stats = db.get_session_snapshot_stats(test_session_id)
        print(f"get_session_snapshot_stats():")
        print(f"  snapshot_count: {stats.get('snapshot_count')}")
        print(f"  first_game_date: {stats.get('first_game_date')}")
        print(f"  last_game_date: {stats.get('last_game_date')}")

        # Test get_recent_events
        recent = db.get_recent_events(session_id=test_session_id, limit=5)
        print(f"get_recent_events(limit=5): {len(recent)} events")

        # Test get_recent_snapshot_points
        points = db.get_recent_snapshot_points(session_id=test_session_id, limit=5)
        print(f"get_recent_snapshot_points(limit=5): {len(points)} points")

    # Test history_context module
    print_section("Testing History Context Builder")
    try:
        from backend.core.history_context import should_include_history, build_history_context

        test_questions = [
            "What changed since last save?",
            "How is my economy trending?",
            "What should I build next?",  # Should NOT trigger history
            "Compare my military to last session",
        ]

        for q in test_questions:
            triggered = should_include_history(q)
            print(f"  '{q[:40]}...' -> history={triggered}")

        # Build actual history context
        if row:
            # We need save_id to test build_history_context
            cursor = db._conn.execute("SELECT save_id FROM sessions WHERE id = ?", (test_session_id,))
            save_id_row = cursor.fetchone()
            if save_id_row:
                ctx = build_history_context(
                    db=db,
                    campaign_id=None,
                    player_id=0,
                    empire_name="United Nations of Earth",
                    save_path=SAVE_DIR / SAVE_FILES[-1],
                    max_events=5,
                    max_points=5,
                )
                if ctx:
                    print(f"\nHistory context ({len(ctx)} chars):")
                    # Show first few lines
                    for line in ctx.split('\n')[:10]:
                        print(f"  {line}")
                    if ctx.count('\n') > 10:
                        print(f"  ... ({ctx.count(chr(10)) - 10} more lines)")
                else:
                    print("\n  (No history context generated)")
    except ImportError as e:
        print(f"  Could not import history_context module: {e}")
    except Exception as e:
        print(f"  Error testing history context: {e}")

    # Summary
    print_header("TEST SUMMARY")
    print(f"Saves processed: {results['saves_processed']}/{len(SAVE_FILES)}")
    print(f"Snapshots inserted: {results['snapshots_inserted']}")
    print(f"Snapshots skipped (duplicates): {results['snapshots_skipped']}")
    print(f"Sessions created: {len(results['sessions_created'])}")
    print(f"Events generated: {results['events_generated']}")

    if results["errors"]:
        print(f"\nErrors ({len(results['errors'])}):")
        for err in results["errors"]:
            print(f"  - {err}")

    # Pass/fail determination
    passed = (
        results["saves_processed"] == len(SAVE_FILES)
        and results["snapshots_inserted"] >= 1
        and len(results["sessions_created"]) >= 1
        and len(results["errors"]) == 0
    )

    print(f"\n{'PASSED' if passed else 'FAILED'}")

    # Recommendations
    if results["events_generated"] == 0:
        print("\nNOTE: No events were generated. This could mean:")
        print("  - Event detection thresholds are too high")
        print("  - The saves are too similar (no significant changes)")
        print("  - There's a bug in record_events_for_new_snapshot()")

    return passed


if __name__ == "__main__":
    success = test_phase3()
    sys.exit(0 if success else 1)
