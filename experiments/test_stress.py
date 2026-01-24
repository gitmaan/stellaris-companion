#!/usr/bin/env python3
"""
Stress Test: Enhanced vs Production
====================================

Comprehensive comparison with proper empire name resolution.
Analyzes output quality to ensure enhanced doesn't miss anything.
"""

import json
import re
import sys
import time
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from google import genai
from google.genai import types
from save_extractor import SaveExtractor

# Comprehensive test questions
TEST_QUESTIONS = [
    # Simple factual
    "What is my current military power?",
    "How many colonies do I have?",
    "What is my total population?",

    # Economy
    "What is the state of my economy?",
    "Am I running any resource deficits?",
    "How much alloy am I producing per month?",

    # Diplomacy
    "Who are my allies?",
    "Do I have any rivals?",
    "What are my relationships with other empires?",
    "How many empires have I met?",

    # Military
    "Tell me about my fleets.",
    "Who is my best military commander?",
    "What starbases do I have?",

    # Leaders & Research
    "Who are my scientists?",
    "What technologies am I currently researching?",
    "Tell me about my leaders.",

    # Strategic
    "Give me a strategic assessment.",
    "What should my top priorities be right now?",
    "What threats should I be worried about?",
]

# Known Stellaris empire localization keys
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

    # Try to get name key
    name_match = re.search(r'name=\s*\{[^}]*key=\"([^\"]+)\"', chunk)
    if not name_match:
        return f"Empire {empire_id}"

    name_key = name_match.group(1)

    # Check known localization keys
    if name_key in EMPIRE_LOC_KEYS:
        return EMPIRE_LOC_KEYS[name_key]

    # Handle procedural names (%ADJECTIVE%, etc.)
    if '%' in name_key:
        # Extract variables
        name_block_match = re.search(r'name=\s*\{([^}]+variables[^}]+\}[^}]+)\}', chunk, re.DOTALL)
        if name_block_match:
            name_block = name_block_match.group(1)

            # Find adjective value
            adj_match = re.search(r'key=\"adjective\"[^}]*value=\s*\{[^}]*key=\"([^\"]+)\"', name_block, re.DOTALL)
            adjective = ""
            if adj_match:
                adj_key = adj_match.group(1)
                # Clean up SPEC_ prefix
                adjective = adj_key.replace('SPEC_', '').replace('_', ' ')

            # Find suffix (like "State", "Empire", etc.)
            suffix_match = re.search(r'key=\"1\"[^}]*value=\s*\{[^}]*key=\"([^\"]+)\"', name_block, re.DOTALL)
            suffix = ""
            if suffix_match:
                suffix = suffix_match.group(1)

            if adjective and suffix:
                return f"{adjective} {suffix}"
            elif adjective:
                return adjective

    # Fallback - try to clean up the key
    clean_name = name_key.replace('EMPIRE_DESIGN_', '').replace('PRESCRIPTED_', '').replace('_', ' ').title()
    return clean_name if clean_name else f"Empire {empire_id}"


def build_enhanced_snapshot(extractor) -> dict:
    """Build enhanced snapshot with resolved empire names."""
    snapshot = extractor.get_full_briefing()

    # Resolve ally IDs to names
    ally_ids = snapshot.get('diplomacy', {}).get('allies', [])
    allies_resolved = []
    for aid in ally_ids:
        name = get_empire_name_by_id(extractor, aid)
        allies_resolved.append({"id": aid, "name": name})

    if 'diplomacy' in snapshot:
        snapshot['diplomacy']['allies_resolved'] = allies_resolved

    # Resolve rival IDs to names
    rival_ids = snapshot.get('diplomacy', {}).get('rivals', [])
    rivals_resolved = []
    for rid in rival_ids:
        name = get_empire_name_by_id(extractor, rid)
        rivals_resolved.append({"id": rid, "name": name})

    if 'diplomacy' in snapshot:
        snapshot['diplomacy']['rivals_resolved'] = rivals_resolved

    # Add current research explicitly
    tech = extractor.get_technology()
    snapshot['current_research'] = tech.get('current_research', {})
    if not snapshot['current_research']:
        snapshot['current_research'] = "None - research slots are idle"

    return snapshot


