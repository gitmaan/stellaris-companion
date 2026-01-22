# Phase 4 Plan: Precompute `/ask` + Parser Direction

**Status:** Approved
**Last updated:** 2026-01-15
**Scope:** Architecture after completing `CODING_AGENT_SPRINTS.md` extraction gaps

---

## 1) Current State (What's Done)

### Extraction gaps
- `CODING_AGENT_SPRINTS.md` is complete: all sprinted extraction gaps described in `GAPS_ANALYSIS.md` are implemented in `stellaris_save_extractor/` with unit tests using `test_save.sav`.
- Extractors follow the current design constraint: **regex/text scanning over `self.gamestate`** with section extraction helpers and brace counting; no dict-style `gamestate.get(...)`.

### Architecture
- `save_extractor.py` remains a compatibility shim.
- The "real" extractor is `stellaris_save_extractor/` with mixins + a composed facade in `stellaris_save_extractor/extractor.py`.
- Internal politics features live in `stellaris_save_extractor/politics.py` (per policy), wired into the facade.

### Current `/ask` behavior (hybrid) — TO BE REPLACED
- The existing "hybrid" pattern is: a slim snapshot + tools (e.g., `get_details(...)` / search) and the model decides whether to call tools.
- This causes quality and latency variance (see Section 2).

---

## 2) The Core Problem We're Solving

### Why hybrid causes quality + latency variance
- When the snapshot contains **some** information but not enough for the user's question, the model frequently:
  - assumes the snapshot is sufficient, producing vague answers, or
  - enters a tool-call spiral, producing high and unpredictable latency.
- The root cause is an **epistemic ambiguity**: the model struggles to distinguish:
  - "not present in snapshot" vs "does not exist in save".

### Benchmark evidence (from `OPTION_B_MIGRATION.md`)

| Metric | Hybrid (Slim + Tools) | Full Precompute (No Tools) |
|--------|----------------------|---------------------------|
| Avg latency | 20,579ms | **11,617ms** |
| Max latency | 41,612ms | **15,932ms** |
| Tool calls | 1-10 (unpredictable) | **0** |
| Latency variance | High | **Low** |

**Full precompute is 1.8× faster with dramatically lower variance.**

### Performance reality (from `PRECOMPUTE_ARCHITECTURE.md`)
- Full extraction on `test_save.sav` (71.4MB gamestate) is ~8.2s.
- Most time is concentrated in a few methods:
  - `get_situation()`: 3,233ms (40%)
  - `get_fallen_empires()`: 2,021ms (25%)
  - `get_player_status()`: 1,179ms (14%)
- Therefore: **synchronous full extraction in the request path is not viable**; background precompute is required.

---

## 3) Decision: Full Precompute with No Truncation

### Key Decision: Pass Everything to Gemini

After analysis, we decided **against** "budgeted" or "tiered" approaches that truncate data. Any form of truncation reintroduces the epistemic ambiguity problem.

**Decision: Inject the complete briefing with no truncation.**

### Why This Works

| Concern | Reality |
|---------|---------|
| Context window | Gemini has 1M tokens. 100KB briefing = ~25K tokens = **2.5% of context** |
| Cost | $0.075/1M tokens × 25K = **$0.002/query** (0.2 cents) |
| Late-game growth | Even 300KB = 75K tokens = 7.5% of context. Still fine. |
| Model confusion | Less data = more ambiguity. More data = model can find what it needs. |

### What "Complete" Means

```
COMPLETE BRIEFING CONTENTS (~45-100KB):
────────────────────────────────────────
✓ All metadata, identity, situation
✓ All resources (stockpiles, income, expenses)
✓ All leaders (names, traits, levels, ages)
✓ All planets (stability, districts, buildings, population)
✓ All diplomacy relations (opinion, treaties, allies, rivals)
✓ All fleets (names, power, ship counts)
✓ All starbases (modules, buildings)
✓ All technology (completed, current research)
✓ All wars (participants, exhaustion, war goals)
✓ All fallen empires (status, archetype, power)

NO TRUNCATION. NO "TOP K". NO SUMMARIES-ONLY.
The model gets everything and can answer any question.
```

