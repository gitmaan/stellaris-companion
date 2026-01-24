#!/usr/bin/env python3
"""
Test: Tool Usage Comparison
===========================

Tests queries that may require tool usage to see how both versions handle them.
"""

import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

sys.path.insert(0, str(Path(__file__).parent / "backend"))

from google import genai
from google.genai import types
from save_extractor import SaveExtractor

# Mix of simple and complex queries - some should need tools
TEST_QUESTIONS = [
    # Simple (snapshot should suffice)
    "What is my current military power?",
    "How many colonies do I have?",

    # Medium (might need details)
    "What is the state of my economy?",
    "Who are my allies?",

    # Complex (likely needs tools/search)
    "Tell me about my best admiral or general.",
    "What technologies am I currently researching?",
    "What are my relationships with neighboring empires?",
    "Tell me about my starbases and their locations.",
    "Who are my scientists and what are they working on?",
    "What species make up my empire's population?",
]


def build_middle_ground_system_prompt(identity: dict, situation: dict) -> str:
    """Middle ground v2: personality + strategic depth, minimal redundancy."""

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

The game state is pre-loaded in the user message. If you need MORE DETAIL not in the snapshot (e.g., specific leader traits, detailed diplomacy, tech details), use the available tools."""

    return prompt


def run_current_version(question: str) -> tuple[str, float, int, list]:
    """Run the current production version."""
    from core.companion import Companion
    companion = Companion(save_path="test_save.sav")
    companion.clear_conversation()
    response, elapsed = companion.ask_simple(question)
    stats = companion.get_call_stats()
    return response, elapsed, stats.get('total_calls', 0), stats.get('tools_used', [])


def run_middle_ground(extractor, client, identity, situation, question: str) -> tuple[str, float, int, list]:
    """Run the middle ground version."""

    system_prompt = build_middle_ground_system_prompt(identity, situation)

    snapshot_data = extractor.get_full_briefing()
    snapshot_json = json.dumps(snapshot_data, separators=(",", ":"), default=str)
    user_prompt = f"GAME STATE:\n```json\n{snapshot_json}\n```\n\n{question}"

    # Track tool calls
    tools_used = []

    def get_details(categories: list[str], limit: int = 50) -> dict:
        """Get detailed data for specific categories like 'leaders', 'diplomacy', 'technology'."""
        tools_used.append(f"get_details({categories})")
        results = {}
        for cat in categories[:5]:
            method = getattr(extractor, f"get_{cat}", None)
            if method:
                results[cat] = method()
        return results

    def search_save_file(query: str, limit: int = 20) -> dict:
        """Search raw save file for specific terms."""
        tools_used.append(f"search_save_file({query})")
        return extractor.search(query, limit)

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
    print("TOOL USAGE COMPARISON TEST")
    print("=" * 80)

    extractor = SaveExtractor("test_save.sav")
    client = genai.Client()

    identity = extractor.get_empire_identity()
    situation = extractor.get_situation()

    print(f"Empire: {identity.get('empire_name')}")
    print(f"Testing {len(TEST_QUESTIONS)} questions...")
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
            print(f"Response ({len(curr_response.split())} words): {curr_response[:300]}...")
        except Exception as e:
            print(f"ERROR: {e}")
            curr_response, curr_time, curr_tools, curr_tools_list = f"Error: {e}", 0, 0, []

        # Run middle ground
        print("\n--- MIDDLE GROUND v2 ---")
        try:
            mg_response, mg_time, mg_tools, mg_tools_list = run_middle_ground(
                extractor, client, identity, situation, question
            )
            print(f"Time: {mg_time:.1f}s | Tools: {mg_tools} {mg_tools_list}")
            print(f"Response ({len(mg_response.split())} words): {mg_response[:300]}...")
        except Exception as e:
            print(f"ERROR: {e}")
            mg_response, mg_time, mg_tools, mg_tools_list = f"Error: {e}", 0, 0, []

        results.append({
            "question": question,
            "current": {
                "time": curr_time,
                "tools": curr_tools,
                "tools_list": curr_tools_list,
                "response": curr_response,
                "word_count": len(curr_response.split()),
            },
            "middle_ground": {
                "time": mg_time,
                "tools": mg_tools,
                "tools_list": mg_tools_list,
                "response": mg_response,
                "word_count": len(mg_response.split()),
            }
        })

        print()

    # Summary table
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"{'Question':<45} {'Curr':>6} {'MG':>6} {'Curr':>8} {'MG':>8}")
    print(f"{'':45} {'Time':>6} {'Time':>6} {'Tools':>8} {'Tools':>8}")
    print("-" * 80)

    for r in results:
        q = r['question'][:43]
        ct = f"{r['current']['time']:.1f}s" if r['current']['time'] > 0 else "ERR"
        mt = f"{r['middle_ground']['time']:.1f}s" if r['middle_ground']['time'] > 0 else "ERR"
        print(f"{q:<45} {ct:>6} {mt:>6} {r['current']['tools']:>8} {r['middle_ground']['tools']:>8}")

    # Averages
    valid_curr = [r for r in results if r['current']['time'] > 0]
    valid_mg = [r for r in results if r['middle_ground']['time'] > 0]

    if valid_curr and valid_mg:
        avg_curr_time = sum(r['current']['time'] for r in valid_curr) / len(valid_curr)
        avg_mg_time = sum(r['middle_ground']['time'] for r in valid_mg) / len(valid_mg)
        avg_curr_tools = sum(r['current']['tools'] for r in valid_curr) / len(valid_curr)
        avg_mg_tools = sum(r['middle_ground']['tools'] for r in valid_mg) / len(valid_mg)

        print("-" * 80)
        print(f"{'AVERAGE':<45} {avg_curr_time:>5.1f}s {avg_mg_time:>5.1f}s {avg_curr_tools:>8.1f} {avg_mg_tools:>8.1f}")

        # Tool usage breakdown
        print("\n" + "=" * 80)
        print("TOOL USAGE BREAKDOWN")
        print("=" * 80)

        print("\nCurrent (Production):")
        for r in results:
            if r['current']['tools'] > 0:
                print(f"  Q: {r['question'][:50]}")
                print(f"     Tools: {r['current']['tools_list']}")

        print("\nMiddle Ground v2:")
        for r in results:
            if r['middle_ground']['tools'] > 0:
                print(f"  Q: {r['question'][:50]}")
                print(f"     Tools: {r['middle_ground']['tools_list']}")

    # Save results
    Path("tool_usage_results.json").write_text(json.dumps({
        "results": results,
    }, indent=2, default=str))
    print("\nDetailed results saved to tool_usage_results.json")


if __name__ == "__main__":
    main()
