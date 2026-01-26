# Rust Parser - Build & Test

## Setup

```bash
# Ensure Rust is installed
rustup --version || curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Navigate to Rust project (from project root)
cd stellaris-parser
```

## Build

```bash
# Debug build (fast compilation)
cd stellaris-parser && cargo build

# Release build (optimized) - USE THIS FOR TESTING
cd stellaris-parser && cargo build --release

# Binary locations:
# Debug: stellaris-parser/target/debug/stellaris-parser
# Release: stellaris-parser/target/release/stellaris-parser
```

## Rust Tests

```bash
# Run all Rust tests
cd stellaris-parser && cargo test

# Run specific test
cd stellaris-parser && cargo test duplicate_keys
cd stellaris-parser && cargo test condensed_syntax
cd stellaris-parser && cargo test escape_sequences
cd stellaris-parser && cargo test encoding

# List all tests
cd stellaris-parser && cargo test -- --list
```

## CLI Verification (from project root)

```bash
# Test extract-save with meta section
./stellaris-parser/target/release/stellaris-parser extract-save test_save.sav --sections meta --output - | jq .

# Test extract-save with multiple sections
./stellaris-parser/target/release/stellaris-parser extract-save test_save.sav --sections meta,galaxy --output - | jq 'keys'

# Test iter-save with country section
./stellaris-parser/target/release/stellaris-parser iter-save test_save.sav --section country --format jsonl | head -5

# Verify exit codes
./stellaris-parser/target/release/stellaris-parser extract-save test_save.sav --sections meta --output -; echo "exit:$?"
./stellaris-parser/target/release/stellaris-parser extract-save nonexistent.sav --sections meta 2>&1; echo "exit:$?"
```

## Python Integration Tests

```bash
# Test rust_bridge module (from project root)
python -c "from rust_bridge import extract_sections; print(extract_sections('test_save.sav', ['meta']))"

python -c "from rust_bridge import iter_section_entries; print(list(iter_section_entries('test_save.sav', 'country'))[:2])"

# Run pytest if tests exist
python -m pytest tests/ -v
```

## Type Check / Lint

```bash
# Rust type checking (faster than full build)
cd stellaris-parser && cargo check

# Clippy lints
cd stellaris-parser && cargo clippy -- -D warnings
```

## Verify All (Full Validation)

```bash
# From project root - run this after each story
cd stellaris-parser && cargo check && cargo clippy -- -D warnings && cargo test && cargo build --release

# Then test CLI
./stellaris-parser/target/release/stellaris-parser extract-save test_save.sav --sections meta --output - | jq .schema_version
```

## Test Save Location

The project has `test_save.sav` in the root directory. Use this for all CLI tests:
- `test_save.sav` - Main test file (Stellaris save, ZIP format)

To extract raw gamestate for debug testing:
```bash
unzip -p test_save.sav gamestate > /tmp/gamestate_test
```

## Learnings

(Ralph adds learnings here as iterations progress)
- Working directory matters: CLI tests should run from project root, cargo commands from stellaris-parser/
