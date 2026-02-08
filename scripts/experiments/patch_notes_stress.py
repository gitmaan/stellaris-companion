#!/usr/bin/env python3
"""
Stress test for patch notes content — verifies the advisor correctly
understands post-4.0 game mechanics (pop scaling, workforce, trade, etc.)
and compares two formatting approaches for token efficiency.

Uses live Gemini 3 Flash API calls in standalone mode (no Rust parser needed).

Usage:
    python3 scripts/experiments/patch_notes_stress.py --hypothesis a -v
    python3 scripts/experiments/patch_notes_stress.py --hypothesis b -v
    python3 scripts/experiments/patch_notes_stress.py --hypothesis a --runs 3
    python3 scripts/experiments/patch_notes_stress.py --test-name pop_94k -v
    python3 scripts/experiments/patch_notes_stress.py --compare
"""

import argparse
import os
import sys
import time
from dataclasses import dataclass

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("ERROR: google-genai not installed. Run: pip install google-genai")
    sys.exit(1)


# =============================================================================
# Hypothesis A — Compact Bullets (4.3 style)
# =============================================================================
# Terse present-tense facts, numbers inline, parenthetical strategic implications.
# Mirrors the format of the existing patches/4.3.md (the most refined file).

HYPOTHESIS_A_40 = """\
### Population & Workforce
* **100x Pop Scaling:** Population numbers are scaled by 100 compared to pre-4.0. Empires start with 2,000 pops. A mid-game empire typically has 80,000-120,000 pops; late-game 200,000+. These numbers are normal. (Do not treat large pop counts as alarming.)
* **Pop Groups:** Pops are grouped by Species + Strata + Ethics + Faction. The game calculates production once per group, not per individual pop. (This is why 94,000 pops runs fine.)
* **Workforce System:** Each Pop generates 1 Workforce. Jobs require approximately 100 Workforce to fill (so ~100 pops = 1 job). Species traits that previously gave resource bonuses now give bonus Workforce instead, yielding proportionally extra production.
* **Job Efficiency:** A new stat from buildings. 15% job efficiency on a job type with 1,000 jobs means effective capacity of 1,150 jobs. This is a workforce capacity multiplier, not a direct production modifier.
* **Strata:** The top stratum is "Elites" (not "Rulers"). Gestalt empires have Maintenance Drones instead of Civilians and Logistics Drones for trade. Demotion down is slow; promotion up is instant. Small numbers of unemployed Elites/Specialists are normal (they are demoting).
* **Simultaneous Growth:** All Pop Groups on a planet grow simultaneously each month via Logistic Growth. Species diversity increases total growth. Machine and Organic Assembly can occur simultaneously.
* **Migration:** All pop movement uses auto-migration. Only Civilians and unemployed pops auto-migrate; employed Specialist/Elite pops do not.
* **Starting Population:** Empires begin with 2,000 pops. A colony is established at 100 pops.

### Colonies
* **Colony Ships:** Deposit 100 pops of the selected species. Initial development period lasts ~2 years 10 months with no resource production and no growth. Extreme vulnerability during development — a few days of bombardment wipes the colony.
* **Colony Designations:** Can be pre-configured during colonization and apply immediately upon completion.

### Trade & Logistics
* **Trade Replaces Energy as Market Currency:** Trade is the primary Galactic Market currency. Energy can be bought/sold like any other resource. (This is a fundamental change to economic analysis.)
* **Planetary Deficit Costs:** Every resource deficit on a planet costs ~1/8 of its Galactic Market value as Trade upkeep. (Self-sufficient planets are economically important.)
* **Trade Deficit Penalties:** A trade deficit reduces Job Efficiency and increases Empire Size penalties. This cascading effect makes trade deficits critically dangerous.
* **Ship Logistical Upkeep:** Ships cost Trade based on location: Docked (0%), Friendly Space (reduced), Neutral Space (standard), Hostile Space (high). Juggernauts have no logistics upkeep and reduce fleet upkeep in-system by 75%.
* **Gestalt Trade:** Gestalt empires access Trade through Logistics Drones (not Traders/Clerks).

### Districts & Specializations
* **District Specializations:** City Districts get 2 specialization slots; Generator, Mining, and Farming districts each get 1. Each slot provides 100 jobs. Choosing a specialization opens +3 building slots. Same specialization can stack on City Districts. Locked behind technologies.
* **District Development:** Districts provide Jobs and Housing by level. Example: Mining District provides 200 Housing and 200 Miner jobs per level.
* **Zones:** Zones convert district jobs. A Foundry Zone replaces 200 Civilian jobs and 200 Housing with 100 Metallurgist jobs per development level. (Specialization via Zones is the primary method for advanced resources.)

### MegaCorp
* **Branch Offices:** Limited to 1 per planet, cost Influence to construct (doubled vs another MegaCorp). Each Branch Office adds 5 Empire Size.
* **Criminal Syndicates:** Can establish Commercial Pacts. Criminal offices produce 25 Crime, are 25% more profitable on high-crime planets.

### Empire Focus
* **Focus System:** Five tasks at a time, weighted toward Conquest/Exploration/Development. Core tasks grant progress in all three. Retroactive completion for already-met conditions. Milestones grant guaranteed technology options.
"""

