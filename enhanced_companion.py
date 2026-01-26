#!/usr/bin/env python3
"""
Enhanced Companion - Optimized Version
======================================

This is the optimized version of the Stellaris Companion that achieves:
- 50-80% faster response times than production
- Same quality advisory responses with rich personality
- Proper empire name resolution
- Comprehensive snapshot with pre-resolved data

KEY FINDINGS:
1. Must use `gemini-3-flash-preview` (not gemini-2.0-flash) for quality responses
2. Must include "express yourself" instruction to avoid terse responses
3. Pre-injecting comprehensive snapshot reduces tool calls dramatically
4. Full production personality prompt is essential - don't over-simplify

USAGE:
    from enhanced_companion import EnhancedCompanion

    companion = EnhancedCompanion("path/to/save.sav")
    response, elapsed = companion.ask("What is my military power?")
    print(response)
"""

import json
import re
import time
from pathlib import Path

from dotenv import load_dotenv


class EnhancedCompanion:
    """Optimized Stellaris Companion with pre-injected snapshots."""

    # Known Stellaris empire localization keys
    EMPIRE_LOC_KEYS = {
        "EMPIRE_DESIGN_orbis": "United Nations of Earth",
        "EMPIRE_DESIGN_humans1": "Commonwealth of Man",
        "EMPIRE_DESIGN_humans2": "Terran Hegemony",
        "PRESCRIPTED_empire_name_orbis": "United Nations of Earth",
    }

    def __init__(self, save_path: str):
        """Initialize with a save file path."""
        # Load environment
        load_dotenv(Path(__file__).parent / ".env")

        # Import here to avoid issues if not installed
        from google import genai
        from google.genai import types

        self.types = types
        self.client = genai.Client()

        # Import extractor and companion for their functionality
        import sys

        sys.path.insert(0, str(Path(__file__).parent / "backend"))
        sys.path.insert(0, str(Path(__file__).parent))

        from core.companion import Companion

        from save_extractor import SaveExtractor

        self.extractor = SaveExtractor(save_path)

        # Get production system prompt (has all the personality instructions)
        temp_companion = Companion(save_path=save_path)
        self.base_system_prompt = temp_companion.system_prompt

        # Build the enhanced system prompt
        self.system_prompt = self._build_system_prompt()

        # Build comprehensive snapshot once
        self.snapshot = self._build_comprehensive_snapshot()
        self.snapshot_json = json.dumps(self.snapshot, separators=(",", ":"), default=str)

    def _build_system_prompt(self) -> str:
        """
        Build enhanced system prompt using production personality + ASK MODE OVERRIDES.

        This is the key insight: use the FULL production prompt (with all personality
        instructions), then add ASK MODE OVERRIDES for efficiency.
        """
        return (
            f"{self.base_system_prompt}\n\n"
            "ASK MODE OVERRIDES:\n"
            "- The current game state snapshot is included in the user message.\n"
            "- Never request get_snapshot(); it is not available in this mode.\n"
            "- Minimize tool usage: usually 0-1 tool calls.\n"
            "- If you must call tools, batch categories in one get_details call.\n"
            "- After gathering enough info, stop calling tools and answer.\n"
            "- IMPORTANT: Maintain your full personality, colorful language, and in-character voice. "
            "Being efficient with tools does NOT mean being terse - express yourself!\n"
        )

    def _get_empire_name_by_id(self, empire_id: int) -> str:
        """Resolve an empire ID to its display name."""
        gamestate = self.extractor.gamestate

        # Find country section
        country_match = re.search(r"^country=\s*\{", gamestate, re.MULTILINE)
        if not country_match:
            return f"Empire {empire_id}"

        start = country_match.start()

        # Find specific empire entry
        pattern = rf"\n\t{empire_id}=\s*\{{"
        id_match = re.search(pattern, gamestate[start : start + 10000000])
        if not id_match:
            return f"Empire {empire_id}"

        chunk_start = start + id_match.start()
        chunk = gamestate[chunk_start : chunk_start + 8000]

        # Try to get name key
        name_match = re.search(r"name=\s*\{[^}]*key=\"([^\"]+)\"", chunk)
        if not name_match:
            return f"Empire {empire_id}"

        name_key = name_match.group(1)

        # Check known localization keys
        if name_key in self.EMPIRE_LOC_KEYS:
            return self.EMPIRE_LOC_KEYS[name_key]

        # Handle procedural names (%ADJECTIVE%, etc.)
        if "%" in name_key:
            name_block_match = re.search(
                r"name=\s*\{([^}]+variables[^}]+\}[^}]+)\}", chunk, re.DOTALL
            )
            if name_block_match:
                name_block = name_block_match.group(1)

                # Find adjective value
                adj_match = re.search(
                    r"key=\"adjective\"[^}]*value=\s*\{[^}]*key=\"([^\"]+)\"", name_block, re.DOTALL
                )
                adjective = ""
                if adj_match:
                    adj_key = adj_match.group(1)
                    adjective = adj_key.replace("SPEC_", "").replace("_", " ")

                # Find suffix
                suffix_match = re.search(
                    r"key=\"1\"[^}]*value=\s*\{[^}]*key=\"([^\"]+)\"", name_block, re.DOTALL
                )
                suffix = ""
                if suffix_match:
                    suffix = suffix_match.group(1)

                if adjective and suffix:
                    return f"{adjective} {suffix}"
                elif adjective:
                    return adjective

        # Fallback - clean up the key
        clean_name = name_key.replace("EMPIRE_DESIGN_", "").replace("PRESCRIPTED_", "")
        clean_name = clean_name.replace("_", " ").title()
        return clean_name if clean_name else f"Empire {empire_id}"

    def _build_comprehensive_snapshot(self) -> dict:
        """
        Build a comprehensive snapshot with:
        - Full briefing data
        - ALL leaders (not truncated)
        - Resolved ally/rival names
        - Detailed diplomatic relations
        """
        # Get base snapshot
        snapshot = self.extractor.get_full_briefing()

        # Add ALL leaders (not just the truncated 15)
        all_leaders = self.extractor.get_leaders()
        snapshot["leadership"]["leaders"] = all_leaders.get("leaders", [])
        snapshot["leadership"]["count"] = len(all_leaders.get("leaders", []))

        # Add detailed diplomacy with resolved names
        detailed_diplo = self.extractor.get_diplomacy()
        relations = []
        for r in detailed_diplo.get("relations", [])[:20]:
            cid = r.get("country_id")
            if cid is not None:
                r["empire_name"] = self._get_empire_name_by_id(cid)
            relations.append(r)
        snapshot["diplomacy"]["relations"] = relations
        snapshot["diplomacy"]["treaties"] = detailed_diplo.get("treaties", [])

        # Resolve ally names
        ally_ids = snapshot["diplomacy"].get("allies", [])
        snapshot["diplomacy"]["allies_named"] = [
            {"id": aid, "name": self._get_empire_name_by_id(aid)} for aid in ally_ids
        ]

        # Resolve rival names
        rival_ids = snapshot["diplomacy"].get("rivals", [])
        snapshot["diplomacy"]["rivals_named"] = [
            {"id": rid, "name": self._get_empire_name_by_id(rid)} for rid in rival_ids
        ]

        # Add current research explicitly
        tech = self.extractor.get_technology()
        snapshot["current_research"] = tech.get("current_research", {})
        if not snapshot["current_research"]:
            snapshot["current_research"] = "None - research slots are idle"

        return snapshot

    def ask(self, question: str) -> tuple[str, float]:
        """
        Ask a question and get a response.

        Returns:
            tuple of (response_text, elapsed_time_seconds)
        """
        tools_used = []

        def get_details(categories: list[str], limit: int = 50) -> dict:
            """Get detailed data for categories like leaders, fleets, diplomacy, etc."""
            tools_used.append(f"get_details({categories})")
            return self.extractor.get_details(categories, limit)

        def search_save_file(query: str, limit: int = 20) -> dict:
            """Search the save file for specific text."""
            tools_used.append(f"search_save_file({query})")
            return self.extractor.search(query)

        # Build user prompt with snapshot
        user_prompt = f"GAME STATE SNAPSHOT:\n{self.snapshot_json}\n\nQuestion: {question}"

        start = time.time()

        config = self.types.GenerateContentConfig(
            system_instruction=self.system_prompt,
            tools=[get_details, search_save_file],
            temperature=1.0,
            max_output_tokens=2048,
            automatic_function_calling=self.types.AutomaticFunctionCallingConfig(
                maximum_remote_calls=6,
            ),
        )

        # IMPORTANT: Use gemini-3-flash-preview for quality responses
        # gemini-2.0-flash gives terse, fact-only responses
        response = self.client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=user_prompt,
            config=config,
        )

        elapsed = time.time() - start

        return response.text, elapsed

    def get_snapshot(self) -> dict:
        """Get the pre-built comprehensive snapshot."""
        return self.snapshot

    def refresh_snapshot(self):
        """Rebuild the snapshot (call after save file changes)."""
        self.snapshot = self._build_comprehensive_snapshot()
        self.snapshot_json = json.dumps(self.snapshot, separators=(",", ":"), default=str)


