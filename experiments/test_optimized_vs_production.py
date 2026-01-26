#!/usr/bin/env python3
"""
Optimized vs Production Prompt Comparison
==========================================

Compares the new optimized prompt against the current production prompt (v2).
Both use tools + pre-injected snapshot for fair comparison.
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

from personality import build_optimized_prompt, build_personality_prompt_v2
from save_extractor import SaveExtractor

MODEL = "gemini-3-flash-preview"

TEST_QUESTIONS = [
    "What's the state of my empire?",
    "Who should I be worried about?",
    "What should I focus on next?",
]


def find_save_file() -> Path:
    """Find the most recent Stellaris save file."""
    save_dirs = [
        Path.home() / "Documents/Paradox Interactive/Stellaris/save games",
        Path.home() / ".local/share/Paradox Interactive/Stellaris/save games",
    ]
    for save_dir in save_dirs:
        if save_dir.exists():
            sav_files = list(save_dir.rglob("*.sav"))
            if sav_files:
                return max(sav_files, key=lambda p: p.stat().st_mtime)
    raise FileNotFoundError("No Stellaris save files found")


def build_snapshot(extractor) -> dict:
    """Build comprehensive snapshot."""
    snapshot = extractor.get_full_briefing()
    leaders = extractor.get_leaders()
    snapshot["leadership"]["leaders"] = leaders.get("leaders", [])
    tech = extractor.get_technology()
    snapshot["current_research"] = tech.get("current_research", {}) or "None - idle"
    return snapshot


def run_single_test(client, extractor, system_prompt: str, snapshot: dict, question: str) -> dict:
    """Run a single test with tools available."""

    snapshot_json = json.dumps(snapshot, separators=(",", ":"), default=str)
    user_message = f"GAME STATE:\n```json\n{snapshot_json}\n```\n\n{question}"

    tools_used = []

    def get_details(categories: list[str], limit: int = 50) -> dict:
        tools_used.append(f"get_details({categories})")
        return extractor.get_details(categories, limit)

    def search_save_file(query: str, limit: int = 20) -> dict:
        tools_used.append(f"search({query})")
        return extractor.search(query)

    start = time.time()

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=[get_details, search_save_file],
        temperature=0.8,
        max_output_tokens=2048,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(
            maximum_remote_calls=6,
        ),
    )

    response = client.models.generate_content(
        model=MODEL,
        contents=user_message,
        config=config,
    )

    elapsed = time.time() - start
    text = response.text if response.text else "[No response]"

    return {
        "response": text,
        "time": elapsed,
        "words": len(text.split()),
        "tools_used": len(tools_used),
        "tools_list": tools_used,
    }


def main():
    print("=" * 80)
    print("OPTIMIZED vs PRODUCTION PROMPT COMPARISON")
    print(f"Model: {MODEL}")
    print("=" * 80)

    # Find save
    save_path = find_save_file()
    print(f"Save: {save_path.name}")

    extractor = SaveExtractor(str(save_path))
    identity = extractor.get_empire_identity()
    situation = extractor.get_situation()
    snapshot = build_snapshot(extractor)

    print(f"Empire: {identity.get('empire_name')}")
    print(f"Ethics: {identity.get('ethics')}")
    print(f"Authority: {identity.get('authority')}")
    print()

    # Build both prompts
    production_prompt = build_personality_prompt_v2(identity, situation)
    optimized_prompt = build_optimized_prompt(identity, situation)

    print(f"Production prompt: {len(production_prompt)} chars")
    print(f"Optimized prompt:  {len(optimized_prompt)} chars")
    print(f"Reduction: {100 - (len(optimized_prompt) / len(production_prompt) * 100):.0f}%")
    print()

    prompts = {
        "Production (v2)": production_prompt,
        "Optimized": optimized_prompt,
    }

    client = genai.Client()
    results = {name: [] for name in prompts}

    print("=" * 80)
    print("RUNNING TESTS...")
    print("=" * 80)

    for qi, question in enumerate(TEST_QUESTIONS, 1):
        print(f"\nQ{qi}: {question}")
        print("-" * 60)

        for name, prompt in prompts.items():
            print(f"  [{name}] ", end="", flush=True)
            try:
                result = run_single_test(client, extractor, prompt, snapshot, question)
                print(
                    f"{result['time']:.1f}s, {result['words']} words, {result['tools_used']} tools"
                )
                results[name].append({"question": question, **result})
            except Exception as e:
                print(f"ERROR: {e}")
                results[name].append(
                    {
                        "question": question,
                        "response": str(e),
                        "time": 0,
                        "words": 0,
                        "tools_used": 0,
                        "tools_list": [],
                    }
                )

    # Generate report
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    for name in prompts:
        avg_time = sum(r["time"] for r in results[name]) / len(results[name])
        avg_words = sum(r["words"] for r in results[name]) / len(results[name])
        total_tools = sum(r["tools_used"] for r in results[name])
        print(
            f"{name}: {avg_time:.1f}s avg, {avg_words:.0f} words avg, {total_tools} total tool calls"
        )

    # Write detailed report
    report = f"""# Optimized vs Production Comparison

**Date:** {datetime.now().strftime("%Y-%m-%d %H:%M")}

**Model:** {MODEL}

**Empire:** {identity.get("empire_name")}

**Ethics:** {", ".join(identity.get("ethics", []))}

**Authority:** {identity.get("authority")}

---

## Prompt Sizes

| Prompt | Characters | Reduction |
|--------|------------|-----------|
| Production (v2) | {len(production_prompt)} | baseline |
| Optimized | {len(optimized_prompt)} | {100 - (len(optimized_prompt) / len(production_prompt) * 100):.0f}% smaller |

---

## Production Prompt (v2)

```
{production_prompt}
```

---

## Optimized Prompt

```
{optimized_prompt}
```

---

## Results Summary

| Prompt | Avg Time | Avg Words | Total Tools |
|--------|----------|-----------|-------------|
"""

    for name in prompts:
        avg_time = sum(r["time"] for r in results[name]) / len(results[name])
        avg_words = sum(r["words"] for r in results[name]) / len(results[name])
        total_tools = sum(r["tools_used"] for r in results[name])
        report += f"| {name} | {avg_time:.1f}s | {avg_words:.0f} | {total_tools} |\n"

    report += "\n---\n\n## Full Responses\n\n"

    for qi, question in enumerate(TEST_QUESTIONS, 1):
        report += f"### Q{qi}: {question}\n\n"

        for name in prompts:
            r = results[name][qi - 1]
            report += f"#### {name}\n\n"
            report += f"*{r['time']:.1f}s | {r['words']} words | {r['tools_used']} tools*\n\n"
            report += f"{r['response']}\n\n"

        report += "---\n\n"

    output_path = Path("OPTIMIZED_VS_PRODUCTION.md")
    output_path.write_text(report)
    print(f"\nFull report: {output_path}")


if __name__ == "__main__":
    main()
