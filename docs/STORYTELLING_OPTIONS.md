# Empire Storytelling: Research Findings & Options Forward

> **Goal**: Transform the advisor into an immersive storyteller that chronicles your empire's history, inspired by Templin Institute's Stellaris Invicta.

**Related Documents**:
- [CHRONICLE_TESTING.md](./CHRONICLE_TESTING.md) - Prompt testing and validation results
- [CHRONICLE_IMPLEMENTATION.md](./CHRONICLE_IMPLEMENTATION.md) - Implementation plan and API spec

---

## Current Infrastructure Assessment

### What's Built & Working ✅

| Component | Status | Location | Notes |
|-----------|--------|----------|-------|
| **SQLite Database** | Complete | `backend/core/database.py` | Sessions, snapshots, events tables with indexes |
| **Event Detection** | Complete | `backend/core/events.py` | 50+ event types detected from snapshot deltas |
| **Snapshot History** | Complete | `backend/core/history.py` | Stores compact per-snapshot event state + session-level latest briefing cache |
| **Session Tracking** | Complete | `backend/core/database.py` | Per-campaign sessions with start/end |
| **Session Reporting** | Complete | `backend/core/reporting.py` | End-of-session summaries with deltas |
| **Personality System** | Complete | `personality.py` | Ethics/civics/authority-based dynamic prompts |
| **Save Parsing** | Complete | `stellaris_save_extractor/` | Mixin architecture + Rust bridge |
| **Discord Bot** | Complete | `backend/bot/commands/` | `/ask`, `/briefing`, `/status`, `/history`, `/end_session` |
| **Electron App** | Complete | `electron/` | Electron UI + packaged local backend/binaries |

### Event Types Currently Detected

The `events.py` module already detects these narrative-ready events:

- **Wars**: `war_started`, `war_ended`, `war_status_changed`
- **Leaders**: `leader_hired`, `leader_died`, `ruler_changed`
- **Diplomacy**: `alliance_formed`, `rivalry_declared`, `federation_joined`, `treaty_signed`
- **Expansion**: `colony_founded`, `system_claimed`, `starbase_upgraded`
- **Technology**: `technology_completed`, `tradition_adopted`, `ascension_perk_selected`
- **Crisis**: `crisis_started`, `crisis_defeated`, `fallen_empire_awakened`
- **Economy**: `economic_crisis`, `megastructure_completed`
- **Milestones**: `first_contact`, `galactic_community_joined`

### What's Designed But Not Implemented 📋

The `docs/CHRONICLE_ROLEPLAY_FEATURES.md` contains a 518-line specification for:

1. **Chronicle System** - `backend/core/chronicle.py` (proposed)
   - `narrate_event()` - Convert raw events to dramatic prose
   - `generate_recap()` - "Previously on..." style summaries
   - `get_empire_story_arc()` - Extract major plot points

2. **Era Naming System** - Auto-detect and name campaign periods
   - Triggers: game start, first contact, first war, crisis, federation, victory
   - Database table: `eras` (name, start_date, end_date, trigger_event_id, description)

3. **Response Modes** - Three personality framings
   - `ADVISOR` - Factual, strategic, data-focused (current)
   - `CHRONICLE` - Narrative with historical references
   - `IMMERSIVE` - Full roleplay, never breaks character

4. **Entity Memory** - Track named entities across campaign
   - Database table: `named_entities` (entity_type, game_id, custom_name, narrative_notes)
   - Personalize leader/fleet/planet references

5. **Reactive Personality** - Personality evolves based on history
   - War outcomes affect confidence
   - Crisis events add existential urgency
   - Long peace shifts toward philosophical tone

---

## Options Forward

### Option A: Chronicle Core (Minimum Viable Storytelling)

**Focus**: Get `/recap` working with dramatic narrative generation

**Deliverables**:
- `backend/core/chronicle.py` module
- `generate_recap(session_id, style="dramatic")` function
- `/recap` Discord command
- "Generate Recap" button in Electron RecapPage

