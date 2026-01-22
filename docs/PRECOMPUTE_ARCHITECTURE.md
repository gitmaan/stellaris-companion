# Pre-compute Architecture Analysis

**Date:** 2026-01-15
**Status:** Analysis Complete
**Benchmark:** `benchmark_extraction.py`

---

## Extraction Timing Reality

```
┌─────────────────────────────────────────────────────────────────┐
│                  EXTRACTION TIMING BREAKDOWN                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Save file: test_save.sav (6.4 MB compressed, 71.4 MB gamestate) │
│                                                                  │
│  SLOW METHODS (need optimization):                               │
│  ├── get_situation()      3233ms  ████████████████████  40%     │
│  ├── get_fallen_empires() 2021ms  ████████████          25%     │
│  ├── get_player_status()  1179ms  ███████               14%     │
│  ├── get_fleets()          667ms  ████                   8%     │
│  └── get_planets()         510ms  ███                    6%     │
│                                                                  │
│  FAST METHODS:                                                   │
│  ├── get_leaders()         149ms  █                              │
│  ├── get_empire_identity() 103ms  █                              │
│  ├── get_technology()       81ms  ▌                              │
│  ├── get_resources()        80ms  ▌                              │
│  ├── get_wars()             64ms  ▌                              │
│  ├── get_starbases()        49ms  ▌                              │
│  ├── get_diplomacy()        14ms  ▏                              │
│  └── get_metadata()          0ms  ▏                              │
│                                                                  │
│  TOTALS:                                                         │
│  ├── Save load:             46ms                                 │
│  ├── All extractions:    8112ms                                  │
│  ├── JSON serialize:         0ms                                 │
│  └── FULL CYCLE:         8167ms (8.2 seconds)                   │
│                                                                  │
│  Briefing JSON size:     45.4 KB                                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Key Finding:** 8.2 seconds is too slow for synchronous extraction. Need background processing.

**Optimization Opportunity:** `get_situation()` and `get_fallen_empires()` account for 65% of extraction time. These could be optimized or cached separately.

---

## Architecture Options

### Option 1: Synchronous on Save Change

```
Save Watcher ──► Extract (8s) ──► Cache ──► Ready
                     │
                     └── BLOCKS for 8 seconds
```

| Aspect | Assessment |
|--------|------------|
| Latency | 8 seconds blocking |
| Complexity | Low |
| User Experience | Poor - UI freezes |
| **Verdict** | ❌ Not viable |

---

### Option 2: Background Thread (Fire and Forget)

```
Save Watcher ──► Spawn Thread ──► [Background: Extract 8s] ──► Update Cache
                     │
                     └── Returns immediately

/ask Query ──► Check cache ──► If stale, use last known good
```

```python
class Companion:
    def on_save_changed(self, path):
        # Fire and forget - non-blocking
        threading.Thread(target=self._extract_background, args=(path,)).start()

    def _extract_background(self, path):
        extractor = SaveExtractor(path)
        briefing = get_complete_briefing(extractor)
        self._complete_briefing = briefing  # Atomic update

    def ask(self, question):
        # Always uses whatever cache exists (may be slightly stale)
        return self._do_ask(self._complete_briefing)
```

| Aspect | Assessment |
|--------|------------|
| Latency | Non-blocking |
| Complexity | Medium |
| Race Condition | User may get stale data for ~8s after save |
| **Verdict** | ⚠️ Viable, but stale data risk |

---

### Option 3: Background with Completion Signal

```
Save Watcher ──► Spawn Thread ──► [Background: Extract 8s] ──► Signal Complete
                     │                                              │
                     └── Returns immediately                        │
                                                                    ▼
/ask Query ──► Is extraction running? ──► YES ──► Wait (or use stale + disclaimer)
                     │
                     └── NO ──► Use fresh cache
```

```python
class Companion:
    def __init__(self):
        self._extraction_lock = threading.Lock()
        self._extraction_complete = threading.Event()
        self._extraction_complete.set()  # Initially "complete"

    def on_save_changed(self, path):
        self._extraction_complete.clear()
        threading.Thread(target=self._extract_background, args=(path,)).start()

    def _extract_background(self, path):
        with self._extraction_lock:
            extractor = SaveExtractor(path)
            briefing = get_complete_briefing(extractor)
            self._complete_briefing = briefing
        self._extraction_complete.set()

    def ask(self, question, wait_for_fresh=True):
        if wait_for_fresh and not self._extraction_complete.is_set():
            # Option A: Wait for extraction
            self._extraction_complete.wait(timeout=15)
            # Option B: Or return immediately with disclaimer
        return self._do_ask(self._complete_briefing)
