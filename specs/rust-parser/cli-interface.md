# CLI Interface Specification

## Commands

### extract-save

Extract specific sections from a .sav file as JSON.

```bash
stellaris-parser extract-save <path> \
  --sections <comma-separated> \
  --schema-version <version> \
  --output <file-or-dash>
```

**Arguments:**
- `path`: Path to .sav file (zip containing gamestate + meta)
- `--sections`: Comma-separated section names (e.g., `meta,galaxy,species_db`)
- `--schema-version`: JSON schema version (default: 1)
- `--output`: Output file or `-` for stdout

**Output format:**
```json
{
  "schema_version": 1,
  "tool_version": "0.1.0",
  "game": "stellaris",
  "meta": { ... },
  "galaxy": { ... }
}
```

### iter-save

Stream entries from a large section as JSONL.

```bash
stellaris-parser iter-save <path> \
  --section <name> \
  --schema-version <version> \
  --format jsonl
```

**Arguments:**
- `path`: Path to .sav file
- `--section`: Single section name (e.g., `country`, `ships`, `pops`)
- `--schema-version`: JSON schema version (default: 1)
- `--format`: Output format (`jsonl`)

**Output format (JSONL):**
```jsonl
{"schema_version":1,"tool_version":"0.1.0","game":"stellaris","section":"country","key":"0","value":{...}}
{"key":"1","value":{...}}
{"key":"2","value":{...}}
```

### extract-gamestate (debug only)

Parse an already-extracted gamestate file (not for production).

```bash
stellaris-parser extract-gamestate <path> --sections <names> --output -
```

## Selectors (optional, future enhancement)

Not in initial scope. If needed later:

```bash
# Extract specific keys
stellaris-parser extract-save save.sav --section country --keys 0,1,2

# Extract nested paths
stellaris-parser extract-save save.sav --path meta.date --path galaxy.template
```

For now, use streaming (`iter-save`) for large sections to avoid JSON bottlenecks.

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | File not found / IO error |
| 2 | Parse error |
| 3 | Invalid arguments |

## Error Output (stderr)

```json
{"schema_version":1,"tool_version":"0.1.0","error":"ParseError","message":"...","line":1234,"col":56,"context":"..."}
```

Important: stderr must be bounded (single JSON object) to avoid subprocess deadlock.
