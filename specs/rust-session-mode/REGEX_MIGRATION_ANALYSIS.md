# Regex Migration Analysis

> **Date**: 2026-01-24 (updated)
> **Context**: Following session mode optimization (259s → 3.87s), this document analyzes remaining regex usage and migration opportunities.

## Executive Summary

The codebase contains **366 regex patterns** across extractor files. Many of these scan the 84MB gamestate string with fixed-size limits that can cause **data truncation** and **accuracy issues**. Migrating to Rust session operations would provide both **performance gains** and **improved accuracy**.

**Key finding**: During the `get_fallen_empires` migration, we discovered the Rust version correctly extracted ethics data that the regex version missed due to nested structure parsing limitations.

**Architecture principle**: Keep **game logic** (what to compute, how to interpret) in Python, and move only **generic data-access primitives** (fast, format-robust) into the Rust session server.

---

## Current Performance Baseline

| Stage | Briefing Time | Speedup |
|-------|---------------|---------|
| Original (cold cache) | 259s | baseline |
| Session mode | 7.76s | 33x |
| + FE optimization | 5.93s | 44x |
| + Player status cache | 4.64s | 56x |
| + Fleet analysis (✅ DONE) | 3.87s | 67x |

## Completed Migrations

| Function | File | Result |
|----------|------|--------|
| `get_fallen_empires()` | diplomacy.py | ✅ 1.5x faster, fixed ethics parsing bug |
| `_analyze_player_fleets()` | base.py | ✅ 6.8x faster (0.375s → 0.055s) |
| `get_crisis_status()` | endgame.py | ✅ Uses count_keys |
| `get_leviathans()` | leviathans.py | ✅ Uses contains_tokens |

---

## Regex Pattern Categories

### 1. Section Finding (~18 patterns)
**Purpose**: Locate where top-level sections start in gamestate
**Example**:
```python
re.search(r'^country=\s*\{', self.gamestate, re.MULTILINE)
```
**Rust solution**: Avoid offsets and slicing. Prefer direct data access:
- `get_entry(section, key)` for “jump to one thing by ID”
- `get_entries(section, keys, fields=None)` for “fetch a small set of IDs”
- `iter_section(section, batch_size=...)` only when you truly need all entries
- `extract_sections([...])` for small, top-level sections that are naturally bounded

**Why not offsets**: returning offsets encourages continued text slicing (`self.gamestate[offset:...]`), which is fragile across formatting differences and mods, and keeps truncation risks alive.
**Files affected**: base.py (7), economy.py (2), leaders.py (2), military.py (2), planets.py (2), player.py (1), technology.py (2)

### 2. Token Presence (~22 patterns)
**Purpose**: Check if a string exists anywhere in gamestate
**Example**:
```python
if re.search(r'war_in_heaven\s*=\s*yes', self.gamestate):
```
**Rust solution**:
- Use `contains_tokens` for true marker strings where formatting is stable (e.g., `killed_dragon`, `ether_drake_killed`).
- For key/value checks like `war_in_heaven\s*=\s*yes`, prefer a structured operation such as `contains_kv(key, value)` (whitespace/formatting insensitive), or a tree-based predicate over parsed data.

**Important**: `contains_tokens(['war_in_heaven=yes'])` is not equivalent to the regex above and may miss cases like `war_in_heaven = yes`.
**Status**: Partially migrated (leviathans.py, endgame.py)

### 3. Data Iteration (~7 patterns)
**Purpose**: Iterate over entries in a section
**Example**:
```python
for m in re.finditer(r'\n\t(\d+)=\n\t\{', country_chunk):
```
**Rust solution**:
- `iter_section` (already implemented) for full scans.
- `get_entries` when you already know which IDs you need (e.g., owned fleets), to avoid deserializing thousands of unrelated entries.
**Status**: Partially migrated (diplomacy.py for fallen empires)

### 4. Value Extraction (~319 patterns)
**Purpose**: Extract specific values from text blocks
**Example**:
```python
match = re.search(r'military_power\s*=\s*([\d.]+)', country_content)
```
**Rust solution**: Direct dict access after `iter_section`
**Status**: Not migrated - largest category

---

