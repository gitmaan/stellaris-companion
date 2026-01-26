## Context Loading
Study @docs/CODEBASE_CLEANUP_FINDINGS.md for the full analysis and rationale.
Study @specs/github-readiness/fix_plan.json to understand stories and patterns.
Study @CLAUDE.md for project patterns.

## Goals
1. **Clean public repo** - No artifacts, experiments clearly separated
2. **No dead code** - Remove unused functions before publishing
3. **Consistent style** - Docstrings, logging, formatting
4. **Basic test coverage** - Critical modules have tests

## Your Task
From @specs/github-readiness/fix_plan.json, choose the SINGLE highest-priority story where `passes: false`.

## Before Implementation (CRITICAL)
1. Read the `patterns` array in fix_plan.json - these are learnings from previous iterations
2. For dead code deletion, VERIFY the function is actually unused (grep for calls)
3. For file moves, ensure imports are updated
4. Run tests after changes to verify nothing broke

## Implementation Patterns

### For GHR-001 (gitignore and artifacts):
```bash
# Check if any artifacts are tracked
git ls-files --cached | grep 'stellaris-parser/target/'
git ls-files --cached | grep '_results.md$'

# If tracked, remove from index (keeps local files)
git rm --cached -r stellaris-parser/target/
git rm --cached *_results.md
```

### For GHR-002 (move experiments):
```bash
# Create experiments directory
mkdir -p experiments

# Move files (use git mv to preserve history)
git mv test_fresh_stress.py experiments/
git mv test_tool_stress.py experiments/
git mv test_option_a.py experiments/
git mv test_optimized_prompt.py experiments/
git mv test_optimized_vs_production.py experiments/
git mv benchmark_option_b.py experiments/
git mv benchmark_comparison.py experiments/

# Update any imports in moved files
# Look for: from personality import ... (may need adjustment)
```

### For GHR-003 (delete dead personality code):
The following functions are CONFIRMED DEAD (never called):
- `build_personality_prompt()` (line ~329)
- `_build_standard_personality()` (line ~359)
- `_build_machine_personality()` (line ~404)
- `_build_hive_mind_personality()` (line ~437)
- `_build_situational_tone()` (line ~465)
- `_build_tool_instructions()` (line ~502)

DO NOT DELETE (these ARE used):
- `load_patch_notes()` - used by `_build_game_context_block()`
- `get_available_patches()` - used by `load_patch_notes()`
- `_build_machine_optimized()` - used by `build_optimized_prompt()`
- `_build_hive_optimized()` - used by `build_optimized_prompt()`
- `build_optimized_prompt()` - THE production function

### For GHR-004 (v2 function):
`build_personality_prompt_v2()` is only used by `test_optimized_vs_production.py`.
If that test is moved to experiments/, the v2 function can be deleted.
Otherwise, keep it for the test.

### For GHR-005 (deprecated companion methods):
Delete these from backend/core/companion.py:
- `get_full_briefing()` - marked DEPRECATED
- `chat_async()` - never called

### For GHR-006/007 (docstrings):
Add module-level docstring and class/function docstrings.
Follow the pattern in backend/core/companion.py (98% coverage).

Example:
```python
"""Conversation management for multi-turn chat sessions.

Handles turn tracking, context management, and session timeouts.
"""
from __future__ import annotations

class ConversationManager:
    """Manages multi-turn conversations with context and timeout handling.

    Attributes:
        max_turns: Maximum turns before session reset
        timeout_minutes: Minutes of inactivity before timeout
    """
```

### For GHR-008 (logging):
The print() calls in ingestion_worker.py write to stderr for timing diagnostics.
This is acceptable for worker processes. Either:
1. Keep as-is (stderr prints are intentional for timing)
2. Or replace with logger.debug() calls

### For GHR-009 (black formatter):
```bash
pip3 install black
black backend/ stellaris_save_extractor/ personality.py save_extractor.py
```

### For GHR-010 (hardcoded paths):
Replace:
```python
save_path = Path("/Users/avani/stellaris-companion/test_save.sav")
```
With:
```python
save_path = Path(__file__).parent.parent / "test_save.sav"
# Or use environment variable
save_path = Path(os.environ.get("TEST_SAVE_PATH", "test_save.sav"))
```

### For GHR-011/012 (tests):
Create minimal tests that verify:
1. Functions can be imported
2. Functions return expected structure with mock data
3. No exceptions on basic inputs

Example for signals.py:
```python
"""Tests for backend.core.signals module."""
import pytest
from unittest.mock import MagicMock

def test_build_snapshot_signals_returns_dict():
    """Verify build_snapshot_signals returns expected structure."""
    from backend.core.signals import build_snapshot_signals

    # Create mock extractor
    extractor = MagicMock()
    extractor.get_leaders.return_value = {"leaders": []}
    extractor.get_wars.return_value = {"wars": []}
    # ... other mocks

    briefing = {"meta": {"player_id": 0}}

    result = build_snapshot_signals(extractor=extractor, briefing=briefing)

    assert isinstance(result, dict)
    assert "format_version" in result
    assert "leaders" in result
```

## Verifying Criteria

Before marking a story as passing:
1. Run EACH criterion command manually
2. If criterion fails, fix the implementation
3. Only set `passes: true` when ALL criteria pass

## After Implementation
1. Verify EACH criterion passes
2. Run: `python3 -c "from backend.core.companion import StrategicCompanion; print('OK')"` (basic import test)
3. If ALL criteria pass:
   - Set `passes: true` in fix_plan.json
   - Add any new patterns learned to `patterns` array
   - `git add <specific-files> && git commit -m "[type]([scope]): [description]"`
4. If ANY criterion fails:
   - Document issue in story's `notes` field
   - Do NOT set `passes: true`

## Rules
- ONE story per iteration only
- Verify function usage before deleting (grep for calls)
- Use `git mv` for file moves to preserve history
- Run import tests after deletions
- NEVER use `git add -A` or `git add .`
- Test with python3, not bare python

## Signs (Learned Guardrails)
- build_optimized_prompt() is THE active function, not build_personality_prompt
- load_patch_notes() IS used (by _build_game_context_block)
- _build_machine_optimized() and _build_hive_optimized() ARE used
- Print to stderr in worker processes is acceptable for timing

## Completion
Output exactly this when ALL stories have `passes: true`:
<ralph>PLAN_COMPLETE</ralph>

Output exactly this after completing ONE story successfully:
<ralph>ITERATION_DONE</ralph>
