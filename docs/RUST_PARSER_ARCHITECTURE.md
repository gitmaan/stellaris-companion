# Rust Parser Architecture (`stellaris-parser`)

This document describes the `stellaris-parser` Rust binary interface used by the Python backend (`stellaris_companion.rust_bridge`) to parse Stellaris `.sav` files.

## Overview

`stellaris-parser` provides two ways to query a save:

1. **One-shot CLI commands** (parse the save each time)
2. **Session mode** via `serve` (parse once, then answer multiple queries over stdin/stdout)

The Python backend primarily uses **session mode** to avoid re-parsing overhead.

## CLI commands

The CLI is implemented in `stellaris-parser/src/main.rs` and supports:

- `extract-save <path> --sections <comma,separated> [--schema-version 1] [--output -]`
- `iter-save <path> --section <name> [--schema-version 1] [--format jsonl]`
- `extract-gamestate <path> --sections <comma,separated> [--schema-version 1] [--output -]` (debug)
- `serve --path <save.sav>` (session mode)

### Exit codes (CLI)

The binary uses consistent exit codes:

- `1` = file not found
- `2` = parse error (or other runtime errors)
- `3` = invalid arguments (clap parse error)

### Error format (CLI)

On fatal CLI errors, the parser prints a JSON object to **stderr**:

```json
{
  "schema_version": 1,
  "tool_version": "0.4.0",
  "error": "ParseError",
  "message": "..."
}
```

## Session mode (`serve`)

### Transport

`serve` reads **newline-delimited JSON** requests from `stdin` and writes **newline-delimited JSON** responses to `stdout`.

- One request per line
- One response per line (except `iter_section`, which returns a stream of multiple response lines)

### Requests

Requests are tagged by `op` and use `snake_case` names.

Common request shapes:

```json
{"op":"extract_sections","sections":["meta","player"]}
{"op":"get_entry","section":"country","key":"0"}
{"op":"get_entries","section":"country","keys":["0","1"],"fields":["name","type"]}
{"op":"iter_section","section":"country","batch_size":100}
{"op":"multi","ops":[{"op":"extract_sections","sections":["meta"]},{"op":"count_keys","keys":["country","fleet"]}]}
{"op":"close"}
```

Supported `op` values (see `stellaris-parser/src/commands/serve.rs`):

- `extract_sections` `{ sections: string[] }`
- `iter_section` `{ section: string, batch_size?: number }` (default `100`)
- `get_entry` `{ section: string, key: string }`
- `get_entries` `{ section: string, keys: string[], fields?: string[] }`
- `count_keys` `{ keys: string[] }`
- `contains_tokens` `{ tokens: string[] }`
- `contains_kv` `{ pairs: [string, string][] }`
- `get_country_summaries` `{ fields: string[] }`
- `get_duplicate_values` `{ section: string, key: string, field: string }`
- `get_entry_text` `{ section: string, key: string }` (raw Clausewitz text for one entry)
- `multi` `{ ops: MultiOp[] }` (batch multiple non-streaming operations)
- `close`

Notes:

- `multi` excludes `iter_section` and `close` (they require special handling).
- `batch_size <= 1` makes `iter_section` emit single-entry stream messages (backward compatible mode).

### Success responses

Success responses are JSON objects of the form:

```json
{"ok":true, ...}
```

Examples:

`get_entry`:

```json
{"ok":true,"entry":{...},"found":true}
```

`extract_sections`:

```json
{"ok":true,"data":{...}}
```

`count_keys`:

```json
{"ok":true,"counts":{"country":42,"fleet":12}}
```

`multi`:

```json
{"ok":true,"results":[{...},{...}]}
```

### Streaming responses (`iter_section`)

`iter_section` returns **multiple** success responses:

1. Stream header:
   ```json
   {"ok":true,"stream":true,"op":"iter_section","section":"country"}
   ```
2. Zero or more entries, either batched or single:
   - Batched:
     ```json
     {"ok":true,"entries":[{"key":"0","value":{...}},{"key":"1","value":{...}}]}
     ```
   - Single-entry:
     ```json
     {"ok":true,"entry":{"key":"0","value":{...}}}
     ```
3. Done marker:
   ```json
   {"ok":true,"done":true,"op":"iter_section","section":"country"}
   ```

### Error responses (session mode)

Session-mode errors are written to **stdout** as a single JSON response line:

```json
{
  "ok": false,
  "error": "ParseError",
  "message": "...",
  "exit_code": 2,
  "schema_version": 1,
  "tool_version": "0.4.0",
  "game": "stellaris"
}
```

Some errors may include `line` and `col` fields when available.

