# Validation Approach

## Principle

**Never mark a migration complete without validated output.**

## Validation Process

### Step 1: Capture Baseline

Before changing ANY code, capture current output:

```bash
# Create baselines directory
mkdir -p tests/migration_baselines

# Run extraction with current code, save output
python3 -c "
import json
from save_extractor import SaveExtractor
ext = SaveExtractor('test_save.sav')
result = ext.get_player_empire()  # or whatever method
with open('tests/migration_baselines/get_player_empire.json', 'w') as f:
    json.dump(result, f, indent=2, default=str)
"
```

### Step 2: Migrate Method

Change the extraction to use Rust:

```python
# Before (regex)
def get_player_empire(self):
    match = re.search(r'player=\{[^}]*country=(\d+)', self.gamestate)
    ...

# After (Rust)
def get_player_empire(self):
    try:
        data = extract_sections(self.gamestate_path, ["country", "player"])
        player_id = data.get("player", {}).get("country")
        ...
    except ParserError as e:
        logging.warning(f"Rust parser failed: {e}, using fallback")
        return self._get_player_empire_regex()  # Keep old code as fallback
```

### Step 3: Compare and Validate

```bash
# Run new extraction, compare to baseline
python3 -c "
import json
from save_extractor import SaveExtractor

# Load baseline
with open('tests/migration_baselines/get_player_empire.json') as f:
    baseline = json.load(f)

# Run new extraction
ext = SaveExtractor('test_save.sav')
result = ext.get_player_empire()

# Compare
import deepdiff
diff = deepdiff.DeepDiff(baseline, result, ignore_order=True)
if diff:
    print('MISMATCH:', json.dumps(diff, indent=2, default=str))
    exit(1)
else:
    print('✅ Output matches baseline')
"
```

### Step 4: Handle Improvements

Sometimes the new parser gives BETTER results (e.g., correctly parsing planet names).

In this case:
1. Document the improvement
2. Update the baseline
3. Verify the new output is correct (not just different)

```python
# If new output is BETTER, update baseline and document
# Example: Planet names now show "Earth" instead of "NEW_COLONY_1"
# This is an improvement, not a regression
```

## Validation Criteria Format

Each story in fix_plan.json uses this pattern:

```json
{
  "criteria": [
    "RUN: python3 scripts/capture_baseline.py <method> (baseline saved)",
    "RUN: python3 scripts/validate_migration.py <method> (output matches or documents improvements)",
    "RUN: grep 'extract_sections\\|iter_section_entries' stellaris_save_extractor/<file>.py (Rust calls present)",
    "RUN: grep 'ParserError' stellaris_save_extractor/<file>.py (fallback present)",
    "RUN: python3 -m pytest tests/ -v (all tests pass)"
  ]
}
```

## Test Save Files

Use multiple saves for validation:
- `test_save.sav` - Standard game
- User's actual saves (if available) - Real-world validation

## Known Improvements to Expect

When migrating, these should get BETTER:
1. **Planet names** - Will show actual names instead of `NEW_COLONY_1`
2. **Species names** - Will show actual names instead of localization keys
3. **Duplicate handling** - Will properly accumulate traits, modifiers, etc.
4. **Encoding** - Will handle Windows-1252 characters correctly
