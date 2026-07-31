"""Build a provider-neutral, model-facing view of extracted campaign data."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from backend.core.json_utils import json_dumps

MODEL_BRIEFING_SCHEMA_VERSION = 1


def build_model_briefing(briefing: dict[str, Any]) -> dict[str, Any]:
    """Return extracted data plus explicit semantics shared by every model provider.

    The stored briefing remains the lossless extraction artifact. This view adds the
    interpretation rules models need without changing save-derived values.
    """
    if not isinstance(briefing, dict):
        return {}

    result = deepcopy(briefing)
    meta = result.get("meta") if isinstance(result.get("meta"), dict) else {}
    version = str(meta.get("version") or "").strip()
    major_version = _major_version(version)

    population: dict[str, Any] = {
        "unit": "in-game population",
        "instruction": "Report population values as provided; do not reinterpret them as jobs.",
    }
    if major_version is not None and major_version >= 4:
        population.update(
            {
                "scale": (
                    "Stellaris 4.x populations are intentionally measured in the thousands; "
                    "these values are normal and are not legacy one-pop counts."
                ),
                "workforce_rule": (
                    "Each population supplies 1 workforce and a typical job consumes about "
                    "100 workforce. Population and filled jobs are not interchangeable."
                ),
            }
        )

    result["model_context"] = {
        "schema_version": MODEL_BRIEFING_SCHEMA_VERSION,
        "game_version": version or None,
        "population": population,
        "diplomacy": {
            "ordinary_empire_country_type": "default",
            "instruction": (
                "relations can include pirates, enclaves, marauders, space fauna, primitives, "
                "and fallen empires. Use diplomacy.empire_count for contacted empires and "
                "country_type to identify special contacts."
            ),
        },
        "threats": {
            "instruction": (
                "Dormant fallen empires and living leviathans are background powers, not "
                "ordinary diplomatic partners or near-term threats without explicit border, "
                "hostility, awakening, or path-blocking evidence."
            )
        },
        "evidence": {
            "instruction": (
                "Treat save-derived fields as observations. Clearly label strategic forecasts "
                "as inference and do not invent availability, costs, borders, or intentions."
            )
        },
    }
    return result


def build_model_briefing_json(raw_briefing_json: str) -> str:
    """Convert a stored briefing JSON string into the model-facing contract."""
    try:
        briefing = json.loads(raw_briefing_json)
    except (TypeError, ValueError):
        return raw_briefing_json
    if not isinstance(briefing, dict):
        return raw_briefing_json
    return json_dumps(build_model_briefing(briefing), default=str)


def _major_version(version: str) -> int | None:
    match = re.search(r"(?:^|\bv)(\d+)(?:\.\d+)", version, flags=re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))
