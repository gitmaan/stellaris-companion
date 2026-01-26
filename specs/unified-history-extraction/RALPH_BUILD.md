## Context Loading
Study @docs/OPTION_D_UNIFIED_HISTORY_EXTRACTION.md for the full architecture and schema.
Study @specs/unified-history-extraction/fix_plan.json to understand stories and patterns.
Study @stellaris_save_extractor/leaders.py for `_extract_leader_name_rust()` - the reference implementation.
Study @backend/core/history.py for current extraction (to understand what signals must replace).
Study @backend/core/ingestion_worker.py for integration point.
Study @backend/core/events.py for where resolved names are used.
Study @CLAUDE.md for project patterns.

## Goals
1. **Single source of truth** - All extraction via SaveExtractor, not duplicate regex
2. **No gamestate for history** - Signals built in worker where Rust session is active
3. **Resolved names** - Chronicle sees "Admiral Chen" not "%LEADER_2%"
4. **Backward compat** - Old snapshots still work (may have unresolved names)

## Your Task
From @specs/unified-history-extraction/fix_plan.json, choose the SINGLE highest-priority story where `passes: false`.

## Before Implementation (CRITICAL)
1. Read the `patterns` array in fix_plan.json - these are learnings from previous iterations
2. Search for EXISTING code that does similar things (grep for patterns)
3. Reference `_extract_leader_name_rust()` in leaders.py for name resolution logic
4. Follow existing patterns EXACTLY

## Implementation Pattern

### For UHE-001/002 (signals.py creation):
```python
"""
SnapshotSignals builder for unified history extraction.

Built once per snapshot in ingestion worker (where Rust session is active).
Provides normalized, resolved data for events and chronicle.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any

SIGNALS_FORMAT_VERSION = 1

def build_snapshot_signals(*, extractor, briefing: dict[str, Any]) -> dict[str, Any]:
    """Build normalized signals payload from SaveExtractor.

    Args:
        extractor: SaveExtractor instance (with active Rust session for best results)
        briefing: Complete briefing dict from extractor

    Returns:
        SnapshotSignals dict with format_version, leaders, wars, diplomacy
    """
    signals = {
        "format_version": SIGNALS_FORMAT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "player_id": briefing.get("meta", {}).get("player_id"),
    }

    # Add leader signals with resolved names
    signals["leaders"] = _extract_leader_signals(extractor)

    return signals

def _extract_leader_signals(extractor) -> dict[str, Any]:
    """Extract normalized leader data with resolved names."""
    raw = extractor.get_leaders()
    # ... normalize and ensure 'name' field is populated
```

### For UHE-003 (date extraction):
Add to `_get_leaders_rust()`:
```python
# Extract dates (may be null)
death_date = leader_data.get("death_date")
if death_date:
    leader_info['death_date'] = death_date

date_added = leader_data.get("date_added")
if date_added:
    leader_info['date_added'] = date_added

recruitment_date = leader_data.get("pre_ruler_date") or leader_data.get("date")
if recruitment_date:
    leader_info['recruitment_date'] = recruitment_date
```

### For UHE-005 (events.py name resolution):
```python
def _get_leader_name(leader: dict) -> str:
    """Get best available leader name."""
    if leader.get('name'):
        return leader['name']
    if leader.get('name_key'):
        key = leader['name_key']
        # Clean up common patterns
        if '_CHR_' in key:
            return key.split('_CHR_')[-1]
        if key.startswith('NAME_'):
            return key[5:].replace('_', ' ')
        if not key.startswith('%'):
            return key
    return f"#{leader.get('id', 'unknown')}"
```

## Key Reference: Name Resolution (from leaders.py)

```python
def _extract_leader_name_rust(self, leader_data: dict) -> str | None:
    name_block = leader_data.get("name")
    if not isinstance(name_block, dict):
        return None

    full_names = name_block.get("full_names")
    if not isinstance(full_names, dict):
        return None

    key = full_names.get("key", "")

    # Pattern 1: _CHR_ suffix (e.g., "HUMAN1_CHR_Miriam")
    if "_CHR_" in key:
        return key.split("_CHR_")[-1]

    # Pattern 2: NAME_ prefix (e.g., "NAME_Skrand_Sharpbeak")
    if key.startswith("NAME_"):
        return key[5:].replace("_", " ")

    # Pattern 3: Template with variables (e.g., "%LEADER_2%")
    variables = full_names.get("variables", [])
    if isinstance(variables, list):
        for var in variables:
            if isinstance(var, dict) and var.get("key") == "1":
                value = var.get("value", {})
                if isinstance(value, dict):
                    val_key = value.get("key", "")
                    if "_CHR_" in val_key:
                        return val_key.split("_CHR_")[-1]

    return None
```

## Verifying Criteria

