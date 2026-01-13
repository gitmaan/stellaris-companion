#!/usr/bin/env python3
"""
Fresh Stress Test - January 2026
================================

Re-run stress tests AFTER building/tech fixes were added to snapshot.
Tests whether model correctly uses tools vs hallucinates.
"""

import json
import time
from datetime import datetime
from pathlib import Path

import os
# Load .env manually
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    for line in env_path.read_text().split('\n'):
        if '=' in line and not line.startswith('#'):
            key, val = line.split('=', 1)
            os.environ[key.strip()] = val.strip()

from google import genai
from google.genai import types
from save_extractor import SaveExtractor
from personality import build_optimized_prompt

MODEL = "gemini-3-flash-preview"

# Mix of questions: some answerable from snapshot, some require tools
STRESS_QUESTIONS = [
    # SHOULD be in snapshot now (after fixes)
    ("What buildings are on Earth?", "snapshot_has_buildings"),
    ("What am I currently researching?", "snapshot_has_tech"),

    # Should NOT be in snapshot - requires tools
    ("What traits does my highest level admiral have?", "needs_leader_details"),
    ("What are the opinion modifiers with my closest ally?", "needs_diplomacy_details"),
    ("What ship designs do I have?", "needs_fleet_details"),

    # Edge cases - may or may not be in snapshot
    ("What is the population breakdown by species?", "might_need_details"),
    ("What starbases have shipyards?", "needs_starbase_details"),
]


def find_save_file() -> Path:
    """Find the most recent Stellaris save file."""
    save_dirs = [
        Path.home() / "Documents/Paradox Interactive/Stellaris/save games",
    ]
    for save_dir in save_dirs:
        if save_dir.exists():
            sav_files = list(save_dir.rglob("*.sav"))
            if sav_files:
                return max(sav_files, key=lambda p: p.stat().st_mtime)
    raise FileNotFoundError("No Stellaris save files found")


def run_test(client, extractor, system_prompt: str, snapshot: dict, question: str) -> dict:
    """Run a single test, tracking tool usage."""

    snapshot_json = json.dumps(snapshot, separators=(',', ':'), default=str)

    user_message = f"""CURRENT_GAME_STATE (use this for facts):
```json
{snapshot_json}
```

QUESTION: {question}

RULES:
- Use the JSON above for facts. If data isn't present, call tools or say 'unknown'.
- Available tools: get_details(categories), search_save_file(query)
"""

    tools_used = []

    def get_details(categories: list[str], limit: int = 50) -> dict:
        """Get detailed data for specific categories."""
        tools_used.append(f"get_details({categories})")
        return extractor.get_details(categories, limit)

    def search_save_file(query: str, limit: int = 20) -> dict:
        """Search the save file for specific data."""
        tools_used.append(f"search({query})")
        return extractor.search(query)

    start = time.time()

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=[get_details, search_save_file],
        temperature=0.5,
        max_output_tokens=1024,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(
            maximum_remote_calls=8,
        ),
    )

    response = client.models.generate_content(
        model=MODEL,
        contents=user_message,
        config=config,
    )

    elapsed = time.time() - start
    text = response.text if response.text else "[No text response]"

    # Check if model admitted not knowing
    admitted_unknown = any(phrase in text.lower() for phrase in [
        "don't have", "do not have", "not available", "cannot find",
        "need to", "would need", "i'll need", "let me check",
        "unknown", "not in the data", "not included", "not listed"
    ])

    return {
        'response': text,
        'time': elapsed,
        'words': len(text.split()),
        'tools_used': tools_used,
        'tool_count': len(tools_used),
        'admitted_unknown': admitted_unknown,
    }


