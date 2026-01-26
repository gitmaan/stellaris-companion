# Chronicles Feature Deep Dive

**Date**: 2026-01-27
**Status**: Analysis Complete

## Executive Summary

The chronicles feature is a **well-architected, production-grade narrative generation system** (~5,500 lines of production code) that transforms Stellaris game data into dramatic multi-chapter histories using Gemini 3 Flash. However, there are significant gaps in data utilization and unit testing that limit the feature's potential.

**Overall Quality Assessment**: 85% - Production ready with room for improvement

| Category | Status | Notes |
|----------|--------|-------|
| Architecture | Excellent | Clean separation of concerns |
| Storage | Excellent | SQLite with WAL, smart caching |
| User Experience | Good | Full Electron UI, Discord bot |
| Data Utilization | Poor | Only 9/43 extractors used |
| Unit Testing | Poor | 0 tests for chronicle.py |
| Integration Testing | Good | 5 dedicated test scripts |
| Documentation | Excellent | 5 comprehensive docs |

---

## 1. Architecture Overview

### Data Flow Pipeline

```
Save File (50-100MB late-game)
        ↓
Rust Parser (stellaris-parser) [Session Mode]
        ↓
SaveExtractor (stellaris_save_extractor/)
        ↓
Signals Pipeline (build_snapshot_signals) [Rust-backed extraction]
        ├─ Leaders (resolved names)
        ├─ Wars (placeholder resolution)
        ├─ Diplomacy (empire names)
        ├─ Technology
        ├─ Megastructures
        ├─ Crisis/Fallen Empires
        └─ Policies, Edicts, Galaxy Settings
        ↓
Events Computation (compute_events) [Diff detection between snapshots]
        ├─ Military changes (power, fleets)
        ├─ War start/end
        ├─ Federation join/leave
        ├─ Leader hire/death
        ├─ Alliance/rivalry
        ├─ Tech researched
        ├─ Systems gained/lost
        ├─ Crisis detection
        └─ Fallen Empire awakening
        ↓
Database Storage (GameDatabase - SQLite)
        ├─ events table (1000+ events per late-game)
        ├─ sessions table (keyed by save_id)
        ├─ snapshots table (one per autosave)
        └─ cached_chronicles table (chapters + current era)
        ↓
ChronicleGenerator (Google Gemini 3 Flash)
        ├─ Finalizes completed chapters (era-ending triggers)
        ├─ Generates current era narrative (unfinalized)
        ├─ Maintains prompt size under 250 events/chapter
        └─ Caches both finalized chapters and current era
        ↓
Output Format
        ├─ Structured JSON: {chapters[], current_era, pending_chapters}
        ├─ Legacy text format: full markdown chronicle
        ├─ Discord bot: /chronicle with message splitting
        └─ Electron app: Real-time chapter management
```

### Design Principles

1. **Rust-First Extraction**: All gamestate parsing via Rust session mode - no regex fallbacks
2. **Incremental Chapters**: Completed chapters are permanent; current era is ephemeral
3. **Cross-Session Persistence**: Chronicles keyed by `save_id`, not `session_id` - survives restarts
4. **Prompt Size Safety**: Hard caps (250 events/chapter) to prevent Gemini timeout
5. **Personality Dynamics**: Narrative voice adapts to empire ethics

---

## 2. Key Components

### 2.1 ChronicleGenerator (`backend/core/chronicle.py`)

**Size**: 1,338 lines

**Main Entry Points:**
- `generate_chronicle(session_id, force_refresh=False)` - Generate/update full chronicle
- `regenerate_chapter(session_id, chapter_number, confirm=True)` - Regenerate specific chapter
- `generate_recap(session_id, style="summary"|"dramatic", max_events=30)` - Quick recap

**Chapter Finalization Triggers:**
- Time threshold: 50+ years elapsed since last chapter
- Era-ending events (with 5-year cooldown):
  - `war_ended`
  - `crisis_defeated`
  - `fallen_empire_awakened`
  - `war_in_heaven_started`
  - `federation_joined`
  - `federation_left`

