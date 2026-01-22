# Rust Parser Migration

## Goal

Migrate all extraction methods from regex-based parsing to the Rust parser, with validation against actual save data.

## Approach: Test-Driven Migration

For each extractor module:
1. **Capture baseline** - Run current regex extraction, save output as JSON
2. **Migrate method** - Switch to Rust parser with `extract_sections()` or `iter_section_entries()`
3. **Compare outputs** - New output must match baseline (or be explicitly better)
4. **Fix discrepancies** - Iterate until values match
5. **Keep fallback** - Regex fallback remains for edge cases

## Validation Script

Each migration creates a validation test:
```python
def test_migration_matches_baseline():
    old_result = load_baseline("method_name.json")
    new_result = run_new_extraction()
    assert new_result == old_result, f"Mismatch: {diff(old_result, new_result)}"
```

## Files to Migrate (by regex count)

| File | Regex Calls | Priority |
|------|-------------|----------|
| diplomacy.py | 69 | 1 |
| base.py | 42 | 1 (partially done) |
| planets.py | 36 | 1 |
| military.py | 36 | 1 |
| player.py | 32 | 1 |
| economy.py | 29 | 2 |
| validation.py | 17 | 3 |
| technology.py | 14 | 2 |
| endgame.py | 14 | 3 |
| species.py | 11 | 2 |
| leaders.py | 11 | 2 |
| armies.py | 11 | 2 |
| projects.py | 10 | 3 |
| politics.py | 9 | 3 |
| leviathans.py | 6 | 3 |

## Key Sections in Save Files

| Section | Used By |
|---------|---------|
| country | player, diplomacy, economy |
| planets | planets, economy |
| galactic_object | planets, military |
| species_db | species, player |
| fleet | military |
| ship | military |
| leaders | leaders |
| war | diplomacy, military |
| federation | diplomacy |
| army | armies |

## Success Criteria

- All extraction methods use Rust parser
- Each method has validated output matching baseline
- Regex fallback exists for error cases
- All existing tests pass
- Briefing produces same results
