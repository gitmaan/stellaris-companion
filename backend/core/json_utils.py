"""JSON utilities with orjson optimization.

Provides a drop-in replacement for json.dumps() that uses orjson when available,
falling back to stdlib json. orjson is ~3x faster for serialization.

Usage:
    from backend.core.json_utils import json_dumps

    # Drop-in replacement for json.dumps()
    json_str = json_dumps(data)
    json_str = json_dumps(data, indent=2)
    json_str = json_dumps(data, default=str)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# Use orjson for faster JSON serialization (~3x faster than stdlib json)
try:
    import orjson

    _ORJSON_AVAILABLE = True

    def json_dumps(
        obj: Any,
        *,
        default: Callable[[Any], Any] | None = None,
        indent: int | None = None,
        ensure_ascii: bool = False,  # Ignored - orjson always outputs UTF-8
        separators: tuple[str, str] | None = None,  # Ignored - orjson uses compact format
    ) -> str:
        """Serialize obj to a JSON string using orjson.

        Args:
            obj: Object to serialize
            default: Function for objects that can't be serialized (e.g., default=str)
            indent: If 2, pretty-print with 2-space indent. Other values ignored.
            ensure_ascii: Ignored (orjson always outputs UTF-8)
            separators: Ignored (orjson uses compact format by default)

        Returns:
            JSON string
        """
        option = 0
        if indent == 2:
            option |= orjson.OPT_INDENT_2

        return orjson.dumps(obj, default=default, option=option).decode("utf-8")

except ImportError:
    import json

    _ORJSON_AVAILABLE = False

    def json_dumps(
        obj: Any,
        *,
        default: Callable[[Any], Any] | None = None,
        indent: int | None = None,
        ensure_ascii: bool = False,
        separators: tuple[str, str] | None = None,
    ) -> str:
        """Serialize obj to a JSON string using stdlib json.

        Fallback when orjson is not available.
        """
        if separators is None:
            separators = (",", ":")
        return json.dumps(
            obj,
            default=default,
            indent=indent,
            ensure_ascii=ensure_ascii,
            separators=separators,
        )


def is_orjson_available() -> bool:
    """Check if orjson is being used."""
    return _ORJSON_AVAILABLE
