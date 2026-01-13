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

    prev_fleets = _safe_int(prev.get("military", {}).get("fleet_count"))
    curr_fleets = _safe_int(curr.get("military", {}).get("fleet_count"))
    if prev_fleets is not None and curr_fleets is not None and prev_fleets != curr_fleets:
        diff = curr_fleets - prev_fleets
        sign = "+" if diff > 0 else ""
        events.append(
            DetectedEvent(
                event_type="fleet_count_change",
                summary=f"Fleets: {prev_fleets} → {curr_fleets} ({sign}{diff})",
                data={
                    "metric": "fleet_count",
                    "before": prev_fleets,
                    "after": curr_fleets,
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

    return events