## Accuracy Risks in Current Code

### Risk 1: Fixed-Size Truncation

The codebase uses hardcoded byte limits that can truncate large entries:

| Limit | Location | Risk |
|-------|----------|------|
| 200KB | `block[:200000]` for ethos parsing | Large countries truncated |
| 80KB | `block[:80000]` for relations | Many relations missed |
| 100KB | Fleet content limits | Large fleets incomplete |
| 50KB | Various block extractions | Data loss |

**Example from diplomacy.py**:
```python
# This WILL miss data if the country block exceeds 200KB
ethos_m = re.search(r'ethos=\s*\{([^}]+)\}', block[:200000])

# Relations limited to 80KB - large empires have more relations
opinion_m = re.search(r'relations_manager=.*?country=0[^}]*opinion=([-\d]+)', block[:80000], re.DOTALL)
```

**Rust solution**: Parsed JSON has complete data, no truncation.

### Risk 2: Nested Structure Mismatch

Regex patterns like `[^}]+` fail on nested braces:

```python
# BROKEN: Stops at first }, misses nested structures
re.search(r'ethos=\s*\{([^}]+)\}', block)

# Actual structure has nesting:
# ethos={
#     ethic={
#         ethic="ethic_fanatic_xenophile"
#     }
# }
```

**Real bug found**: `get_fallen_empires` regex returned `Ethics: None` for Ubaric (ID:19), but Rust correctly found `ethic_fanatic_materialist`.

### Risk 3: Position-Based Fragility

Code calculates byte positions and assumes specific formatting:

```python
# Assumes exact whitespace and structure
country_entries = [(int(m.group(1)), country_start + m.start())
                  for m in re.finditer(r'\n\t(\d+)=\n\t\{', country_chunk)]
```

This breaks if:
- Save format changes slightly
- Mods alter structure
- Different game versions use different formatting

**Rust solution**: jomini parser handles format variations.

### Risk 4: “Partial Correctness” When Replacing Regex With Tokens

Replacing regex like `key\\s*=\\s*value` with `contains_tokens(['key=value'])` can silently reduce accuracy. Prefer `contains_kv(key, value)` or a parsed-tree check for these cases.

---

## Files with Fixed-Size Limits

```
stellaris_save_extractor/diplomacy.py:1030:  block[:200000]
stellaris_save_extractor/diplomacy.py:1051:  block[:200000]
stellaris_save_extractor/diplomacy.py:1082:  block[:80000]
stellaris_save_extractor/base.py:354:        content[:100000]
stellaris_save_extractor/base.py:440:        50000 limit
stellaris_save_extractor/base.py:994:        100000 limit
stellaris_save_extractor/economy.py:485:     100000 limit
stellaris_save_extractor/military.py:276:    100000 limit
stellaris_save_extractor/player.py:376:      500000 limit
stellaris_save_extractor/technology.py:206:  500000 limit
stellaris_save_extractor/technology.py:379:  100000 limit
```

---

## Migration Effort by File

| File | Regex Patterns | Effort | Priority | Notes |
|------|----------------|--------|----------|-------|
| **base.py** | 42 | High | P1 | `_analyze_player_fleets` ✅ DONE, others remain |
| **diplomacy.py** | 75 | Medium | P1 | `get_fallen_empires` ✅ DONE, relations parsing risky |
| **military.py** | 36 | Medium | P2 | Fleet/war analysis, iteration patterns |
| **planets.py** | 36 | Medium | P3 | Colony data, 20MB limits |
| **player.py** | 32 | Low | P3 | Cached, lower priority |
| **economy.py** | 29 | Medium | P3 | Budget/resource parsing |
| **technology.py** | 18 | Low | P4 | Tech tree, simpler structures |
| **leaders.py** | 14 | Low | P4 | Leader data extraction |
| **endgame.py** | 18 | ✅ Done | - | Migrated to count_keys |
| **leviathans.py** | 6 | ✅ Done | - | Migrated to contains_tokens |

---

## High-Impact Migration Targets

### 1. ✅ `_analyze_player_fleets()` in base.py - COMPLETED

**Result**: 0.375s → 0.055s (6.8x faster), exact data match with baseline.

