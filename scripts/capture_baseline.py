#!/usr/bin/env python3
"""Capture baseline output from current extraction methods before migration."""

import json
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from save_extractor import SaveExtractor

BASELINE_DIR = Path(__file__).parent.parent / "tests" / "migration_baselines"
TEST_SAVE = Path(__file__).parent.parent / "test_save.sav"


def capture_baseline(method_name: str, save_path: str = None):
    """Capture baseline output for a method."""
    save_path = save_path or str(TEST_SAVE)

    if not os.path.exists(save_path):
        print(f"ERROR: Save file not found: {save_path}")
        sys.exit(1)

    BASELINE_DIR.mkdir(parents=True, exist_ok=True)

    ext = SaveExtractor(save_path)

    # Get the method
    if not hasattr(ext, method_name):
        print(f"ERROR: Method not found: {method_name}")
        print(
            f"Available methods: {[m for m in dir(ext) if m.startswith('get_') or m.startswith('extract_')]}"
        )
        sys.exit(1)

    method = getattr(ext, method_name)

    try:
        result = method()
    except Exception as e:
        print(f"ERROR: Method failed: {e}")
        sys.exit(1)

    # Save baseline
    baseline_file = BASELINE_DIR / f"{method_name}.json"

    def json_serializer(obj):
        """Handle non-serializable objects."""
        if hasattr(obj, "__dict__"):
            return obj.__dict__
        return str(obj)

    with open(baseline_file, "w") as f:
        json.dump(result, f, indent=2, default=json_serializer)

    print(f"✅ Baseline saved: {baseline_file}")
    print(f"   Result type: {type(result).__name__}")
    if isinstance(result, dict):
        print(f"   Keys: {list(result.keys())[:10]}")
    elif isinstance(result, list):
        print(f"   Items: {len(result)}")

    return result


def list_methods():
    """List all extractable methods."""
    ext = SaveExtractor.__new__(SaveExtractor)
    methods = [m for m in dir(ext) if m.startswith("get_") or m.startswith("extract_")]
    print("Available methods:")
    for m in sorted(methods):
        print(f"  - {m}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python capture_baseline.py <method_name> [save_path]")
        print("       python capture_baseline.py --list")
        sys.exit(1)

    if sys.argv[1] == "--list":
        list_methods()
    else:
        method_name = sys.argv[1]
        save_path = sys.argv[2] if len(sys.argv) > 2 else None
        capture_baseline(method_name, save_path)
