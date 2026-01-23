# Rust Parser Optimization Plan

## Executive Summary

Session mode successfully eliminated re-parsing overhead (5.9x speedup on cold cache). However, profiling reveals that **90% of remaining time is Python-side work**, primarily regex operations scanning the full 84MB gamestate. This document outlines the next optimizations.

## Current Performance Baseline

**Test Environment:** MacBook M4, 7.7MB save file (late-game, 12K ships, 4K fleets)

| Metric | Value |
|--------|-------|
| Gamestate size | 84 MB (6.3M lines) |
| Session mode briefing time | 24-45s |
| Without session (cold) | 259s |
| Without session (warm) | 59s |

### Time Breakdown (from cProfile)

```
Total: 142s (profiler overhead inflates this ~2x)

Regex operations:     77s  (54%)  ← PRIMARY BOTTLENECK
  - re.search:        77s  (29,122 calls)
  - re.findall:       36s  (1,525 calls)

Rust bridge IPC:      14s  (10%)
  - json.loads:        8s  (104,894 calls)
  - queue.get:         9s  (blocking)

Python processing:    51s  (36%)
  - Data transformation, dict building
```

## Bottleneck Analysis

### 1. Regex on Full Gamestate (77s, 54%)

**The Problem:**
```python
# This scans 84MB of text for EACH pattern
if re.search(r'killed_dragon', self.gamestate, re.IGNORECASE):
    return True
```

**Scale:**
- 44 unique regex patterns in code
- Called in loops = 29,000+ actual executions
- Each scan: O(84MB) × 29K = catastrophic

**Hotspots:**
| File | Function | Issue |
|------|----------|-------|
| `leviathans.py` | `_check_leviathan_defeated` | 4 patterns × N leviathans |
| `endgame.py` | `get_crisis_status` | `re.findall` counting flags |
| `endgame.py` | `get_lgate_status` | Multiple pattern searches |

### 2. Repeated Country Iteration (15 passes)

**The Problem:**
```python
# Called 15 times across different extractors
for cid, country in iter_section_entries(save_path, "country"):
    ...
```

Each pass re-serializes and re-decodes the entire country section via IPC.

**Locations:**
- `base.py`: `_get_country_names`, `_analyze_player_fleets`
- `player.py`: `get_player_status`
- `diplomacy.py`: `get_diplomacy`, `get_fallen_empires`
- `endgame.py`: `get_crisis_status`, `get_menace`, `get_great_khan`
- `species.py`: `get_species_rights`
- `politics.py`: `get_claims`

### 3. IPC Overhead (14s, 10%)

**The Problem:**
```python
# 104,894 json.loads() calls for streaming
for line in proc.stdout:
    entry = json.loads(line)  # Called per entry
    yield entry["key"], entry["value"]
```

**Additionally in Rust:**
```rust
// Clone every value for serialization
value: value.clone(),  // Expensive for large ship/country data
```

### 4. Gamestate Still Loaded in Python

Even with Rust extraction, Python loads `self.gamestate` (84MB string) for regex fallbacks. This wastes memory and enables slow paths.

## Optimization Plan

### Phase 1: Aho-Corasick Pattern Search (Highest ROI)

**Goal:** Replace 29K regex scans with 1 multi-pattern scan

**Implementation:**

Add new Rust operation using the `aho-corasick` crate:

```rust
// Request
{"op": "search_patterns", "patterns": ["killed_dragon", "crisis_triggered", ...]}

// Response
{"ok": true, "matches": {
    "killed_dragon": true,
    "crisis_triggered": false,
    "dreadnought_captured": true,
    ...
}}
```

**Rust side (`serve.rs`):**
```rust
use aho_corasick::AhoCorasick;

fn handle_search_patterns(gamestate: &[u8], patterns: &[String]) -> Result<Value> {
    let ac = AhoCorasick::new(patterns)?;
    let mut matches = HashMap::new();

    for pattern in patterns {
        matches.insert(pattern.clone(), false);
    }

    for mat in ac.find_iter(gamestate) {
        matches.insert(patterns[mat.pattern()].clone(), true);
    }

    Ok(json!({"matches": matches}))
}
```

**Python side:**
```python
class RustSession:
    def search_patterns(self, patterns: list[str]) -> dict[str, bool]:
        self._send({"op": "search_patterns", "patterns": patterns})
        response = self._recv()
        return response.get("matches", {})
```

**Extractor usage:**
```python
# Before (29K scans)
def _check_leviathan_defeated(self, lev_type):
    for pattern in [f'killed_{lev_type}', f'{lev_type}_defeated', ...]:
        if re.search(pattern, self.gamestate, re.IGNORECASE):
            return True

# After (1 scan, cached)
def _check_leviathan_defeated(self, lev_type):
    patterns = [f'killed_{lev_type}', f'{lev_type}_defeated', ...]
    return any(self._pattern_matches.get(p) for p in patterns)
```