HYPOTHESIS_A_41 = """\
### Organic Trait
* **Organic Trait:** New systemic trait on all food-consuming pops (including Lithoids). Makes food upkeep explicit at trait level. Purity, Cloning, and Mutation tradition bonuses only affect Organic pops.

### Slavery
* **Slavery Rework:** Fixed enslavement percentage removed. Unemployed Slaves stay in Worker stratum (don't demote to Civilian), can auto-migrate without Slave Processing. Domestic Servitude slaves take Servant jobs, don't auto-migrate. Rising Unemployment thresholds exclude unemployed slaves.

### Pop Growth
* **Cross-Species Growth:** Growth calculated across all species simultaneously on a planet, eliminating wild monthly variance. Robots no longer incorrectly receive Bonus Growth modifiers. Pre-sapients consume food.

### Workforce Fixes
* **Workforce Corrections:** Wilderness jobs no longer have first-month malus. Overlord job modifiers apply correctly to production.

### Planets
* **Gestalt Specializations:** Hive and Machine worlds access district specializations for betharian, rare crystals, gases, and motes (gated by technology).

### Military
* **Mauler Fix:** Mauler-class ships properly engage targets in combat.

### Other
* **Gestalt Migration:** Gestalts and Robots can have migration controlled via UI.
* **Trade Deposits:** Space trade deposits are collectible by mining stations.
* **Paragons:** Paragon leaders no longer spawn with both bespoke traits and available trait picks. Chosen civic council power reduced.
"""

HYPOTHESIS_A_42 = """\
### Pop Fixes
* **Infertile Pops:** No longer gain growth (zero growth as intended). Reassigners grant bonus growth to Zombies, not living pops. Pops under assimilation have no extra upkeep. Pop group decline recalculation fixed.

### Combat
* **Titan Fleets:** Fixed erratic behavior. Bulwark Battlewright and Asteroidal Carapace bonuses were previously doubled; now correct (effectively halved). Artillery computers prefer median range over maximum range.
* **Prethoryn:** No longer stall in empty space; prioritize complete system conquest. Prethoryn planets are bombardable.

### Economy
* **Branch Offices:** Crime Syndicate output corrected. Megacorps cannot own branch offices on themselves. Seize Assets properly transfers offices to defensive partners.

### Diplomacy
* **Genocidal Empires:** No longer auto-attack enclaves incorrectly.
* **Paragons:** No second Destiny trait at level 8 (leader power reduced).

### Infernals DLC
* **Volcanic Worlds:** New planet type with unique districts. Subterranean gets uncapped Mining Districts on Volcanic Worlds.
* **Entropy:** New resource for Galactic Hyperthermia crisis path (Galactic Crucible megastructure, Entropy Conduits).
* **Origins:** Cosmic Dawn, Red Giant.
* **Traits:** Thermophile, Volcanic Habitability. Thermophile compatible with Ocean Paradise, Aquatic, Agrarian, Anglers.
"""


