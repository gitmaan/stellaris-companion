#!/usr/bin/env python3
"""
Test: Enhanced Snapshot + Stronger Tool Instructions
=====================================================

Tests two improvements:
1. Enhanced snapshot with resolved ally names and current research
2. Stronger tool usage instructions when data is missing
"""

import json
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

sys.path.insert(0, str(Path(__file__).parent / "backend"))

from google import genai
from google.genai import types
from save_extractor import SaveExtractor

TEST_QUESTIONS = [
    "What is my current military power?",
    "Who are my allies?",
    "What technologies am I currently researching?",
    "Tell me about my best admiral or general.",
    "What are my relationships with neighboring empires?",
    "Give me a strategic assessment.",
]


def get_empire_name_by_id(extractor, empire_id: int) -> str:
    """Resolve an empire ID to its name by searching the save file."""
    # Search for the country entry with this ID
    gamestate = extractor.gamestate

    # Find country section
    country_match = re.search(r'^country=\s*\{', gamestate, re.MULTILINE)
    if not country_match:
        return f"Empire {empire_id}"

    start = country_match.start()

    # Look for the specific country ID entry
    pattern = rf'\n\t{empire_id}=\s*\{{'
    id_match = re.search(pattern, gamestate[start:start + 5000000])
    if not id_match:
        return f"Empire {empire_id}"

    # Extract a chunk and find the name
    chunk_start = start + id_match.start()
    chunk = gamestate[chunk_start:chunk_start + 5000]

    name_match = re.search(r'name="([^"]+)"', chunk)
    if name_match:
        return name_match.group(1)

    return f"Empire {empire_id}"


def build_enhanced_snapshot(extractor) -> dict:
    """Build an enhanced snapshot with resolved names and more detail."""

    # Get base snapshot
    snapshot = extractor.get_full_briefing()

    # Resolve ally IDs to names
    ally_ids = snapshot.get('diplomacy', {}).get('allies', [])
    ally_names = []
    for aid in ally_ids:
        name = get_empire_name_by_id(extractor, aid)
        ally_names.append({"id": aid, "name": name})

    # Update diplomacy with resolved names
    if 'diplomacy' in snapshot:
        snapshot['diplomacy']['allies_resolved'] = ally_names

    # Add current research (even if empty, be explicit)
    tech = extractor.get_technology()
    snapshot['current_research'] = tech.get('current_research', {})
    if not snapshot['current_research']:
        snapshot['current_research'] = "None - research slots are idle"

    return snapshot


