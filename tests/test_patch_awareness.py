#!/usr/bin/env python3
"""
Stress test for patch notes awareness integration.

Tests that the LLM:
1. Gives CORRECT advice based on patch data
2. Does NOT over-reference patches/changes
3. Speaks naturally as if current mechanics are "how it's always been"

Usage:
    python tests/test_patch_awareness.py
    python tests/test_patch_awareness.py --verbose
    python tests/test_patch_awareness.py --test-name ecumenopolis
"""

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import Optional

import requests

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("ERROR: google-genai not installed. Run: pip install google-genai")
    sys.exit(1)


# =============================================================================
# Patch Notes Fetching
# =============================================================================

def fetch_steam_patch_notes(count: int = 10) -> list[dict]:
    """Fetch recent patch notes from Steam API."""
    url = f"https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid=281990&count={count}&maxlength=0"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("appnews", {}).get("newsitems", [])


def strip_bbcode(text: str) -> str:
    """Remove BBCode tags from text."""
    return re.sub(r'\[.*?\]', '', text)


def extract_balance_section(content: str) -> str:
    """Extract the Balance section from patch notes."""
    clean = strip_bbcode(content)

    # Try to find Balance section
    balance_match = re.search(
        r'Balance\s*(.*?)(?=Bugfix|Bug\s*fix|Performance|Stability|AI\b|UI\b|Modding|$)',
        clean,
        re.IGNORECASE | re.DOTALL
    )

    if balance_match:
        return balance_match.group(1).strip()

    return ""


def extract_features_section(content: str) -> str:
    """Extract the Features section from patch notes."""
    clean = strip_bbcode(content)

    features_match = re.search(
        r'Features?\s*(.*?)(?=Balance|Bugfix|Bug\s*fix|Improvements?|$)',
        clean,
        re.IGNORECASE | re.DOTALL
    )

    if features_match:
        return features_match.group(1).strip()

    return ""


def get_latest_patch_notes() -> tuple[str, str, str]:
    """Fetch and parse the latest patch notes.

    Returns:
        Tuple of (version, balance_section, features_section)
    """
    items = fetch_steam_patch_notes(20)

    for item in items:
        title = item.get("title", "")
        # Look for release notes
        if "release notes" in title.lower() or ("update" in title.lower() and "patch" in title.lower()):
            content = item.get("contents", "")

            # Extract version from title
            version_match = re.search(r'(\d+\.\d+(?:\.\d+)?)', title)
            version = version_match.group(1) if version_match else "unknown"

            balance = extract_balance_section(content)
            features = extract_features_section(content)

            if balance or features:
                return version, balance, features

    return "unknown", "", ""


# =============================================================================
# Test Framework
# =============================================================================

@dataclass
class TestCase:
    """A test case for patch awareness."""
    name: str
    question: str
    patch_relevant_info: str  # The specific patch info that's relevant
    expected_behavior: str  # What we expect the LLM to do
    bad_patterns: list[str]  # Patterns that indicate over-indexing
    good_patterns: list[str]  # Patterns that indicate correct behavior