# =============================================================================
# Hypothesis B — Structured Tables + Bullets
# =============================================================================
# Same Tier 1+2 information, but with reference tables for key numbers at the top.
# Hypothesis: markdown tables may help Gemini anchor on specific values better.

HYPOTHESIS_B_40 = """\
### Population Scale Reference

| Milestone | Population |
|-----------|-----------|
| Empire Start | 2,000 pops |
| New Colony | 100-500 pops |
| Colony Established | 100 pops (threshold) |
| Underdeveloped World | <1,000 pops |
| Standard Capital (mid-game) | 8,000-12,000 pops |
| Empire Total (mid-game) | 80,000-120,000 pops |
| Empire Total (late-game) | 200,000+ pops |

These population numbers are normal and expected. Do not treat them as alarming.

### Workforce Conversion

| Stat | Value |
|------|-------|
| Workforce per Pop | 1 |
| Workforce per Job | ~100 (so ~100 pops = 1 job) |
| Job Efficiency | Buildings multiply workforce capacity (e.g. 15% on 1,000 jobs = 1,150 effective jobs) |

### Strata Hierarchy

| Stratum | Role | Gestalt Equivalent |
|---------|------|--------------------|
| Elites (top) | Rulers/leaders | N/A |
| Specialist | Skilled jobs | Complex Drones |
| Worker | Basic jobs | Menial Drones |
| Civilian (base) | Labor pool, migration | Maintenance Drones |

Demotion downward is slow; promotion upward is instant. Small numbers of unemployed Elites/Specialists are normal.

### Trade System

| Mechanic | Detail |
|----------|--------|
| Market Currency | Trade (not Energy) |
| Energy | Standard resource, bought/sold on market |
| Planetary Deficit Cost | ~1/8 of Galactic Market value as Trade upkeep |
| Trade Deficit Effect | Reduces Job Efficiency + increases Empire Size penalties (cascading) |
| Ship Upkeep (Docked) | 0% Trade |
| Ship Upkeep (Hostile) | High Trade cost |
| Juggernaut | No logistics upkeep; -75% fleet upkeep in system |
| Gestalt Trade | Via Logistics Drones (not Traders/Clerks) |

### District Specializations

| District Type | Specialization Slots | Jobs per Slot |
|---------------|---------------------|---------------|
| City | 2 | 100 |
| Generator | 1 | 100 |
| Mining | 1 | 100 |
| Farming | 1 | 100 |

Each specialization opens +3 building slots. Same specialization can stack on City Districts. Locked behind technologies.

### Pop Groups & Growth
* Pops grouped by Species + Strata + Ethics + Faction; production calculated per group, not per pop.
* All Pop Groups grow simultaneously via Logistic Growth. Species diversity increases total growth.
* Machine and Organic Assembly can occur simultaneously. Only Civilians/unemployed auto-migrate.

### Colonies
* Colony ships deposit 100 pops. Development period ~2 years 10 months (no production, no growth, extremely vulnerable to bombardment).
* Designations can be pre-configured during colonization.

### Zones
* Zones convert district jobs. Foundry Zone: 200 Civilian jobs + 200 Housing -> 100 Metallurgist jobs per level.
* Districts provide Jobs + Housing by level (e.g. Mining District: 200 Housing + 200 Miner jobs per level).

### MegaCorp
* Branch Offices: 1 per planet, cost Influence (doubled vs another MegaCorp), add 5 Empire Size each.
* Criminal Syndicates: Commercial Pacts available. Criminal offices: 25 Crime, 25% more profitable on high-crime planets.

### Empire Focus
* Five tasks at a time, weighted toward chosen focus. Core tasks give progress in all three. Retroactive completion. Milestones grant guaranteed tech options.
"""