**How it works**:
1. Fetch recent events from database
2. Build context with personality + empire identity
3. Single LLM call with narrative prompt
4. Return Stellaris Invicta style prose

**Infrastructure requirements**: ✅ All in place

**New code**: ~200-300 lines (chronicle.py + command handler)

**Example output**:
```
═══════════════════════════════════════════════════════════
           PREVIOUSLY ON: THE GREATER TERRAN UNION
═══════════════════════════════════════════════════════════

The year is 2285. What began as a minor border dispute with the
Kel-Azaan Consciousness has escalated into total war.

Admiral Chen's Third Fleet scored a decisive victory at Procyon,
breaking the enemy's forward momentum—but at great cost. The
legendary battleship "Indomitable" was lost with all hands.

Meanwhile, our scientists have unlocked the secrets of jump drive
technology. The stars themselves now bend to our will.

The Third Fleet regroups at Arcturus. The enemy masses at the border.
The galaxy holds its breath.

What happens next is up to you.
═══════════════════════════════════════════════════════════
```

#### Option A Implementation Approaches

Given the recent DB changes (commit `9eaa4c2`), here are three implementation approaches:

---

**A1: Events-Only Recap (Simplest)**

Pull events from the `events` table and narrativize them directly.

```python
# chronicle.py
def generate_recap(session_id: str, db: GameDatabase) -> str:
    events = db.get_recent_events(session_id=session_id, limit=30)
    session = db.get_session_by_id(session_id)

    prompt = f"""
    Empire: {session['empire_name']}
    Current Date: {session['last_game_date']}

    Recent Events (newest first):
    {format_events(events)}

    Write a dramatic "Previously on..." recap in the style of Stellaris Invicta.
    """
    return call_gemini(prompt)
```

**Pros**:
- No new DB queries needed
- Events already have `summary` field with human-readable text
- Works with compact snapshot storage

**Cons**:
- Limited context (no current empire state)
- No personality injection

---

**A2: Events + Latest State (Recommended)**

Combine events with `sessions.latest_briefing_json` for richer context.

```python
def generate_recap(session_id: str, db: GameDatabase) -> str:
    events = db.get_recent_events(session_id=session_id, limit=30)
    latest_briefing = db.get_session_latest_briefing_json(session_id)
    session = db.get_session_by_id(session_id)

    # Extract identity for personality
    identity = extract_identity(latest_briefing)  # ethics, civics, authority
    personality_prompt = build_optimized_prompt(identity, situation=None)

    prompt = f"""
    {personality_prompt}

    Empire: {session['empire_name']}
    Current State: {summarize_state(latest_briefing)}

    Recent Events:
    {format_events(events)}

    Write a dramatic "Previously on..." recap. Stay in character.
    """
    return call_gemini(prompt)
```

**Pros**:
- Personality-aware (advisor speaks in character)
- Current state provides context (military power, resources, wars)
- Uses existing `sessions.latest_briefing_json` (no extra DB load)

**Cons**:
- Slightly more complex
- Need to extract identity from briefing

---

**A3: Events + Baseline + Latest (Full Arc)**

Use baseline snapshot + events + latest state for complete campaign arc.

```python
def generate_recap(session_id: str, db: GameDatabase) -> str:
    # Get baseline (first snapshot with full briefing)
    first, last = db.get_first_last_snapshot_rows(session_id)
    baseline_briefing = json.loads(first['full_briefing_json'] or first['event_state_json'])

    # Get current state
    latest_briefing = db.get_session_latest_briefing_json(session_id)

    # Get events
    events = db.get_recent_events(session_id=session_id, limit=50)

    prompt = f"""
    Empire: {session['empire_name']}

    === CAMPAIGN START ({first['game_date']}) ===
    {summarize_state(baseline_briefing)}

    === CURRENT STATE ({last['game_date']}) ===
    {summarize_state(latest_briefing)}

    === KEY EVENTS ===
    {format_events(events)}

    Write an epic "Previously on..." that shows how far the empire has come.
    """
    return call_gemini(prompt)
```