```

| Aspect | Assessment |
|--------|------------|
| Latency | Non-blocking (or controlled wait) |
| Complexity | Medium |
| Race Condition | Handled explicitly |
| **Verdict** | ✅ Good - explicit control |

---

### Option 4: Integrated with SQLite History Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    UNIFIED EXTRACTION PIPELINE                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Save Watcher                                                                │
│       │                                                                      │
│       ▼                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ Background Extraction Thread                                        │    │
│  │                                                                      │    │
│  │   1. Load save file                                     (~50ms)     │    │
│  │   2. get_complete_briefing()                           (~8000ms)    │    │
│  │   3. Compute events vs previous snapshot               (~100ms)     │    │
│  │   4. Store in SQLite:                                               │    │
│  │      - snapshots.full_briefing_json (for /ask)                      │    │
│  │      - snapshots.metrics (for timeline graphs)                      │    │
│  │      - events (for /history, session reports)                       │    │
│  │   5. Update in-memory cache                                         │    │
│  │   6. Signal completion                                              │    │
│  │                                                                      │    │
│  │   Single extraction serves:                                          │    │
│  │   ✓ /ask queries (Option B full pre-compute)                        │    │
│  │   ✓ /history command                                                 │    │
│  │   ✓ Session timeline (Phase 3)                                       │    │
│  │   ✓ Event detection (wars started, leaders died, etc.)              │    │
│  │   ✓ End-of-session reports                                           │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  /ask Query                                                                  │
│       │                                                                      │
│       ▼                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ Cache Lookup Strategy                                                │    │
│  │                                                                      │    │
│  │   1. Check in-memory cache (_complete_briefing)                     │    │
│  │      └── If fresh: use it (instant)                                 │    │
│  │                                                                      │    │
│  │   2. If extraction in progress:                                     │    │
│  │      └── Load last snapshot from SQLite (fallback)                  │    │
│  │      └── Add disclaimer: "Using data from {date}"                   │    │
│  │                                                                      │    │
│  │   3. On cold start (no cache):                                      │    │
│  │      └── Load most recent snapshot from SQLite                      │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  Benefits:                                                                   │
│  ✓ Single extraction for multiple features                                  │
│  ✓ SQLite provides persistence across restarts                              │
│  ✓ Never blocks user queries                                                │
│  ✓ Graceful degradation (stale data with disclaimer)                        │
│  ✓ Historical snapshots enable /history and timeline                        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Database Schema (from Phase 3 plan, slightly modified):**

```sql
CREATE TABLE snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    game_date TEXT NOT NULL,
    game_days INTEGER,  -- For sorting
    captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Quick metrics (for timeline graphs, no JSON parse needed)
    military_power INTEGER,
    economy_power INTEGER,
    tech_power INTEGER,
    colony_count INTEGER,
    population INTEGER,
    fleet_count INTEGER,

    -- FULL briefing for Option B injection (45-80 KB)
    full_briefing_json TEXT NOT NULL,

    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX idx_snapshots_session_date ON snapshots(session_id, captured_at);
```

| Aspect | Assessment |
|--------|------------|
| Latency | Non-blocking |
| Complexity | Medium-High |
| Integration | ✅ Feeds history, /ask, events, reports |
| Persistence | ✅ Survives restarts |
| **Verdict** | ✅ Best - unified architecture |

---

### Option 5: Tiered Pre-compute (Fast + Slow)

Split extraction into two tiers:

```
Save Watcher
     │
     ├──► TIER 1 (Immediate, ~500ms):
     │    - get_metadata()
     │    - get_empire_identity()
     │    - get_resources()
     │    - get_diplomacy()
     │    - get_leaders()
     │    Cache immediately, answer simple questions
     │
     └──► TIER 2 (Background, ~7500ms):
          - get_situation()      [SLOW: 3233ms]
          - get_fallen_empires() [SLOW: 2021ms]
          - get_player_status()  [SLOW: 1179ms]
          - get_fleets()         [SLOW: 667ms]
          - get_planets()        [SLOW: 510ms]
          Merge into cache when complete
