#!/usr/bin/env python3
"""
Test LLM pre-processing of patch notes.

Compares:
1. Raw patch notes (what we get from Steam)
2. Regex-normalized (current approach)
3. LLM-transformed (proposed approach)

Then tests each with the advisor to see which produces better responses.
"""

import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google import genai
from google.genai import types

# Sample raw patch notes (actual content from 4.0/4.2)
RAW_PATCH_NOTES = """
Ecumenopolises no longer provide bonuses to pop growth.
Gaia Worlds now provide +15% pop growth.
Clone Army: The Clone Soldier trait now adds a 25% increase to food and mineral pop upkeep. Clone vats max pop assembly has been reduced from 25 to 20.
Subterranean: Reduced the Pop growth/assembly penalty from the cave-dweller trait from 20 to 10%. All planets now get +2 max districts.
Overtuned traits now also slightly reduce pop growth, between 1.5% to 5% depending on trait potency.
Pre-Planned growth instead adds a 15% pop food/mineral/alloys upkeep.
The Summon Dimensional Fleet Astral Action now summons Astral Cruisers and Astral Escorts equal to twice the number of Rifts you have explored.
Augmentation Bazaars can now select cybernetic traits in empire creation.
Knights of the Toxic God: Reduced quest progress from Knight Jobs. Luminous Blades no longer negates alloy upkeep for knights.
Life-Seeded: Planet has improved rare resource features.
Synthetic Fertility: The Identity repository output has been decreased by 25%, while its upkeep has been increased by 20%.
"""


# Regex normalization (current approach)
def regex_normalize(text: str) -> str:
    """Current regex-based normalization."""
    text = re.sub(r"\bno longer\b", "does not", text, flags=re.IGNORECASE)
    text = re.sub(r"\bnow\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"reduced from \S+ to (\S+)", r"is \1", text, flags=re.IGNORECASE)
    text = re.sub(r"increased from \S+ to (\S+)", r"is \1", text, flags=re.IGNORECASE)
    text = re.sub(r"has been reduced from \S+ to (\S+)", r"is \1", text, flags=re.IGNORECASE)
    text = re.sub(r"has been increased from \S+ to (\S+)", r"is \1", text, flags=re.IGNORECASE)
    text = re.sub(r"was changed to", "is", text, flags=re.IGNORECASE)
    text = re.sub(r"has been (?:reduced|increased) to", "is", text, flags=re.IGNORECASE)
    text = re.sub(
        r"has been (?:decreased|increased) by", "is adjusted by", text, flags=re.IGNORECASE
    )
    return text


# LLM transformation prompt
LLM_TRANSFORM_PROMPT = """Convert these Stellaris patch notes into present-tense FACTS about game mechanics.

RULES:
1. Remove ALL change-oriented language:
   - "no longer" → state what it DOESN'T do
   - "now provides" → just state what it provides
   - "reduced from X to Y" → just state the current value Y
   - "increased/decreased by" → state the current state

2. Write as if these mechanics have ALWAYS been this way

3. Keep specific numbers (percentages, values)

4. Add brief strategic implication where helpful (in parentheses)

5. Format as clean bullet points

6. Skip bug fixes, UI changes, tooltip fixes

EXAMPLE INPUT:
"Ecumenopolises no longer provide pop growth bonuses. Gaia Worlds now provide +15% pop growth (was 10%)."

EXAMPLE OUTPUT:
• Ecumenopolises: No pop growth bonus (focus is production density, not growth)
• Gaia Worlds: +15% pop growth, 100% habitability (best for population farming)

NOW TRANSFORM THESE PATCH NOTES:

"""


def llm_transform(text: str, client: genai.Client) -> str:
    """Transform patch notes using LLM."""
    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=LLM_TRANSFORM_PROMPT + text,
        config=types.GenerateContentConfig(
            temperature=0.3,  # Low temp for consistent output
            max_output_tokens=1500,
        ),
    )
    return response.text


