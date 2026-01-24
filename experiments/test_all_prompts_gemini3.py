#!/usr/bin/env python3
"""
Test All Prompts with Gemini 3 Flash Preview
=============================================

This script tests ALL prompt variants we've developed, but this time
using the CORRECT model (gemini-3-flash-preview) instead of gemini-2.0-flash.

Prompts tested:
1. Clean/Minimal - stripped down prompt
2. Middle Ground - full personality + strategic depth
3. Enhanced - personality + strong tool instructions
4. Production + DATA/TOOLS - full production prompt with custom tools section
5. Production + ASK MODE - full production prompt with ASK MODE OVERRIDES

All results saved to PROMPT_COMPARISON_GEMINI3.md
"""

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from google import genai
from google.genai import types
from save_extractor import SaveExtractor

# THE CORRECT MODEL
MODEL = "gemini-3-flash-preview"

# Test questions - mix of simple and complex
TEST_QUESTIONS = [
    "What is my current military power?",
    "Who are my allies?",
    "What is the state of my economy?",
    "Who is my best military commander?",
    "Give me a strategic assessment.",
]

# Known empire localization keys
EMPIRE_LOC_KEYS = {
    'EMPIRE_DESIGN_orbis': 'United Nations of Earth',
    'EMPIRE_DESIGN_humans1': 'Commonwealth of Man',
    'EMPIRE_DESIGN_humans2': 'Terran Hegemony',
    'PRESCRIPTED_empire_name_orbis': 'United Nations of Earth',
}


def get_empire_name_by_id(extractor, empire_id: int) -> str:
    """Resolve an empire ID to its display name."""
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
            adjective = ""
            if adj_match:
                adj_key = adj_match.group(1)
                adjective = adj_key.replace('SPEC_', '').replace('_', ' ')
            suffix_match = re.search(r'key=\"1\"[^}]*value=\s*\{[^}]*key=\"([^\"]+)\"', name_block, re.DOTALL)
            suffix = ""
            if suffix_match:
                suffix = suffix_match.group(1)
            if adjective and suffix:
                return f"{adjective} {suffix}"
            elif adjective:
                return adjective

    clean_name = name_key.replace('EMPIRE_DESIGN_', '').replace('PRESCRIPTED_', '').replace('_', ' ').title()
    return clean_name if clean_name else f"Empire {empire_id}"


def build_comprehensive_snapshot(extractor) -> dict:
    """Build comprehensive snapshot with all leaders and resolved names."""
    snapshot = extractor.get_full_briefing()

    # Add ALL leaders
    all_leaders = extractor.get_leaders()
    snapshot['leadership']['leaders'] = all_leaders.get('leaders', [])
    snapshot['leadership']['count'] = len(all_leaders.get('leaders', []))

    # Detailed diplomacy with resolved names
    detailed_diplo = extractor.get_diplomacy()
    relations = []
    for r in detailed_diplo.get('relations', [])[:20]:
        cid = r.get('country_id')
        if cid is not None:
            r['empire_name'] = get_empire_name_by_id(extractor, cid)
        relations.append(r)
    snapshot['diplomacy']['relations'] = relations

    # Resolve ally names
    ally_ids = snapshot['diplomacy'].get('allies', [])
    snapshot['diplomacy']['allies_named'] = [
        {'id': aid, 'name': get_empire_name_by_id(extractor, aid)}
        for aid in ally_ids
    ]

    # Resolve rival names
    rival_ids = snapshot['diplomacy'].get('rivals', [])
    snapshot['diplomacy']['rivals_named'] = [
        {'id': rid, 'name': get_empire_name_by_id(extractor, rid)}
        for rid in rival_ids
    ]

    # Current research
    tech = extractor.get_technology()
    snapshot['current_research'] = tech.get('current_research', {})
    if not snapshot['current_research']:
        snapshot['current_research'] = "None - research slots are idle"

    return snapshot


# =============================================================================
# PROMPT BUILDERS
# =============================================================================

