#!/usr/bin/env python3
"""
T2 vs T2.5 LLM Comparison Test

Actually runs questions through both approaches and compares:
1. Response quality
2. Tool calls made
3. Latency
4. Token usage (estimated)

Usage:
    python test_t25_llm_comparison.py [--quick]
"""

import json
import os
import sys
import time
from pathlib import Path
from dataclasses import dataclass, field

sys.path.insert(0, str(Path(__file__).parent.parent))

from save_loader import find_most_recent_save
from backend.core.companion import Companion

# Test questions - mix of simple and complex
TEST_QUESTIONS = [
    # Simple - should NOT need tool calls
    ("What is my current military power?", "simple"),
    ("How much energy am I making per month?", "simple"),
    ("What year is it?", "simple"),
    ("Who is my ruler?", "simple"),

    # Detail - SHOULD need tool calls (in T2.5)
    ("What traits does my ruler have?", "detail"),  # Actually in slim!
    ("List my top 3 admirals by level", "detail"),
    ("What are the specific opinion modifiers with my closest ally?", "detail"),
]

QUICK_QUESTIONS = TEST_QUESTIONS[:3]  # Just first 3 for quick test


@dataclass
class TestResult:
    question: str
    category: str
    approach: str  # "t2_full" or "t25_slim"
    response: str
    elapsed_ms: float
    tool_calls: int
    tools_used: list[str]
    input_tokens_estimate: int
    success: bool
    error: str = ""


def estimate_tokens(text: str) -> int:
    """Rough token estimate (4 chars per token)."""
    return len(text) // 4


def run_t2_full(companion: Companion, question: str) -> TestResult:
    """Run question with T2 full briefing injection (ask_precomputed)."""
    start = time.time()
    try:
        response, elapsed = companion.ask_precomputed(question, session_key="t2_test")
        stats = companion.get_call_stats()

        # Estimate input tokens from briefing size
        briefing_size = stats.get("payload_sizes", {}).get("briefing_json", 0)

        return TestResult(
            question=question,
            category="",
            approach="t2_full",
            response=response[:500] + "..." if len(response) > 500 else response,
            elapsed_ms=elapsed * 1000,
            tool_calls=0,  # T2 doesn't use tools
            tools_used=[],
            input_tokens_estimate=estimate_tokens(str(briefing_size)),
            success=True,
        )
    except Exception as e:
        return TestResult(
            question=question,
            category="",
            approach="t2_full",
            response="",
            elapsed_ms=(time.time() - start) * 1000,
            tool_calls=0,
            tools_used=[],
            input_tokens_estimate=0,
            success=False,
            error=str(e),
        )


def run_t25_slim(companion: Companion, question: str) -> TestResult:
    """Run question with T2.5 slim briefing + tools (ask_simple)."""
    start = time.time()
    try:
        # Clear chat session to start fresh
        companion._chat_session = None

        response, elapsed = companion.ask_simple(question)
        stats = companion.get_call_stats()

        return TestResult(
            question=question,
            category="",
            approach="t25_slim",
            response=response[:500] + "..." if len(response) > 500 else response,
            elapsed_ms=elapsed * 1000,
            tool_calls=stats.get("total_calls", 0),
            tools_used=stats.get("tools_used", []),
            input_tokens_estimate=sum(stats.get("payload_sizes", {}).values()) // 4,
            success=True,
        )
    except Exception as e:
        return TestResult(
            question=question,
            category="",
            approach="t25_slim",
            response="",
            elapsed_ms=(time.time() - start) * 1000,
            tool_calls=0,
            tools_used=[],
            input_tokens_estimate=0,
            success=False,
            error=str(e),
        )


def print_comparison(t2_result: TestResult, t25_result: TestResult):
    """Print side-by-side comparison."""
    print(f"\n{'='*70}")
    print(f"Q: {t2_result.question}")
    print(f"{'='*70}")

    print(f"\n  {'T2 (Full Briefing)':<30} | {'T2.5 (Slim + Tools)':<30}")
    print(f"  {'-'*30} | {'-'*30}")
    print(f"  Latency: {t2_result.elapsed_ms:>6.0f}ms          | Latency: {t25_result.elapsed_ms:>6.0f}ms")
    print(f"  Tool calls: {t2_result.tool_calls:<3}              | Tool calls: {t25_result.tool_calls:<3}")
    print(f"  Tools: {t2_result.tools_used or 'none':<20} | Tools: {t25_result.tools_used or 'none'}")

    # Verdict
    faster = "T2" if t2_result.elapsed_ms < t25_result.elapsed_ms else "T2.5"
    latency_diff = abs(t2_result.elapsed_ms - t25_result.elapsed_ms)

    print(f"\n  Winner: {faster} (by {latency_diff:.0f}ms)")

    if t25_result.tool_calls == 0:
        print(f"  ✓ T2.5 answered WITHOUT tool calls (good for simple questions)")
    else:
        print(f"  → T2.5 used {t25_result.tool_calls} tool call(s): {t25_result.tools_used}")

    print(f"\n  T2 Response preview:")
    print(f"    {t2_result.response[:200]}...")
    print(f"\n  T2.5 Response preview:")
    print(f"    {t25_result.response[:200]}...")


