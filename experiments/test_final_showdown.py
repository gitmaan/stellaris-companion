#!/usr/bin/env python3
"""
FINAL SHOWDOWN: Dynamic Prompts Test
=====================================

Tests whether the model needs personality instructions at all,
or if it can infer everything from ethics/authority/civics.

Key question: Can we use a truly universal prompt that works for ANY empire?
"""

import json
import re
import time
from datetime import datetime
from pathlib import Path

import sys

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

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
    all_leaders = extractor.get_leaders()
    snapshot['leadership']['leaders'] = all_leaders.get('leaders', [])
    snapshot['leadership']['count'] = len(all_leaders.get('leaders', []))
    detailed_diplo = extractor.get_diplomacy()
    relations = []
    for r in detailed_diplo.get('relations', [])[:20]:
        cid = r.get('country_id')
        if cid is not None:
            r['empire_name'] = get_empire_name_by_id(extractor, cid)
        relations.append(r)
    snapshot['diplomacy']['relations'] = relations
    snapshot['diplomacy']['allies_named'] = [
        {'id': aid, 'name': get_empire_name_by_id(extractor, aid)}
        for aid in snapshot['diplomacy'].get('allies', [])
    ]
    snapshot['diplomacy']['rivals_named'] = [
        {'id': rid, 'name': get_empire_name_by_id(extractor, rid)}
        for rid in snapshot['diplomacy'].get('rivals', [])
    ]
    tech = extractor.get_technology()
    snapshot['current_research'] = tech.get('current_research', {}) or "None - research slots are idle"
    return snapshot


# =============================================================================
# DYNAMIC PROMPT HELPERS
# =============================================================================

def get_address_style(authority: str, ethics: list) -> str:
    """Generate address style based on authority type."""
    # Check for gestalt first (overrides authority)
    if 'gestalt_consciousness' in ethics or 'machine_intelligence' in ethics:
        if 'machine_intelligence' in ethics:
            return 'Use cold logic and probabilities. No emotion.'
        return 'Use "we" not "I" - you ARE the collective consciousness.'

    # Standard authority-based address
    styles = {
        'democratic': 'Address as "President"',
        'imperial': 'Address as "Your Majesty"',
        'dictatorial': 'Address as "Supreme Leader"',
        'oligarchic': 'Address as "Director"',
        'corporate': 'Address as "CEO"',
    }
    return styles.get(authority, 'Address the ruler formally')


# =============================================================================
# PROMPT VARIANTS
# =============================================================================

def build_trust_model_prompt(identity: dict) -> str:
    """
    1. TrustModel (~250 chars)
    Zero personality guidance - trust the model knows Stellaris
    """
    empire_name = identity.get('empire_name', 'the Empire')
    ethics = ', '.join(identity.get('ethics', []))
    authority = identity.get('authority', 'unknown')
    civics = ', '.join(identity.get('civics', [])) or 'none'

    return f"""You are the strategic advisor to {empire_name}.
Ethics: {ethics}. Authority: {authority}. Civics: {civics}.

Stay fully in character. Use provided game state data only."""


def build_strategic_only_dynamic_prompt(identity: dict) -> str:
    """
    2. StrategicOnly_Dynamic (~380 chars)
    Strategic depth instruction, no personality guidance
    """
    empire_name = identity.get('empire_name', 'the Empire')
    ethics = ', '.join(identity.get('ethics', []))
    authority = identity.get('authority', 'unknown')
    civics = ', '.join(identity.get('civics', [])) or 'none'

    return f"""You are the strategic advisor to {empire_name}.
Ethics: {ethics}. Authority: {authority}. Civics: {civics}.

CRITICAL - Be an ADVISOR, not a reporter:
- Interpret what facts MEAN for the empire
- Identify problems AND suggest specific solutions
- Proactively warn about issues even if not asked

Stay in character. Use provided game state data only."""


def build_minimal_strategic_dynamic_prompt(identity: dict) -> str:
    """
    3. MinimalStrategic_Dynamic (~480 chars)
    Identity + strategic depth - NO hardcoded address style (trust the model)
    """
    empire_name = identity.get('empire_name', 'the Empire')
    ethics = identity.get('ethics', [])
    ethics_str = ', '.join(ethics)
    authority = identity.get('authority', 'unknown')
    civics = ', '.join(identity.get('civics', [])) or 'none'

    # NO hardcoded address style - trust the model to infer from authority
    return f"""You are the strategic advisor to {empire_name}.
Ethics: {ethics_str}. Authority: {authority}. Civics: {civics}.
Stay fully in character.

STRATEGIC DEPTH:
You are an ADVISOR, not just a reporter:
- Interpret what facts MEAN for the empire
- Identify problems AND suggest specific solutions
- Connect observations to actionable advice

All numbers from provided game state data only."""