def build_clean_prompt(identity: dict, situation: dict) -> str:
    """1. Clean/Minimal prompt (~600 chars)"""
    empire_name = identity.get('empire_name', 'the Empire')
    ethics = identity.get('ethics', [])
    authority = identity.get('authority', 'unknown')
    civics = identity.get('civics', [])
    year = situation.get('year', 2200)
    game_phase = situation.get('game_phase', 'early')
    at_war = situation.get('at_war', False)
    economy = situation.get('economy', {})
    deficits = economy.get('resources_in_deficit', 0)

    return f"""You are the strategic advisor to {empire_name}.

YOUR PERSONALITY:
You embody {', '.join(ethics)} values with {authority} governance.
Civics: {', '.join(civics) if civics else 'none'}.
Address the ruler as "President" (democratic authority). Be collegial, passionate about liberty and citizen welfare.

CURRENT SITUATION: Year {year} ({game_phase} game), {'AT WAR' if at_war else 'at peace'}, {deficits} resource deficits.

RULES:
1. All facts and numbers MUST come from the provided game state data - never guess.
2. Stay fully in character with colorful, passionate language befitting your ethics.
3. You have drill-down tools (get_details, search_save_file) if the provided data lacks something specific."""


def build_middle_ground_prompt(identity: dict, situation: dict) -> str:
    """2. Middle Ground prompt (~1700 chars) - Full personality + strategic depth"""
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


def build_enhanced_prompt(identity: dict, situation: dict) -> str:
    """3. Enhanced prompt (~1500 chars) - Personality + strong tool instructions"""
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
- Egalitarian: passionate about freedom, informal, uses phrases like "liberty", "citizen welfare", "the people"
- Xenophile: curious about aliens, cooperative, optimistic
- Fanatic versions are MORE intense - let it show!

Address style: Democratic = "President", collegial and open.

Civics flavor:
- beacon_of_liberty: reference freedom, democracy as a "shining beacon"
- meritocracy: value achievement, "the best rise to the top"
- idealistic_foundation: optimistic, principled

Be colorful and passionate! This is NOT a dry report - you CARE about this empire.

STRATEGIC DEPTH:
You are an ADVISOR, not just a reporter:
- Interpret what facts MEAN for the empire
- Identify problems AND suggest specific solutions
- Connect observations to actionable advice

DATA & TOOLS:
- The game state snapshot is in the user message - use it for most answers.
- CRITICAL: If data is missing or incomplete, you MUST call a tool. Do NOT say "I need more information" without actually calling the tool.
- If you would say "I don't have that data" - STOP and call get_details() or search_save_file() instead.
- Available tools:
  * get_details(categories=["leaders", "diplomacy", "technology", etc.]) - for structured data
  * search_save_file(query="search term") - for finding specific things
- When you see raw IDs (like "Empire 1" or "ally ID 16777227"), call tools to get actual names.

ACCURACY: All numbers from data only. Say "unknown" if truly missing."""


def build_production_data_tools_prompt(base_prompt: str) -> str:
    """4. Production + DATA/TOOLS - Replace tools section with custom one"""
    tools_marker = "TOOLS: You have access to tools"
    if tools_marker in base_prompt:
        prompt = base_prompt[:base_prompt.index(tools_marker)]
    else:
        prompt = base_prompt

    prompt += """DATA & TOOLS:
- The game state snapshot is pre-loaded in the user message - use it for most answers.
- CRITICAL: If data is missing or incomplete, you MUST call a tool YOURSELF.
- NEVER ask the user to run tools. NEVER say "could you run get_details" or "I recommend calling the tool".
- YOU have direct access to these tools - call them immediately when needed:
  * get_details(categories=["leaders", "diplomacy", "technology", "military", etc.]) - for detailed data
  * search_save_file(query="search term") - for finding specific things
- The snapshot is a SUMMARY. For detailed questions (fleet compositions, specific leader traits, diplomatic details), call get_details().
- When you see raw IDs without names, call tools to resolve them.