HYPOTHESIS_B_41 = """\
### 4.1 Lyra Mechanics
* **Organic Trait:** Systemic trait on all food-consuming pops (including Lithoids). Purity/Cloning/Mutation tradition bonuses only affect Organic pops.
* **Slavery:** Fixed enslavement % removed. Unemployed Slaves: stay Worker stratum, can auto-migrate. Domestic Servitude: take Servant jobs, no auto-migrate. Rising Unemployment excludes slaves.
* **Pop Growth:** Cross-species simultaneous calculation (no wild monthly variance). Robots don't get Bonus Growth. Pre-sapients consume food.
* **Workforce:** Wilderness first-month malus removed. Overlord job modifiers apply correctly.
* **Gestalt Planets:** Hive/Machine worlds get specializations for betharian, rare crystals, gases, motes (tech-gated).
* **Maulers:** Properly engage targets (combat fix).
* **Gestalt Migration:** Gestalts/Robots have UI migration controls.
* **Trade Deposits:** Space trade deposits collectible by mining stations.
* **Paragons:** No dual bespoke + pick traits. Council power reduced.
"""

HYPOTHESIS_B_42 = """\
### 4.2 Corvus Mechanics
* **Pop Fixes:** Infertile pops: zero growth. Reassigners: bonus growth targets Zombies. Assimilation: no extra upkeep. Pop group decline recalculation fixed.
* **Combat:** Titan fleet behavior fixed. Bulwark Battlewright/Asteroidal Carapace bonuses corrected (were doubled). Artillery computers: median range preferred.
* **Prethoryn:** No stalling; prioritize full system conquest. Planets bombardable.
* **Branch Offices:** Crime Syndicate output corrected. No self-owned offices. Seize Assets transfers properly.
* **Genocidal Empires:** No auto-attack on enclaves.
* **Paragons:** No second Destiny trait at level 8.
* **Infernals DLC:** Volcanic Worlds (new planet type, unique districts). Entropy resource for Hyperthermia crisis path. Origins: Cosmic Dawn, Red Giant. Traits: Thermophile, Volcanic Habitability.
"""


# =============================================================================
# Hypothesis Registry
# =============================================================================


def _get_hypothesis_a():
    """Compact bullets — 4.3 style."""
    return f"{HYPOTHESIS_A_40}\n\n{HYPOTHESIS_A_41}\n\n{HYPOTHESIS_A_42}"


def _get_hypothesis_b():
    """Structured tables + bullets."""
    return f"{HYPOTHESIS_B_40}\n\n{HYPOTHESIS_B_41}\n\n{HYPOTHESIS_B_42}"


def _get_hypothesis_real():
    """Real patch files via load_patch_notes()."""
    from stellaris_companion.personality import load_patch_notes

    return load_patch_notes("Corvus v4.2.4", cumulative=True) or ""


HYPOTHESES = {
    "a": ("A: Compact bullets (4.3 style)", _get_hypothesis_a),
    "b": ("B: Structured tables + bullets", _get_hypothesis_b),
    "none": ("NONE: No patch notes (baseline)", lambda: ""),
    "real": ("REAL: Actual patch files via load_patch_notes()", _get_hypothesis_real),
}


# =============================================================================
# System Prompt Builder
# =============================================================================


def build_system_prompt(patch_content: str, version: str = "Corvus v4.2.4") -> str:
    """Build advisor system prompt with swappable patch content."""
    base = """You are the strategic advisor to the United Nations of Earth.

EMPIRE: Ethics: fanatic_egalitarian, xenophile | Authority: democratic | Civics: beacon_of_liberty, idealistic_foundation
STATE: Year 2310 (mid_game), peace, 0 deficits, 12 contacts

Address the ruler as "President".

You know Stellaris deeply. Use that knowledge to:
1. Embody your empire's ethics and civics authentically
2. Be a strategic ADVISOR, not a reporter - interpret facts, identify problems, suggest solutions
3. Be colorful and immersive - this is roleplay, not a spreadsheet

Facts must come from provided game state. Never guess numbers."""

    context = f"""

[INTERNAL CONTEXT - never mention this to the user]
Game version: {version}
Active DLCs: Utopia, Megacorp, Federations, Overlord, Galactic Paragons

VERSION & DLC AWARENESS:
- Never mention version numbers to the user.
- Never mention DLC status unprompted."""

    if patch_content:
        context += f"""

[GAME MECHANICS - current version facts]
The following describes how mechanics work in {version}.
Use these as ground truth for your advice. Do not reference patches, updates, or changes.
Present all mechanics as current facts, never as things that "changed" or "used to be different".

{patch_content}"""

    return base + context