Before marking a story as passing:
1. Run EACH criterion command
2. If criterion fails, fix the implementation
3. If criterion is wrong, update it and add a pattern explaining why
4. Only set `passes: true` when ALL criteria pass

## After Implementation
1. Verify EACH criterion passes
2. Run: `python3 -c "from backend.core.signals import build_snapshot_signals; print('OK')"` (basic import test)
3. If ALL criteria pass:
   - Set `passes: true` in fix_plan.json
   - Add any new patterns learned to `patterns` array
   - `git add <specific-files> && git commit -m "[type]([scope]): [description]"`
4. If ANY criterion fails:
   - Document issue in story's `notes` field
   - Do NOT set `passes: true`

## Rules
- ONE story per iteration only
- NO placeholder implementations - FULL implementations only
- ALL criteria must pass before setting `passes: true`
- Use subagents for search operations
- NEVER use `git add -A` or `git add .`
- Test with test_save.sav in project root

## Signs (Learned Guardrails)
- Cargo is at ~/.cargo/bin/cargo, not in PATH
- Use python3, not bare python
- Entry from iter_section might be string "none" - check isinstance(entry, dict)
- Use .get() with defaults, never direct [] access
- Test save is at test_save.sav in project root
- Reference: `_extract_leader_name_rust()` in leaders.py for name patterns

## Phase 2 Stories (UHE-011+)

These stories expand signals coverage and improve Chronicle quality further.

### Empire Names (UHE-011, UHE-012)
get_diplomacy() already returns `{id: X, name: "Empire Name"}` for allies/rivals.
- UHE-011: Capture these names in signals as `diplomacy.empire_names: {country_id: name}`
- UHE-012: Add `_get_empire_name(cid, empire_names)` helper to events.py

### Expanded Signals (UHE-013 through UHE-017)
These methods are ALREADY Rust-backed in SaveExtractor. Just call them:
- `extractor.get_technology()` → signals["technology"]
- `extractor.get_megastructures()` → signals["megastructures"]
- `extractor.get_crisis_status()` → signals["crisis"]
- `extractor.get_fallen_empires()` → signals["fallen_empires"]

Normalize output to match what history.py event detection expects.

### Phase 3 Stories (UHE-020+) - Final Cleanup

These complete the migration and clean up dead code.

#### Galaxy Settings (UHE-020)
Extract from briefing metadata or use extract_sections(['galaxy']):
```python
def _extract_galaxy_settings_signals(extractor: "SaveExtractor", briefing: dict) -> dict:
    meta = briefing.get("meta", {})
    return {
        "mid_game_start": meta.get("mid_game_start"),
        "end_game_start": meta.get("end_game_start"),
        "victory_year": meta.get("victory_year"),
        "difficulty": meta.get("difficulty"),
        "ironman": meta.get("ironman"),
    }
```

#### Systems Count (UHE-021)
Use get_starbases() which is already Rust-backed:
```python
def _extract_systems_signals(extractor: "SaveExtractor") -> dict:
    starbases = extractor.get_starbases()
    count = len(starbases.get("starbases", []))
    return {"count": count}
```

#### War Name Resolution (UHE-022)
Resolve placeholders like %ADJ%, %LEADER%, %TARGET%:
```python
def _resolve_war_name(name: str, empire_adjectives: dict, leader_names: dict) -> str:
    if "%ADJ%" in name:
        # Look up attacker/defender adjective
        name = name.replace("%ADJ%", adjective)
    if "%LEADER%" in name:
        name = name.replace("%LEADER%", leader_name)
    return name
```
Empire adjectives come from get_player_status()["adjective"] or country entries.

#### Delete Old Functions (UHE-023)
Remove these from history.py:
- extract_player_leaders_from_gamestate
- extract_player_diplomacy_from_gamestate
- extract_player_techs_from_gamestate
- extract_player_policies_from_gamestate
- extract_player_edicts_from_gamestate
- extract_megastructures_from_gamestate
- extract_crisis_from_gamestate
- extract_fallen_empires_from_gamestate
- extract_player_wars_from_gamestate

Keep extract_campaign_id_from_gamestate (still used for campaign identification).

### Example: Adding technology signals
```python
def _extract_technology_signals(extractor: "SaveExtractor") -> dict[str, Any]:
    """Extract technology data for history diffing."""
    raw = extractor.get_technology()
    if not isinstance(raw, dict):
        return {"researched": [], "in_progress": []}

    return {
        "researched": raw.get("researched", []),
        "in_progress": [t.get("id") for t in raw.get("in_progress", []) if isinstance(t, dict)],
    }
```

## Completion
Output exactly this when ALL stories have `passes: true`:
<ralph>PLAN_COMPLETE</ralph>

Output exactly this after completing ONE story successfully:
<ralph>ITERATION_DONE</ralph>