def build_enhanced_system_prompt(base_personality_prompt: str) -> str:
    """
    Use the PRODUCTION personality prompt and replace the tools section
    with our enhanced data & tools instructions.
    """
    # Remove the outdated TOOLS section from production prompt
    # It ends with "Always use tools to get current data rather than guessing."
    tools_marker = "TOOLS: You have access to tools"
    if tools_marker in base_personality_prompt:
        # Cut off at TOOLS section
        prompt = base_personality_prompt[:base_personality_prompt.index(tools_marker)]
    else:
        prompt = base_personality_prompt

    # Add our enhanced data & tools section
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


def run_current_version(question: str) -> dict:
    """Run the current production version."""
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


def run_enhanced_version(extractor, client, production_system_prompt: str, question: str) -> dict:
    """Run enhanced version using production personality prompt."""
    system_prompt = build_enhanced_system_prompt(production_system_prompt)
    snapshot_data = build_enhanced_snapshot(extractor)
    snapshot_json = json.dumps(snapshot_data, separators=(",", ":"), default=str)
    user_prompt = f"GAME STATE:\n```json\n{snapshot_json}\n```\n\n{question}"

    tools_used = []

    def get_details(categories: list[str], limit: int = 50) -> dict:
        """Get detailed data for categories like leaders, fleets, diplomacy, etc."""
        tools_used.append(f"get_details({categories})")
        # Use extractor's native get_details which properly maps categories
        return extractor.get_details(categories, limit)

    def search_save_file(query: str, limit: int = 20) -> dict:
        tools_used.append(f"search_save_file({query})")
        return extractor.search(query)

    tools = [get_details, search_save_file]

    start = time.time()

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=tools,
        temperature=1.0,
        max_output_tokens=2048,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(
            maximum_remote_calls=6,
        ),
    )

    response = client.models.generate_content(
        model="gemini-2.0-flash",
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


def analyze_response_quality(question: str, current: dict, enhanced: dict) -> dict:
    """Analyze if enhanced response is missing anything from current."""

    curr_resp = current['response'].lower()
    enh_resp = enhanced['response'].lower()

    # Extract numbers from both responses
    curr_numbers = set(re.findall(r'\d+(?:,\d{3})*(?:\.\d+)?', current['response']))
    enh_numbers = set(re.findall(r'\d+(?:,\d{3})*(?:\.\d+)?', enhanced['response']))

    # Key numbers that should be present
    missing_numbers = curr_numbers - enh_numbers
    extra_numbers = enh_numbers - curr_numbers

    # Check for key terms
    key_terms = {
        'military': ['military power', 'fleet', 'ships', 'naval'],
        'economy': ['energy', 'minerals', 'alloys', 'deficit', 'surplus'],
        'diplomacy': ['allies', 'rivals', 'relations', 'trust'],
        'research': ['research', 'technology', 'science'],
        'strategic': ['priority', 'threat', 'recommend', 'suggest'],
    }

    curr_terms = set()
    enh_terms = set()

    for category, terms in key_terms.items():
        for term in terms:
            if term in curr_resp:
                curr_terms.add(term)
            if term in enh_resp:
                enh_terms.add(term)

    missing_terms = curr_terms - enh_terms

    return {
        "curr_numbers": len(curr_numbers),
        "enh_numbers": len(enh_numbers),
        "missing_numbers": list(missing_numbers)[:5],  # Top 5
        "curr_terms": len(curr_terms),
        "enh_terms": len(enh_terms),
        "missing_terms": list(missing_terms),
        "quality_score": "GOOD" if len(missing_numbers) < 3 and len(missing_terms) < 2 else "CHECK",
    }


def main():
    print("=" * 90)
    print("COMPREHENSIVE STRESS TEST: Enhanced vs Production")
    print("=" * 90)

    extractor = SaveExtractor("test_save.sav")
    client = genai.Client()

    # Get production system prompt from Companion
    from core.companion import Companion
    companion = Companion(save_path="test_save.sav")
    production_system_prompt = companion.system_prompt
    print(f"\nProduction system prompt: {len(production_system_prompt)} chars")

    # Test empire name resolution
    print("\n=== EMPIRE NAME RESOLUTION TEST ===")
    for eid in [0, 1, 2, 16777227]:
        name = get_empire_name_by_id(extractor, eid)
        print(f"  Empire {eid}: {name}")

    print(f"\nTesting {len(TEST_QUESTIONS)} questions...")
    print()

    results = []
    quality_issues = []

    for i, question in enumerate(TEST_QUESTIONS, 1):
        print(f"[{i}/{len(TEST_QUESTIONS)}] {question[:50]}...", end=" ", flush=True)

        try:
            current = run_current_version(question)
        except Exception as e:
            current = {"response": str(e), "time": 0, "tools": 0, "tools_list": [], "words": 0}

        try:
            enhanced = run_enhanced_version(extractor, client, production_system_prompt, question)
        except Exception as e:
            enhanced = {"response": str(e), "time": 0, "tools": 0, "tools_list": [], "words": 0}

        quality = analyze_response_quality(question, current, enhanced)

        print(f"Curr: {current['time']:.1f}s/{current['words']}w | Enh: {enhanced['time']:.1f}s/{enhanced['words']}w | {quality['quality_score']}")

        if quality['quality_score'] == "CHECK":
            quality_issues.append({
                "question": question,
                "missing_numbers": quality['missing_numbers'],
                "missing_terms": quality['missing_terms'],
            })

        results.append({
            "question": question,
            "current": current,
            "enhanced": enhanced,
            "quality": quality,
        })

    # Summary
    print("\n" + "=" * 90)
    print("SUMMARY")
    print("=" * 90)

    valid = [r for r in results if r['current']['time'] > 0 and r['enhanced']['time'] > 0]

    avg_curr_time = sum(r['current']['time'] for r in valid) / len(valid)
    avg_enh_time = sum(r['enhanced']['time'] for r in valid) / len(valid)
    avg_curr_tools = sum(r['current']['tools'] for r in valid) / len(valid)
    avg_enh_tools = sum(r['enhanced']['tools'] for r in valid) / len(valid)
    avg_curr_words = sum(r['current']['words'] for r in valid) / len(valid)
    avg_enh_words = sum(r['enhanced']['words'] for r in valid) / len(valid)

    print(f"\n{'Metric':<25} {'Current':>12} {'Enhanced':>12} {'Change':>12}")
    print("-" * 65)
    print(f"{'Avg Response Time':<25} {avg_curr_time:>11.1f}s {avg_enh_time:>11.1f}s {((avg_curr_time-avg_enh_time)/avg_curr_time*100):>+11.0f}%")
    print(f"{'Avg Tool Calls':<25} {avg_curr_tools:>12.1f} {avg_enh_tools:>12.1f} {((avg_curr_tools-avg_enh_tools)/max(avg_curr_tools,0.1)*100):>+11.0f}%")
    print(f"{'Avg Word Count':<25} {avg_curr_words:>12.0f} {avg_enh_words:>12.0f} {((avg_enh_words-avg_curr_words)/avg_curr_words*100):>+11.0f}%")

    good_count = sum(1 for r in results if r['quality']['quality_score'] == "GOOD")
    print(f"\n{'Quality Score':<25} {good_count}/{len(results)} responses rated GOOD")

    # Quality issues
    if quality_issues:
        print("\n" + "=" * 90)
        print("QUALITY ISSUES TO REVIEW")
        print("=" * 90)
        for issue in quality_issues:
            print(f"\nQ: {issue['question']}")
            if issue['missing_numbers']:
                print(f"   Missing numbers: {issue['missing_numbers']}")
            if issue['missing_terms']:
                print(f"   Missing terms: {issue['missing_terms']}")

    # Detailed comparison for flagged items
    print("\n" + "=" * 90)
    print("DETAILED RESPONSE COMPARISON (Flagged Items)")
    print("=" * 90)

    for r in results:
        if r['quality']['quality_score'] == "CHECK":
            print(f"\n### {r['question']}")
            print(f"\n**CURRENT** ({r['current']['words']} words, {r['current']['tools']} tools):")
            print(r['current']['response'][:600] + "..." if len(r['current']['response']) > 600 else r['current']['response'])
            print(f"\n**ENHANCED** ({r['enhanced']['words']} words, {r['enhanced']['tools']} tools):")
            print(r['enhanced']['response'][:600] + "..." if len(r['enhanced']['response']) > 600 else r['enhanced']['response'])

    # Save full results
    Path("stress_test_results.json").write_text(json.dumps(results, indent=2, default=str))
    print(f"\n\nFull results saved to stress_test_results.json")


if __name__ == "__main__":
    main()