RESPONSE STYLE:
- Maintain your full personality, colorful language, and in-character voice.
- Being efficient with tools does NOT mean being terse - express yourself!
- Proactively mention critical issues (deficits, threats) even if not directly asked.
- For complex questions (strategy, assessments, economy): provide THOROUGH analysis with specific numbers.
- Don't just summarize - explain what the data MEANS and give specific, actionable recommendations.
- Include relevant context: treasury balances, exact deficit amounts, comparative strengths."""

    return prompt


def build_production_ask_mode_prompt(base_prompt: str) -> str:
    """5. Production + ASK MODE OVERRIDES"""
    return (
        f"{base_prompt}\n\n"
        "ASK MODE OVERRIDES:\n"
        "- The current game state snapshot is included in the user message.\n"
        "- Never request get_snapshot(); it is not available in this mode.\n"
        "- Minimize tool usage: usually 0-1 tool calls.\n"
        "- If you must call tools, batch categories in one get_details call.\n"
        "- After gathering enough info, stop calling tools and answer.\n"
        "- IMPORTANT: Maintain your full personality, colorful language, and in-character voice. "
        "Being efficient with tools does NOT mean being terse - express yourself!\n"
    )


# =============================================================================
# TEST RUNNER
# =============================================================================

def run_prompt_test(client, extractor, system_prompt: str, snapshot: dict, question: str) -> dict:
    """Run a single test with given prompt."""
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
        model=MODEL,  # gemini-3-flash-preview
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


def run_production_version(question: str) -> dict:
    """Run production companion for comparison."""
    from core.companion import Companion
    companion = Companion(save_path="test_save.sav")
    companion.clear_conversation()

    start = time.time()
    response, elapsed = companion.ask_simple(question)
    stats = companion.get_call_stats()

    return {
        "response": response,
        "time": elapsed,
        "tools": stats.get('total_calls', 0),
        "tools_list": stats.get('tools_used', []),
        "words": len(response.split()),
    }


def main():
    print("=" * 90)
    print(f"TESTING ALL PROMPTS WITH {MODEL}")
    print("=" * 90)

    extractor = SaveExtractor("test_save.sav")
    client = genai.Client()

    identity = extractor.get_empire_identity()
    situation = extractor.get_situation()

    # Get production system prompt
    from core.companion import Companion
    temp_companion = Companion(save_path="test_save.sav")
    production_base_prompt = temp_companion.system_prompt

    print(f"Empire: {identity.get('empire_name')}")
    print(f"Ethics: {identity.get('ethics')}")
    print(f"Model: {MODEL}")
    print()

    # Build comprehensive snapshot
    snapshot = build_comprehensive_snapshot(extractor)

    # Build all prompts
    prompts = {
        "1_Clean": build_clean_prompt(identity, situation),
        "2_MiddleGround": build_middle_ground_prompt(identity, situation),
        "3_Enhanced": build_enhanced_prompt(identity, situation),
        "4_ProdDataTools": build_production_data_tools_prompt(production_base_prompt),
        "5_ProdAskMode": build_production_ask_mode_prompt(production_base_prompt),
    }

    # Show prompt sizes
    print("PROMPT SIZES:")
    for name, prompt in prompts.items():
        print(f"  {name}: {len(prompt)} chars")
    print(f"  Production (baseline): {len(production_base_prompt)} chars")
    print()

    # Results storage
    all_results = {name: [] for name in prompts}
    all_results["0_Production"] = []

    # Run tests
    for qi, question in enumerate(TEST_QUESTIONS, 1):
        print(f"\n{'='*90}")
        print(f"Q{qi}/{len(TEST_QUESTIONS)}: {question}")
        print("=" * 90)

        # Run production baseline
        print(f"\n[0_Production] ", end="", flush=True)
        try:
            prod_result = run_production_version(question)
            print(f"{prod_result['time']:.1f}s, {prod_result['words']} words, {prod_result['tools']} tools")
            all_results["0_Production"].append({"question": question, **prod_result})
        except Exception as e:
            print(f"ERROR: {e}")
            all_results["0_Production"].append({"question": question, "response": str(e), "time": 0, "tools": 0, "tools_list": [], "words": 0})

        # Run each prompt variant
        for name, prompt in prompts.items():
            print(f"[{name}] ", end="", flush=True)
            try:
                result = run_prompt_test(client, extractor, prompt, snapshot, question)
                print(f"{result['time']:.1f}s, {result['words']} words, {result['tools']} tools")
                all_results[name].append({"question": question, **result})
            except Exception as e:
                print(f"ERROR: {e}")
                all_results[name].append({"question": question, "response": str(e), "time": 0, "tools": 0, "tools_list": [], "words": 0})

    # Generate markdown report
    generate_markdown_report(all_results, prompts, production_base_prompt)

    # Save raw JSON
    Path("prompt_comparison_gemini3_results.json").write_text(
        json.dumps(all_results, indent=2, default=str)
    )
    print("\n\nRaw results saved to prompt_comparison_gemini3_results.json")
    print("Full report saved to PROMPT_COMPARISON_GEMINI3.md")


def generate_markdown_report(all_results: dict, prompts: dict, production_base_prompt: str):
    """Generate comprehensive markdown report."""

    md = []
    md.append("# Prompt Comparison with gemini-3-flash-preview")
    md.append(f"\n**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    md.append(f"\n**Model:** gemini-3-flash-preview")
    md.append(f"\n**Questions tested:** {len(TEST_QUESTIONS)}")

    # Summary table
    md.append("\n\n## Summary")
    md.append("\n| Prompt | Avg Time | Avg Words | Avg Tools | Prompt Size |")
    md.append("|--------|----------|-----------|-----------|-------------|")

    for name in ["0_Production"] + list(prompts.keys()):
        results = all_results[name]
        valid = [r for r in results if r['time'] > 0]
        if valid:
            avg_time = sum(r['time'] for r in valid) / len(valid)
            avg_words = sum(r['words'] for r in valid) / len(valid)
            avg_tools = sum(r['tools'] for r in valid) / len(valid)
        else:
            avg_time = avg_words = avg_tools = 0

        if name == "0_Production":
            size = len(production_base_prompt)
        else:
            size = len(prompts[name])

        md.append(f"| {name} | {avg_time:.1f}s | {avg_words:.0f} | {avg_tools:.1f} | {size} |")

    # Per-question comparison
    md.append("\n\n## Per-Question Results")

    for qi, question in enumerate(TEST_QUESTIONS):
        md.append(f"\n### Q{qi+1}: {question}")
        md.append("\n| Prompt | Time | Words | Tools |")
        md.append("|--------|------|-------|-------|")

        for name in ["0_Production"] + list(prompts.keys()):
            r = all_results[name][qi]
            md.append(f"| {name} | {r['time']:.1f}s | {r['words']} | {r['tools']} |")

    # Full responses for each question
    md.append("\n\n## Full Responses")

    for qi, question in enumerate(TEST_QUESTIONS):
        md.append(f"\n\n---\n### Q{qi+1}: {question}\n")

        for name in ["0_Production"] + list(prompts.keys()):
            r = all_results[name][qi]
            md.append(f"\n#### {name}")
            md.append(f"\n*Time: {r['time']:.1f}s | Words: {r['words']} | Tools: {r['tools']} {r.get('tools_list', [])}*\n")
            md.append(f"\n{r['response']}\n")

    # Prompt definitions
    md.append("\n\n---\n## Prompt Definitions\n")

    for name, prompt in prompts.items():
        md.append(f"\n### {name} ({len(prompt)} chars)\n")
        md.append(f"\n```\n{prompt}\n```\n")

    # Write file
    Path("PROMPT_COMPARISON_GEMINI3.md").write_text("\n".join(md))


if __name__ == "__main__":
    main()
