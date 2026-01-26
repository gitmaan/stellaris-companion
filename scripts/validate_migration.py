#!/usr/bin/env python3
"""Validate migrated extraction against baseline."""

import json
import os
import sys
from pathlib import Path
from typing import Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from save_extractor import SaveExtractor

BASELINE_DIR = Path(__file__).parent.parent / "tests" / "migration_baselines"
TEST_SAVE = Path(__file__).parent.parent / "test_save.sav"


def deep_diff(old: Any, new: Any, path: str = "") -> list[str]:
    """Find differences between old and new values."""
    diffs = []

    if type(old) != type(new):
        diffs.append(f"{path}: type changed from {type(old).__name__} to {type(new).__name__}")
        return diffs

    if isinstance(old, dict):
        all_keys = set(old.keys()) | set(new.keys())
        for key in all_keys:
            new_path = f"{path}.{key}" if path else key
            if key not in old:
                diffs.append(f"{new_path}: added (new value: {repr(new[key])[:100]})")
            elif key not in new:
                diffs.append(f"{new_path}: removed (old value: {repr(old[key])[:100]})")
            else:
                diffs.extend(deep_diff(old[key], new[key], new_path))
    elif isinstance(old, list):
        if len(old) != len(new):
            diffs.append(f"{path}: list length changed from {len(old)} to {len(new)}")
        for i, (o, n) in enumerate(zip(old, new, strict=False)):
            diffs.extend(deep_diff(o, n, f"{path}[{i}]"))
    elif old != new:
        old_str = repr(old)[:50]
        new_str = repr(new)[:50]
        diffs.append(f"{path}: value changed from {old_str} to {new_str}")

    return diffs


def validate_migration(method_name: str, save_path: str = None, update_baseline: bool = False):
    """Validate migrated method against baseline."""
    save_path = save_path or str(TEST_SAVE)

    if not os.path.exists(save_path):
        print(f"ERROR: Save file not found: {save_path}")
        sys.exit(1)

    baseline_file = BASELINE_DIR / f"{method_name}.json"
    if not baseline_file.exists():
        print(f"ERROR: Baseline not found: {baseline_file}")
        print(f"Run: python scripts/capture_baseline.py {method_name}")
        sys.exit(1)

    # Load baseline
    with open(baseline_file) as f:
        baseline = json.load(f)

    # Run new extraction
    ext = SaveExtractor(save_path)

    if not hasattr(ext, method_name):
        print(f"ERROR: Method not found: {method_name}")
        sys.exit(1)

    method = getattr(ext, method_name)

    try:
        result = method()
    except Exception as e:
        print(f"ERROR: Method failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    # Serialize for comparison
    def json_serializer(obj):
        if hasattr(obj, "__dict__"):
            return obj.__dict__
        return str(obj)

    result_json = json.loads(json.dumps(result, default=json_serializer))

    # Compare
    diffs = deep_diff(baseline, result_json)

    if not diffs:
        print(f"✅ {method_name}: Output matches baseline exactly")
        return True

    # Check if differences are improvements
    print(f"⚠️  {method_name}: Found {len(diffs)} difference(s)")
    print()

    improvements = []
    regressions = []

    for diff in diffs[:20]:  # Show first 20
        # Heuristic: if old value looks like a localization key and new is readable, it's an improvement
        if "NEW_COLONY" in diff or "PLANET_FORMAT" in diff or "NAME_" in diff:
            improvements.append(diff)
        elif "value changed from" in diff:
            # Could be improvement or regression - needs review
            print(f"  CHANGED: {diff}")
        else:
            regressions.append(diff)

    if improvements:
        print(f"\n🎉 IMPROVEMENTS ({len(improvements)}):")
        for imp in improvements[:10]:
            print(f"  + {imp}")

    if regressions:
        print(f"\n❌ REGRESSIONS ({len(regressions)}):")
        for reg in regressions[:10]:
            print(f"  - {reg}")

    if len(diffs) > 20:
        print(f"\n  ... and {len(diffs) - 20} more differences")

    if update_baseline and not regressions:
        print("\n📝 Updating baseline (improvements only)...")
        with open(baseline_file, "w") as f:
            json.dump(result_json, f, indent=2, default=json_serializer)
        print(f"✅ Baseline updated: {baseline_file}")
        return True

    if regressions:
        print(f"\n❌ FAILED: {len(regressions)} regressions found")
        sys.exit(1)
    else:
        print("\n⚠️  Review improvements above. Use --update to accept them.")
        return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python validate_migration.py <method_name> [save_path] [--update]")
        sys.exit(1)

    method_name = sys.argv[1]
    save_path = None
    update = False

    for arg in sys.argv[2:]:
        if arg == "--update":
            update = True
        else:
            save_path = arg

    validate_migration(method_name, save_path, update)