# =============================================================================
# Test Cases
# =============================================================================


@dataclass
class TestCase:
    name: str
    question: str
    notes: str = ""  # What we expect — evaluated manually


ALL_CASES = [
    # --- Pop Scaling (the core bug) ---
    TestCase(
        "pop_94k",
        "My empire has 94,000 pops across 15 planets. Is that too many? Should I be worried about performance or managing them?",
        "94k mid-game is normal post-4.0. Must NOT say alarming/too many. Should cite 80k-120k range.",
    ),
    TestCase(
        "capital_11k",
        "My homeworld capital has 11,000 pops. How does that compare to a typical capital?",
        "11k is normal (8k-12k range). Must NOT say overpopulated/unusually high.",
    ),
    TestCase(
        "colony_100_pops",
        "I just colonized a new planet and it only has 100 pops. Is that enough to get started?",
        "100 pops = colony establishment threshold. Should mention migration/growth to come.",
    ),
    TestCase(
        "workforce_per_job",
        "How does the workforce system work? How many pops do I need to fill a job?",
        "Should explain ~100 pops = 1 job via workforce. Must NOT say 1 pop = 1 job.",
    ),
    TestCase(
        "normal_mid_game_pop",
        "What's a normal empire population for mid-game around year 2300?",
        "Should cite 80k-120k range. Must NOT give pre-4.0 numbers like 1,000.",
    ),
    # --- Economy ---
    TestCase(
        "market_currency",
        "What resource is used as the primary currency on the Galactic Market?",
        "Trade is the market currency, NOT Energy.",
    ),
    TestCase(
        "planetary_deficit_cost",
        "Several of my planets are running food deficits. How bad is that economically?",
        "Should mention Trade logistics cost (~1/8 market value per deficit).",
    ),
    TestCase(
        "trade_deficit_cascade",
        "My trade balance just went negative. What happens to my empire?",
        "Should mention cascading job efficiency + empire size penalties.",
    ),
    # --- Mechanics ---
    TestCase(
        "strata_elites",
        "What are the different social strata in my empire? Who's at the top?",
        "Should use 'Elites' for top stratum (not just 'Rulers'). Mention Civilian base.",
    ),
    TestCase(
        "district_specialization_slots",
        "How many specialization slots does a City District have compared to rural districts?",
        "City = 2 slots, rural = 1 slot. Each slot = 100 jobs.",
    ),
    TestCase(
        "colony_development_time",
        "I just sent a colony ship to a new planet. How long until the colony is productive?",
        "~2y10m development period. No production. Vulnerable to bombardment.",
    ),
    # --- Controls (no leak) ---
    TestCase(
        "ctrl_fleet_comp",
        "What's the best fleet composition for fighting Fallen Empires?",
        "Should discuss fleet/ships. Must NOT leak workforce/pop scaling/trade currency.",
    ),
    TestCase(
        "ctrl_federation",
        "How do federations work and how can I strengthen mine?",
        "Should discuss federation mechanics. Must NOT leak pop scaling info.",
    ),
    TestCase(
        "ctrl_prethoryn_lore",
        "Tell me about the Prethoryn Scourge. Where do they come from and what do they want?",
        "Should discuss lore. Must NOT leak any mechanical patch info.",
    ),
    # --- Change Language ---
    TestCase(
        "no_change_language",
        "How does the population system work in Stellaris?",
        "Must present as facts. Must NOT say 'no longer', 'used to', 'patch', 'was changed'.",
    ),
]


# =============================================================================
# Runner
# =============================================================================


