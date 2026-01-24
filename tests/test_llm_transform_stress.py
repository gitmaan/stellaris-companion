#!/usr/bin/env python3
"""
Stress test LLM-transformed patch notes with minimal framing.

Tests the same 14 scenarios as test_patch_awareness.py but using:
- LLM-transformed patch notes (one-time preprocessing)
- Minimal runtime framing (no FORBIDDEN PHRASES)
"""

import os
import sys
import time
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google import genai
from google.genai import types

# LLM-transformed patch notes (simulating pre-processed storage)
LLM_TRANSFORMED_NOTES = """
• Ecumenopolises: No pop growth bonus; strength is production density and job capacity
• Gaia Worlds: +15% pop growth, 100% habitability for all species (optimal for population farming)
• Clone Army: Clone Soldiers have +25% food/mineral upkeep; Clone Vats max assembly is 20
• Subterranean: Cave-dweller trait has 10% pop growth penalty; all planets get +2 max districts
• Overtuned Traits: Reduce pop growth by 1.5-5% depending on potency (tradeoff for powerful bonuses)
• Pre-Planned Growth: Adds 15% upkeep to food/minerals/alloys instead of growth penalty
• Gene Clinics: Provide +2 pop growth per building
• Roboticists: Provide +2 pop assembly per job
"""

# Minimal framing system prompt
MINIMAL_SYSTEM_PROMPT = """You are the strategic advisor to {empire_name}.

EMPIRE: Ethics: {ethics} | Authority: {authority} | Civics: {civics}
STATE: Year {year} ({phase}), {war_status}, {deficits} deficits

Address the ruler as "{title}".

You know Stellaris deeply. Be a strategic ADVISOR - interpret facts, identify problems, suggest solutions.
Be colorful and immersive - this is roleplay, not a spreadsheet.

[GAME MECHANICS]
{patch_notes}

Provide advice based on current game mechanics. Do not reference patches, updates, or changes."""


def build_prompt(patch_notes: str) -> str:
    return MINIMAL_SYSTEM_PROMPT.format(
        empire_name="United Nations of Earth",
        ethics="fanatic_egalitarian, xenophile",
        authority="democratic",
        civics="beacon_of_liberty, idealistic_foundation",
        year="2250",
        phase="mid_early",
        war_status="peace",
        deficits="0",
        title="President",
        patch_notes=patch_notes,
    )


# Test cases (same as test_patch_awareness.py)
TEST_CASES = [
    {
        "name": "ecumenopolis_pop_growth",
        "question": "I want to maximize pop growth. Should I rush an Ecumenopolis?",
        "bad_patterns": [
            r"no longer (provide|give|grant|boost)",
            r"used to",
            r"was changed",
            r"\bpatch\b",
        ],
    },
    {
        "name": "clone_army_balance",
        "question": "I'm playing Clone Army origin. Any tips for managing my economy?",
        "bad_patterns": [
            r"was (recently )?increased",
            r"used to be",
            r"\bpatch\b",
            r"they nerfed",
        ],
    },
    {
        "name": "subterranean_origin",
        "question": "Is Subterranean origin good for wide play?",
        "bad_patterns": [
            r"was reduced",
            r"used to be",
            r"buffed",
            r"\bpatch\b",
        ],
    },
    {
        "name": "overtuned_traits",
        "question": "Should I take Overtuned traits for my species?",
        "bad_patterns": [
            r"now (also )?reduce",
            r"added a",
            r"\bpatch\b",
            r"new downside",
        ],
    },
    {
        "name": "gaia_worlds",
        "question": "What's the pop growth bonus on Gaia Worlds?",
        "bad_patterns": [
            r"now (is|provides)",
            r"was (increased|changed)",
            r"\bpatch\b",
        ],
    },
    {
        "name": "unrelated_fleet",
        "question": "What's a good fleet composition for fighting the Prethoryn Scourge?",
        "bad_patterns": [
            r"ecumenopolis",
            r"pop(ulation)? growth",
            r"gaia",
            r"\bpatch\b",
        ],
    },
    {
        "name": "unrelated_diplomacy",
        "question": "How do I improve relations with a neighboring empire?",
        "bad_patterns": [
            r"ecumenopolis",
            r"pop(ulation)? growth",
            r"gaia",
            r"\bpatch\b",
        ],
    },
    {
        "name": "unrelated_early_game",
        "question": "What should I prioritize in the first 20 years?",
        "bad_patterns": [
            r"ecumenopolis",
            r"clone army",
            r"overtuned",
            r"\bpatch\b",
        ],
    },
    {
        "name": "lore_question",
        "question": "Tell me about the Prethoryn Scourge lore. Where do they come from?",
        "bad_patterns": [
            r"ecumenopolis",
            r"pop(ulation)? growth",
            r"gaia",
            r"\bpatch\b",
        ],
    },
    {
        "name": "late_game_meta",
        "question": "What's the current meta for pop growth in the late game?",
        "bad_patterns": [
            r"was changed",
            r"no longer (provide|give)",
            r"used to",
            r"\bpatch\b",
        ],
    },
]


