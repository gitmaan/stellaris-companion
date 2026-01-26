# Codebase Cleanup & Rust Migration Findings

Generated: 2026-01-24
Updated: 2026-01-24 (corrected dead code analysis after review)

This document summarizes findings from a comprehensive codebase exploration before publishing to GitHub.

## Executive Summary

| Category | Priority | Effort | Impact |
|----------|----------|--------|--------|
| Repo Hygiene (.gitignore, artifacts) | HIGH | Low | Clean public repo |
| Dead Code Removal | HIGH | Low | Clean public repo |
| Test Coverage | HIGH | High | Reliability |
| Inconsistent Patterns | MEDIUM | Medium | Maintainability |
| Regex → Rust Migration | MEDIUM | High | Performance |
| Hardcoded Values | LOW | Medium | Configurability |
| TODO/FIXME Comments | LOW | Low | Code quality |

---

## 0. Repo Hygiene (Do First)

### Missing from .gitignore

| Path | Type | Status |
|------|------|--------|
| `stellaris-parser/target/` | Rust/Cargo build output | **Added** |
| `*_results.md` | Benchmark outputs | **Added** |

### Consider Moving to `experiments/` or `notes/`

| Files | Purpose |
|-------|---------|
| `test_*.py` (root level) | Stress tests, comparisons, not unit tests |
| `benchmark_*.py` | Performance comparisons |
| Long-form experiment docs | Research notes |

---

## 1. Dead Code & Unused Functions

**Total: ~185 lines to delete** (revised down from 235)

### personality.py (Root Level)

#### CONFIRMED DEAD (Safe to Delete)

| Lines | Function | Status |
|-------|----------|--------|
| 329-357 | `build_personality_prompt()` | Old v1 entrypoint, never called |
| 359-402 | `_build_standard_personality()` | Only called by dead v1 function |
| 404-435 | `_build_machine_personality()` | Only called by dead v1 function |
| 437-463 | `_build_hive_mind_personality()` | Only called by dead v1 function |
| 465-500 | `_build_situational_tone()` | Only called by dead v1 function |
| 502-515 | `_build_tool_instructions()` | Only called by dead v1 function |
| 517-615 | `build_personality_prompt_v2()` | Test-only (test_optimized_vs_production.py) |

#### NOT DEAD (Incorrectly Flagged Earlier)

| Lines | Function | Actually Used By |
|-------|----------|------------------|
| 24-95 | `load_patch_notes()`, `get_available_patches()` | `_build_game_context_block()` → `build_optimized_prompt()` |
| 757-785 | `_build_machine_optimized()` | `build_optimized_prompt()` line 674 |
| 786-809 | `_build_hive_optimized()` | `build_optimized_prompt()` line 676 |

**Note**: The active production function is `build_optimized_prompt()` which calls the machine/hive helpers and patch loading.

### backend/core/companion.py

| Lines | Function | Status |
|-------|----------|--------|
| 620-622 | `get_full_briefing()` | Marked DEPRECATED |
| 672-683 | `chat_async()` | Never called in production |

### Recommendation

```bash
# Delete these functions before publishing
# personality.py: lines 24-95, 329-809
# companion.py: lines 620-622, 672-683
```

---

## 2. Regex → Rust Migration Status

**Total regex occurrences: 378 across 16 files**
**Migration status: ~70% complete**

### High Priority (Major Performance Gains)

| File | Function | Issue | Complexity |
|------|----------|-------|------------|
| economy.py | `get_pop_statistics()` | 50MB chunk slicing | High |
| diplomacy.py | Multiple methods | 75 regex calls | High |
| base.py | `_get_country_names_map_regex()` | Hot path, 300+ countries | High |
| military.py | `_get_fleet_composition_regex()` | Triple nested loops | High |

### Medium Priority

| File | Function | Issue |
|------|----------|-------|
| base.py | `_count_player_starbases_regex()` | 5MB windows |
| economy.py | `get_budget_breakdown()` | Recursive extraction |
| military.py | `_get_starbases_regex()` | Complex cross-reference |

### Already Migrated (Good Examples)

- `_get_planets_rust()` - Uses `session.extract_sections()`
- `_get_wars_rust()` - Uses `iter_section_entries()`
- `_get_fleets_rust()` - Uses `iter_section_entries()`
- `_get_megastructures_rust()` - Clean null handling
- `_analyze_player_fleets_rust()` - Uses batch `get_entries()`

### Intentionally Hybrid (Keep Regex)

| File | Function | Reason |
|------|----------|--------|
| species.py | `_extract_species_traits_regex()` | Clausewitz allows duplicate `trait=` keys; Rust parser keeps only last |

