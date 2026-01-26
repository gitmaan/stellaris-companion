## Context Loading
Study @docs/CODEBASE_CLEANUP_FINDINGS.md for the comprehensive analysis.
Study @CLAUDE.md for project patterns.

## Planning Goal
The planning for this loop is already complete. The stories in fix_plan.json were derived from a 6-agent exploration that covered:

1. Dead code analysis
2. Regex → Rust migration status
3. Inconsistent patterns (logging, docstrings, quotes)
4. TODO/FIXME comments
5. Test coverage gaps
6. Hardcoded values

## Story Summary

| ID | Title | Priority | Purpose |
|----|-------|----------|---------|
| GHR-001 | Fix .gitignore and artifacts | 1 | Clean repo |
| GHR-002 | Move experiments to experiments/ | 2 | Separate product from research |
| GHR-003 | Delete dead personality.py v1 | 3 | Remove unused code |
| GHR-004 | Handle build_personality_prompt_v2 | 3 | Remove or relocate |
| GHR-005 | Delete deprecated companion methods | 3 | Remove unused code |
| GHR-006 | Docstrings for conversation.py | 4 | Code quality |
| GHR-007 | Docstrings for reporting.py | 4 | Code quality |
| GHR-008 | Standardize logging | 5 | Consistency |
| GHR-009 | Run black formatter | 5 | Code style |
| GHR-010 | Fix hardcoded paths | 6 | Portability |
| GHR-011 | Tests for signals.py | 7 | Test coverage |
| GHR-012 | Tests for events.py | 7 | Test coverage |

## Skip to Build Phase
Since planning is complete, proceed directly to RALPH_BUILD.md.

Output:
<ralph>PLANNING_COMPLETE</ralph>
