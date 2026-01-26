## Context Loading
Study @specs/rust-parser/* to learn the specifications.
Study @fix_plan.json to understand stories and patterns.
Study @AGENT.md to learn how to build and test.
Study @CLAUDE.md for project patterns.
Study @docs/RUST_PARSER_ARCHITECTURE.md for the full architecture decision record.
Check for AGENTS.md in any directory you plan to modify.

## Your Task
From @fix_plan.json, choose the SINGLE highest-priority story where `passes: false`.

## Before Implementation (CRITICAL)
1. Read @CLAUDE.md thoroughly - it has all project patterns
2. Read the `patterns` array in @fix_plan.json - these are learnings from previous iterations
3. Read @docs/RUST_PARSER_ARCHITECTURE.md for detailed interface specifications
4. If implementing Rust code, check jomini library docs and examples
5. For Python integration, read existing save_extractor.py for patterns
6. DON'T ASSUME something isn't implemented - SEARCH FIRST

## Project Patterns (from CLAUDE.md)
- Save files can be ~70MB - use smart extraction, not full context
- Privacy-first: saves stay local, no uploads
- Universal compatibility: must work with any empire type, game stage, mods
- Commit style: imperative mood ("Add", "Fix", "Implement")

## Rust Specifics
- Use jomini 0.28+ for Clausewitz parsing
- Use clap 4 with derive feature for CLI
- Use anyhow for error handling
- Output JSON via serde_json
- Keep stderr bounded (single JSON error object)

## Verifying Criteria

Criteria use these formats:
- `RUN: <command> (<expected result>)` - Execute the command and verify the expected result
- `Code review: <what to check>` - Manually verify in source code

**CRITICAL - Self-Healing Criteria:**
Before executing a criterion, check if it conflicts with learned patterns:
1. If a path in the criterion doesn't exist, check patterns for the correct path
2. If a command fails (e.g., `python` not found), find the working alternative (e.g., `venv/bin/python`)
3. **UPDATE the criterion in fix_plan.json** with the corrected command
4. Add a pattern documenting the fix for future iterations
5. Then execute the corrected criterion

For RUN criteria:
1. Check for conflicts with patterns array first
2. Fix the command if needed (update fix_plan.json)
3. Execute the (possibly corrected) command
4. Check the output matches the expected result in parentheses
5. If a command fails after correction attempts, the criterion FAILS

Example:
- `RUN: cargo test (all tests pass)` → Run cargo test, verify exit code 0
- `RUN: jq .schema_version (returns 1)` → Verify jq outputs 1
- `RUN: echo $? (exit code 1)` → Verify previous command exited with 1

## After Implementation
1. Execute EACH `RUN:` command and verify expected result
2. Perform EACH `Code review:` check
3. If ALL criteria pass:
   - Set `passes: true` for this story in @fix_plan.json
   - Add any discovered patterns to the `patterns` array
   - Add any new issues to the `discovered` array
   - git add <specific-files-you-changed> && git commit -m "[type]([scope]): [description]"
   - NEVER use `git add -A` or `git add .` - only add files you actually modified
4. If ANY criterion fails:
   - Document which criterion failed in the story's `notes` field
   - Do NOT set `passes: true`

## Per-Directory AGENTS.md
When you discover 3+ patterns specific to ONE directory:
1. Create or update `[directory]/AGENTS.md`
2. Add patterns that future iterations should know
3. Only add reusable knowledge, not story-specific notes

## Self-Improvement
- Update @AGENT.md when you learn something new about building/testing
- Add to `patterns` array in fix_plan.json for cross-cutting learnings
- Create per-directory AGENTS.md for localized patterns (3+ patterns threshold)

## Rules
- ONE story per iteration only - this is critical
- NO placeholder or minimal implementations - FULL implementations only
- ALL criteria must pass before setting `passes: true`
- Use subagents for search operations (up to 50 parallel)
- Use only 1 subagent for build/test (backpressure)
- Search before creating - don't assume not implemented
- When tests unrelated to your work fail, fix them

## Story Categories
- RUST-xxx: Core Rust CLI implementation (Phase 1)
- INT-xxx: Python integration with rust_bridge.py (Phase 2)
- MIG-xxx: Migrate Python extractors to use Rust (Phase 3)
- BUILD-xxx: CI/CD and GitHub Actions
- DIST-xxx: Distribution and packaging (Phase 4)
- TEST-xxx: Testing infrastructure

## Signs (Learned Guardrails)
- NEVER use `git add -A` or `git add .` - commits unrelated files and pollutes history
- Only `git add` the specific files you changed in this iteration
- Verify EVERY criterion before marking passes: true
- Stellaris .sav files are ZIP archives containing gamestate and meta files
- jomini returns duplicate keys as Vec, not overwritten values
- Windows-1252 encoding and color codes need explicit validation (marked ⚠️ in architecture doc)
- RUN criteria MUST be executed - don't assume they pass, actually run the commands
- CLI tests run from project root; cargo commands run from stellaris-parser/
- test_save.sav exists in project root - use it for all validation
- Use venv/bin/python NOT python - system python doesn't exist
- Extractors are in stellaris_save_extractor/ NOT backend/extractors/
- SELF-HEAL: If criteria conflict with patterns, UPDATE the criteria first, then execute
- SELF-HEAL: If a command fails, find the working alternative, update criteria, add pattern

## Completion
Output exactly this when ALL stories in @fix_plan.json have `passes: true`:
<ralph>PLAN_COMPLETE</ralph>

Output exactly this after completing ONE story successfully:
<ralph>ITERATION_DONE</ralph>
