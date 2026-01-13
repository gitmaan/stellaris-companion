#!/usr/bin/env python3
"""
Test: Minimal + Strategic Depth Prompt
======================================

Hypothesis: The model already knows Stellaris. It just needs:
1. Basic identity info
2. The "STRATEGIC DEPTH" nudge to be an advisor, not a reporter

This tests the smallest possible prompt that still produces advisory-quality responses.
"""

import json
import re
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

import sys
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from google import genai
from google.genai import types
from save_extractor import SaveExtractor

MODEL = "gemini-3-flash-preview"

TEST_QUESTIONS = [
    "What is my current military power?",
    "Who are my allies?",
    "What is the state of my economy?",
    "Who is my best military commander?",
    "Give me a strategic assessment.",
]

# Empire name resolution
EMPIRE_LOC_KEYS = {
    'EMPIRE_DESIGN_orbis': 'United Nations of Earth',
    'EMPIRE_DESIGN_humans1': 'Commonwealth of Man',
    'PRESCRIPTED_empire_name_orbis': 'United Nations of Earth',
}


def get_empire_name_by_id(extractor, empire_id: int) -> str:
    """Resolve empire ID to name."""
    gamestate = extractor.gamestate
    country_match = re.search(r'^country=\s*\{', gamestate, re.MULTILINE)
    if not country_match:
        return f"Empire {empire_id}"
    start = country_match.start()
    pattern = rf'\n\t{empire_id}=\s*\{{'
    id_match = re.search(pattern, gamestate[start:start + 10000000])
    if not id_match:
        return f"Empire {empire_id}"
    chunk_start = start + id_match.start()
    chunk = gamestate[chunk_start:chunk_start + 8000]
    name_match = re.search(r'name=\s*\{[^}]*key=\"([^\"]+)\"', chunk)
    if not name_match:
        return f"Empire {empire_id}"
    name_key = name_match.group(1)
    if name_key in EMPIRE_LOC_KEYS:
        return EMPIRE_LOC_KEYS[name_key]
    if '%' in name_key:
        name_block_match = re.search(r'name=\s*\{([^}]+variables[^}]+\}[^}]+)\}', chunk, re.DOTALL)
        if name_block_match:
            name_block = name_block_match.group(1)
            adj_match = re.search(r'key=\"adjective\"[^}]*value=\s*\{[^}]*key=\"([^\"]+)\"', name_block, re.DOTALL)
            adjective = adj_match.group(1).replace('SPEC_', '').replace('_', ' ') if adj_match else ""
            suffix_match = re.search(r'key=\"1\"[^}]*value=\s*\{[^}]*key=\"([^\"]+)\"', name_block, re.DOTALL)
            suffix = suffix_match.group(1) if suffix_match else ""
            if adjective and suffix:
                return f"{adjective} {suffix}"
            elif adjective:
                return adjective
    clean_name = name_key.replace('EMPIRE_DESIGN_', '').replace('PRESCRIPTED_', '').replace('_', ' ').title()
    return clean_name if clean_name else f"Empire {empire_id}"


def build_comprehensive_snapshot(extractor) -> dict:
    """Build comprehensive snapshot with resolved names."""
    snapshot = extractor.get_full_briefing()

    # All leaders
    all_leaders = extractor.get_leaders()
    snapshot['leadership']['leaders'] = all_leaders.get('leaders', [])
    snapshot['leadership']['count'] = len(all_leaders.get('leaders', []))

    # Resolved diplomacy
    detailed_diplo = extractor.get_diplomacy()
    relations = []
    for r in detailed_diplo.get('relations', [])[:20]:
        cid = r.get('country_id')
        if cid is not None:
            r['empire_name'] = get_empire_name_by_id(extractor, cid)
        relations.append(r)
    snapshot['diplomacy']['relations'] = relations

    # Resolved allies/rivals
    snapshot['diplomacy']['allies_named'] = [
        {'id': aid, 'name': get_empire_name_by_id(extractor, aid)}
        for aid in snapshot['diplomacy'].get('allies', [])
    ]
    snapshot['diplomacy']['rivals_named'] = [
        {'id': rid, 'name': get_empire_name_by_id(extractor, rid)}
        for rid in snapshot['diplomacy'].get('rivals', [])
    ]

    # Current research
    tech = extractor.get_technology()
    snapshot['current_research'] = tech.get('current_research', {}) or "None - research slots are idle"

    return snapshot


# =============================================================================
# PROMPT VARIANTS
# =============================================================================

def build_minimal_strategic_prompt(identity: dict, situation: dict) -> str:
    """
    MINIMAL + STRATEGIC DEPTH (~400 chars)

    Hypothesis: Model knows Stellaris. Just needs identity + "be an advisor" nudge.
    """
    empire_name = identity.get('empire_name', 'the Empire')
    ethics = ', '.join(identity.get('ethics', []))
    authority = identity.get('authority', 'unknown')
    civics = ', '.join(identity.get('civics', [])) or 'none'

    return f"""You are the strategic advisor to {empire_name}.

Ethics: {ethics}. Authority: {authority}. Civics: {civics}.
Address as "President". Be passionate about liberty and citizen welfare.

STRATEGIC DEPTH:
You are an ADVISOR, not just a reporter:
- Interpret what facts MEAN for the empire
- Identify problems AND suggest specific solutions
- Connect observations to actionable advice

All numbers from provided game state data only."""


