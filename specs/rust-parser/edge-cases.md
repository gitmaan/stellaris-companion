# Edge Cases

## Validation Status (from Architecture Doc)

| Edge Case | Status | Notes |
|-----------|--------|-------|
| Duplicate keys (`trait=x trait=y`) | ✅ jomini handles | Accumulated as arrays |
| Condensed syntax (`a={b="1"c=d}`) | ✅ jomini handles | Parsed correctly |
| Escape sequences (`\"`, `\\`) | ✅ jomini handles | Handled properly |
| Windows-1252 / odd bytes | ⚠️ VALIDATE | End-to-end decoding/round-trip needed |
| Color codes (`<0x15>`) | ⚠️ VALIDATE | Preservation in JSON output needed |
| 100MB+ files | ✅ Architecture | Streaming, low memory via iter-save |
| Malformed/modded saves | ✅ Architecture | Errors surfaced; Python catches + fallback |

## Critical Validations Required

### Windows-1252 Encoding
- Stellaris uses Windows-1252 for some text (empire names, etc.)
- Must not corrupt non-ASCII characters
- Strategy: escape non-UTF8 bytes or use lossy conversion with documentation
- **Test**: Create save with special characters, verify round-trip

### Color Codes
- Format: `<0x15>` embedded in strings
- Must preserve in JSON output (don't strip or corrupt)
- Used in empire names, system names
- **Test**: Parse save with color codes, verify JSON contains them

## Test Cases Required

1. **test_save.sav** - Standard save file parsing
2. **Duplicate keys test** - Verify array accumulation
3. **Condensed syntax test** - Verify no whitespace edge cases
4. **Encoding test** - Verify Windows-1252 round-trip
5. **Color codes test** - Verify `<0x15>` preservation
6. **Large save test** - Verify streaming works for 70MB+ files
7. **Modded save test** - Verify graceful error handling

## Jomini Library Handles

The jomini crate (0.28+) handles:
- Clausewitz format parsing
- Duplicate key handling (returns as Vec)
- Escape sequences
- Binary token format (if present in Ironman saves)

## Python Fallback Strategy

When Rust parser fails:
1. Log warning with error details (line, column, context)
2. Fall back to regex-based extraction in Python
3. Continue operation (degraded but functional)
4. Track fallback frequency for debugging

```python
try:
    sections = extract_sections(self._gamestate_path, ["buildings"])
    # use parsed data
except ParserError as e:
    logging.warning(f"Rust parser failed: {e}, falling back to regex")
    # use regex fallback
```
