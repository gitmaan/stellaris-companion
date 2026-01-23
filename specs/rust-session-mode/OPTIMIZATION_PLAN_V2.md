# Rust Parser Optimization Plan v2

> **Supersedes:** `OPTIMIZATION_PLAN.md` - The original plan proposed Aho-Corasick on raw bytes, but this has boundary/regex compatibility issues. This revised plan uses the already-parsed JSON tree for structured queries, which is more robust and avoids false positives.

## Design Principles

1. **Keep game logic in Python** - Rust provides fast primitives, Python interprets results
2. **Use the parsed tree** - We already have `HashMap<String, Value>`, traverse it instead of re-scanning bytes
3. **Small payloads** - Return projections, not full objects
4. **Mod-safe** - Don't assume specific schema, just query the tree structure

## Current Bottlenecks (from profiling)

| Bottleneck | Time | Root Cause |
|------------|------|------------|
| Regex on 84MB gamestate | 77s (54%) | 29K `re.search/findall` calls |
| IPC overhead | 14s (10%) | 104K `json.loads`, `value.clone()` per entry |
| Repeated country iteration | ~10s | 15 full passes over country section |

## Implementation Plan

### Phase 1: IPC/Serialization Fixes

**Goal:** Reduce IPC overhead from 14s to ~2s

#### 1a. Remove `value.clone()` in serve.rs

**Current code (expensive):**
```rust
// serve.rs line 185-186
ResponseData::StreamEntry {
    entry: EntryData {
        key: key.clone(),
        value: value.clone(),  // Clones entire Value tree
    },
}
```

**Fix:** Serialize directly without intermediate clone:
```rust
fn write_entry(stdout: &mut impl Write, key: &str, value: &Value) -> io::Result<()> {
    write!(stdout, r#"{{"ok":true,"entry":{{"key":"{}","value":"#, key)?;
    serde_json::to_writer(&mut *stdout, value)?;
    stdout.write_all(b"}}\n")?;
    stdout.flush()
}
```

#### 1b. Add Batched Streaming

**Current:** 1 JSON message per entry (104K messages for large sections)

**New:** Batch entries (100 per message, ~1K messages)

```rust
// Request
{"op": "iter_section", "section": "country", "batch_size": 100}

// Response frames
{"ok": true, "stream": true, "op": "iter_section", "section": "country"}
{"ok": true, "entries": [{"key": "0", "value": {...}}, {"key": "1", "value": {...}}, ...]}
{"ok": true, "entries": [{"key": "100", "value": {...}}, ...]}
{"ok": true, "done": true, "op": "iter_section", "section": "country"}
```

**Python side:** Accept both `entry` (single) and `entries` (batch) for backward compatibility:
```python
def iter_section(self, section: str, batch_size: int = 100):
    # ... send request ...
    while True:
        frame = self._recv()
        if frame.get("done"):
            return
        # Handle both formats
        if "entries" in frame:
            for entry in frame["entries"]:
                yield entry["key"], entry["value"]
        elif "entry" in frame:
            yield frame["entry"]["key"], frame["entry"]["value"]
```

**Expected impact:** 104K decodes → ~1K decodes, ~12s saved

---

### Phase 2: Tree-Based Query Operations

**Goal:** Replace regex scans with structured tree queries

#### 2a. `count_keys` Operation

Traverse the parsed `HashMap<String, Value>` and count occurrences of specific keys.

**Request:**
```json
{"op": "count_keys", "keys": ["prethoryn_system", "contingency_system", "unbidden_portal_system"]}
```

**Response:**
```json
{"ok": true, "counts": {"prethoryn_system": 5, "contingency_system": 0, "unbidden_portal_system": 12}}
```

**Rust implementation:**
```rust
fn handle_count_keys(parsed: &HashMap<String, Value>, keys: &[String]) -> Result<Value> {
    let key_set: HashSet<&str> = keys.iter().map(|s| s.as_str()).collect();
    let mut counts: HashMap<String, usize> = keys.iter().map(|k| (k.clone(), 0)).collect();

    fn traverse(value: &Value, key_set: &HashSet<&str>, counts: &mut HashMap<String, usize>) {
        match value {
            Value::Object(map) => {
                for (k, v) in map {
                    if key_set.contains(k.as_str()) {
                        *counts.get_mut(k).unwrap() += 1;
                    }
                    traverse(v, key_set, counts);
                }
            }
            Value::Array(arr) => {
                for v in arr {
                    traverse(v, key_set, counts);
                }
            }
            _ => {}
        }
    }

    for section in parsed.values() {
        traverse(section, &key_set, &mut counts);
    }

    Ok(json!({"counts": counts}))
}
```

**Python usage (replaces regex):**
```python
# Before (slow - 84MB scan per flag)
for flag in crisis_system_flags:
    total += len(re.findall(rf'\b{flag}=', self.gamestate))

# After (fast - single tree traversal)
result = session.count_keys(crisis_system_flags)
total = sum(result["counts"].values())
```

**Expected impact:** Eliminates ~40s of regex scanning

#### 2b. `contains_tokens` Operation