### Escape Hatch

For obscure questions about raw save internals not covered by extractors:
- Separate `/search` command (not part of `/ask`)
- Uses `search_save_file()` tool
- Advanced users only

---

## 4) Decision: Stateful Conversations

### The Follow-up Problem

Without state, users can't ask natural follow-ups:
```
User: "What's my military power?"
Bot:  "125,210"
User: "How does that compare to my rivals?"
Bot:  [Needs context: we were talking about military power]
```

### Decision: Sliding Window Conversation State

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     CONVERSATION MODEL                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Each /ask query builds a prompt:                                            │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ [Note: Game state updated from 2431.02.18 to 2432.01.01]           │    │
│  │                                                                      │    │
│  │ CURRENT EMPIRE STATE (2432.01.01):                                  │    │
│  │ ```json                                                              │    │
│  │ {complete briefing, ~40K tokens}                                    │    │
│  │ ```                                                                  │    │
│  │                                                                      │    │
│  │ RECENT CONVERSATION:                                                 │    │
│  │ User: "What's my military power?"                                   │    │
│  │ Advisor: "Your military power is 125,210..." [truncated to 500ch]  │    │
│  │                                                                      │    │
│  │ User: "How does that compare to my rivals?"                         │    │
│  │ Advisor: "Your rivals have 89,000 and 156,000..." [truncated]      │    │
│  │                                                                      │    │
│  │ CURRENT QUESTION: "Should I attack them?"                           │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  DESIGN DECISIONS:                                                           │
│  ├── Re-inject briefing EVERY turn (ensures current game state)             │
│  ├── Keep last 5 turns of history (sliding window)                          │
│  ├── Truncate previous answers to ~500 chars each                           │
│  ├── Session timeout: 15 minutes of inactivity                              │
│  ├── Session scope: per user + per channel (Discord)                        │
│  └── Note when game date changes between turns                              │
│                                                                              │
│  TOKEN BUDGET PER QUERY:                                                     │
│  ├── Briefing (fresh each turn):  ~40,000 tokens                            │
│  ├── History (5 turns):            ~5,000 tokens                            │
│  ├── Current question:               ~200 tokens                            │
│  └── TOTAL:                       ~45,000 tokens (4.5% of 1M context)       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Why Re-inject Briefing Every Turn?

The user might save the game between questions:
```
Turn 1: [Briefing @ 2431] "Military power?" → "125,210"
        [User plays, builds ships, saves]
Turn 2: [Briefing @ 2432] "Did it improve?"
        → Model compares: briefing says 145,000, previous answer said 125,210
        → "Yes! Increased from 125,210 to 145,000 (+15.8%)"
```

This is a **feature** - model can track changes over time.

### Edge Cases

| Scenario | Handling |
|----------|----------|
| User inactive 15 min | Session expires, next /ask starts fresh |
| User switches channels | New session (scoped per channel) |
| Game date jumps backward | Note: "Game state reverted from X to Y" |
| Very long previous answer | Truncate to 500 chars + "..." |

---

## 5) Work Plan (Phased, Shippable)

### Phase 1 — Optimize Slow Extractors (1-2 days, nice-to-have)

**Goal:** Reduce precompute time where feasible. This is optimization gravy, not a blocker.

**Targets (from profiling):**
- `get_situation()` (3.2s): Avoid redundant subcalls, cache expensive computations
- `get_fallen_empires()` (2s): Single-pass scan pattern
- `get_player_status()` (1.2s): Reuse fleet computations from `get_fleets()`

**Success criteria:** Reduce from ~8.2s toward ~3s if achievable. But Phase 2 is the real solution regardless.

**Important:** Don't block on this. Background precompute (Phase 2) solves the UX problem even if extraction stays at 8s.

### Phase 2 — Background Precompute for `/ask` (MVP) (1-2 days, CRITICAL PATH)

**Goal:** Never block a Discord interaction on extraction.