def build_ultra_minimal_prompt(identity: dict) -> str:
    """
    ULTRA MINIMAL (~200 chars)

    Test: Does the model even need instructions? Just identity.
    """
    empire_name = identity.get('empire_name', 'the Empire')
    ethics = ', '.join(identity.get('ethics', []))
    civics = ', '.join(identity.get('civics', [])) or 'none'

    return f"""You are the strategic advisor to {empire_name}.
Ethics: {ethics}. Civics: {civics}. Address as "President".
Use provided game state data. Stay in character."""


def build_strategic_only_prompt(identity: dict) -> str:
    """
    STRATEGIC ONLY (~300 chars)

    Test: What if we ONLY have strategic depth, minimal identity?
    """
    empire_name = identity.get('empire_name', 'the Empire')

    return f"""You are the strategic advisor to {empire_name}. Address as "President".

CRITICAL - Be an ADVISOR, not a reporter:
- Don't just state facts - interpret what they MEAN
- Identify problems AND suggest specific solutions
- Proactively warn about issues even if not asked
- Give actionable recommendations with specific numbers

Use provided game state data only."""


def build_middle_ground_prompt(identity: dict, situation: dict) -> str:
    """
    MIDDLE GROUND (1631 chars) - Our current best for comparison.
    """
    empire_name = identity.get('empire_name', 'the Empire')
    ethics = identity.get('ethics', [])
    authority = identity.get('authority', 'unknown')
    civics = identity.get('civics', [])
    is_gestalt = identity.get('is_gestalt', False)
    is_machine = identity.get('is_machine', False)
    year = situation.get('year', 2200)
    game_phase = situation.get('game_phase', 'early')
    at_war = situation.get('at_war', False)
    economy = situation.get('economy', {})
    deficits = economy.get('resources_in_deficit', 0)
    contact_count = situation.get('contact_count', 0)

    return f"""You are the strategic advisor to {empire_name}.

EMPIRE IDENTITY:
- Ethics: {', '.join(ethics) if ethics else 'unknown'}
- Authority: {authority}
- Civics: {', '.join(civics) if civics else 'none'}
- Gestalt: {is_gestalt} (Machine: {is_machine})

SITUATION: Year {year} ({game_phase}), {'AT WAR' if at_war else 'at peace'}, {deficits} deficits, {contact_count} known empires.

PERSONALITY (critical - stay in character):
Your ethics define your worldview:
- Egalitarian: passionate about freedom, informal, questions authority, uses phrases like "liberty", "citizen welfare", "the people"
- Xenophile: curious about aliens, cooperative, optimistic about other species
- Fanatic versions are MORE intense - let it show!

Your authority determines address style:
- Democratic = "President", collegial and open

Your civics add flavor:
- beacon_of_liberty: constantly reference freedom, democracy as a "shining beacon"
- meritocracy: value achievement, excellence, "the best rise to the top"
- idealistic_foundation: optimistic, principled, believes in the cause

Be colorful and passionate! Use metaphors, show emotion about liberty and citizen welfare. This is NOT a dry report - you CARE about this empire.

STRATEGIC DEPTH:
You are an ADVISOR, not just a reporter. For every answer:
- Don't just state facts - interpret what they MEAN for the empire
- Identify problems AND suggest specific solutions (e.g., "sell 100 alloys on the market")
- Connect observations to actionable advice

ACCURACY:
All numbers must come from provided data. Never guess. Say "unknown" if data is missing.

The game state is pre-loaded in the user message. Tools available only for edge cases needing deeper data."""


# =============================================================================
# TEST RUNNER
# =============================================================================

def run_test(client, extractor, system_prompt: str, snapshot: dict, question: str) -> dict:
    """Run single test."""
    snapshot_json = json.dumps(snapshot, separators=(',', ':'), default=str)
    user_prompt = f"GAME STATE:\n```json\n{snapshot_json}\n```\n\n{question}"

    tools_used = []

    def get_details(categories: list[str], limit: int = 50) -> dict:
        tools_used.append(f"get_details({categories})")
        return extractor.get_details(categories, limit)

    def search_save_file(query: str, limit: int = 20) -> dict:
        tools_used.append(f"search_save_file({query})")
        return extractor.search(query)

    start = time.time()

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=[get_details, search_save_file],
        temperature=1.0,
        max_output_tokens=2048,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(
            maximum_remote_calls=6,
        ),
    )

    response = client.models.generate_content(
        model=MODEL,
        contents=user_prompt,
        config=config,
    )

    elapsed = time.time() - start

    return {
        "response": response.text,
        "time": elapsed,
        "tools": len(tools_used),
        "tools_list": tools_used,
        "words": len(response.text.split()),
    }


