# SaveExtractor Refactor Plan (LLM-Agent Friendly)

**Status:** Proposed (no code changes yet)  
**Scope:** Refactor `save_extractor.py` for maintainability + LLM context windows  
**Non-scope:** Adding new extractors from `GAPS_ANALYSIS.md` (separate sprint)

---

## Why refactor?

`save_extractor.py` is large (~3k LOC) and mixes:
- Save I/O (unzipping `.sav`, reading `gamestate` / `meta`)
- Low-level Clausewitz parsing (brace matching, section extraction)
- High-level Stellaris domain extractors (“tools” like fleets/planets/resources)

In an “LLM coding agents only” workflow, this increases risk because:
- Agents can’t reliably keep the entire file in context (partial views lead to incorrect edits).
- Adding more extractors (see `GAPS_ANALYSIS.md`) will push size further.
- It’s hard to make a small, safe change without re-reading lots of unrelated code.

---

## Goals

1. **Keep public API stable**: `from save_extractor import SaveExtractor` continues to work.
2. **Reduce per-file size**: split by responsibility so each module fits typical context windows.
3. **Make changes safer**: isolate parsing utilities from domain logic.
4. **Enable future growth**: new extractors can be added in dedicated modules without bloating a single file.
5. **Keep runtime acceptable**: avoid accidental O(N) scans repeated across tools.

---

## Non-goals (this sprint)

- Implementing the gaps in `GAPS_ANALYSIS.md` (factions, traditions, galactic community, etc.).
- Rewriting the parser into a full Clausewitz AST or changing extraction semantics.
- Changing Discord bot behavior or Phase 3 history/event logic.

---

## Key constraint: Avoid import ambiguity

Today we have a top-level module `save_extractor.py`. Creating a folder named `save_extractor/`
in the same directory can introduce ambiguous imports (`import save_extractor` could resolve to
either the module or the package depending on tooling/packaging).

**Recommendation:** create a new package with a different name (e.g. `stellaris_save_extractor/`)
and keep `save_extractor.py` as a thin compatibility shim.

---

## Target architecture

### 1) Compatibility shim (keeps imports stable)

`save_extractor.py` becomes a small file that re-exports the implementation:
- `from stellaris_save_extractor.extractor import SaveExtractor`

### 2) New package with cohesive modules

Create `stellaris_save_extractor/`:
- `extractor.py` — `SaveExtractor` class (thin orchestration + shared state)
- `io.py` — `.sav` unzip + read `gamestate`/`meta`
- `clausewitz.py` — section/bounds/braces helpers, nested block extraction
- `cache.py` — section cache + memoization helpers (optional; can be inside `extractor.py`)
- Domain modules (pure extraction):
  - `empire.py` — player id, identity, status
  - `economy.py` — resources, budget-ish primitives used elsewhere
  - `military.py` — fleets/starbases/war basics
  - `planets.py` — planets, pops, buildings/districts helpers
  - `diplomacy.py` — relations/treaties/federation hooks (current scope only)
  - `technology.py` — tech/research extraction
  - `search.py` — generic search helpers exposed as tool(s)
  - `briefing.py` — `get_full_briefing`, `get_slim_briefing`, `get_details`

Design rule: domain modules should be “dumb” functions that accept `gamestate` text (and
optionally a small helper object) and return dicts/lists. Avoid circular dependencies.

---

## Migration plan (safe, incremental)

### Step 0 — Baseline and guardrails
- Record a baseline run on `test_save.sav` (existing test scripts) and keep outputs for comparison.
- Add a tiny smoke test (if there’s an existing test pattern) to ensure imports and 1–2 methods work.

### Step 1 — Move without changing behavior (mechanical refactor)
- Create `stellaris_save_extractor/` and copy current implementation into it (initially as one file).
- Replace the contents of `save_extractor.py` with the compatibility shim.
- Run the existing CLI/bot entry points that import `SaveExtractor`.

Acceptance criteria:
- No call sites change.
- Output is byte-for-byte identical for a small set of methods on `test_save.sav` (or equivalent).

### Step 2 — Split by responsibility (still no behavior change)
- Extract I/O helpers into `io.py`.
- Extract clausewitz parsing helpers into `clausewitz.py`.
- Keep `SaveExtractor` as the public object storing `gamestate`, `meta`, and caches.

Acceptance criteria:
- No semantic changes; only imports/module boundaries change.

### Step 3 — Split domain modules (minimize cross-cutting edits)
Move one domain at a time (e.g. `economy.py`, then `technology.py`, then `planets.py`), each as:
- Copy method body into `domain.py` as a function.
- Make the `SaveExtractor.get_x()` wrapper call the function.

Acceptance criteria:
- Each move is a small diff; easy to review and revert.

### Step 4 — Optional cleanup pass (small improvements)
Only after the split is stable:
- Replace “fixed-size chunk slicing” with shared helpers + documented constants.
- Normalize regex patterns and make them easier to audit.
- Add optional profiling hooks (off by default) for “hot” extractors.

---

## Testing/validation strategy

Minimum:
- Import test: `from save_extractor import SaveExtractor`.
- Smoke: call `get_metadata()` and one heavier method (e.g. `get_player_status()`).
- Compare key outputs before/after for `test_save.sav` for a small set of methods.

Nice-to-have:
- Add a golden JSON snapshot for `get_slim_briefing()` and/or `get_full_briefing()` (stable fields only).

---

## Performance considerations (don’t regress)

- Keep `gamestate` as a single in-memory string (current approach).
- Preserve and centralize `_section_cache` behavior.
- Avoid repeated full-file `re.search` for the same section across multiple tools:
  - Make “top-level section bounds” cacheable.
  - Consider a single pass index for common anchors (`^country=`, `^ships=`, etc.) if needed later.
- Keep per-tool scan limits explicit and documented (why 1MB vs 5MB vs 80MB).

---

## LLM-agent ergonomics guidelines (practical)

- Keep each module roughly **≤ 300–500 lines**.
- Put “how to modify safely” notes at the top of each module (inputs, assumptions, hotspots).
- Prefer **pure functions** for extraction and keep state in `SaveExtractor` only (cache + gamestate/meta).
- Avoid metaprogramming/dynamic method injection; keep it grep-able.

---

## Relationship to future work (`GAPS_ANALYSIS.md`)

This refactor makes it easier to implement the `GAPS_ANALYSIS.md` backlog later:
- New extractors can land in `factions.py`, `federation.py`, `galactic_community.py`, etc.
- Phase 3 delta/event logic can consume the new extracted fields without growing a monolithic file.

That work should be scheduled as its own sprint after the refactor stabilizes.

