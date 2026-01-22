# Rust Migration - Build Mode

## Context Loading
Study @specs/rust-migration/overview.md to understand the migration goals.
Study @specs/rust-migration/validation-approach.md to understand the validation process.
Study @specs/rust-migration/fix_plan.json to understand stories and patterns.
Study @specs/rust-migration/AGENT.md to learn how to build and test.
Study @CLAUDE.md for project patterns.
Study @rust_bridge.py to understand the Python-Rust interface.

## Your Task
From @specs/rust-migration/fix_plan.json, choose the SINGLE highest-priority story where `passes: false`.

## Before Implementation (CRITICAL)

1. **Read patterns first** - The `patterns` array in fix_plan.json contains critical learnings
2. **Use python3** - Never use bare `python`, always `python3` or `venv/bin/python`
3. **Correct paths** - Extractors are in `stellaris_save_extractor/`, NOT `backend/extractors/`
4. **Baseline first** - ALWAYS capture baseline BEFORE making any code changes
5. **Understand the data** - Read the target extractor file before migrating
6. **Check existing Rust usage** - Look at already-migrated methods for patterns

## Rust Parser API

The Rust parser provides two main functions via `rust_bridge.py`:

```python
from rust_bridge import extract_sections, iter_section_entries, ParserError

# Extract specific sections as a dict
data = extract_sections(save_path, ["country", "player", "galactic_object"])

# Iterate over entries in a section (for large sections)
for key, value in iter_section_entries(save_path, "country"):
    # key is the country ID, value is the country dict
    pass
```

## Migration Pattern

For each extractor method:

```python
# BEFORE (regex-based)
def get_something(self):
    match = re.search(r'pattern', self.gamestate)
    # fragile regex parsing...

# AFTER (Rust-based with fallback)
def get_something(self):
    try:
        data = extract_sections(self.save_path, ["section_name"])
        # structured data access...
    except ParserError as e:
        logging.warning(f"Rust parser failed: {e}, using fallback")
        return self._get_something_regex()  # Keep old code as fallback

def _get_something_regex(self):
    # Original regex implementation moved here
    match = re.search(r'pattern', self.gamestate)
    ...
```

## Name Resolution Pattern

Planet and species names use `key`/`variables` structure:

```python
# Wrong - gives "NEW_COLONY_1"
name = planet.get("key", "Unknown")

# Right - extracts real name from variables
def resolve_name(name_block):
    if isinstance(name_block, dict):
        variables = name_block.get("variables", [])
        for var in variables:
            if var.get("key") == "1":
                return var.get("value", {}).get("key", name_block.get("key", "Unknown"))
        return name_block.get("key", "Unknown")
    return str(name_block)
```

## Verifying Criteria (CRITICAL - Self-Healing)

Before executing ANY criterion, check if it conflicts with learned patterns:

1. **Check patterns first** - Read the `patterns` array in fix_plan.json
2. **Detect conflicts** - Does the criterion reference a path/command that patterns say is wrong?
3. **Self-heal** - If conflict detected:
   - UPDATE the criterion in fix_plan.json with the correct command
   - Add a pattern documenting the fix
   - Then execute the corrected criterion
4. **Execute** - Run the (possibly corrected) criterion
5. **Verify** - Criterion passes only if the command succeeds

## After Implementation

1. Verify EACH criterion in the story's `criteria` array
2. Run validation: `python3 scripts/validate_migration.py <method_name>`
3. If ALL criteria pass:
   - Set `passes: true` for this story in @specs/rust-migration/fix_plan.json
   - Add any discovered patterns to the `patterns` array
   - Add any new issues to the `discovered` array
   - `git add <specific-files-you-changed> && git commit -m "[type]([scope]): [description]"`
   - NEVER use `git add -A` or `git add .`
4. If ANY criterion fails:
   - Document which criterion failed in the story's `notes` field
   - Do NOT set `passes: true`

## Self-Improvement

- Update @specs/rust-migration/AGENT.md when you learn something new about building/testing
- Add to `patterns` array in fix_plan.json for cross-cutting learnings
- Capture WHY in docstrings and comments

## Rules

- ONE story per iteration only - this is critical
- NO placeholder implementations - FULL implementations only
- ALL criteria must pass before setting `passes: true`
- Use subagents for search operations (up to 50 parallel)
- Use only 1 subagent for build/test (backpressure)
- Search before creating - don't assume not implemented
- When tests unrelated to your work fail, fix them
- ALWAYS capture baseline BEFORE code changes

## Signs (Learned Guardrails)

- NEVER use `git add -A` or `git add .` - commits unrelated files
- Use `python3` not `python` - bare python doesn't exist
- Extractors are in `stellaris_save_extractor/` not `backend/extractors/`
- Always capture baseline BEFORE changing code
- Planet names are in variables block, not key field
- Species names similarly need variable extraction
- extract_sections() returns dict, iter_section_entries() yields (key, value) tuples
- If a criterion path is wrong, UPDATE IT before executing

## Completion

Output exactly this when ALL stories in @specs/rust-migration/fix_plan.json have `passes: true`:
<ralph>PLAN_COMPLETE</ralph>

Output exactly this after completing ONE story successfully:
<ralph>ITERATION_DONE</ralph>
