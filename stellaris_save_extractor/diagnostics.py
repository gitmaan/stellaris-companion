"""Diagnostics export module for Stellaris save extractor.

Provides functions to collect and export diagnostic information about
the save extractor's operation without including any save file data.

Captures:
- Python version
- Rust parser version
- Which extractors used fallback (regex vs Rust)
- Any errors/warnings
- Timing breakdown

Privacy: No save data is included in diagnostics exports.
"""

from __future__ import annotations

import logging
import platform
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

logger = logging.getLogger(__name__)

# Thread-local storage for diagnostics collection
_diagnostics_tls = threading.local()


@dataclass
class ExtractorTiming:
    """Timing information for a single extractor call."""

    name: str
    duration_ms: float
    used_rust: bool
    fallback_reason: str | None = None


@dataclass
class DiagnosticsCollector:
    """Collects diagnostic information during a save extraction session.

    Thread-local singleton that tracks fallbacks, errors, and timing
    for diagnostic reporting.
    """

    # Version information
    python_version: str = field(default_factory=lambda: sys.version)
    platform_info: str = field(default_factory=lambda: platform.platform())
    rust_parser_version: str | None = None
    rust_schema_version: int | None = None

    # Fallback tracking
    fallbacks: list[dict[str, Any]] = field(default_factory=list)

    # Error tracking
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)

    # Timing breakdown
    timings: list[ExtractorTiming] = field(default_factory=list)
    session_start: float | None = None
    session_end: float | None = None

    # Session info
    session_active: bool = False
    rust_bridge_available: bool = False
    orjson_available: bool = False

    def start_session(self) -> None:
        """Mark the start of a diagnostics collection session."""
        self.session_start = time.time()
        self.session_active = True
        self._detect_capabilities()

    def end_session(self) -> None:
        """Mark the end of a diagnostics collection session."""
        self.session_end = time.time()
        self.session_active = False

    def _detect_capabilities(self) -> None:
        """Detect available capabilities (Rust bridge, orjson, etc.)."""
        try:
            from rust_bridge import _ORJSON_AVAILABLE, PARSER_BINARY

            self.rust_bridge_available = PARSER_BINARY.exists()
            self.orjson_available = _ORJSON_AVAILABLE
        except ImportError:
            self.rust_bridge_available = False
            self.orjson_available = False

    def record_fallback(
        self,
        extractor_name: str,
        reason: str,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Record when an extractor falls back from Rust to regex.

        Args:
            extractor_name: Name of the extractor method
            reason: Why fallback occurred (e.g., "ParserError", "no_session")
            error_type: Type of error if applicable
            error_message: Error message if applicable
        """
        self.fallbacks.append(
            {
                "extractor": extractor_name,
                "reason": reason,
                "error_type": error_type,
                "error_message": error_message,
                "timestamp": time.time(),
            }
        )

    def record_error(
        self,
        context: str,
        error_type: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Record an error that occurred during extraction.

        Args:
            context: Where the error occurred (e.g., method name)
            error_type: Type of error (e.g., "ParserError", "ValueError")
            message: Error message
            details: Additional details (no save data!)
        """
        self.errors.append(
            {
                "context": context,
                "error_type": error_type,
                "message": message,
                "details": details or {},
                "timestamp": time.time(),
            }
        )

    def record_warning(
        self,
        context: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Record a warning that occurred during extraction.

        Args:
            context: Where the warning occurred
            message: Warning message
            details: Additional details (no save data!)
        """
        self.warnings.append(
            {
                "context": context,
                "message": message,
                "details": details or {},
                "timestamp": time.time(),
            }
        )

    def record_timing(
        self,
        name: str,
        duration_ms: float,
        used_rust: bool,
        fallback_reason: str | None = None,
    ) -> None:
        """Record timing information for an extractor.

        Args:
            name: Extractor method name
            duration_ms: Duration in milliseconds
            used_rust: Whether Rust path was used
            fallback_reason: If not using Rust, why
        """
        self.timings.append(
            ExtractorTiming(
                name=name,
                duration_ms=duration_ms,
                used_rust=used_rust,
                fallback_reason=fallback_reason,
            )
        )

    def set_rust_version(self, version: str, schema_version: int) -> None:
        """Set the Rust parser version info (from extract_sections response).

        Args:
            version: Tool version string (e.g., "0.1.0")
            schema_version: Schema version number
        """
        self.rust_parser_version = version
        self.rust_schema_version = schema_version


def get_collector() -> DiagnosticsCollector:
    """Get the thread-local diagnostics collector, creating if needed."""
    if not hasattr(_diagnostics_tls, "collector"):
        _diagnostics_tls.collector = DiagnosticsCollector()
    return _diagnostics_tls.collector


def reset_collector() -> None:
    """Reset the diagnostics collector for a new session."""
    _diagnostics_tls.collector = DiagnosticsCollector()


def get_diagnostics() -> dict[str, Any]:
    """Get current diagnostics as a dictionary.

    Returns a snapshot of all collected diagnostic information.
    This is safe to export as it contains no save data.

    Returns:
        Dict containing:
        - versions: Python, Rust parser, schema versions
        - capabilities: What's available (Rust bridge, orjson)
        - fallbacks: List of fallback events
        - errors: List of errors
        - warnings: List of warnings
        - timing: Timing breakdown and totals
    """
    collector = get_collector()

    # Calculate timing totals
    total_rust_ms = sum(t.duration_ms for t in collector.timings if t.used_rust)
    total_regex_ms = sum(t.duration_ms for t in collector.timings if not t.used_rust)
    session_duration_ms = None
    if collector.session_start and collector.session_end:
        session_duration_ms = (collector.session_end - collector.session_start) * 1000

    return {
        "versions": {
            "python": collector.python_version,
            "python_version_info": list(sys.version_info[:3]),
            "platform": collector.platform_info,
            "rust_parser": collector.rust_parser_version,
            "rust_schema": collector.rust_schema_version,
        },
        "capabilities": {
            "rust_bridge_available": collector.rust_bridge_available,
            "orjson_available": collector.orjson_available,
            "session_active": collector.session_active,
        },
        "fallbacks": collector.fallbacks,
        "fallback_count": len(collector.fallbacks),
        "fallback_extractors": list(set(f["extractor"] for f in collector.fallbacks)),
        "errors": collector.errors,
        "error_count": len(collector.errors),
        "warnings": collector.warnings,
        "warning_count": len(collector.warnings),
        "timing": {
            "session_duration_ms": session_duration_ms,
            "total_rust_ms": total_rust_ms,
            "total_regex_ms": total_regex_ms,
            "extractor_count": len(collector.timings),
            "rust_extractor_count": sum(1 for t in collector.timings if t.used_rust),
            "regex_extractor_count": sum(1 for t in collector.timings if not t.used_rust),
            "breakdown": [
                {
                    "name": t.name,
                    "duration_ms": t.duration_ms,
                    "used_rust": t.used_rust,
                    "fallback_reason": t.fallback_reason,
                }
                for t in collector.timings
            ],
        },
    }


def export_diagnostics(filepath: str | None = None) -> str:
    """Export diagnostics to JSON format.

    Args:
        filepath: Optional path to write JSON file. If None, returns JSON string.

    Returns:
        JSON string of diagnostics data.

    Example:
        # Get as string
        json_str = export_diagnostics()

        # Write to file
        export_diagnostics("/tmp/stellaris_diagnostics.json")
    """
    import json

    diagnostics = get_diagnostics()

    # Add export metadata
    diagnostics["export_timestamp"] = time.time()
    diagnostics["export_info"] = {
        "note": "This file contains diagnostic information only. No save game data is included.",
        "purpose": "Troubleshooting and performance analysis for Stellaris save extractor.",
    }

    json_str = json.dumps(diagnostics, indent=2, default=str)

    if filepath:
        with open(filepath, "w") as f:
            f.write(json_str)
        logger.info(f"Diagnostics exported to {filepath}")

    return json_str


# Convenience decorators for instrumenting extractors


class timed_extractor:
    """Decorator to time an extractor method and record diagnostics.

    Example:
        @timed_extractor("get_leaders")
        def get_leaders(self):
            ...
    """

    def __init__(self, name: str):
        self.name = name

    def __call__(self, func):
        def wrapper(*args, **kwargs):
            collector = get_collector()
            start = time.time()
            used_rust = False
            fallback_reason = None

            try:
                # Check if session is active to determine if Rust path is used
                try:
                    from rust_bridge import _get_active_session

                    if _get_active_session() is not None:
                        used_rust = True
                except ImportError:
                    fallback_reason = "rust_bridge_unavailable"

                result = func(*args, **kwargs)
                return result
            finally:
                duration_ms = (time.time() - start) * 1000
                collector.record_timing(
                    name=self.name,
                    duration_ms=duration_ms,
                    used_rust=used_rust,
                    fallback_reason=fallback_reason,
                )

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper


def record_fallback_on_exception(extractor_name: str):
    """Decorator to automatically record fallbacks when exceptions occur.

    Use this on the Rust-path method to record when it falls back to regex.

    Example:
        @record_fallback_on_exception("get_leaders")
        def _get_leaders_rust(self):
            ...
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                collector = get_collector()
                collector.record_fallback(
                    extractor_name=extractor_name,
                    reason="exception",
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
                raise

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper

    return decorator
