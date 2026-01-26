## Context Loading
Study @specs/rust-session-mode/REGEX_MIGRATION_ANALYSIS.md to understand remaining work and priorities.
Study @specs/rust-session-mode/MIGRATION_PATTERN.md for the 7-step migration process.
Study @specs/rust-session-mode/fix_plan.json to understand stories and patterns.
Study @CLAUDE.md for project patterns.
Study @stellaris-parser/src/commands/serve.rs for Rust session implementation.
Study @rust_bridge.py for Python session implementation.

## Phase 2 Goals
1. **No raw gamestate in hot path** - Remove self.gamestate access from briefing flow
2. **Eliminate _extract_section()** - Migrate callers to extract_sections()/iter_section()
3. **Fix duplicate-key accuracy** - Add Rust op for leader traits
4. **Reduce IPC overhead** - Multi-op requests, then orjson
5. **Compatibility guardrails** - Save corpus tests, diagnostics export

## Your Task
From @specs/rust-session-mode/fix_plan.json, choose the SINGLE highest-priority story where `passes: false`.

## Before Implementation (CRITICAL)
1. Read the `patterns` array in fix_plan.json - these are learnings from previous iterations
2. Read MIGRATION_PATTERN.md for the established migration workflow
3. Search for SIMILAR existing code (e.g., `_analyze_player_fleets_rust` as reference)
4. Follow existing patterns EXACTLY

## Migration Pattern (from MIGRATION_PATTERN.md)

For function migrations (MIG-004+), follow this 7-step process:

```
1. BASELINE    → Run original, capture output to /tmp/baseline.json
2. ANALYZE     → Understand data structure via Rust session
3. IMPLEMENT   → Write _function_rust() using iter_section/dict access
4. COMPARE     → Verify output matches baseline exactly
5. BENCHMARK   → Measure speedup (target: 3-10x faster)
6. DISPATCH    → Update original to call Rust version when session active
7. FALLBACK    → Keep _function_regex() for non-session use
```

## Code Structure Template

```python
def some_function(self, args) -> dict:
    """Docstring unchanged."""
    session = _get_active_session()
    if session:
        return self._some_function_rust(args)
    return self._some_function_regex(args)

def _some_function_rust(self, args) -> dict:
    """Rust-optimized version."""
    session = _get_active_session()
    if not session:
        return self._some_function_regex(args)

    for entry_id, entry in session.iter_section('section'):
        if not isinstance(entry, dict):  # P010: handle "none" strings
            continue
        value = entry.get('field')  # P011: use .get() with defaults
    return result

def _some_function_regex(self, args) -> dict:
    """Original regex implementation - fallback."""
    # Original code moved here unchanged
```

## Key Implementation Details

### Rust Primitives (serve.rs)
- `iter_section(section, batch_size)` - iterate entries
- `get_entry(section, key)` - single entry lookup (MIG-001)
- `get_entries(section, keys, fields)` - batch lookup (MIG-002)
- `contains_kv(key, value)` - whitespace-insensitive check (MIG-003)
- `count_keys(keys)` - count occurrences
- `contains_tokens(tokens)` - Aho-Corasick string presence

### Python (rust_bridge.py)
- RustSession class manages subprocess
- `_get_active_session()` returns thread-local session or None

### Cargo
- Located at ~/.cargo/bin/cargo (not in PATH)
- Build: `cd stellaris-parser && ~/.cargo/bin/cargo build --release`

## Verifying Criteria (Self-Healing)

Before executing ANY criterion:
1. **Check patterns** - Read `patterns` array in fix_plan.json
2. **Detect conflicts** - Does criterion conflict with learned patterns?
3. **Self-heal** - If conflict: UPDATE criterion, add pattern, then execute
4. **Handle failures** - Find working alternative, update criterion, add pattern

## After Implementation
1. Verify EACH criterion (self-heal if needed)
2. Build Rust: `cd stellaris-parser && ~/.cargo/bin/cargo build --release`
3. Run Rust tests: `cd stellaris-parser && ~/.cargo/bin/cargo test`
4. For function migrations: Compare output with baseline
5. If ALL criteria pass:
   - Set `passes: true` in fix_plan.json
   - Add patterns to `patterns` array
   - `git add <specific-files> && git commit -m "[type]([scope]): [description]"`
6. If ANY criterion fails after self-healing:
   - Document in story's `notes` field
   - Do NOT set `passes: true`

## Rules
- ONE story per iteration only
- NO placeholder implementations - FULL implementations only
- ALL criteria must pass before setting `passes: true`
- Use subagents for search operations
- NEVER use `git add -A` or `git add .`

## Signs (Learned Guardrails)
- Cargo is at ~/.cargo/bin/cargo, not in PATH
- Use python3, not bare python
- serve.rs stdout is for protocol only, use stderr for logs
- Entry might be string "none" - check isinstance(entry, dict)
- Use .get() with defaults, never direct [] access
- Fields can be str, int, float, dict, or list
- Entry IDs from iter_section are strings
- Test save is at test_save.sav in project root
- Reference implementations: `_analyze_player_fleets_rust`, `_get_fallen_empires_rust`

## Completion
Output exactly this when ALL stories have `passes: true`:
<ralph>PLAN_COMPLETE</ralph>

Output exactly this after completing ONE story successfully:
<ralph>ITERATION_DONE</ralph>