**Voice Adaptation by Ethics:**
| Ethics | Voice Style |
|--------|-------------|
| Machine Intelligence | Cold, logical precision |
| Hive Mind | Collective memory; "we" and "the swarm" |
| Authoritarian | Imperial grandeur; hierarchy and order |
| Egalitarian | Collective achievement; democratic ideals |
| Militarist | Martial pride; battles and conquest |
| Spiritualist | Religious reverence; divine providence |
| Pacifist | Peace and diplomacy; conflict as tragedy |
| Materialist | Scientific progress; march of reason |

### 2.2 Events Detection (`backend/core/events.py`)

**Size**: 1,048 lines
**Event Types**: 35+

**Categories:**
1. **Military** - power changes (±15% and ±2000), fleet changes, war start/end
2. **Territory** - colony count, systems gained/lost
3. **Economy** - tech completed, resource net changes
4. **Diplomacy** - alliances, rivalries, treaties, federations
5. **Leaders** - hired, removed, died
6. **Game Phase** - midgame/endgame milestones
7. **Megastructures** - started, upgraded
8. **Crisis** - started, defeated, War in Heaven

### 2.3 Signals Pipeline (`backend/core/signals.py`)

**Size**: 1,192 lines

**Currently Extracted (9 domains):**
- Leaders (resolved names via Rust)
- Wars (name resolution from nested structures)
- Diplomacy (empire names mapping)
- Technology (completed + in-progress)
- Megastructures (type, stage)
- Crisis/Fallen Empires
- Policies
- Edicts
- Galaxy Settings

---

## 3. Storage Architecture

### Database Schema (SQLite with WAL)

**Location**: `./stellaris_history.db`

```sql
-- Sessions: coarse-grained play sessions
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    save_id TEXT NOT NULL,
    save_path TEXT,
    empire_name TEXT,
    latest_briefing_json TEXT,
    started_at INTEGER,
    ended_at INTEGER,
    last_game_date TEXT
);

-- Snapshots: one per autosave
CREATE TABLE snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    game_date TEXT,
    save_hash TEXT,
    military_power INTEGER,
    colony_count INTEGER,
    event_state_json TEXT,
    full_briefing_json TEXT
);

-- Events: derived deltas
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    game_date TEXT,
    event_type TEXT,
    summary TEXT,
    data_json TEXT
);

-- Chronicles: LLM-generated narratives
CREATE TABLE cached_chronicles (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    save_id TEXT,
    chronicle_text TEXT,
    chapters_json TEXT,
    event_count INTEGER,
    snapshot_count INTEGER,
    generated_at TEXT
);
```

### Storage Optimizations

- **Full briefing stored once per session** (not per snapshot)
- **Event state JSON is compact** (2-5KB vs 50-100MB full briefing)
- **Current era cached separately** from finalized chapters
- **WAL mode** enables concurrent reads during writes
- **Busy timeout** of 5 seconds prevents lock conflicts

### Chapters JSON Structure

```json
{
    "format_version": 1,
    "chapters": [
        {
            "number": 1,
            "title": "The Cradle's Awakening",
            "start_date": "2200.01.01",
            "end_date": "2250.01.01",
            "start_snapshot_id": 1,
            "end_snapshot_id": 50,
            "narrative": "...",
            "summary": "...",
            "generated_at": "2026-01-26T...",
            "is_finalized": true,
            "context_stale": false,
            "trigger": "time_threshold"
        }
    ],
    "current_era_start_date": "2250.01.01",
    "current_era_start_snapshot_id": 51,
    "current_era_cache": {...}
}
```

---

## 4. User Experience

### 4.1 Electron App (Primary Interface)

**Files:**
- `electron/renderer/pages/ChroniclePage.tsx` - Main page
- `electron/renderer/components/ChronicleChapterList.tsx` - Sidebar navigation
- `electron/renderer/components/ChronicleContent.tsx` - Chapter display