For simple "does this string appear anywhere" checks, use Aho-Corasick on raw bytes.

**Requires:** Keep `gamestate_bytes: Vec<u8>` in `ParsedSave`

```rust
struct ParsedSave {
    gamestate: HashMap<String, Value>,
    gamestate_bytes: Vec<u8>,  // Keep for token scanning
    meta: Option<HashMap<String, Value>>,
}
```

**Request:**
```json
{"op": "contains_tokens", "tokens": ["killed_dragon", "dragon_killed", "ether_drake_killed"]}
```

**Response:**
```json
{"ok": true, "matches": {"killed_dragon": true, "dragon_killed": false, "ether_drake_killed": false}}
```

**Rust implementation:**
```rust
use aho_corasick::AhoCorasick;

fn handle_contains_tokens(gamestate_bytes: &[u8], tokens: &[String]) -> Result<Value> {
    let ac = AhoCorasick::builder()
        .ascii_case_insensitive(true)
        .build(tokens)?;

    let mut matches: HashMap<String, bool> = tokens.iter().map(|t| (t.clone(), false)).collect();

    for mat in ac.find_iter(gamestate_bytes) {
        matches.insert(tokens[mat.pattern().as_usize()].clone(), true);
    }

    Ok(json!({"matches": matches}))
}
```

**Expected impact:** Eliminates ~30s of leviathan/flag checking

---

### Phase 3: Country Summaries Projection

**Goal:** Replace 15 full country iterations with 1 lightweight pass

#### 3a. `get_country_summaries` Operation

Return only the fields extractors actually need, not full country blobs.

**Request:**
```json
{"op": "get_country_summaries", "fields": ["name", "type", "flag", "ruler"]}
```

**Response:**
```json
{
  "ok": true,
  "countries": [
    {"id": "0", "name": "United Nations of Earth", "type": "default", "flag": {...}, "ruler": 12345},
    {"id": "1", "name": "Commonwealth of Man", "type": "default", "flag": {...}, "ruler": 12346},
    ...
  ]
}
```

**Python usage:**
```python
# Before (15 iterations, full data each time)
for cid, country in iter_section_entries(save_path, "country"):
    name = country.get("name", {}).get("key", "Unknown")
    # ... only using 2-3 fields ...

# After (1 call, minimal data)
summaries = session.get_country_summaries(["name", "type"])
country_names = {c["id"]: c["name"] for c in summaries["countries"]}
```

**Expected impact:** ~10s saved, significant memory reduction

---

## Dependency: Cargo.toml Addition

```toml
[dependencies]
aho-corasick = "1.1"
```

---

## Implementation Order

| Step | Effort | Impact | Dependencies |
|------|--------|--------|--------------|
| 1a. Remove clone | 1 hour | ~3s saved | None |
| 1b. Batch streaming | 2 hours | ~10s saved | None |
| 2a. count_keys | 2 hours | ~40s saved | None |
| 2b. contains_tokens | 1 hour | ~30s saved | Keep raw bytes |
| 3. country_summaries | 2 hours | ~10s saved | None |

**Recommended order:** 1a → 1b → 2a → 2b → 3

---

## Migration Strategy

1. **Add new ops without breaking existing code** - Old paths continue to work
2. **Update hotspots one at a time** - Verify each change improves performance
3. **Remove gamestate access last** - Only after all extractors migrated

**Hotspots to migrate (in order):**
1. `endgame.py`: `get_crisis_status` - uses `re.findall` for flag counting → `count_keys`
2. `leviathans.py`: `_check_leviathan_defeated` - uses `re.search` → `contains_tokens`
3. `endgame.py`: `get_lgate_status` - uses `re.search` → `contains_tokens`
4. `base.py`: `_get_country_names` - iterates country → `get_country_summaries`
5. `diplomacy.py`: `get_fallen_empires` - iterates country → `get_country_summaries`

---

## Expected Final Performance

| Stage | Briefing Time |
|-------|---------------|
| Current (session mode) | 24-45s |
| After Phase 1 | 15-25s |
| After Phase 2 | 5-10s |
| After Phase 3 | 3-7s |

**Target:** <10s briefing generation (vs 259s original = 25x+ speedup)

---

## Success Metrics

- [ ] Zero `value.clone()` in streaming hot path
- [ ] Batch size ≥100 entries per IPC message
- [ ] Zero `re.search/findall(..., self.gamestate)` in hot path
- [ ] Single country iteration per briefing (via summaries)
- [ ] Briefing time <10s on M4 MacBook

---

## Files to Modify

**Rust:**
- `stellaris-parser/src/commands/serve.rs` - Add ops, fix cloning, add batching
- `stellaris-parser/Cargo.toml` - Add aho-corasick

**Python:**
- `rust_bridge.py` - Add new op methods, handle batched responses
- `stellaris_save_extractor/endgame.py` - Use count_keys
- `stellaris_save_extractor/leviathans.py` - Use contains_tokens
- `stellaris_save_extractor/base.py` - Use country_summaries
- `stellaris_save_extractor/diplomacy.py` - Use country_summaries