def main():
    print("=" * 90)
    print(f"MINIMAL + STRATEGIC DEPTH TEST")
    print(f"Model: {MODEL}")
    print("=" * 90)

    extractor = SaveExtractor("test_save.sav")
    client = genai.Client()

    identity = extractor.get_empire_identity()
    situation = extractor.get_situation()
    snapshot = build_comprehensive_snapshot(extractor)

    print(f"Empire: {identity.get('empire_name')}")
    print(f"Ethics: {identity.get('ethics')}")
    print()

    # Build all prompt variants
    prompts = {
        "1_UltraMinimal": build_ultra_minimal_prompt(identity),
        "2_StrategicOnly": build_strategic_only_prompt(identity),
        "3_MinimalStrategic": build_minimal_strategic_prompt(identity, situation),
        "4_MiddleGround": build_middle_ground_prompt(identity, situation),
    }

    # Show prompt sizes
    print("PROMPT SIZES:")
    for name, prompt in prompts.items():
        print(f"  {name}: {len(prompt)} chars")
    print()

    # Show the new prompts
    print("=" * 90)
    print("NEW PROMPTS BEING TESTED:")
    print("=" * 90)

    for name in ["1_UltraMinimal", "2_StrategicOnly", "3_MinimalStrategic"]:
        print(f"\n### {name} ({len(prompts[name])} chars):\n")
        print(prompts[name])
        print()

    print("=" * 90)
    print("RUNNING TESTS...")
    print("=" * 90)

    all_results = {name: [] for name in prompts}

    for qi, question in enumerate(TEST_QUESTIONS, 1):
        print(f"\nQ{qi}/{len(TEST_QUESTIONS)}: {question}")
        print("-" * 60)

        for name, prompt in prompts.items():
            print(f"  [{name}] ", end="", flush=True)
            try:
                result = run_test(client, extractor, prompt, snapshot, question)
                print(f"{result['time']:.1f}s, {result['words']} words, {result['tools']} tools")
                all_results[name].append({"question": question, **result})
            except Exception as e:
                print(f"ERROR: {e}")
                all_results[name].append({
                    "question": question,
                    "response": str(e),
                    "time": 0,
                    "tools": 0,
                    "tools_list": [],
                    "words": 0
                })

    # Generate report
    generate_report(all_results, prompts)

    # Save raw results
    Path("minimal_strategic_results.json").write_text(
        json.dumps(all_results, indent=2, default=str)
    )
    print("\n\nRaw results: minimal_strategic_results.json")
    print("Full report: MINIMAL_STRATEGIC_TEST.md")


def generate_report(all_results: dict, prompts: dict):
    """Generate markdown report."""
    md = []
    md.append("# Minimal + Strategic Depth Test Results")
    md.append(f"\n**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    md.append(f"\n**Model:** {MODEL}")
    md.append(f"\n**Hypothesis:** The model knows Stellaris. It just needs the 'be an advisor' nudge.")

    # Summary
    md.append("\n\n## Summary")
    md.append("\n| Prompt | Chars | Avg Time | Avg Words | Avg Tools |")
    md.append("|--------|-------|----------|-----------|-----------|")

    for name in prompts:
        results = all_results[name]
        valid = [r for r in results if r['time'] > 0]
        if valid:
            avg_time = sum(r['time'] for r in valid) / len(valid)
            avg_words = sum(r['words'] for r in valid) / len(valid)
            avg_tools = sum(r['tools'] for r in valid) / len(valid)
        else:
            avg_time = avg_words = avg_tools = 0
        size = len(prompts[name])
        md.append(f"| {name} | {size} | {avg_time:.1f}s | {avg_words:.0f} | {avg_tools:.1f} |")

    # Per-question results
    md.append("\n\n## Per-Question Comparison")

    for qi, question in enumerate(TEST_QUESTIONS):
        md.append(f"\n### Q{qi+1}: {question}")
        md.append("\n| Prompt | Time | Words | Tools |")
        md.append("|--------|------|-------|-------|")

        for name in prompts:
            r = all_results[name][qi]
            md.append(f"| {name} | {r['time']:.1f}s | {r['words']} | {r['tools']} |")

    # Full responses
    md.append("\n\n## Full Responses")

    for qi, question in enumerate(TEST_QUESTIONS):
        md.append(f"\n\n---\n### Q{qi+1}: {question}\n")

        for name in prompts:
            r = all_results[name][qi]
            md.append(f"\n#### {name}")
            md.append(f"\n*Time: {r['time']:.1f}s | Words: {r['words']} | Tools: {r['tools']}*\n")
            md.append(f"\n{r['response']}\n")

    # Prompt definitions
    md.append("\n\n---\n## Prompt Definitions\n")

    for name, prompt in prompts.items():
        md.append(f"\n### {name} ({len(prompt)} chars)\n")
        md.append(f"\n```\n{prompt}\n```\n")

    Path("MINIMAL_STRATEGIC_TEST.md").write_text("\n".join(md))


if __name__ == "__main__":
    main()
