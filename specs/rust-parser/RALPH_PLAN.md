## Context Loading
Study @specs/rust-parser/* to learn the specifications.
Study @docs/RUST_PARSER_ARCHITECTURE.md for the full architecture.
Study existing source code in stellaris-parser/ if it exists.

## Your Task
Use up to 50 parallel subagents to:
1. Study @docs/RUST_PARSER_ARCHITECTURE.md for requirements
2. Check stellaris-parser/ directory for existing implementation
3. Search for TODO, FIXME, placeholders, minimal implementations
4. Identify gaps between spec and implementation
5. Check rust_bridge.py for Python integration status

Create/update @fix_plan.json with:
- Stories ordered by priority (lower = more important)
- Each story has explicit, testable acceptance criteria
- Preserve any existing `patterns` array
- Consider what's blocking other items

## Criteria Guidelines
Good criteria are testable:
- "cargo build --release succeeds"
- "extract-save command outputs valid JSON"
- "Exit code 2 on parse error"
- "rust_bridge.py extract_sections() returns dict"

Bad criteria are vague:
- "parsing works" (how do you verify?)
- "handles edge cases" (which ones?)
- "implemented correctly" (not testable)

## Story Categories
- RUST-xxx: Core Rust CLI implementation
- INT-xxx: Python integration
- BUILD-xxx: CI/CD and distribution
- TEST-xxx: Testing infrastructure

Think extra hard. Use subagents for thorough search.

Do NOT assume items are not implemented - SEARCH FIRST.

## Completion
Output exactly this when planning is complete:
<ralph>PLANNING_DONE</ralph>
