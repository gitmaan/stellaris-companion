# Stellaris Companion — Stress Test Plan (Tiers + Scenarios)

**Goal:** Validate that the app stays fast, stable, and cross-version/mod tolerant across real Stellaris play scenarios (small early saves through 70MB late-game), while keeping LLM context and costs under control.

This plan stress-tests the current **Tier 0/1/2** architecture and the proposed **Tier 2.5/3** extension:
- **T0**: meta-only (zip `meta`)
- **T1**: fast status snapshot (worker, minimal extraction)
- **T2**: full precompute briefing (worker, persisted snapshot JSON)
- **T2.5 (proposed)**: tool-calls over cached T2 JSON (no re-parse)
- **T3 (proposed)**: tool-calls that parse the save on demand (deep/rare queries)

---

## Why this matters (what Stellaris saves do in practice)

**Stress dimensions**
- **Save size & density:** late game routinely 50–100MB with huge lists (pops, planets, ships, relations).
- **Write pattern:** autosaves write in bursts; the file can be unreadable/partial mid-write.
- **Version/DLC drift:** keys move or alternate (`migration_treaty` vs `migration_pact`, Overlord `agreements`, etc.).
- **Mods:** add new resources/sections; strict schema assumptions break.
- **Question shapes:** broad advice vs pinpoint lookup vs time-series (“what changed?”).

---

## Tier responsibilities (expected behavior)

### Tier 0 (T0) — meta-only
- **Must:** be near-instant; never parse full gamestate.
- **Provides:** empire name/date/version, file size, modified time, save path.
- **Used for:** “save detected” UI and scheduling downstream work.

### Tier 1 (T1) — fast status snapshot
- **Must:** stay fast even on huge saves; bounded work; low memory.
- **Provides:** core heartbeat metrics for UI (date, empire name, military power, a few resource nets, colonies/pops, active wars list).
- **Used for:** UI status display and basic answers if T2 not ready.

### Tier 2 (T2) — full precompute briefing
- **Must:** run in a cancellable worker; may take longer; should be resilient to churn.
- **Provides:** a comprehensive JSON briefing persisted into SQLite snapshots for history/recaps/diffs.
- **Important:** the *injected* context should remain **slim** even if the persisted JSON is large.

### Tier 2.5 (proposed) — cached retrieval tools (no re-parse)
- **Must:** keep LLM prompts small; return bounded slices.
- **Provides:** “query” access to cached T2 briefing (in-memory or SQLite), e.g.:
  - `get_cached_section("diplomacy")`
  - `get_cached_subject_contract(subject_id)`
  - `search_cached("trade_deal")`
- **Used for:** deep answers without re-parsing the save and without dumping massive JSON into the prompt.

### Tier 3 (proposed) — on-demand save parsing tools
- **Must:** be rare, bounded, and time-limited; safe under mod drift.
- **Provides:** deep/volatile data not cached in T2 (queues, mod-specific sections, object-level drill downs).
- **Used for:** “show me the exact X” where caching is not worth it.

---

## Scenario matrix (Stellaris-player reality check)

| Scenario | Common player questions | Primary risk | Tier strategy |
|---|---|---|---|
| Early game (2200–2230) | expansion picks, early economy, scouting | T2 overkill | T1 first; defer T2 until needed |
| Midgame diplomacy (Fed + GC) | votes, laws, envoys, pacts | huge lists in prompt | T2 summaries + T2.5 detail fetch |
| Overlord/vassal web | contracts, specialization, taxes | nested agreements, variability | T2 compact per-subject rows; T2.5 full contract |
| Crisis / multi-war / WiH | war priorities, fleet allocation | large combined datasets | T2 bounded wars; T3 only for rare deep reads |
| Late game 70MB+ | bottlenecks, stability, planet optimization | T2 churn + prompt bloat | slim injected summary; rely on T2.5 |
| Gestalt empires | drones, deviancy, special civics | irrelevant-human fields | T2 flags; guard tool choices |
| Megacorp | trade, branch offices, pacts value | needs budget/trade breakdown | T2 economy levers + T2.5 drilldowns |
| Modded (Gigas/ACOT/etc.) | mod resources/megastructures | unknown keys/sections | core tiers still work; T3 search tools for mods |

---

## Budgets (targets to keep UX + costs sane)

These are practical targets; adjust after baseline measurements.

**Latency**
- **T0:** < 200ms
- **T1:** < 3s typical, < 8s worst-case (very large saves)
- **T2:** “eventual consistency” — can be tens of seconds on 70MB saves, but must be cancellable and should complete once the save stream is idle.

**Prompt size**
- **Injected summary (for chat):** keep intentionally small (a “strategy summary”, not the entire world state).
- **T2.5 responses:** cap returned data (top-N lists, specific entity only) to avoid ballooning context.

**Resource usage**
- Worker-based precompute must avoid leaking processes/threads on rapid save churn.
- SQLite snapshot retention must keep disk bounded (existing pruning policy should be validated).

---

## What to test (automation-ready checklist)

### A) Save stream & churn
- Rapid autosaves (e.g., 10 saves in 30s): verify only the latest save “wins”.
- Partial writes: verify stable-file detection prevents parsing corrupted/partial zip.
- Cancellation: verify worker cancellation actually stops CPU/RAM use and doesn’t leak zombie processes.

### B) Scale by save size
- Small (early), medium (mid), huge (late 70MB+): measure:
  - T0 time, T1 time, T2 time
  - peak memory (RSS) during T2
  - resulting `briefing_json` byte size
  - cancellation count under churn

### C) Content coverage & correctness
- Federation + GC: current vote/laws present; no hallucinated “missing” structures.
- Subjects: contracts extracted and summarized correctly.
- Treaties: migration/commercial/defensive/non-aggression/research agreements consistent and symmetric where expected.
- Gestalt: faction extraction disabled and messaging correct.

### D) Mod tolerance
- Unknown top-level blocks present: extractor should degrade gracefully (warnings + partial results), not crash.
- Provide a fallback “search” mechanism in T3 for mod-specific questions.

---

## Proposed harness (implementation outline)

**Inputs**
- A folder of `.sav` files representing scenario categories (early/mid/late, gestalt, megacorp, modded).
- Optional “save stream replay” script that touches/copies saves into a watched folder to mimic autosaves.

**Runner behavior**
- For each save:
  1. Run T0 extraction and record timing.
  2. Run T1 worker and record timing + output sanity.
  3. Run T2 worker and record timing + JSON size + peak RSS.
  4. (Future) Run T2.5 queries against the cached T2 result and record response sizes.
  5. (Future) Run a small set of T3 “deep” tools on demand and measure bounded performance.

**Outputs**
- A markdown report with per-save metrics and pass/fail against budgets.
- A JSON artifact for trend tracking across commits.

---

## What NOT to do (anti-patterns)
- Don’t inject the entire T2 JSON into every model call “because context is big”.
- Don’t return unbounded lists from tools (resolutions, pops, relations, etc.).
- Don’t couple extraction to exact line numbers or rigid schemas; prefer “best-effort” parsing with safe fallbacks.

---

## Next steps (recommended order)

1. Establish baseline metrics for T0/T1/T2 across a representative save set.
2. Define a slim “strategy summary” payload for prompt injection (separate from persisted full JSON).
3. Add Tier 2.5 cached retrieval tools (query cached T2 JSON/SQLite).
4. Add minimal Tier 3 deep tools for uncached, high-value queries (queues, targeted lookups, mod search).
5. Add CI hooks to run the harness on a small public/non-sensitive fixture set (or synthetic micro-saves), and run full suite locally.

