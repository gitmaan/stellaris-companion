## Context Loading
Study @specs/rust-session-mode/REGEX_MIGRATION_ANALYSIS.md for the full analysis.
Study @specs/rust-session-mode/MIGRATION_PATTERN.md for the established migration pattern.
Study @stellaris-parser/src/commands/serve.rs for current Rust implementation.
Study @rust_bridge.py for Python session implementation.
Study existing Rust-migrated functions: `_analyze_player_fleets_rust`, `_get_fallen_empires_rust`.

## Your Task
Use subagents to:
1. Review current regex usage in extractor files
2. Identify functions that haven't been migrated yet
3. Check for fixed-size limits (truncation risks)
4. Verify what Rust primitives exist vs what's needed

Update @specs/rust-session-mode/fix_plan.json with:
- Stories ordered by priority (lower = more important)
- Each story has explicit, testable acceptance criteria
- Preserve existing `patterns` array

## Criteria Guidelines
Good criteria are testable:
- "RUN: grep -q 'pattern' file.py (pattern exists)"
- "RUN: cargo test (tests pass)"
- "RUN: python3 -c 'code' (specific behavior works)"

Bad criteria are vague:
- "regex is removed" (how do you verify?)
- "works correctly" (not testable)

## Current State

**Completed:**
- Session mode basics (iter_section, count_keys, contains_tokens)
- `get_fallen_empires()` - Rust version exists
- `_analyze_player_fleets()` - Rust version exists
- `get_crisis_status()` - uses count_keys
- `get_leviathans()` - uses contains_tokens

**Needed Rust Primitives:**
- `get_entry(section, key)` - single entry lookup
- `get_entries(section, keys, fields)` - batch lookup with projection
- `contains_kv(key, value)` - whitespace-insensitive k=v check

**High-Priority Migrations:**
- `get_diplomacy()` - 80KB truncation risk on relations
- `get_military_summary()` - fleet/war data
- `get_planets()` - complex nested structures

## Completion
Output exactly this when planning is complete:
<ralph>PLANNING_DONE</ralph>
