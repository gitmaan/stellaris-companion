# Clausewitz Parser Proposal

## Problem Statement

The current save extraction uses regex patterns to parse the Clausewitz format. This approach has two issues:

### 1. Regex Brittleness

Patterns like these assume exact whitespace and formatting:

```python
# From base.py:67 - assumes specific spacing
pattern = r'(\d+)=\s*\{\s*type="([^"]+)"'

# From base.py:215 - assumes exact tab indentation
pattern = rf'\n\t{player_id}=\n\t\{{'
```

If Paradox changes formatting in a patch (extra spaces, different indentation), these silently fail.

### 2. Memory Usage

The entire 70MB+ gamestate is loaded into memory as a string (`base.py:79-82`), which can cause memory pressure on systems with limited RAM.

---

## Initial Proposal Issues

An initial recursive descent parser was proposed and validated. While it worked for basic cases, critical review identified these problems:

### Issue 1: Silent Partial Parses

The original parser would silently stop parsing on unexpected input:

```python
# Original behavior - DANGEROUS
test = 'a="1"\nb\nc="3"'  # 'b' has no '='
result = OriginalParser(test).parse()
# Returns {'a': '1'} - silently lost 'c'!
```

For a tool used by thousands of players, silent data loss is unacceptable.

### Issue 2: Dict-Only Model Too Restrictive

Clausewitz blocks can contain both key=value pairs AND bare items:

```
player={
    {
        name="unknown"
        country=0
    }
}
```

This is a list containing a dict - the original "peek first item to decide dict vs list" heuristic works here, but a mixed container is more robust.

### Issue 3: Memory Multiplier

Parsing a 71MB file into nested Python dicts/lists can use 2-3x the original text size (100-200MB+), potentially worse than the regex approach.

---

## Revised Approach: Span-Based + Strict Parser

Based on critical review, the recommended approach is:

1. **Span extraction** (fast, low-memory): Find block boundaries and iterate entries without materializing everything
2. **Small-block parsing** (safe): Only parse blocks that are known-small (one country, one fleet, etc.)
3. **Explicit errors**: Raise `ClausewitzParseError` with location info instead of silent partial results
4. **Mixed container**: Support both key=value pairs AND bare items in the same block

---

## Implementation

### Error Type

```python
class ClausewitzParseError(Exception):
    """Explicit parse error with location info."""
    def __init__(self, msg: str, pos: int, text: str):
        self.pos = pos
        self.line = text[:pos].count('\n') + 1
        line_start = text.rfind('\n', 0, pos) + 1
        self.col = pos - line_start + 1
        # Context excerpt
        start = max(0, pos - 20)
        end = min(len(text), pos + 20)
        self.context = text[start:end].replace('\n', '\\n')
        super().__init__(f"{msg} at line {self.line}, col {self.col}: ...{self.context}...")
```

### Mixed Block Container

```python
@dataclass
class Block:
    """Mixed container: supports both key=value pairs AND list items."""
    pairs: dict = field(default_factory=dict)  # key -> value or list of values
    items: list = field(default_factory=list)  # bare items

    def get(self, key, default=None):
        return self.pairs.get(key, default)

    def __getitem__(self, key):
        return self.pairs[key]

    def __contains__(self, key):
        return key in self.pairs

    def is_pure_dict(self) -> bool:
        return len(self.items) == 0

    def is_pure_list(self) -> bool:
        return len(self.pairs) == 0
```

This handles the problematic case correctly:

```python
test = 'a="1"\nb\nc="3"'  # 'b' has no '='

# Original parser: {'a': '1'} - LOST 'c'!
# Improved parser: Block(pairs={'a': '1', 'c': '3'}, items=['b']) - ALL preserved
```

### Span-Based Iteration (Low Memory)

For huge sections, iterate entries without full parsing:

```python
@dataclass
class ValueSpan:
    """Reference to a value's location without parsing it."""
    kind: str  # "string", "literal", "block"
    start: int
    end: int


def find_braced_span(text: str, open_pos: int) -> tuple[int, int]:
    """Find matching close brace. Returns (start, end_exclusive)."""
    if text[open_pos] != '{':
        raise ValueError("open_pos must point to '{'")

    depth = 0
    pos = open_pos
    in_string = False

    while pos < len(text):
        ch = text[pos]
        if in_string:
            if ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return (open_pos, pos + 1)
        pos += 1

    raise ClausewitzParseError("Unclosed block", open_pos, text)


def iter_block_entries(text: str, span: tuple[int, int]) -> Iterator[tuple[str | None, ValueSpan]]:
    """Iterate top-level entries without full parsing.

    Yields:
        (key, ValueSpan) for key=value pairs
        (None, ValueSpan) for bare items
    """
    # Implementation iterates without materializing nested structures
    ...
```

### Strict Parser

