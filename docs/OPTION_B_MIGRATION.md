# Option B Migration: Full Pre-compute Architecture

**Date:** 2026-01-15
**Status:** Proposed
**Related:** `benchmark_option_b.py`, `benchmark_option_b_results.json`

---

## Executive Summary

Benchmark testing reveals that **pre-computing all empire data and injecting it directly** (Option B) outperforms the current hybrid approach (slim snapshot + tools) by **1.8x on average**, with far more predictable latency and equal or better response quality.

**Recommendation:** Migrate `/ask` to Option B architecture.

---

## The Problem with Current Approach

The current `ask_simple()` method uses a hybrid strategy:
1. Inject a "slim" snapshot (~2KB) with counts/totals only
2. Provide tools for the model to fetch details if needed
3. Model decides whether to call tools based on the question

**This creates a fundamental issue:** The model cannot distinguish between "data not in snapshot" and "data doesn't exist." When the slim snapshot has partial information (e.g., `leaders: {count: 12, admirals: 3}`), the model often assumes it has enough context and generates answers without calling tools—leading to vague or hallucinated responses.

### Example Failure Mode

```
Slim Snapshot: {leaders: {count: 12, admirals: 3}}

User: "Which admiral should lead my fleet?"

Model thinks: "I see 3 admirals, I can answer this..."
Model says: "Your admirals are well-suited for combat"

PROBLEM: Model doesn't have names/traits/levels
         but doesn't KNOW it's missing them
         so it never calls get_details(['leaders'])
```

---

## Benchmark Results

### Test Configuration

- **Save file:** `test_save.sav` (Corvus v4.2.4, game date 2431.02.18)
- **Model:** `gemini-3-flash-preview`
- **Questions:** 6 queries covering military, leaders, planets, diplomacy, fleets, and strategic assessment

### Performance Comparison

| Metric | Option B (Full Pre-compute) | Current (Slim + Tools) |
|--------|----------------------------|------------------------|
| **Avg Latency** | **11,617ms** | 20,579ms |
| **Min Latency** | **7,569ms** | 10,976ms |
| **Max Latency** | **15,932ms** | 41,612ms |
| **Latency Variance** | Low (predictable) | High (unpredictable) |
| **Tool Calls** | 0 (always) | 1-10 (varies wildly) |
| **Context Size** | 45 KB | ~2 KB + tool responses |

**Option B is 1.8x faster on average.**

### Per-Question Breakdown

| Question | Option B | Current | Winner |
|----------|----------|---------|--------|
| "What is my current military power?" | 7.6s, 0 tools | 19.7s, 1 tool | **Option B** |
| "Which admiral has the best traits?" | 15.9s, 0 tools | 20.3s, 2 tools | **Option B** |
| "Which planet has lowest stability?" | 14.7s, 0 tools | 11.0s, 1 tool | Current (marginal) |
| "Who are my strongest allies?" | **9.7s**, 0 tools | **41.6s**, 10 tools | **Option B** |
| "What is my largest fleet?" | 9.6s, 0 tools | 16.5s, 1 tool | **Option B** |
| "Should I go to war right now?" | 12.1s, 0 tools | 14.5s, 1 tool | **Option B** |

### The Allies Question: A Case Study

This question demonstrates the current approach's worst case:

| Approach | Time | Tool Calls | What Happened |
|----------|------|------------|---------------|
| **Option B** | 9.7s | 0 | Complete answer with ally names and treaties |
| **Current** | 41.6s | 10 | Model spiraled: `search_save_file` × 3, `get_details` × 6, then `finalize_no_tools` |

The slim snapshot didn't have treaty details, so the model kept calling tools trying to find the information. This is the AFC unpredictability problem.

### Response Quality

Both approaches produced accurate, specific answers when they had the data. Key observations:

- **Option B:** Always had complete data, responses referenced specific values (e.g., "125,210.14 military power", "Natacha" as best admiral)
- **Current:** When tools worked correctly, quality was equal. But the slim snapshot sometimes led to less detailed responses.

**Verdict:** Response quality is equal or better with Option B, with the added benefit of no hallucination risk.

---

## Option B Architecture

### Philosophy

**All or nothing.** Either the model has complete data (and no tools), or it has no data (and must use tools). No hybrid middle ground.

We choose "all" because:
- 45KB context is well within Gemini's limits (~10-15K tokens)
- Single API call = predictable latency
- No AFC complexity or tool call variability
- Model cannot hallucinate about missing data

### Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     OPTION B ARCHITECTURE                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  SAVE CHANGE (background, on file watcher trigger)              │
│  ───────────────────────────────────────────────                │
│  1. SaveExtractor parses gamestate                               │
│  2. get_complete_briefing() extracts ALL data (no truncation)   │
│  3. Cache as _complete_briefing (~45-80KB JSON)                 │
│  4. Ready for instant queries                                    │
│                                                                  │
│  USER QUERY (foreground, when /ask is called)                   │
│  ───────────────────────────────────────────────                │
│  1. Inject _complete_briefing JSON into prompt                  │
│  2. Single Gemini API call (tools=None)                         │
│  3. Return response (~10-15 seconds)                            │
│                                                                  │
│                                                                  │
│        Save Watcher                                              │
│             │                                                    │
│             ▼                                                    │
│    ┌─────────────────┐                                          │
│    │ Parse & Extract │                                          │
│    │ get_complete_   │                                          │
│    │   briefing()    │                                          │
│    └────────┬────────┘                                          │
│             │                                                    │
│             ▼                                                    │
│    ┌─────────────────┐         ┌─────────────────┐             │
│    │ _complete_      │         │  User Question  │             │
│    │   briefing      │ ◄───────│     /ask        │             │
│    │  (45KB cache)   │         └─────────────────┘             │
│    └────────┬────────┘                                          │
│             │                                                    │
│             ▼                                                    │
│    ┌─────────────────┐                                          │
│    │  Single Gemini  │                                          │
│    │   API Call      │                                          │
│    │  (no tools)     │                                          │
│    └────────┬────────┘                                          │
│             │                                                    │
│             ▼                                                    │
│         Response                                                 │
│        (~10-15s)                                                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### What "Complete" Data Includes

| Category | Data | Estimated Size |
|----------|------|----------------|
| Meta | Empire name, date, version | 0.5 KB |
| Identity | Ethics, civics, authority, species | 1 KB |
| Situation | Game phase, war status, crisis, fallen empires | 2 KB |
| Military | Power, fleet count, army count | 1 KB |
| Economy | All resources (stockpiles, income, expenses, net) | 3 KB |
| Leaders | **ALL** leaders with names, traits, levels, ages | 4-8 KB |
| Planets | **ALL** planets with stability, districts, buildings | 8-15 KB |
| Diplomacy | **ALL** relations with opinion scores, treaties | 5-10 KB |
| Technology | Completed techs, current research | 8-12 KB |
| Starbases | All starbases with modules, buildings | 3-5 KB |
| Fleets | All fleets with ship counts, power | 2-4 KB |
| Wars | Active wars with participants, exhaustion | 1-2 KB |
| **Total** | | **40-80 KB** |

This is ~10-20K tokens, well within Gemini's context window.

---

## Implementation Plan

### Phase 1: Add `get_complete_briefing()` Method

**File:** `stellaris_save_extractor/briefing.py`

```python
def get_complete_briefing(self) -> dict:
    """Get ALL empire data without truncation for full context injection.

    Unlike get_full_briefing() which truncates lists for tool responses,
    this method returns complete data for direct prompt injection.

    Returns:
        Complete empire data (~40-80KB JSON)
    """
    return {
        'meta': self.get_metadata(),
        'identity': self.get_empire_identity(),
        'situation': self.get_situation(),
        'military': self.get_player_status(),
        'economy': self.get_resources(),
        'leaders': self.get_leaders(),          # Full list, no truncation
        'planets': self.get_planets(),          # Full list, no truncation
        'diplomacy': self.get_diplomacy(),      # Full list, no truncation
        'technology': self.get_technology(),    # Full list, no truncation
        'starbases': self.get_starbases(),      # Full list, no truncation
        'fleets': self.get_fleets(),            # Full list, no truncation
        'wars': self.get_wars(),
        'fallen_empires': self.get_fallen_empires(),
    }
```

**Task:** Review existing extractors for truncation logic and either:
- Add a `limit=None` parameter to disable truncation, or
- Create dedicated no-truncation variants

### Phase 2: Cache on Save Load

**File:** `backend/core/companion.py`

```python
def load_save(self, save_path: str | Path) -> None:
    """Load a save file and pre-compute complete briefing."""
    # ... existing code ...

    # Pre-compute complete briefing for Option B
    self._complete_briefing = self.extractor.get_complete_briefing()
    self._complete_briefing_json = json.dumps(
        self._complete_briefing,
        indent=2,
        default=str
    )
    self._complete_briefing_size = len(self._complete_briefing_json)

def reload_save(self, new_path: Path | None = None) -> bool:
    """Reload save and refresh complete briefing cache."""
    # ... existing code ...

    # Refresh complete briefing
    self._complete_briefing = self.extractor.get_complete_briefing()
    self._complete_briefing_json = json.dumps(
        self._complete_briefing,
        indent=2,
        default=str
    )
```