# =============================================================================
# TEST / COMPARISON CODE
# =============================================================================


def run_comparison():
    """Run a comparison between production and enhanced versions."""
    import sys

    sys.path.insert(0, str(Path(__file__).parent / "backend"))
    from core.companion import Companion

    QUESTIONS = [
        "What is my current military power?",
        "Who are my allies?",
        "Who is my best military commander?",
        "What is the state of my economy?",
        "Give me a strategic assessment.",
    ]

    print("=" * 80)
    print("PRODUCTION vs ENHANCED COMPARISON")
    print("=" * 80)

    # Initialize both
    production = Companion(save_path="test_save.sav")
    enhanced = EnhancedCompanion("test_save.sav")

    results = []

    for q in QUESTIONS:
        print(f"\nQ: {q}")
        print("-" * 60)

        # Run production
        production.clear_conversation()
        prod_response, prod_time = production.ask_simple(q)
        prod_stats = production.get_call_stats()

        # Run enhanced
        enh_response, enh_time = enhanced.ask(q)

        print(
            f"Production: {prod_time:.1f}s, {len(prod_response.split())} words, {prod_stats.get('total_calls', 0)} tools"
        )
        print(f"Enhanced:   {enh_time:.1f}s, {len(enh_response.split())} words")

        results.append(
            {
                "question": q,
                "production": {
                    "time": prod_time,
                    "words": len(prod_response.split()),
                    "tools": prod_stats.get("total_calls", 0),
                    "response": prod_response,
                },
                "enhanced": {
                    "time": enh_time,
                    "words": len(enh_response.split()),
                    "response": enh_response,
                },
            }
        )

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    prod_avg_time = sum(r["production"]["time"] for r in results) / len(results)
    enh_avg_time = sum(r["enhanced"]["time"] for r in results) / len(results)
    prod_avg_words = sum(r["production"]["words"] for r in results) / len(results)
    enh_avg_words = sum(r["enhanced"]["words"] for r in results) / len(results)

    print(f"Avg Time:  Production {prod_avg_time:.1f}s | Enhanced {enh_avg_time:.1f}s")
    print(f"Speedup:   {((prod_avg_time - enh_avg_time) / prod_avg_time * 100):.0f}% faster")
    print(f"Avg Words: Production {prod_avg_words:.0f} | Enhanced {enh_avg_words:.0f}")

    # Save results
    Path("enhanced_comparison_results.json").write_text(json.dumps(results, indent=2, default=str))
    print("\nResults saved to enhanced_comparison_results.json")

    return results


def show_sample_responses():
    """Show sample responses from the enhanced companion."""
    enhanced = EnhancedCompanion("test_save.sav")

    QUESTIONS = [
        "What is my current military power?",
        "Who are my allies?",
        "Who is my best military commander?",
    ]

    print("=" * 80)
    print("ENHANCED COMPANION SAMPLE RESPONSES")
    print("=" * 80)

    for q in QUESTIONS:
        print(f"\nQ: {q}")
        print("-" * 60)
        response, elapsed = enhanced.ask(q)
        print(f"Time: {elapsed:.1f}s")
        print(response)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--compare":
        run_comparison()
    else:
        show_sample_responses()
