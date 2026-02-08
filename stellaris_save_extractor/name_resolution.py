from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

NameSource = Literal["missing", "literal", "template", "localization_key", "fallback"]
NameContext = Literal["generic", "planet", "country", "species", "fleet"]


@dataclass(frozen=True, slots=True)
class ResolvedName:
    """Structured name resolution result.

    - display: Human-readable string suitable for UI/LLM.
    - raw_key: Original localization key (if applicable).
    - source: Where the display name came from.
    - confidence: Heuristic confidence in [0.0, 1.0].
    """

    display: str
    raw_key: str | None = None
    source: NameSource = "fallback"
    confidence: float = 0.5


_TRAILING_DIGITS_RE = re.compile(r"(\D)(\d+)$")
_ORDINAL_RE = re.compile(r"^(\d+)(ST|ND|RD|TH)$", re.IGNORECASE)

_ROMAN_NUMERALS = {
    "I",
    "II",
    "III",
    "IV",
    "V",
    "VI",
    "VII",
    "VIII",
    "IX",
    "X",
}


def resolve_name(
    value: Any, *, default: str = "Unknown", context: NameContext = "generic"
) -> ResolvedName:
    """Resolve a Stellaris name into a human-readable string.

    Accepts either:
    - literal strings (already a display name)
    - localization keys (SPEC_*, NAME_*, etc.)
    - Clausewitz "name blocks" as parsed by Rust/Jomini: {key: ..., variables: [...]}
    """
    if value is None:
        return ResolvedName(display=default, raw_key=None, source="missing", confidence=0.0)

    if isinstance(value, dict):
        return _resolve_name_block(value, default=default, context=context)

    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return ResolvedName(display=default, raw_key=None, source="missing", confidence=0.0)

        # Heuristic: underscore-heavy, known prefixes, or all-caps keys are likely localization keys.
        is_likely_key = (
            "_" in raw
            or raw.startswith(
                (
                    "NAME_",
                    "SPEC_",
                    "ADJ_",
                    "PRESCRIPTED_",
                    "EMPIRE_DESIGN_",
                    "FALLEN_EMPIRE_",
                    "AWAKENED_EMPIRE_",
                    "shipclass_",
                    "TRANS_",
                )
            )
            or (raw.isalpha() and raw.isupper() and len(raw) > 4)
        )

        if is_likely_key:
            return _resolve_localization_key(raw)

        return ResolvedName(display=raw, raw_key=None, source="literal", confidence=1.0)

    return ResolvedName(display=str(value), raw_key=None, source="fallback", confidence=0.2)


def _resolve_name_block(
    block: dict[str, Any], *, default: str, context: NameContext
) -> ResolvedName:
    key = block.get("key")
    variables = block.get("variables", [])

    if not isinstance(key, str) or not key.strip():
        return ResolvedName(display=default, raw_key=None, source="missing", confidence=0.0)

    key = key.strip()

    # Fleet %SEQ% templates (e.g. Fleet #1)
    if context == "fleet" and key == "%SEQ%":
        if isinstance(variables, list):
            for var in variables:
                if isinstance(var, dict) and var.get("key") == "num":
                    value = var.get("value", {})
                    if isinstance(value, dict):
                        num = value.get("key")
                        if isinstance(num, str) and num.strip():
                            return ResolvedName(
                                display=f"Fleet #{num.strip()}",
                                raw_key=key,
                                source="template",
                                confidence=0.95,
                            )
        return ResolvedName(display=default, raw_key=key, source="template", confidence=0.3)

    # Planet templates (colony numbering, parent + numeral, habitats)
    if context == "planet":
        resolved = _resolve_planet_template(key, variables, default=default)
        if resolved is not None:
            return resolved

        # e.g. HUMAN2_PLANET_StCaspar -> StCaspar
        if "_PLANET_" in key:
            tail = key.split("_PLANET_", 1)[-1]
            return ResolvedName(
                display=_format_key_text(tail),
                raw_key=key,
                source="localization_key",
                confidence=0.8,
            )

    # Generic template resolution: extract concrete values from nested variables.
    parts: list[str] = []
    if isinstance(variables, list):
        for var in variables:
            if not isinstance(var, dict):
                continue
            value = var.get("value")
            for extracted in _extract_concrete_values(value):
                if extracted and not extracted.startswith("%"):
                    parts.append(resolve_name(extracted, default="", context="generic").display)

    parts = [p for p in (p.strip() for p in parts) if p]
    if parts:
        return ResolvedName(
            display=" ".join(parts),
            raw_key=key,
            source="template",
            confidence=0.85,
        )

    # Fallback: treat the block key as a localization key.
    return _resolve_localization_key(key)


