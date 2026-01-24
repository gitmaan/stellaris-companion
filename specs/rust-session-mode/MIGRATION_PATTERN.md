# Regex-to-Rust Migration Pattern

> Established from manual migration of `_analyze_player_fleets` (2026-01-24)

## The Pattern

Every regex-based function follows this migration pattern:

```
1. BASELINE    → Run original, capture output + timing
2. ANALYZE     → Understand data structure via Rust session
3. IMPLEMENT   → Write _function_rust() using iter_section/dict access
4. COMPARE     → Verify output matches baseline exactly
5. BENCHMARK   → Measure speedup
6. DISPATCH    → Update original to call Rust version when session active
7. FALLBACK    → Keep _function_regex() for non-session use
```

## Code Structure

```python
def some_function(self, args) -> dict:
    """Docstring unchanged."""
    # Dispatch to Rust version when session is active
    session = _get_active_session()
    if session:
        return self._some_function_rust(args)
    return self._some_function_regex(args)

def _some_function_rust(self, args) -> dict:
    """Rust-optimized version using iter_section."""
    session = _get_active_session()
    if not session:
        return self._some_function_regex(args)

    # Use iter_section + dict access
    for entry_id, entry in session.iter_section('section_name'):
        if not isinstance(entry, dict):
            continue
        # Direct dict access - no regex, no size limits
        value = entry.get('field_name')

    return result

def _some_function_regex(self, args) -> dict:
    """Original regex implementation - fallback."""
    # Original code moved here unchanged
```

## Key Transformations

### 1. Section Iteration

```python
# BEFORE (regex)
for m in re.finditer(r'\n\t(\d+)=\n\t\{', section_content):
    entry_id = m.group(1)
    # Extract block with size limits
    block = section_content[m.start():m.start() + 100000]

# AFTER (Rust)
for entry_id, entry in session.iter_section('section_name'):
    if not isinstance(entry, dict):
        continue
    # Complete data, no limits
```

### 2. Field Extraction

```python
# BEFORE (regex with truncation risk)
match = re.search(r'field_name\s*=\s*([\d.]+)', block[:50000])
value = float(match.group(1)) if match else 0.0

# AFTER (dict access)
value = entry.get('field_name')
value = float(value) if value is not None else 0.0
```

### 3. Nested Structures

```python
# BEFORE (regex fails on nesting)
match = re.search(r'name=\s*\{([^}]+)\}', block)  # BROKEN: [^}] stops at first }

# AFTER (handles nesting correctly)
name_data = entry.get('name', {})
if isinstance(name_data, dict):
    key = name_data.get('key')
    variables = name_data.get('variables', [])
```

### 4. Boolean Fields

```python
# BEFORE
is_station = re.search(r'\n\t\tstation=yes', block) is not None

# AFTER
is_station = entry.get('station') == 'yes'
```

### 5. List Fields

```python
# BEFORE (regex can miss entries)
ships_match = re.search(r'ships=\s*\{([^}]+)\}', block)
ship_count = len(ships_match.group(1).split()) if ships_match else 0

# AFTER (complete list)
ships = entry.get('ships', [])
ship_count = len(ships) if isinstance(ships, (list, dict)) else 0
```

## Required Import

Add to file imports:
```python
try:
    from rust_bridge import extract_sections, iter_section_entries, ParserError, _get_active_session
    RUST_BRIDGE_AVAILABLE = True
except ImportError:
    RUST_BRIDGE_AVAILABLE = False
    ParserError = Exception
    _get_active_session = lambda: None
```

## Testing Checklist

- [ ] Run baseline, save output to `/tmp/baseline.json`
- [ ] Run Rust version, save output to `/tmp/rust.json`
- [ ] Compare all numeric fields (exact match or < 0.01 diff)
- [ ] Compare all string fields (exact match)
- [ ] Compare list lengths and contents
- [ ] Benchmark: Rust should be 3-10x faster
- [ ] Full briefing time should decrease

## Common Pitfalls

1. **entry might be string "none"** - Always check `isinstance(entry, dict)`
2. **Missing fields** - Use `.get()` with defaults, never direct `[]` access
3. **Type variations** - Fields can be str, int, float, dict, or list
4. **ID types** - Entry IDs from iter_section are strings, convert if needed

## Results from Manual Migration

### _analyze_player_fleets

| Metric | Regex | Rust | Improvement |
|--------|-------|------|-------------|
| Time | 0.375s | 0.055s | 6.8x faster |
| Data accuracy | 100KB limit | Complete | No truncation |
| Code clarity | Complex regex | Dict access | Much cleaner |

### Full Briefing Impact

| Stage | Time | Total Speedup |
|-------|------|---------------|
| Original | 259s | baseline |
| + Session mode | 7.76s | 33x |
| + FE optimization | 5.93s | 44x |
| + Player cache | 4.64s | 56x |
| + Fleet analysis | 3.87s | 67x |
