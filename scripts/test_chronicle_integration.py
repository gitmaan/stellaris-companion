#!/usr/bin/env python3
"""
Integration test for chronicle generation.
Tests the full ChronicleGenerator against real database data.

Run: python scripts/test_chronicle_integration.py
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
    print("CHRONICLE INTEGRATION TEST")
    print("=" * 60)

    # Step 1: Initialize database (applies migration 3 if needed)
    print("\n1. Initializing database...")
    from backend.core.database import GameDatabase

    db = GameDatabase()
    print(f"   Schema version: {db.get_schema_version()}")

    # Verify cached_chronicles table exists
    tables = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='cached_chronicles'"
    ).fetchall()
    if tables:
        print("   cached_chronicles table: EXISTS")
    else:
        print("   ERROR: cached_chronicles table NOT FOUND")
        return 1

    # Step 2: List sessions
    print("\n2. Available sessions:")
    sessions = db.get_sessions(limit=5)
    for s in sessions:
        event_count = db.get_event_count(s["id"])
        print(
            f"   {s['id'][:8]}... | {s['empire_name']} | {event_count} events | {s['snapshot_count']} snapshots"
        )

    if not sessions:
        print("   No sessions found!")
        return 1

    # Use session with most events
    session = max(sessions, key=lambda s: s.get("snapshot_count", 0))
    session_id = session["id"]
    print(f"\n3. Testing with: {session['empire_name']} ({session['snapshot_count']} snapshots)")

    # Step 3: Test get_all_events (no 100 cap)
    print("\n4. Testing get_all_events()...")
    all_events = db.get_all_events(session_id=session_id)
    print(f"   Retrieved {len(all_events)} events (no cap)")

    # Compare with get_recent_events (has 100 cap)
    recent = db.get_recent_events(session_id=session_id, limit=1000)
    print(f"   get_recent_events(limit=1000) returned {len(recent)} (capped at 100)")

    # Step 4: Test ChronicleGenerator
    print("\n5. Testing ChronicleGenerator...")

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("   GOOGLE_API_KEY not set - skipping LLM call")
        print("   Set GOOGLE_API_KEY to test full generation")

        # Test data gathering without LLM
        from backend.core.chronicle import ChronicleGenerator

        generator = ChronicleGenerator(db=db, api_key="dummy")

        try:
            data = generator._gather_session_data(session_id)
            print(f"   Gathered data: {len(data['events'])} events")
            print(f"   Date range: {data['first_date']} to {data['last_date']}")

            prompt = generator._build_chronicler_prompt(data)
            print(f"   Prompt built: {len(prompt):,} chars (~{len(prompt) // 4:,} tokens)")

            # Save prompt for inspection
            prompt_path = Path(__file__).parent / "test_chronicle_prompt_integration.txt"
            prompt_path.write_text(prompt)
            print(f"   Saved prompt to: {prompt_path}")
        except Exception as e:
            print(f"   Error gathering data: {e}")
            return 1

        return 0

    # Full test with LLM
    from backend.core.chronicle import ChronicleGenerator

    generator = ChronicleGenerator(db=db)

    print("   Generating chronicle (this may take 10-20 seconds)...")
    try:
        result = generator.generate_chronicle(session_id=session_id, force_refresh=True)

        chronicle = result["chronicle"]
        cached = result["cached"]
        event_count = result["event_count"]

        print(f"\n   Generated: {len(chronicle):,} chars")
        print(f"   Events used: {event_count}")
        print(f"   Cached: {cached}")

        # Save output
        output_path = Path(__file__).parent / "test_chronicle_output_integration.txt"
        output_path.write_text(chronicle)
        print(f"   Saved to: {output_path}")

        # Show preview
        print("\n" + "=" * 60)
        print("CHRONICLE PREVIEW (first 1500 chars)")
        print("=" * 60)
        print(chronicle[:1500])
        if len(chronicle) > 1500:
            print(f"\n... ({len(chronicle) - 1500} more chars)")

    except Exception as e:
        print(f"   Error generating chronicle: {e}")
        import traceback

        traceback.print_exc()
        return 1

    # Step 5: Test caching
    print("\n" + "=" * 60)
    print("6. Testing cache...")
    result2 = generator.generate_chronicle(session_id=session_id, force_refresh=False)
    print(f"   Second call cached: {result2['cached']}")

    if result2["cached"]:
        print("   Cache working correctly!")
    else:
        print("   WARNING: Cache not working as expected")

    # Step 6: Test recap
    print("\n7. Testing recap (dramatic style)...")
    try:
        recap_result = generator.generate_recap(session_id=session_id, style="dramatic")
        print(f"   Generated: {len(recap_result['recap']):,} chars")
        print(f"   Events: {recap_result['events_summarized']}")
        print("\n   Preview:")
        print(recap_result["recap"][:500])
    except Exception as e:
        print(f"   Error: {e}")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
