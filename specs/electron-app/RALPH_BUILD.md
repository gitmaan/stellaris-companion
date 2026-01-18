## Context Loading
Study @specs/electron-app/* to learn the specifications.
Study @specs/electron-app/fix_plan.json to understand stories and patterns.
Study @specs/electron-app/AGENT.md to learn how to build and test.
Study @CLAUDE.md for project patterns.
Check for AGENTS.md in any directory you plan to modify.

## Your Task
From @specs/electron-app/fix_plan.json, choose the SINGLE highest-priority story where `passes: false`.

## Before Implementation (CRITICAL FOR EXISTING CODEBASES)
1. Read @CLAUDE.md thoroughly - it has all project patterns
2. Read the `patterns` array in @specs/electron-app/fix_plan.json - these are learnings from previous iterations
3. Search for SIMILAR existing code using subagents (e.g., "how does companion.py handle errors?")
4. Read 2-3 examples of similar features in the codebase
5. Follow existing patterns EXACTLY - DO NOT invent new approaches
6. Check how errors are handled in similar code
7. DON'T ASSUME something isn't implemented - SEARCH FIRST

## Existing Code to Reuse
- `backend/core/companion.py` - Companion class with ask_precomputed(), get_status_data(), etc.
- `backend/core/database.py` - GameDatabase class with session/snapshot/event methods
- `backend/core/save_watcher.py` - SaveWatcher class for file monitoring
- `backend/core/conversation.py` - ConversationManager for chat history
- `personality.py`, `save_extractor.py`, `save_loader.py` - Data extraction

## After Implementation
1. Verify EACH criterion in the story's `criteria` array
2. Run tests per AGENT.md for the unit you changed
3. If ALL criteria pass:
   - Set `passes: true` for this story in @specs/electron-app/fix_plan.json
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

Example triggers:
- "FastAPI routes need dependency injection via app.state"
- "IPC handlers must return serializable objects"

## Self-Improvement
- Update @specs/electron-app/AGENT.md when you learn something new about building/testing
- Add to `patterns` array in fix_plan.json for cross-cutting learnings
- Create per-directory AGENTS.md for localized patterns (3+ patterns threshold)
- Capture WHY in docstrings and test descriptions

## Rules
- ONE story per iteration only - this is critical
- NO placeholder or minimal implementations - FULL implementations only
- ALL criteria must pass before setting `passes: true`
- Use subagents for search operations (up to 50 parallel)
- Use only 1 subagent for build/test (backpressure)
- Search before creating - don't assume not implemented
- When tests unrelated to your work fail, fix them

## Signs (Learned Guardrails)
- NEVER use `git add -A` or `git add .` - commits unrelated files and pollutes history
- Only `git add` the specific files you changed in this iteration
- Verify EVERY criterion before marking passes: true
- Companion class requires GOOGLE_API_KEY - check for it before instantiation
- FastAPI app must be created via create_app() factory for dependency injection
- IPC handlers receive (event, args) - don't forget the event parameter
- Renderer never imports 'electron' directly - use window.electronAPI from preload

## Project Patterns (from CLAUDE.md)
- LLM: Use gemini-3-flash-preview (not gemini-2.0-flash)
- Save files can be ~70MB - use smart extraction, not full context
- Discord messages limited to 2000 chars - split long responses
- Privacy-first: saves stay local, no uploads
- Universal compatibility: must work with any empire type, game stage, mods
- CLI: python v2_native_tools.py
- Discord bot: python backend/main.py
- Key files: save_extractor.py, personality.py, backend/core/companion.py

## Completion
Output exactly this when ALL stories in @specs/electron-app/fix_plan.json have `passes: true`:
<ralph>PLAN_COMPLETE</ralph>

Output exactly this after completing ONE story successfully:
<ralph>ITERATION_DONE</ralph>
