# Rust Parser Architecture Decision

## Executive Summary

After evaluating parsing approaches for Stellaris save files, the recommended architecture is **Option 3: Rust CLI using Jomini**, invoked by Python via subprocess. This provides the best tradeoff between reliability, performance, and distribution complexity.

This document defines the *contract* between Python and the Rust binary. The guiding principles are:
- Keep outputs small by default (stream for large sections).
- Make failures explicit and machine-readable (no silent partial parses).
- Version the interface (avoid breaking Python extractors accidentally).

---

## Options Evaluated

| Option | Description | Verdict |
|--------|-------------|---------|
| 1. Pure Python | Harden existing parser + regex fallback | Works but accumulates edge case bugs |
| 2. Rust via PyO3 | Native Python extension | Python 3.14 ABI issues, wheel complexity |
| **3. Rust CLI** | Standalone binary, Python calls via subprocess | **Recommended** |
| 4. Full Rust | Rewrite all extraction in Rust | Overkill, loses Python flexibility |

---

## Why Option 3

### Constraints

| Requirement | Option 3 Fit |
|-------------|--------------|
| Windows + Mac distribution | Ship binaries per platform, no Python ABI issues |
| Many games/mods/patches | Python owns extraction logic - easy to update |
| Process before autosave (minutes) | Rust parsing is fast; overall pipeline should be comfortably within minutes |
| Electron bundling | Include binary in resources folder |
| Python 3.14 compatibility | Binary is Python-version independent |
| Agent implementation | Clear contract: file → JSON |

### Why Not Option 2 (PyO3 Extension)

The project uses Python 3.14 (bleeding edge). PyO3 wheel support may be incomplete. Native extensions require:
- Building wheels for each Python version × platform
- Complex PyInstaller/Electron bundling
- Users with matching Python version

A standalone binary avoids all of this.

### Why Not Option 4 (Full Rust Rewrite)

The project has **7,585 lines of working Python extraction logic** across 19 modules. Rewriting in Rust:
- Takes months instead of days
- Duplicates tested domain knowledge
- Makes patch/mod responses slower (Rust rebuild vs Python edit)
- Only worthwhile for multi-client engine (not this project)

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Python Layer                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │
│  │ Discord Bot │  │  Electron   │  │    CLI      │      │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘      │
│         │                │                │              │
│         └────────────────┼────────────────┘              │
│                          ▼                               │
│              ┌───────────────────────┐                   │
│              │   SaveExtractor       │                   │
│              │   (Python - 7.5k LOC) │                   │
│              │   - Domain logic      │                   │
│              │   - Field mapping     │                   │
│              │   - Validation        │                   │
│              └───────────┬───────────┘                   │
│                          │                               │
│              ┌───────────▼───────────┐                   │
│              │   rust_bridge.py      │                   │
│              │   - subprocess call   │                   │
│              │   - JSON parsing      │                   │
│              │   - Error handling    │                   │
│              └───────────┬───────────┘                   │
└──────────────────────────┼───────────────────────────────┘
                           │ subprocess + JSON
                           ▼
┌──────────────────────────────────────────────────────────┐
│                    Rust Binary                            │
│              ┌───────────────────────┐                    │
│              │   stellaris-parser    │                    │
│              │   - jomini library    │                    │
│              │   - Section extraction│                    │
│              │   - Encoding handling │                    │
│              │   - Edge case parsing │                    │
│              └───────────────────────┘                    │
└──────────────────────────────────────────────────────────┘
```

---

## Rust CLI Interface

### Commands (contract-first)

Primary use case is `.sav` inputs (the binary reads both `gamestate` and `meta` internally). This avoids Python having to extract files to disk and ensures consistent decoding/edge-case handling.

```bash
# Extract selected content from a .sav file as JSON (recommended for small outputs)
stellaris-parser extract-save /path/to/save.sav \
  --sections meta,galaxy \
  --output -

# Stream entries from a large section (recommended for huge sections like country/ships/pops)
stellaris-parser iter-save /path/to/save.sav \
  --section country \
  --format jsonl
```

Raw gamestate path support is optional and only intended for debugging:

```bash
# Debug: parse an already-extracted gamestate file (not recommended for production integration)
stellaris-parser extract-gamestate /path/to/gamestate \
  --sections galaxy \
  --output -
