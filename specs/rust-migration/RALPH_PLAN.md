# Rust Migration - Plan Mode

## Context Loading
Study @specs/rust-migration/overview.md for migration goals.
Study @specs/rust-migration/validation-approach.md for validation process.
Study @stellaris_save_extractor/*.py to understand current extractors.
Study @rust_bridge.py to understand Rust parser interface.

## Your Task
Use up to 50 parallel subagents to:
1. Analyze all extractor files in stellaris_save_extractor/
2. Count regex usages per file
3. Identify which methods need migration
4. Check existing baselines in tests/migration_baselines/
5. Identify dependencies between extractors

Create/update @specs/rust-migration/fix_plan.json with:
- Stories ordered by priority (lower = more important)
- Each story has explicit, testable acceptance criteria using RUN: prefix
- Preserve any existing `patterns` array
- Consider what's blocking other items

## Criteria Guidelines

Good criteria are testable with RUN: prefix:
- `RUN: python3 scripts/capture_baseline.py <method> (baseline saved)`
- `RUN: python3 scripts/validate_migration.py <method> (matches or improves)`
- `RUN: grep 'extract_sections' stellaris_save_extractor/<file>.py (Rust calls present)`
- `RUN: grep 'ParserError' stellaris_save_extractor/<file>.py (fallback present)`

Bad criteria are vague:
- "migration works" (how do you verify?)
- "output is correct" (not testable)
- "implemented properly" (subjective)

## Priority Guidelines

Priority 1: Core methods (player, planets, military, diplomacy, economy)
Priority 2: Secondary methods (species, leaders, technology, armies)
Priority 3: Tertiary methods (endgame, politics, projects, leviathans, base)
Priority 4: Final validation and cleanup

## Completion

Output exactly this when planning is complete:
<ralph>PLANNING_DONE</ralph>
