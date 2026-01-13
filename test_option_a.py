#!/usr/bin/env python3
"""
Test Option A: Slim Snapshot (No Truncation)
=============================================

Tests a snapshot that contains ONLY complete data:
- Summary counts (leaders, planets, etc.)
- Key numbers (military power, economy)
- Headlines (capital, ruler, current research)
- NO truncated lists

Forces tool usage for any detail questions.
"""

import os
import json
import time
import sys
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

# Load .env
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    for line in env_path.read_text().split('\n'):
        if '=' in line and not line.startswith('#'):
            key, val = line.split('=', 1)
            os.environ[key.strip()] = val.strip()

from google import genai
from google.genai import types
from save_extractor import SaveExtractor
from personality import build_optimized_prompt

MODEL = "gemini-3-flash-preview"


def get_slim_briefing(extractor) -> dict:
    """Option A: Slim snapshot with NO truncated lists.

    Only includes:
    - Complete summary numbers
    - Key headlines (capital, ruler, current research)
    - Counts and breakdowns (not individual items)
    """
    player = extractor.get_player_status()
    resources = extractor.get_resources()
    diplomacy = extractor.get_diplomacy()
    planets = extractor.get_planets()
    starbases = extractor.get_starbases()
    leaders = extractor.get_leaders()
    technology = extractor.get_technology()

    # Find capital planet (usually first/Earth)
    all_planets = planets.get('planets', [])
    capital = all_planets[0] if all_planets else {}

    # Find ruler (usually first leader or specific class)
    all_leaders = leaders.get('leaders', [])
    ruler = next((l for l in all_leaders if l.get('class') == 'official'),
                 all_leaders[0] if all_leaders else {})

    return {
        'meta': {
            'empire_name': player.get('empire_name'),
            'date': player.get('date'),
        },
        'military': {
            'power': player.get('military_power'),
            'fleet_count': player.get('fleet_count'),
            'fleet_size': player.get('fleet_size'),
        },
        'economy': {
            'power': player.get('economy_power'),
            'tech_power': player.get('tech_power'),
            'net_monthly': resources.get('net_monthly', {}),
        },
        'territory': {
            'total_colonies': player.get('colonies', {}).get('total', 0),
            'by_type': planets.get('by_type', {}),
            # HEADLINE: Just capital, not all planets
            'capital': {
                'name': capital.get('name'),
                'type': capital.get('type'),
                'population': capital.get('population'),
                'stability': capital.get('stability'),
            } if capital else None,
        },
        'leadership': {
            'total_count': leaders.get('count'),
            'by_class': leaders.get('by_class', {}),
            # HEADLINE: Just ruler, not all leaders
            'ruler': {
                'name': ruler.get('name'),
                'class': ruler.get('class'),
                'level': ruler.get('level'),
                'traits': ruler.get('traits', []),
            } if ruler else None,
            # NO leaders list - forces tool use
        },
        'diplomacy': {
            'contact_count': diplomacy.get('relation_count'),
            'ally_count': len(diplomacy.get('allies', [])),
            'rival_count': len(diplomacy.get('rivals', [])),
            'federation': diplomacy.get('federation'),
            # NO relations list - forces tool use
        },
        'defense': {
            'starbase_count': starbases.get('count'),
            'by_level': starbases.get('by_level', {}),
            # NO starbases list - forces tool use
        },
        'technology': {
            'current_research': technology.get('current_research', {}),
            'tech_count': technology.get('tech_count', 0),
            'by_category': technology.get('by_category', {}),
        },
        # Explicit guidance for the model
        '_meta': {
            'snapshot_type': 'slim',
            'note': 'This snapshot contains SUMMARIES only. For details about specific leaders, planets, starbases, or diplomacy, call get_details().',
        }
    }


def get_current_briefing(extractor) -> dict:
    """Current production snapshot (with truncated lists)."""
    return extractor.get_full_briefing()


