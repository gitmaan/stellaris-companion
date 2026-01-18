## Context Loading
Study @specs/electron-app/* to learn the specifications.
Study existing source code in backend/ and electron/ directories.

## Your Task
Use up to 50 parallel subagents to:
1. Study existing source code
2. Compare against specifications
3. Search for TODO, FIXME, placeholders, minimal implementations
4. Identify gaps between spec and implementation

Create/update @specs/electron-app/fix_plan.json with:
- Stories ordered by priority (lower = more important)
- Each story has explicit, testable acceptance criteria
- Preserve any existing `patterns` array
- Consider what's blocking other items

## Criteria Guidelines
Good criteria are testable:
- "typecheck passes" (run pnpm run typecheck:api)
- "python -c 'from backend.api.server import create_app' succeeds"
- "GET /api/health returns status field"
- "npm run build in electron/renderer succeeds"

Bad criteria are vague:
- "auth works" (how do you verify?)
- "looks good" (subjective)
- "implemented correctly" (not testable)

## Story ID Prefixes
- API-xxx: Python FastAPI endpoints
- ELEC-xxx: Electron main process
- UI-xxx: React renderer components
- PKG-xxx: Packaging and build
- INT-xxx: Integration tests

## Priority Guidelines
- Priority 1: Core functionality that blocks other work (API server, auth)
- Priority 2: Main features (Electron scaffold, React scaffold)
- Priority 3: UI components (pages, widgets)
- Priority 4: Polish (styling, packaging)
- Priority 5: Integration testing

Think extra hard. Use subagents for thorough search.

Do NOT assume items are not implemented - SEARCH FIRST.

## Completion
Output exactly this when planning is complete:
<ralph>PLANNING_DONE</ralph>