**Behavior:**
```
Save Watcher detects change
        │
        ▼
Background thread: Extract complete briefing (~8s)
        │
        ├── While running: /ask uses last snapshot + disclaimer
        │   "Note: Using data from 2431.02.18 (new save processing...)"
        │
        └── When complete: Atomic swap of _complete_briefing_json
                           Next /ask uses fresh data
```

**Cold start (no cached snapshot):**
- Do one blocking extraction with Discord defer + progress message
- Or load from SQLite if available (Phase 3)

**Implementation:**
```python
class Companion:
    def __init__(self):
        self._complete_briefing_json: str | None = None
        self._briefing_game_date: str | None = None
        self._extraction_in_progress = threading.Event()
        self._extraction_in_progress.set()  # Initially "complete"

    def on_save_changed(self, path: Path):
        self._extraction_in_progress.clear()
        threading.Thread(target=self._extract_background, args=(path,)).start()

    def _extract_background(self, path: Path):
        extractor = SaveExtractor(str(path))
        briefing = extractor.get_complete_briefing()

        # Atomic swap
        self._complete_briefing_json = json.dumps(briefing, separators=(',', ':'))
        self._briefing_game_date = briefing['meta']['date']
        self._extraction_in_progress.set()

    def ask(self, question: str, session_key: str) -> str:
        if self._complete_briefing_json is None:
            return "No save loaded. Please load a save file first."

        is_stale = not self._extraction_in_progress.is_set()
        # Build prompt with conversation context...
```

### Phase 3 — Conversation State Manager (1 day)

**Goal:** Enable natural follow-up questions.

**Implementation:**
```python
class ConversationManager:
    def __init__(self, max_turns=5, timeout_minutes=15):
        self.sessions: dict[str, Session] = {}

    def build_prompt(self, session_key: str, briefing_json: str,
                     game_date: str, question: str) -> str:
        session = self._get_or_create(session_key)

        prompt = ""

        # Note game state changes
        if session.last_game_date and session.last_game_date != game_date:
            prompt += f"[Game updated: {session.last_game_date} → {game_date}]\n\n"

        # Current state (re-injected fresh)
        prompt += f"EMPIRE STATE ({game_date}):\n```json\n{briefing_json}\n```\n\n"

        # Recent history (sliding window)
        if session.history:
            prompt += "RECENT CONVERSATION:\n"
            for turn in session.history[-self.max_turns:]:
                prompt += f"User: {turn.question}\n"
                prompt += f"Advisor: {turn.answer[:500]}...\n\n"

        prompt += f"CURRENT QUESTION: {question}"
        return prompt

    def record_turn(self, session_key: str, question: str,
                    answer: str, game_date: str):
        session = self._get_or_create(session_key)
        session.history.append(Turn(question, answer))
        session.last_game_date = game_date
        session.last_active = time.time()
```

### Phase 4 — SQLite Snapshot Persistence (2-4 days)

**Goal:** Persistence across restarts + historical timeline foundation.

**Schema:**
```sql
CREATE TABLE snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    game_date TEXT NOT NULL,
    game_days INTEGER,
    captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Quick metrics (for timeline, no JSON parse needed)
    military_power INTEGER,
    economy_power INTEGER,
    tech_power INTEGER,
    colony_count INTEGER,

    -- Complete briefing for /ask injection
    full_briefing_json TEXT NOT NULL
);
```

**Behavior:**
- On startup/cold start: Load latest snapshot from SQLite
- During extraction: Write new snapshot, then swap in-memory cache
- Enables `/history` and timeline features (Phase 5+)

### ~~Phase 5 — Deterministic Slice Injection~~ (REMOVED)

**This phase has been removed.**

Any approach that selectively injects data based on question classification reintroduces the epistemic ambiguity problem. If the classifier guesses wrong, the model won't have the data it needs.

**If size becomes a problem in the future:**
- Use more aggressive JSON minification
- Accept larger prompts (Gemini handles it fine)
- Do NOT implement question-based filtering

---

## 6) Rust Parser: Path Forward