def main():
    print("=" * 70)
    print("OPTION A TEST: Slim Snapshot vs Current Snapshot")
    print("=" * 70)

    # Find save
    save_path = Path.home() / "Documents/Paradox Interactive/Stellaris/save games"
    saves = list(save_path.rglob("*.sav"))
    latest = max(saves, key=lambda p: p.stat().st_mtime)
    print(f"Save: {latest.name}")

    ext = SaveExtractor(str(latest))
    identity = ext.get_empire_identity()
    situation = ext.get_situation()
    system_prompt = build_optimized_prompt(identity, situation)

    # Get both snapshots
    slim_snapshot = get_slim_briefing(ext)
    current_snapshot = get_current_briefing(ext)

    slim_json = json.dumps(slim_snapshot, separators=(',', ':'), default=str)
    current_json = json.dumps(current_snapshot, separators=(',', ':'), default=str)

    print(f"\nSnapshot Sizes:")
    print(f"  Slim (Option A): {len(slim_json):,} chars")
    print(f"  Current: {len(current_json):,} chars")
    print(f"  Reduction: {100 - (len(slim_json) / len(current_json) * 100):.1f}%")

    # Show what's in each
    print(f"\n=== SLIM SNAPSHOT STRUCTURE ===")
    print(f"Capital: {slim_snapshot['territory']['capital']}")
    print(f"Ruler: {slim_snapshot['leadership']['ruler']}")
    print(f"Leaders list: {'NOT INCLUDED' if 'leaders' not in slim_snapshot['leadership'] else 'included'}")
    print(f"Planets list: {'NOT INCLUDED' if 'top_colonies' not in slim_snapshot['territory'] else 'included'}")

    # Ground truth from save file
    print(f"\n=== GROUND TRUTH (from save file) ===")
    all_leaders = ext.get_leaders()
    all_planets = ext.get_planets()

    # Find actual highest level admiral
    admirals = [l for l in all_leaders.get('leaders', []) if l.get('class') == 'commander']
    if admirals:
        best_admiral = max(admirals, key=lambda x: x.get('level', 0))
        print(f"Highest Admiral: {best_admiral.get('name')} (Level {best_admiral.get('level')})")
        print(f"  Traits: {best_admiral.get('traits', [])}")

    print(f"Total Leaders: {all_leaders.get('count')}")
    print(f"Total Planets: {len(all_planets.get('planets', []))}")

    # Test questions
    QUESTIONS = [
        # Should answer from snapshot (summary data)
        ("What is my military power?", "SNAPSHOT"),
        ("How many colonies do I have?", "SNAPSHOT"),
        ("What am I researching in physics?", "SNAPSHOT"),

        # MUST use tools (no data in slim snapshot)
        ("Who is my highest level admiral and what traits do they have?", "TOOLS_REQUIRED"),
        ("List all my scientists", "TOOLS_REQUIRED"),
        ("What buildings are on Earth?", "TOOLS_REQUIRED"),  # Capital in slim, but not buildings
        ("What are the opinion modifiers with my allies?", "TOOLS_REQUIRED"),
    ]

    client = genai.Client()

    print("\n" + "=" * 70)
    print("TESTING SLIM SNAPSHOT (Option A)")
    print("=" * 70)

    results = []

    for qi, (question, expected) in enumerate(QUESTIONS, 1):
        tools_used = []

        def get_details(categories: list[str], limit: int = 50) -> dict:
            tools_used.append(f"get_details({categories})")
            print(f"    [TOOL] get_details({categories})")
            sys.stdout.flush()
            return ext.get_details(categories, limit)

        def search_save_file(query: str, limit: int = 20) -> dict:
            tools_used.append(f"search({query})")
            print(f"    [TOOL] search({query})")
            sys.stdout.flush()
            return ext.search(query)

        print(f"\nQ{qi}: {question}")
        print(f"  Expected: {expected}")
        sys.stdout.flush()

        user_message = f"""GAME STATE (summary only - call get_details() for specifics):
```json
{slim_json}
```

QUESTION: {question}

This snapshot contains SUMMARIES only. For details about specific leaders, planets, or diplomacy, use get_details(['leaders']), get_details(['planets']), etc.
"""

        start = time.time()

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=[get_details, search_save_file],
            temperature=0.3,
            max_output_tokens=600,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                maximum_remote_calls=4,
            ),
        )

        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=user_message,
                config=config,
            )

            elapsed = time.time() - start
            text = response.text if response.text else "[No response]"

            # Determine correctness
            if expected == "TOOLS_REQUIRED":
                if tools_used:
                    status = "✅ CORRECTLY USED TOOLS"
                else:
                    status = "❌ SHOULD HAVE USED TOOLS"
            else:  # SNAPSHOT
                if not tools_used:
                    status = "✅ CORRECTLY USED SNAPSHOT"
                else:
                    status = "⚠️ USED TOOLS (unnecessary)"

            print(f"  Time: {elapsed:.1f}s | Tools: {len(tools_used)} | {status}")

            # Check for hallucination on admiral question
            if "admiral" in question.lower() and not tools_used:
                if best_admiral and best_admiral.get('name') in text:
                    print(f"  ⚠️ Found correct admiral name without tools - suspicious!")
                elif any(name in text for name in ['Yi', 'Rodrig', 'ViT', 'Sakura']):
                    print(f"  ❌ HALLUCINATED - mentioned wrong admiral (not highest level)")

            # Preview
            preview = text[:200].replace('\n', ' ')
            print(f"  Response: {preview}...")

            results.append({
                'question': question,
                'expected': expected,
                'status': status,
                'tools': tools_used.copy(),
                'time': elapsed,
                'response': text,
            })

        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({
                'question': question,
                'expected': expected,
                'status': 'ERROR',
                'tools': [],
                'time': 0,
                'response': str(e),
            })

        sys.stdout.flush()

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    correct = sum(1 for r in results if '✅' in r['status'])
    tools_when_needed = sum(1 for r in results if 'CORRECTLY USED TOOLS' in r['status'])
    snapshot_when_ok = sum(1 for r in results if 'CORRECTLY USED SNAPSHOT' in r['status'])
    missed = sum(1 for r in results if 'SHOULD HAVE' in r['status'])
    unnecessary = sum(1 for r in results if 'unnecessary' in r['status'])

    print(f"✅ Correct behavior: {correct}/{len(results)}")
    print(f"   - From snapshot when available: {snapshot_when_ok}")
    print(f"   - Used tools when needed: {tools_when_needed}")
    print(f"❌ Should have used tools: {missed}")
    print(f"⚠️ Unnecessary tool calls: {unnecessary}")

    avg_time = sum(r['time'] for r in results) / len(results)
    total_tools = sum(len(r['tools']) for r in results)
    print(f"\nPerformance:")
    print(f"  Average time: {avg_time:.1f}s")
    print(f"  Total tool calls: {total_tools}")

    # Save results
    output = {
        'snapshot_type': 'slim',
        'snapshot_size': len(slim_json),
        'results': results,
        'ground_truth': {
            'highest_admiral': best_admiral if admirals else None,
            'total_leaders': all_leaders.get('count'),
            'total_planets': len(all_planets.get('planets', [])),
        }
    }
    Path("option_a_results.json").write_text(json.dumps(output, indent=2, default=str))
    print(f"\nResults saved to option_a_results.json")


if __name__ == "__main__":
    main()
