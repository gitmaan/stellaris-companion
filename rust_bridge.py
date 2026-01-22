"""Bridge to Rust Clausewitz parser.

This module provides Python bindings to the stellaris-parser Rust binary.
It handles subprocess communication, JSON parsing, and error handling.

The Rust binary can be located in multiple places (in order of priority):
0. PARSER_BINARY environment variable (for testing/override)
1. Electron packaged app: rust-parser/ in Electron resources folder
2. Development: stellaris-parser/target/release/stellaris-parser
3. Packaged: bin/ directory relative to this file
4. System: PATH-accessible stellaris-parser binary
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Iterator


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

    # Binary name varies by platform
    if system == "windows":
        binary_name = "stellaris-parser.exe"
    elif system == "darwin":
        if "arm" in machine or machine == "aarch64":
            binary_name = "stellaris-parser-darwin-arm64"
        else:
            binary_name = "stellaris-parser-darwin-x64"
    else:
        binary_name = "stellaris-parser-linux-x64"

    # 1. Electron packaged app detection
    # When running as a PyInstaller bundle inside Electron, sys.frozen is set
    # and the executable is at: resources/python-backend/stellaris-backend
    # The Rust parser is at: resources/rust-parser/<binary_name>
    if getattr(sys, 'frozen', False):
        # Running as a PyInstaller bundle
        # sys.executable points to the bundled executable
        # e.g., /path/to/resources/python-backend/stellaris-backend
        executable_path = Path(sys.executable)
        resources_path = executable_path.parent.parent  # Go up from python-backend/
        electron_parser_path = resources_path / "rust-parser" / binary_name
        if electron_parser_path.exists():
            return electron_parser_path

    # 2. Development location (most common during development)
    base = Path(__file__).parent
    dev_path = base / "stellaris-parser" / "target" / "release" / "stellaris-parser"
    if system == "windows":
        dev_path = dev_path.with_suffix(".exe")
    if dev_path.exists():
        return dev_path

    # 3. Package bin/ directory
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
        err = json.loads(stderr)
        return {
            "message": err.get("message") or err.get("error", "Unknown error"),
            "line": err.get("line"),
            "col": err.get("col"),
            "exit_code": exit_code,
        }
    except json.JSONDecodeError:
        # Fallback for non-JSON error output
        return {
            "message": stderr.decode(errors="replace").strip() or "Unknown error",
            "line": None,
            "col": None,
            "exit_code": exit_code,
        }


def extract_sections(save_path: str | Path, sections: list[str]) -> dict:
    """Extract specific sections from a save file as parsed JSON.

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
    binary_path = _get_binary_path()
    if not binary_path.exists():
        raise FileNotFoundError(f"Parser binary not found: {binary_path}")

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

    return json.loads(result.stdout)


def iter_section_entries(
    save_path: str | Path, section: str
) -> Iterator[tuple[str, dict]]:
    """Stream entries from a large section without loading all into memory.

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
    binary_path = _get_binary_path()
    if not binary_path.exists():
        raise FileNotFoundError(f"Parser binary not found: {binary_path}")

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
            entry = json.loads(line)
            yield entry["key"], entry["value"]

    proc.wait()
    if proc.returncode != 0:
        error_info = _parse_error(proc.stderr.read(), proc.returncode)
        raise ParserError(**error_info)
