# Rust Migration - Build & Test

## Setup

```bash
# Ensure in project root
cd /Users/avani/stellaris-companion

# Verify Rust parser works
./stellaris-parser/target/release/stellaris-parser extract-save test_save.sav --sections meta --output - | jq .schema_version
```

## Capture Baselines

```bash
# Capture baseline for a specific method
python3 scripts/capture_baseline.py get_player_empire

# List all available methods
python3 scripts/capture_baseline.py --list

# Capture all major baselines
for method in get_player_empire get_empire_planets get_military_overview get_diplomatic_relations get_economy_overview; do
    python3 scripts/capture_baseline.py $method
done
```

## Validate Migration

```bash
# Validate a migrated method
python3 scripts/validate_migration.py get_player_empire

# Validate and update baseline if only improvements
python3 scripts/validate_migration.py get_player_empire --update
```

## Test Extraction

```bash
# Quick test of an extraction method
python3 -c "from save_extractor import SaveExtractor; e=SaveExtractor('test_save.sav'); print(e.get_player_empire())"

# Test briefing still works
python3 v2_native_tools.py test_save.sav --briefing 2>&1 | head -30
```

## Verify Rust Usage

```bash
# Check which files use Rust parser
grep -l 'extract_sections\|iter_section_entries' stellaris_save_extractor/*.py

# Count Rust usages per file
grep -c 'extract_sections\|iter_section_entries' stellaris_save_extractor/*.py | grep -v ':0$'

# Count remaining regex per file
grep -c 're\.' stellaris_save_extractor/*.py | sort -t: -k2 -nr
```

## Learnings

(Ralph adds learnings here)
- Always capture baseline BEFORE code changes
- Planet names are in variables block, not key field
- Rust parser doesn't handle duplicate keys (e.g., traits="x" repeated multiple times) - only keeps last value
- Use hybrid approach: Rust for main iteration, regex for fields with duplicate keys (like traits)
- Leader names are under name.full_names.key - may be NAME_X format or %LEADER_2% with variables
- iter_section_entries returns in numeric ID order, not file order
- When comparing by ID (ignoring order), migration is correct even if validation fails on order
- Can manually update baseline by running extraction and saving result
- relations_manager.relation has multiple entries with same key - must use regex for parsing relations
