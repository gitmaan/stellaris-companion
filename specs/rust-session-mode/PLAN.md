# Rust Parser Session Mode Plan

## Goal
Eliminate re-parsing overhead by keeping parsed save data in memory across multiple queries. Currently every briefing parses the save **58 times**. Session mode parses **once**, giving ~25-50x speedup with zero distribution changes.

## Current State
- Rust parser: `stellaris-parser/` (CLI binary)
- Python bridge: `rust_bridge.py` (spawns new subprocess per call)
- 58 subprocess calls per briefing, each parsing the full save
- Distribution: ship platform-specific binaries (working well)

## Target State
- Rust parser gains `serve` command (session mode)
- Python spawns ONE subprocess per briefing
- Subprocess holds parsed save in memory, responds to queries
- Fallback to current spawn-per-call if session fails
- **Same distribution model** - just ship updated binary

## Why This Over PyO3

| Factor | Session Mode | PyO3 |
|--------|--------------|------|
| Speedup | ~25-50x | ~30-50x |
| Distribution change | **None** | Wheels, maturin, ABI |
| Electron compatibility | **Perfect** | Complex bundling |
| Implementation effort | 5 stories | 8 stories |
| Risk | Very low | Medium |

The ~400ms difference (IPC overhead) isn't worth the distribution complexity for an Electron app.

## Protocol Design

### Rust Side: `serve` Command

```bash
stellaris-parser serve --path save.sav
```

Rust loads and parses save once, then reads newline-delimited JSON requests from stdin:

```json
{"op": "extract_sections", "sections": ["meta", "player"]}
{"op": "iter_section", "section": "country"}
{"op": "close"}
```

Responds with newline-delimited JSON to stdout. **Protocol rule:** stdout is reserved for protocol frames only; any logging must go to stderr.

```json
{"ok": true, "data": {"meta": {...}, "player": {...}}}
{"ok": true, "stream": true, "op": "iter_section", "section": "country"}
{"ok": true, "entry": {"key": "0", "value": {...}}}
{"ok": true, "entry": {"key": "1", "value": {...}}}
{"ok": true, "done": true, "op": "iter_section", "section": "country"}
{"ok": true, "closed": true}
```

### Error Responses

```json
{"ok": false, "error": "SectionNotFound", "message": "Section 'foo' not found", "line": null, "col": null}
```

Preserves existing `ParserError` contract fields (`message`, `line`, `col`) and adds stable structured keys that work in both modes:
- `error`: short machine code (e.g., `InvalidRequest`, `SectionNotFound`, `ParseError`)
- `exit_code`: numeric code matching CLI semantics where applicable (1/2/3), or 2 as a default for request-level failures
- `tool_version`, `schema_version`, `game`: optionally included for parity with existing CLI output

### Python Side: Session Client

```python
class RustSession:
    def __init__(self, save_path):
        self._proc = subprocess.Popen(
            [PARSER_BINARY, "serve", "--path", str(save_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def extract_sections(self, sections: list[str]) -> dict:
        self._send({"op": "extract_sections", "sections": sections})
        return self._recv()["data"]

    def iter_section(self, section: str) -> Iterator[tuple[str, dict]]:
        self._send({"op": "iter_section", "section": section})
        # First frame: {"ok": true, "stream": true, ...}
        header = self._recv()
        if not header.get("stream"):
            raise ParserError("Expected stream header")
        # Then stream entry frames until {"done": true}
        while True:
            frame = self._recv()
            if frame.get("done"):
                return
            entry = frame.get("entry") or {}
            yield entry["key"], entry["value"]

    def close(self):
        self._send({"op": "close"})
        self._proc.wait(timeout=5)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
```

### Python Side: Seamless “Default Fast Path”

Goal: **no “power user” vs “normal user” split**. Existing extractor code keeps calling `rust_bridge.extract_sections()` and `rust_bridge.iter_section_entries()` and automatically benefits from session mode when active.