# Test cases based on real 4.0/4.2 changes
# Note: patch_relevant_info uses change-language but will be normalized by normalize_patch_language()
TEST_CASES = [
    TestCase(
        name="ecumenopolis_pop_growth",
        question="I want to maximize pop growth. Should I rush an Ecumenopolis?",
        patch_relevant_info="Ecumenopolises do not provide bonuses to pop growth. Gaia Worlds provide +15% pop growth.",
        expected_behavior="Should recommend Gaia Worlds for pop growth, not mention that Ecumenopolis 'changed'",
        bad_patterns=[
            r"since (the )?(patch|update|4\.\d)",
            r"no longer (provide|give|grant|boost|has|have|offer|work|function|apply)",
            r"was changed",
            r"used to",
            r"patch notes",
            r"recently changed",
            r"as of (version|patch|update)",
        ],
        good_patterns=[
            r"gaia",
            r"pop(ulation)? growth",
        ]
    ),
    TestCase(
        name="clone_army_balance",
        question="I'm playing Clone Army origin. Any tips for managing my economy?",
        patch_relevant_info="Clone Army: The Clone Soldier trait adds a 25% increase to food and mineral pop upkeep. Clone vats max pop assembly is 20.",
        expected_behavior="Should mention the upkeep costs as fact, not as a recent change",
        bad_patterns=[
            r"since (the )?(patch|update|nerf)",
            r"was (recently )?increased",
            r"used to be",
            r"patch \d+\.\d+",
            r"they nerfed",
        ],
        good_patterns=[
            r"upkeep",
            r"food|mineral",
            r"clone",
        ]
    ),
    TestCase(
        name="subterranean_origin",
        question="Is Subterranean origin good for wide play?",
        patch_relevant_info="Subterranean: The Pop growth/assembly penalty from the cave-dweller trait is 10%. All planets get +2 max districts.",
        expected_behavior="Should mention the 10% penalty and +2 districts as facts",
        bad_patterns=[
            r"was reduced",
            r"used to be 20%",
            r"buffed",
            r"since (the )?(patch|update)",
            r"recent(ly)? changed",
        ],
        good_patterns=[
            r"10%",
            r"district",
            r"cave.?dweller",
        ]
    ),
    TestCase(
        name="overtuned_traits",
        question="Should I take Overtuned traits for my species?",
        patch_relevant_info="Overtuned traits slightly reduce pop growth, between 1.5% to 5% depending on trait potency.",
        expected_behavior="Should mention the pop growth reduction as an inherent tradeoff",
        bad_patterns=[
            r"now (also )?reduce",
            r"added a",
            r"since (the )?(patch|update)",
            r"new downside",
            r"they changed",
        ],
        good_patterns=[
            r"pop(ulation)? growth",
            r"trade.?off|downside|cost",
            r"overtuned",
        ]
    ),
    TestCase(
        name="general_strategy_no_patch",
        question="What's the best way to expand early game?",
        patch_relevant_info="",  # No specific patch info - general question
        expected_behavior="Should give general advice without any patch references",
        bad_patterns=[
            r"\bpatch\b",
            r"update",
            r"version",
            r"changed",
            r"used to",
        ],
        good_patterns=[
            r"expand|colony|colonize",
            r"starbase|outpost",
        ]
    ),
    # Edge case: Direct question about mechanic that changed
    TestCase(
        name="direct_mechanic_question",
        question="Does building an Ecumenopolis help with pop growth?",
        patch_relevant_info="Ecumenopolises do not provide bonuses to pop growth. Gaia Worlds provide +15% pop growth.",
        expected_behavior="Should say no without referencing that it 'changed'",
        bad_patterns=[
            r"no longer (provide|give|grant|boost|has|have|offer|work|function|apply)",
            r"used to",
            r"was changed",
            r"\bpatch\b",
            r"anymore",
            r"not anymore",
        ],
        good_patterns=[
            r"(not|don't|doesn't).*pop(ulation)? growth",
            r"gaia",
        ]
    ),
    # Edge case: Asking about specific numbers
    TestCase(
        name="specific_numbers",
        question="What's the pop growth bonus on Gaia Worlds?",
        patch_relevant_info="Gaia Worlds provide +15% pop growth.",
        expected_behavior="Should state 15% as fact",
        bad_patterns=[
            r"currently (in|as of|since)",  # "Currently" alone is fine
            r"as of (version|patch|\d)",
            r"now (is|provides|gives)",
        ],
        good_patterns=[
            r"15%",
            r"pop(ulation)? growth",
        ]
    ),
    # Edge case: Comparative question
    TestCase(
        name="comparative_question",
        question="Which is better for tall play: Ecumenopolis or Ring World?",
        patch_relevant_info="Ecumenopolises do not provide bonuses to pop growth but excel at production density.",
        expected_behavior="Should compare without referencing changes",
        bad_patterns=[
            r"no longer (provide|give|grant|boost|has|have|offer|work|function|apply)",
            r"used to",
            r"changed",
            r"\bpatch\b",
            r"since (the )?(patch|update|version)",
        ],
        good_patterns=[
            r"ecumenopolis|ring.?world",
            r"production|research|unity",
        ]
    ),
    # ==========================================================================
    # OVER-INJECTION TESTS
    # These test that patch info doesn't leak into unrelated questions
    # ==========================================================================
    TestCase(
        name="unrelated_fleet_question",
        question="What's a good fleet composition for fighting the Prethoryn Scourge?",
        patch_relevant_info="Ecumenopolises do not provide bonuses to pop growth. Gaia Worlds provide +15% pop growth. Clone Army upkeep is 25% higher.",
        expected_behavior="Should NOT mention pop growth, Ecumenopolises, Clone Army, or any patch-related info",
        bad_patterns=[
            r"ecumenopolis",
            r"pop(ulation)? growth",
            r"gaia",
            r"clone army",
            r"upkeep",
            r"\bpatch\b",
            r"balance change",  # More specific - "balanced fleet" is fine
        ],
        good_patterns=[
            r"prethoryn|scourge",
            r"fleet|ship|corvette|battleship|cruiser",
            r"armor|hull|strike craft",
        ]
    ),
    TestCase(
        name="unrelated_diplomacy_question",
        question="How do I improve relations with a neighboring empire?",
        patch_relevant_info="Ecumenopolises do not provide bonuses to pop growth. Gaia Worlds provide +15% pop growth.",
        expected_behavior="Should focus on diplomacy, not mention economy/pop mechanics",
        bad_patterns=[
            r"ecumenopolis",
            r"pop(ulation)? growth",
            r"gaia",
            r"\bpatch\b",  # Word boundary to avoid "dispatch"
        ],
        good_patterns=[
            r"envoy|embassy|relation",
            r"treaty|agreement|pact",
            r"opinion|trust",
        ]
    ),
    TestCase(
        name="unrelated_early_game",
        question="What should I prioritize in the first 20 years?",
        patch_relevant_info="Ecumenopolises do not provide bonuses to pop growth. Clone Army upkeep is 25% higher. Overtuned traits reduce pop growth.",
        expected_behavior="Should give general early game advice without forcing in late-game Ecumenopolis info",
        bad_patterns=[
            r"ecumenopolis",  # Too early to mention
            r"clone army",   # Origin-specific
            r"overtuned",    # Trait-specific
            r"\bpatch\b",
        ],
        good_patterns=[
            r"explor|survey|science|discover",
            r"expand|colony|colonize|system|border",
            r"research|tech|unity|tradition",
            r"diplo|neighbor|contact",
        ]
    ),
    TestCase(
        name="lore_question",
        question="Tell me about the Prethoryn Scourge lore. Where do they come from?",
        patch_relevant_info="Ecumenopolises do not provide bonuses to pop growth. Gaia Worlds provide +15% pop growth.",
        expected_behavior="Should discuss lore only, no mechanical patch info",
        bad_patterns=[
            r"ecumenopolis",
            r"pop(ulation)? growth",
            r"gaia",
            r"balance",
            r"mechanic",
        ],
        good_patterns=[
            r"prethoryn|scourge",
            r"galaxy|dimension|flee|hunt|consume",
        ]
    ),
    # ==========================================================================
    # PROPORTIONALITY TESTS
    # Ensure patch info doesn't dominate responses
    # ==========================================================================
    TestCase(
        name="broad_strategy_question",
        question="Give me a general strategy overview for a xenophile empire.",
        patch_relevant_info="Ecumenopolises do not provide bonuses to pop growth. Gaia Worlds provide +15% pop growth. Migration treaties are very powerful.",
        expected_behavior="Should cover diplomacy, economy, military - not ONLY mention Gaia/migration",
        bad_patterns=[
            r"\bpatch\b",
            r"was changed",
            r"no longer (provide|give|grant|boost|has|have|offer|work|function|apply)",  # Specific to mechanics, not narrative
        ],
        good_patterns=[
            r"diplomacy|federation|ally",
            r"xenophile",
            r"migration|treaty|agreement",
        ]
    ),
    # ==========================================================================
    # AMALGAMATED PATCHES TEST
    # Simulates multiple patches combined
    # ==========================================================================
    TestCase(
        name="amalgamated_patches",
        question="What's the current meta for pop growth in the late game?",
        patch_relevant_info="""- Ecumenopolises do not provide pop growth bonuses
- Gaia Worlds provide +15% pop growth
- Gene Clinics provide +2 pop growth
- Cloning Vats max assembly is 20
- Roboticists provide +2 pop assembly
- Overtuned traits slightly reduce pop growth (1.5-5%)
- Pre-Planned Growth adds +15% pop upkeep instead of growth penalty""",
        expected_behavior="Should synthesize multiple mechanics into coherent advice without listing patch notes",
        bad_patterns=[
            r"\bpatch\b",
            r"was changed",
            r"no longer (provide|give|grant|boost|has|have|offer|work|function|apply)",  # Specific to mechanics
            r"used to (provide|give|grant|boost|be)",
            r"as of (version|patch)",
            r"in the current (patch|version|update)",
        ],
        good_patterns=[
            r"gaia|gene clinic|robot",
            r"pop(ulation)? (growth|assembly)",
        ]
    ),
]