def main():
    print("=" * 80)
    print("FRESH STRESS TEST - Post-Fix Verification")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Model: {MODEL}")
    print("=" * 80)

    save_path = find_save_file()
    print(f"Save: {save_path.name}")

    extractor = SaveExtractor(str(save_path))
    identity = extractor.get_empire_identity()
    situation = extractor.get_situation()

    # Get snapshot
    snapshot = extractor.get_full_briefing()
    snapshot_json = json.dumps(snapshot, separators=(',', ':'), default=str)

    print(f"Empire: {identity.get('empire_name')}")
    print(f"Snapshot size: {len(snapshot_json):,} chars")

    # Show what's IN the snapshot
    print(f"\n=== SNAPSHOT CONTENTS ===")
    print(f"Leaders in snapshot: {len(snapshot.get('leadership', {}).get('leaders', []))}")
    print(f"Planets in snapshot: {len(snapshot.get('territory', {}).get('top_colonies', []))}")

    tech = snapshot.get('technology', {})
    current_research = tech.get('current_research', {})
    print(f"Current research: {list(current_research.keys())}")

    # Check if buildings are in planets
    planets = snapshot.get('territory', {}).get('top_colonies', [])
    if planets:
        earth = next((p for p in planets if p.get('name') == 'Earth'), None)
        if earth:
            print(f"Earth buildings: {earth.get('buildings', 'NOT PRESENT')}")

    print()

    system_prompt = build_optimized_prompt(identity, situation)
    client = genai.Client()

    results = []

    print("=" * 80)
    print("RUNNING TESTS...")
    print("=" * 80)

    for qi, (question, category) in enumerate(STRESS_QUESTIONS, 1):
        print(f"\nQ{qi}: {question}")
        print(f"  Category: {category}")
        print("-" * 60)

        try:
            result = run_test(client, extractor, system_prompt, snapshot, question)

            # Determine status
            if result['tool_count'] > 0:
                status = "✅ USED TOOLS"
            elif result['admitted_unknown']:
                status = "⚠️ ADMITTED UNKNOWN"
            elif category.startswith("snapshot_has"):
                status = "✅ ANSWERED FROM SNAPSHOT"
            else:
                status = "❌ CHECK FOR HALLUCINATION"

            print(f"  {status}")
            print(f"  Time: {result['time']:.1f}s | Words: {result['words']} | Tools: {result['tool_count']}")
            if result['tools_used']:
                print(f"  Tool calls: {result['tools_used']}")

            # Show response preview
            preview = result['response'][:200].replace('\n', ' ')
            if len(result['response']) > 200:
                preview += "..."
            print(f"  Preview: {preview}")

            results.append({
                'question': question,
                'category': category,
                'status': status,
                **result
            })

        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({
                'question': question,
                'category': category,
                'status': "ERROR",
                'response': str(e),
                'time': 0,
                'words': 0,
                'tools_used': [],
                'tool_count': 0,
                'admitted_unknown': False,
            })

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    used_tools = sum(1 for r in results if r['tool_count'] > 0)
    from_snapshot = sum(1 for r in results if "SNAPSHOT" in r['status'])
    admitted_unknown = sum(1 for r in results if "ADMITTED" in r['status'])
    possible_hallucination = sum(1 for r in results if "HALLUCINATION" in r['status'])
    errors = sum(1 for r in results if "ERROR" in r['status'])

    print(f"✅ Used tools correctly: {used_tools}/{len(results)}")
    print(f"✅ Answered from snapshot: {from_snapshot}/{len(results)}")
    print(f"⚠️ Admitted unknown: {admitted_unknown}/{len(results)}")
    print(f"❌ Possible hallucination: {possible_hallucination}/{len(results)}")
    if errors:
        print(f"🔴 Errors: {errors}/{len(results)}")

    # Write report
    report = f"""# Fresh Stress Test Results

**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}

**Model:** {MODEL}

**Purpose:** Verify tool usage after building/tech fixes were added to snapshot.

---

## Summary

| Outcome | Count |
|---------|-------|
| ✅ Used tools | {used_tools}/{len(results)} |
| ✅ From snapshot | {from_snapshot}/{len(results)} |
| ⚠️ Admitted unknown | {admitted_unknown}/{len(results)} |
| ❌ Possible hallucination | {possible_hallucination}/{len(results)} |

---

## Snapshot Contents

- Leaders: {len(snapshot.get('leadership', {}).get('leaders', []))} (truncated)
- Planets: {len(snapshot.get('territory', {}).get('top_colonies', []))} (top 10)
- Current research: {list(current_research.keys())}
- Buildings in Earth: {earth.get('buildings', 'N/A') if earth else 'N/A'}

---

## Individual Results

"""

    for r in results:
        report += f"""### Q: {r['question']}

**Category:** {r['category']}
**Status:** {r['status']}
**Time:** {r['time']:.1f}s | **Words:** {r['words']} | **Tool calls:** {r['tool_count']}

"""
        if r['tools_used']:
            report += f"**Tools:** {', '.join(r['tools_used'])}\n\n"

        report += f"**Response:**\n\n{r['response']}\n\n---\n\n"

    output_path = Path("FRESH_STRESS_TEST.md")
    output_path.write_text(report)
    print(f"\nFull report: {output_path}")

    # Also save JSON for analysis
    json_path = Path("fresh_stress_results.json")
    json_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"JSON results: {json_path}")


if __name__ == "__main__":
    main()
