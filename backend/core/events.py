"""
Event detection for Phase 3 (Milestone 3).

Derives human-readable events from two snapshots (previous vs current).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DetectedEvent:
    event_type: str
    summary: str
    data: dict[str, Any]


def _safe_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


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
        # Common patterns: {"name": "..."} or {"federation_name": "..."}
        for key in ("name", "federation_name", "federation", "id"):
            val = fed.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        return "Federation"
    return "Federation"


def _extract_war_names(briefing: dict[str, Any]) -> set[str]:
    history = briefing.get("history", {}) if isinstance(briefing, dict) else {}
    wars = history.get("wars")
    if not isinstance(wars, dict):
        return set()
    names = wars.get("wars") or wars.get("names") or []
    if not isinstance(names, list):
        return set()
    return {str(n).strip() for n in names if str(n).strip()}


def _extract_player_leaders(briefing: dict[str, Any]) -> dict[int, dict[str, Any]]:
    history = briefing.get("history", {}) if isinstance(briefing, dict) else {}
    leaders = history.get("leaders") if isinstance(history, dict) else None
    if not isinstance(leaders, dict):
        return {}
    items = leaders.get("leaders")
    if not isinstance(items, list):
        return {}
    out: dict[int, dict[str, Any]] = {}
    for l in items:
        if not isinstance(l, dict):
            continue
        lid = l.get("id")
        try:
            lid_int = int(lid)
        except Exception:
            continue
        out[lid_int] = l
    return out


def _get_leader_name(leader: dict[str, Any]) -> str:
    """Get best available leader name with fallback chain.

    Priority: name (resolved) → name_key (with cleanup) → #{id}

    This ensures Chronicle and event summaries use human-readable names
    instead of placeholders like %LEADER_2%.
    """
    # Prefer resolved name (from signals/Rust extraction)
    name = leader.get('name')
    if name and isinstance(name, str) and name.strip():
        return name.strip()

    # Fallback to name_key with cleanup
    name_key = leader.get('name_key')
    if name_key and isinstance(name_key, str):
        key = name_key.strip()
        # Clean up common patterns (same logic as _extract_leader_name_rust)
        if '_CHR_' in key:
            return key.split('_CHR_')[-1]
        if key.startswith('NAME_'):
            return key[5:].replace('_', ' ')
        # Return as-is if not a placeholder template
        if not key.startswith('%'):
            return key

    # Final fallback to ID
    lid = leader.get('id')
    return f"#{lid}" if lid is not None else "#unknown"


def _extract_diplomacy_sets(briefing: dict[str, Any]) -> tuple[set[int], set[int], dict[str, set[int]]]:
    history = briefing.get("history", {}) if isinstance(briefing, dict) else {}
    dip = history.get("diplomacy") if isinstance(history, dict) else None
    if not isinstance(dip, dict):
        return set(), set(), {}

    def _to_int_set(value: Any) -> set[int]:
        if not isinstance(value, list):
            return set()
        out: set[int] = set()
        for v in value:
            try:
                out.add(int(v))
            except Exception:
                continue
        return out

    allies = _to_int_set(dip.get("allies"))
    rivals = _to_int_set(dip.get("rivals"))
    treaties_raw = dip.get("treaties") if isinstance(dip.get("treaties"), dict) else {}
    treaties: dict[str, set[int]] = {}
    for k, v in treaties_raw.items():
        treaties[str(k)] = _to_int_set(v)

    return allies, rivals, treaties


def _parse_year(date_str: Any) -> int | None:
    if not isinstance(date_str, str):
        return None
    if len(date_str) < 4:
        return None
    try:
        return int(date_str[:4])
    except Exception:
        return None


def _extract_galaxy_settings(briefing: dict[str, Any]) -> dict[str, Any]:
    history = briefing.get("history", {}) if isinstance(briefing, dict) else {}
    galaxy = history.get("galaxy") if isinstance(history, dict) else None
    return galaxy if isinstance(galaxy, dict) else {}


# ===== PHASE 6 HELPER FUNCTIONS =====

def _extract_tech_list(briefing: dict[str, Any]) -> set[str]:
    """Extract the set of completed technology names."""
    history = briefing.get("history", {}) if isinstance(briefing, dict) else {}
    techs = history.get("techs") if isinstance(history, dict) else None
    if not isinstance(techs, dict):
        return set()
    tech_list = techs.get("techs") or []
    if not isinstance(tech_list, list):
        return set()
    return {str(t).strip() for t in tech_list if str(t).strip()}


def _extract_system_count(briefing: dict[str, Any]) -> int | None:
    """Extract the total system count."""
    history = briefing.get("history", {}) if isinstance(briefing, dict) else {}
    systems = history.get("systems") if isinstance(history, dict) else None
    if not isinstance(systems, dict):
        return None
    count = systems.get("system_count") or systems.get("celestial_bodies")
    try:
        return int(count) if count is not None else None
    except Exception:
        return None


def _extract_policies(briefing: dict[str, Any]) -> dict[str, str]:
    """Extract policy settings."""
    history = briefing.get("history", {}) if isinstance(briefing, dict) else {}
    policies = history.get("policies") if isinstance(history, dict) else None
    if not isinstance(policies, dict):
        return {}
    policy_dict = policies.get("policies") or {}
    if not isinstance(policy_dict, dict):
        return {}
    return {str(k): str(v) for k, v in policy_dict.items()}


def _extract_edicts(briefing: dict[str, Any]) -> set[str]:
    """Extract active edict names."""
    history = briefing.get("history", {}) if isinstance(briefing, dict) else {}
    edicts = history.get("edicts") if isinstance(history, dict) else None
    if not isinstance(edicts, dict):
        return set()
    edict_list = edicts.get("edicts") or []
    if not isinstance(edict_list, list):
        return set()
    return {str(e).strip() for e in edict_list if str(e).strip()}


def _extract_megastructures(briefing: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """Extract megastructure data keyed by ID."""
    history = briefing.get("history", {}) if isinstance(briefing, dict) else {}
    megas = history.get("megastructures") if isinstance(history, dict) else None
    if not isinstance(megas, dict):
        return {}
    mega_list = megas.get("megastructures") or []
    if not isinstance(mega_list, list):
        return {}
    result: dict[int, dict[str, Any]] = {}
    for m in mega_list:
        if not isinstance(m, dict):
            continue
        mid = m.get("id")
        try:
            mid_int = int(mid)
        except Exception:
            continue
        result[mid_int] = m
    return result


def _extract_crisis(briefing: dict[str, Any]) -> dict[str, Any]:
    """Extract crisis status."""
    history = briefing.get("history", {}) if isinstance(briefing, dict) else {}
    crisis = history.get("crisis") if isinstance(history, dict) else None
    if not isinstance(crisis, dict):
        return {"active": False, "type": None}
    return crisis


def _extract_fallen_empires(briefing: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Extract all fallen empires keyed by name."""
    history = briefing.get("history", {}) if isinstance(briefing, dict) else {}
    fe_data = history.get("fallen_empires") if isinstance(history, dict) else None
    if not isinstance(fe_data, dict):
        return {}
    empire_list = fe_data.get("fallen_empires") or []
    if not isinstance(empire_list, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for e in empire_list:
        if not isinstance(e, dict):
            continue
        name = e.get("name")
        if not name:
            continue
        result[str(name)] = e
    return result


def compute_events(
    *,
    prev: dict[str, Any],
    curr: dict[str, Any],
    from_snapshot_id: int,
    to_snapshot_id: int,
) -> list[DetectedEvent]:
    """Compute a list of derived events between two briefings."""
    events: list[DetectedEvent] = []

    prev_mil = _safe_int(prev.get("military", {}).get("military_power"))
    curr_mil = _safe_int(curr.get("military", {}).get("military_power"))
    if prev_mil is not None and curr_mil is not None and prev_mil != curr_mil:
        pct = _pct_change(prev_mil, curr_mil)
        delta = curr_mil - prev_mil
        # Only log if meaningful: >=15% and >=2000 absolute, or >=10000 absolute.
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

    # Military fleet count change (actual combat fleets, not starbases/civilian)
    # Only log if meaningful change (>= 2 fleets gained or lost)
    prev_mil_fleets = _safe_int(prev.get("military", {}).get("military_fleets"))
    curr_mil_fleets = _safe_int(curr.get("military", {}).get("military_fleets"))
    if prev_mil_fleets is not None and curr_mil_fleets is not None and prev_mil_fleets != curr_mil_fleets:
        diff = curr_mil_fleets - prev_mil_fleets
        if abs(diff) >= 2:  # Threshold to avoid noise
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

    prev_colonies = _safe_int(prev.get("territory", {}).get("colonies", {}).get("total_count"))
    curr_colonies = _safe_int(curr.get("territory", {}).get("colonies", {}).get("total_count"))
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

    prev_tech = _safe_int(prev.get("technology", {}).get("tech_count"))
    curr_tech = _safe_int(curr.get("technology", {}).get("tech_count"))
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

    prev_energy = _safe_float(prev.get("economy", {}).get("net_monthly", {}).get("energy"))
    curr_energy = _safe_float(curr.get("economy", {}).get("net_monthly", {}).get("energy"))
    if prev_energy is not None and curr_energy is not None and prev_energy != curr_energy:
        delta = curr_energy - prev_energy
        pct = _pct_change(prev_energy, curr_energy)
        if _sign_changed(prev_energy, curr_energy) or abs(delta) >= max(20.0, abs(prev_energy) * 0.25):
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

    prev_alloys = _safe_float(prev.get("economy", {}).get("net_monthly", {}).get("alloys"))
    curr_alloys = _safe_float(curr.get("economy", {}).get("net_monthly", {}).get("alloys"))
    if prev_alloys is not None and curr_alloys is not None and prev_alloys != curr_alloys:
        delta = curr_alloys - prev_alloys
        pct = _pct_change(prev_alloys, curr_alloys)
        if _sign_changed(prev_alloys, curr_alloys) or abs(delta) >= max(5.0, abs(prev_alloys) * 0.25):
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

    # Economy bottlenecks players care about: CG, food, minerals.
    for key, label, min_abs in [
        ("consumer_goods", "Consumer Goods net", 5.0),
        ("food", "Food net", 5.0),
        ("minerals", "Minerals net", 20.0),
    ]:
        prev_val = _safe_float(prev.get("economy", {}).get("net_monthly", {}).get(key))
        curr_val = _safe_float(curr.get("economy", {}).get("net_monthly", {}).get(key))
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

    prev_fed = _normalize_federation(prev)
    curr_fed = _normalize_federation(curr)
    if prev_fed != curr_fed:
        if prev_fed is None and curr_fed is not None:
            events.append(
                DetectedEvent(
                    event_type="federation_joined",
                    summary=f"Joined a federation: {curr_fed}",
                    data={"before": None, "after": curr_fed, "from_snapshot_id": from_snapshot_id, "to_snapshot_id": to_snapshot_id},
                )
            )
        elif prev_fed is not None and curr_fed is None:
            events.append(
                DetectedEvent(
                    event_type="federation_left",
                    summary=f"Left federation: {prev_fed}",
                    data={"before": prev_fed, "after": None, "from_snapshot_id": from_snapshot_id, "to_snapshot_id": to_snapshot_id},
                )
            )
        elif prev_fed and curr_fed:
            events.append(
                DetectedEvent(
                    event_type="federation_changed",
                    summary=f"Federation changed: {prev_fed} → {curr_fed}",
                    data={"before": prev_fed, "after": curr_fed, "from_snapshot_id": from_snapshot_id, "to_snapshot_id": to_snapshot_id},
                )
            )

    prev_wars = _extract_war_names(prev)
    curr_wars = _extract_war_names(curr)
    started = sorted(curr_wars - prev_wars)
    ended = sorted(prev_wars - curr_wars)
    for name in started[:5]:
        events.append(
            DetectedEvent(
                event_type="war_started",
                summary=f"War started: {name}",
                data={"war_name": name, "from_snapshot_id": from_snapshot_id, "to_snapshot_id": to_snapshot_id},
            )
        )
    for name in ended[:5]:
        events.append(
            DetectedEvent(
                event_type="war_ended",
                summary=f"War ended: {name}",
                data={"war_name": name, "from_snapshot_id": from_snapshot_id, "to_snapshot_id": to_snapshot_id},
            )
        )

    # Leader roster events (hire/death/removal)
    prev_leaders = _extract_player_leaders(prev)
    curr_leaders = _extract_player_leaders(curr)
    prev_ids = set(prev_leaders.keys())
    curr_ids = set(curr_leaders.keys())

    hired = sorted(curr_ids - prev_ids)[:5]
    removed = sorted(prev_ids - curr_ids)[:5]

    for lid in hired:
        l = curr_leaders.get(lid, {})
        cls = l.get("class") or "leader"
        lvl = l.get("level")
        name = _get_leader_name(l)  # Prefer resolved name, fallback to name_key
        lvl_text = f" (Lv{lvl})" if isinstance(lvl, int) else ""
        events.append(
            DetectedEvent(
                event_type="leader_hired",
                summary=f"Hired {cls}: {name}{lvl_text}",
                data={"leader_id": lid, "class": cls, "level": lvl, "name": l.get("name"), "name_key": l.get("name_key"), "from_snapshot_id": from_snapshot_id, "to_snapshot_id": to_snapshot_id},
            )
        )

    for lid in removed:
        l = prev_leaders.get(lid, {})
        cls = l.get("class") or "leader"
        name = _get_leader_name(l)  # Prefer resolved name, fallback to name_key
        events.append(
            DetectedEvent(
                event_type="leader_removed",
                summary=f"Leader removed: {cls} {name}",
                data={"leader_id": lid, "class": cls, "name": l.get("name"), "name_key": l.get("name_key"), "from_snapshot_id": from_snapshot_id, "to_snapshot_id": to_snapshot_id},
            )
        )

    for lid in sorted(prev_ids & curr_ids):
        before = prev_leaders.get(lid, {})
        after = curr_leaders.get(lid, {})
        if (before.get("death_date") is None) and after.get("death_date"):
            cls = after.get("class") or "leader"
            name = _get_leader_name(after)  # Prefer resolved name, fallback to name_key
            events.append(
                DetectedEvent(
                    event_type="leader_died",
                    summary=f"Leader died: {cls} {name} (death_date {after.get('death_date')})",
                    data={"leader_id": lid, "class": cls, "name": after.get("name"), "name_key": after.get("name_key"), "death_date": after.get("death_date"), "from_snapshot_id": from_snapshot_id, "to_snapshot_id": to_snapshot_id},
                )
            )

    # Diplomacy shifts (allies/rivals/treaties) from stable country IDs.
    prev_allies, prev_rivals, prev_treaties = _extract_diplomacy_sets(prev)
    curr_allies, curr_rivals, curr_treaties = _extract_diplomacy_sets(curr)

    for cid in sorted(curr_allies - prev_allies)[:5]:
        events.append(
            DetectedEvent(
                event_type="alliance_formed",
                summary=f"Alliance formed with empire #{cid}",
                data={"country_id": cid, "from_snapshot_id": from_snapshot_id, "to_snapshot_id": to_snapshot_id},
            )
        )
    for cid in sorted(prev_allies - curr_allies)[:5]:
        events.append(
            DetectedEvent(
                event_type="alliance_ended",
                summary=f"Alliance ended with empire #{cid}",
                data={"country_id": cid, "from_snapshot_id": from_snapshot_id, "to_snapshot_id": to_snapshot_id},
            )
        )
    for cid in sorted(curr_rivals - prev_rivals)[:5]:
        events.append(
            DetectedEvent(
                event_type="rivalry_declared",
                summary=f"Rivalry declared with empire #{cid}",
                data={"country_id": cid, "from_snapshot_id": from_snapshot_id, "to_snapshot_id": to_snapshot_id},
            )
        )
    for cid in sorted(prev_rivals - curr_rivals)[:5]:
        events.append(
            DetectedEvent(
                event_type="rivalry_ended",
                summary=f"Rivalry ended with empire #{cid}",
                data={"country_id": cid, "from_snapshot_id": from_snapshot_id, "to_snapshot_id": to_snapshot_id},
            )
        )

    for treaty, curr_set in curr_treaties.items():
        prev_set = prev_treaties.get(treaty, set())
        for cid in sorted(curr_set - prev_set)[:5]:
            events.append(
                DetectedEvent(
                    event_type="treaty_signed",
                    summary=f"Treaty signed ({treaty}) with empire #{cid}",
                    data={"treaty": treaty, "country_id": cid, "from_snapshot_id": from_snapshot_id, "to_snapshot_id": to_snapshot_id},
                )
            )
        for cid in sorted(prev_set - curr_set)[:5]:
            events.append(
                DetectedEvent(
                    event_type="treaty_ended",
                    summary=f"Treaty ended ({treaty}) with empire #{cid}",
                    data={"treaty": treaty, "country_id": cid, "from_snapshot_id": from_snapshot_id, "to_snapshot_id": to_snapshot_id},
                )
            )

    # Game phase milestones (midgame/endgame) based on galaxy settings and current year.
    prev_year = _parse_year(prev.get("meta", {}).get("date"))
    curr_year = _parse_year(curr.get("meta", {}).get("date"))
    galaxy = _extract_galaxy_settings(curr) or _extract_galaxy_settings(prev)
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
                    data={"milestone_year": mid_year, "from_snapshot_id": from_snapshot_id, "to_snapshot_id": to_snapshot_id},
                )
            )
        if end_year is not None and prev_year < end_year <= curr_year:
            events.append(
                DetectedEvent(
                    event_type="milestone_endgame",
                    summary=f"Entered Endgame (year {end_year})",
                    data={"milestone_year": end_year, "from_snapshot_id": from_snapshot_id, "to_snapshot_id": to_snapshot_id},
                )
            )

    # ===== PHASE 6 EXPANDED EVENTS =====

    # Technology researched (individual techs, not just count)
    prev_techs = _extract_tech_list(prev)
    curr_techs = _extract_tech_list(curr)
    new_techs = sorted(curr_techs - prev_techs)[:10]  # Cap at 10 to avoid noise
    for tech in new_techs:
        # Format tech name for display (tech_lasers_1 -> Lasers 1)
        display_name = tech.replace("tech_", "").replace("_", " ").title()
        events.append(
            DetectedEvent(
                event_type="technology_researched",
                summary=f"Researched: {display_name}",
                data={"tech": tech, "from_snapshot_id": from_snapshot_id, "to_snapshot_id": to_snapshot_id},
            )
        )

    # System count changes (conquered/lost)
    prev_systems = _extract_system_count(prev)
    curr_systems = _extract_system_count(curr)
    if prev_systems is not None and curr_systems is not None and prev_systems != curr_systems:
        diff = curr_systems - prev_systems
        if diff > 0:
            events.append(
                DetectedEvent(
                    event_type="systems_gained",
                    summary=f"Gained {diff} system{'s' if diff != 1 else ''} ({prev_systems} → {curr_systems})",
                    data={"before": prev_systems, "after": curr_systems, "delta": diff, "from_snapshot_id": from_snapshot_id, "to_snapshot_id": to_snapshot_id},
                )
            )
        else:
            events.append(
                DetectedEvent(
                    event_type="systems_lost",
                    summary=f"Lost {-diff} system{'s' if diff != -1 else ''} ({prev_systems} → {curr_systems})",
                    data={"before": prev_systems, "after": curr_systems, "delta": diff, "from_snapshot_id": from_snapshot_id, "to_snapshot_id": to_snapshot_id},
                )
            )

    # Policy changes
    prev_policies = _extract_policies(prev)
    curr_policies = _extract_policies(curr)
    for policy, new_val in curr_policies.items():
        old_val = prev_policies.get(policy)
        if old_val is not None and old_val != new_val:
            events.append(
                DetectedEvent(
                    event_type="policy_changed",
                    summary=f"Policy changed: {policy} ({old_val} → {new_val})",
                    data={"policy": policy, "before": old_val, "after": new_val, "from_snapshot_id": from_snapshot_id, "to_snapshot_id": to_snapshot_id},
                )
            )

    # Edict changes
    prev_edicts = _extract_edicts(prev)
    curr_edicts = _extract_edicts(curr)
    activated = sorted(curr_edicts - prev_edicts)[:5]
    expired = sorted(prev_edicts - curr_edicts)[:5]
    for edict in activated:
        display_name = edict.replace("edict_", "").replace("_", " ").title()
        events.append(
            DetectedEvent(
                event_type="edict_activated",
                summary=f"Edict activated: {display_name}",
                data={"edict": edict, "from_snapshot_id": from_snapshot_id, "to_snapshot_id": to_snapshot_id},
            )
        )
    for edict in expired:
        display_name = edict.replace("edict_", "").replace("_", " ").title()
        events.append(
            DetectedEvent(
                event_type="edict_expired",
                summary=f"Edict expired: {display_name}",
                data={"edict": edict, "from_snapshot_id": from_snapshot_id, "to_snapshot_id": to_snapshot_id},
            )
        )

    # Megastructure progress
    prev_megas = _extract_megastructures(prev)
    curr_megas = _extract_megastructures(curr)
    for mega_id, curr_mega in curr_megas.items():
        prev_mega = prev_megas.get(mega_id)
        mega_type = curr_mega.get("type", "megastructure")
        display_type = mega_type.replace("_", " ").title()

        if prev_mega is None:
            # New megastructure started
            events.append(
                DetectedEvent(
                    event_type="megastructure_started",
                    summary=f"Megastructure started: {display_type}",
                    data={"mega_id": mega_id, "type": mega_type, "stage": curr_mega.get("stage", 0), "from_snapshot_id": from_snapshot_id, "to_snapshot_id": to_snapshot_id},
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
                        data={"mega_id": mega_id, "type": mega_type, "prev_stage": prev_stage, "stage": curr_stage, "from_snapshot_id": from_snapshot_id, "to_snapshot_id": to_snapshot_id},
                    )
                )

    # Crisis events
    prev_crisis = _extract_crisis(prev)
    curr_crisis = _extract_crisis(curr)
    if not prev_crisis.get("active") and curr_crisis.get("active"):
        crisis_type = curr_crisis.get("type", "unknown")
        events.append(
            DetectedEvent(
                event_type="crisis_started",
                summary=f"Crisis begun: {crisis_type.replace('_', ' ').title()}",
                data={"crisis_type": crisis_type, "from_snapshot_id": from_snapshot_id, "to_snapshot_id": to_snapshot_id},
            )
        )
    elif prev_crisis.get("active") and not curr_crisis.get("active"):
        crisis_type = prev_crisis.get("type", "unknown")
        events.append(
            DetectedEvent(
                event_type="crisis_defeated",
                summary=f"Crisis defeated: {crisis_type.replace('_', ' ').title()}",
                data={"crisis_type": crisis_type, "from_snapshot_id": from_snapshot_id, "to_snapshot_id": to_snapshot_id},
            )
        )

    # Fallen Empire awakening detection
    prev_fe = _extract_fallen_empires(prev)
    curr_fe = _extract_fallen_empires(curr)

    # Detect when a fallen empire changes from dormant to awakened
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

    # War in Heaven detection (two awakened empires fighting)
    prev_war_in_heaven = prev.get("history", {}).get("fallen_empires", {}).get("war_in_heaven", False)
    curr_war_in_heaven = curr.get("history", {}).get("fallen_empires", {}).get("war_in_heaven", False)
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

    return events