def amalgamate_patches(patches: list[dict]) -> str:
    """Combine multiple patch notes into a single, deduplicated context.

    Strategy:
    - Only keep the LATEST state of each mechanic
    - Remove bug fixes and UI changes
    - Prioritize balance and feature changes
    - Keep under ~1000 tokens

    Args:
        patches: List of dicts with 'version', 'balance', 'features' keys

    Returns:
        Amalgamated patch context string
    """
    # Track mechanics we've seen (to dedupe)
    seen_mechanics = set()
    lines = []

    # Process patches in reverse order (newest first)
    for patch in sorted(patches, key=lambda p: p.get('version', ''), reverse=True):
        version = patch.get('version', 'unknown')
        balance = patch.get('balance', '')
        features = patch.get('features', '')

        # Extract individual balance changes
        for line in balance.split('\n'):
            line = line.strip()
            if not line or len(line) < 10:
                continue

            # Skip bug fixes
            if any(skip in line.lower() for skip in ['fixed', 'fix ', 'bug', 'crash', 'tooltip', 'ui ']):
                continue

            # Extract mechanic identifier (first few words)
            words = line.split()[:3]
            mechanic_key = ' '.join(words).lower()

            # Only keep first occurrence (newest)
            if mechanic_key not in seen_mechanics:
                seen_mechanics.add(mechanic_key)
                lines.append(f"- {line}")

    # Limit total size
    result = '\n'.join(lines[:30])  # Max 30 lines

    # Normalize language
    result = normalize_patch_language(result)

    return result