Design:
- `rust_bridge` exposes a context manager `session(save_path)` that sets a context-local “active session” (thread-local) for the duration of a briefing.
- Module-level functions use the active session if present; otherwise they fall back to the current spawn-per-call implementation.

```python
# rust_bridge.py
from contextlib import contextmanager
from threading import local

_tls = local()

@contextmanager
def session(save_path: str | Path):
    s = RustSession(save_path)
    prev = getattr(_tls, "session", None)
    _tls.session = s
    try:
        yield s
    finally:
        _tls.session = prev
        s.close()

def extract_sections(save_path, sections):
    s = getattr(_tls, "session", None)
    if s is not None:
        return s.extract_sections(list(sections))
    return _spawn_extract_sections(save_path, sections)

def iter_section_entries(save_path, section):
    s = getattr(_tls, "session", None)
    if s is not None:
        yield from s.iter_section(section)
        return
    yield from _spawn_iter_section_entries(save_path, section)
```

## Stories

### 1. Add `serve` Command to Rust CLI
**Files:** `stellaris-parser/src/main.rs`, `stellaris-parser/src/commands/serve.rs`

Add new subcommand that:
- Loads and parses save file once
- Enters read loop on stdin
- Responds to JSON requests on stdout

```rust
Commands::Serve { path } => commands::serve::run(&path),
```

**Acceptance:**
- `echo '{"op":"extract_sections","sections":["meta"]}' | stellaris-parser serve --path test_save.sav` returns JSON
- Process stays alive waiting for more input
- `{"op":"close"}` cleanly exits

### 2. Implement `extract_sections` Operation
**File:** `stellaris-parser/src/commands/serve.rs`

Handle `extract_sections` requests using already-parsed data.

```rust
fn handle_extract_sections(parsed: &ParsedSave, sections: &[String]) -> Result<Value> {
    // Reuse logic from commands/extract.rs but don't re-parse
}
```

**Acceptance:**
- Multiple `extract_sections` calls return correct data
- No re-parsing between calls (verify with timing)

### 3. Implement `iter_section` Operation
**File:** `stellaris-parser/src/commands/serve.rs`

Handle `iter_section` requests **as a stream** to keep memory usage bounded and preserve the benefits of the current `iter-save --format jsonl` design.

Protocol:
- Write a stream header frame: `{"ok": true, "stream": true, "op":"iter_section", "section":"country"}`
- Then write one entry frame per item: `{"ok": true, "entry": {"key":"0","value":{...}}}`
- Finish with a done frame: `{"ok": true, "done": true, "op":"iter_section", "section":"country"}`

**Acceptance:**
- `iter_section` for "country" returns all countries
- `iter_section` for "fleet" returns all fleets
- Large sections (1000+ entries) don't crash and don't allocate an entire `Vec` of entries

### 4. Add Error Handling and Graceful Shutdown
**File:** `stellaris-parser/src/commands/serve.rs`

- Invalid JSON → error response, keep running
- Unknown operation → error response, keep running
- `close` operation → clean exit with code 0
- stdin EOF → clean exit
- Parse errors → structured error response matching `ParserError` contract

**Acceptance:**
- Malformed input doesn't crash server
- Error responses have `message`, `line`, `col`, and stable `error` and `exit_code` fields
- Clean shutdown on `close` or EOF

### 5. Update rust_bridge.py with Session Mode
**File:** `rust_bridge.py`

Add `RustSession` + a **context-local default fast path**:
- New context manager `session(save_path)` (see above)
- Existing `extract_sections()` / `iter_section_entries()` automatically use the active session when present
- Keep the old spawn-per-call code as fallback implementation, not the default during briefing generation

**Acceptance:**
- Existing `extract_sections()` calls still work (backward compatible)
- `session()` context manager works
- No extractor call-site changes required to benefit during a briefing run

### 6. Add SaveCache Using Session Mode
**File:** `rust_bridge.py`