```

### Interface Versioning

All successful JSON outputs MUST include:

```json
{"schema_version": 1, "tool_version": "0.1.0", "game": "stellaris"}
```

All commands MUST accept:
- `--schema-version 1` (defaults to latest supported)

This makes the CLI contract forward-compatible and allows Python to refuse unknown schemas.

```bash
# Extract specific sections as JSON (small)
stellaris-parser extract-save /path/to/save.sav \
  --sections galaxy,species_db \
  --output -

# Stream entries from large section (JSONL)
stellaris-parser iter-save /path/to/save.sav \
  --section country \
  --format jsonl
```

### Output Format

**Section extraction:**
```json
{
  "schema_version": 1,
  "tool_version": "0.1.0",
  "game": "stellaris",
  "meta": {
    "version": "Corvus v4.2.4",
    "date": "2431.02.18"
  },
  "galaxy": {
    "template": "huge",
    "shape": "elliptical",
    "num_empires": "15"
  },
  "species_db": {
    "0": {
      "traits": {}
    },
    "3036676097": {
      "name_list": "HUMAN1",
      "class": "HUM",
      "traits": {
        "trait": ["trait_organic", "trait_adaptive", "trait_nomadic"]
      }
    }
  }
}
```

**Entry iteration (JSONL):**
```jsonl
{"schema_version":1,"tool_version":"0.1.0","game":"stellaris","section":"country","key":"0","value":{"name":"United Nations of Earth", ...}}
{"key": "1", "value": {"name": "Tzynn Empire", ...}}
{"key": "2", "value": {"name": "Jehetma Dominion", ...}}
```

Notes:
- For JSONL, the first form (with `schema_version/tool_version`) is preferred; at minimum include `section`, `key`, and `value`.
- For large sections, streaming JSONL is strongly preferred over returning one huge JSON object.

### Selectors (keep outputs small)

The binary SHOULD support selectors to avoid dumping entire sections:

```bash
# Only a few keys from a large section
stellaris-parser extract-save /path/to/save.sav \
  --section country --keys 0,1,2 \
  --output -

# Extract a nested path (best-effort), returning a small JSON object
stellaris-parser extract-save /path/to/save.sav \
  --path meta.date \
  --path galaxy.template \
  --output -
```

If selectors are not implemented initially, the architecture should still prioritize streaming (`iter-save`) for any large section to avoid JSON bottlenecks.

### Error Handling

Exit codes:
- `0`: Success
- `1`: File not found / IO error
- `2`: Parse error (with position info in stderr)
- `3`: Invalid arguments

Stderr contains structured error info:
```json
{"schema_version":1,"tool_version":"0.1.0","error":"ParseError","message":"...","line":1234,"col":56,"context":"..."}
```

Important:
- Rust must keep stderr output bounded (single JSON object on failure). This prevents Python subprocess pipes from filling and deadlocking.

---

## Python Integration

### rust_bridge.py

```python
"""Bridge to Rust Clausewitz parser."""

import subprocess
import json
import platform
from pathlib import Path
from typing import Iterator

# Binary location (bundled with package)
def _get_binary_path() -> Path:
    """Get path to stellaris-parser binary for current platform."""
    base = Path(__file__).parent / "bin"
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "windows":
        return base / "stellaris-parser.exe"
    elif system == "darwin":
        if "arm" in machine:
            return base / "stellaris-parser-darwin-arm64"
        return base / "stellaris-parser-darwin-x64"
    else:
        return base / "stellaris-parser-linux-x64"


PARSER_BINARY = _get_binary_path()


class ParserError(Exception):
    """Error from Rust parser."""
    def __init__(self, message: str, line: int = None, col: int = None):
        self.line = line
        self.col = col
        super().__init__(message)


def extract_sections(gamestate_path: Path, sections: list[str]) -> dict:
    """Extract specific sections from gamestate as parsed JSON.

    Args:
        gamestate_path: Path to .sav file (recommended) or extracted gamestate (debug only)
        sections: List of section names (e.g., ["galaxy", "species_db"])

    Returns:
        Dict with section names as keys, parsed content as values

    Raises:
        ParserError: If parsing fails
        FileNotFoundError: If binary or gamestate not found
    """
    if not PARSER_BINARY.exists():
        raise FileNotFoundError(f"Parser binary not found: {PARSER_BINARY}")

    result = subprocess.run(
        [str(PARSER_BINARY), "extract-save", str(gamestate_path),
         "--sections", ",".join(sections),
         "--schema-version", "1",
         "--output", "-"],
        capture_output=True,
        timeout=60,
    )

    if result.returncode != 0:
        error_info = _parse_error(result.stderr)
        raise ParserError(**error_info)

    return json.loads(result.stdout)