def normalize_patch_language(text: str) -> str:
    """Convert change-oriented language to present-tense facts.

    Transforms:
        "X no longer does Y" -> "X does not do Y"
        "X now does Y" -> "X does Y"
        "reduced from 20 to 10" -> "is 10"
        "increased from X to Y" -> "is Y"
    """
    import re

    # "no longer provides" -> "does not provide"
    text = re.sub(r'\bno longer\b', 'does not', text, flags=re.IGNORECASE)

    # "now provides" -> "provides"
    text = re.sub(r'\bnow\s+', '', text, flags=re.IGNORECASE)

    # "reduced from X to Y" -> "is Y"
    text = re.sub(r'reduced from \S+ to (\S+)', r'is \1', text, flags=re.IGNORECASE)

    # "increased from X to Y" -> "is Y"
    text = re.sub(r'increased from \S+ to (\S+)', r'is \1', text, flags=re.IGNORECASE)

    # "was changed to" -> "is"
    text = re.sub(r'was changed to', 'is', text, flags=re.IGNORECASE)

    # "has been reduced/increased to" -> "is"
    text = re.sub(r'has been (?:reduced|increased) to', 'is', text, flags=re.IGNORECASE)

    return text


def build_test_system_prompt(patch_corrections: str, version: str = "4.2") -> str:
    """Build the system prompt with patch awareness."""

    base_prompt = """You are the strategic advisor to the United Nations of Earth.

EMPIRE: Ethics: fanatic_egalitarian, xenophile | Authority: democratic | Civics: beacon_of_liberty, idealistic_foundation
STATE: Year 2250 (mid_early), peace, 0 deficits, 5 contacts

Address the ruler as "President".

You know Stellaris deeply. Use that knowledge to:
1. Embody your empire's ethics and civics authentically
2. Be a strategic ADVISOR, not a reporter - interpret facts, identify problems, suggest solutions
3. Be colorful and immersive - this is roleplay, not a spreadsheet

Facts must come from provided game state. Never guess numbers."""

    # Normalize patch language to remove change-oriented phrasing
    if patch_corrections:
        patch_corrections = normalize_patch_language(patch_corrections)

    game_context = f"""

[INTERNAL CONTEXT - never mention this to the user]
Game version: {version}
Active DLCs: Utopia, Federations, Megacorp, Overlord

VERSION & DLC AWARENESS:
- Only recommend features, mechanics, and content available with the active DLCs
- Consider how game mechanics and balance work in this specific version
- Never explicitly mention version numbers or DLC status to the user

[VERSION-SPECIFIC MECHANICS - state as facts, not changes]
The following describes how mechanics work in this version.
Present these as FACTS about the game, not as changes or updates.

FORBIDDEN PHRASES (never use these):
- "no longer", "used to", "was changed", "since patch", "recently"
- "now provides" (just say "provides")
- "was nerfed/buffed", "they changed", "in the current version"

CORRECT APPROACH:
- BAD: "Ecumenopolises no longer provide pop growth bonuses"
- GOOD: "Ecumenopolises excel at production density but don't boost pop growth"

- BAD: "Gaia Worlds now provide +15% pop growth"
- GOOD: "Gaia Worlds provide +15% pop growth"

Mechanics for this version:
{patch_corrections if patch_corrections else "Standard mechanics apply."}
"""

    return base_prompt + game_context


