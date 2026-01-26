# Option D: Push Extraction Upstream (Unified History Signals)

## Summary

The long-term fix is to **eliminate duplicate parsing paths** (especially regex-on-gamestate in `backend/core/history.py`) by pushing all “history-relevant extraction” **upstream into the ingestion pipeline** (where we already have an active Rust parser session). The history module becomes **pure diffing/event-enrichment**, consuming a compact, normalized “signals” payload computed once per snapshot.

This prevents Chronicle/Recap narratives from seeing unresolved placeholders (e.g. `%LEADER_2%`) and removes a major performance footgun: loading the full 70MB+ `gamestate` string just to compute history deltas.

---

## Problem Statement

### Symptoms
- Chronicle narratives include fabricated or placeholder names like `Seedkugh`, `Hoggagha`, or `%LEADER_2%`.
- Event summaries show unresolved `name_key` values instead of resolved human names.

### Root causes
1. **Two independent extraction paths** for the same concepts:
   - “Good path”: Rust-session-backed extraction in `stellaris_save_extractor/*` (e.g. `stellaris_save_extractor/leaders.py`) which resolves name templates.
   - “Bad path”: `backend/core/history.py` parsing raw `gamestate` with bounded regex windows and no proper name resolution.
2. **Chronicle depends on events**, and events depend on history payload:
   - `backend/core/events.py` builds leader events from `history["leaders"]` and currently uses `name_key` in summaries.
   - Chronicle consumes those summaries, compounding placeholder leakage.
3. **Performance bottleneck**:
   - `backend/core/ingestion_worker.py` explicitly loads `extractor.gamestate` for history enrichment, which can materialize 70MB+ strings.

---

## Goals

1. **Single source of truth** for leader names and other “history signals”.
2. **No raw gamestate string required** for snapshot history/enrichment in the ingestion pipeline.
3. **History module becomes diff-only** (no parsing), so it can’t drift from the extractor.
4. Chronicle/Recap/event summaries should use **resolved names** whenever available.

---

## Non-goals (for this refactor)

- Perfect localization of all in-game strings (we only need stable, human-readable names).
- Rewriting Chronicle’s narrative logic beyond improving inputs.
- Replacing all regex parsing everywhere in one sweep (we’ll migrate incrementally).

---

## Proposed Architecture

### New concept: `SnapshotSignals` (versioned)

At ingestion time (tier `t2` worker), build a compact payload containing just the pieces needed for:
- event detection (`backend/core/events.py`)
- recap/chronicle context
- snapshot “history” display

This payload is attached to the snapshot as structured JSON and used downstream.

**Key properties**
- Built once per snapshot in the worker, while `rust_bridge.session(save_path)` is active.
- Uses Rust-backed `SaveExtractor` methods (or direct Rust session calls) for quality and performance.
- Versioned so we can evolve it safely.

### Data flow

1. `backend/core/ingestion_worker.py` (tier `t2`)
   - Starts `rust_bridge.session(save_path)`
   - Initializes `SaveExtractor(save_path)`
   - Builds:
     - `briefing = extractor.get_complete_briefing()`
     - `signals = build_snapshot_signals(extractor, briefing)`
   - Attaches:
     - `briefing["history"] = signals_to_history(signals)` (or `briefing["signals"] = signals` if we want separate fields)
   - Serializes and returns briefing JSON to main process for DB write.

2. `backend/core/history.py`
   - Stops parsing `gamestate`.
   - Provides diff helpers operating only on `SnapshotSignals` / normalized history.

3. `backend/core/events.py`
   - Reads normalized history/signal payload.
   - Uses `leader.name` (resolved) first, falls back to `name_key`, then `#id`.

4. Chronicle (`backend/core/chronicle.py`)
   - Continues to use event list; event summaries now contain correct names.

---

## SnapshotSignals Schema (initial draft)

Store as JSON with `format_version` (int).

### Top-level
```json
{
  "format_version": 1,
  "generated_at": "2026-01-24T00:00:00Z",
  "player_id": 0,
  "leaders": {
    "count": 12,
    "leaders": [
      {
        "id": 123,
        "class": "admiral",
        "level": 5,
        "name": "Admiral Chen",
        "name_key": "%LEADER_2%",
        "death_date": null,
        "date_added": "2240.01.01",
        "recruitment_date": "2240.01.01"
      }
    ]
  },
  "wars": {
    "player_at_war": true,
    "count": 1,
    "wars": ["War of ..."]
  },
  "diplomacy": {
    "allies": [12, 55],
    "rivals": [98],
    "treaties": { "commercial_pact": [12] }
  }
}
```

### Notes
- Keep both `name` and `name_key`:
  - `name` drives UI/event summaries/Chronicle.
  - `name_key` helps debugging and future localization work.
- Include only fields needed for event diffs and narrative quality.
- Prefer stable IDs for diffs (`leader.id`, empire/country ids, etc.).

---

## Implementation Plan (Incremental Milestones)

### Milestone D1 (Leaders-only, unblock Chronicle quality)

**Objective:** Chronicle and event summaries use resolved leader names.

