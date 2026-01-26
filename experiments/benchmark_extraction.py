#!/usr/bin/env python3
"""
Benchmark: How long does extraction take?

Measures:
1. Save file load time (unzip + read gamestate)
2. Individual extractor method times
3. Complete briefing extraction time
4. JSON serialization time
"""

import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from save_extractor import SaveExtractor


def benchmark_extraction(save_path: str):
    """Benchmark all extraction operations."""

    print("=" * 70)
    print("EXTRACTION TIMING BENCHMARK")
    print("=" * 70)
    print(f"Save file: {save_path}")
    print(f"File size: {Path(save_path).stat().st_size / 1024 / 1024:.1f} MB")
    print()

    # 1. Save file load
    print("1. SAVE FILE LOAD")
    print("-" * 40)
    start = time.time()
    extractor = SaveExtractor(save_path)
    load_time = time.time() - start
    print(f"   Load time: {load_time * 1000:.0f}ms ({load_time:.2f}s)")
    print(f"   Gamestate size: {len(extractor.gamestate) / 1024 / 1024:.1f} MB")
    print()

    # 2. Individual method times
    print("2. INDIVIDUAL EXTRACTOR METHODS")
    print("-" * 40)

    methods = [
        ("get_metadata", lambda: extractor.get_metadata()),
        ("get_empire_identity", lambda: extractor.get_empire_identity()),
        ("get_situation", lambda: extractor.get_situation()),
        ("get_player_status", lambda: extractor.get_player_status()),
        ("get_resources", lambda: extractor.get_resources()),
        ("get_leaders", lambda: extractor.get_leaders()),
        ("get_planets", lambda: extractor.get_planets()),
        ("get_diplomacy", lambda: extractor.get_diplomacy()),
        ("get_technology", lambda: extractor.get_technology()),
        ("get_starbases", lambda: extractor.get_starbases()),
        ("get_fleets", lambda: extractor.get_fleets()),
        ("get_wars", lambda: extractor.get_wars()),
        ("get_fallen_empires", lambda: extractor.get_fallen_empires()),
    ]

    results = {}
    total_extract_time = 0

    for name, method in methods:
        start = time.time()
        result = method()
        elapsed = time.time() - start
        total_extract_time += elapsed

        result_json = json.dumps(result, default=str)
        size_kb = len(result_json) / 1024

        results[name] = {
            "time_ms": elapsed * 1000,
            "size_kb": size_kb,
            "data": result,
        }

        print(f"   {name:25} {elapsed * 1000:6.0f}ms  {size_kb:6.1f} KB")

    print(f"   {'─' * 40}")
    print(f"   {'TOTAL':25} {total_extract_time * 1000:6.0f}ms")
    print()

    # 3. Complete briefing (all at once, fresh extractor to avoid caching effects)
    print("3. COMPLETE BRIEFING (fresh extractor)")
    print("-" * 40)

    start = time.time()
    extractor2 = SaveExtractor(save_path)
    load_time2 = time.time() - start

    start = time.time()
    complete_briefing = {
        "meta": extractor2.get_metadata(),
        "identity": extractor2.get_empire_identity(),
        "situation": extractor2.get_situation(),
        "military": extractor2.get_player_status(),
        "economy": extractor2.get_resources(),
        "leaders": extractor2.get_leaders(),
        "planets": extractor2.get_planets(),
        "diplomacy": extractor2.get_diplomacy(),
        "technology": extractor2.get_technology(),
        "starbases": extractor2.get_starbases(),
        "fleets": extractor2.get_fleets(),
        "wars": extractor2.get_wars(),
        "fallen_empires": extractor2.get_fallen_empires(),
    }
    extract_time = time.time() - start

    start = time.time()
    briefing_json = json.dumps(complete_briefing, indent=2, default=str)
    json_time = time.time() - start

    print(f"   Save load:        {load_time2 * 1000:6.0f}ms")
    print(f"   All extractions:  {extract_time * 1000:6.0f}ms")
    print(f"   JSON serialize:   {json_time * 1000:6.0f}ms")
    print(f"   {'─' * 40}")
    print(f"   TOTAL:            {(load_time2 + extract_time + json_time) * 1000:6.0f}ms")
    print()
    print(f"   Briefing size:    {len(briefing_json) / 1024:.1f} KB")
    print()

    # 4. Reload time (simulating save watcher scenario)
    print("4. RELOAD SCENARIO (save changed, re-extract)")
    print("-" * 40)

    start = time.time()
    extractor3 = SaveExtractor(save_path)
    complete_briefing = {
        "meta": extractor3.get_metadata(),
        "identity": extractor3.get_empire_identity(),
        "situation": extractor3.get_situation(),
        "military": extractor3.get_player_status(),
        "economy": extractor3.get_resources(),
        "leaders": extractor3.get_leaders(),
        "planets": extractor3.get_planets(),
        "diplomacy": extractor3.get_diplomacy(),
        "technology": extractor3.get_technology(),
        "starbases": extractor3.get_starbases(),
        "fleets": extractor3.get_fleets(),
        "wars": extractor3.get_wars(),
        "fallen_empires": extractor3.get_fallen_empires(),
    }
    briefing_json = json.dumps(complete_briefing, indent=2, default=str)
    total_reload = time.time() - start

    print(
        f"   Full reload + extract + serialize: {total_reload * 1000:.0f}ms ({total_reload:.2f}s)"
    )
    print()

    # 5. Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"   Save file size:     {Path(save_path).stat().st_size / 1024 / 1024:.1f} MB")
    print(f"   Gamestate size:     {len(extractor.gamestate) / 1024 / 1024:.1f} MB")
    print(f"   Briefing JSON size: {len(briefing_json) / 1024:.1f} KB")
    print()
    print(f"   Initial load:       {load_time * 1000:.0f}ms")
    print(f"   Extraction only:    {extract_time * 1000:.0f}ms")
    print(f"   Full reload cycle:  {total_reload * 1000:.0f}ms ({total_reload:.2f}s)")
    print()

    # Categorize for architecture decision
    if total_reload < 1:
        print("   ✅ FAST: Can run synchronously on every save change")
    elif total_reload < 3:
        print("   ⚠️  MODERATE: Consider background thread")
    else:
        print("   🔴 SLOW: Needs background processing + caching")

    return {
        "load_time_ms": load_time * 1000,
        "extract_time_ms": extract_time * 1000,
        "total_reload_ms": total_reload * 1000,
        "briefing_size_kb": len(briefing_json) / 1024,
        "method_times": {k: v["time_ms"] for k, v in results.items()},
    }


if __name__ == "__main__":
    save_path = sys.argv[1] if len(sys.argv) > 1 else str(PROJECT_ROOT / "test_save.sav")

    if not Path(save_path).exists():
        print(f"Save file not found: {save_path}")
        sys.exit(1)

    results = benchmark_extraction(save_path)

    # Save results
    results_path = PROJECT_ROOT / "benchmark_extraction_results.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to: {results_path}")
