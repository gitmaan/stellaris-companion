#!/usr/bin/env python3
"""
Integration test for incremental chronicle generation.
Tests the updated ChronicleGenerator with save_id-based chapters.

Run: python scripts/test_incremental_chronicle.py
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load .env if exists
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def main():
    print("=" * 60)
    print("INCREMENTAL CHRONICLE INTEGRATION TEST")
    print("=" * 60)

    # Step 1: Initialize database
    print("\n1. Initializing database...")
    from backend.core.database import GameDatabase

    db = GameDatabase()
    print(f"   Schema version: {db.get_schema_version()}")

    # Verify migration 4 applied (save_id column)
    try:
        db.execute("SELECT save_id FROM cached_chronicles LIMIT 1")
        print("   save_id column: EXISTS")
    except Exception as e:
        print(f"   ERROR: save_id column NOT FOUND: {e}")
        return 1

    # Step 2: List sessions with save_id
    print("\n2. Available sessions:")
    sessions = db.get_sessions(limit=5)
    for s in sessions:
        save_id = s.get("save_id", "N/A")
        event_count = db.get_event_count(s["id"])
        print(
            f"   {s['id'][:8]}... | {s['empire_name']} | save_id={save_id[:16]}... | {event_count} events"
        )

    if not sessions:
        print("   No sessions found!")
        return 1

    # Use session with most snapshots
    session = max(sessions, key=lambda s: s.get("snapshot_count", 0))
    session_id = session["id"]
    save_id = session.get("save_id")
    print(f"\n3. Testing with: {session['empire_name']}")
    print(f"   Session ID: {session_id}")
    print(f"   Save ID: {save_id}")

    # Step 3: Test new database methods
    print("\n4. Testing new database methods...")

    if save_id:
        # Test get_save_id_for_session
        retrieved_save_id = db.get_save_id_for_session(session_id)
        print(
            f"   get_save_id_for_session: {retrieved_save_id[:16] if retrieved_save_id else 'None'}..."
        )

        # Test get_all_events_by_save_id
        all_events = db.get_all_events_by_save_id(save_id=save_id)
        print(f"   get_all_events_by_save_id: {len(all_events)} events")

        # Test get_snapshot_range_for_save
        snapshot_range = db.get_snapshot_range_for_save(save_id)
        print(
            f"   get_snapshot_range_for_save: {snapshot_range.get('first_game_date')} to {snapshot_range.get('last_game_date')}"
        )
        print(f"   Snapshot count: {snapshot_range.get('snapshot_count')}")
    else:
        print("   SKIP: No save_id for this session")

    # Step 4: Test ChronicleGenerator without LLM
    print("\n5. Testing ChronicleGenerator structure...")
    api_key = os.environ.get("GOOGLE_API_KEY")

    from backend.core.chronicle import ChronicleGenerator

    generator = ChronicleGenerator(db=db, api_key=api_key or "dummy")

    # Test _load_chapters_data
    chapters_data = generator._load_chapters_data(None)
    print(f"   Default chapters_data format: {chapters_data.get('format_version')}")
    print(f"   Default chapters: {len(chapters_data.get('chapters', []))}")

    # Test _should_finalize_chapter
    if save_id:
        snapshot_range = db.get_snapshot_range_for_save(save_id)
        should_finalize, trigger = generator._should_finalize_chapter(
            save_id=save_id,
            chapters_data=chapters_data,
            current_date=snapshot_range.get("last_game_date"),
            current_snapshot_id=snapshot_range.get("last_snapshot_id"),
        )
        print(f"   Should finalize first chapter: {should_finalize} (trigger: {trigger})")

        # Count pending chapters
        pending = generator._count_pending_chapters(
            save_id=save_id,
            chapters_data=chapters_data,
            current_date=snapshot_range.get("last_game_date"),
            current_snapshot_id=snapshot_range.get("last_snapshot_id"),
        )
        print(f"   Pending chapters: {pending}")

    if not api_key:
        print("\n   GOOGLE_API_KEY not set - skipping LLM calls")
        print("   Set GOOGLE_API_KEY to test full chronicle generation")

        # Test data gathering without LLM
        try:
            data = generator._gather_session_data(session_id)
            print("\n6. Gathered session data:")
            print(f"   Events: {len(data['events'])}")
            print(f"   Date range: {data['first_date']} to {data['last_date']}")
            print(
                f"   Empire: {data['briefing'].get('identity', {}).get('empire_name', 'Unknown')}"
            )
        except Exception as e:
            print(f"   Error gathering data: {e}")
            return 1

        print("\n" + "=" * 60)
        print("STRUCTURE TESTS PASSED (no LLM)")
        print("=" * 60)
        return 0

    # Full test with LLM
    print("\n6. Generating incremental chronicle (may take 15-30 seconds)...")
    try:
        result = generator.generate_chronicle(session_id=session_id, force_refresh=True)

        print("\n   Response fields:")
        print(f"   - chapters: {len(result.get('chapters', []))} chapters")
        print(f"   - current_era: {'present' if result.get('current_era') else 'none'}")
        print(f"   - pending_chapters: {result.get('pending_chapters', 0)}")
        print(f"   - message: {result.get('message')}")
        print(f"   - chronicle (backward compat): {len(result.get('chronicle', ''))} chars")
        print(f"   - cached: {result.get('cached')}")
        print(f"   - event_count: {result.get('event_count')}")

        # Show chapter details
        if result.get("chapters"):
            print("\n   Chapter details:")
            for ch in result["chapters"]:
                stale = "⚠️ STALE" if ch.get("context_stale") else ""
                print(
                    f"   - Chapter {ch['number']}: {ch['title']} ({ch['start_date']} - {ch['end_date']}) {stale}"
                )

        # Show current era
        if result.get("current_era"):
            era = result["current_era"]
            print(
                f"\n   Current Era: {era.get('start_date')} - present ({era.get('events_covered')} events)"
            )
            print(f"   Preview: {era.get('narrative', '')[:200]}...")

        # Save output
        output_path = Path(__file__).parent / "test_incremental_output.txt"
        output_path.write_text(result.get("chronicle", ""))
        print(f"\n   Saved full chronicle to: {output_path}")

    except Exception as e:
        print(f"   Error generating chronicle: {e}")
        import traceback

        traceback.print_exc()
        return 1

    # Step 7: Test caching
    print("\n7. Testing cache...")
    result2 = generator.generate_chronicle(session_id=session_id, force_refresh=False)
    print(f"   Second call cached: {result2.get('cached')}")
    print(f"   Chapters preserved: {len(result2.get('chapters', []))}")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
