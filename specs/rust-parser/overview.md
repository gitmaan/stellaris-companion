# Rust Parser Overview

## Purpose

Replace fragile Python regex-based parsing with a robust Rust CLI using the jomini library. The Rust binary handles Clausewitz format parsing while Python retains domain logic.

## Architecture

```
Python Extractors (7.5k LOC)
        │
        ▼
  rust_bridge.py
        │ subprocess + JSON
        ▼
  stellaris-parser (Rust CLI)
        │ jomini library
        ▼
  .sav file (gamestate + meta)
```

## Key Decisions

1. **Option 3: Rust CLI** - Not PyO3 (Python 3.14 ABI issues) or full Rust rewrite (overkill)
2. **Subprocess interface** - Language-agnostic, easy distribution
3. **JSON/JSONL output** - Small sections as JSON, large sections as streaming JSONL
4. **Schema versioning** - All outputs include `schema_version` for forward compatibility
5. **Python fallback** - Regex fallback when Rust parser unavailable or fails

## Commands

```bash
# Extract sections as JSON
stellaris-parser extract-save /path/to/save.sav --sections meta,galaxy --output -

# Stream large sections as JSONL
stellaris-parser iter-save /path/to/save.sav --section country --format jsonl
```

## Distribution

- Windows x64: `stellaris-parser.exe`
- macOS x64: `stellaris-parser-darwin-x64`
- macOS ARM64: `stellaris-parser-darwin-arm64`
- Linux x64: `stellaris-parser-linux-x64`