**Features:**
- Game/save selector dropdown
- Chapter navigation with status indicators:
  - 🔒 Finalized
  - ⚠️ Stale context
  - ⟳ Regenerating
  - ⏳ Current era (in progress)
- Regenerate chapter with confirmation dialog
- Pending chapters notification with refresh button
- Full markdown rendering

### 4.2 Discord Bot

**Commands:**
- `/chronicle [force_refresh]` - Full dramatic chronicle
- `/recap [style: summary|dramatic]` - Quick session recap

**Features:**
- Smart message splitting (1900 char limit)
- Breaks at chapter boundaries → paragraphs → sentences
- Footer shows cache status and event count

### 4.3 REST API

**Endpoints:**
```
POST /api/chronicle
  Request: { session_id, force_refresh? }
  Response: { chapters[], current_era, pending_chapters, chronicle, cached, event_count }

POST /api/recap
  Request: { session_id, style? }
  Response: { recap, style, events_summarized, date_range }

POST /api/chronicle/regenerate-chapter
  Request: { session_id, chapter_number, confirm }
  Response: { chapter, regenerated, stale_chapters, error? }
```

### 4.4 CLI (Gap Identified)

**Current state**: No `/chronicle` or `/recap` commands in interactive mode.

**Available commands:**
- `/quit`, `/clear`, `/reload`, `/personality`, `/prompt`, `/thinking`

**Missing**: Direct chronicle access from CLI.

---

## 5. Data Utilization Analysis

### Design Philosophy (from STORYTELLING_OPTIONS.md)

The original design explicitly chose **LLM-based chapter generation with hindsight** over rule-based era detection:

> "The LLM naturally creates 4-7 eras because good storytelling requires meaningful chapters, not micro-chapters."

This means:
1. **Quality over quantity** - Not every game event needs to be tracked
2. **Major turning points matter** - Wars, crises, federations define eras
3. **LLM handles noise** - The LLM filters minor events when writing narrative

### Original Design vs Current Implementation

The original STORYTELLING_OPTIONS.md (line 33-38) listed these as "narrative-ready events":

| Proposed Event | Status | Notes |
|----------------|--------|-------|
| `war_started`, `war_ended` | ✅ Implemented | Working |
| `leader_hired`, `leader_died` | ✅ Implemented | Working |
| `alliance_formed`, `rivalry_declared` | ✅ Implemented | Working |
| `federation_joined`, `treaty_signed` | ✅ Implemented | Working |
| `crisis_started`, `crisis_defeated` | ✅ Implemented | Working |
| `fallen_empire_awakened` | ✅ Implemented | Working |
| `megastructure_completed` | ✅ Implemented | Working |
| `technology_completed` | ✅ Implemented | Working |
| **`tradition_adopted`** | ❌ Not implemented | Was in design |
| **`ascension_perk_selected`** | ❌ Not implemented | Was in design |
| **`first_contact`** | ❌ Not implemented | Was in design |
| **`ruler_changed`** | ❌ Not implemented | Was in design |
| **`galactic_community_joined`** | ❌ Not implemented | Was in design |

### Stress-Tested Signal Recommendations

Each signal below was evaluated using the "Stellaris Invicta test" - would this make for a compelling moment in a dramatic chronicle? See `docs/CHRONICLE_SIGNAL_ANALYSIS.md` for full analysis.

---

### PHASE 1: Chapter-Defining Moments (Must Add)

These are the highest-impact signals - each represents a potential chapter title or turning point.

| Event | Chronicle Example | Freq/Game | Extractor |
|-------|-------------------|-----------|-----------|
| **`ascension_perk_selected`** | "We chose Synthetic Ascension. The flesh was weak." | 8-10 | `player.py:439` ✅ |
| **`first_contact`** | "We learned we were not alone." | 1-5 | Needs detection |
| **`ruler_changed`** | "The Third Emperor rose to power." | 3-8 | Needs detection |
| **`lgate_opened`** | "The L-Gate opened. The Tempest poured through." | 0-1 | `endgame.py:279` ✅ |
| **`crisis_level_increased`** | "We chose to become the galaxy's doom." | 0-5 | `endgame.py:432` ✅ |