```

```python
def on_save_changed(self, path):
    # Tier 1: Fast extraction (blocks ~500ms - acceptable)
    extractor = SaveExtractor(path)
    tier1 = {
        'meta': extractor.get_metadata(),
        'identity': extractor.get_empire_identity(),
        'resources': extractor.get_resources(),
        'diplomacy': extractor.get_diplomacy(),
        'leaders': extractor.get_leaders(),
        'technology': extractor.get_technology(),
        'starbases': extractor.get_starbases(),
        'wars': extractor.get_wars(),
    }
    self._partial_briefing = tier1

    # Tier 2: Slow extraction (background)
    threading.Thread(target=self._extract_tier2, args=(extractor,)).start()

def _extract_tier2(self, extractor):
    tier2 = {
        'situation': extractor.get_situation(),
        'fallen_empires': extractor.get_fallen_empires(),
        'military': extractor.get_player_status(),
        'fleets': extractor.get_fleets(),
        'planets': extractor.get_planets(),
    }
    # Merge into complete briefing
    self._complete_briefing = {**self._partial_briefing, **tier2}
```

| Aspect | Assessment |
|--------|------------|
| Latency | 500ms blocking + 7.5s background |
| Complexity | High |
| Partial Data Risk | Yes - need to handle carefully |
| **Verdict** | ⚠️ Complex, but could optimize UX |

---

## Recommendation

### Primary: Option 4 (Unified Pipeline with SQLite)

**Why:**

1. **Single extraction serves everything** - /ask, /history, events, reports
2. **SQLite provides persistence** - survives restarts, cold starts work
3. **Aligns with Phase 3 plan** - history tracking already needs this
4. **Graceful degradation** - stale data with disclaimer, never blocks

### Secondary: Optimize Slow Methods

Before implementing, optimize the bottlenecks:

| Method | Current | Target | Optimization |
|--------|---------|--------|--------------|
| `get_situation()` | 3233ms | <500ms | Cache sub-calls, avoid redundant scans |
| `get_fallen_empires()` | 2021ms | <200ms | Single-pass scan for all FEs |
| `get_player_status()` | 1179ms | <300ms | Reuse fleet analysis from get_fleets() |

If we can get total extraction under 2-3 seconds, Option 3 (background without SQLite) becomes more viable.

---

## Implementation Plan

### Phase A: Optimize Slow Extractors

1. Profile `get_situation()` - why is it 3.2 seconds?
2. Profile `get_fallen_empires()` - why is it 2 seconds?
3. Reduce total extraction to <3 seconds if possible

### Phase B: Background Extraction

1. Add `threading.Event` for extraction completion signaling
2. Move extraction to background thread on save change
3. Handle race condition (query during extraction)

### Phase C: SQLite Integration

1. Create `snapshots` table with `full_briefing_json` column
2. Store snapshot on each extraction
3. Load from SQLite on cold start
4. Use SQLite as fallback during extraction

### Phase D: Unified Pipeline

1. Single extraction feeds: cache, SQLite, event detection
2. `/history` reads from events table
3. Session reports generated from SQLite snapshots

---

## Quick Decision Matrix

| Scenario | Recommended Option |
|----------|-------------------|
| MVP / quick win | Option 3 (Background + Signal) |
| Full Phase 3 implementation | Option 4 (Unified Pipeline) |
| If extraction optimized to <2s | Option 2 (Fire and Forget) is fine |
| Maximum UX (partial data fast) | Option 5 (Tiered) - but complex |

---

## Next Steps

1. **Profile slow methods** - understand why `get_situation()` takes 3.2s
2. **Decide on MVP approach** - Option 3 for quick win, Option 4 for full integration
3. **Implement background extraction** - threading with completion signal
4. **Add SQLite persistence** - for cold start and fallback

---

## Appendix: Full Timing Data

```json
{
  "load_time_ms": 46,
  "extract_time_ms": 8112,
  "total_reload_ms": 8167,
  "briefing_size_kb": 45.4,
  "method_times": {
    "get_metadata": 0,
    "get_empire_identity": 103,
    "get_situation": 3233,
    "get_player_status": 1179,
    "get_resources": 80,
    "get_leaders": 149,
    "get_planets": 510,
    "get_diplomacy": 14,
    "get_technology": 81,
    "get_starbases": 49,
    "get_fleets": 667,
    "get_wars": 64,
    "get_fallen_empires": 2021
  }
}
```