**Pros**:
- Shows full campaign arc ("where we started" → "where we are")
- Best for dramatic storytelling
- Can highlight transformation

**Cons**:
- More DB queries
- Baseline might be large (full_briefing_json)
- Only useful for longer campaigns

---

**Recommendation: Start with A2**

A2 (Events + Latest State) is the sweet spot:
- Uses the new `sessions.latest_briefing_json` efficiently
- Enables personality-driven narrative
- Can add A3's baseline comparison later as an enhancement

---

#### Available DB Queries (from `database.py`)

```python
# Session data
db.get_session_by_id(session_id) -> {id, empire_name, started_at, last_game_date, ...}
db.get_sessions(limit=50) -> list of sessions with snapshot stats

# Events (narrative fuel)
db.get_recent_events(session_id=id, limit=20) -> [{event_type, summary, data_json, game_date}, ...]

# State snapshots
db.get_session_latest_briefing_json(session_id) -> full current state JSON
db.get_first_last_snapshot_rows(session_id) -> (baseline_row, latest_row)

# Snapshot timeline
db.get_recent_snapshot_points(session_id, limit=8) -> [{game_date, military_power, colony_count, ...}]
```

#### Event Types Available for Narrative

From `events.py`, these event types are detected and stored:

| Category | Event Types |
|----------|-------------|
| **Military** | `military_power_change`, `military_fleet_change` |
| **Wars** | `war_started`, `war_ended` |
| **Leaders** | `leader_hired`, `leader_died`, `ruler_changed` |
| **Diplomacy** | `alliance_formed`, `alliance_lost`, `rivalry_declared`, `rivalry_ended`, `treaty_signed`, `treaty_lost`, `federation_joined`, `federation_left` |
| **Economy** | `resource_crisis` (energy/food/minerals go negative) |
| **Territory** | `colony_count_change` |
| **Technology** | `tech_completed` |
| **Megastructures** | `megastructure_started`, `megastructure_stage_completed`, `megastructure_completed` |
| **Crisis** | `crisis_started`, `crisis_type_change`, `crisis_ended` |
| **Fallen Empires** | `fallen_empire_awakened`, `fallen_empire_destroyed` |

Each event has:
- `event_type`: machine-readable category
- `summary`: human-readable one-liner (e.g., "War started: The Humiliation of Blorg")
- `data`: structured details (names, IDs, before/after values)
- `game_date`: when it happened

---

### Option B: Era System (Campaign Structure)

**Focus**: Automatically detect and name significant campaign periods

**Deliverables**:
- New `eras` database table
- Era detection logic in `backend/core/eras.py`
- Era naming via LLM (thematic names)
- `/era` Discord command
- Era headers in Electron timeline

**Era triggers** (from spec):
| Trigger | Era Name Example |
|---------|------------------|
| Game start | "The Founding" |
| First contact | "The Awakening" |
| First war | "The Trial by Fire" |
| Major expansion | "The Great Expansion" |
| Crisis begins | "The Long Night" |
| Federation formed | "The Alliance" |
| Victory | "The Ascension" |

**Database schema**:
```sql
CREATE TABLE eras (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL,
    name TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT,  -- NULL if current era
    trigger_event_id INTEGER,
    description TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id),
    FOREIGN KEY (trigger_event_id) REFERENCES events(id)
);
```

**Infrastructure requirements**:
- ✅ Events table exists
- ⚠️ Need `eras` table migration
- ⚠️ Need era detection triggers

**New code**: ~400-500 lines

**Example output**:
```
📜 THE LONG NIGHT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Since: 2350.1.1 (35 years)

The Prethoryn Scourge arrived from beyond the galactic rim,
consuming three minor civilizations before the galaxy could
respond. The Greater Terran Union leads a desperate coalition.

Key Events This Era:
• Fall of the Kel-Azaan Consciousness (2351)
• Formation of the Galactic Defense Pact (2352)
• Battle of the Shroud Gate (2358)
• Death of Fleet Admiral Chen (2360)

Military Power: 45,000 → 125,000 (+178%)
Colonies Lost: 3
Allies Gained: 7
```

