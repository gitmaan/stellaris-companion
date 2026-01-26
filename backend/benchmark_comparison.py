#!/usr/bin/env python3
"""
Benchmark Comparison: Old vs New Approach
==========================================

Compares:
- OLD: chat() with consolidated tools (model calls tools as needed)
- NEW: ask_simple() with pre-injected snapshot + drill-down tools

Measures: response time, tool calls, response length, quality
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

# Load environment variables from .env
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

# Add project paths
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from core.companion import Companion

# Test questions covering different aspects
TEST_QUESTIONS = [
    # Simple factual questions (should be answerable from snapshot)
    "What is my current military power?",
    "How much energy am I producing per month?",
    "How many colonies do I have?",
    # Medium complexity (may need some context)
    "What is the state of my economy? Am I in deficit anywhere?",
    "Who are my allies and rivals?",
    "What technologies am I currently researching?",
    # Complex strategic questions
    "Give me a brief strategic assessment of my empire's current situation.",
    "Should I be worried about any neighboring empires?",
    "What are my top 3 priorities right now?",
]


def run_test(companion: Companion, question: str, method: str) -> dict:
    """Run a single test and return metrics."""

    # Clear conversation for clean test
    companion.clear_conversation()

    time.time()

    if method == "old":
        # OLD approach: chat() with tools, model decides what to call
        response, elapsed = companion.chat(question)
    else:
        # NEW approach: ask_simple() with pre-injected snapshot
        response, elapsed = companion.ask_simple(question)

    stats = companion.get_call_stats()

    return {
        "question": question,
        "method": method,
        "response": response,
        "response_length": len(response),
        "elapsed_seconds": elapsed,
        "tool_calls": stats.get("total_calls", 0),
        "tools_used": stats.get("tools_used", []),
        "payload_sizes": stats.get("payload_sizes", {}),
    }


def evaluate_quality(result: dict) -> dict:
    """Basic quality evaluation of a response."""
    response = result["response"]

    # Check for error indicators
    has_error = any(
        phrase in response.lower()
        for phrase in [
            "could not generate",
            "error",
            "i don't have",
            "unable to",
            "cannot determine",
        ]
    )

    # Check for numeric content (indicates factual grounding)
    import re

    numbers = re.findall(r"\d+(?:,\d{3})*(?:\.\d+)?", response)
    has_numbers = len(numbers) > 0

    # Check response completeness
    word_count = len(response.split())
    is_substantial = word_count > 30

    # Check for hedging language
    hedging_phrases = [
        "might be",
        "could be",
        "possibly",
        "perhaps",
        "i think",
        "i believe",
    ]
    hedging_count = sum(1 for phrase in hedging_phrases if phrase in response.lower())

    return {
        "has_error": has_error,
        "has_numbers": has_numbers,
        "word_count": word_count,
        "is_substantial": is_substantial,
        "hedging_count": hedging_count,
        "quality_score": (
            (0 if has_error else 2)
            + (1 if has_numbers else 0)
            + (1 if is_substantial else 0)
            + (1 if hedging_count < 2 else 0)
        ),  # Max score: 5
    }


def run_benchmark(save_path: str) -> dict:
    """Run full benchmark comparison."""

    print(f"Loading save file: {save_path}")
    companion = Companion(save_path=save_path)
    print(f"Loaded empire: {companion.metadata.get('name', 'Unknown')}")
    print(f"Game date: {companion.metadata.get('date', 'Unknown')}")
    print()

    results = {
        "metadata": {
            "save_file": str(save_path),
            "empire_name": companion.metadata.get("name"),
            "game_date": companion.metadata.get("date"),
            "timestamp": datetime.now().isoformat(),
        },
        "old_approach": [],
        "new_approach": [],
    }

    total_questions = len(TEST_QUESTIONS)

    # Run OLD approach tests
    print("=" * 60)
    print("TESTING OLD APPROACH (chat with tools)")
    print("=" * 60)

    for i, question in enumerate(TEST_QUESTIONS, 1):
        print(f"\n[{i}/{total_questions}] {question[:50]}...")
        result = run_test(companion, question, "old")
        result["quality"] = evaluate_quality(result)
        results["old_approach"].append(result)
        print(
            f"  Time: {result['elapsed_seconds']:.1f}s | Tools: {result['tool_calls']} | Words: {result['quality']['word_count']}"
        )

    # Run NEW approach tests
    print("\n" + "=" * 60)
    print("TESTING NEW APPROACH (ask_simple with pre-injected snapshot)")
    print("=" * 60)

    for i, question in enumerate(TEST_QUESTIONS, 1):
        print(f"\n[{i}/{total_questions}] {question[:50]}...")
        result = run_test(companion, question, "new")
        result["quality"] = evaluate_quality(result)
        results["new_approach"].append(result)
        print(
            f"  Time: {result['elapsed_seconds']:.1f}s | Tools: {result['tool_calls']} | Words: {result['quality']['word_count']}"
        )

    return results


def generate_markdown_report(results: dict) -> str:
    """Generate a detailed markdown report."""

    md = []
    md.append("# Benchmark Comparison: Old vs New Approach")
    md.append("")
    md.append(f"**Generated:** {results['metadata']['timestamp']}")
    md.append(f"**Empire:** {results['metadata']['empire_name']}")
    md.append(f"**Game Date:** {results['metadata']['game_date']}")
    md.append("")

    # Summary statistics
    old_times = [r["elapsed_seconds"] for r in results["old_approach"]]
    new_times = [r["elapsed_seconds"] for r in results["new_approach"]]
    old_tools = [r["tool_calls"] for r in results["old_approach"]]
    new_tools = [r["tool_calls"] for r in results["new_approach"]]
    old_quality = [r["quality"]["quality_score"] for r in results["old_approach"]]
    new_quality = [r["quality"]["quality_score"] for r in results["new_approach"]]

    md.append("## Summary")
    md.append("")
    md.append("| Metric | Old Approach | New Approach | Improvement |")
    md.append("|--------|--------------|--------------|-------------|")

    avg_old_time = sum(old_times) / len(old_times)
    avg_new_time = sum(new_times) / len(new_times)
    time_improvement = ((avg_old_time - avg_new_time) / avg_old_time) * 100
    md.append(
        f"| Avg Response Time | {avg_old_time:.1f}s | {avg_new_time:.1f}s | {time_improvement:+.0f}% |"
    )

    avg_old_tools = sum(old_tools) / len(old_tools)
    avg_new_tools = sum(new_tools) / len(new_tools)
    tool_reduction = ((avg_old_tools - avg_new_tools) / max(avg_old_tools, 0.1)) * 100
    md.append(
        f"| Avg Tool Calls | {avg_old_tools:.1f} | {avg_new_tools:.1f} | {tool_reduction:+.0f}% |"
    )

    avg_old_quality = sum(old_quality) / len(old_quality)
    avg_new_quality = sum(new_quality) / len(new_quality)
    quality_change = ((avg_new_quality - avg_old_quality) / max(avg_old_quality, 0.1)) * 100
    md.append(
        f"| Avg Quality Score | {avg_old_quality:.1f}/5 | {avg_new_quality:.1f}/5 | {quality_change:+.0f}% |"
    )

    total_old = sum(old_times)
    total_new = sum(new_times)
    md.append(
        f"| Total Time | {total_old:.0f}s | {total_new:.0f}s | {total_old - total_new:.0f}s saved |"
    )

    md.append("")

    # Detailed results per question
    md.append("## Detailed Results")
    md.append("")

    for i, question in enumerate(TEST_QUESTIONS):
        old = results["old_approach"][i]
        new = results["new_approach"][i]

        md.append(f"### Question {i + 1}: {question}")
        md.append("")
        md.append("| Metric | Old | New |")
        md.append("|--------|-----|-----|")
        md.append(
            f"| Response Time | {old['elapsed_seconds']:.1f}s | {new['elapsed_seconds']:.1f}s |"
        )
        md.append(f"| Tool Calls | {old['tool_calls']} | {new['tool_calls']} |")
        md.append(
            f"| Tools Used | {', '.join(old['tools_used']) or 'None'} | {', '.join(new['tools_used']) or 'None'} |"
        )
        md.append(
            f"| Word Count | {old['quality']['word_count']} | {new['quality']['word_count']} |"
        )
        md.append(
            f"| Quality Score | {old['quality']['quality_score']}/5 | {new['quality']['quality_score']}/5 |"
        )
        md.append("")

        md.append("**Old Response:**")
        md.append("```")
        md.append(old["response"][:500] + ("..." if len(old["response"]) > 500 else ""))
        md.append("```")
        md.append("")

        md.append("**New Response:**")
        md.append("```")
        md.append(new["response"][:500] + ("..." if len(new["response"]) > 500 else ""))
        md.append("```")
        md.append("")

    # Quality Analysis
    md.append("## Quality Analysis")
    md.append("")

    old_errors = sum(1 for r in results["old_approach"] if r["quality"]["has_error"])
    new_errors = sum(1 for r in results["new_approach"] if r["quality"]["has_error"])
    md.append(
        f"- **Error responses:** Old: {old_errors}/{len(TEST_QUESTIONS)}, New: {new_errors}/{len(TEST_QUESTIONS)}"
    )

    old_numbers = sum(1 for r in results["old_approach"] if r["quality"]["has_numbers"])
    new_numbers = sum(1 for r in results["new_approach"] if r["quality"]["has_numbers"])
    md.append(
        f"- **Responses with numbers:** Old: {old_numbers}/{len(TEST_QUESTIONS)}, New: {new_numbers}/{len(TEST_QUESTIONS)}"
    )

    old_substantial = sum(1 for r in results["old_approach"] if r["quality"]["is_substantial"])
    new_substantial = sum(1 for r in results["new_approach"] if r["quality"]["is_substantial"])
    md.append(
        f"- **Substantial responses (>30 words):** Old: {old_substantial}/{len(TEST_QUESTIONS)}, New: {new_substantial}/{len(TEST_QUESTIONS)}"
    )

    md.append("")

    # Conclusions
    md.append("## Conclusions")
    md.append("")

    if avg_new_time < avg_old_time:
        md.append(f"- **Speed:** New approach is {time_improvement:.0f}% faster on average")
    else:
        md.append(f"- **Speed:** Old approach was faster by {-time_improvement:.0f}%")

    if avg_new_tools < avg_old_tools:
        md.append(f"- **Efficiency:** New approach uses {tool_reduction:.0f}% fewer tool calls")

    if avg_new_quality >= avg_old_quality:
        md.append(
            f"- **Quality:** New approach maintains or improves quality ({avg_new_quality:.1f} vs {avg_old_quality:.1f})"
        )
    else:
        md.append(
            f"- **Quality:** Some quality regression ({avg_new_quality:.1f} vs {avg_old_quality:.1f}) - may need prompt tuning"
        )

    md.append("")

    return "\n".join(md)


def main():
    """Run the benchmark and save results."""

    # Default save path
    save_path = Path("/Users/avani/stellaris-companion/test_save.sav")

    if len(sys.argv) > 1:
        save_path = Path(sys.argv[1])

    if not save_path.exists():
        print(f"ERROR: Save file not found: {save_path}")
        return 1

    print("=" * 60)
    print("BENCHMARK: Old vs New Approach Comparison")
    print("=" * 60)
    print()

    # Run benchmark
    results = run_benchmark(str(save_path))

    # Generate markdown report
    report = generate_markdown_report(results)

    # Save results
    output_path = Path("/Users/avani/stellaris-companion/benchmark_results.md")
    output_path.write_text(report)
    print(f"\n\nReport saved to: {output_path}")

    # Also save raw JSON for analysis
    json_path = Path("/Users/avani/stellaris-companion/benchmark_results.json")

    # Make results JSON serializable
    def make_serializable(obj):
        if isinstance(obj, dict):
            return {k: make_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [make_serializable(v) for v in obj]
        elif isinstance(obj, (int, float, str, bool, type(None))):
            return obj
        else:
            return str(obj)

    json_path.write_text(json.dumps(make_serializable(results), indent=2))
    print(f"Raw data saved to: {json_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