def main():
    quick_mode = "--quick" in sys.argv

    # Check for API key
    if not os.environ.get("GOOGLE_API_KEY"):
        print("Error: GOOGLE_API_KEY not set")
        print("Run: export GOOGLE_API_KEY=your_key")
        return 1

    # Find save
    save_path = find_most_recent_save()
    if not save_path:
        print("No save file found")
        return 1

    print(f"Save: {save_path.name}")
    print(f"Mode: {'Quick (3 questions)' if quick_mode else 'Full (7 questions)'}")

    # Initialize companion
    print("\nInitializing companion...")
    companion = Companion(save_path=save_path)

    # Wait for precompute to finish
    print("Waiting for briefing precompute...")
    companion._briefing_ready.wait(timeout=30)

    questions = QUICK_QUESTIONS if quick_mode else TEST_QUESTIONS

    results = []

    for question, category in questions:
        print(f"\n\nTesting: {question[:50]}...")

        # Run T2 (full briefing)
        print("  Running T2 (full briefing)...")
        t2_result = run_t2_full(companion, question)
        t2_result.category = category

        # Small delay to avoid rate limiting
        time.sleep(1)

        # Run T2.5 (slim + tools)
        print("  Running T2.5 (slim + tools)...")
        t25_result = run_t25_slim(companion, question)
        t25_result.category = category

        results.append((t2_result, t25_result))

        # Print comparison
        print_comparison(t2_result, t25_result)

        time.sleep(1)

    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)

    t2_total_ms = sum(r[0].elapsed_ms for r in results)
    t25_total_ms = sum(r[1].elapsed_ms for r in results)
    t25_tool_calls = sum(r[1].tool_calls for r in results)
    t25_zero_tool_questions = sum(1 for r in results if r[1].tool_calls == 0)

    print(f"\nTotal latency:")
    print(f"  T2 (full):  {t2_total_ms:,.0f}ms")
    print(f"  T2.5 (slim): {t25_total_ms:,.0f}ms")
    print(f"  Difference: {t2_total_ms - t25_total_ms:+,.0f}ms")

    print(f"\nT2.5 tool usage:")
    print(f"  Questions with 0 tool calls: {t25_zero_tool_questions}/{len(results)}")
    print(f"  Total tool calls: {t25_tool_calls}")

    simple_qs = [r for r in results if r[0].category == "simple"]
    simple_no_tools = sum(1 for r in simple_qs if r[1].tool_calls == 0)
    print(f"\nSimple questions answered without tools: {simple_no_tools}/{len(simple_qs)}")

    if t25_total_ms < t2_total_ms and t25_zero_tool_questions >= len(simple_qs) * 0.8:
        print("\n✓ T2.5 RECOMMENDED")
        print("  - Faster overall")
        print("  - Simple questions don't trigger unnecessary tools")
    else:
        print("\n? T2.5 NEEDS TUNING")
        if t25_total_ms >= t2_total_ms:
            print("  - Not faster (tool overhead?)")
        if t25_zero_tool_questions < len(simple_qs) * 0.8:
            print("  - Too many tool calls for simple questions")

    # Save results
    output = {
        "summary": {
            "t2_total_ms": t2_total_ms,
            "t25_total_ms": t25_total_ms,
            "t25_tool_calls": t25_tool_calls,
            "t25_zero_tool_questions": t25_zero_tool_questions,
        },
        "results": [
            {
                "question": r[0].question,
                "category": r[0].category,
                "t2": {
                    "elapsed_ms": r[0].elapsed_ms,
                    "tool_calls": r[0].tool_calls,
                    "response_preview": r[0].response[:200],
                },
                "t25": {
                    "elapsed_ms": r[1].elapsed_ms,
                    "tool_calls": r[1].tool_calls,
                    "tools_used": r[1].tools_used,
                    "response_preview": r[1].response[:200],
                },
            }
            for r in results
        ],
    }

    with open("t25_llm_comparison_results.json", "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to: t25_llm_comparison_results.json")

    return 0


if __name__ == "__main__":
    sys.exit(main())
