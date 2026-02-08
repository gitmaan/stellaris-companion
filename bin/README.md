# Stellaris Parser Binaries

This directory contains the `stellaris-parser` Rust binary for your platform.

## Binary Placement

Place the appropriate binary for your platform in this directory:

| Platform | Binary Name |
|----------|-------------|
| Windows x64 | `stellaris-parser.exe` |
| macOS x64 (Intel) | `stellaris-parser-darwin-x64` |
| macOS ARM64 (Apple Silicon) | `stellaris-parser-darwin-arm64` |
| Linux x64 | `stellaris-parser-linux-x64` |

## Getting Binaries

### Option 1: Download from GitHub Releases

Download pre-built binaries from:

https://github.com/gitmaan/stellaris-companion/releases

### Option 2: Build from Source

```bash
cd stellaris-parser
cargo build --release

# Binary will be at: stellaris-parser/target/release/stellaris-parser
# Copy it to bin/ with the appropriate name for your platform
```

## Development

During development, you don't need to copy binaries here. The `stellaris_companion.rust_bridge` module automatically checks:

1. `PARSER_BINARY` environment variable (for testing/override)
2. `stellaris-parser/target/release/stellaris-parser` (development build)
3. `bin/` directory (packaged distribution; supports both suffixed + legacy unsuffixed names)

## Binary Interface

The stellaris-parser binary provides:

```bash
# Session-mode server (used by the Electron app / Python backend)
stellaris-parser serve --path save.sav

# Extract sections from a save file
stellaris-parser extract-save save.sav --sections meta,galaxy --output -

# Stream entries from large sections
stellaris-parser iter-save save.sav --section country --format jsonl
```

See `docs/RUST_PARSER_ARCHITECTURE.md` for the full CLI interface specification.