def build_enhanced_system_prompt(identity: dict, situation: dict) -> str:
    """Enhanced prompt with stronger tool instructions."""

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

    prompt = f"""You are the strategic advisor to {empire_name}.

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

    return prompt


def run_current_version(question: str) -> tuple[str, float, int, list]:
    """Run the current production version."""
    from core.companion import Companion
    companion = Companion(save_path="test_save.sav")
    companion.clear_conversation()
    response, elapsed = companion.ask_simple(question)
    stats = companion.get_call_stats()
    return response, elapsed, stats.get('total_calls', 0), stats.get('tools_used', [])


def run_enhanced_version(extractor, client, identity, situation, question: str) -> tuple[str, float, int, list]:
    """Run enhanced version with better snapshot and stronger tool instructions."""

    system_prompt = build_enhanced_system_prompt(identity, situation)

    # Use enhanced snapshot
    snapshot_data = build_enhanced_snapshot(extractor)
    snapshot_json = json.dumps(snapshot_data, separators=(",", ":"), default=str)
    user_prompt = f"GAME STATE:\n```json\n{snapshot_json}\n```\n\n{question}"

    tools_used = []

    def get_details(categories: list[str], limit: int = 50) -> dict:
        """Get detailed data for specific categories."""
        tools_used.append(f"get_details({categories})")
        results = {}
        for cat in categories[:5]:
            method = getattr(extractor, f"get_{cat}", None)
            if method:
                results[cat] = method()
        return results

    def search_save_file(query: str, limit: int = 20) -> dict:
        """Search raw save file."""
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

    return response.text, elapsed, len(tools_used), tools_used


def main():
    print("=" * 80)
    print("ENHANCED SNAPSHOT + STRONGER TOOL INSTRUCTIONS TEST")
    print("=" * 80)

    extractor = SaveExtractor("test_save.sav")
    client = genai.Client()

    identity = extractor.get_empire_identity()
    situation = extractor.get_situation()

    # Show what we enhanced
    print("\n=== ENHANCED SNAPSHOT ADDITIONS ===")
    enhanced = build_enhanced_snapshot(extractor)
    print(f"Allies resolved: {enhanced['diplomacy'].get('allies_resolved', [])}")
    print(f"Current research: {enhanced.get('current_research', 'N/A')}")
    print()

    results = []

    for i, question in enumerate(TEST_QUESTIONS, 1):
        print("=" * 80)
        print(f"Q{i}: {question}")
        print("=" * 80)

        # Run current version
        print("\n--- CURRENT (Production) ---")
        try:
            curr_response, curr_time, curr_tools, curr_tools_list = run_current_version(question)
            print(f"Time: {curr_time:.1f}s | Tools: {curr_tools} {curr_tools_list}")
            print(f"Response ({len(curr_response.split())} words): {curr_response[:350]}...")
        except Exception as e:
            print(f"ERROR: {e}")
            curr_response, curr_time, curr_tools, curr_tools_list = str(e), 0, 0, []

        # Run enhanced version
        print("\n--- ENHANCED (Better snapshot + tool instructions) ---")
        try:
            enh_response, enh_time, enh_tools, enh_tools_list = run_enhanced_version(
                extractor, client, identity, situation, question
            )
            print(f"Time: {enh_time:.1f}s | Tools: {enh_tools} {enh_tools_list}")
            print(f"Response ({len(enh_response.split())} words): {enh_response[:350]}...")
        except Exception as e:
            print(f"ERROR: {e}")
            enh_response, enh_time, enh_tools, enh_tools_list = str(e), 0, 0, []

        results.append({
            "question": question,
            "current": {
                "time": curr_time,
                "tools": curr_tools,
                "tools_list": curr_tools_list,
                "response": curr_response,
                "words": len(curr_response.split()),
            },
            "enhanced": {
                "time": enh_time,
                "tools": enh_tools,
                "tools_list": enh_tools_list,
                "response": enh_response,
                "words": len(enh_response.split()),
            }
        })
        print()

    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"{'Question':<42} {'Curr':>7} {'Enh':>7} {'C.Tools':>7} {'E.Tools':>7} {'C.Words':>7} {'E.Words':>7}")
    print("-" * 80)

    for r in results:
        q = r['question'][:40]
        ct = f"{r['current']['time']:.1f}s" if r['current']['time'] else "ERR"
        et = f"{r['enhanced']['time']:.1f}s" if r['enhanced']['time'] else "ERR"
        print(f"{q:<42} {ct:>7} {et:>7} {r['current']['tools']:>7} {r['enhanced']['tools']:>7} {r['current']['words']:>7} {r['enhanced']['words']:>7}")

    # Averages
    valid = [r for r in results if r['current']['time'] and r['enhanced']['time']]
    if valid:
        avg_ct = sum(r['current']['time'] for r in valid) / len(valid)
        avg_et = sum(r['enhanced']['time'] for r in valid) / len(valid)
        avg_c_tools = sum(r['current']['tools'] for r in valid) / len(valid)
        avg_e_tools = sum(r['enhanced']['tools'] for r in valid) / len(valid)

        print("-" * 80)
        print(f"{'AVERAGE':<42} {avg_ct:>6.1f}s {avg_et:>6.1f}s {avg_c_tools:>7.1f} {avg_e_tools:>7.1f}")

        if avg_ct > avg_et:
            print(f"\nEnhanced is {((avg_ct - avg_et) / avg_ct * 100):.0f}% faster")

    # Tool usage breakdown
    print("\n" + "=" * 80)
    print("TOOL USAGE COMPARISON")
    print("=" * 80)

    print("\nCurrent:")
    for r in results:
        print(f"  {r['question'][:45]}: {r['current']['tools']} tools {r['current']['tools_list']}")

    print("\nEnhanced:")
    for r in results:
        print(f"  {r['question'][:45]}: {r['enhanced']['tools']} tools {r['enhanced']['tools_list']}")

    # Save results
    Path("enhanced_results.json").write_text(json.dumps(results, indent=2, default=str))
    print("\nResults saved to enhanced_results.json")


if __name__ == "__main__":
    main()
