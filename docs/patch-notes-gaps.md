# Patch Notes System

How the advisor stays accurate across Stellaris versions.

## The Problem

Stellaris 4.0 "Phoenix" overhauled nearly every core system. Population scaled by 100x, Trade replaced Energy as the market currency, the strata hierarchy was renamed, and workforce math changed from 1:1 to 100:1. The LLM advisor (Gemini 3 Flash) was trained on pre-4.0 data, so without correction it gives confidently wrong answers — calling 94,000 pops "physically impossible" or telling players that one pop fills one job.

Patch notes injected into the system prompt fix this. They give the model ground-truth facts about how mechanics actually work in the player's game version.

## How It Works

Each major Stellaris version has a corresponding file in `patches/`:

```
patches/
  4.0.md   Stellaris 4.0 "Phoenix"
  4.1.md   Stellaris 4.1 "Lyra"
  4.2.md   Stellaris 4.2 "Corvus"
  4.3.md   Stellaris 4.3 "Cetus"
```

When the advisor builds its system prompt, `load_patch_notes()` in `stellaris_companion/personality.py` reads the player's game version from their save file and loads all patch files cumulatively up to that version. A player on v4.2 gets 4.0 + 4.1 + 4.2 concatenated. The content is injected into the `[GAME MECHANICS]` block of the system prompt with an instruction to treat it as ground truth and never reference patches or changes.

Lines starting with `#` (markdown headers) or `<!--` (HTML comments) are stripped during loading. Headers exist only for human readability of the files — the model sees flat content.

## Content Format

We A/B tested two formatting approaches with 15 adversarial test cases and live Gemini 3 Flash API calls:

| Approach | Format | Score | Tokens |
|----------|--------|-------|--------|
| Baseline | No patch notes | 3/13 pass | ~219 |
| A: Compact bullets | Terse bullets (4.3 style) | 10/13 pass | ~2,041 |
| **B: Structured tables** | **Reference tables + bullets** | **12/13 pass** | **~1,550** |

Structured tables won on both accuracy and token efficiency. Tables give the model a lookup structure for key numbers ("is 94k pops normal?" maps to a table row) and compartmentalize information so mechanics don't leak into unrelated questions.

The test script is at `scripts/experiments/patch_notes_stress.py`. It runs standalone Gemini API calls with crafted system prompts and collects responses for manual review.

### Format by file

**4.0.md** uses reference tables for the fundamental system overhaul — the numbers the model needs to anchor on:

- Pop Scale (empire start through late-game benchmarks)
- Workforce Conversion (pops per job, job efficiency)
- Strata Hierarchy (Elites/Specialist/Worker/Civilian)
- Trade System (market currency, deficit mechanics, ship upkeep)
- District Specializations (slot counts, jobs per slot)

Below the tables, standard bullets cover other 4.0 mechanics (growth, colonies, zones, MegaCorp, Empire Focus).

**4.1.md, 4.2.md, 4.3.md** use terse bullets only, since they're incremental changes building on the 4.0 baseline.

### Writing rules

All patch files follow the same conventions:

- **Present-tense facts only.** Never use change language ("no longer", "used to", "was changed", "patch"). The model should present mechanics as how the game works, not as things that changed.
- **Parenthetical strategic implications** at the end of bullets where useful, e.g. "(Early colonies require military protection.)"
- **Concrete numbers inline.** Don't say "a lot of pops" — say "80,000-120,000 pops."
- **Section headers by gameplay domain** (`### Population & Growth`, `### Trade & Logistics`, etc.) for human readability. These are stripped before injection.

## Content Selection

Not everything from official patch notes belongs here. The advisor needs mechanics that affect strategic advice, not every balance tweak.

**Tier 1 (must include):** System-level changes that cause wrong advice without correction. Pop scaling, workforce math, market currency, strata names.

**Tier 2 (should include):** Mechanics the advisor might reference in strategy. Colony development time, MegaCorp branch offices, trade deficit cascading, district specialization slots.

**Tier 3 (skip):** Balance numbers, exploit fixes, performance changes, modding fields, UI tooltip adjustments. These don't affect the advisor's ability to give correct strategic guidance.

## Adding a New Patch Version

1. Create `patches/{major}.{minor}.md` with the `# Stellaris X.Y "Name" Game Mechanics` header and `<!-- LLM-transformed -->` comment.
2. Write present-tense facts covering Tier 1 and Tier 2 content. Use terse bullets unless the patch introduces a fundamental system overhaul (in which case, reference tables).
3. Run the stress test to verify: `PYTHONPATH=. python3 scripts/experiments/patch_notes_stress.py --hypothesis real -v`
4. Check that unrelated questions (fleet comp, federation mechanics, lore) don't leak the new content.

## Sources

Patch file content is compiled from:

- Official Stellaris patch notes (Paradox Interactive)
- Dev Diaries on Steam and Paradox Forums
- Stellaris Wiki patch pages
- Community guides (e.g. Paradox Forums economy threads)
- Hotfix patch notes (4.0.13, 4.1.5, 4.2.2-4.2.4)