def test_advisor_response(
    patch_context: str, question: str, client: genai.Client, use_minimal_framing: bool = False
) -> tuple[str, list[str]]:
    """Test advisor response with given patch context.

    Returns:
        Tuple of (response_text, list_of_violations)
    """

    if use_minimal_framing:
        # Minimal framing - just inject facts
        system_prompt = f"""You are the strategic advisor to the United Nations of Earth.
EMPIRE: Ethics: fanatic_egalitarian, xenophile | Authority: democratic
Address the ruler as "President". Be a strategic ADVISOR, stay in character.

[GAME MECHANICS - for accurate advice]
{patch_context}

Give advice based on these mechanics. Never reference patches or changes."""
    else:
        # Full framing (current approach)
        system_prompt = f"""You are the strategic advisor to the United Nations of Earth.
EMPIRE: Ethics: fanatic_egalitarian, xenophile | Authority: democratic
Address the ruler as "President". Be a strategic ADVISOR, stay in character.

[VERSION-SPECIFIC MECHANICS - state as facts, not changes]
FORBIDDEN PHRASES (never use these):
- "no longer", "used to", "was changed", "since patch", "recently"
- "now provides" (just say "provides")
- "was nerfed/buffed", "they changed"

CORRECT APPROACH:
- BAD: "Ecumenopolises no longer provide pop growth bonuses"
- GOOD: "Ecumenopolises excel at production density but don't boost pop growth"

Mechanics:
{patch_context}"""

    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=question,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.7,
            max_output_tokens=800,
        ),
    )

    text = response.text or ""

    # Check for violations
    violations = []
    bad_patterns = [
        (
            r"no longer (provide|give|grant|boost|has|have|offer|work|function|apply)",
            "no longer [verb]",
        ),
        (r"used to (provide|give|be)", "used to [verb]"),
        (r"was changed", "was changed"),
        (r"since (the )?(patch|update)", "since patch"),
        (r"\bpatch\b", "patch"),
        (r"they (nerfed|buffed)", "nerfed/buffed"),
    ]

    for pattern, name in bad_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            violations.append(name)

    return text, violations


def main():
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("ERROR: GOOGLE_API_KEY not set")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    print("=" * 70)
    print("LLM PATCH NOTES TRANSFORMATION TEST")
    print("=" * 70)

    # Step 1: Show raw patch notes
    print("\n### RAW PATCH NOTES (from Steam API)")
    print("-" * 50)
    print(RAW_PATCH_NOTES.strip())

    # Step 2: Show regex-normalized
    print("\n### REGEX NORMALIZED (current approach)")
    print("-" * 50)
    regex_result = regex_normalize(RAW_PATCH_NOTES)
    print(regex_result.strip())

    # Step 3: LLM transform
    print("\n### LLM TRANSFORMED (proposed approach)")
    print("-" * 50)
    start = time.time()
    llm_result = llm_transform(RAW_PATCH_NOTES, client)
    llm_time = time.time() - start
    print(llm_result.strip())
    print(f"\n(Transform took {llm_time:.1f}s)")

    # Step 4: Compare token counts
    print("\n### CONTEXT SIZE COMPARISON")
    print("-" * 50)
    print(f"Raw patch notes:     {len(RAW_PATCH_NOTES.split())} words")
    print(f"Regex normalized:    {len(regex_result.split())} words")
    print(f"LLM transformed:     {len(llm_result.split())} words")

    # Step 5: Test both approaches with advisor
    print("\n### ADVISOR RESPONSE COMPARISON")
    print("-" * 50)

    test_questions = [
        "Should I rush an Ecumenopolis for pop growth?",
        "What's the best way to maximize pop growth late game?",
        "I'm playing Clone Army. How should I manage my economy?",
    ]

    results = {
        "regex_full_framing": {"violations": 0, "tests": 0},
        "llm_minimal_framing": {"violations": 0, "tests": 0},
    }

    for question in test_questions:
        print(f"\nQ: {question}")
        print()

        # Test regex + full framing
        print("--- Regex + Full Framing ---")
        resp1, violations1 = test_advisor_response(
            regex_result, question, client, use_minimal_framing=False
        )
        results["regex_full_framing"]["tests"] += 1
        if violations1:
            results["regex_full_framing"]["violations"] += 1
            print(f"⚠️  VIOLATIONS: {violations1}")
        else:
            print("✓ No violations")
        print(f"Response preview: {resp1[:200]}...")

        print()

        # Test LLM + minimal framing
        print("--- LLM Transform + Minimal Framing ---")
        resp2, violations2 = test_advisor_response(
            llm_result, question, client, use_minimal_framing=True
        )
        results["llm_minimal_framing"]["tests"] += 1
        if violations2:
            results["llm_minimal_framing"]["violations"] += 1
            print(f"⚠️  VIOLATIONS: {violations2}")
        else:
            print("✓ No violations")
        print(f"Response preview: {resp2[:200]}...")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    for approach, data in results.items():
        pass_rate = (data["tests"] - data["violations"]) / data["tests"] * 100
        print(
            f"{approach}: {data['tests'] - data['violations']}/{data['tests']} passed ({pass_rate:.0f}%)"
        )

    print("\n### RECOMMENDATION")
    print("-" * 50)

    llm_violations = results["llm_minimal_framing"]["violations"]
    regex_violations = results["regex_full_framing"]["violations"]

    if llm_violations <= regex_violations:
        print("✓ LLM Transform approach works well!")
        print("  - Cleaner context (facts not change-language)")
        print("  - Minimal runtime framing needed")
        print("  - One-time cost per patch (~$0.01)")
        print("  - Strategic implications included")
    else:
        print("⚠️  LLM Transform needs tuning - regex approach currently better")


if __name__ == "__main__":
    main()
