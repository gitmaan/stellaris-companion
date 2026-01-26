## Context Loading
Study @docs/OPTION_D_UNIFIED_HISTORY_EXTRACTION.md for the full architecture proposal.
Study @backend/core/history.py for current regex-based extraction (the "bad path").
Study @stellaris_save_extractor/leaders.py for Rust-backed extraction with name resolution (the "good path").
Study @backend/core/ingestion_worker.py for where signals should be built.
Study @backend/core/events.py for where resolved names should be used.
Study @CLAUDE.md for project patterns.

## Problem Summary

Chronicle generates poor narratives with placeholder names like `%LEADER_2%` or fabricated names because:
1. **Two extraction paths exist**: SaveExtractor (Rust, resolves names) vs history.py (regex, no resolution)
2. **Chronicle depends on events**, events depend on history, history uses the "bad path"
3. **70MB gamestate loaded** just to run regex for history enrichment (performance bottleneck)

## Solution: Push Extraction Upstream

Build `SnapshotSignals` once per snapshot in the ingestion worker (where Rust session is active), using SaveExtractor methods. History module becomes pure diffing.

## Your Task
Review the current state and verify/update @specs/unified-history-extraction/fix_plan.json:

1. Check that signals.py doesn't already exist
2. Verify ingestion_worker.py still uses gamestate for history
3. Confirm events.py uses name_key (not name) for leader events
4. Ensure leaders.py has _extract_leader_name_rust() we can reference
5. Update criteria if any assumptions are wrong

Use subagents for search operations.

## Criteria Guidelines
Good criteria are testable:
- "RUN: test -f path/file.py (file exists)"
- "RUN: grep -q 'pattern' file.py (pattern exists)"
- "RUN: python3 -c 'code' (specific behavior works)"

Bad criteria are vague:
- "names are resolved" (how do you verify?)
- "works correctly" (not testable)

## Completion
Output exactly this when planning is complete:
<ralph>PLANNING_DONE</ralph>
