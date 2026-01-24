# Regex Migration Analysis

> **Date**: 2026-01-24
> **Context**: Following session mode optimization (259s → 4.64s), this document analyzes remaining regex usage and migration opportunities.

## Executive Summary

The codebase contains **366 regex patterns** across extractor files. Many of these scan the 84MB gamestate string with fixed-size limits that can cause **data truncation** and **accuracy issues**. Migrating to Rust session operations would provide both **performance gains** and **improved accuracy**.

**Key finding**: During the `get_fallen_empires` migration, we discovered the Rust version correctly extracted ethics data that the regex version missed due to nested structure parsing limitations.

---

## Current Performance Baseline

| Stage | Briefing Time | Speedup |
|-------|---------------|---------|
| Original (cold cache) | 259s | baseline |
| Session mode | 7.76s | 33x |
| + FE optimization | 5.93s | 44x |
| + Player status cache | 4.64s | 56x |

---

## Regex Pattern Categories

### 1. Section Finding (~18 patterns)
**Purpose**: Locate where top-level sections start in gamestate
**Example**:
```python
re.search(r'^country=\s*\{', self.gamestate, re.MULTILINE)
```
**Rust solution**: Add `get_section_offset` operation
**Files affected**: base.py (7), economy.py (2), leaders.py (2), military.py (2), planets.py (2), player.py (1), technology.py (2)

### 2. Token Presence (~22 patterns)
**Purpose**: Check if a string exists anywhere in gamestate
**Example**:
```python
if re.search(r'war_in_heaven\s*=\s*yes', self.gamestate):
```
**Rust solution**: `contains_tokens` (already implemented)
**Status**: Partially migrated (leviathans.py, endgame.py)

### 3. Data Iteration (~7 patterns)
**Purpose**: Iterate over entries in a section
**Example**:
```python
for m in re.finditer(r'\n\t(\d+)=\n\t\{', country_chunk):
```
**Rust solution**: `iter_section` (already implemented)
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
| **base.py** | 42 | High | P1 | Core utilities, `_analyze_player_fleets` is hot path |
| **diplomacy.py** | 75 | Medium | P2 | 60% has Rust fallback, relations parsing risky |
| **military.py** | 36 | Medium | P2 | Fleet/war analysis, iteration patterns |
| **planets.py** | 36 | Medium | P3 | Colony data, 20MB limits |
| **player.py** | 32 | Low | P3 | Already cached, lower priority |
| **economy.py** | 29 | Medium | P3 | Budget/resource parsing |
| **technology.py** | 18 | Low | P4 | Tech tree, simpler structures |
| **leaders.py** | 14 | Low | P4 | Leader data extraction |
| **endgame.py** | 18 | Done | - | Migrated to count_keys |
| **leviathans.py** | 6 | Done | - | Migrated to contains_tokens |

---

## High-Impact Migration Targets

### 1. `_analyze_player_fleets()` in base.py

**Current state**:
- Called during `get_player_status()` (hot path)
- Takes ~0.8s per call
- Uses 100KB limits for fleet content
- Regex iteration over fleet section

**Current code**:
```python
def _analyze_player_fleets(self, owned_fleet_ids: list[int]) -> dict:
    # Find fleet section with regex
    fleet_section = self._find_fleet_section()  # Regex scan

    for fleet_id in owned_fleet_ids:
        # Regex to find each fleet
        pattern = rf'\n\t{fleet_id}=\s*\{{'
        match = re.search(pattern, fleet_section)

        # Limited content extraction
        search_window = fleet_section[fleet_start + 10:fleet_start + 100000]
```

**Rust migration**:
```python
def _analyze_player_fleets_rust(self, owned_fleet_ids: list[int]) -> dict:
    session = _get_active_session()
    owned_set = set(owned_fleet_ids)

    for fid, fleet in session.iter_section('fleet'):
        if int(fid) not in owned_set:
            continue

        # Direct dict access - no truncation, no regex
        is_station = fleet.get('station') == 'yes'
        is_civilian = fleet.get('civilian') == 'yes'
        ships = fleet.get('ships', {})
        military_power = fleet.get('military_power', 0)
```

**Expected benefit**: 0.8s → ~0.1s, plus accuracy for large fleets

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

### Phase 1: Hot Path (Immediate)
1. `_analyze_player_fleets()` - 0.8s savings, accuracy gains
2. `_find_section_bounds()` - 0.9s savings (add Rust section index)

### Phase 2: Accuracy Critical
3. `get_diplomacy()` relations parsing - truncation risk
4. `get_fallen_empires()` regex fallback removal - already have Rust version

### Phase 3: Comprehensive
5. `get_planets()` - complex structures
6. `get_military_summary()` - fleet/war data
7. Remaining files

---

## Success Metrics

After full migration:

| Metric | Current | Target |
|--------|---------|--------|
| Briefing time | 4.64s | <2s |
| Regex on gamestate | 58 direct calls | 0 |
| Fixed-size limits | 40+ | 0 |
| Data truncation bugs | Unknown | 0 |

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

1. Review this analysis
2. Prioritize based on accuracy vs performance needs
3. Start with `_analyze_player_fleets()` (hot path + accuracy)
4. Create test cases to verify data correctness before/after migration
