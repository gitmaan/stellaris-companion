#!/usr/bin/env python3
"""
Benchmark: Option B (Full Pre-compute) vs Current (Slim + Tools)

Tests:
- Response latency
- Tool call counts
- Response quality (completeness)
- Token usage approximation
"""

import json
import os
import sys
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables from .env file
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # dotenv not installed, rely on environment variables

from google import genai
from google.genai import types

from backend.core.companion import Companion
from personality import build_optimized_prompt
from save_extractor import SaveExtractor

# Test questions that cover different data needs
TEST_QUESTIONS = [
    # Simple - should work with summary
    "What is my current military power?",
    # Needs leader details
    "Which of my admirals has the best traits for combat?",
    # Needs planet details
    "Which of my planets has the lowest stability and why?",
    # Needs diplomacy details
    "Who are my strongest allies and what treaties do we have?",
    # Needs fleet details
    "What is my largest fleet and how many ships does it have?",
    # Complex - needs multiple categories
    "Give me a strategic assessment: should I go to war right now?",
]


class OptionBCompanion:
    """Option B: Full pre-compute, no tools."""

    def __init__(self, save_path: str):
        self.api_key = os.environ.get("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY not set")

        self.client = genai.Client(api_key=self.api_key)
        self.extractor = SaveExtractor(save_path)

        # Pre-compute EVERYTHING
        self._complete_briefing = self._get_complete_briefing()
        self._briefing_json = json.dumps(self._complete_briefing, indent=2, default=str)
        self._briefing_size = len(self._briefing_json)

        # Build personality
        identity = self.extractor.get_empire_identity()
        situation = self.extractor.get_situation()
        self.system_prompt = build_optimized_prompt(identity, situation)

        print(
            f"[Option B] Complete briefing size: {self._briefing_size:,} bytes ({self._briefing_size // 1024} KB)"
        )

    def _get_complete_briefing(self) -> dict:
        """Get ALL data without truncation."""
        return {
            "meta": self.extractor.get_metadata(),
            "identity": self.extractor.get_empire_identity(),
            "situation": self.extractor.get_situation(),
            "military": self.extractor.get_player_status(),
            "economy": self.extractor.get_resources(),
            "leaders": self.extractor.get_leaders(),
            "planets": self.extractor.get_planets(),
            "diplomacy": self.extractor.get_diplomacy(),
            "technology": self.extractor.get_technology(),
            "starbases": self.extractor.get_starbases(),
            "fleets": self.extractor.get_fleets(),
            "wars": self.extractor.get_wars(),
            "fallen_empires": self.extractor.get_fallen_empires(),
        }

    def ask(self, question: str) -> tuple[str, float, dict]:
        """Ask with full pre-computed data, no tools."""
        start = time.time()

        prompt = f"""COMPLETE EMPIRE DATA (use this to answer - do not make up information):
```json
{self._briefing_json}
```

QUESTION: {question}

Answer based ONLY on the data above. Be specific and reference actual values from the data.
If information is not present in the data, say "I don't have that information."
"""

        config = types.GenerateContentConfig(
            system_instruction=self.system_prompt,
            temperature=1.0,
            max_output_tokens=4096,
            # NO TOOLS - everything is pre-injected
        )

        response = self.client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt,
            config=config,
        )

        elapsed = time.time() - start
        response_text = response.text or "No response"

        stats = {
            "tool_calls": 0,
            "briefing_size_kb": self._briefing_size // 1024,
            "response_length": len(response_text),
            "latency_ms": elapsed * 1000,
        }

        return response_text, elapsed, stats