def iter_section_entries(gamestate_path: Path, section: str) -> Iterator[tuple[str, dict]]:
    """Stream entries from a large section without loading all into memory.

    Args:
        gamestate_path: Path to .sav file (recommended) or extracted gamestate (debug only)
        section: Section name (e.g., "country", "ships")

    Yields:
        Tuples of (key, value) for each entry in the section
    """
    if not PARSER_BINARY.exists():
        raise FileNotFoundError(f"Parser binary not found: {PARSER_BINARY}")

    proc = subprocess.Popen(
        [str(PARSER_BINARY), "iter-save", str(gamestate_path),
         "--section", section,
         "--schema-version", "1",
         "--format", "jsonl"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    for line in proc.stdout:
        if line.strip():
            entry = json.loads(line)
            yield entry["key"], entry["value"]

    proc.wait()
    if proc.returncode != 0:
        error_info = _parse_error(proc.stderr.read())
        raise ParserError(**error_info)


def _parse_error(stderr: bytes) -> dict:
    """Parse error info from stderr."""
    try:
        err = json.loads(stderr)
        return {
            "message": err.get("error", "Unknown error"),
            "line": err.get("line"),
            "col": err.get("col"),
        }
    except json.JSONDecodeError:
        return {"message": stderr.decode(errors="replace")}
```

Implementation note:
- To avoid subprocess deadlocks, the Rust tool MUST keep stderr output bounded (single JSON error object). If verbose logs are needed, provide an explicit `--verbose` flag and consider writing logs to a file instead of stderr when called from Python.

### Updated Extractor Pattern

```python
# Before (regex-based)
class SaveExtractorBase:
    def _get_building_types(self) -> dict:
        if self._building_types is not None:
            return self._building_types

        match = re.search(r'^buildings=\s*\{', self.gamestate, re.MULTILINE)
        if not match:
            return {}

        chunk = self.gamestate[match.start():match.start() + 5000000]
        self._building_types = {}
        for m in re.finditer(r'(\d+)=\s*\{\s*type="([^"]+)"', chunk):
            self._building_types[m.group(1)] = m.group(2)

        return self._building_types


# After (Rust-parsed)
from .rust_bridge import extract_sections, ParserError

class SaveExtractorBase:
    def _get_building_types(self) -> dict:
        if self._building_types is not None:
            return self._building_types

        try:
            sections = extract_sections(self._gamestate_path, ["buildings"])
            buildings = sections.get("buildings", {})
            self._building_types = {
                bid: data.get("type")
                for bid, data in buildings.items()
                if isinstance(data, dict) and "type" in data
            }
        except ParserError as e:
            # Fallback to regex on parse error
            logging.warning(f"Rust parser failed: {e}, falling back to regex")
            self._building_types = self._get_building_types_regex()

        return self._building_types
```

---

## Rust Implementation

### Project Structure

```
stellaris-parser/
├── Cargo.toml
├── src/
│   ├── main.rs           # CLI entry point
│   ├── commands/
│   │   ├── mod.rs
│   │   ├── extract.rs    # Section extraction
│   │   └── iter.rs       # Entry iteration
│   └── output.rs         # JSON formatting
└── .github/
    └── workflows/
        └── release.yml   # Cross-platform builds
```

### Cargo.toml

```toml
[package]
name = "stellaris-parser"
version = "0.1.0"
edition = "2021"

[dependencies]
jomini = "0.28"
clap = { version = "4", features = ["derive"] }
serde_json = "1.0"
anyhow = "1.0"

[profile.release]
lto = true
codegen-units = 1
strip = true
```

### Main Entry Point (Sketch)

```rust
use clap::{Parser, Subcommand};
use anyhow::Result;

#[derive(Parser)]
#[command(name = "stellaris-parser")]
#[command(about = "Fast Clausewitz format parser for Stellaris saves")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Extract specific sections as JSON
    ExtractSave {
        /// Path to .sav file
        path: String,
        /// Comma-separated section names
        #[arg(long)]
        sections: String,
        /// Schema version for JSON contract
        #[arg(long, default_value = "1")]
        schema_version: String,
        /// Output file (- for stdout)
        #[arg(long, default_value = "-")]
        output: String,
    },
    /// Iterate entries in a section (JSONL output)
    IterSave {
        /// Path to .sav file
        path: String,
        /// Section name
        #[arg(long)]
        section: String,
        /// Schema version for JSON contract
        #[arg(long, default_value = "1")]
        schema_version: String,
        /// Output format
        #[arg(long, default_value = "jsonl")]
        format: String,
    },
}

fn main() -> Result<()> {
    let cli = Cli::parse();

    match cli.command {
        Commands::ExtractSave { path, sections, schema_version, output } => {
            commands::extract::run_save(&path, &sections, &schema_version, &output)
        }
        Commands::IterSave { path, section, schema_version, format } => {
            commands::iter::run_save(&path, &section, &schema_version, &format)
        }
    }
}
```

---

## Implementation Phases

### Phase 1: Minimal Rust CLI (1-2 days)

**Deliverables:**
- Rust project with jomini dependency
- `extract-save` command: reads `.sav`, extracts sections, outputs JSON
- `iter-save` command: streams section entries as JSONL
- GitHub Actions workflow for cross-platform builds

**Validation:**
- Parse `test_save.sav` successfully
- Output matches expected structure
- Handles edge cases (escapes, condensed syntax, duplicates) with end-to-end tests
- Encoding/odd bytes validated end-to-end (do not assume without tests)

### Phase 2: Python Integration (1 day)

**Deliverables:**
- `rust_bridge.py` with `extract_sections()` and `iter_section_entries()`
- Binary bundling in package structure
- Fallback detection when binary missing

**Validation:**
- Python can call binary and parse output
- Errors propagate correctly
- Fallback to regex works

### Phase 3: Migrate Extractors (2-3 days)

**Deliverables:**
- Update `base.py` to use Rust bridge
- Update extraction modules one by one
- Keep regex fallback for each

**Validation:**
- All existing tests pass
- Briefing extraction produces same results
- Performance is acceptable for real saves (measure; do not hardcode expectations)

### Phase 4: Distribution (1 day)

**Deliverables:**
- Binaries in GitHub releases (Windows x64, macOS x64, macOS ARM64, Linux x64)
- Electron app bundles correct binary
- Python package includes binary or downloads on install

**Validation:**
- Fresh install works on Windows
- Fresh install works on macOS
- Electron app works standalone

---

## Performance Expectations

| Operation | Expected Time |
|-----------|---------------|
| Read + decompress `.sav` (70MB gamestate) | typically sub-second to a few seconds (disk dependent) |
| Extract small sections to JSON | usually fast; dominated by IO + JSON encoding |
| Stream 300 country entries (JSONL) | typically fast; dominated by serialization |
| Full extraction pipeline | target “well under autosave interval”; measure on Windows laptops |

Autosave interval is typically 3-6 months in-game, which translates to minutes of real time. Performance is not a concern.

---

## Edge Cases (what to validate end-to-end)

| Edge Case | Status |
|-----------|--------|
| Duplicate keys (`trait=x trait=y`) | ✅ Accumulated as arrays |
| Condensed syntax (`a={b="1"c=d}`) | ✅ Parsed correctly |
| Escape sequences (`\"`, `\\`) | ✅ Handled |
| Windows-1252 / odd bytes | ⚠️ Validate end-to-end decoding/round-trip strategy |
| Color codes (`<0x15>`) | ⚠️ Validate preservation in JSON output |
| 100MB+ files | ✅ Streaming, low memory |
| Malformed/modded saves | ✅ Errors surfaced; Python must catch + fallback |

---

## Future Evolution Path

If the project later needs:
- **Multi-client support** (Python, JS, C#): The CLI contract is already language-agnostic
- **Higher performance**: Move hot extraction logic to Rust (Option 4 territory)
- **Web deployment**: Compile to WASM using jomini's WASM support

The architecture supports incremental evolution without rewrites.

---

## Decision Record

**Date:** 2025-01-22

**Decision:** Implement Option 3 (Rust CLI using Jomini)

**Rationale:**
1. Project uses Python 3.14, making native extensions (Option 2) risky
2. 7,585 lines of working Python extraction logic exists - no need to rewrite (Option 4)
3. Cross-platform binary distribution is simpler than Python wheels
4. Jomini handles all Clausewitz edge cases we discovered
5. Clear contract enables agent implementation with validation loops

**Alternatives Rejected:**
- Option 1 (Pure Python): Accumulates edge case bugs indefinitely
- Option 2 (PyO3): Python 3.14 ABI issues, wheel complexity
- Option 4 (Full Rust): Overkill, loses Python flexibility