def run_test(
    client: genai.Client,
    test: TestCase,
    patch_notes: str,
    verbose: bool = False
) -> dict:
    """Run a single test case."""

    # Build prompt with relevant patch info
    system_prompt = build_test_system_prompt(
        patch_corrections=test.patch_relevant_info,
        version="4.2"
    )

    if verbose:
        print(f"\n{'='*60}")
        print(f"TEST: {test.name}")
        print(f"{'='*60}")
        print(f"Question: {test.question}")
        print(f"Patch info: {test.patch_relevant_info[:100]}...")

    start = time.time()

    try:
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=test.question,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.7,  # Slightly lower for more consistent testing
                max_output_tokens=1024,
            )
        )
        response_text = response.text or ""
        elapsed = time.time() - start

    except Exception as e:
        return {
            "name": test.name,
            "passed": False,
            "error": str(e),
            "response": "",
            "elapsed": 0,
            "bad_matches": [],
            "good_matches": [],
        }

    if verbose:
        print(f"\nResponse ({elapsed:.1f}s):")
        print("-" * 40)
        print(response_text)
        print("-" * 40)

    # Check for bad patterns (over-indexing) - these are HARD FAILURES
    bad_matches = []
    for pattern in test.bad_patterns:
        matches = re.findall(pattern, response_text, re.IGNORECASE)
        if matches:
            bad_matches.append((pattern, matches))

    # Check for good patterns (correct behavior) - these are SOFT (informational)
    good_matches = []
    for pattern in test.good_patterns:
        matches = re.findall(pattern, response_text, re.IGNORECASE)
        if matches:
            good_matches.append((pattern, matches))

    # PASS if no bad patterns, regardless of good patterns
    # (LLM responses vary, good patterns are hints not requirements)
    passed = len(bad_matches) == 0

    if verbose:
        print(f"\nResults:")
        print(f"  Bad patterns found: {len(bad_matches)}")
        for pattern, matches in bad_matches:
            print(f"    ❌ '{pattern}' -> {matches}")
        print(f"  Good patterns found: {len(good_matches)}")
        for pattern, matches in good_matches:
            print(f"    ✓ '{pattern}' -> {matches[:3]}")
        print(f"  PASSED: {passed}")

    return {
        "name": test.name,
        "passed": passed,
        "response": response_text,
        "elapsed": elapsed,
        "bad_matches": bad_matches,
        "good_matches": good_matches,
    }