### Migration Patterns

**Pattern 1: Replace chunk slicing**
```python
# Before (slow)
chunk = self.gamestate[start:start + 5000000]
for match in re.finditer(pattern, chunk): ...

# After (fast)
for key, value in session.iter_section("section_name"):
    if isinstance(value, dict): ...
```

**Pattern 2: Replace brace matching**
```python
# Before (error-prone)
brace_count = 0
for i, char in enumerate(chunk): ...

# After (automatic)
entry = session.get_entry("section", entry_id)
```

**Pattern 3: Batch lookups**
```python
# Before (N queries)
for id in ids:
    snippet = chunk[start:start + 3000]
    value = re.search(pattern, snippet)

# After (1 query)
entries = session.get_entries("section", ids)
```

---

## 3. Inconsistent Patterns

### Logging (HIGH Priority)

**Issue**: Mixed `print()` and `logger` usage in backend/core

| File | Lines | Issue |
|------|-------|-------|
| companion.py | 246 | `print()` for personality build failures |
| save_watcher.py | 215, 219-231 | `print()` for user-facing output |
| ingestion_worker.py | 83, 180-195 | `print()` to stderr for timing |

**Recommendation**:
- Use `logger` for all backend/core operational logs
- Reserve `print()` for CLI-only user feedback (v2_native_tools.py)

### Docstring Coverage (MODERATE Priority)

| File | Coverage | Status |
|------|----------|--------|
| companion.py | 98% | Excellent |
| save_watcher.py | 92% | Excellent |
| chronicle.py | 85% | Good |
| database.py | 61% | Acceptable |
| history_context.py | 50% | Needs work |
| ingestion_worker.py | 20% | Needs work |
| ingestion.py | 7% | Needs work |
| conversation.py | 0% | Critical |
| reporting.py | 0% | Critical |

**Recommendation**: Add module-level and function docstrings to 0% files.

### Quote Styles (LOW Priority)

| File | Issue |
|------|-------|
| signals.py | 67% single quotes, 33% double quotes |

**Recommendation**: Run `black` formatter to normalize to double quotes.

### Import Styles (LOW Priority)

| File | Issue |
|------|-------|
| companion.py | Mixes absolute (`from save_extractor`) and relative (`from backend.core.conversation`) |

**Recommendation**: Standardize on one style throughout.

---

## 4. TODO/FIXME/HACK Comments

### Should Fix Now

| File | Line | Comment | Action |
|------|------|---------|--------|
| companion.py | 621 | `DEPRECATED: Use get_snapshot() instead` | Remove method |

### Can Defer (Legacy Support)

| File | Lines | Purpose |
|------|-------|---------|
| chronicle.py | 172, 195-210 | Legacy blob-based cache for sessions without save_id |
| chronicle.py | 1023-1031 | `_generate_legacy_chronicle()` fallback |
| database.py | 1253 | Legacy DB record handling |
| history.py | 773 | Gamestate fallback when signals unavailable |

### Reword for Clarity

| File | Line | Current | Suggested |
|------|------|---------|-----------|
| test_t25_comparison.py | 140 | `# What's in slim vs full?` | `# Compare briefing schemas` |
| diplomacy.py | 1900, 1904 | `# Is this player claiming...?` | `# Branch 1: Player's claims` |
| base.py | 563, 629 | `# Trace ownership: ship → fleet → player?` | `# Verify fleet belongs to player` |

### Keep As-Is

- **P-code references** (P010, P011, MIG-005, etc.) - Legitimate issue tracking
- **Fallback/best-effort patterns** - Architectural necessities

---

## 5. Test Coverage Gaps

### Overview

| Category | Tested | Total | Coverage |
|----------|--------|-------|----------|
| backend/core | 2 | 12 | **17%** |
| stellaris_save_extractor | 2 | 18 | **11%** |
| **Total** | **4** | **30** | **13%** |

### Tested Modules (4)

- `backend/core/ingestion.py` - Full coverage
- `backend/core/ingestion_worker.py` - Partial coverage
- `stellaris_save_extractor/extractor.py` - Via fixtures
- `stellaris_save_extractor/validation.py` - 113 test cases

### Critical Gaps (Zero Tests)

#### signals.py (13 functions)
```
build_snapshot_signals()
_extract_leader_signals()
_extract_war_signals()
_extract_diplomacy_signals()
_extract_technology_signals()
_extract_megastructures_signals()
_extract_crisis_signals()
_extract_fallen_empires_signals()
_extract_policies_signals()
_extract_edicts_signals()
_extract_galaxy_settings_signals()
_extract_galaxy_settings_rust()
_extract_systems_signals()
```