### Phase 3: New `ask()` Method (Option B)

**File:** `backend/core/companion.py`

```python
def ask(self, question: str) -> tuple[str, float]:
    """Ask a question using full pre-computed data (Option B).

    Injects complete empire data into prompt. No tools.
    Single API call, predictable ~10-15s latency.

    Args:
        question: User's question

    Returns:
        Tuple of (response_text, elapsed_time_seconds)
    """
    if not self.is_loaded:
        return "No save file loaded.", 0.0

    start = time.time()

    prompt = f"""COMPLETE EMPIRE DATA:
```json
{self._complete_briefing_json}
```

QUESTION: {question}

RULES:
- Answer based ONLY on the data above
- Reference specific values (names, numbers, percentages)
- If information is not in the data, say "I don't have that information"
- Maintain your advisor personality
"""

    config = types.GenerateContentConfig(
        system_instruction=self.system_prompt,
        temperature=1.0,
        max_output_tokens=4096,
        # NO TOOLS - everything is in the prompt
    )

    if self._thinking_level != 'dynamic':
        config.thinking_config = types.ThinkingConfig(
            thinking_level=self._thinking_level
        )

    response = self.client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=prompt,
        config=config,
    )

    elapsed = time.time() - start
    return response.text or "No response generated.", elapsed
```

### Phase 4: Update Discord Bot

**File:** `backend/bot/commands/ask.py`

```python
@app_commands.command(name="ask", description="Ask your strategic advisor")
async def ask(interaction: discord.Interaction, question: str):
    await interaction.response.defer(thinking=True)

    # Use Option B method
    response, elapsed = bot.companion.ask(question)

    # Split for Discord's 2000 char limit
    chunks = split_response(response, max_length=1900)
    await interaction.followup.send(chunks[0])
    for chunk in chunks[1:]:
        await interaction.channel.send(chunk)
```

### Phase 5: Keep Escape Hatch for Edge Cases

For questions about specific save file internals not covered by extractors, keep `search_save_file()` available via a separate command:

```python
@app_commands.command(name="search", description="Search raw save file (advanced)")
async def search(interaction: discord.Interaction, query: str):
    # ... existing search functionality ...
```

### Phase 6: Deprecate Old Methods

Mark `ask_simple()` and related hybrid methods as deprecated:

```python
def ask_simple(self, question: str, history_context: str | None = None) -> tuple[str, float]:
    """DEPRECATED: Use ask() instead. Kept for backwards compatibility."""
    import warnings
    warnings.warn("ask_simple() is deprecated, use ask() instead", DeprecationWarning)
    return self.ask(question)
```

---

## Migration Checklist

- [ ] **Phase 1:** Add `get_complete_briefing()` to `stellaris_save_extractor/briefing.py`
- [ ] **Phase 1:** Review extractors for truncation, add `limit=None` support where needed
- [ ] **Phase 2:** Add `_complete_briefing` caching to `Companion.load_save()` and `reload_save()`
- [ ] **Phase 3:** Implement new `Companion.ask()` method (Option B)
- [ ] **Phase 4:** Update `/ask` Discord command to use new method
- [ ] **Phase 5:** Add `/search` command for escape hatch
- [ ] **Phase 6:** Deprecate `ask_simple()`, `chat()` hybrid methods
- [ ] **Testing:** Run benchmark against test save to verify performance
- [ ] **Testing:** Test edge cases (very large empires, many planets/leaders)
- [ ] **Docs:** Update CLAUDE.md with new architecture

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Context too large for huge empires | Low | Medium | Add size check, warn if >100KB |
| Token cost increase | Certain | Low | ~2-5¢ more per query is acceptable |
| Missing obscure data | Low | Low | Keep `/search` escape hatch |
| Stale data mid-session | Medium | Low | Refresh cache on save watcher trigger |

---

## Success Criteria

1. **Latency:** Average /ask response time ≤ 15 seconds (currently ~20s)
2. **Consistency:** Max latency variance ≤ 5 seconds (currently up to 30s variance)
3. **Quality:** No hallucinated responses (model has complete data or says "unknown")
4. **Reliability:** No AFC failures or tool call spirals

---

## References

- Benchmark script: `benchmark_option_b.py`
- Benchmark results: `benchmark_option_b_results.json`
- Current implementation: `backend/core/companion.py`
- Extractor package: `stellaris_save_extractor/`