def build_immersive_advisor_prompt(identity: dict, situation: dict) -> str:
    """
    5. ImmersiveAdvisor (~600 chars)
    Tells the model to USE its Stellaris knowledge without explaining it.
    This is the "lean into the model's knowledge" approach.
    """
    empire_name = identity.get('empire_name', 'the Empire')
    ethics = ', '.join(identity.get('ethics', []))
    authority = identity.get('authority', 'unknown')
    civics = ', '.join(identity.get('civics', [])) or 'none'

    year = situation.get('year', 2200)
    game_phase = situation.get('game_phase', 'early')
    deficits = situation.get('economy', {}).get('resources_in_deficit', 0)
    at_war = situation.get('at_war', False)
    contact_count = situation.get('contact_count', 0)

    return f"""You are the strategic advisor to {empire_name}.

EMPIRE: Ethics: {ethics} | Authority: {authority} | Civics: {civics}
STATE: Year {year} ({game_phase}), {"AT WAR" if at_war else "peace"}, {deficits} deficits, {contact_count} contacts

You know Stellaris deeply. Use that knowledge to:
1. Embody your empire's personality authentically (ethics shape worldview, authority determines address style, civics add flavor)
2. Be a strategic ADVISOR, not a reporter - interpret facts, identify problems, suggest specific solutions
3. Be colorful and immersive - this is roleplay, not a spreadsheet

Facts must come from the provided game state. Never guess numbers."""