```python
class SaveCache:
    """Cache for parsed save data using Rust session."""

    def __init__(self, save_path):
        self._session = RustSession(save_path)
        self._section_cache = {}  # Optional: cache repeated section requests

    def extract_sections(self, sections):
        return self._session.extract_sections(sections)

    def iter_section(self, section):
        return self._session.iter_section(section)

    def close(self):
        self._session.close()
```

**Acceptance:**
- `SaveCache` can serve multiple extractor calls
- Cache can be passed to extractors or used in base class (optional). Primary integration path is `rust_bridge.session()` so callers don't need to thread cache objects.

### 7. Integrate SaveCache into Briefing Generation
**File:** `stellaris_save_extractor/base.py` or `backend/core/ingestion_worker.py`

Update briefing generation to use session mode:

```python
def _process_main(job, out_q):
    # One line integration: all internal rust_bridge calls become session-backed.
    from rust_bridge import session as rust_session
    with rust_session(job["save_path"]):
        extractor = SaveExtractor(str(job["save_path"]))
        briefing = extractor.get_complete_briefing()
```

**Acceptance:**
- `get_complete_briefing()` completes in < 2 seconds (was 10-20s)
- "Briefing not ready" message rarely seen
- All existing tests pass

### 8. Add Timeout and Zombie Process Handling
**File:** `rust_bridge.py`

Handle edge cases:
- Session process crashes → detect and fall back to spawn-per-call
- Session hangs → timeout and kill
- Python exits without closing → process cleanup

```python
class RustSession:
    def _send(self, request):
        try:
            self._proc.stdin.write(json.dumps(request).encode() + b'\n')
            self._proc.stdin.flush()
        except BrokenPipeError:
            raise ParserError("Session crashed unexpectedly")

    def _recv(self, timeout=30):
        # Cross-platform approach: reader thread pushes stdout lines into a queue.
        # _recv pops with a timeout and parses JSON.
        ...
```

**Acceptance:**
- Crashed session raises `ParserError`, caller can retry with spawn mode
- Hung session times out after 30s
- No zombie processes after Python exits

## Implementation Order

```
1. Serve command (Rust)     ─┐
2. extract_sections op      ─┼─► Rust work (can test with echo/pipe)
3. iter_section op          ─┤
4. Error handling           ─┘

5. RustSession class        ─┐
6. SaveCache                ─┼─► Python integration
7. Briefing integration     ─┤
8. Timeout/cleanup          ─┘
```

Stories 1-4 are Rust-only, testable independently.
Stories 5-8 integrate with Python.

## Testing Strategy

### Manual Testing (Stories 1-4)
```bash
# Start session
stellaris-parser serve --path test_save.sav

# In another terminal, send requests
echo '{"op":"extract_sections","sections":["meta"]}' | nc localhost ...
# Or just test with stdin pipe
```

### Integration Testing (Stories 5-8)
```python
def test_session_mode_faster_than_spawn():
    # Time spawn-per-call
    start = time.time()
    for _ in range(10):
        extract_sections("test_save.sav", ["meta"])
    spawn_time = time.time() - start

    # Time session mode
    start = time.time()
    with RustSession("test_save.sav") as s:
        for _ in range(10):
            s.extract_sections(["meta"])
    session_time = time.time() - start

    assert session_time < spawn_time / 10  # At least 10x faster
```

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Session process crashes | Automatic fallback to spawn-per-call |
| Memory leak in long session | Session is per-briefing, not long-lived |
| Protocol bugs | Extensive error handling, keep it simple |
| Windows stdin/stdout issues | Test on Windows early |

## Success Metrics

- [ ] `get_complete_briefing()` < 2 seconds (currently 10-20s)
- [ ] "Briefing not ready" rarely seen in normal use
- [ ] All existing tests pass
- [ ] No distribution changes needed
- [ ] Works on macOS, Windows, Linux

## Future Optimization (Optional)

If session mode IPC becomes a bottleneck:
1. **Streaming iter_section** - Send entries one-by-one instead of batched
2. **Binary protocol** - MessagePack instead of JSON
3. **PyO3 native module** - Eliminate IPC entirely

But measure first - session mode may be fast enough.
