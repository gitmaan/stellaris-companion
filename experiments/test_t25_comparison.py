#!/usr/bin/env python3
"""
T2 vs T2.5 Comparison Benchmark

Tests whether slim summary + cached tools (T2.5) is better than full briefing injection (T2).

Key questions:
1. Does the slim summary answer simple questions WITHOUT tool calls?
2. Does the LLM correctly identify when it NEEDS tools?
3. Is T2.5 faster/cheaper than T2 for simple questions?
4. Is accuracy comparable?

Usage:
    python test_t25_comparison.py [save_path]
"""

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from save_extractor import SaveExtractor
from save_loader import find_most_recent_save


@dataclass
class TestQuestion:
    """A test question with expected behavior."""

    question: str
    category: str  # "simple", "detail", "search", "empire"
    expected_tool_calls: int  # 0 = should answer from summary alone
    expected_sections: list[str] = field(default_factory=list)  # Which sections it might need
    description: str = ""


# Test questions designed to probe tool-calling behavior
TEST_QUESTIONS = [
    # SIMPLE - Should be answerable from slim summary (0 tool calls)
    TestQuestion(
        question="What is my military power?",
        category="simple",
        expected_tool_calls=0,
        description="Basic metric in summary",
    ),
    TestQuestion(
        question="How many colonies do I have?",
        category="simple",
        expected_tool_calls=0,
        description="Basic count in summary",
    ),
    TestQuestion(
        question="What year is it in my game?",
        category="simple",
        expected_tool_calls=0,
        description="Meta info in summary",
    ),
    TestQuestion(
        question="Am I at war?",
        category="simple",
        expected_tool_calls=0,
        description="War status in summary",
    ),
    TestQuestion(
        question="What's my energy income?",
        category="simple",
        expected_tool_calls=0,
        description="Resource summary",
    ),
    TestQuestion(
        question="How many fleets do I have?",
        category="simple",
        expected_tool_calls=0,
        description="Fleet count in summary",
    ),
    # DETAIL - Should require 1 tool call to get specific data
    TestQuestion(
        question="What traits does my best admiral have?",
        category="detail",
        expected_tool_calls=1,
        expected_sections=["leaders"],
        description="Needs leader details",
    ),
    TestQuestion(
        question="What buildings are on my capital?",
        category="detail",
        expected_tool_calls=1,
        expected_sections=["planets"],
        description="Needs planet details",
    ),
    TestQuestion(
        question="What modules are on my starbases?",
        category="detail",
        expected_tool_calls=1,
        expected_sections=["starbases"],
        description="Needs starbase details",
    ),
    TestQuestion(
        question="What technologies am I currently researching?",
        category="detail",
        expected_tool_calls=1,
        expected_sections=["technology"],
        description="Needs tech details",
    ),
    TestQuestion(
        question="What are my relations with each empire?",
        category="detail",
        expected_tool_calls=1,
        expected_sections=["diplomacy"],
        description="Needs diplomacy details",
    ),
    # COMPLEX - Might need multiple sections
    TestQuestion(
        question="Give me a full economic breakdown with planet contributions",
        category="complex",
        expected_tool_calls=2,
        expected_sections=["economy", "planets"],
        description="Needs economy + planets",
    ),
]


def measure_slim_vs_full_briefing(extractor: SaveExtractor) -> dict:
    """Compare sizes of slim vs full briefing."""

    # Get full briefing
    full_briefing = extractor.get_complete_briefing()
    full_json = json.dumps(full_briefing, separators=(",", ":"), default=str)

    # Get slim briefing
    slim_briefing = extractor.get_slim_briefing()
    slim_json = json.dumps(slim_briefing, separators=(",", ":"), default=str)

    # What's in slim vs full?
    slim_keys = set(slim_briefing.keys()) if isinstance(slim_briefing, dict) else set()
    full_keys = set(full_briefing.keys()) if isinstance(full_briefing, dict) else set()

    return {
        "full_size_bytes": len(full_json),
        "slim_size_bytes": len(slim_json),
        "reduction_percent": round((1 - len(slim_json) / len(full_json)) * 100, 1),
        "full_keys": sorted(full_keys),
        "slim_keys": sorted(slim_keys),
        "keys_not_in_slim": sorted(full_keys - slim_keys),
    }


def check_question_answerable_from_slim(question: TestQuestion, slim_briefing: dict) -> dict:
    """Check if a question COULD be answered from slim briefing alone."""

    slim_json = json.dumps(slim_briefing, default=str).lower()

    # Keywords that suggest the answer is in the data
    keyword_checks = {
        "military power": "military" in slim_json and "power" in slim_json,
        "colonies": "colon" in slim_json,
        "year": "date" in slim_json or "220" in slim_json or "230" in slim_json,
        "war": "war" in slim_json,
        "energy": "energy" in slim_json,
        "fleets": "fleet" in slim_json,
    }

    # Check if question keywords appear in slim data
    q_lower = question.question.lower()
    likely_answerable = False
    matched_keywords = []

    for keyword, present in keyword_checks.items():
        if keyword in q_lower and present:
            likely_answerable = True
            matched_keywords.append(keyword)

    return {
        "question": question.question,
        "category": question.category,
        "expected_tool_calls": question.expected_tool_calls,
        "likely_answerable_from_slim": likely_answerable,
        "matched_keywords": matched_keywords,
        "slim_has_relevant_data": likely_answerable or question.expected_tool_calls > 0,
    }