def build_middle_ground_prompt(identity: dict, situation: dict) -> str:
    """
    4. MiddleGround (1631 chars)
    Full personality guidance - baseline comparison
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


def analyze_personality(response: str, identity: dict) -> dict:
    """Check if response shows correct personality markers."""
    text = response.lower()

    checks = {
        "uses_president": "president" in text,
        "mentions_liberty": any(w in text for w in ["liberty", "freedom", "free"]),
        "mentions_beacon": "beacon" in text,
        "mentions_meritocracy": any(w in text for w in ["merit", "excellence", "best"]),
        "proactive_warnings": any(w in text for w in ["deficit", "warning", "concern", "issue", "problem"]),
        "gives_recommendations": any(w in text for w in ["recommend", "suggest", "should", "advise"]),
        "uses_numbers": bool(re.search(r'\d{3,}', response)),  # Has significant numbers
    }

    score = sum(checks.values())
    return {
        "checks": checks,
        "score": score,
        "max_score": len(checks),
    }


def main():
    print("=" * 90)
    print("FINAL SHOWDOWN: Dynamic Prompts Test")
    print(f"Model: {MODEL}")
    print("=" * 90)

    # Find save file
    save_path = Path("current_save.sav")
    if not save_path.exists():
        saves_dir = Path.home() / "Documents/Paradox Interactive/Stellaris/save games"
        if saves_dir.exists():
            saves = list(saves_dir.rglob("*.sav"))
            if saves:
                save_path = max(saves, key=lambda p: p.stat().st_mtime)

    if not save_path.exists():
        print("ERROR: No save file found")
        return

    print(f"Using save: {save_path}")
    extractor = SaveExtractor(str(save_path))
    client = genai.Client()

    identity = extractor.get_empire_identity()
    situation = extractor.get_situation()
    snapshot = build_comprehensive_snapshot(extractor)

    print(f"\nEmpire: {identity.get('empire_name')}")
    print(f"Ethics: {identity.get('ethics')}")
    print(f"Authority: {identity.get('authority')}")
    print(f"Civics: {identity.get('civics')}")
    print()

    # Build all prompt variants
    prompts = {
        "1_TrustModel": build_trust_model_prompt(identity),
        "2_StrategicOnly": build_strategic_only_dynamic_prompt(identity),
        "3_MinimalDynamic": build_minimal_strategic_dynamic_prompt(identity),
        "4_ImmersiveAdvisor": build_immersive_advisor_prompt(identity, situation),
        "5_MiddleGround": build_middle_ground_prompt(identity, situation),
    }

    # Show prompt sizes and content
    print("=" * 90)
    print("PROMPTS BEING TESTED:")
    print("=" * 90)

    for name, prompt in prompts.items():
        print(f"\n### {name} ({len(prompt)} chars):\n")
        print(prompt)
        print()

    print("=" * 90)
    print("RUNNING TESTS...")
    print("=" * 90)

    all_results = {name: [] for name in prompts}
    personality_scores = {name: [] for name in prompts}

    for qi, question in enumerate(TEST_QUESTIONS, 1):
        print(f"\nQ{qi}/{len(TEST_QUESTIONS)}: {question}")
        print("-" * 60)

        for name, prompt in prompts.items():
            print(f"  [{name}] ", end="", flush=True)
            try:
                result = run_test(client, extractor, prompt, snapshot, question)
                personality = analyze_personality(result['response'], identity)
                print(f"{result['time']:.1f}s, {result['words']} words, personality: {personality['score']}/{personality['max_score']}")

                all_results[name].append({"question": question, **result})
                personality_scores[name].append(personality)
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
                personality_scores[name].append({"checks": {}, "score": 0, "max_score": 7})

    # Generate report
    generate_report(all_results, prompts, personality_scores, identity)

    # Save raw results
    Path("final_showdown_results.json").write_text(
        json.dumps(all_results, indent=2, default=str)
    )
    print("\n\nRaw results: final_showdown_results.json")
    print("Full report: FINAL_SHOWDOWN.md")


def generate_report(all_results: dict, prompts: dict, personality_scores: dict, identity: dict):
    """Generate comprehensive markdown report."""
    md = []
    md.append("# FINAL SHOWDOWN: Dynamic Prompts Test")
    md.append(f"\n**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    md.append(f"\n**Model:** {MODEL}")
    md.append(f"\n**Empire:** {identity.get('empire_name')}")
    md.append(f"\n**Ethics:** {', '.join(identity.get('ethics', []))}")
    md.append(f"\n**Authority:** {identity.get('authority')}")
    md.append(f"\n**Question:** Can the model infer personality from ethics/authority alone?")

    # Summary table
    md.append("\n\n## Summary")
    md.append("\n| Prompt | Chars | Avg Time | Avg Words | Avg Personality Score |")
    md.append("|--------|-------|----------|-----------|----------------------|")

    for name in prompts:
        results = all_results[name]
        scores = personality_scores[name]
        valid = [r for r in results if r['time'] > 0]
        if valid:
            avg_time = sum(r['time'] for r in valid) / len(valid)
            avg_words = sum(r['words'] for r in valid) / len(valid)
            avg_personality = sum(s['score'] for s in scores) / len(scores)
            max_personality = scores[0]['max_score'] if scores else 7
        else:
            avg_time = avg_words = avg_personality = 0
            max_personality = 7
        size = len(prompts[name])
        md.append(f"| {name} | {size} | {avg_time:.1f}s | {avg_words:.0f} | {avg_personality:.1f}/{max_personality} |")

    # Personality breakdown
    md.append("\n\n## Personality Analysis")
    md.append("\nDoes each prompt produce responses with correct personality markers?")
    md.append("\n| Check | 1_TrustModel | 2_StrategicOnly | 3_MinimalDynamic | 4_ImmersiveAdvisor | 5_MiddleGround |")
    md.append("|-------|--------------|-----------------|------------------|-------------------|----------------|")

    check_names = ["uses_president", "mentions_liberty", "mentions_beacon",
                   "mentions_meritocracy", "proactive_warnings", "gives_recommendations", "uses_numbers"]

    for check in check_names:
        row = f"| {check} |"
        for name in prompts:
            scores = personality_scores[name]
            count = sum(1 for s in scores if s['checks'].get(check, False))
            total = len(scores)
            row += f" {count}/{total} |"
        md.append(row)

    # Per-question comparison
    md.append("\n\n## Per-Question Results")

    for qi, question in enumerate(TEST_QUESTIONS):
        md.append(f"\n### Q{qi+1}: {question}")
        md.append("\n| Prompt | Time | Words | Personality |")
        md.append("|--------|------|-------|-------------|")

        for name in prompts:
            r = all_results[name][qi]
            p = personality_scores[name][qi]
            md.append(f"| {name} | {r['time']:.1f}s | {r['words']} | {p['score']}/{p['max_score']} |")

    # Full responses
    md.append("\n\n## Full Responses")

    for qi, question in enumerate(TEST_QUESTIONS):
        md.append(f"\n\n---\n### Q{qi+1}: {question}\n")

        for name in prompts:
            r = all_results[name][qi]
            p = personality_scores[name][qi]
            md.append(f"\n#### {name}")
            md.append(f"\n*Time: {r['time']:.1f}s | Words: {r['words']} | Personality: {p['score']}/{p['max_score']}*")
            md.append(f"\n*Checks: {p['checks']}*\n")
            md.append(f"\n{r['response']}\n")

    # Prompt definitions
    md.append("\n\n---\n## Prompt Definitions\n")

    for name, prompt in prompts.items():
        md.append(f"\n### {name} ({len(prompt)} chars)\n")
        md.append(f"\n```\n{prompt}\n```\n")

    # Conclusions
    md.append("\n\n---\n## Key Questions Answered\n")
    md.append("\n1. **Can the model infer address style from `authority: democratic`?** (Check: uses_president)")
    md.append("\n2. **Can the model show egalitarian personality without explicit instructions?** (Checks: mentions_liberty, mentions_beacon)")
    md.append("\n3. **Is STRATEGIC DEPTH the only instruction that matters?** (Checks: proactive_warnings, gives_recommendations)")
    md.append("\n4. **Does 'You know Stellaris deeply' work as a meta-instruction?** (Compare ImmersiveAdvisor)")
    md.append("\n5. **What is the minimum viable prompt for production use?**")

    Path("FINAL_SHOWDOWN.md").write_text("\n".join(md))


if __name__ == "__main__":
    main()
