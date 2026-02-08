"""
Event detection for Phase 3 (Milestone 3).

Derives human-readable events from two snapshots (previous vs current).

ARCHITECTURE:
- This file DETECTS changes between snapshots using snapshot_reader
- snapshot_reader.py READS data from stored snapshots (briefing.history)
- signals.py CREATES data during save ingestion
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.core.snapshot_reader import (
    get_ascension_perk_set,
    get_border_neighbors,
    get_crisis,
    get_diplomacy_sets,
    get_discovered_homeworlds,
    get_edicts,
    get_empire_names,
    get_fallen_empires,
    get_fallen_empires_by_name,
    get_finished_traditions,
    get_galactic_community,
    get_galaxy,
    get_great_khan,
    get_known_empire_ids,
    get_lgate,
    get_megastructures_by_id,
    get_menace,
    get_player_leaders,
    get_policies,
    get_precursors,
    get_ruler_info,
    get_subject_details,
    get_subject_sets,
    get_system_count,
    get_tech_list,
    get_war_battle_locations,
    get_war_names,
)


@dataclass(frozen=True)
class DetectedEvent:
    event_type: str
    summary: str
    data: dict[str, Any]


from backend.core.utils import safe_float, safe_int


def _pct_change(before: float | int | None, after: float | int | None) -> float | None:
    if before is None or after is None:
        return None
    before_f = float(before)
    after_f = float(after)
    if before_f == 0:
        return None
    return (after_f - before_f) / before_f


def _sign_changed(before: float | int | None, after: float | int | None) -> bool:
    if before is None or after is None:
        return False
    return (before >= 0 > after) or (before < 0 <= after)


def _normalize_federation(briefing: dict[str, Any]) -> str | None:
    dip = briefing.get("diplomacy", {}) if isinstance(briefing, dict) else {}
    fed = dip.get("federation")
    if not fed:
        return None
    if isinstance(fed, str):
        return fed.strip() or "Federation"
    if isinstance(fed, dict):
        for key in ("name", "federation_name", "federation", "id"):
            val = fed.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        return "Federation"
    return "Federation"


def _get_leader_name(leader: dict[str, Any]) -> str:
    """Get best available leader name with fallback chain.

    Priority: name (resolved) → name_key (with cleanup) → #{id}
    """
    name = leader.get("name")
    if name and isinstance(name, str) and name.strip():
        return name.strip()

    name_key = leader.get("name_key")
    if name_key and isinstance(name_key, str):
        key = name_key.strip()
        if "_CHR_" in key:
            return key.split("_CHR_")[-1]
        if key.startswith("NAME_"):
            return key[5:].replace("_", " ")
        if not key.startswith("%"):
            return key

    lid = leader.get("id")
    return f"#{lid}" if lid is not None else "#unknown"


def _get_empire_name(cid: int, empire_names: dict[int, str]) -> str:
    """Get empire name with fallback to ID."""
    name = empire_names.get(cid)
    if name:
        return name
    return f"empire #{cid}"


def _parse_year(date_str: Any) -> int | None:
    if not isinstance(date_str, str):
        return None
    if len(date_str) < 4:
        return None
    try:
        return int(date_str[:4])
    except Exception:
        return None


# Notable ascension perks that should be highlighted in chronicles
_NOTABLE_ASCENSION_PERKS = {
    "ap_synthetic_evolution",
    "ap_the_flesh_is_weak",
    "ap_mind_over_matter",
    "ap_transcendence",
    "ap_become_the_crisis",
    "ap_colossus",
    "ap_galactic_force_projection",
    "ap_world_shaper",
    "ap_arcology_project",
    "ap_machine_worlds",
}


def _format_perk_name(perk_id: str) -> str:
    """Format ascension perk ID for display."""
    name = perk_id.replace("ap_", "").replace("_", " ").title()
    return name


def _format_tradition_tree_name(tree_id: str) -> str:
    """Format tradition tree ID for display."""
    name = tree_id.replace("tr_", "")
    return name.title()


def _get_precursor_name(precursor_key: str, briefing: dict[str, Any]) -> str:
    """Get the display name for a precursor from the progress dict."""
    precursors = get_precursors(briefing)
    progress = precursors.get("precursor_progress", {})
    if isinstance(progress, dict):
        precursor_data = progress.get(precursor_key)
        if isinstance(precursor_data, dict):
            name = precursor_data.get("name")
            if name and isinstance(name, str) and name.strip():
                return name.strip()
    return _format_precursor_name(precursor_key)


def _format_precursor_name(precursor_key: str) -> str:
    """Format precursor key for display."""
    name = precursor_key
    for prefix in ("precursor_", "pre_"):
        if name.startswith(prefix):
            name = name[len(prefix) :]
            break
    return name.replace("_", " ").title()


def compute_events(
    *,
    prev: dict[str, Any],
    curr: dict[str, Any],
    from_snapshot_id: int,
    to_snapshot_id: int,
) -> list[DetectedEvent]:
    """Compute a list of derived events between two briefings."""
    events: list[DetectedEvent] = []

    # Military power change
    prev_mil = safe_int(prev.get("military", {}).get("military_power"))
    curr_mil = safe_int(curr.get("military", {}).get("military_power"))
    if prev_mil is not None and curr_mil is not None and prev_mil != curr_mil:
        pct = _pct_change(prev_mil, curr_mil)
        delta = curr_mil - prev_mil
        if (pct is not None and abs(pct) >= 0.15 and abs(delta) >= 2000) or abs(delta) >= 10000:
            sign = "+" if delta > 0 else ""
            pct_text = f"{pct * 100:+.0f}%" if pct is not None else "n/a"
            events.append(
                DetectedEvent(
                    event_type="military_power_change",
                    summary=f"Military power: {prev_mil:,} → {curr_mil:,} ({sign}{delta:,}, {pct_text})",
                    data={
                        "metric": "military_power",
                        "before": prev_mil,
                        "after": curr_mil,
                        "delta": delta,
                        "pct": pct,
                        "from_snapshot_id": from_snapshot_id,
                        "to_snapshot_id": to_snapshot_id,
                    },
                )
            )

    # Military fleet count change
    prev_mil_fleets = safe_int(prev.get("military", {}).get("military_fleets"))
    curr_mil_fleets = safe_int(curr.get("military", {}).get("military_fleets"))
    if (
        prev_mil_fleets is not None
        and curr_mil_fleets is not None
        and prev_mil_fleets != curr_mil_fleets
    ):
        diff = curr_mil_fleets - prev_mil_fleets
        if abs(diff) >= 2:
            sign = "+" if diff > 0 else ""
            events.append(
                DetectedEvent(
                    event_type="military_fleet_change",
                    summary=f"Military fleets: {prev_mil_fleets} → {curr_mil_fleets} ({sign}{diff})",
                    data={
                        "metric": "military_fleets",
                        "before": prev_mil_fleets,
                        "after": curr_mil_fleets,
                        "delta": diff,
                        "from_snapshot_id": from_snapshot_id,
                        "to_snapshot_id": to_snapshot_id,
                    },
                )
            )

    # Colony count change
    prev_colonies = safe_int(prev.get("territory", {}).get("colonies", {}).get("total_count"))
    curr_colonies = safe_int(curr.get("territory", {}).get("colonies", {}).get("total_count"))
    if prev_colonies is not None and curr_colonies is not None and prev_colonies != curr_colonies:
        diff = curr_colonies - prev_colonies
        sign = "+" if diff > 0 else ""
        events.append(
            DetectedEvent(
                event_type="colony_count_change",
                summary=f"Colonies: {prev_colonies} → {curr_colonies} ({sign}{diff})",
                data={
                    "metric": "colony_count",
                    "before": prev_colonies,
                    "after": curr_colonies,
                    "delta": diff,
                    "from_snapshot_id": from_snapshot_id,
                    "to_snapshot_id": to_snapshot_id,
                },
            )
        )

    # Tech count change
    prev_tech = safe_int(prev.get("technology", {}).get("tech_count"))
    curr_tech = safe_int(curr.get("technology", {}).get("tech_count"))
    if prev_tech is not None and curr_tech is not None and curr_tech > prev_tech:
        diff = curr_tech - prev_tech
        events.append(
            DetectedEvent(
                event_type="tech_completed",
                summary=f"Technology completed: +{diff} (total {prev_tech} → {curr_tech})",
                data={
                    "metric": "tech_count",
                    "before": prev_tech,
                    "after": curr_tech,
                    "delta": diff,
                    "from_snapshot_id": from_snapshot_id,
                    "to_snapshot_id": to_snapshot_id,
                },
            )
        )

    # Energy net change
    prev_energy = safe_float(prev.get("economy", {}).get("net_monthly", {}).get("energy"))
    curr_energy = safe_float(curr.get("economy", {}).get("net_monthly", {}).get("energy"))
    if prev_energy is not None and curr_energy is not None and prev_energy != curr_energy:
        delta = curr_energy - prev_energy
        pct = _pct_change(prev_energy, curr_energy)
        if _sign_changed(prev_energy, curr_energy) or abs(delta) >= max(
            20.0, abs(prev_energy) * 0.25
        ):
            events.append(
                DetectedEvent(
                    event_type="energy_net_change",
                    summary=f"Energy net: {prev_energy:+.1f} → {curr_energy:+.1f} ({delta:+.1f})",
                    data={
                        "metric": "energy_net",
                        "before": prev_energy,
                        "after": curr_energy,
                        "delta": delta,
                        "pct": pct,
                        "from_snapshot_id": from_snapshot_id,
                        "to_snapshot_id": to_snapshot_id,
                    },
                )
            )

    # Alloys net change
    prev_alloys = safe_float(prev.get("economy", {}).get("net_monthly", {}).get("alloys"))
    curr_alloys = safe_float(curr.get("economy", {}).get("net_monthly", {}).get("alloys"))
    if prev_alloys is not None and curr_alloys is not None and prev_alloys != curr_alloys:
        delta = curr_alloys - prev_alloys
        pct = _pct_change(prev_alloys, curr_alloys)
        if _sign_changed(prev_alloys, curr_alloys) or abs(delta) >= max(
            5.0, abs(prev_alloys) * 0.25
        ):
            events.append(
                DetectedEvent(
                    event_type="alloys_net_change",
                    summary=f"Alloys net: {prev_alloys:+.1f} → {curr_alloys:+.1f} ({delta:+.1f})",
                    data={
                        "metric": "alloys_net",
                        "before": prev_alloys,
                        "after": curr_alloys,
                        "delta": delta,
                        "pct": pct,
                        "from_snapshot_id": from_snapshot_id,
                        "to_snapshot_id": to_snapshot_id,
                    },
                )
            )

    # Economy bottlenecks: CG, food, minerals
    for key, label, min_abs in [
        ("consumer_goods", "Consumer Goods net", 5.0),
        ("food", "Food net", 5.0),
        ("minerals", "Minerals net", 20.0),
    ]:
        prev_val = safe_float(prev.get("economy", {}).get("net_monthly", {}).get(key))
        curr_val = safe_float(curr.get("economy", {}).get("net_monthly", {}).get(key))
        if prev_val is None or curr_val is None or prev_val == curr_val:
            continue
        delta = curr_val - prev_val
        pct = _pct_change(prev_val, curr_val)
        if _sign_changed(prev_val, curr_val) or abs(delta) >= max(min_abs, abs(prev_val) * 0.25):
            events.append(
                DetectedEvent(
                    event_type=f"{key}_net_change",
                    summary=f"{label}: {prev_val:+.1f} → {curr_val:+.1f} ({delta:+.1f})",
                    data={
                        "metric": f"{key}_net",
                        "before": prev_val,
                        "after": curr_val,
                        "delta": delta,
                        "pct": pct,
                        "from_snapshot_id": from_snapshot_id,
                        "to_snapshot_id": to_snapshot_id,
                    },
                )
            )

    # Federation changes
    prev_fed = _normalize_federation(prev)
    curr_fed = _normalize_federation(curr)
    if prev_fed != curr_fed:
        if prev_fed is None and curr_fed is not None:
            events.append(
                DetectedEvent(
                    event_type="federation_joined",
                    summary=f"Joined a federation: {curr_fed}",
                    data={
                        "before": None,
                        "after": curr_fed,
                        "from_snapshot_id": from_snapshot_id,
                        "to_snapshot_id": to_snapshot_id,
                    },
                )
            )
        elif prev_fed is not None and curr_fed is None:
            events.append(
                DetectedEvent(
                    event_type="federation_left",
                    summary=f"Left federation: {prev_fed}",
                    data={
                        "before": prev_fed,
                        "after": None,
                        "from_snapshot_id": from_snapshot_id,
                        "to_snapshot_id": to_snapshot_id,
                    },
                )
            )
        elif prev_fed and curr_fed:
            events.append(
                DetectedEvent(
                    event_type="federation_changed",
                    summary=f"Federation changed: {prev_fed} → {curr_fed}",
                    data={
                        "before": prev_fed,
                        "after": curr_fed,
                        "from_snapshot_id": from_snapshot_id,
                        "to_snapshot_id": to_snapshot_id,
                    },
                )
            )

    # War events - using snapshot_reader
    prev_wars = get_war_names(prev)
    curr_wars = get_war_names(curr)
    started = sorted(curr_wars - prev_wars)
    ended = sorted(prev_wars - curr_wars)
    for name in started[:5]:
        events.append(
            DetectedEvent(
                event_type="war_started",
                summary=f"War started: {name}",
                data={
                    "war_name": name,
                    "from_snapshot_id": from_snapshot_id,
                    "to_snapshot_id": to_snapshot_id,
                },
            )
        )
    prev_battle_locs = get_war_battle_locations(prev)
    for name in ended[:5]:
        # Enrich with battle locations from previous snapshot (where war still existed)
        locs = prev_battle_locs.get(name, [])
        loc_text = f" (fought at {', '.join(locs[:3])})" if locs else ""
        events.append(
            DetectedEvent(
                event_type="war_ended",
                summary=f"War ended: {name}{loc_text}",
                data={
                    "war_name": name,
                    "battle_locations": locs[:3],
                    "from_snapshot_id": from_snapshot_id,
                    "to_snapshot_id": to_snapshot_id,
                },
            )
        )

    # Border neighbor changes - using snapshot_reader
    prev_border = get_border_neighbors(prev)
    curr_border = get_border_neighbors(curr)
    prev_neighbor_names = {
        n.get("empire_name") for n in prev_border if isinstance(n, dict) and n.get("empire_name")
    }
    curr_neighbor_names = {
        n.get("empire_name") for n in curr_border if isinstance(n, dict) and n.get("empire_name")
    }
    # Build lookup for current neighbor directions
    curr_neighbor_dir = {
        n.get("empire_name"): n.get("direction", "")
        for n in curr_border
        if isinstance(n, dict) and n.get("empire_name")
    }
    for name in sorted(curr_neighbor_names - prev_neighbor_names)[:3]:
        direction = curr_neighbor_dir.get(name, "")
        dir_text = f" to the {direction}" if direction else ""
        events.append(
            DetectedEvent(
                event_type="new_border_contact",
                summary=f"New border neighbor: {name}{dir_text}",
                data={
                    "empire_name": name,
                    "direction": direction,
                    "from_snapshot_id": from_snapshot_id,
                    "to_snapshot_id": to_snapshot_id,
                },
            )
        )

    # Leader roster events - using snapshot_reader
    prev_leaders = get_player_leaders(prev)
    curr_leaders = get_player_leaders(curr)
    prev_ids = set(prev_leaders.keys())
    curr_ids = set(curr_leaders.keys())

    hired = sorted(curr_ids - prev_ids)[:5]
    removed = sorted(prev_ids - curr_ids)[:5]

    for lid in hired:
        l = curr_leaders.get(lid, {})
        cls = l.get("class") or "leader"
        lvl = l.get("level")
        name = _get_leader_name(l)
        lvl_text = f" (Lv{lvl})" if isinstance(lvl, int) else ""
        events.append(
            DetectedEvent(
                event_type="leader_hired",
                summary=f"Hired {cls}: {name}{lvl_text}",
                data={
                    "leader_id": lid,
                    "class": cls,
                    "level": lvl,
                    "name": l.get("name"),
                    "name_key": l.get("name_key"),
                    "from_snapshot_id": from_snapshot_id,
                    "to_snapshot_id": to_snapshot_id,
                },
            )
        )

    for lid in removed:
        l = prev_leaders.get(lid, {})
        cls = l.get("class") or "leader"
        name = _get_leader_name(l)
        events.append(
            DetectedEvent(
                event_type="leader_removed",
                summary=f"Leader removed: {cls} {name}",
                data={
                    "leader_id": lid,
                    "class": cls,
                    "name": l.get("name"),
                    "name_key": l.get("name_key"),
                    "from_snapshot_id": from_snapshot_id,
                    "to_snapshot_id": to_snapshot_id,
                },
            )
        )

    for lid in sorted(prev_ids & curr_ids):
        before = prev_leaders.get(lid, {})
        after = curr_leaders.get(lid, {})
        if (before.get("death_date") is None) and after.get("death_date"):
            cls = after.get("class") or "leader"
            name = _get_leader_name(after)
            events.append(
                DetectedEvent(
                    event_type="leader_died",
                    summary=f"Leader died: {cls} {name} (death_date {after.get('death_date')})",
                    data={
                        "leader_id": lid,
                        "class": cls,
                        "name": after.get("name"),
                        "name_key": after.get("name_key"),
                        "death_date": after.get("death_date"),
                        "from_snapshot_id": from_snapshot_id,
                        "to_snapshot_id": to_snapshot_id,
                    },
                )
            )

    # Ruler changed detection - using snapshot_reader
    prev_ruler = get_ruler_info(prev)
    curr_ruler = get_ruler_info(curr)
    prev_ruler_id = prev_ruler.get("ruler_id")
    curr_ruler_id = curr_ruler.get("ruler_id")

    if prev_ruler_id is not None and curr_ruler_id is not None and prev_ruler_id != curr_ruler_id:
        old_ruler_died = prev_ruler_id in removed
        if not old_ruler_died and prev_ruler_id in curr_leaders:
            old_ruler_data = curr_leaders.get(prev_ruler_id, {})
            if old_ruler_data.get("death_date"):
                old_ruler_died = True

        if not old_ruler_died:
            prev_name = prev_ruler.get("ruler_name") or f"Ruler #{prev_ruler_id}"
            curr_name = curr_ruler.get("ruler_name") or f"Ruler #{curr_ruler_id}"
            events.append(
                DetectedEvent(
                    event_type="ruler_changed",
                    summary=f"New ruler: {curr_name} (replacing {prev_name})",
                    data={
                        "prev_ruler_id": prev_ruler_id,
                        "prev_ruler_name": prev_name,
                        "new_ruler_id": curr_ruler_id,
                        "new_ruler_name": curr_name,
                        "from_snapshot_id": from_snapshot_id,
                        "to_snapshot_id": to_snapshot_id,
                    },
                )
            )

    # Diplomacy shifts - using snapshot_reader
    prev_allies, prev_rivals, prev_treaties = get_diplomacy_sets(prev)
    curr_allies, curr_rivals, curr_treaties = get_diplomacy_sets(curr)

    # Merge empire names from both snapshots
    empire_names = get_empire_names(prev)
    empire_names.update(get_empire_names(curr))

    for cid in sorted(curr_allies - prev_allies)[:5]:
        empire_name = _get_empire_name(cid, empire_names)
        events.append(
            DetectedEvent(
                event_type="alliance_formed",
                summary=f"Alliance formed with {empire_name}",
                data={
                    "country_id": cid,
                    "empire_name": empire_name,
                    "from_snapshot_id": from_snapshot_id,
                    "to_snapshot_id": to_snapshot_id,
                },
            )
        )
    for cid in sorted(prev_allies - curr_allies)[:5]:
        empire_name = _get_empire_name(cid, empire_names)
        events.append(
            DetectedEvent(
                event_type="alliance_ended",
                summary=f"Alliance ended with {empire_name}",
                data={
                    "country_id": cid,
                    "empire_name": empire_name,
                    "from_snapshot_id": from_snapshot_id,
                    "to_snapshot_id": to_snapshot_id,
                },
            )
        )
    for cid in sorted(curr_rivals - prev_rivals)[:5]:
        empire_name = _get_empire_name(cid, empire_names)
        events.append(
            DetectedEvent(
                event_type="rivalry_declared",
                summary=f"Rivalry declared with {empire_name}",
                data={
                    "country_id": cid,
                    "empire_name": empire_name,
                    "from_snapshot_id": from_snapshot_id,
                    "to_snapshot_id": to_snapshot_id,
                },
            )
        )
    for cid in sorted(prev_rivals - curr_rivals)[:5]:
        empire_name = _get_empire_name(cid, empire_names)
        events.append(
            DetectedEvent(
                event_type="rivalry_ended",
                summary=f"Rivalry ended with {empire_name}",
                data={
                    "country_id": cid,
                    "empire_name": empire_name,
                    "from_snapshot_id": from_snapshot_id,
                    "to_snapshot_id": to_snapshot_id,
                },
            )
        )

    for treaty, curr_set in curr_treaties.items():
        prev_set = prev_treaties.get(treaty, set())
        for cid in sorted(curr_set - prev_set)[:5]:
            empire_name = _get_empire_name(cid, empire_names)
            events.append(
                DetectedEvent(
                    event_type="treaty_signed",
                    summary=f"Treaty signed ({treaty}) with {empire_name}",
                    data={
                        "treaty": treaty,
                        "country_id": cid,
                        "empire_name": empire_name,
                        "from_snapshot_id": from_snapshot_id,
                        "to_snapshot_id": to_snapshot_id,
                    },
                )
            )
        for cid in sorted(prev_set - curr_set)[:5]:
            empire_name = _get_empire_name(cid, empire_names)
            events.append(
                DetectedEvent(
                    event_type="treaty_ended",
                    summary=f"Treaty ended ({treaty}) with {empire_name}",
                    data={
                        "treaty": treaty,
                        "country_id": cid,
                        "empire_name": empire_name,
                        "from_snapshot_id": from_snapshot_id,
                        "to_snapshot_id": to_snapshot_id,
                    },
                )
            )

    # First contact detection - using snapshot_reader
    prev_known = get_known_empire_ids(prev)
    curr_known = get_known_empire_ids(curr)
    new_contacts = sorted(curr_known - prev_known)[:5]
    for cid in new_contacts:
        empire_name = _get_empire_name(cid, empire_names)
        events.append(
            DetectedEvent(
                event_type="first_contact",
                summary=f"First contact with {empire_name}",
                data={
                    "country_id": cid,
                    "empire_name": empire_name,
                    "from_snapshot_id": from_snapshot_id,
                    "to_snapshot_id": to_snapshot_id,
                },
            )
        )

    # Subject/vassal changes - using snapshot_reader
    prev_our_subjects, prev_our_overlords = get_subject_sets(prev)
    curr_our_subjects, curr_our_overlords = get_subject_sets(curr)

    # Merge subject details from both snapshots for preset info
    subject_detail_map = get_subject_details(prev)
    subject_detail_map.update(get_subject_details(curr))

    for cid in sorted(curr_our_subjects - prev_our_subjects)[:5]:
        empire_name = _get_empire_name(cid, empire_names)
        detail = subject_detail_map.get(cid, {})
        preset = detail.get("preset", "subject")
        events.append(
            DetectedEvent(
                event_type="subject_gained",
                summary=f"New {preset}: {empire_name}",
                data={
                    "country_id": cid,
                    "empire_name": empire_name,
                    "preset": preset,
                    "from_snapshot_id": from_snapshot_id,
                    "to_snapshot_id": to_snapshot_id,
                },
            )
        )
    for cid in sorted(prev_our_subjects - curr_our_subjects)[:5]:
        empire_name = _get_empire_name(cid, empire_names)
        detail = subject_detail_map.get(cid, {})
        preset = detail.get("preset", "subject")
        events.append(
            DetectedEvent(
                event_type="subject_lost",
                summary=f"Lost {preset}: {empire_name}",
                data={
                    "country_id": cid,
                    "empire_name": empire_name,
                    "preset": preset,
                    "from_snapshot_id": from_snapshot_id,
                    "to_snapshot_id": to_snapshot_id,
                },
            )
        )
    for cid in sorted(curr_our_overlords - prev_our_overlords)[:5]:
        empire_name = _get_empire_name(cid, empire_names)
        detail = subject_detail_map.get(cid, {})
        preset = detail.get("preset", "overlord")
        events.append(
            DetectedEvent(
                event_type="became_subject",
                summary=f"Became {preset} of {empire_name}",
                data={
                    "country_id": cid,
                    "empire_name": empire_name,
                    "preset": preset,
                    "from_snapshot_id": from_snapshot_id,
                    "to_snapshot_id": to_snapshot_id,
                },
            )
        )
    for cid in sorted(prev_our_overlords - curr_our_overlords)[:5]:
        empire_name = _get_empire_name(cid, empire_names)
        detail = subject_detail_map.get(cid, {})
        preset = detail.get("preset", "overlord")
        events.append(
            DetectedEvent(
                event_type="freed_from_subject",
                summary=f"Freed from {empire_name}",
                data={
                    "country_id": cid,
                    "empire_name": empire_name,
                    "preset": preset,
                    "from_snapshot_id": from_snapshot_id,
                    "to_snapshot_id": to_snapshot_id,
                },
            )
        )

    # Game phase milestones - using snapshot_reader
    prev_year = _parse_year(prev.get("meta", {}).get("date"))
    curr_year = _parse_year(curr.get("meta", {}).get("date"))
    galaxy = get_galaxy(curr) or get_galaxy(prev)
    if prev_year is not None and curr_year is not None and isinstance(galaxy, dict):
        mid = galaxy.get("mid_game_start")
        end = galaxy.get("end_game_start")
        try:
            mid_year = 2200 + int(mid) if mid is not None else None
        except Exception:
            mid_year = None
        try:
            end_year = 2200 + int(end) if end is not None else None
        except Exception:
            end_year = None

        if mid_year is not None and prev_year < mid_year <= curr_year:
            events.append(
                DetectedEvent(
                    event_type="milestone_midgame",
                    summary=f"Entered Midgame (year {mid_year})",
                    data={
                        "milestone_year": mid_year,
                        "from_snapshot_id": from_snapshot_id,
                        "to_snapshot_id": to_snapshot_id,
                    },
                )
            )
        if end_year is not None and prev_year < end_year <= curr_year:
            events.append(
                DetectedEvent(
                    event_type="milestone_endgame",
                    summary=f"Entered Endgame (year {end_year})",
                    data={
                        "milestone_year": end_year,
                        "from_snapshot_id": from_snapshot_id,
                        "to_snapshot_id": to_snapshot_id,
                    },
                )
            )

    # ===== PHASE 6 EXPANDED EVENTS - using snapshot_reader =====

    # Technology researched (individual techs)
    prev_techs = get_tech_list(prev)
    curr_techs = get_tech_list(curr)
    new_techs = sorted(curr_techs - prev_techs)[:10]
    for tech in new_techs:
        display_name = tech.replace("tech_", "").replace("_", " ").title()
        events.append(
            DetectedEvent(
                event_type="technology_researched",
                summary=f"Researched: {display_name}",
                data={
                    "tech": tech,
                    "from_snapshot_id": from_snapshot_id,
                    "to_snapshot_id": to_snapshot_id,
                },
            )
        )

    # System count changes
    prev_systems = get_system_count(prev)
    curr_systems = get_system_count(curr)
    if prev_systems is not None and curr_systems is not None and prev_systems != curr_systems:
        diff = curr_systems - prev_systems
        if diff > 0:
            events.append(
                DetectedEvent(
                    event_type="systems_gained",
                    summary=f"Gained {diff} system{'s' if diff != 1 else ''} ({prev_systems} → {curr_systems})",
                    data={
                        "before": prev_systems,
                        "after": curr_systems,
                        "delta": diff,
                        "from_snapshot_id": from_snapshot_id,
                        "to_snapshot_id": to_snapshot_id,
                    },
                )
            )
        else:
            events.append(
                DetectedEvent(
                    event_type="systems_lost",
                    summary=f"Lost {-diff} system{'s' if diff != -1 else ''} ({prev_systems} → {curr_systems})",
                    data={
                        "before": prev_systems,
                        "after": curr_systems,
                        "delta": diff,
                        "from_snapshot_id": from_snapshot_id,
                        "to_snapshot_id": to_snapshot_id,
                    },
                )
            )

    # Policy changes
    prev_policies = get_policies(prev)
    curr_policies = get_policies(curr)
    for policy, new_val in curr_policies.items():
        old_val = prev_policies.get(policy)
        if old_val is not None and old_val != new_val:
            events.append(
                DetectedEvent(
                    event_type="policy_changed",
                    summary=f"Policy changed: {policy} ({old_val} → {new_val})",
                    data={
                        "policy": policy,
                        "before": old_val,
                        "after": new_val,
                        "from_snapshot_id": from_snapshot_id,
                        "to_snapshot_id": to_snapshot_id,
                    },
                )
            )

    # Edict changes
    prev_edicts = get_edicts(prev)
    curr_edicts = get_edicts(curr)
    activated = sorted(curr_edicts - prev_edicts)[:5]
    expired = sorted(prev_edicts - curr_edicts)[:5]
    for edict in activated:
        display_name = edict.replace("edict_", "").replace("_", " ").title()
        events.append(
            DetectedEvent(
                event_type="edict_activated",
                summary=f"Edict activated: {display_name}",
                data={
                    "edict": edict,
                    "from_snapshot_id": from_snapshot_id,
                    "to_snapshot_id": to_snapshot_id,
                },
            )
        )
    for edict in expired:
        display_name = edict.replace("edict_", "").replace("_", " ").title()
        events.append(
            DetectedEvent(
                event_type="edict_expired",
                summary=f"Edict expired: {display_name}",
                data={
                    "edict": edict,
                    "from_snapshot_id": from_snapshot_id,
                    "to_snapshot_id": to_snapshot_id,
                },
            )
        )

    # Ascension perk selection
    prev_perks = get_ascension_perk_set(prev)
    curr_perks = get_ascension_perk_set(curr)
    new_perks = sorted(curr_perks - prev_perks)[:5]
    for perk in new_perks:
        perk_name = _format_perk_name(perk)
        is_notable = perk in _NOTABLE_ASCENSION_PERKS
        events.append(
            DetectedEvent(
                event_type="ascension_perk_selected",
                summary=f"Selected ascension perk: {perk_name}",
                data={
                    "perk": perk,
                    "perk_name": perk_name,
                    "notable": is_notable,
                    "from_snapshot_id": from_snapshot_id,
                    "to_snapshot_id": to_snapshot_id,
                },
            )
        )

    # Megastructure progress
    prev_megas = get_megastructures_by_id(prev)
    curr_megas = get_megastructures_by_id(curr)
    for mega_id, curr_mega in curr_megas.items():
        prev_mega = prev_megas.get(mega_id)
        mega_type = curr_mega.get("type", "megastructure")
        display_type = mega_type.replace("_", " ").title()

        if prev_mega is None:
            events.append(
                DetectedEvent(
                    event_type="megastructure_started",
                    summary=f"Megastructure started: {display_type}",
                    data={
                        "mega_id": mega_id,
                        "type": mega_type,
                        "stage": curr_mega.get("stage", 0),
                        "from_snapshot_id": from_snapshot_id,
                        "to_snapshot_id": to_snapshot_id,
                    },
                )
            )
        else:
            prev_stage = prev_mega.get("stage", 0)
            curr_stage = curr_mega.get("stage", 0)
            if curr_stage > prev_stage:
                events.append(
                    DetectedEvent(
                        event_type="megastructure_upgraded",
                        summary=f"Megastructure upgraded: {display_type} (stage {prev_stage} → {curr_stage})",
                        data={
                            "mega_id": mega_id,
                            "type": mega_type,
                            "prev_stage": prev_stage,
                            "stage": curr_stage,
                            "from_snapshot_id": from_snapshot_id,
                            "to_snapshot_id": to_snapshot_id,
                        },
                    )
                )

    # Crisis events
    prev_crisis = get_crisis(prev)
    curr_crisis = get_crisis(curr)
    if not prev_crisis.get("active") and curr_crisis.get("active"):
        crisis_type = curr_crisis.get("type", "unknown")
        events.append(
            DetectedEvent(
                event_type="crisis_started",
                summary=f"Crisis begun: {crisis_type.replace('_', ' ').title()}",
                data={
                    "crisis_type": crisis_type,
                    "from_snapshot_id": from_snapshot_id,
                    "to_snapshot_id": to_snapshot_id,
                },
            )
        )
    elif prev_crisis.get("active") and not curr_crisis.get("active"):
        crisis_type = prev_crisis.get("type", "unknown")
        events.append(
            DetectedEvent(
                event_type="crisis_defeated",
                summary=f"Crisis defeated: {crisis_type.replace('_', ' ').title()}",
                data={
                    "crisis_type": crisis_type,
                    "from_snapshot_id": from_snapshot_id,
                    "to_snapshot_id": to_snapshot_id,
                },
            )
        )

    # L-Gate opened detection
    prev_lgate = get_lgate(prev)
    curr_lgate = get_lgate(curr)
    if not prev_lgate.get("opened") and curr_lgate.get("opened"):
        events.append(
            DetectedEvent(
                event_type="lgate_opened",
                summary="The L-Gate has been opened!",
                data={
                    "from_snapshot_id": from_snapshot_id,
                    "to_snapshot_id": to_snapshot_id,
                },
            )
        )

    # Crisis level increased (Become the Crisis path)
    prev_menace = get_menace(prev)
    curr_menace = get_menace(curr)
    prev_crisis_level = prev_menace.get("crisis_level", 0)
    curr_crisis_level = curr_menace.get("crisis_level", 0)
    if curr_menace.get("has_crisis_perk") and curr_crisis_level > prev_crisis_level:
        if curr_crisis_level == 5:
            summary = "Became the Crisis! (level 5 - Aetherophasic Engine unlocked)"
        else:
            summary = f"Crisis level increased to {curr_crisis_level}"
        events.append(
            DetectedEvent(
                event_type="crisis_level_increased",
                summary=summary,
                data={
                    "prev_level": prev_crisis_level,
                    "new_level": curr_crisis_level,
                    "menace_level": curr_menace.get("menace_level", 0),
                    "from_snapshot_id": from_snapshot_id,
                    "to_snapshot_id": to_snapshot_id,
                },
            )
        )

    # Fallen Empire awakening detection
    prev_fe = get_fallen_empires_by_name(prev)
    curr_fe = get_fallen_empires_by_name(curr)

    for name, empire in curr_fe.items():
        if empire.get("status") == "awakened":
            prev_empire = prev_fe.get(name, {})
            if prev_empire.get("status") == "dormant":
                archetype = empire.get("archetype", "Unknown")
                military_power = empire.get("military_power")
                power_text = f" ({military_power:,.0f} power)" if military_power else ""
                events.append(
                    DetectedEvent(
                        event_type="fallen_empire_awakened",
                        summary=f"Fallen Empire awakened: {name} ({archetype}){power_text}",
                        data={
                            "name": name,
                            "archetype": archetype,
                            "ethics": empire.get("ethics"),
                            "military_power": military_power,
                            "from_snapshot_id": from_snapshot_id,
                            "to_snapshot_id": to_snapshot_id,
                        },
                    )
                )

    # War in Heaven detection
    prev_fe_data = get_fallen_empires(prev)
    curr_fe_data = get_fallen_empires(curr)
    prev_war_in_heaven = prev_fe_data.get("war_in_heaven", False)
    curr_war_in_heaven = curr_fe_data.get("war_in_heaven", False)
    if not prev_war_in_heaven and curr_war_in_heaven:
        awakened_names = [name for name, e in curr_fe.items() if e.get("status") == "awakened"]
        events.append(
            DetectedEvent(
                event_type="war_in_heaven_started",
                summary="War in Heaven has begun! Two Awakened Empires are at war.",
                data={
                    "awakened_empires": awakened_names,
                    "from_snapshot_id": from_snapshot_id,
                    "to_snapshot_id": to_snapshot_id,
                },
            )
        )

    # Great Khan spawn/death detection
    prev_khan = get_great_khan(prev)
    curr_khan = get_great_khan(curr)

    prev_khan_risen = prev_khan.get("khan_risen", False)
    curr_khan_risen = curr_khan.get("khan_risen", False)
    curr_khan_status = curr_khan.get("khan_status")

    if not prev_khan_risen and curr_khan_risen:
        events.append(
            DetectedEvent(
                event_type="great_khan_spawned",
                summary="The Great Khan has arisen from the Marauders!",
                data={
                    "khan_country_id": curr_khan.get("khan_country_id"),
                    "from_snapshot_id": from_snapshot_id,
                    "to_snapshot_id": to_snapshot_id,
                },
            )
        )

    prev_khan_status = prev_khan.get("khan_status")
    if prev_khan_status == "active" and curr_khan_status == "defeated":
        events.append(
            DetectedEvent(
                event_type="great_khan_died",
                summary="The Great Khan has fallen!",
                data={
                    "khan_country_id": prev_khan.get("khan_country_id"),
                    "from_snapshot_id": from_snapshot_id,
                    "to_snapshot_id": to_snapshot_id,
                },
            )
        )

    # Galactic Community join/leave detection
    prev_gc = get_galactic_community(prev)
    curr_gc = get_galactic_community(curr)

    prev_member = prev_gc.get("member", False)
    curr_member = curr_gc.get("member", False)
    if not prev_member and curr_member:
        events.append(
            DetectedEvent(
                event_type="galactic_community_joined",
                summary="Joined the Galactic Community",
                data={
                    "members_count": curr_gc.get("members_count", 0),
                    "from_snapshot_id": from_snapshot_id,
                    "to_snapshot_id": to_snapshot_id,
                },
            )
        )

    if prev_member and not curr_member:
        events.append(
            DetectedEvent(
                event_type="galactic_community_left",
                summary="Left the Galactic Community",
                data={
                    "from_snapshot_id": from_snapshot_id,
                    "to_snapshot_id": to_snapshot_id,
                },
            )
        )

    prev_council = prev_gc.get("council_member", False)
    curr_council = curr_gc.get("council_member", False)
    if not prev_council and curr_council:
        events.append(
            DetectedEvent(
                event_type="galactic_community_council_joined",
                summary="Joined the Galactic Council",
                data={
                    "from_snapshot_id": from_snapshot_id,
                    "to_snapshot_id": to_snapshot_id,
                },
            )
        )

    # Tradition tree completion detection
    prev_finished_trees = get_finished_traditions(prev)
    curr_finished_trees = get_finished_traditions(curr)
    new_finished_trees = sorted(curr_finished_trees - prev_finished_trees)[:5]
    for tree in new_finished_trees:
        tree_name = _format_tradition_tree_name(tree)
        events.append(
            DetectedEvent(
                event_type="tradition_tree_completed",
                summary=f"Completed the {tree_name} tradition tree",
                data={
                    "tree": tree,
                    "tree_name": tree_name,
                    "from_snapshot_id": from_snapshot_id,
                    "to_snapshot_id": to_snapshot_id,
                },
            )
        )

    # Precursor homeworld discovered detection
    prev_homeworlds = get_discovered_homeworlds(prev)
    curr_homeworlds = get_discovered_homeworlds(curr)
    new_homeworlds = sorted(curr_homeworlds - prev_homeworlds)[:3]
    for precursor_key in new_homeworlds:
        precursor_name = _get_precursor_name(precursor_key, curr)
        events.append(
            DetectedEvent(
                event_type="precursor_homeworld_discovered",
                summary=f"Discovered the {precursor_name} homeworld",
                data={
                    "precursor_key": precursor_key,
                    "precursor_name": precursor_name,
                    "from_snapshot_id": from_snapshot_id,
                    "to_snapshot_id": to_snapshot_id,
                },
            )
        )

    return events