def _resolve_planet_template(key: str, variables: Any, *, default: str) -> ResolvedName | None:
    # PLANET_NAME_FORMAT: {PARENT: <name>, NUMERAL: <roman>}
    if key == "PLANET_NAME_FORMAT":
        parent_name: str | None = None
        numeral: str | None = None
        if isinstance(variables, list):
            for var in variables:
                if not isinstance(var, dict):
                    continue
                var_key = var.get("key")
                value = var.get("value", {})
                if var_key == "PARENT" and isinstance(value, dict):
                    parent_name = resolve_name(value, default="", context="planet").display
                elif var_key == "NUMERAL" and isinstance(value, dict):
                    numeral_key = value.get("key")
                    if isinstance(numeral_key, str):
                        numeral = numeral_key.strip()
        if parent_name and numeral:
            return ResolvedName(
                display=f"{parent_name} {numeral}", raw_key=key, source="template", confidence=0.95
            )
        if parent_name:
            return ResolvedName(display=parent_name, raw_key=key, source="template", confidence=0.8)
        return ResolvedName(display=default, raw_key=key, source="template", confidence=0.3)

    # NEW_COLONY_NAME_X: {NAME: <system>}
    if key.startswith("NEW_COLONY_NAME_"):
        colony_num = key.replace("NEW_COLONY_NAME_", "").strip()
        if isinstance(variables, list):
            for var in variables:
                if isinstance(var, dict) and var.get("key") == "NAME":
                    value = var.get("value", {})
                    if isinstance(value, dict):
                        system = resolve_name(value, default="", context="planet").display
                        if system:
                            return ResolvedName(
                                display=f"{system} {colony_num}" if colony_num else system,
                                raw_key=key,
                                source="template",
                                confidence=0.95,
                            )
        return ResolvedName(
            display=f"Colony {colony_num}".strip(), raw_key=key, source="template", confidence=0.6
        )

    # HABITAT_PLANET_NAME: variables often contain solar_system name
    if key == "HABITAT_PLANET_NAME":
        if isinstance(variables, list):
            for var in variables:
                if not isinstance(var, dict):
                    continue
                var_key = str(var.get("key", ""))
                if "solar_system" in var_key or var_key == "NAME":
                    value = var.get("value", {})
                    if isinstance(value, dict):
                        system = resolve_name(value, default="", context="planet").display
                        if system:
                            return ResolvedName(
                                display=f"{system} Habitat",
                                raw_key=key,
                                source="template",
                                confidence=0.9,
                            )
        return ResolvedName(display="Habitat", raw_key=key, source="template", confidence=0.6)

    return None


def _extract_concrete_values(value: Any) -> list[str]:
    """Extract concrete string-ish values from nested variable structures."""
    out: list[str] = []

    if value is None:
        return out

    if isinstance(value, str):
        out.append(value)
        return out

    if not isinstance(value, dict):
        out.append(str(value))
        return out

    key = value.get("key")
    if isinstance(key, str) and key and not key.startswith("%"):
        out.append(key)

    variables = value.get("variables", [])
    if isinstance(variables, list):
        for var in variables:
            if isinstance(var, dict):
                out.extend(_extract_concrete_values(var.get("value")))

    return out