---

### Option C: Response Mode System

**Focus**: Let users toggle between Advisor / Chronicle / Immersive

**Deliverables**:
- `ResponseMode` enum in personality system
- Mode persistence (session setting or user preference)
- System prompt variants for each mode
- `/mode` Discord command
- Mode toggle in Electron settings

**Mode definitions**:

| Mode | Behavior | Example Response |
|------|----------|------------------|
| **Advisor** | Factual, strategic, data-focused | "Your fleet power is 15,000. The enemy has 12,000. You have numerical advantage." |
| **Chronicle** | Narrative with historical context | "Since the War of Proxima, your fleets have grown to 15,000—a testament to the reforms Admiral Chen championed before her death." |
| **Immersive** | Full roleplay, never breaks character | "*adjusts tactical display* Your Majesty, the Third Fleet stands ready. Fifteen thousand souls await your command. Shall we remind these xenos why they should fear Terra?" |

**Infrastructure requirements**: ✅ Personality system ready

**New code**: ~150-200 lines (mode enum + prompt variants)

---

### Option D: Named Entity Memory

**Focus**: Track and personalize references to fleets/leaders/planets

**Deliverables**:
- New `named_entities` database table
- Entity tracking across snapshots
- `/name` Discord command
- Entity context injection into prompts
- Narrative notes generation

**Database schema**:
```sql
CREATE TABLE named_entities (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,  -- "leader", "fleet", "planet", "empire"
    game_id TEXT NOT NULL,      -- In-game ID for matching
    custom_name TEXT,           -- Player-assigned name
    narrative_notes TEXT,       -- "Survived 3 battles", "Founded in 2225"
    first_seen_date TEXT,
    last_seen_date TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);
```

**How it enriches narrative**:
- Before: "An admiral led your fleet to victory"
- After: "Admiral Chen, hero of the Proxima Campaign, led the Third Fleet to victory"

**Infrastructure requirements**:
- ⚠️ Need `named_entities` table
- ⚠️ Need entity ID tracking across save snapshots
- ⚠️ Need game_id extraction from save parsing

**New code**: ~500-600 lines

---

### Option E: Reactive Personality Evolution

**Focus**: Advisor personality shifts based on campaign history

**Deliverables**:
- `compute_personality_modifiers()` function
- Modifier injection into system prompts
- Personality evolution tracking

**Modifiers** (from spec):
| History Pattern | Personality Shift |
|-----------------|-------------------|
| 3+ wars won | Increased confidence, aggressive options |
| War lost | More cautious recommendations |
| Long peace (50+ years) | Philosophical, diplomatic focus |
| Crisis survived | Existential wisdom, preparation focus |
| Multiple leader deaths | Somber, memorial references |
| Rapid expansion | Ambitious, manifest destiny tone |

**Infrastructure requirements**: ✅ Events table has the data

**New code**: ~200-300 lines

---

### Option F: Full Chronicle Package

**Focus**: Implement all features as integrated system

**Phases** (from spec):
1. Chronicle backend (Options A) → `/recap`, `narrate_event()`
2. Response modes (Option C) → mode switching
3. Era system (Option B) → era detection and naming
4. Discord commands → `/recap`, `/era`, `/chronicle`, `/name`, `/mode`
5. Entity memory (Option D) → named entities
6. Reactive personality (Option E) → personality evolution
7. Electron UI → Timeline visualization, era headers

---

## Building Chapters: LLM-Generated Eras (Recommended)

**The question**: Which approach builds chapters throughout a full game?

**The answer**: Let the LLM analyze all events and create chapters when the user requests a chronicle. Since we're paying for narrative generation anyway, let the LLM decide chapter structure with full hindsight.

### Why LLM-Based Is Better Than Rule-Based