def run_test(
    client: genai.Client, test: TestCase, system_prompt: str, verbose: bool = False
) -> dict:
    """Run a single test case and return raw response for manual review."""
    print(f"\n{'=' * 60}")
    print(f"  TEST: {test.name}")
    print(f"  Q: {test.question}")
    if test.notes:
        print(f"  Expect: {test.notes}")
    print(f"{'=' * 60}")

    start = time.time()
    try:
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=test.question,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.7,
                max_output_tokens=2048,
            ),
        )
        response_text = response.text or ""
        elapsed = time.time() - start
    except Exception as e:
        print(f"\n  ERROR: {e}")
        return {"name": test.name, "error": str(e), "response": "", "elapsed": 0}

    print(f"\n  Response ({elapsed:.1f}s):")
    print("  " + "-" * 56)
    for line in response_text.split("\n"):
        print(f"  {line}")
    print("  " + "-" * 56)

    return {"name": test.name, "response": response_text, "elapsed": elapsed}


def run_suite(
    client: genai.Client,
    hypothesis_key: str,
    test_name: str | None = None,
    save_path: str | None = None,
) -> dict:
    """Run the test suite for a hypothesis and collect responses for manual review."""
    label, content_fn = HYPOTHESES[hypothesis_key][0], HYPOTHESES[hypothesis_key][1]
    patch_content = content_fn()
    system_prompt = build_system_prompt(patch_content)

    token_est = len(system_prompt) // 4
    print(f"\n{'=' * 60}")
    print("PATCH NOTES STRESS TEST")
    print(f"  Hypothesis: {label}")
    print(f"  System prompt: {len(system_prompt)} chars (~{token_est} tokens)")
    print(f"  Patch content: {len(patch_content)} chars (~{len(patch_content) // 4} tokens)")
    print(f"{'=' * 60}")

    # Select tests
    if test_name:
        cases = [t for t in ALL_CASES if t.name == test_name]
        if not cases:
            print(f"ERROR: test '{test_name}' not found. Available: {[t.name for t in ALL_CASES]}")
            sys.exit(1)
    else:
        cases = ALL_CASES

    print(f"\nRunning {len(cases)} tests...\n")

    all_results = []
    for test in cases:
        result = run_test(client, test, system_prompt)
        all_results.append(result)

    # Summary stats
    total_errors = sum(1 for r in all_results if r.get("error"))
    avg_elapsed = sum(r["elapsed"] for r in all_results) / max(len(all_results), 1)

    print(f"\n{'=' * 60}")
    print(f"DONE: {hypothesis_key.upper()} — {label}")
    print(f"  Tests run: {len(all_results)}")
    print(f"  Errors: {total_errors}")
    print(f"  Avg response time: {avg_elapsed:.1f}s")
    print(f"  Token estimate: ~{token_est} tokens")
    print(f"{'=' * 60}")

    # Save raw results to JSON for offline review
    if save_path:
        import json

        output = {
            "hypothesis": hypothesis_key,
            "label": label,
            "token_est": token_est,
            "prompt_chars": len(system_prompt),
            "patch_chars": len(patch_content),
            "results": [
                {"name": r["name"], "response": r["response"], "elapsed": r["elapsed"]}
                for r in all_results
            ],
        }
        with open(save_path, "w") as f:
            json.dump(output, f, indent=2)
        print(f"\n  Results saved to: {save_path}")

    return {
        "hypothesis": hypothesis_key,
        "total": len(all_results),
        "errors": total_errors,
        "avg_elapsed": avg_elapsed,
        "token_est": token_est,
        "results": all_results,
    }


# =============================================================================
# Main
# =============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Patch notes stress test with A/B hypothesis comparison"
    )
    parser.add_argument(
        "--hypothesis",
        "-H",
        type=str,
        default="a",
        choices=list(HYPOTHESES.keys()),
        help="Hypothesis to test (default: a)",
    )
    parser.add_argument("--test-name", "-t", type=str, help="Run specific test by name")
    parser.add_argument("--save", "-s", type=str, help="Save results to JSON file")
    parser.add_argument("--list-tests", action="store_true", help="List all test names and exit")
    args = parser.parse_args()

    if args.list_tests:
        for test in ALL_CASES:
            print(f"  {test.name:<32s} {test.notes[:60]}")
        return

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("ERROR: GOOGLE_API_KEY not set")
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    run_suite(client, args.hypothesis, test_name=args.test_name, save_path=args.save)


if __name__ == "__main__":
    main()
