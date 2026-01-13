#!/usr/bin/env python3
"""
Tool Usage Stress Test
======================

Tests questions that REQUIRE tool calls to answer properly.
The pre-injected snapshot doesn't contain this data.

If the model answers without tools, it's either:
1. Making stuff up (BAD)
2. Saying "I don't know" (GOOD)
3. Calling tools (GOOD)
"""

import json
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from google import genai
from google.genai import types
from save_extractor import SaveExtractor
from personality import build_optimized_prompt

MODEL = "gemini-3-flash-preview"

# Questions that REQUIRE tool calls - snapshot doesn't have this data
STRESS_QUESTIONS = [
    # Leader-specific (snapshot only has counts, not details)
    "What traits does Admiral Manon have and how much experience?",

    # Planet-specific (snapshot has top 10 summary, not buildings)
    "What buildings are currently on Earth?",

    # Technology-specific (snapshot doesn't include tech tree)
    "What specific technologies am I currently researching?",

    # Fleet-specific (snapshot has power, not composition)
    "What ship types make up my main fleet?",

    # Diplomacy-specific (snapshot has counts, not details)
    "What are the specific opinion modifiers with empire ID 1?",
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


def build_snapshot(extractor) -> dict:
    """Build the SAME snapshot used in production - intentionally limited."""
    return extractor.get_full_briefing()


def run_test(client, extractor, system_prompt: str, snapshot: dict, question: str) -> dict:
    """Run a single test, tracking tool usage."""

    snapshot_json = json.dumps(snapshot, separators=(',', ':'), default=str)
    user_message = f"GAME STATE:\n```json\n{snapshot_json}\n```\n\n{question}"

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
        temperature=0.5,  # Lower temp for more deterministic behavior
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
        "unknown", "not in the data", "not included"
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
    print("TOOL USAGE STRESS TEST")
    print("Questions that REQUIRE tools to answer properly")
    print(f"Model: {MODEL}")
    print("=" * 80)

    save_path = find_save_file()
    print(f"Save: {save_path.name}")

    extractor = SaveExtractor(str(save_path))
    identity = extractor.get_empire_identity()
    situation = extractor.get_situation()

    # Use LIMITED snapshot (same as production)
    snapshot = build_snapshot(extractor)

    print(f"Empire: {identity.get('empire_name')}")
    print(f"\nSnapshot keys: {list(snapshot.keys())}")
    print("(Note: Snapshot intentionally limited - tools needed for details)")
    print()

    system_prompt = build_optimized_prompt(identity, situation)
    client = genai.Client()

    results = []

    print("=" * 80)
    print("RUNNING STRESS TESTS...")
    print("=" * 80)

    for qi, question in enumerate(STRESS_QUESTIONS, 1):
        print(f"\nQ{qi}: {question}")
        print("-" * 60)

        try:
            result = run_test(client, extractor, system_prompt, snapshot, question)

            status = "✅ USED TOOLS" if result['tool_count'] > 0 else (
                "⚠️ ADMITTED UNKNOWN" if result['admitted_unknown'] else "❌ MADE UP DATA?"
            )

            print(f"  {status}")
            print(f"  Time: {result['time']:.1f}s | Words: {result['words']} | Tools: {result['tool_count']}")
            if result['tools_used']:
                print(f"  Tool calls: {result['tools_used']}")

            results.append({
                'question': question,
                **result
            })

        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({
                'question': question,
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
    admitted_unknown = sum(1 for r in results if r['admitted_unknown'] and r['tool_count'] == 0)
    made_up = sum(1 for r in results if r['tool_count'] == 0 and not r['admitted_unknown'])

    print(f"✅ Used tools when needed: {used_tools}/{len(results)}")
    print(f"⚠️ Admitted unknown (acceptable): {admitted_unknown}/{len(results)}")
    print(f"❌ Possibly made up data: {made_up}/{len(results)}")

    # Write report
    report = f"""# Tool Usage Stress Test

**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}

**Model:** {MODEL}

**Purpose:** Test if the model correctly uses tools when data is NOT in the pre-injected snapshot.

---

## Summary

| Outcome | Count |
|---------|-------|
| ✅ Used tools | {used_tools}/{len(results)} |
| ⚠️ Admitted unknown | {admitted_unknown}/{len(results)} |
| ❌ Possibly hallucinated | {made_up}/{len(results)} |

---

## Individual Results

"""

    for r in results:
        status = "✅ USED TOOLS" if r['tool_count'] > 0 else (
            "⚠️ ADMITTED UNKNOWN" if r['admitted_unknown'] else "❌ CHECK FOR HALLUCINATION"
        )

        report += f"""### Q: {r['question']}

**Status:** {status}

**Time:** {r['time']:.1f}s | **Words:** {r['words']} | **Tool calls:** {r['tool_count']}

"""
        if r['tools_used']:
            report += f"**Tools:** {', '.join(r['tools_used'])}\n\n"

        report += f"**Response:**\n\n{r['response']}\n\n---\n\n"

    output_path = Path("TOOL_STRESS_TEST.md")
    output_path.write_text(report)
    print(f"\nFull report: {output_path}")


if __name__ == "__main__":
    main()