**Rule-based (during gameplay):**
```
Events happen → Rules detect era triggers → Eras stored → LLM writes chapters
                       ↑
              Complex logic here
              (cooldowns, priorities, min durations, etc.)
```

**LLM-based (on demand):**
```
Events happen → Events stored → User requests /chronicle → LLM creates eras + writes chapters
                                                              ↑
                                                    One intelligent pass
```

### The Key Insight: Hindsight Creates Better Chapters

Rule-based (during gameplay):
```
2265: War starts → "Era: The War of Expansion" (seems important at the time)
2267: War ends quickly, minor victory → awkward 2-year era
```

LLM-based (looking back):
```
LLM sees: "That 2265 war was a footnote. The REAL turning point
was the 2280 crisis. I'll group 2265-2280 as 'The Long Peace'
and start a new era at the crisis."
```

### Benefits of LLM-Based Era Generation

| Aspect | Rule-Based | LLM-Based |
|--------|------------|-----------|
| Era detection | Complex rules (cooldowns, priorities) | LLM decides naturally |
| Era naming | Templates ("The {war_name}") | Thematic, contextual names |
| Bloat prevention | Manual rules needed | LLM's narrative sense |
| Code complexity | High (~200+ lines) | Low (~50 lines) |
| Hindsight | None | Full story visible |
| Chapter quality | Mechanical boundaries | Narratively coherent |

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     DURING GAMEPLAY                         │
│                                                             │
│  Save detected → Snapshot stored → Events computed          │
│                                    (existing system)        │
│                                                             │
│  No era detection. Just accumulate events.                  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   USER REQUESTS /chronicle                  │
│                                                             │
│  1. Load all events + baseline + current state              │
│  2. Check cache: recent enough? → Return cached             │
│  3. Otherwise: LLM generates eras + narratives in one pass  │
│  4. Cache result for future requests                        │
│  5. Return formatted chronicle                              │
└─────────────────────────────────────────────────────────────┘
```

### Implementation

```python
# backend/core/chronicle.py

def generate_chronicle(session_id: str, db: GameDatabase) -> Chronicle:
    """Generate a full chronicle with LLM-created eras."""

    # Check cache first
    cached = db.get_cached_chronicle(session_id)
    current_snapshot_count = db.get_snapshot_count(session_id)

    if cached and (current_snapshot_count - cached.snapshot_count) < 10:
        return cached  # Use cached version if < 10 new snapshots

    # Gather all data
    events = db.get_all_events(session_id=session_id)
    baseline = db.get_baseline_snapshot(session_id)
    latest = db.get_session_latest_briefing_json(session_id)
    session = db.get_session_by_id(session_id)
    identity = extract_identity(latest)

    prompt = f"""
    {build_personality_prompt(identity)}

    You are chronicling the history of {session['empire_name']}.

    === FOUNDING STATE ({baseline['game_date']}) ===
    {summarize_state(baseline)}

    === CURRENT STATE ({session['last_game_date']}) ===
    {summarize_state(latest)}

    === COMPLETE EVENT HISTORY ===
    {format_all_events(events)}

    Create a chronicle divided into 4-7 chapters (eras). For each chapter:
    1. Choose a thematic name that captures its essence
    2. Define start/end dates based on natural turning points
    3. Identify the theme (founding, exploration, conflict, peace, crisis, triumph)
    4. Write 2-4 paragraphs of dramatic narrative in your voice

    The LLM naturally avoids creating too many eras because good storytelling
    requires meaningful chapters, not a chapter for every minor event.

    Return as JSON:
    {{
      "eras": [
        {{
          "name": "The Founding",
          "start_date": "2230.1.1",
          "end_date": "2245.3.12",
          "theme": "founding",
          "narrative": "When President Chen launched..."
        }},
        ...
      ]
    }}
    """

    response = call_gemini(prompt, response_format="json")

    # Cache for future requests
    db.cache_chronicle(session_id, response, current_snapshot_count)

    return Chronicle(eras=response.eras)
