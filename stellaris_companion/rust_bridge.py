"""Bridge to Rust Clausewitz parser.

This module provides Python bindings to the stellaris-parser Rust binary.
It handles subprocess communication, JSON parsing, and error handling.

The Rust binary can be located in multiple places (in order of priority):
0. PARSER_BINARY environment variable (for testing/override)
1. Electron packaged app: rust-parser/ in Electron resources folder
2. Development: stellaris-parser/target/release/stellaris-parser
3. Packaged: bin/ directory relative to this file
4. System: PATH-accessible stellaris-parser binary

Session Mode:
    For improved performance when making multiple queries against the same save,
    use the session() context manager. This keeps the parsed save in memory:

        from stellaris_companion.rust_bridge import session as rust_session

        with rust_session(save_path):
            # All extract_sections/iter_section_entries calls inside this block
            # will use the same parsed data without re-parsing.
            data1 = extract_sections(save_path, ["meta"])
            data2 = extract_sections(save_path, ["player"])
            for key, country in iter_section_entries(save_path, "country"):
                ...
"""

from __future__ import annotations

import atexit
import os

# Use orjson for faster JSON parsing (~80% faster than stdlib json)
try:
    import orjson

    _json_loads = orjson.loads

    def _json_dumps(obj) -> bytes:
        """orjson.dumps returns bytes, which is what we need for stdin."""
        return orjson.dumps(obj)

    _ORJSON_AVAILABLE = True
except ImportError:
    import json

    _json_loads = json.loads

    def _json_dumps(obj) -> bytes:
        """Fallback to stdlib json, encode to bytes for consistency."""
        return json.dumps(obj).encode()

    _ORJSON_AVAILABLE = False

import json  # Keep for error parsing fallback
import platform
import queue
import subprocess
import sys
import threading
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

from .paths import get_repo_root


def _unsupported_platform_hint() -> str | None:
    """Return a user-facing hint for known unsupported platform/arch combinations."""
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "linux" and machine in {"aarch64", "arm64"}:
        return (
            "Linux ARM64 is not currently supported by bundled parser binaries. "
            "Build and provide a custom parser via PARSER_BINARY to run on this architecture."
        )
    return None


def _raise_parser_binary_not_found(binary_path: Path) -> None:
    """Raise a clear parser-missing error with platform-specific hints when available."""
    hint = _unsupported_platform_hint()
    if hint:
        raise FileNotFoundError(f"{hint} Missing parser path: {binary_path}")
    raise FileNotFoundError(f"Parser binary not found: {binary_path}")


def _get_binary_path() -> Path:
    """Get path to stellaris-parser binary for current platform.

    Searches in order:
    0. PARSER_BINARY environment variable (for testing/override)
    1. Electron packaged app: rust-parser/ folder in resources
       (when running as PyInstaller bundle inside Electron)
    2. Development location: stellaris-parser/target/release/
    3. Package bin/ directory
    4. Fallback to development path (even if not found, for error messages)

    Returns:
        Path to the binary (may not exist if not found)
    """
    # 0. Environment variable override (useful for testing and custom deployments)
    env_binary = os.environ.get("PARSER_BINARY")
    if env_binary:
        return Path(env_binary)

    system = platform.system().lower()
    machine = platform.machine().lower()

    # Binary name varies by platform. We support both the platform-suffixed
    # names (preferred) and the legacy unsuffixed name "stellaris-parser"
    # (defense-in-depth for local builds / older bundles).
    if system == "windows":
        binary_candidates = ["stellaris-parser.exe"]
    elif system == "darwin":
        if "arm" in machine or machine == "aarch64":
            binary_candidates = ["stellaris-parser-darwin-arm64", "stellaris-parser"]
        else:
            binary_candidates = ["stellaris-parser-darwin-x64", "stellaris-parser"]
    elif system == "linux":
        if machine in {"x86_64", "amd64"}:
            binary_candidates = ["stellaris-parser-linux-x64", "stellaris-parser"]
        elif machine in {"aarch64", "arm64"}:
            binary_candidates = ["stellaris-parser-linux-arm64", "stellaris-parser"]
        else:
            binary_candidates = ["stellaris-parser"]
    else:
        binary_candidates = ["stellaris-parser"]

    # 1. Electron packaged app detection
    # When running as a PyInstaller bundle inside Electron, sys.frozen is set
    # and the executable is at: resources/python-backend/stellaris-backend
    # The Rust parser is at: resources/rust-parser/<binary_name>
    if getattr(sys, "frozen", False):
        # Running as a PyInstaller bundle
        # sys.executable points to the bundled executable
        # e.g., /path/to/resources/python-backend/stellaris-backend
        executable_path = Path(sys.executable)
        resources_path = executable_path.parent.parent  # Go up from python-backend/
        for binary_name in binary_candidates:
            electron_parser_path = resources_path / "rust-parser" / binary_name
            if electron_parser_path.exists():
                return electron_parser_path

    # 2. Development location (most common during development)
    base = get_repo_root(Path(__file__))
    dev_path = base / "stellaris-parser" / "target" / "release" / "stellaris-parser"
    if system == "windows":
        dev_path = dev_path.with_suffix(".exe")
    if dev_path.exists():
        return dev_path

    # 3. Package bin/ directory
    for binary_name in binary_candidates:
        bin_path = base / "bin" / binary_name
        if bin_path.exists():
            return bin_path

    # 4. Fallback to development path (even if not found, for error messages)
    return dev_path