**Implementation**: Uses `iter_section('fleet')` with dict access. See `MIGRATION_PATTERN.md` for the established pattern.

**Note**: Currently iterates all fleets to find owned ones. Could be optimized further with `get_entries(section, keys)` primitive to fetch only owned fleet IDs directly.

### 2. `get_diplomacy()` in diplomacy.py

**Current issues**:
- 80KB limit on relations parsing
- Nested structure parsing with regex
- Multiple passes over country section

**Accuracy risk**: Empires with many relations (federation members, vassals) may have truncated data.

### 3. `get_planets()` in planets.py

**Current issues**:
- 20MB limit (should be safe but arbitrary)
- Complex nested structures (pops, buildings, districts)
- Many regex patterns for extraction

---

## Recommended Migration Strategy

### Phase 1: New Rust Primitives (NEXT)
Add generic data-access primitives to serve.rs:
1. `get_entry(section, key)` - fetch single entry by ID
2. `get_entries(section, keys, fields=None)` - batch fetch with optional projection
3. `contains_kv(key, value)` - whitespace-insensitive key=value check

**Why these matter**:
- `get_entries` would optimize `_analyze_player_fleets` further (fetch 200 owned fleets directly instead of iterating 10K+ fleets)
- `contains_kv` fixes the whitespace issue with `contains_tokens` for patterns like `war_in_heaven=yes`

### Phase 2: Accuracy-Critical Migrations
1. `get_diplomacy()` relations parsing - 80KB truncation risk
2. Remaining diplomacy.py functions

### Phase 3: Comprehensive File Migration
3. `get_planets()` - complex nested structures (pops, buildings, districts)
4. `get_military_summary()` - fleet/war data
5. base.py remaining functions
6. Other files by priority

### Rust Primitives Summary

**Implemented:**
- `iter_section(section, batch_size)` - iterate all entries
- `count_keys(keys)` - count key occurrences in tree
- `contains_tokens(tokens)` - Aho-Corasick string presence
- `get_country_summaries(fields)` - country projections

**Needed:**
- `get_entry(section, key)` - single entry lookup
- `get_entries(section, keys, fields)` - batch lookup with projection
- `contains_kv(key, value)` - whitespace-insensitive k=v check

---

## Success Metrics

| Metric | Original | Current | Target |
|--------|----------|---------|--------|
| Briefing time | 259s | 3.87s | <2s |
| Speedup | - | 67x | 100x+ |
| Regex on gamestate | ~366 | ~350 | 0 |
| Fixed-size limits | 40+ | ~38 | 0 |
| Data truncation bugs | Unknown | Some fixed | 0 |

---

## Appendix: All Fixed-Size Limits Found

```
armies.py:175:        army_start + 5000000
base.py:137:          start + 5000000
base.py:354:          content[:100000]
base.py:440:          50000
base.py:570:          start + 5000000
base.py:994:          100000
base.py:999:          100000
base.py:1113:         start + 2000000
base.py:1194:         start + 20000000
base.py:1279:         start + 20000000
diplomacy.py:1030:    200000
diplomacy.py:1051:    200000
diplomacy.py:1082:    80000
diplomacy.py:1222:    10000000
economy.py:200:       50000000
economy.py:466:       1000000
economy.py:485:       100000
endgame.py:209:       50000000
endgame.py:217:       50000
endgame.py:742:       10000000
military.py:262:      5000000
military.py:276:      100000
military.py:995:      5000000
military.py:1016:     2000000
planets.py:357:       20000000
planets.py:766:       100000000
player.py:370:        1000000
player.py:376:        500000
player.py:420:        2000000
species.py:319:       50000
technology.py:201:    1000000
technology.py:206:    500000
technology.py:270:    1000000
technology.py:276:    500000
technology.py:379:    100000
```

---

## Next Steps

1. ✅ ~~Review this analysis~~
2. ✅ ~~Manual migration of `_analyze_player_fleets()` to establish pattern~~
3. **Add new Rust primitives** (`get_entry`, `get_entries`, `contains_kv`)
4. **Migrate remaining high-priority functions** using established pattern
5. **Use Ralph** for systematic file-by-file migration with MIGRATION_PATTERN.md