```

### Chronicle Output Example

```
═══════════════════════════════════════════════════════════
THE UNITED EARTH DIRECTORATE: A CHRONICLE IN FIVE ERAS
═══════════════════════════════════════════════════════════

BOOK I: THE FOUNDING (2230-2245)

President Chen launched humanity into the stars with two colonies
and a dream. For fifteen years, we built in silence...

BOOK II: THE AWAKENING (2245-2265)

First contact with the Blorg changed everything. Then came the
Hegemony, and we learned the galaxy was not as empty as we'd hoped...

BOOK III: THE WAR OF RECLAMATION (2265-2280)

Fifteen years of fire. Admiral Tanaka's campaigns across three
sectors. The fall of Hegemony Prime. We became conquerors...

BOOK IV: THE GOLDEN AGE (2280-2350)

Seventy years of peace. Three generations of rulers built what
warriors had won. The Federation grew from dream to reality...

BOOK V: THE LONG NIGHT (2350-Present)

The swarm came from outside the galaxy. Everything we built now
burns. But we have faced extinction before...

═══════════════════════════════════════════════════════════
```

### Cost Analysis

| Approach | Era Detection | Chronicle Generation | Total per /chronicle |
|----------|---------------|---------------------|---------------------|
| Rule-based | $0 (code) | ~$0.0008 | $0.0008 |
| LLM-based | Included ↓ | ~$0.0012 | $0.0012 |

**Difference: $0.0004 per chronicle** (~0.04 cents). Negligible.

LLM calls only happen when user explicitly requests `/chronicle`, not during gameplay.

### Caching Strategy

```sql
CREATE TABLE cached_chronicles (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL UNIQUE,
    eras_json TEXT NOT NULL,  -- Full chronicle with narratives
    generated_at TEXT NOT NULL,
    snapshot_count INTEGER NOT NULL,  -- Snapshots when generated
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);
```

**Regeneration logic:**
- If < 10 new snapshots since last generation → return cached
- If 10+ new snapshots → regenerate (significant new events)
- User can force regenerate with `/chronicle --refresh`

### What About `/era` (Current Era)?

For quick "what era am I in?" queries without generating a full chronicle:

**Option 1: Use cached chronicle's last era**
```python
def get_current_era(session_id: str, db: GameDatabase) -> Era | None:
    cached = db.get_cached_chronicle(session_id)
    if cached:
        return cached.eras[-1]  # Last era is current
    return None  # No chronicle generated yet
```

**Option 2: Quick heuristic (no LLM)**
```python
def get_current_era_quick(session: Session) -> str:
    if session.in_crisis:
        return "The Long Night"
    elif session.at_war:
        return f"The {session.current_war_name}"
    elif session.years_since_last_war > 50:
        return "The Long Peace"
    else:
        return "The Current Age"