**Expected Impact:** 77s → ~2s (eliminate regex entirely)

---

### Phase 2: Batch IPC Responses

**Goal:** Reduce 104K json.loads to ~1K

**Implementation:**

```rust
// Instead of 1 entry per line:
{"ok": true, "entry": {"key": "0", "value": {...}}}
{"ok": true, "entry": {"key": "1", "value": {...}}}
...

// Batch 100 entries per message:
{"ok": true, "entries": [
    {"key": "0", "value": {...}},
    {"key": "1", "value": {...}},
    ... (100 entries)
]}
```

**Python side:**
```python
def iter_section(self, section: str, batch_size: int = 100):
    self._send({"op": "iter_section", "section": section, "batch_size": batch_size})
    header = self._recv()

    while True:
        frame = self._recv()
        if frame.get("done"):
            return
        for entry in frame.get("entries", []):
            yield entry["key"], entry["value"]
```

**Expected Impact:** 8s → ~1s (90% fewer decodes)

---

### Phase 3: Single-Pass Country Index

**Goal:** Build country data once, reuse everywhere

**Implementation:**

```python
class SaveExtractorBase:
    @cached_property
    def _country_index(self) -> dict[str, dict]:
        """Load all countries once, cache for briefing lifetime."""
        sess = _get_active_session()
        if sess:
            return {cid: cdata for cid, cdata in sess.iter_section("country")}
        return {}

    def get_country(self, country_id: str) -> dict:
        return self._country_index.get(str(country_id), {})

    def get_country_name(self, country_id: str) -> str:
        country = self.get_country(country_id)
        name = country.get("name", {})
        if isinstance(name, dict):
            return name.get("key", f"Country {country_id}")
        return str(name)
```

**Expected Impact:** 15 iterations → 1 iteration, ~10s saved

---

### Phase 4: Remove Gamestate Loading

**Goal:** Eliminate 84MB Python string allocation

**Implementation:**

Once all extractors use Rust operations:

```python
class SaveExtractorBase:
    @property
    def gamestate(self) -> str:
        raise DeprecationWarning(
            "Direct gamestate access is deprecated. "
            "Use Rust bridge operations instead."
        )
```

**Expected Impact:** ~5s saved, 84MB memory freed

---

### Phase 5: Zero-Copy Rust Streaming (Optional)

**Goal:** Avoid `value.clone()` per entry

**Implementation:**

Use `serde_json::value::RawValue` to avoid intermediate parsing:

```rust
// Current (clones parsed Value)
value: value.clone()

// Optimized (streams raw JSON bytes)
value: RawValue::from_string(raw_json_string)?
```

**Expected Impact:** ~2s saved for large sections

---

## Implementation Priority

| Phase | Effort | Impact | Priority |
|-------|--------|--------|----------|
| 1. Aho-Corasick | 2-3 hours | **~75s saved** | 🔴 Critical |
| 2. Batch IPC | 1-2 hours | ~7s saved | 🟡 High |
| 3. Country Index | 1 hour | ~10s saved | 🟡 High |
| 4. Remove Gamestate | 30 min | ~5s saved | 🟢 Medium |
| 5. Zero-Copy | 2 hours | ~2s saved | 🟢 Low |

## Expected Final Performance

| Stage | Time | Notes |
|-------|------|-------|
| Current | 24-45s | Session mode enabled |
| After Phase 1 | 10-15s | Regex eliminated |
| After Phase 2-3 | 5-8s | IPC + iteration optimized |
| After Phase 4-5 | 3-5s | Fully optimized |

**Target: <5s briefing generation** (vs 259s original, 50x+ speedup)

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Aho-Corasick case sensitivity | Use `AhoCorasickBuilder::ascii_case_insensitive()` |
| Pattern explosion | Deduplicate patterns, cache AC automaton |
| Country index memory | Only index needed fields, not full dicts |
| Breaking existing code | Keep regex fallback paths during transition |

## Success Metrics

- [ ] `get_complete_briefing()` < 5 seconds
- [ ] Zero `re.search(..., self.gamestate)` calls
- [ ] Single country iteration per briefing
- [ ] < 2000 json.loads calls (vs 104K)
- [ ] No Python gamestate loading in hot path

## Dependencies

**Rust crates to add:**
```toml
[dependencies]
aho-corasick = "1.1"
```

## References

- [Aho-Corasick crate](https://docs.rs/aho-corasick/latest/aho_corasick/)
- [Session mode implementation](./PLAN.md)
- Profile data from cProfile run (2026-01-23)