**Total new events**: ~15-25 per game

---

### PHASE 2: Significant Era Markers (Should Add)

These mark significant transitions but aren't always chapter-defining.

| Event | Chronicle Example | Freq/Game | Extractor |
|-------|-------------------|-----------|-----------|
| **`great_khan_spawned`** | "From the Marauders, a conqueror arose." | 0-1 | `endgame.py:540` ✅ |
| **`great_khan_died`** | "The Khan fell. His empire shattered." | 0-1 | `endgame.py:540` ✅ |
| **`galactic_community_joined`** | "We took our seat among the stars." | 0-1 | `diplomacy.py:474` ✅ |
| **`tradition_tree_completed`** | "We completed the Supremacy traditions." | 5-7 | `player.py:385` ✅ |
| **`precursor_homeworld_discovered`** | "We found Cybrex Alpha. The machines had been here before." | 0-6 | `projects.py:39` ✅ |

**Total new events**: ~10-15 per game

---

### PHASE 3: Optional Flavor (Consider with Filtering)

Only add if filtered to prevent noise.

| Event | Filtering Required | Freq/Game |
|-------|-------------------|-----------|
| **`guardian_defeated`** | Only 6 major guardians (Drake, Horror, Dreadnought, Fortress, Stellarite, Voidspawn) | 0-6 |
| **`legendary_relic_acquired`** | Only ~5 legendaries (Galatron, Brood-Queen, Defragmentor, etc.) | 0-3 |
| **`subject_acquired`** | Cap at 3-5 per chapter | 0-10 |

---

### DO NOT ADD (Noise, Not Narrative)

| Signal | Why Skip |
|--------|----------|
| Individual traditions | 20+/game - tree completion is enough |
| Archaeological sites | Too many individual discoveries |
| Fleet composition | Tactical advisor data, not chronicle |
| Faction changes | Internal politics = noise in epic narrative |
| Policy changes | Administrative minutiae |
| Claims | Pre-war positioning, too tactical |
| Espionage operations | Many small operations |
| Common space fauna | Tiyanki, crystals, etc. are common encounters |

---

### Event Budget Summary

| Phase | New Events/Game | Cumulative |
|-------|-----------------|------------|
| Current | ~600-1000 | ~600-1000 |
| Phase 1 | +15-25 | ~615-1025 |
| Phase 2 | +10-15 | ~625-1040 |
| Phase 3 | +5-10 | ~630-1050 |

**Total increase: ~5%** - well within the LLM's ability to filter.

---

## 6. Critical Issue: Testing Gap

### Current Test Coverage

| Module | Lines | Unit Tests | Status |
|--------|-------|------------|--------|
| `chronicle.py` | 1,338 | 0 | **Critical gap** |
| `events.py` | 1,048 | 43 | Good |
| `signals.py` | 1,192 | 43 | Good |
| `database.py` | 1,383 | Integration only | Acceptable |

### Untested Critical Functions

1. **`_repair_json_string()`** (lines 51-105)
   - Complex state machine for escaping newlines in Gemini output
   - No tests for edge cases (tabs, mixed line endings)
   - Risk: JSON parsing failures in production

2. **`_select_events_for_prompt()`** (lines 367-421)
   - Deduplication + ranking logic
   - No tests for truncation at 250 event limit
   - Risk: Important events silently dropped

3. **`_should_finalize_chapter()`** (lines 273-328)
   - Time threshold and era-ending event detection
   - No tests for edge cases
   - Risk: Chapters finalized incorrectly

4. **`regenerate_chapter()`** (lines 458-545)
   - Downstream stale marking
   - No tests
   - Risk: Stale context not properly tracked

### Integration Test Scripts (Good Coverage)

