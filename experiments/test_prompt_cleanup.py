#!/usr/bin/env python3
"""
Test: Current vs Cleaned-up Prompt
==================================

Compares the current verbose prompt against a streamlined version.
"""

import json
import sys
import time
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from google import genai
from google.genai import types

from personality import get_personality_summary
from save_extractor import SaveExtractor

# Test questions
TEST_QUESTIONS = [
    "What is my current military power?",
    "How many colonies do I have?",
    "What is the state of my economy?",
    "Give me a brief strategic assessment.",
]


def build_clean_system_prompt(identity: dict, situation: dict) -> str:
    """Build a cleaner, less redundant system prompt."""

    empire_name = identity.get("empire_name", "the Empire")
    ethics = identity.get("ethics", [])
    authority = identity.get("authority", "unknown")
    civics = identity.get("civics", [])

    year = situation.get("year", 2200)
    game_phase = situation.get("game_phase", "early")
    at_war = situation.get("at_war", False)
    economy = situation.get("economy", {})
    deficits = economy.get("resources_in_deficit", 0)

    # Build concise prompt
    prompt = f"""You are the strategic advisor to {empire_name}.

YOUR PERSONALITY:
You embody {", ".join(ethics)} values with {authority} governance.
Civics: {", ".join(civics) if civics else "none"}.
Address the ruler as "President" (democratic authority). Be collegial, passionate about liberty and citizen welfare.

CURRENT SITUATION: Year {year} ({game_phase} game), {"AT WAR" if at_war else "at peace"}, {deficits} resource deficits.

RULES:
1. All facts and numbers MUST come from the provided game state data - never guess.
2. Stay fully in character with colorful, passionate language befitting your ethics.
3. You have drill-down tools (get_details, search_save_file) if the provided data lacks something specific."""

    return prompt


def build_clean_user_prompt(snapshot_json: str, question: str) -> str:
    """Build a cleaner user prompt without redundant rules."""

    return f"GAME STATE:\n```json\n{snapshot_json}\n```\n\nQUESTION: {question}"


def run_current_version(extractor, client, question: str) -> tuple[str, float, int]:
    """Run the current verbose version."""

    from core.companion import Companion

    companion = Companion(save_path="test_save.sav")
    companion.clear_conversation()

    response, elapsed = companion.ask_simple(question)
    stats = companion.get_call_stats()

    return response, elapsed, stats.get("total_calls", 0)


def run_clean_version(
    extractor, client, identity, situation, question: str
) -> tuple[str, float, int]:
    """Run the cleaned-up version."""

    # Build clean prompts
    system_prompt = build_clean_system_prompt(identity, situation)

    snapshot_data = extractor.get_full_briefing()
    snapshot_json = json.dumps(snapshot_data, separators=(",", ":"), default=str)
    user_prompt = build_clean_user_prompt(snapshot_json, question)

    # Create tools (same as ask_simple)
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

    # Count tool calls from response
    tool_calls = 0
    if hasattr(response, "automatic_function_calling_history"):
        for item in response.automatic_function_calling_history:
            if hasattr(item, "parts"):
                tool_calls += sum(1 for p in item.parts if hasattr(p, "function_call"))

    return response.text, elapsed, tool_calls


def main():
    print("=" * 70)
    print("PROMPT CLEANUP COMPARISON TEST")
    print("=" * 70)

    # Initialize
    extractor = SaveExtractor("test_save.sav")
    client = genai.Client()

    identity = extractor.get_empire_identity()
    situation = extractor.get_situation()

    print(f"Empire: {identity.get('empire_name')}")
    print(f"Ethics: {identity.get('ethics')}")
    print()

    # Show prompt comparison
    print("=" * 70)
    print("CLEAN SYSTEM PROMPT:")
    print("=" * 70)
    print(build_clean_system_prompt(identity, situation))
    print()

    results = []

    for i, question in enumerate(TEST_QUESTIONS, 1):
        print("=" * 70)
        print(f"Q{i}: {question}")
        print("=" * 70)

        # Run current version
        print("\n--- CURRENT VERSION ---")
        curr_response, curr_time, curr_tools = run_current_version(extractor, client, question)
        print(f"Time: {curr_time:.1f}s | Tools: {curr_tools}")
        print(f"Response preview: {curr_response[:300]}...")

        # Run clean version
        print("\n--- CLEAN VERSION ---")
        clean_response, clean_time, clean_tools = run_clean_version(
            extractor, client, identity, situation, question
        )
        print(f"Time: {clean_time:.1f}s | Tools: {clean_tools}")
        print(f"Response preview: {clean_response[:300]}...")

        results.append(
            {
                "question": question,
                "current": {
                    "time": curr_time,
                    "tools": curr_tools,
                    "response": curr_response,
                    "word_count": len(curr_response.split()),
                },
                "clean": {
                    "time": clean_time,
                    "tools": clean_tools,
                    "response": clean_response,
                    "word_count": len(clean_response.split()),
                },
            }
        )

        print()

    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(
        f"{'Question':<40} {'Curr Time':>10} {'Clean Time':>10} {'Curr Tools':>10} {'Clean Tools':>10}"
    )
    print("-" * 70)

    for r in results:
        q = r["question"][:38]
        print(
            f"{q:<40} {r['current']['time']:>9.1f}s {r['clean']['time']:>9.1f}s {r['current']['tools']:>10} {r['clean']['tools']:>10}"
        )

    # Averages
    avg_curr_time = sum(r["current"]["time"] for r in results) / len(results)
    avg_clean_time = sum(r["clean"]["time"] for r in results) / len(results)
    avg_curr_tools = sum(r["current"]["tools"] for r in results) / len(results)
    avg_clean_tools = sum(r["clean"]["tools"] for r in results) / len(results)

    print("-" * 70)
    print(
        f"{'AVERAGE':<40} {avg_curr_time:>9.1f}s {avg_clean_time:>9.1f}s {avg_curr_tools:>10.1f} {avg_clean_tools:>10.1f}"
    )

    # Save detailed results
    output = {
        "summary": {
            "current_avg_time": avg_curr_time,
            "clean_avg_time": avg_clean_time,
            "current_avg_tools": avg_curr_tools,
            "clean_avg_tools": avg_clean_tools,
        },
        "results": results,
    }

    Path("prompt_cleanup_results.json").write_text(json.dumps(output, indent=2, default=str))
    print("\nDetailed results saved to prompt_cleanup_results.json")


if __name__ == "__main__":
    main()