def run_comparison_test(
    client: genai.Client,
    test: TestCase,
    verbose: bool = False
) -> dict:
    """Run a test with and without patch context to compare behavior."""

    # Without patch context
    system_prompt_no_patch = build_test_system_prompt(patch_corrections="", version="4.2")

    # With patch context
    system_prompt_with_patch = build_test_system_prompt(
        patch_corrections=test.patch_relevant_info,
        version="4.2"
    )

    if verbose:
        print(f"\n{'='*60}")
        print(f"COMPARISON TEST: {test.name}")
        print(f"{'='*60}")
        print(f"Question: {test.question}")

    results = {}

    for label, prompt in [("without_patch", system_prompt_no_patch), ("with_patch", system_prompt_with_patch)]:
        try:
            response = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=test.question,
                config=types.GenerateContentConfig(
                    system_instruction=prompt,
                    temperature=0.7,
                    max_output_tokens=1024,
                )
            )
            results[label] = response.text or ""
        except Exception as e:
            results[label] = f"ERROR: {e}"

    if verbose:
        print(f"\n--- WITHOUT patch context ---")
        print(results["without_patch"][:500])
        print(f"\n--- WITH patch context ---")
        print(results["with_patch"][:500])

    return results


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Test patch notes awareness")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show full responses")
    parser.add_argument("--test-name", "-t", type=str, help="Run specific test by name")
    parser.add_argument("--compare", "-c", action="store_true", help="Run comparison tests (with/without patch)")
    parser.add_argument("--fetch-only", action="store_true", help="Only fetch and show patch notes")
    parser.add_argument("--runs", "-n", type=int, default=1, help="Number of runs per test")
    args = parser.parse_args()

    print("=" * 60)
    print("PATCH AWARENESS STRESS TEST")
    print("=" * 60)

    # Fetch real patch notes
    print("\nFetching latest patch notes from Steam API...")
    version, balance, features = get_latest_patch_notes()
    print(f"Found version: {version}")
    print(f"Balance section: {len(balance)} chars")
    print(f"Features section: {len(features)} chars")

    if args.fetch_only:
        print("\n--- BALANCE SECTION ---")
        print(balance[:2000] if balance else "(empty)")
        print("\n--- FEATURES SECTION ---")
        print(features[:2000] if features else "(empty)")
        return

    # Check API key
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("\nERROR: GOOGLE_API_KEY not set")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    # Filter tests if specific one requested
    tests = TEST_CASES
    if args.test_name:
        tests = [t for t in TEST_CASES if args.test_name.lower() in t.name.lower()]
        if not tests:
            print(f"No test matching '{args.test_name}'")
            sys.exit(1)

    if args.compare:
        # Run comparison tests
        print(f"\nRunning {len(tests)} comparison tests...")
        for test in tests:
            run_comparison_test(client, test, verbose=True)
    else:
        # Run standard tests
        print(f"\nRunning {len(tests)} tests x {args.runs} runs...")

        all_results = []
        for run in range(args.runs):
            if args.runs > 1:
                print(f"\n--- Run {run + 1}/{args.runs} ---")

            for test in tests:
                result = run_test(client, test, balance, verbose=args.verbose)
                all_results.append(result)

                status = "✓ PASS" if result["passed"] else "✗ FAIL"
                print(f"  {status}: {result['name']} ({result.get('elapsed', 0):.1f}s)")

                if not result["passed"] and not args.verbose:
                    # Show why it failed
                    for pattern, matches in result.get("bad_matches", []):
                        print(f"       Bad pattern '{pattern}': {matches[:2]}")

        # Summary
        passed = sum(1 for r in all_results if r["passed"])
        total = len(all_results)
        print(f"\n{'='*60}")
        print(f"SUMMARY: {passed}/{total} passed ({100*passed/total:.0f}%)")
        print("=" * 60)

        if passed < total:
            print("\nFailed tests need prompt tuning to avoid over-indexing on patch info.")


if __name__ == "__main__":
    main()