| Script | Purpose | Status |
|--------|---------|--------|
| `scripts/test_chronicle.py` | Main LLM generation | Working |
| `scripts/test_chronicle_integration.py` | Database + generator | Working |
| `scripts/test_chronicle_compare.py` | Style guide A/B | Completed |
| `scripts/test_chronicle_variety.py` | Cookie-cutter prevention | Pass |
| `scripts/test_chronicle_ethics.py` | Voice differentiation | Pass |
| `scripts/test_incremental_chronicle.py` | Incremental system | Working |

---

## 7. Implementation Roadmap

### Phase 1: Chapter-Defining Events (Priority: HIGH)

**Goal**: Add the 5 highest-impact signals that define empire identity and major turning points.

| # | Event | Implementation | Files to Modify |
|---|-------|----------------|-----------------|
| 1 | `ascension_perk_selected` | Add signal extraction + event detection | `signals.py`, `events.py` |
| 2 | `first_contact` | Track known empires, detect additions | `signals.py`, `events.py` |
| 3 | `ruler_changed` | Track ruler ID from leaders, detect changes | `signals.py`, `events.py` |
| 4 | `lgate_opened` | Add signal extraction + event detection | `signals.py`, `events.py` |
| 5 | `crisis_level_increased` | Add menace signal + level change detection | `signals.py`, `events.py` |

**Estimated effort**: 3-4 days
**New events per game**: ~15-25

---

### Phase 2: Era Markers (Priority: MEDIUM)

**Goal**: Add significant markers that enhance narrative but aren't always chapter-defining.

| # | Event | Implementation | Files to Modify |
|---|-------|----------------|-----------------|
| 6 | `great_khan_spawned` | Add Khan signal + status detection | `signals.py`, `events.py` |
| 7 | `great_khan_died` | Detect Khan death from status change | `events.py` |
| 8 | `galactic_community_joined` | Add GC membership signal | `signals.py`, `events.py` |
| 9 | `tradition_tree_completed` | Track `by_tree[].finished` changes | `signals.py`, `events.py` |
| 10 | `precursor_homeworld_discovered` | Track precursor completion flags | `signals.py`, `events.py` |

**Estimated effort**: 2-3 days
**New events per game**: ~10-15

---

### Phase 3: Unit Tests for Chronicle.py (Priority: HIGH)

**Goal**: Add test coverage for the 1,338-line chronicle.py module (currently 0 tests).

```python
# tests/test_chronicle.py - Critical functions to test:

# JSON repair (complex state machine)
def test_repair_json_string_with_newlines(): ...
def test_repair_json_string_with_tabs(): ...
def test_repair_json_string_already_escaped(): ...

# Event selection (250 event cap)
def test_select_events_deduplication(): ...
def test_select_events_truncation_at_limit(): ...
def test_select_events_notable_prioritization(): ...

# Chapter finalization (trigger logic)
def test_should_finalize_time_threshold(): ...
def test_should_finalize_era_ending_event(): ...
def test_should_finalize_cooldown_period(): ...
```

**Estimated effort**: 2-3 days

---

### Phase 4: CLI Parity (Priority: LOW)

**Goal**: Add `/chronicle` and `/recap` commands to `v2_native_tools.py`.

**Estimated effort**: 1-2 days

---

### Phase 5: Optional Flavor (Priority: FUTURE)

Only add if Phase 1-2 events prove insufficient for narrative richness.

| Event | Filtering Required |
|-------|-------------------|
| `guardian_defeated` | Only 6 major guardians |
| `legendary_relic_acquired` | Only ~5 legendaries |
| `subject_acquired` | Cap at 3-5 per chapter |

---

### What NOT to Do

Per the design philosophy in STORYTELLING_OPTIONS.md:

> "The LLM naturally creates 4-7 eras because good storytelling requires meaningful chapters, not micro-chapters."

**Explicitly avoid adding:**
- Individual traditions (tree completion is enough)
- Archaeological sites (precursor homeworlds capture the important ones)
- Fleet composition (tactical, not narrative)
- Faction changes (internal politics = noise)
- Policy changes (administrative minutiae)
- Claims, espionage, market trades (too granular)