Changes:
1. Add `backend/core/signals.py` (new module)
   - `build_snapshot_signals(*, extractor: SaveExtractor, briefing: dict) -> dict`
   - `signals_to_history(signals) -> dict` (if we keep storing under `briefing["history"]`)

2. Update `backend/core/ingestion_worker.py`
   - Remove dependency on `extractor.gamestate` for leaders.
   - Use `extractor.get_leaders()` (Rust-backed when session active).
   - Normalize into `signals["leaders"]` with `name` populated.

3. Update `backend/core/events.py`
   - When building leader event summaries, prefer `leader["name"]`.

4. Update `backend/core/history.py`
   - Keep `extract_player_leaders_from_gamestate` temporarily (for backward-compat), but stop using it in ingestion.
   - Add a compatibility function to accept precomputed leaders payload.

Acceptance criteria:
- New snapshots contain `history.leaders.leaders[].name` populated with readable names.
- `leader_hired/leader_died/leader_removed` summaries show human names.
- Chronicle no longer emits placeholder leader tokens for new snapshots.

### Milestone D2 (Wars + basic diplomacy)

Objective:
- Stop regex parsing for wars/diplomacy in history enrichment.

Approach:
- Build wars/diplomacy via `extractor.get_wars()` and `extractor.get_diplomacy()` inside the worker.
- Normalize to stable sets for diffs.

### Milestone D3 (Handle duplicate-key “relations_manager.relation” properly)

Current issue:
- Some diplomacy extraction uses regex because parsed dict collapses duplicate keys.

Long-term fix:
- Add a Rust “serve” op to return raw text slice for a specific entry or to expose duplicate-key lists without regex:
  - Option 1: `get_entry_text(section, key)` (returns Clausewitz text for that entry)
  - Option 2: `get_duplicate_blocks(section, key, field)` (returns list of raw blocks)
  - Option 3: implement a Rust-side `get_relations_for_country(country_id)` op

Goal:
- Replace regex on 70MB gamestate with **small, targeted** parsing from raw entry bytes.

### Milestone D4 (Delete legacy gamestate-based history parsing)

Once all signal types are migrated, remove:
- `build_history_enrichment(gamestate=...)` dependencies
- all `extract_*_from_gamestate` functions (or relegate to debug-only)
- the ingestion worker’s `⚠️ Gamestate load` path

---

## Detailed Task Breakdown (for coding agents)

### 1) Add `backend/core/signals.py`

Implement:
- `def build_snapshot_signals(*, extractor: SaveExtractor, briefing: dict[str, Any]) -> dict[str, Any]:`
  - Extract `player_id` from `briefing["meta"]["player_id"]` when available.
  - Populate `leaders` from `extractor.get_leaders()`.
  - Normalize leader objects:
    - `id` (int), `class` (str), `level` (int|None), `name` (str|None), `name_key` (str|None)
  - Add `format_version` and `generated_at`.

Optional helper:
- `def normalize_leaders_payload(leaders: dict) -> dict`

### 2) Update `backend/core/ingestion_worker.py` (t2 only)

Replace the current history enrichment block:
- Remove `gamestate = getattr(extractor, "gamestate", None)` usage.
- Instead:
  - `signals = build_snapshot_signals(extractor=extractor, briefing=briefing)`
  - Attach signals to briefing:
    - Either `briefing["history"] = merge_history(briefing.get("history"), signals_to_history(signals))`
    - Or store separately as `briefing["signals"] = signals` and update downstream readers.

Preference:
- Keep storing under `briefing["history"]` initially to minimize downstream changes.

### 3) Update `backend/core/events.py`

In leader event summaries:
- Use `l.get("name")` first.
- Fallback to `l.get("name_key")`.
- Fallback to `f"#{lid}"`.

Also store `name` in event `data` where helpful for Chronicle prompt quality.

### 4) Backward compatibility strategy

Existing DB snapshots may have only `name_key`. For old snapshots:
- Event summaries remain imperfect historically.
- New snapshots will be correct.

Optional backfill:
- Provide a “recompute signals for last N snapshots” maintenance command later.

---

## Testing Plan

1. Unit-ish tests (Python):
   - Add a small test for `normalize_leaders_payload` that feeds in known Rust-style `leader_data` name structures and verifies `name` is resolved and never `%LEADER_` when variables exist.

2. Integration sanity (existing save corpus):
   - Run tier `t2` ingestion on a known save and assert:
     - `briefing["history"]["leaders"]["leaders"][0]["name"]` exists and does not start with `%`.
     - `compute_events` output leader summaries use that name.

3. Performance check:
   - Ensure ingestion logs no longer show `⚠️  Gamestate load (bottleneck!)` for history.

---

## Risks / Edge Cases

- Some leader names may still be localization keys without variables; use best-effort cleaning (already handled in extractor).
- Multiplayer/modded saves can introduce unexpected name formats; keep fallbacks.
- Ensure signals schema is versioned to avoid breaking older DB content.

---

## Definition of Done

- History enrichment in ingestion worker does **not** require `extractor.gamestate`.
- New snapshots store resolved leader names (`name`) in history/signals.
- Event summaries and Chronicle narratives use resolved names for newly recorded events.
- Duplicate parsing paths are reduced, with a clear migration path for wars/diplomacy and duplicate-key sections via Rust ops.