PARSER_BINARY = _get_binary_path()


class ParserError(Exception):
    """Error from Rust parser.

    Attributes:
        message: Human-readable error description
        line: Line number where error occurred (if available)
        col: Column number where error occurred (if available)
        exit_code: Process exit code (1=file not found, 2=parse error, 3=invalid args)
    """

    def __init__(
        self,
        message: str,
        line: int | None = None,
        col: int | None = None,
        exit_code: int | None = None,
    ):
        self.line = line
        self.col = col
        self.exit_code = exit_code
        super().__init__(message)


# Thread-local storage for session context
_tls = threading.local()


class RustSession:
    """Session-mode connection to Rust parser.

    Keeps a persistent subprocess with parsed save data in memory.
    All queries reuse the same parsed data without re-parsing.

    Usage:
        with RustSession("save.sav") as sess:
            data = sess.extract_sections(["meta", "player"])
            for key, country in sess.iter_section("country"):
                print(country["name"])
    """

    def __init__(self, save_path: str | Path, timeout: float = 30.0):
        """Start a session with a save file.

        Args:
            save_path: Path to the .sav file
            timeout: Timeout in seconds for receiving responses (default: 30)
        """
        self._save_path = Path(save_path)
        self._timeout = timeout
        self._proc: subprocess.Popen | None = None
        self._response_queue: queue.Queue = queue.Queue()
        self._reader_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._stderr_lines: deque[str] = deque(maxlen=200)
        self._closed = False
        self._in_stream = False  # Track if we're in a stream (iter_section)

        # Start the session process
        self._start()

    def _start(self):
        """Start the serve subprocess."""
        binary_path = _get_binary_path()
        if not binary_path.exists():
            _raise_parser_binary_not_found(binary_path)

        if not self._save_path.exists():
            raise FileNotFoundError(f"Save file not found: {self._save_path}")

        self._proc = subprocess.Popen(
            [str(binary_path), "serve", "--path", str(self._save_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Start a reader thread to handle stdout asynchronously
        # This prevents deadlocks on Windows and allows timeouts
        self._reader_thread = threading.Thread(
            target=self._reader_loop, daemon=True, name="RustSession-reader"
        )
        self._reader_thread.start()

        # Drain stderr to avoid deadlocks if the Rust process logs heavily.
        self._stderr_thread = threading.Thread(
            target=self._stderr_loop, daemon=True, name="RustSession-stderr"
        )
        self._stderr_thread.start()

        # Register cleanup on interpreter exit
        atexit.register(self._cleanup)

    def _reader_loop(self):
        """Background thread that reads stdout lines into a queue."""
        try:
            for line in self._proc.stdout:
                if line:
                    self._response_queue.put(line)
            # EOF reached
            self._response_queue.put(None)
        except Exception as e:
            self._response_queue.put(e)

    def _stderr_loop(self):
        """Background thread that drains stderr to avoid subprocess deadlocks.

        The Rust parser logs status to stderr; if stderr isn't drained, the
        subprocess can block once the pipe buffer fills.
        """
        try:
            if self._proc is None or self._proc.stderr is None:
                return
            for line in self._proc.stderr:
                if not line:
                    break
                self._stderr_lines.append(line.decode(errors="replace").rstrip())
        except Exception as e:
            self._stderr_lines.append(f"[stderr-reader] {e!r}")

    def _drain_stream(self) -> None:
        """Drain any remaining stream entries from a previous iter_section call.

        This is necessary when a caller breaks out of iter_section early,
        leaving unread entries in the queue.
        """
        if not self._in_stream:
            return

        # Read until we see the done marker
        while True:
            try:
                item = self._response_queue.get(timeout=self._timeout)
            except queue.Empty:
                # Timeout - assume stream ended badly
                break

            if item is None or isinstance(item, Exception):
                break

            try:
                response = _json_loads(item)
                if response.get("done"):
                    break
            except (ValueError, TypeError):
                # orjson raises ValueError, json raises JSONDecodeError (subclass of ValueError)
                break

        self._in_stream = False

    def _send(self, request: dict) -> None:
        """Send a JSON request to the subprocess."""
        if self._closed or self._proc is None or self._proc.poll() is not None:
            exit_code = self._proc.poll() if self._proc is not None else None
            tail = "\n".join(list(self._stderr_lines)[-20:])
            msg = "Session is closed or crashed"
            if exit_code is not None:
                msg += f" (exit_code={exit_code})"
            if tail:
                msg += f"\n[stderr tail]\n{tail}"
            raise ParserError(msg, exit_code=exit_code)

        # Drain any leftover stream entries from a previous iter_section
        self._drain_stream()

        try:
            data = _json_dumps(request) + b"\n"
            self._proc.stdin.write(data)
            self._proc.stdin.flush()
        except BrokenPipeError:
            raise ParserError("Session crashed unexpectedly")

    def _recv(self, *, timeout: float | None = None) -> dict:
        """Receive a JSON response from the subprocess with timeout."""
        effective_timeout = self._timeout if timeout is None else timeout
        try:
            item = self._response_queue.get(timeout=effective_timeout)
        except queue.Empty:
            exit_code = self._proc.poll() if self._proc is not None else None
            tail = "\n".join(list(self._stderr_lines)[-20:])
            msg = f"Session timed out after {effective_timeout}s"
            if exit_code is not None:
                msg += f" (exit_code={exit_code})"
            if tail:
                msg += f"\n[stderr tail]\n{tail}"
            raise ParserError(msg, exit_code=exit_code)

        if item is None:
            exit_code = self._proc.poll() if self._proc is not None else None
            tail = "\n".join(list(self._stderr_lines)[-20:])
            msg = "Session ended unexpectedly (EOF)"
            if exit_code is not None:
                msg += f" (exit_code={exit_code})"
            if tail:
                msg += f"\n[stderr tail]\n{tail}"
            raise ParserError(msg, exit_code=exit_code)
        if isinstance(item, Exception):
            raise ParserError(f"Session reader error: {item}")

        response = _json_loads(item)
        if not response.get("ok", False):
            raise ParserError(
                message=response.get("message", "Unknown error"),
                line=response.get("line"),
                col=response.get("col"),
                exit_code=response.get("exit_code"),
            )
        return response

    def extract_sections(self, sections: list[str]) -> dict:
        """Extract specific sections from the parsed save.

        Args:
            sections: List of section names (e.g., ["meta", "player"])

        Returns:
            Dict with section names as keys, parsed content as values.
        """
        self._send({"op": "extract_sections", "sections": sections})
        response = self._recv()
        return response.get("data", {})

    def iter_section(
        self,
        section: str,
        batch_size: int = 100,
        *,
        timeout: float | None = None,
    ) -> Iterator[tuple[str, dict]]:
        """Stream entries from a section.

        Args:
            section: Section name (e.g., "country", "fleet")
            batch_size: Number of entries per batch (default: 100).
                       Use 1 for single-entry mode (backward compatible).
            timeout: Optional per-frame receive timeout override (seconds).
                     Useful for very large entries (e.g., wars with huge battle logs).

        Yields:
            Tuples of (key, value) for each entry

        Note:
            If you break out of the iterator early, remaining entries will be
            automatically drained before the next request.
        """
        # Drain any leftover stream from a previous iter_section (prevents nested stream corruption)
        self._drain_stream()

        self._send({"op": "iter_section", "section": section, "batch_size": batch_size})

        # First frame: stream header
        header = self._recv(timeout=timeout)
        if not header.get("stream"):
            raise ParserError("Expected stream header from iter_section")

        # Mark that we're in a stream (for drain logic)
        self._in_stream = True

        # Read entry frames until done
        # Handle both single entry and batched formats
        while True:
            frame = self._recv(timeout=timeout)
            if frame.get("done"):
                self._in_stream = False
                return
            # Handle batched format: {"entries": [...]}
            if "entries" in frame:
                for entry in frame["entries"]:
                    yield entry.get("key", ""), entry.get("value", {})
            # Handle single entry format: {"entry": {...}}
            elif "entry" in frame:
                entry = frame["entry"]
                yield entry.get("key", ""), entry.get("value", {})

    def get_entry(self, section: str, key: str) -> dict | None:
        """Fetch a single entry by section and key ID.

        This is more efficient than iter_section when you know the exact
        entry you need, as it avoids iterating over the entire section.

        Args:
            section: Section name (e.g., "country", "fleet")
            key: Entry ID/key (e.g., "0", "12345")

        Returns:
            The entry dict if found, None if not found.
            Note: Entry might be the string "none" for deleted entries,
            so always check isinstance(result, dict) before use.

        Example:
            >>> sess.get_entry("country", "0")
            {"name": "UNE", "type": "default", ...}
        """
        self._send({"op": "get_entry", "section": section, "key": key})
        response = self._recv()
        if response.get("found", False):
            return response.get("entry")
        return None

    def get_entries(
        self, section: str, keys: list[str], fields: list[str] | None = None
    ) -> list[dict]:
        """Batch fetch multiple entries by section and keys with optional field projection.

        This is more efficient than multiple get_entry calls or iter_section when
        you know the exact entries you need (e.g., fetching owned fleets by ID).

        Args:
            section: Section name (e.g., "country", "fleet")
            keys: List of entry IDs/keys (e.g., ["0", "1", "2"])
            fields: Optional list of field names to extract (projection).
                   If None, returns full entries with _key and _value.
                   If specified, returns entries with _key plus only those fields.

        Returns:
            List of entry dicts. Each entry contains:
            - With projection: {"_key": "id", "field1": value, "field2": value, ...}
            - Without projection: {"_key": "id", "_value": <full entry>}

            Note: Keys that don't exist are silently skipped.
            Entry values might be the string "none" for deleted entries.

        Example:
            >>> sess.get_entries("country", ["0", "1", "2"])
            [{"_key": "0", "_value": {...}}, {"_key": "1", "_value": {...}}, ...]

            >>> sess.get_entries("country", ["0"], fields=["name", "type"])
            [{"_key": "0", "name": "UNE", "type": "default"}]
        """
        request = {"op": "get_entries", "section": section, "keys": keys}
        if fields is not None:
            request["fields"] = fields
        self._send(request)
        response = self._recv()
        return response.get("entries", [])

    def count_keys(self, keys: list[str]) -> dict:
        """Count occurrences of specific keys throughout the parsed save.

        Traverses the entire parsed JSON tree and counts how many times
        each specified key appears. Useful for checking flags, crisis systems, etc.

        Args:
            keys: List of key names to count (e.g., ["prethoryn_system", "contingency_system"])

        Returns:
            Dict with "counts" key containing a mapping of key -> count.
            Example: {"counts": {"prethoryn_system": 5, "contingency_system": 0}}
        """
        self._send({"op": "count_keys", "keys": keys})
        response = self._recv()
        return response

    def contains_tokens(self, tokens: list[str]) -> dict:
        """Check if specific tokens appear anywhere in the raw gamestate bytes.

        Uses Aho-Corasick algorithm for efficient multi-pattern matching.
        This is faster than regex for simple "does string exist" checks.

        Args:
            tokens: List of tokens to search for (e.g., ["killed_dragon", "ether_drake_killed"])

        Returns:
            Dict with "matches" key containing a mapping of token -> bool.
            Example: {"matches": {"killed_dragon": true, "ether_drake_killed": false}}
        """
        self._send({"op": "contains_tokens", "tokens": tokens})
        response = self._recv()
        return response

    def contains_kv(self, pairs: list[tuple[str, str]]) -> dict:
        """Check if specific key=value pairs exist anywhere in the parsed gamestate.

        This is whitespace-insensitive, handling both 'key=value' and 'key = value'
        formatting variations. It traverses the parsed JSON tree, so it's more
        accurate than regex for structured data like booleans and nested keys.

        Args:
            pairs: List of (key, value) tuples to search for.
                   Example: [("war_in_heaven", "yes"), ("version", "3")]

        Returns:
            Dict with "matches" key containing a mapping of "key=value" -> bool.
            Example: {"matches": {"war_in_heaven=yes": true, "version=3": false}}

        Note:
            - Boolean values in Stellaris saves are stored as "yes"/"no" strings
            - Numeric values are compared as strings
            - This searches the entire parsed tree, not just top-level keys
        """
        self._send({"op": "contains_kv", "pairs": pairs})
        response = self._recv()
        return response

    def get_country_summaries(self, fields: list[str]) -> dict:
        """Get lightweight country projections with only the requested fields.

        Returns a list of country summaries containing only the specified fields,
        which is much more efficient than iterating over the full country section
        when you only need a few fields.

        Args:
            fields: List of field names to extract (e.g., ["name", "type", "flag", "ruler"])

        Returns:
            Dict with "countries" key containing a list of country objects.
            Each country has an "id" field plus the requested fields.
            Example: {"countries": [{"id": "0", "name": "UNE", "type": "default"}, ...]}
        """
        self._send({"op": "get_country_summaries", "fields": fields})
        response = self._recv()
        return response

    def get_duplicate_values(self, section: str, key: str, field: str) -> list[str]:
        """Extract all values for a field that has duplicate keys in Clausewitz format.

        Stellaris save files use duplicate keys for list-like structures (e.g.,
        `traits="x"` appearing multiple times for a leader). The standard JSON-style
        parser only keeps the last value. This method scans the raw bytes to extract
        ALL values for the specified field.

        Args:
            section: Section name (e.g., "leaders", "species_db")
            key: Entry ID/key within the section (e.g., "123" for leader ID)
            field: Field name that has duplicate values (e.g., "traits")

        Returns:
            List of all values for that field. Empty list if entry not found
            or field has no values.

        Example:
            >>> sess.get_duplicate_values("leaders", "12345", "traits")
            ["leader_trait_resilient", "leader_trait_carefree", "leader_trait_spark_of_genius"]

        Note:
            This is specifically for fields with duplicate keys in Clausewitz format.
            For normal fields, use get_entry() instead.
        """
        self._send(
            {
                "op": "get_duplicate_values",
                "section": section,
                "key": key,
                "field": field,
            }
        )
        response = self._recv()
        return response.get("values", [])

    def get_entry_text(self, section: str, key: str) -> str | None:
        """Get raw Clausewitz text for a single entry.

        This is useful when you need to parse duplicate keys (like relation={})
        that can't be represented in JSON. Instead of searching the entire gamestate
        in Python, this returns just the entry's raw text for targeted regex parsing.

        Args:
            section: Section name (e.g., "country")
            key: Entry ID/key within the section (e.g., "0" for player country)

        Returns:
            Raw Clausewitz text for the entry, or None if not found.

        Example:
            >>> text = sess.get_entry_text("country", "0")
            >>> # text contains the raw ~500KB country block
            >>> # Now parse with regex for duplicate relation={} blocks
        """
        self._send(
            {
                "op": "get_entry_text",
                "section": section,
                "key": key,
            }
        )
        response = self._recv()
        if response.get("found"):
            return response.get("text", "")
        return None

    def batch_ops(self, ops: list[dict]) -> list[dict]:
        """Execute multiple operations in a single request to reduce IPC overhead.

        This is useful when you need to make many small queries (e.g., get_entry,
        count_keys) and want to avoid the round-trip latency for each one.

        Args:
            ops: List of operation dicts, each with an "op" key and operation-specific
                 parameters. Supported operations:
                 - {"op": "extract_sections", "sections": [...]}
                 - {"op": "get_entry", "section": "...", "key": "..."}
                 - {"op": "get_entries", "section": "...", "keys": [...], "fields": [...]}
                 - {"op": "count_keys", "keys": [...]}
                 - {"op": "contains_tokens", "tokens": [...]}
                 - {"op": "contains_kv", "pairs": [[key, value], ...]}
                 - {"op": "get_country_summaries", "fields": [...]}
                 - {"op": "get_duplicate_values", "section": "...", "key": "...", "field": "..."}
                 - {"op": "get_entry_text", "section": "...", "key": "..."}

                 Note: iter_section and close are NOT supported in batch mode.

        Returns:
            List of result dicts, one per operation in the same order as input.
            Each result contains the same data as the corresponding single operation
            would return (e.g., {"entry": ..., "found": true} for get_entry).

        Example:
            >>> results = sess.batch_ops([
            ...     {"op": "get_entry", "section": "country", "key": "0"},
            ...     {"op": "get_entry", "section": "country", "key": "1"},
            ...     {"op": "count_keys", "keys": ["name", "type"]}
            ... ])
            >>> country_0 = results[0]["entry"]
            >>> country_1 = results[1]["entry"]
            >>> name_count = results[2]["counts"]["name"]

        Performance:
            Sending N operations as a batch is significantly faster than N individual
            calls, especially for small operations like get_entry. The speedup comes
            from eliminating IPC round-trip latency (typically 1-5ms per call).
        """
        if not ops:
            return []

        self._send({"op": "multi", "ops": ops})
        response = self._recv()
        return response.get("results", [])

    def close(self):
        """Close the session and terminate the subprocess."""
        if self._closed:
            return
        self._closed = True

        try:
            if self._proc and self._proc.poll() is None:
                self._send({"op": "close"})
                self._proc.wait(timeout=5)
        except Exception:
            pass
        finally:
            self._cleanup()

    def _cleanup(self):
        """Forcefully clean up subprocess if still running."""
        with suppress(Exception):
            atexit.unregister(self._cleanup)

        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._proc.kill()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


@contextmanager
def session(save_path: str | Path):
    """Context manager for session-mode parsing.

    All extract_sections() and iter_section_entries() calls within this
    context will automatically use the session, avoiding re-parsing.

    Args:
        save_path: Path to the .sav file

    Yields:
        RustSession instance

    Example:
        with session("save.sav"):
            # These calls reuse the same parsed data:
            meta = extract_sections("save.sav", ["meta"])
            for key, country in iter_section_entries("save.sav", "country"):
                ...
    """
    sess = RustSession(save_path)
    prev = getattr(_tls, "session", None)
    _tls.session = sess
    try:
        yield sess
    finally:
        _tls.session = prev
        sess.close()


def _get_active_session() -> RustSession | None:
    """Get the current thread-local session if any."""
    return getattr(_tls, "session", None)


def _parse_error(stderr: bytes, exit_code: int | None = None) -> dict:
    """Parse error info from stderr.

    The Rust binary outputs JSON errors to stderr:
    {"schema_version":1,"tool_version":"0.1.0","error":"ErrorType","message":"...","line":123,"col":45}

    Args:
        stderr: Raw stderr bytes from subprocess
        exit_code: Process exit code for context

    Returns:
        Dict with keys: message, line, col, exit_code
    """
    try:
        err = _json_loads(stderr)
        return {
            "message": err.get("message") or err.get("error", "Unknown error"),
            "line": err.get("line"),
            "col": err.get("col"),
            "exit_code": exit_code,
        }
    except (ValueError, TypeError):
        # orjson raises ValueError, json raises JSONDecodeError (subclass of ValueError)
        # Fallback for non-JSON error output
        return {
            "message": stderr.decode(errors="replace").strip() or "Unknown error",
            "line": None,
            "col": None,
            "exit_code": exit_code,
        }


def extract_sections(save_path: str | Path, sections: list[str]) -> dict:
    """Extract specific sections from a save file as parsed JSON.

    If called within a session() context, uses the session's cached parsed data.
    Otherwise, spawns a new subprocess for this call.

    Args:
        save_path: Path to .sav file (recommended) or extracted gamestate (debug only)
        sections: List of section names (e.g., ["galaxy", "species_db", "meta"])

    Returns:
        Dict with section names as keys, parsed content as values.
        Also includes schema_version, tool_version, and game fields.

    Raises:
        ParserError: If parsing fails
        FileNotFoundError: If binary or save file not found

    Example:
        >>> data = extract_sections("save.sav", ["meta", "galaxy"])
        >>> print(data["meta"]["date"])
        "2431.02.18"
    """
    # Use active session if available
    sess = _get_active_session()
    if sess is not None:
        return sess.extract_sections(list(sections))

    # Fallback to spawn-per-call
    return _spawn_extract_sections(save_path, sections)


def _spawn_extract_sections(save_path: str | Path, sections: list[str]) -> dict:
    """Spawn a subprocess to extract sections (original implementation)."""
    binary_path = _get_binary_path()
    if not binary_path.exists():
        _raise_parser_binary_not_found(binary_path)

    save_path = Path(save_path)
    if not save_path.exists():
        raise FileNotFoundError(f"Save file not found: {save_path}")

    result = subprocess.run(
        [
            str(binary_path),
            "extract-save",
            str(save_path),
            "--sections",
            ",".join(sections),
            "--schema-version",
            "1",
            "--output",
            "-",
        ],
        capture_output=True,
        timeout=60,
    )

    if result.returncode != 0:
        error_info = _parse_error(result.stderr, result.returncode)
        raise ParserError(**error_info)

    return _json_loads(result.stdout)


def iter_section_entries(save_path: str | Path, section: str) -> Iterator[tuple[str, dict]]:
    """Stream entries from a large section without loading all into memory.

    If called within a session() context, uses the session's cached parsed data.
    Otherwise, spawns a new subprocess for this call.

    This is ideal for large sections like country, ships, or pops that would
    be too large to load entirely into memory.

    Args:
        save_path: Path to .sav file (recommended) or extracted gamestate (debug only)
        section: Section name (e.g., "country", "ships", "pops")

    Yields:
        Tuples of (key, value) for each entry in the section

    Raises:
        ParserError: If parsing fails
        FileNotFoundError: If binary or save file not found

    Example:
        >>> for key, country in iter_section_entries("save.sav", "country"):
        ...     print(f"Country {key}: {country.get('name', 'Unknown')}")
    """
    # Use active session if available
    sess = _get_active_session()
    if sess is not None:
        yield from sess.iter_section(section)
        return

    # Fallback to spawn-per-call
    yield from _spawn_iter_section_entries(save_path, section)


def _spawn_iter_section_entries(save_path: str | Path, section: str) -> Iterator[tuple[str, dict]]:
    """Spawn a subprocess to iterate section entries (original implementation)."""
    binary_path = _get_binary_path()
    if not binary_path.exists():
        _raise_parser_binary_not_found(binary_path)

    save_path = Path(save_path)
    if not save_path.exists():
        raise FileNotFoundError(f"Save file not found: {save_path}")

    proc = subprocess.Popen(
        [
            str(binary_path),
            "iter-save",
            str(save_path),
            "--section",
            section,
            "--schema-version",
            "1",
            "--format",
            "jsonl",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    for line in proc.stdout:
        if line.strip():
            entry = _json_loads(line)
            yield entry["key"], entry["value"]

    proc.wait()
    if proc.returncode != 0:
        error_info = _parse_error(proc.stderr.read(), proc.returncode)
        raise ParserError(**error_info)