```

### Enriching Schema for Better Narratives

These tables help the LLM write richer chapters:

```sql
-- Track leader careers for meaningful death narratives
CREATE TABLE leader_records (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL,
    leader_id INTEGER,
    name TEXT NOT NULL,
    class TEXT,  -- admiral, general, scientist, ruler
    hired_date TEXT,
    death_date TEXT,
    career_events TEXT,  -- JSON: ["won Battle of X", "discovered Y"]
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

-- Track war context for richer conflict narratives
CREATE TABLE war_records (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL,
    war_name TEXT NOT NULL,
    start_date TEXT,
    end_date TEXT,
    outcome TEXT,  -- victory, defeat, status_quo
    enemy_empire TEXT,
    casus_belli TEXT,
    territory_changed TEXT,  -- JSON: {gained: [], lost: []}
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

-- Track ruler succession for generational sagas
CREATE TABLE rulers (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL,
    name TEXT NOT NULL,
    title TEXT,
    start_date TEXT,
    end_date TEXT,
    succession_type TEXT,  -- elected, inherited, coup
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

-- Track empire relationships over time
CREATE TABLE empire_relationships (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL,
    empire_name TEXT NOT NULL,
    first_contact_date TEXT,
    current_status TEXT,  -- ally, rival, neutral, vassal, overlord, destroyed
    arc_type TEXT,  -- "nemesis", "faithful_ally", "redemption", "betrayer"
    key_events TEXT,  -- JSON: ["saved us in 2250", "betrayed treaty"]
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);
```

### Why the LLM Won't Create Too Many Eras

The LLM naturally creates 4-7 eras because:

1. **Narrative instinct**: Good storytelling requires meaningful chapters, not micro-chapters
2. **Prompt guidance**: "4-7 chapters" sets expectations
3. **Event density**: Minor events get grouped; only major turning points become chapter breaks
4. **Hindsight**: Seeing the full story, the LLM knows which events actually mattered

No complex bloat-prevention rules needed.

### A2 vs A3 Summary

| Dimension | A2 (Events + Latest) | A3 + LLM Eras |
|-----------|---------------------|---------------|
| **Chapters** | ❌ No | ✅ Yes (LLM-generated) |
| **Best for** | Quick session recaps | Full campaign chronicles |
| **Prose style** | Dramatic present tense | Epic multi-chapter saga |
| **Era creation** | N/A | On-demand when user requests `/chronicle` |
| **Schema needs** | Minimal | `cached_chronicles` + enrichment tables |
| **When to use** | `/recap` (recent events) | `/chronicle` (full history) |

### Recommended Approach

Build **both** with LLM-generated eras:

1. **A2 for `/recap`** - Quick, personality-driven, recent events only
2. **A3 + LLM for `/chronicle`** - Full chapter-based narrative with LLM-created eras
3. **No live era detection** - Eras created on-demand with full hindsight
4. **Enrichment tables** - Leader records, war records, rulers improve narrative quality

This way:
- Short sessions get good recaps (A2)
- Long campaigns get epic chronicles with intelligent chapter breaks (A3)
- No complex rule-based era detection code
- LLM sees the whole story before deciding chapters

---

## Recommendation

### Build A3 with LLM-Generated Eras

**Decision**: Let the LLM create chapters on-demand when the user requests a chronicle.

**Rationale**:
1. **Hindsight creates better chapters** - LLM sees the whole story before deciding turning points
2. **No bloat rules needed** - LLM naturally creates 4-7 meaningful chapters
3. **Simpler code** - No era detection logic, just event accumulation (already done)
4. **Better names** - LLM creates thematic names with full context
5. **Negligible cost difference** - ~$0.0004 more per chronicle

### Implementation Order

**Phase 1: Chronicle Generation**
1. Create `backend/core/chronicle.py`
2. Implement `generate_recap()` (A2 style - quick, recent events)
3. Implement `generate_chronicle()` (A3 style - LLM creates eras + narratives)
4. Add `cached_chronicles` table for caching
5. Add `/recap` and `/chronicle` Discord commands

**Phase 2: Enriched Schema**
1. Add `leader_records` table (track careers for richer narratives)
2. Add `war_records` table (track conflicts with context)
3. Add `rulers` table (track succession for generational sagas)
4. Hook enrichment into event detection

**Phase 3: Polish**
1. Add `empire_relationships` table (nemesis/ally arcs)
2. Response modes (Option C)
3. Electron UI with chronicle viewer
4. `/chronicle --refresh` to force regeneration

### Commands

| Command | Approach | Use Case |
|---------|----------|----------|
| `/recap` | A2 | "What happened recently?" - quick, present-focused |
| `/chronicle` | A3 + LLM | "Tell me my empire's story" - full chapter narrative |
| `/era` | Cache lookup | "What era am I in?" - returns last era from cached chronicle |

### Files to Create/Modify

**Phase 1: Chronicle Generation**
- **Modify**: `backend/core/database.py` (add `cached_chronicles` table)
- **Create**: `backend/core/chronicle.py` (recap + chronicle generation, LLM calls)
- **Create**: `backend/bot/commands/recap.py`
- **Create**: `backend/bot/commands/chronicle.py`
- **Modify**: `backend/bot/cog.py` (register new commands)

**Phase 2: Enriched Schema**
- **Modify**: `backend/core/database.py` (add `leader_records`, `war_records`, `rulers`)
- **Modify**: `backend/core/events.py` (populate enriched tables on event detection)
- **Create**: `backend/core/enrichment.py` (helpers for leader/war/ruler tracking)

**Phase 3: Polish**
- **Modify**: `backend/core/database.py` (add `empire_relationships`)
- **Modify**: `personality.py` (add `ResponseMode` enum)
- **Create**: `backend/bot/commands/mode.py`

---

## Technical Notes

### Snapshot Storage Model (Important for Storytelling)

Recent changes make history storage much more scalable without reducing narrative capability:

- **Per-snapshot compact state**: each snapshot stores `event_state_json` (the minimal structured state used for diffing + event detection).
- **Baseline full state**: only the baseline snapshot keeps a full `full_briefing_json` payload (to avoid DB bloat).
- **Latest full state cached once**: `sessions.latest_briefing_json` is updated on each ingest and used for “current state” prompts and end-of-session reporting.

**Implication for storytelling**:
- Recaps/timelines should primarily be driven by the `events` table + per-snapshot `event_state_json` (fast and stable across mods/versions).
- If you later want “time travel” deep dives with full detail at arbitrary past snapshots, add periodic “anchor” snapshots (e.g. store full briefing every N snapshots or at era boundaries) rather than reverting to “store full briefing every snapshot”.

### LLM Considerations

- **Model**: Gemini 3 Flash handles narrative well
- **Context**: Events + personality fit within limits
- **Prompt structure**: Feed events as structured data, LLM creates eras + narratives
- **Chronicle caching**: Cache generated chronicles, regenerate after 10+ new snapshots
- **Cost**: ~$0.0012 per `/chronicle` call (eras + narrative in one pass)

### Database Migrations

New tables needed for chronicle system:
1. `cached_chronicles` - Store LLM-generated eras and narratives
2. `leader_records`, `war_records`, `rulers` - Enrichment tables (Phase 2)
3. `empire_relationships` - Track nemesis/ally arcs (Phase 3)

Migration path:
1. Increment `schema_version` in database.py
2. Add migration in `_migrate_schema()`
3. Create tables with proper foreign keys

### Discord Message Limits

Dramatic recaps may exceed 2000 chars. Solutions:
- Split into multiple messages with `───` separators
- Use Discord embeds for structured sections
- Offer "full" vs "brief" recap styles

---

## Full File List (Recommended Implementation)

### Phase 1: Chronicle Generation (LLM-Based Eras)
| Action | File | Purpose |
|--------|------|---------|
| Modify | `backend/core/database.py` | Add `cached_chronicles` table, migration v3 |
| Create | `backend/core/chronicle.py` | `generate_recap()`, `generate_chronicle()` with LLM era creation |
| Create | `backend/bot/commands/recap.py` | `/recap` command handler |
| Create | `backend/bot/commands/chronicle.py` | `/chronicle` command handler |
| Create | `backend/bot/commands/era.py` | `/era` command handler (reads from cache) |
| Modify | `backend/bot/cog.py` | Register new commands |

### Phase 2: Enriched Schema
| Action | File | Purpose |
|--------|------|---------|
| Modify | `backend/core/database.py` | Add `leader_records`, `war_records`, `rulers` tables |
| Modify | `backend/core/events.py` | Populate enriched tables on event detection |
| Create | `backend/core/enrichment.py` | Leader/war/ruler tracking helpers |

### Phase 3: Polish
| Action | File | Purpose |
|--------|------|---------|
| Modify | `backend/core/database.py` | Add `empire_relationships` table |
| Modify | `personality.py` | Add `ResponseMode` enum, prompt variants |
| Create | `backend/bot/commands/mode.py` | `/mode` command handler |
| Modify | `backend/core/companion.py` | Accept mode parameter |
