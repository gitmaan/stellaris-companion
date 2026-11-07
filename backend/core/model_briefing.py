"""Build a provider-neutral, model-facing view of extracted campaign data."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from backend.core.json_utils import json_dumps
from stellaris_companion.campaign_evidence import (
    resolve_content_availability,
    resolve_empire_identity,
)
from stellaris_companion.evidence_policy import build_evidence_policy

MODEL_BRIEFING_SCHEMA_VERSION = 3


def get_briefing_metadata(briefing: dict[str, Any]) -> dict[str, Any]:
    """Recover only copied version metadata from older model-facing snapshots.

    Old contexts can retain the source version after metadata compaction. Their
    derived availability and identity are never reused. Raw evidence stays intact.
    """
    metadata = briefing.get("meta")
    result = dict(metadata) if isinstance(metadata, dict) else {}
    previous_context = briefing.get("model_context")
    if not result.get("version") and isinstance(previous_context, dict):
        version = previous_context.get("game_version")
        if isinstance(version, str) and version.strip():
            result["version"] = version
    return result


def build_model_briefing(briefing: dict[str, Any]) -> dict[str, Any]:
    """Return extracted data plus explicit semantics shared by every model provider.

    The stored briefing remains the lossless extraction artifact. This view adds the
    interpretation rules models need without changing save-derived values.
    """
    if not isinstance(briefing, dict):
        return {}

    result = deepcopy(briefing)
    meta = get_briefing_metadata(result)
    # This legacy field is our old set-difference heuristic, not a save observation.
    # Preserve it in storage, but do not keep presenting a known-bad inference to models.
    if isinstance(result.get("meta"), dict):
        result["meta"].pop("missing_dlcs", None)
    version = str(meta.get("version") or "").strip()
    major_version = _major_version(version)

    _add_model_facing_war_stats(result)

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
        "content_availability": resolve_content_availability(meta),
        "empire_identity": resolve_empire_identity(result.get("identity")),
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
        "military": {
            "wars": {
                "participation_scope": (
                    "battle_stats cover only engagements where the player country directly "
                    "participated; allied-only engagements are excluded."
                ),
                "side_scope": (
                    "Victory and casualty fields are parent-war coalition totals. In a "
                    "multi-country engagement, our_side losses may include allied casualties."
                ),
                "assessment_rule": (
                    "Battle history is tactical evidence, not a complete measure of overall war "
                    "progress. Consider occupation, war goals, controlled capitals and systems, "
                    "and current military strength before declaring a war won or lost."
                ),
                "preferred_fields": (
                    "Use the explicit player_involved_battles, our_side_victories, "
                    "opposing_side_victories, our_side_ship_losses, and "
                    "opposing_side_ship_losses aliases when discussing battle history."
                ),
            }
        },
        "evidence": build_evidence_policy(),
    }
    nomad = result.get("nomad")
    if isinstance(nomad, dict) and nomad.get("is_nomadic") is True:
        result["model_context"]["nomad_economy"] = _nomad_economy_rules(version)
    return result


def _nomad_economy_rules(version: str) -> dict[str, str]:
    """Rules for reading a Nomad empire's economy, regardless of the question asked."""
    parsed = _version_tuple(version)
    if parsed is not None and parsed >= (4, 4, 5):
        pool = (
            "Energy Credits and Minerals are pooled as Operational Reserves "
            "(nomad.operational_reserves.current); one point equals one Mineral or one "
            "Energy Credit."
        )
    else:
        pool = (
            "Energy Credits and Minerals are pooled as Operational Reserves "
            "(nomad.operational_reserves.current). The conversion rate changed in 4.4.5; "
            "do not assume a ratio for this version."
        )
    return {
        "applies_to": "This empire is Nomadic. These rules override settled-empire assumptions.",
        "operational_reserves": (
            f"{pool} Judge affordability and economic health against this pool and its "
            "stage, not against separate Energy and Mineral balances, and do not add them "
            "together yourself."
        ),
        "monthly_lines": (
            "Negative or missing monthly Mineral and Energy lines are normal for Nomads. "
            "Income arrives in lumps from harvesting and from collecting Waystation and "
            "Logistic Ship stockpiles, which do not appear as monthly production. Use "
            "operational_reserves.monthly_change and stage; never diagnose failing mining "
            "or an unhealthy economy from the empire balance alone."
        ),
        "stages": (
            "Reserve stages are critical, low, medium and high. Critical brings severe "
            "research and production penalties. The approach (conserve, balance, burn, "
            "festival) sets how fast reserves are spent."
        ),
        "collection_chain": (
            "Waystations collect resources into their own stockpile until a Logistic Ship "
            "or Arkship collects them; Logistic Ships carry cargo back to the Arkships. Use "
            "nomad.waystations and nomad.logistic_ships for this chain."
        ),
        "missing_data": (
            "If reserves, stockpiles or cargo are absent from the data, say the save "
            "information is not available rather than inferring the economy is unhealthy."
        ),
        "market": "Minerals and Energy can be bought on the market but not sold.",
    }


def _version_tuple(version: str) -> tuple[int, int, int] | None:
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", version or "")
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)


def _add_model_facing_war_stats(briefing: dict[str, Any]) -> None:
    """Add unambiguous aliases without changing the stored extraction artifact."""
    military = briefing.get("military")
    if not isinstance(military, dict):
        return
    wars_block = military.get("wars")
    if not isinstance(wars_block, dict):
        return
    wars = wars_block.get("wars")
    if not isinstance(wars, list):
        return

    aliases = {
        "player_involved_battles": "total_battles",
        "our_side_victories": "our_victories",
        "opposing_side_victories": "their_victories",
        "unknown_outcomes": "unknown_outcomes",
        "our_side_ship_losses": "our_ship_losses",
        "opposing_side_ship_losses": "their_ship_losses",
        "our_side_army_losses": "our_army_losses",
        "opposing_side_army_losses": "their_army_losses",
    }
    for war in wars:
        if not isinstance(war, dict):
            continue
        stats = war.get("battle_stats")
        if not isinstance(stats, dict):
            continue
        for alias, source in aliases.items():
            if source in stats:
                stats[alias] = stats[source]


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