```python
class StrictParser:
    """Parser that raises on any unexpected condition."""

    def __init__(self, text: str, max_depth: int = 100, max_nodes: int = 500000):
        self.text = text
        self.pos = 0
        self.length = len(text)
        self.max_depth = max_depth
        self.max_nodes = max_nodes
        self.node_count = 0
        self.depth = 0

    def parse(self) -> Block:
        """Parse entire text as block content."""
        return self._parse_block_content()

    def _parse_block_content(self) -> Block:
        """Parse content inside a block (pairs and/or items)."""
        self.depth += 1
        if self.depth > self.max_depth:
            raise ClausewitzParseError(f"Max depth {self.max_depth} exceeded", self.pos, self.text)

        result = Block()

        while True:
            self._skip_ws()
            if self.pos >= self.length or self.text[self.pos] == '}':
                break

            self.node_count += 1
            if self.node_count > self.max_nodes:
                raise ClausewitzParseError(f"Max nodes {self.max_nodes} exceeded", self.pos, self.text)

            first = self._parse_token_or_block()
            self._skip_ws()

            if self.pos < self.length and self.text[self.pos] == '=':
                # Key=value pair
                if not isinstance(first, str):
                    raise ClausewitzParseError("Block cannot be a key", self.pos, self.text)
                self.pos += 1
                value = self._parse_value()

                # Duplicate keys always accumulate into list
                if first in result.pairs:
                    existing = result.pairs[first]
                    if isinstance(existing, list):
                        existing.append(value)
                    else:
                        result.pairs[first] = [existing, value]
                else:
                    result.pairs[first] = value
            else:
                # Bare item
                result.items.append(first)

        self.depth -= 1
        return result

    # ... (full implementation in parser.py)
```

---

## Validation Results

Tested against real save file (`test_save.sav`, 71.4 MB):

### Error Handling

| Input | Original Parser | Strict Parser |
|-------|-----------------|---------------|
| `a="1"\nb\nc="3"` | `{'a': '1'}` (lost c!) | `Block(pairs={a,c}, items=[b])` |
| `outer={inner=` | `{'outer': {}}` (wrong) | `ClausewitzParseError` |
| `key="unterminated` | `{'key': 'unterminated'}` | `ClausewitzParseError` |

### Real Data Parsing

| Section | Result |
|---------|--------|
| Galaxy | template=huge, shape=elliptical, num_empires=15 |
| Species traits | Correctly accumulated as list: `['trait_organic', 'trait_adaptive', ...]` |
| Span iteration | 100+ species entries iterated without full parse |

### Performance

| Operation | Time |
|-----------|------|
| Find braced span (5MB section) | < 50ms |
| Iterate 100 species entries | < 10ms |
| Parse galaxy section | < 1ms |

---

## Integration Pattern

### Error + Fallback

```python
def extract_with_fallback(section_text: str) -> dict:
    """Try parser, fallback to regex on error."""
    try:
        result = StrictParser(section_text).parse()
        return {"method": "parser", "data": result}
    except ClausewitzParseError as e:
        # Log for debugging
        logging.warning(f"Parser failed: {e}, falling back to regex")
        # Fallback to simple regex extraction
        pairs = {}
        for m in re.finditer(r'(\w+)="([^"]*)"', section_text):
            pairs[m.group(1)] = m.group(2)
        return {"method": "regex_fallback", "error": str(e), "data": pairs}
```

### Span-Based Extraction (Recommended for Large Sections)

```python
def get_country_names_efficient(gamestate: str) -> dict[int, str]:
    """Extract country names without parsing entire country section."""
    country_match = re.search(r'^country=\s*\{', gamestate, re.MULTILINE)
    if not country_match:
        return {}

    brace_pos = gamestate.find('{', country_match.start())
    span = find_braced_span(gamestate, brace_pos)

    names = {}
    for key, val_span in iter_block_entries(gamestate, span):
        if key and key.isdigit():
            country_id = int(key)
            # Only parse the small country block, not the whole section
            country_block = gamestate[val_span.start:val_span.end]
            # Quick regex for name within small block
            name_match = re.search(r'name\s*=\s*"([^"]+)"', country_block[:500])
            if name_match:
                names[country_id] = name_match.group(1)

    return names
```

---

## Migration Strategy

### Phase 1: Add Parser Module

Create `stellaris_save_extractor/parser.py` with:
- `ClausewitzParseError`
- `Block` dataclass
- `find_braced_span()`
- `iter_block_entries()`
- `StrictParser`

### Phase 2: Migrate High-Value Extractors

Start with extractors where regex brittleness hurts most:
1. Country name resolution (handles localization templates)
2. Fleet analysis (complex nested structures)
3. Species traits (duplicate keys)

### Phase 3: Add Golden Tests

Create test fixtures from multiple saves:
- Early game
- Mid game
- Late game (large)
- Modded games

Assert key extracted facts match expected values.

### Phase 4: Performance Optimization (If Needed)

If parsing becomes a bottleneck:
1. Use span iteration for huge sections (ships, pops)
2. Add `max_nodes` limits to prevent pathological saves from hanging
3. Consider mmap for very large files

---

## Key Differences from Initial Proposal

| Aspect | Initial | Revised |
|--------|---------|---------|
| Error handling | Silent break | Explicit `ClausewitzParseError` |
| Data model | Pure dict | `Block(pairs, items)` |
| Memory strategy | Parse everything | Span iteration + small-block parsing |
| Duplicate keys | Inconsistent | Always accumulate to list |
| Safety limits | None | `max_depth`, `max_nodes` |
| Fallback | None | Regex fallback on parse error |

---

## Conclusion

The revised approach provides:

1. **Robustness**: Explicit errors instead of silent data loss
2. **Correctness**: Mixed blocks handled properly
3. **Memory efficiency**: Span-based iteration for large sections
4. **Safety**: Limits prevent pathological inputs from hanging
5. **Graceful degradation**: Fallback to regex on parse errors

This is suitable for a tool used by thousands of Stellaris players across different game versions, mods, and save file sizes.
