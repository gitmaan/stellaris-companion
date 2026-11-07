"""Nomad empire state: Operational Reserves, Arkships, Waystations and logistics.

Nomads (4.4+) pool Energy Credits and Minerals as Operational Reserves, a
situation whose progress is the pool. Waystations hold collected resources in
their own stockpile until a Logistic Ship or Arkship collects them, so the
empire's monthly Mineral and Energy lines alone do not describe the economy.

Layouts confirmed in real 4.4.6 saves: ``situations.situations.<id>``
(``type``, ``country``, ``progress``, ``last_month_progress``, ``approach``,
``stage``), ``starbase_mgr.starbases.<id>`` (``level``, ``station``),
``ships.<id>`` (``fleet``, ``coordinate``, ``ship_design_implementation``) and
``ship_design.<id>.growth_stages[0].ship_size``. The Nomad-specific keys come
from the game's own definitions and are read defensively.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from stellaris_companion.rust_bridge import ParserError, _get_active_session

logger = logging.getLogger(__name__)

NOMAD_ECONOMY_SITUATION = "situation_nomad_economy"
# Index order of the situation's stages, with the in-game names.
RESERVE_STAGES = ("critical", "low", "medium", "high")
RESERVE_APPROACHES = {
    "situation_nomad_economy_stringent_budget": "conserve",
    "situation_nomad_economy_smooth_spending": "balance",
    "situation_nomad_economy_full_spending": "burn",
    "situation_nomad_economy_harvest_everything": "festival",
}
WAYSTATION_LEVEL_PREFIX = "starbase_level_waystation"
LOGISTIC_SHIP_SIZE = "nomads_constructor"
_ARKSHIP_SIZE = re.compile(r"^(?P<role>[a-z]+)_arkship_tier_(?P<tier>\d+)$")
_NULL_ID = "4294967295"
_MAX_LISTED_WAYSTATIONS = 15


def resource_amounts(value: Any) -> dict[str, float]:
    """Normalise a resource block to ``{resource: amount}``.

    Accepts a mapping, a list of mappings, or a list of ``[resource, amount]``
    pairs, which is how unkeyed Clausewitz blocks such as ``{ { minerals 50 } }``
    can reach JSON.
    """
    amounts: dict[str, float] = {}

    def add(resource: Any, amount: Any) -> None:
        if not isinstance(resource, str) or not resource:
            return
        try:
            number = float(amount)
        except (TypeError, ValueError):
            return
        amounts[resource] = round(amounts.get(resource, 0.0) + number, 2)

    if isinstance(value, dict):
        for resource, amount in value.items():
            add(resource, amount)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                for resource, amount in item.items():
                    add(resource, amount)
            elif isinstance(item, (list, tuple)) and len(item) == 2:
                add(item[0], item[1])
    return {resource: amount for resource, amount in amounts.items() if amount}


def _sum_into(total: dict[str, float], amounts: dict[str, float]) -> None:
    for resource, amount in amounts.items():
        total[resource] = round(total.get(resource, 0.0) + amount, 2)


def _number(value: Any) -> float | None:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


class NomadsMixin:
    """Extract Nomad-specific economy state for the player's empire."""

    def get_nomad_economy(self) -> dict[str, Any]:
        """Return ``{"is_nomadic": bool | None, ...}`` plus Nomad state when nomadic.

        ``is_nomadic`` is True when the player has an Arkship colony or an
        Operational Reserves situation, False when the player only has
        planet-carried colonies, and None when the save cannot tell.
        """
        session = _get_active_session()
        if not session:
            raise ParserError("Rust session required for get_nomad_economy")

        player_id = str(self.get_player_empire_id())
        try:
            refs = self._get_player_colony_resolution().refs
        except Exception as exc:  # colony layout drift must not break the briefing
            logger.warning("Nomad detection could not resolve colonies: %s", exc)
            refs = ()
        arkship_refs = [ref for ref in refs if ref.carrier_type == "ship"]
        reserves_entry = self._find_reserves_situation(session, player_id)

        signals = []
        if arkship_refs:
            signals.append("arkship_colony")
        if reserves_entry is not None:
            signals.append("operational_reserves_situation")
        if not signals:
            settled = any(ref.carrier_type == "planet" for ref in refs)
            return {"is_nomadic": False if settled else None}

        result: dict[str, Any] = {
            "is_nomadic": True,
            "detected_by": signals,
            "operational_reserves": self._reserves_summary(reserves_entry),
        }
        try:
            result.update(self._nomad_fleet_state(session, arkship_refs))
        except Exception as exc:
            logger.warning("Nomad logistics extraction failed: %s", exc)
            result["logistics_unavailable"] = True
        return result

    def _find_reserves_situation(self, session: Any, player_id: str) -> dict | None:
        data = session.extract_sections(["situations"]).get("situations") or {}
        entries = data.get("situations", data) if isinstance(data, dict) else {}
        if not isinstance(entries, dict):
            return None
        for entry in entries.values():
            if (
                isinstance(entry, dict)
                and entry.get("type") == NOMAD_ECONOMY_SITUATION
                and str(entry.get("country")) == player_id
            ):
                return entry
        return None

    @staticmethod
    def _reserves_summary(entry: dict | None) -> dict[str, Any] | None:
        if entry is None:
            return None
        stage = None
        try:
            index = int(entry.get("stage"))
            if 0 <= index < len(RESERVE_STAGES):
                stage = RESERVE_STAGES[index]
        except (TypeError, ValueError):
            pass
        approach = entry.get("approach")
        return {
            "current": _number(entry.get("progress")),
            "monthly_change": _number(entry.get("last_month_progress")),
            "stage": stage,
            "approach": RESERVE_APPROACHES.get(approach, approach),
        }

    def _nomad_fleet_state(self, session: Any, arkship_refs: list) -> dict[str, Any]:
        """Arkships, Waystation stockpiles and Logistic Ship cargo from owned fleets."""
        country = self._get_player_country_entry(self.get_player_empire_id()) or {}
        fleet_ids = self._get_owned_fleet_ids_from_entry(country)
        ship_ids: list[str] = []
        for entry in session.get_entries("fleet", fleet_ids) if fleet_ids else []:
            fleet = entry.get("_value")
            if isinstance(fleet, dict):
                ship_ids.extend(str(ship_id) for ship_id in fleet.get("ships") or [])
        ship_ids.extend(ref.carrier_id for ref in arkship_refs if ref.carrier_id)
        ships = {
            str(entry["_key"]): entry["_value"]
            for entry in (
                session.get_entries("ships", list(dict.fromkeys(ship_ids))) if ship_ids else []
            )
            if isinstance(entry.get("_value"), dict)
        }
        design_ids = {
            str(impl.get("design"))
            for ship in ships.values()
            if isinstance(impl := ship.get("ship_design_implementation"), dict)
            and impl.get("design") is not None
        }
        sizes = self._design_ship_sizes(session, sorted(design_ids))

        def size_of(ship: dict) -> str | None:
            impl = ship.get("ship_design_implementation")
            design = impl.get("design") if isinstance(impl, dict) else None
            return sizes.get(str(design)) if design is not None else None

        arkships = []
        for ref in arkship_refs:
            ship = ships.get(str(ref.carrier_id)) or ref.carrier or {}
            match = _ARKSHIP_SIZE.match(size_of(ship) or "")
            name = ship.get("name") or ref.colony.get("name")
            arkships.append(
                {
                    "name": self.resolve_name(name, default="Arkship", context="generic").display
                    if name
                    else "Arkship",
                    "role": match["role"] if match else None,
                    "tier": int(match["tier"]) if match else None,
                    "system": self._ship_system_name(ship),
                }
            )

        station_ships: dict[str, dict] = {}
        starbases = session.extract_sections(["starbase_mgr"]).get("starbase_mgr") or {}
        for starbase in (starbases.get("starbases") or {}).values():
            if not isinstance(starbase, dict):
                continue
            level = str(starbase.get("level") or "")
            station = str(starbase.get("station"))
            if level.startswith(WAYSTATION_LEVEL_PREFIX) and station in ships:
                station_ships[station] = {"level": level.replace("starbase_level_", "")}

        waystation_total: dict[str, float] = {}
        stations = []
        for ship_id, info in station_ships.items():
            stockpile = resource_amounts(ships[ship_id].get("resources"))
            _sum_into(waystation_total, stockpile)
            stations.append(
                {**info, "system": self._ship_system_name(ships[ship_id]), "stockpile": stockpile}
            )
        stations.sort(key=lambda station: -sum(station["stockpile"].values()))

        logistic_count, cargo = 0, {}
        for ship_id, ship in ships.items():
            if ship_id in station_ships or size_of(ship) != LOGISTIC_SHIP_SIZE:
                continue
            logistic_count += 1
            _sum_into(cargo, resource_amounts(ship.get("resources")))

        return {
            "arkships": arkships,
            "waystations": {
                "count": len(stations),
                "stockpile_total": waystation_total,
                "stations": stations[:_MAX_LISTED_WAYSTATIONS],
            },
            "logistic_ships": {"count": logistic_count, "cargo_total": cargo},
        }

    @staticmethod
    def _design_ship_sizes(session: Any, design_ids: list[str]) -> dict[str, str]:
        sizes: dict[str, str] = {}
        for entry in session.get_entries("ship_design", design_ids) if design_ids else []:
            design = entry.get("_value")
            if not isinstance(design, dict):
                continue
            size = design.get("ship_size")
            stages = design.get("growth_stages")
            if not size and isinstance(stages, list) and stages and isinstance(stages[0], dict):
                size = stages[0].get("ship_size")
            if size:
                sizes[str(entry["_key"])] = str(size)
        return sizes

    def _ship_system_name(self, ship: dict) -> str | None:
        coordinate = ship.get("coordinate")
        origin = coordinate.get("origin") if isinstance(coordinate, dict) else None
        if origin is None or str(origin) == _NULL_ID:
            return None
        try:
            return self._resolve_system_name(int(origin))
        except (TypeError, ValueError):
            return None
