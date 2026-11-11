"""Build a provider-neutral, model-facing view of extracted campaign data."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from backend.core.briefing_names import briefing_value_name
from backend.core.json_utils import json_dumps
from stellaris_companion.campaign_evidence import (
    resolve_content_availability,
    resolve_empire_identity,
)
from stellaris_companion.evidence_policy import build_evidence_policy
from stellaris_companion.technology_names import (
    catalog_covers_game_version,
    name_usage,
    names_game_version,
    names_source,
    technology_display_name,
    technology_names_for,
    technology_variant_names,
)

MODEL_BRIEFING_SCHEMA_VERSION = 3

# Sections left as they are when values are given their in-game names: identity
# holds the raw IDs other code reads (model_context.empire_identity has the names),
# and technology is named by _name_technologies, which keeps research options by ID.
_SECTIONS_KEPT_AS_IDS = frozenset({"meta", "identity", "technology", "model_context"})
# Codes that instructions and code refer to by value, not things with a name on screen.
_FIELDS_KEPT_AS_IDS = frozenset({"country_type"})


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
    technology = _name_technologies(result.get("technology"), version)
    if technology:
        result["model_context"]["technology"] = technology
    if _name_values(result):
        result["model_context"]["names"] = {
            "source": names_source(),
            "instruction": (
                "Buildings, districts, traditions, ascension perks, traits, starbase modules, "
                "megastructures and similar values in this briefing are written as the "
                "player's own game shows them. Use those names exactly as written. A value "
                "still written as an ID (lowercase_words_joined_by_underscores) has no "
                "in-game name here: describe it in plain words and never present a name "
                "guessed from it as the exact in-game name."
            ),
        }
    nomad = result.get("nomad")
    if isinstance(nomad, dict) and nomad.get("is_nomadic") is True:
        result["model_context"]["nomad_economy"] = _nomad_economy_rules(version)
    return result


def _name_values(briefing: dict[str, Any]) -> int:
    """Replace save IDs with the installed game's names, in place; return how many.

    The save records a building as ``building_factory_3`` and the player sees
    "Civilian Repli-Complexes". Only values are renamed, never keys, and only when
    the installed game has a name for that kind of value; without an install
    nothing changes.
    """
    renamed = 0

    def name(value: Any, section: str, field: str) -> Any:
        nonlocal renamed
        if isinstance(value, str):
            shown = briefing_value_name(value, section, field)
            if shown and shown != value:
                renamed += 1
                return shown
        elif isinstance(value, list):
            value[:] = [name(item, section, field) for item in value]
        elif isinstance(value, dict):
            for key, item in value.items():
                if key not in _FIELDS_KEPT_AS_IDS:
                    value[key] = name(item, section, str(key))
        return value

    for section, value in briefing.items():
        if section not in _SECTIONS_KEPT_AS_IDS:
            name(value, section, "")
    return renamed


def _name_technologies(technology: Any, game_version: str) -> dict[str, Any] | None:
    """Give the model in-game technology names; the save only records internal IDs.

    Researched technologies are renamed in place in this model-facing copy, which
    costs nothing: a name is about as long as its ID. Current research and the
    research options keep their IDs and are named alongside, with the other names
    an empire-specific variant can show.
    """
    if not isinstance(technology, dict):
        return None
    identifiers: list[Any] = []
    for group in (technology.get("in_progress"), technology.get("available_techs")):
        if not isinstance(group, dict):
            continue
        for value in group.values():
            if isinstance(value, dict):
                identifiers.append(value.get("tech"))
                queued = value.get("queued_techs")
                identifiers.extend(queued if isinstance(queued, list) else [])
            elif isinstance(value, list):
                identifiers.extend(value)
    researched = technology.get("researched_techs")
    has_researched = isinstance(researched, list) and bool(researched)
    if has_researched:
        technology["researched_techs"] = [
            technology_display_name(identifier) or identifier for identifier in researched
        ]
    if not has_researched and not any(isinstance(i, str) and i for i in identifiers):
        return None

    names = technology_names_for(identifiers)
    context: dict[str, Any] = {
        "names": names,
        "names_source": names_source(),
        "instruction": (
            "Saves record technologies by internal ID, which often differs from what the "
            "player sees: tech_cryostasis_1 is Automated Colony Ships. names gives the "
            "in-game name of each ID in technology.in_progress and "
            "technology.available_techs, and technology.researched_techs already lists "
            "in-game names. A technology in in_progress (tech or queued_techs) is not "
            "researched yet; special_project means that field is working on a project first. "
            f"Refer to technologies by these names, {name_usage()}, "
            "and match a technology the player mentions against them before saying it is "
            "missing. An entry that still looks like an ID (tech_...) is one these names do not "
            "cover (a mod, or a newer game): never present it, or a name guessed from it, as the exact in-game "
            "name, and never invent an ID."
        ),
    }
    also_shown_as = {
        identifier: list(variants)
        for identifier in names
        if (variants := technology_variant_names(identifier))
    }
    if also_shown_as:
        context["also_shown_as"] = also_shown_as
        context["variant_rule"] = (
            "Some empire types (Wilderness, Nomads and others) see a technology under the "
            "also_shown_as name instead. The save does not say which; treat both as the same "
            "technology."
        )
    if catalog_covers_game_version(game_version, names_game_version()) is False:
        context["catalog_note"] = (
            f"This save is from {game_version}, newer than the name catalog "
            f"({names_game_version()}). Technologies added or renamed since may be missing or "
            "out of date here."
        )
    return context


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
            "Logistic Ship stockpiles, which do not appear as monthly production. The save "
            "holds the reserves' level and stage, not a monthly change, so do not state one; "
            "operational_reserves.festival_upkeep_last_month, when present, is only what the "
            "Festival approach drained last month. Never diagnose failing mining or an "
            "unhealthy economy from the empire balance alone."
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