#### events.py (21+ functions)
```
compute_events()
_extract_war_names()
_extract_player_leaders()
_extract_empire_names()
_extract_diplomacy_sets()
_extract_tech_list()
_extract_policies()
_extract_megastructures()
_extract_crisis()
_extract_fallen_empires()
_extract_system_count()
```

#### Other Critical Modules
- `chronicle.py` - Narrative generation
- `companion.py` - Main LLM advisor
- `database.py` - Game history persistence
- `conversation.py` - Session management

### Missing Integration Tests

- Complete advisor pipeline (question → briefing → signals → events → response)
- Discord bot command execution
- Database history tracking across snapshots
- Conversation session management

### Missing Test Saves

Current: Only `test_save.sav` (late-game organic empire)

Needed:
- Early-game save
- Mid-game save
- Machine empire
- Hive mind empire
- With various DLC
- With popular mods
- Multiplayer save

---

## 6. Hardcoded Values

### High Priority (Machine-Specific)

| File | Line | Value | Recommendation |
|------|------|-------|----------------|
| benchmark_comparison.py | 290-316 | `/Users/avani/...` paths | Environment variable |

### Medium Priority (Should Be Configurable)

#### Game Phase Years
```python
# Found in: companion.py, briefing.py, date_utils.py
EARLY_END = 2230
MID_EARLY_END = 2300
MID_LATE_END = 2350
LATE_END = 2400
```

#### Chronicle Constants
```python
# Found in: chronicle.py lines 119-130
CHAPTER_TIME_THRESHOLD = 50
MIN_YEARS_AFTER_EVENT = 5
MAX_CHAPTERS_PER_REQUEST = 2
MAX_EVENTS_PER_CHAPTER_PROMPT = 250
MAX_EVENTS_CURRENT_ERA_PROMPT = 200
```

#### Conversation Limits
```python
# Found in: companion.py line 145
max_turns = 5
timeout_minutes = 15
max_answer_chars = 500
```

#### Ingestion Timeouts
```python
# Found in: ingestion.py lines 77-84
stable_window_seconds = 0.6
stable_max_wait_seconds = 10.0
```

#### Logging Config
```python
# Found in: electron_main.py, main.py
maxBytes = 5_000_000
backupCount = 3
```

### Low Priority (Acceptable Defaults)

- Extraction limits (function parameter defaults)
- Steam API endpoint and app ID
- Regex context window sizes

### Suggested Configuration Structure

```yaml
# config.yaml
logging:
  max_bytes: 5000000
  backup_count: 3

game_phases:
  early_end_year: 2230
  mid_early_end_year: 2300
  mid_late_end_year: 2350
  late_end_year: 2400

chronicle:
  chapter_time_threshold_years: 50
  min_years_after_event: 5
  max_chapters_per_request: 2

conversation:
  max_turns: 5
  timeout_minutes: 15

ingestion:
  stable_window_seconds: 0.6
  max_wait_seconds: 10.0
```

---

## Recommended Action Order

### Phase 1: Quick Wins (Before GitHub)
1. Delete ~235 lines of dead code in personality.py and companion.py
2. Remove `/Users/avani/` hardcoded paths
3. Reword 4 question-mark comments

### Phase 2: Code Quality
1. Add docstrings to conversation.py, reporting.py, ingestion.py
2. Standardize logging (replace print() with logger)
3. Run formatter for quote style consistency

### Phase 3: Test Coverage
1. Add tests for signals.py (13 functions)
2. Add tests for events.py (21+ functions)
3. Add tests for companion.py, chronicle.py
4. Create test save corpus (early/mid/late game, different empire types)

### Phase 4: Performance
1. Migrate `get_pop_statistics()` to Rust
2. Migrate diplomacy.py methods to Rust
3. Complete remaining regex → Rust migrations

### Phase 5: Configuration
1. Create config.yaml with game phase years, chronicle constants
2. Move remaining magic numbers to config
3. Document configuration options

---

## Files by Priority

### Must Touch Before GitHub
- `personality.py` - Delete dead code
- `backend/core/companion.py` - Delete deprecated methods
- `benchmark_comparison.py` - Fix hardcoded paths

### Should Touch Soon
- `backend/core/conversation.py` - Add docstrings
- `backend/core/reporting.py` - Add docstrings
- `backend/core/signals.py` - Add tests
- `backend/core/events.py` - Add tests

### Can Defer
- Regex → Rust migrations (already 70% done)
- Configuration file creation
- Full test coverage