---

## 8. File Reference

| File | Lines | Purpose |
|------|-------|---------|
| `backend/core/chronicle.py` | 1,338 | Main chronicle generation engine |
| `backend/core/events.py` | 1,048 | Event detection & name resolution |
| `backend/core/signals.py` | 1,192 | Normalized data snapshots from Rust |
| `backend/core/database.py` | 1,383 | SQLite persistence + query interface |
| `backend/core/history.py` | ~400 | Snapshot recording, save_id computation |
| `backend/core/ingestion_worker.py` | ~180 | Background processing pipeline |
| `backend/bot/commands/chronicle.py` | 185 | Discord /chronicle command |
| `backend/bot/commands/recap.py` | ~100 | Discord /recap command |
| `backend/api/server.py` | ~650 | REST API endpoints |
| `electron/renderer/pages/ChroniclePage.tsx` | ~200 | Main Electron page |
| `electron/renderer/components/ChronicleContent.tsx` | ~150 | Chapter display component |
| `electron/renderer/components/ChronicleChapterList.tsx` | ~180 | Chapter navigation |

---

## 9. Constants Reference

| Constant | Value | Purpose |
|----------|-------|---------|
| `CHAPTER_TIME_THRESHOLD` | 50 years | Time between auto-finalized chapters |
| `MIN_YEARS_AFTER_EVENT` | 5 years | Cooldown after era-ending event |
| `MAX_CHAPTERS_PER_REQUEST` | 2 | Rate limit on finalization per call |
| `MAX_EVENTS_PER_CHAPTER_PROMPT` | 250 | Hard cap to avoid Gemini timeout |
| `MAX_EVENTS_CURRENT_ERA_PROMPT` | 200 | Smaller cap for current era |
| `STALE_EVENT_THRESHOLD` | 10 | Events before cache invalidation |
| `STALE_SNAPSHOT_THRESHOLD` | 5 | Snapshots before cache invalidation |

---

## 10. Conclusion

The chronicles feature demonstrates **excellent software engineering** with clean architecture, robust error handling, and thoughtful caching. The design philosophy (LLM-based chapters with hindsight) was the right choice.

### What's Working Well

- **Voice differentiation** by ethics (tested, validated in CHRONICLE_TESTING.md)
- **Incremental chapters** that persist across sessions
- **Era-ending event detection** for natural chapter breaks
- **Event truncation** to prevent prompt overflow
- **Caching** for fast repeat access

### Implementation Summary

| Phase | Events to Add | Impact | Effort |
|-------|--------------|--------|--------|
| **Phase 1** | `ascension_perk_selected`, `first_contact`, `ruler_changed`, `lgate_opened`, `crisis_level_increased` | Chapter-defining moments | 3-4 days |
| **Phase 2** | `great_khan_*`, `galactic_community_joined`, `tradition_tree_completed`, `precursor_discovered` | Era markers | 2-3 days |
| **Phase 3** | Unit tests for chronicle.py | Risk reduction | 2-3 days |
| **Phase 4** | CLI `/chronicle` command | Feature parity | 1-2 days |

**Total new events per game**: ~25-40 (only 5% increase)

### Guiding Principle

> "The LLM naturally creates 4-7 eras because good storytelling requires meaningful chapters, not micro-chapters."

The goal is **story fuel, not data completeness**. Each signal was stress-tested with the question: "Would this make for a compelling moment in a Stellaris Invicta-style chronicle?"

### Quick Reference: What to Add vs Skip

**ADD (chapter-defining):**
- Ascension perks, L-Gate, Become the Crisis
- First contact, ruler changes
- Great Khan, precursor homeworlds
- Tradition tree completion (not individual traditions)
- Galactic Community membership

**SKIP (noise):**
- Individual traditions, archaeological sites
- Fleet composition, faction changes
- Policy changes, claims, espionage
- Common space fauna encounters
- Market trades, minor relics