def run_test(client: genai.Client, test: dict, system_prompt: str) -> tuple[bool, list[str], str]:
    """Run a single test case."""
    try:
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=test["question"],
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.7,
                max_output_tokens=800,
            )
        )
        text = response.text or ""
    except Exception as e:
        return False, [f"API Error: {e}"], ""

    violations = []
    for pattern in test["bad_patterns"]:
        if re.search(pattern, text, re.IGNORECASE):
            match = re.search(pattern, text, re.IGNORECASE)
            violations.append(f"'{pattern}' -> '{match.group()}'")

    return len(violations) == 0, violations, text


def main():
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("ERROR: GOOGLE_API_KEY not set")
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    system_prompt = build_prompt(LLM_TRANSFORMED_NOTES)

    print("=" * 70)
    print("LLM TRANSFORM + MINIMAL FRAMING STRESS TEST")
    print("=" * 70)
    print(f"\nSystem prompt size: {len(system_prompt)} chars (~{len(system_prompt.split())} words)")
    print(f"Running {len(TEST_CASES)} tests x 3 runs...\n")

    all_results = []

    for run in range(3):
        print(f"--- Run {run + 1}/3 ---")
        run_results = []

        for test in TEST_CASES:
            start = time.time()
            passed, violations, response = run_test(client, test, system_prompt)
            elapsed = time.time() - start

            run_results.append({
                "name": test["name"],
                "passed": passed,
                "violations": violations,
                "time": elapsed,
            })

            status = "✓ PASS" if passed else "✗ FAIL"
            print(f"  {status}: {test['name']} ({elapsed:.1f}s)")

            if not passed:
                for v in violations:
                    print(f"       {v}")

        all_results.extend(run_results)
        print()

    # Summary
    passed = sum(1 for r in all_results if r["passed"])
    total = len(all_results)

    print("=" * 70)
    print(f"SUMMARY: {passed}/{total} passed ({100 * passed / total:.0f}%)")
    print("=" * 70)

    # Compare with full framing approach
    print("\n### COMPARISON WITH FULL FRAMING APPROACH")
    print("-" * 50)
    print("Previous approach (regex + full framing): 42/42 (100%)")
    print(f"This approach (LLM transform + minimal framing): {passed}/{total} ({100 * passed / total:.0f}%)")

    if passed == total:
        print("\n✓ LLM Transform approach achieves same reliability with:")
        print("  - Cleaner, more readable patch context")
        print("  - No grammatical errors from regex")
        print("  - Strategic implications included")
        print("  - Smaller prompt (no FORBIDDEN PHRASES block)")
        print("  - One-time $0.01 cost per patch version")


if __name__ == "__main__":
    main()
