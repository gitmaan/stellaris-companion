#!/usr/bin/env python3
"""
Test: Current vs Middle Ground Prompt
=====================================

Middle ground: Keep personality depth, trim tool instruction redundancy.
"""

import json
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

TEST_QUESTIONS = [
    "What is my current military power?",
    "How many colonies do I have?",
    "What is the state of my economy?",
    "Give me a brief strategic assessment.",
]


def build_middle_ground_system_prompt(identity: dict, situation: dict) -> str:
    """Middle ground: Full personality guidance, minimal tool redundancy."""

    empire_name = identity.get("empire_name", "the Empire")
    ethics = identity.get("ethics", [])
    authority = identity.get("authority", "unknown")
    civics = identity.get("civics", [])
    is_gestalt = identity.get("is_gestalt", False)
    is_machine = identity.get("is_machine", False)

    year = situation.get("year", 2200)
    game_phase = situation.get("game_phase", "early")
    at_war = situation.get("at_war", False)
    war_count = situation.get("war_count", 0)
    economy = situation.get("economy", {})
    deficits = economy.get("resources_in_deficit", 0)
    contact_count = situation.get("contact_count", 0)

    # Keep full personality section but streamline
    prompt = f"""You are the strategic advisor to {empire_name}.

EMPIRE IDENTITY:
- Ethics: {", ".join(ethics) if ethics else "unknown"}
- Authority: {authority}
- Civics: {", ".join(civics) if civics else "none"}
- Gestalt: {is_gestalt} (Machine: {is_machine})

SITUATION: Year {year} ({game_phase}), {"AT WAR" if at_war else "at peace"}, {deficits} deficits, {contact_count} known empires.

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

    return prompt


def build_middle_ground_user_prompt(snapshot_json: str, question: str) -> str:
    """Simplified user prompt - no redundant rules."""
    return f"GAME STATE:\n```json\n{snapshot_json}\n```\n\n{question}"


def run_current_version(question: str) -> tuple[str, float, int]:
    """Run the current production version."""
    from core.companion import Companion

    companion = Companion(save_path="test_save.sav")
    companion.clear_conversation()
    response, elapsed = companion.ask_simple(question)
    stats = companion.get_call_stats()
    return response, elapsed, stats.get("total_calls", 0)


def run_middle_ground(
    extractor, client, identity, situation, question: str
) -> tuple[str, float, int]:
    """Run the middle ground version."""

    system_prompt = build_middle_ground_system_prompt(identity, situation)

    snapshot_data = extractor.get_full_briefing()
    snapshot_json = json.dumps(snapshot_data, separators=(",", ":"), default=str)
    user_prompt = build_middle_ground_user_prompt(snapshot_json, question)

    def get_details(categories: list[str], limit: int = 50) -> dict:
        """Get detailed data for specific categories."""
        results = {}
        for cat in categories[:5]:
            method = getattr(extractor, f"get_{cat}", None)
            if method:
                results[cat] = method()
        return results

    def search_save_file(query: str, limit: int = 20) -> dict:
        """Search raw save file."""
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

    tool_calls = 0
    if hasattr(response, "automatic_function_calling_history"):
        for item in response.automatic_function_calling_history:
            if hasattr(item, "parts"):
                tool_calls += sum(1 for p in item.parts if hasattr(p, "function_call"))

    return response.text, elapsed, tool_calls


def main():
    print("=" * 70)
    print("MIDDLE GROUND COMPARISON TEST")
    print("=" * 70)

    extractor = SaveExtractor("test_save.sav")
    client = genai.Client()

    identity = extractor.get_empire_identity()
    situation = extractor.get_situation()

    print(f"Empire: {identity.get('empire_name')}")
    print(f"Ethics: {identity.get('ethics')}")
    print()

    # Show the middle ground prompt
    print("=" * 70)
    print("MIDDLE GROUND SYSTEM PROMPT:")
    print("=" * 70)
    mg_prompt = build_middle_ground_system_prompt(identity, situation)
    print(mg_prompt)
    print()
    print(f"[Middle ground prompt: {len(mg_prompt)} chars]")

    # For comparison, show current prompt size
    from core.companion import Companion

    temp_companion = Companion(save_path="test_save.sav")
    print(f"[Current production prompt: {len(temp_companion.system_prompt)} chars]")
    print()

    results = []

    for i, question in enumerate(TEST_QUESTIONS, 1):
        print("=" * 70)
        print(f"Q{i}: {question}")
        print("=" * 70)

        # Run current version
        print("\n--- CURRENT (Production) ---")
        curr_response, curr_time, curr_tools = run_current_version(question)
        print(f"Time: {curr_time:.1f}s | Tools: {curr_tools} | Words: {len(curr_response.split())}")
        print(f"Response:\n{curr_response[:500]}...")

        # Run middle ground
        print("\n--- MIDDLE GROUND ---")
        mg_response, mg_time, mg_tools = run_middle_ground(
            extractor, client, identity, situation, question
        )
        print(f"Time: {mg_time:.1f}s | Tools: {mg_tools} | Words: {len(mg_response.split())}")
        print(f"Response:\n{mg_response[:500]}...")

        results.append(
            {
                "question": question,
                "current": {
                    "time": curr_time,
                    "tools": curr_tools,
                    "response": curr_response,
                    "word_count": len(curr_response.split()),
                },
                "middle_ground": {
                    "time": mg_time,
                    "tools": mg_tools,
                    "response": mg_response,
                    "word_count": len(mg_response.split()),
                },
            }
        )

        print()

    # Summary table
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"{'Question':<35} {'Curr':>8} {'MG':>8} {'Curr':>6} {'MG':>6} {'Curr':>6} {'MG':>6}")
    print(f"{'':35} {'Time':>8} {'Time':>8} {'Tools':>6} {'Tools':>6} {'Words':>6} {'Words':>6}")
    print("-" * 70)

    for r in results:
        q = r["question"][:33]
        print(
            f"{q:<35} {r['current']['time']:>7.1f}s {r['middle_ground']['time']:>7.1f}s "
            f"{r['current']['tools']:>6} {r['middle_ground']['tools']:>6} "
            f"{r['current']['word_count']:>6} {r['middle_ground']['word_count']:>6}"
        )

    # Averages
    avg_curr_time = sum(r["current"]["time"] for r in results) / len(results)
    avg_mg_time = sum(r["middle_ground"]["time"] for r in results) / len(results)
    avg_curr_tools = sum(r["current"]["tools"] for r in results) / len(results)
    avg_mg_tools = sum(r["middle_ground"]["tools"] for r in results) / len(results)
    avg_curr_words = sum(r["current"]["word_count"] for r in results) / len(results)
    avg_mg_words = sum(r["middle_ground"]["word_count"] for r in results) / len(results)

    print("-" * 70)
    print(
        f"{'AVERAGE':<35} {avg_curr_time:>7.1f}s {avg_mg_time:>7.1f}s "
        f"{avg_curr_tools:>6.1f} {avg_mg_tools:>6.1f} "
        f"{avg_curr_words:>6.0f} {avg_mg_words:>6.0f}"
    )

    speedup = (avg_curr_time - avg_mg_time) / avg_curr_time * 100
    print(
        f"\nMiddle ground is {speedup:.0f}% faster"
        if speedup > 0
        else f"\nCurrent is {-speedup:.0f}% faster"
    )

    # Save results
    Path("middle_ground_results.json").write_text(
        json.dumps(
            {
                "summary": {
                    "current_avg_time": avg_curr_time,
                    "mg_avg_time": avg_mg_time,
                    "current_avg_tools": avg_curr_tools,
                    "mg_avg_tools": avg_mg_tools,
                    "current_avg_words": avg_curr_words,
                    "mg_avg_words": avg_mg_words,
                },
                "results": results,
            },
            indent=2,
            default=str,
        )
    )
    print("\nDetailed results saved to middle_ground_results.json")


if __name__ == "__main__":
    main()