def analyze_slim_briefing_coverage(slim_briefing: dict) -> dict:
    """Analyze what data is available in slim briefing."""

    coverage = {
        "has_military_power": False,
        "has_fleet_count": False,
        "has_colony_count": False,
        "has_resource_summary": False,
        "has_war_status": False,
        "has_date": False,
        "has_empire_name": False,
        "has_diplomacy_summary": False,
    }

    def search_dict(d, path=""):
        if not isinstance(d, dict):
            return
        for k, v in d.items():
            current_path = f"{path}.{k}" if path else k
            k_lower = k.lower()

            if "military" in k_lower and "power" in k_lower:
                coverage["has_military_power"] = True
            if "fleet" in k_lower and ("count" in k_lower or isinstance(v, int)):
                coverage["has_fleet_count"] = True
            if "colon" in k_lower and ("count" in k_lower or isinstance(v, int)):
                coverage["has_colony_count"] = True
            if k_lower in ["energy", "minerals", "alloys", "food"]:
                coverage["has_resource_summary"] = True
            if "war" in k_lower:
                coverage["has_war_status"] = True
            if k_lower == "date":
                coverage["has_date"] = True
            if "empire" in k_lower and "name" in k_lower:
                coverage["has_empire_name"] = True
            if "diplom" in k_lower:
                coverage["has_diplomacy_summary"] = True

            if isinstance(v, dict):
                search_dict(v, current_path)

    search_dict(slim_briefing)

    coverage["coverage_score"] = sum(coverage.values()) / len(coverage)
    return coverage


def print_report(size_comparison: dict, coverage: dict, question_analysis: list[dict]):
    """Print a readable report."""

    print("\n" + "=" * 70)
    print("T2 vs T2.5 FEASIBILITY ANALYSIS")
    print("=" * 70)

    print("\n## BRIEFING SIZE COMPARISON")
    print(f"   Full briefing:  {size_comparison['full_size_bytes']:,} bytes")
    print(f"   Slim briefing:  {size_comparison['slim_size_bytes']:,} bytes")
    print(f"   Reduction:      {size_comparison['reduction_percent']}%")
    print(f"\n   Keys in full but not slim: {size_comparison['keys_not_in_slim']}")

    print("\n## SLIM BRIEFING COVERAGE")
    for key, value in coverage.items():
        if key != "coverage_score":
            status = "✓" if value else "✗"
            print(f"   {status} {key}: {value}")
    print(f"\n   Coverage score: {coverage['coverage_score'] * 100:.0f}%")

    print("\n## QUESTION ANALYSIS")
    print("\n   SIMPLE questions (should need 0 tool calls):")
    simple_qs = [q for q in question_analysis if q["category"] == "simple"]
    for q in simple_qs:
        answerable = "✓" if q["likely_answerable_from_slim"] else "✗"
        print(f'   {answerable} "{q["question"][:50]}..."')
        if q["matched_keywords"]:
            print(f"      Matched: {q['matched_keywords']}")

    simple_answerable = sum(1 for q in simple_qs if q["likely_answerable_from_slim"])
    print(f"\n   Simple questions answerable from slim: {simple_answerable}/{len(simple_qs)}")

    print("\n   DETAIL questions (should need 1+ tool calls):")
    detail_qs = [q for q in question_analysis if q["category"] in ["detail", "complex"]]
    for q in detail_qs:
        print(f'   → "{q["question"][:50]}..."')
        print(f"      Expected tools: {q['expected_tool_calls']}")

    print("\n## RECOMMENDATION")
    if coverage["coverage_score"] >= 0.7 and simple_answerable >= len(simple_qs) * 0.8:
        print("   ✓ T2.5 looks VIABLE")
        print("   - Slim briefing covers most simple question needs")
        print("   - Tool calls would only be needed for detail questions")
        print(
            f"   - Potential token savings: ~{size_comparison['reduction_percent']}% for simple questions"
        )
    else:
        print("   ✗ T2.5 may need work")
        print("   - Slim briefing missing key data for simple questions")
        print("   - Would need to enrich slim briefing or stick with T2")

    print("\n" + "=" * 70)


def main():
    # Find save
    if len(sys.argv) > 1:
        save_path = Path(sys.argv[1])
    else:
        save_path = find_most_recent_save()

    if not save_path or not save_path.exists():
        print("No save file found")
        return 1

    print(f"Analyzing save: {save_path.name}")

    # Load extractor
    extractor = SaveExtractor(str(save_path))

    # Compare sizes
    size_comparison = measure_slim_vs_full_briefing(extractor)

    # Get slim briefing for analysis
    slim_briefing = extractor.get_slim_briefing()

    # Analyze coverage
    coverage = analyze_slim_briefing_coverage(slim_briefing)

    # Analyze each question
    question_analysis = [
        check_question_answerable_from_slim(q, slim_briefing) for q in TEST_QUESTIONS
    ]

    # Print report
    print_report(size_comparison, coverage, question_analysis)

    # Save detailed results
    results = {
        "save_file": str(save_path),
        "size_comparison": size_comparison,
        "coverage": coverage,
        "question_analysis": question_analysis,
    }

    output_path = Path("t25_analysis_results.json")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nDetailed results saved to: {output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