def run_benchmark(save_path: str):
    """Run benchmark comparing Option B vs Current."""

    print("=" * 80)
    print("BENCHMARK: Option B (Full Pre-compute) vs Current (Slim + Tools)")
    print("=" * 80)
    print(f"Save file: {save_path}")
    print()

    # Initialize both approaches
    print("Initializing Option B (full pre-compute)...")
    option_b = OptionBCompanion(save_path)

    print("Initializing Current (slim + tools)...")
    current = Companion(save_path)

    print()
    print("-" * 80)

    results = []

    for i, question in enumerate(TEST_QUESTIONS):
        print(f"\n[Question {i + 1}/{len(TEST_QUESTIONS)}]")
        print(f"Q: {question}")
        print("-" * 40)

        result = {"question": question}

        # Test Option B
        print("\n>>> Option B (Full Pre-compute, No Tools):")
        try:
            response_b, elapsed_b, stats_b = option_b.ask(question)
            result["option_b"] = {
                "latency_ms": stats_b["latency_ms"],
                "tool_calls": stats_b["tool_calls"],
                "response_length": stats_b["response_length"],
                "response_preview": response_b[:300] + "..."
                if len(response_b) > 300
                else response_b,
            }
            print(f"    Latency: {stats_b['latency_ms']:.0f}ms")
            print(f"    Tool calls: {stats_b['tool_calls']}")
            print(f"    Response: {len(response_b)} chars")
            print(f"    Preview: {response_b[:200]}...")
        except Exception as e:
            print(f"    ERROR: {e}")
            result["option_b"] = {"error": str(e)}

        # Test Current (ask_simple)
        print("\n>>> Current (Slim Snapshot + Tools):")
        try:
            response_c, elapsed_c = current.ask_simple(question)
            stats_c = current.get_call_stats()
            result["current"] = {
                "latency_ms": stats_c["wall_time_ms"],
                "tool_calls": stats_c["total_calls"],
                "tools_used": stats_c["tools_used"],
                "response_length": len(response_c),
                "response_preview": response_c[:300] + "..."
                if len(response_c) > 300
                else response_c,
            }
            print(f"    Latency: {stats_c['wall_time_ms']:.0f}ms")
            print(f"    Tool calls: {stats_c['total_calls']} ({stats_c['tools_used']})")
            print(f"    Response: {len(response_c)} chars")
            print(f"    Preview: {response_c[:200]}...")
        except Exception as e:
            print(f"    ERROR: {e}")
            result["current"] = {"error": str(e)}

        results.append(result)

        # Small delay between questions to avoid rate limiting
        time.sleep(1)

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    option_b_latencies = [
        r["option_b"]["latency_ms"] for r in results if "latency_ms" in r.get("option_b", {})
    ]
    current_latencies = [
        r["current"]["latency_ms"] for r in results if "latency_ms" in r.get("current", {})
    ]
    current_tool_calls = [
        r["current"]["tool_calls"] for r in results if "tool_calls" in r.get("current", {})
    ]

    if option_b_latencies:
        print(f"\nOption B (Full Pre-compute):")
        print(f"  Avg latency: {sum(option_b_latencies) / len(option_b_latencies):.0f}ms")
        print(f"  Min latency: {min(option_b_latencies):.0f}ms")
        print(f"  Max latency: {max(option_b_latencies):.0f}ms")
        print(f"  Tool calls: 0 (always)")
        print(f"  Context size: {option_b._briefing_size // 1024} KB")

    if current_latencies:
        print(f"\nCurrent (Slim + Tools):")
        print(f"  Avg latency: {sum(current_latencies) / len(current_latencies):.0f}ms")
        print(f"  Min latency: {min(current_latencies):.0f}ms")
        print(f"  Max latency: {max(current_latencies):.0f}ms")
        print(f"  Avg tool calls: {sum(current_tool_calls) / len(current_tool_calls):.1f}")
        print(f"  Max tool calls: {max(current_tool_calls)}")

    if option_b_latencies and current_latencies:
        speedup = (sum(current_latencies) / len(current_latencies)) / (
            sum(option_b_latencies) / len(option_b_latencies)
        )
        print(f"\nOption B is {speedup:.1f}x {'faster' if speedup > 1 else 'slower'} on average")

    # Save detailed results
    results_path = PROJECT_ROOT / "benchmark_option_b_results.json"
    with open(results_path, "w") as f:
        json.dump(
            {
                "summary": {
                    "option_b_avg_ms": sum(option_b_latencies) / len(option_b_latencies)
                    if option_b_latencies
                    else None,
                    "current_avg_ms": sum(current_latencies) / len(current_latencies)
                    if current_latencies
                    else None,
                    "option_b_context_kb": option_b._briefing_size // 1024,
                },
                "results": results,
            },
            f,
            indent=2,
            default=str,
        )
    print(f"\nDetailed results saved to: {results_path}")

    return results


if __name__ == "__main__":
    save_path = sys.argv[1] if len(sys.argv) > 1 else str(PROJECT_ROOT / "test_save.sav")

    if not Path(save_path).exists():
        print(f"Save file not found: {save_path}")
        sys.exit(1)

    run_benchmark(save_path)
