# Coding Agent Sprint Plan (GAPS implementation)

This repo is built primarily by LLM coding agents, so the work should be split into **small, shippable vertical slices** with:
- one or two new extractor methods per sprint
- a stable return schema (small + explicit)
- tests against `test_save.sav` for keys/types/basic invariants (avoid brittle “exact match” snapshots)
- optional wiring into aggregators (`get_full_briefing()`) as **summary-only** to keep tool outputs compact

## Why vertical slices (pros/cons)

**Pros**
- Easier reviews and safer merges (small diffs, fewer regressions)
- Fits typical LLM context windows; reduces “god module” drift
- Keeps downstream surfaces stable (Discord bot, `/ask`, future history tracking)

**Cons**
- Slightly more “wiring” work per feature (new method + test + optional briefing hook)
- Some features want shared helpers; avoid premature abstraction, refactor after 2+ methods need the same helper

---

## Sprint 0: Conventions + wiring checklist (one-time)

Definition of done:
- New methods return compact schemas with `count` + summaries (no huge raw lists like pop IDs).
- New domain features go into the right mixin module.
- New mixin modules are wired into `stellaris_save_extractor/extractor.py`.

Coding checklist (every sprint):
1. Implement method in the correct mixin module under `stellaris_save_extractor/`.
2. If it’s a new domain (e.g. internal politics), create a new mixin file and wire it into `stellaris_save_extractor/extractor.py`.
3. Add tests that:
   - run extraction on `test_save.sav`
   - assert schema keys/types
   - assert a couple “sanity invariants” (e.g. count >= 0, lists contain strings)
4. Keep outputs small:
   - aggregate counts
   - include top-N items if needed
   - never return raw IDs lists that can be 10k+

---

## Sprint 1: Progression (high certainty / low complexity)

Goal: answer “where am I in my build path?”
- `get_traditions()` (`stellaris_save_extractor/player.py`)
- `get_ascension_perks()` (`stellaris_save_extractor/player.py`)

User journeys unlocked:
- “Which tradition trees have I adopted/finished?”
- “What perks have I taken; what path am I on (psionic/synth/bio)?”

---

## Sprint 2: Federation + core diplomacy completeness

Goal: answer “what bloc am I in and what are my major treaties?”
- `get_federation_details()` (`stellaris_save_extractor/diplomacy.py`)
- Enhance `get_diplomacy()` for the 6 missing relation types

User journeys unlocked:
- “What federation type/laws/level/cohesion do we have?”
- “Who am I in treaties with (NAP/defensive/commercial/migration/etc.)?”

---

## Sprint 3: Internal politics (new mixin)

Goal: answer “why is stability/happiness trending down?”
- Create `stellaris_save_extractor/politics.py` + wire into `stellaris_save_extractor/extractor.py`
- `get_factions()` in `politics.py` (summary only: support/approval/members_count)

User journeys unlocked:
- “Which factions matter most and are they happy?”
- “Are we at risk of unrest / ethics drift signals?”

Notes:
- Do not return raw pop ID lists; return counts.
- If gestalt, return `is_gestalt: true` and an empty factions list (or a clear message flag).

---

## Sprint 4: Fleet composition (linked data, moderate complexity)

Goal: answer “what is my navy actually made of?”
- `get_fleet_composition()` (`stellaris_save_extractor/military.py`)

User journeys unlocked:
- “Am I over-indexed on corvettes/destroyers?”
- “Do I have enough capitals / titans?”

Notes:
- Unknown `ship_size` values can appear (mods); bucket into `"unknown"` or keep raw string keys safely.

---

## Sprint 5: Galactic Community (summary-first)

Goal: answer “what is happening in galactic politics?”
- `get_galactic_community()` (`stellaris_save_extractor/diplomacy.py`)

User journeys unlocked:
- “Who is on the council?”
- “How many resolutions are proposed/passed; what’s currently being voted on?”

---

## Sprint 6: Subjects / overlord agreements

Goal: answer “how are my vassals set up?”
- `get_subjects()` (`stellaris_save_extractor/diplomacy.py`)

User journeys unlocked:
- “What subject types do I have and what are their terms?”
- “Which agreements are likely to cause loyalty issues?”

---

## Sprint 7: Market + budget deep dive

Goal: answer “why is my economy breaking and what lever do I pull?”
- `get_market()` (`stellaris_save_extractor/economy.py`)
- `get_trade_value()` (`stellaris_save_extractor/economy.py`)
- `get_budget_breakdown()` (`stellaris_save_extractor/economy.py`)

User journeys unlocked:
- “Which resources are overpriced/underpriced right now?”
- “Where is my income/expense actually coming from?”

---

## Sprint 8: Specialty systems (higher variance / nice-to-have)

Goal: fill in “side systems” as needed by players.
- `get_espionage()` (`stellaris_save_extractor/diplomacy.py`)
- `get_archaeology()` (`stellaris_save_extractor/planets.py`)
- `get_relics()` (`stellaris_save_extractor/player.py`)

User journeys unlocked:
- “What operations are running and how long left?”
- “Which dig sites are active/complete?”
- “Which relics do I have; are they on cooldown?”