### Summary of External Research

**stellaris-dashboard approach:**
- Custom Rust parser using `nom` (parser combinators)
- PyO3/maturin bridge to Python
- Returns parsed data as Python dict

**jomini crate:**
- Professional Paradox-focused Rust library
- Claims 1 GB/s parsing throughput
- Powers PDX Tools and Paradox Game Converters
- No official Python bindings (would require PyO3 wrapping)

### Important Reality Check

**The "Section Indexer" idea won't help.**

Our profiling showed:
- Save file load: **46ms** (already fast!)
- Section extraction: Not the bottleneck
- The slow parts are **Python processing logic after extraction**

A Rust "section indexer" that returns byte offsets doesn't address the actual bottleneck. If we do Rust, it needs to be **full parsing to dict** (like stellaris-dashboard), not just indexing.

### Recommendation: Don't Do Rust Yet

**Background precompute solves the UX problem without Rust.**

With Phase 2:
- Extraction happens in background (~8s, user doesn't wait)
- `/ask` always responds quickly from cached briefing
- No packaging complexity (maturin, platform builds)

### Decision Gate for Rust

Only commit to Rust integration if:
1. Background precompute is insufficient (unlikely)
2. We need sub-second extraction for some reason
3. Packaging friction is acceptable for users

**Current decision: Defer Rust. Revisit after Phase 4 is complete.**

---

## 7) Answered Questions

| Question | Decision |
|----------|----------|
| Max `/ask` latency (p95)? | **15 seconds** (users expect advisor "thinking time") |
| Acceptable staleness window? | **10 seconds** with disclaimer |
| Prompt budget? | **No limit** - pass everything (~45-100KB, 2-5% of context) |
| Truncation strategy? | **None** - pass complete data, no "top K" |
| Conversation state? | **Yes** - sliding window, 5 turns, 15 min timeout |
| Deterministic slice injection? | **No** - removed, reintroduces hybrid problem |
| Rust extension? | **Deferred** - background precompute is sufficient |

---

## 8) Summary: What We're Building

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         /ASK ARCHITECTURE (FINAL)                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  SAVE WATCHER                                                                │
│       │                                                                      │
│       ▼                                                                      │
│  Background Thread ──► Extract complete briefing (~8s)                       │
│       │                 - All leaders, planets, fleets, etc.                │
│       │                 - No truncation                                      │
│       │                 - ~45-100KB JSON                                     │
│       │                                                                      │
│       ├──► Store in SQLite (for persistence + history)                      │
│       │                                                                      │
│       └──► Atomic swap to in-memory cache                                   │
│                                                                              │
│  /ASK QUERY                                                                  │
│       │                                                                      │
│       ▼                                                                      │
│  Build Prompt:                                                               │
│       │                                                                      │
│       ├── [Game state change note if applicable]                            │
│       ├── Complete briefing JSON (~40K tokens)                              │
│       ├── Last 5 conversation turns (~5K tokens)                            │
│       └── Current question                                                   │
│                                                                              │
│       │                                                                      │
│       ▼                                                                      │
│  Single Gemini Call (NO TOOLS)                                              │
│       │                                                                      │
│       ▼                                                                      │
│  Response + Record Turn in Session                                          │
│                                                                              │
│  PROPERTIES:                                                                 │
│  ✓ No epistemic ambiguity (model has everything)                            │
│  ✓ No tool call spirals (no tools)                                          │
│  ✓ Predictable latency (~10-15s)                                            │
│  ✓ Natural follow-up questions (conversation state)                         │
│  ✓ Handles game state changes between turns                                 │
│  ✓ Never blocks on extraction (background + stale fallback)                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 9) Implementation Order

1. **Phase 2 (Background Precompute)** — Critical path, do first
2. **Phase 3 (Conversation State)** — Enables good UX
3. **Phase 1 (Optimizer)** — Nice-to-have, do if time permits
4. **Phase 4 (SQLite)** — Persistence + history foundation

**Estimated total: 5-8 days for Phases 1-4**