def _resolve_localization_key(key: str) -> ResolvedName:
    key = key.strip()
    if not key:
        return ResolvedName(display="Unknown", raw_key=None, source="missing", confidence=0.0)

    # High-signal special cases first
    if key.startswith("AWAKENED_EMPIRE_"):
        suffix = key[len("AWAKENED_EMPIRE_") :]
        if suffix.isdigit():
            return ResolvedName(
                display=f"Awakened Empire {suffix}",
                raw_key=key,
                source="localization_key",
                confidence=0.9,
            )
        return ResolvedName(
            display=f"Awakened Empire ({_format_key_text(suffix)})",
            raw_key=key,
            source="localization_key",
            confidence=0.85,
        )

    if key.startswith("FALLEN_EMPIRE_"):
        suffix = key[len("FALLEN_EMPIRE_") :]
        if suffix.isdigit():
            return ResolvedName(
                display=f"Fallen Empire {suffix}",
                raw_key=key,
                source="localization_key",
                confidence=0.9,
            )
        return ResolvedName(
            display=f"Fallen Empire ({_format_key_text(suffix)})",
            raw_key=key,
            source="localization_key",
            confidence=0.85,
        )

    if key.startswith("TRANS_"):
        # Common case: TRANS_FLEET
        if key == "TRANS_FLEET":
            return ResolvedName(
                display="Transport Fleet", raw_key=key, source="localization_key", confidence=0.8
            )
        suffix = key[len("TRANS_") :]
        return ResolvedName(
            display=_format_key_text(suffix), raw_key=key, source="localization_key", confidence=0.6
        )

    if key.startswith("shipclass_"):
        result = key[len("shipclass_") :]
        if result.endswith("_name"):
            result = result[: -len("_name")]
        return ResolvedName(
            display=_format_key_text(result),
            raw_key=key,
            source="localization_key",
            confidence=0.75,
        )

    if key.endswith("_FLEET") and len(key) > len("_FLEET"):
        base = key[: -len("_FLEET")]
        return ResolvedName(
            display=f"{_format_key_text(base)} Fleet",
            raw_key=key,
            source="localization_key",
            confidence=0.7,
        )

    if key.startswith("EMPIRE_DESIGN_"):
        result = key[len("EMPIRE_DESIGN_") :]
        result = _TRAILING_DIGITS_RE.sub(r"\1 \2", result)
        return ResolvedName(
            display=_format_key_text(result), raw_key=key, source="localization_key", confidence=0.8
        )

    if key.startswith("NAME_"):
        result = key[len("NAME_") :]
        return ResolvedName(
            display=result.replace("_", " "),
            raw_key=key,
            source="localization_key",
            confidence=0.75,
        )

    # General prefix stripping
    prefixes = (
        "PRESCRIPTED_species_name_",
        "PRESCRIPTED_adjective_",
        "PRESCRIPTED_",
        "SPEC_",
        "ADJ_",
        "EMPIRE_",
        "COUNTRY_",
        "CIV_",
    )

    result = key
    for prefix in prefixes:
        if result.startswith(prefix):
            result = result[len(prefix) :]
            break

    if result.endswith("_name") and len(result) > len("_name"):
        result = result[: -len("_name")]

    result = _TRAILING_DIGITS_RE.sub(r"\1 \2", result)
    return ResolvedName(
        display=_format_key_text(result), raw_key=key, source="localization_key", confidence=0.65
    )


def _format_key_text(text: str) -> str:
    """Format a localization-ish token into a readable string."""
    if not text:
        return ""

    # Keep hyphens, convert underscores to spaces
    text = text.replace("_", " ").strip()
    words = [w for w in text.split(" ") if w]
    if not words:
        return ""

    return " ".join(_format_token(w) for w in words)


def _format_token(token: str) -> str:
    if not token:
        return token

    # Roman numerals should stay uppercase (Sol III)
    if token in _ROMAN_NUMERALS:
        return token

    # Fix ordinals: 1ST -> 1st (avoid 1St)
    m = _ORDINAL_RE.match(token)
    if m:
        return f"{m.group(1)}{m.group(2).lower()}"

    # Common casing heuristics
    if token.isalpha() and token.isupper():
        return token.title()
    if token.isalpha() and token.islower():
        return token.title()

    return token
