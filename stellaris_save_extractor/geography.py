from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)


class GeographyMixin:
    """Strategic geography: border neighbors, chokepoints, empire centroid."""

    SENTINEL = 4294967295

    def _get_system_owner_map(self) -> dict[str, int]:
        """Return cached system_id -> owner country_id mapping.

        Builds the map on first call via the starbase ownership chain,
        then caches for reuse by geography, starbase defenses, etc.
        """
        if self._system_owner_map_cache is not None:
            return self._system_owner_map_cache
        self._system_owner_map_cache = self._build_system_owner_map(
            self._get_galactic_objects_cached()
        )
        return self._system_owner_map_cache

    def _build_system_owner_map(self, galactic_objects: dict[str, dict]) -> dict[str, int]:
        """Build system_id -> owner country_id mapping via starbase ownership chain.

        Ownership chain: system -> starbase (via galactic_object.starbases) ->
        station ship_id (via starbase_mgr) -> fleet_id (via ships) -> country_id
        (via country.fleets_manager.owned_fleets).
        """
        from stellaris_companion.rust_bridge import _get_active_session, extract_sections

        owner_map: dict[str, int] = {}

        session = _get_active_session()
        if not session:
            return owner_map

        # Step 1: fleet_id -> country_id from cached countries
        fleet_to_country: dict[str, int] = {}
        for cid, cdata in self._get_countries_cached().items():
            fm = cdata.get("fleets_manager", {})
            if not isinstance(fm, dict):
                continue
            owned_fleets = fm.get("owned_fleets", [])
            if not isinstance(owned_fleets, list):
                continue
            for entry in owned_fleets:
                if isinstance(entry, dict):
                    fid = entry.get("fleet")
                    if fid is not None:
                        fleet_to_country[str(fid)] = int(cid)

        # Step 2: starbase -> station ship_id from starbase_mgr
        data = extract_sections(self.gamestate_path, ["starbase_mgr"])
        starbases = data.get("starbase_mgr", {}).get("starbases", {})
        starbase_stations: dict[str, str] = {}  # sb_id -> station ship_id
        for sb_id, sb_data in starbases.items():
            if isinstance(sb_data, dict):
                station = sb_data.get("station")
                if station is not None:
                    starbase_stations[sb_id] = str(station)

        # Step 3: batch lookup station ships -> fleet_id
        all_ship_ids = list(set(starbase_stations.values()))
        ship_to_fleet: dict[str, str] = {}
        if all_ship_ids:
            ship_entries = session.get_entries("ships", all_ship_ids)
            for entry in ship_entries:
                ship_id = entry.get("_key", "")
                ship_data = entry.get("_value")
                if isinstance(ship_data, dict):
                    fleet_id = ship_data.get("fleet")
                    if fleet_id is not None:
                        ship_to_fleet[str(ship_id)] = str(fleet_id)

        # Step 4: system -> starbase -> station -> fleet -> country
        for sys_id, sys_data in galactic_objects.items():
            sbs = sys_data.get("starbases", [])
            if isinstance(sbs, list):
                sb_ids = [str(sb) for sb in sbs]
            elif sbs and str(sbs) != str(self.SENTINEL):
                sb_ids = [str(sbs)]
            else:
                continue

            for sb_id in sb_ids:
                ship_id = starbase_stations.get(sb_id)
                if ship_id:
                    fleet_id = ship_to_fleet.get(ship_id)
                    if fleet_id:
                        country_id = fleet_to_country.get(fleet_id)
                        if country_id is not None:
                            owner_map[sys_id] = country_id
                            break

        return owner_map

    def get_strategic_geography(self) -> dict[str, Any]:
        """Compute spatial intelligence from galactic_object data.

        Returns:
            Dict with:
            - border_neighbors: list of {empire_name, empire_id, direction, shared_border_systems}
            - chokepoints: list of {system_name, system_id, friendly_connections, enemy_neighbors}
            - empire_centroid: {x, y} or None
            - total_player_systems: int
        """
        result: dict[str, Any] = {
            "border_neighbors": [],
            "chokepoints": [],
            "empire_centroid": None,
            "total_player_systems": 0,
        }

        try:
            player_id = self.get_player_empire_id()
        except Exception:
            return result

        country_names = self._get_country_names_map()
        galactic_objects = self._get_galactic_objects_cached()

        if not galactic_objects:
            return result

        # Build ownership via starbase chain (system -> starbase -> ship -> fleet -> country)
        owner_map = self._get_system_owner_map()

        # Build coords, adjacency, and identify player systems
        coords: dict[str, tuple[float, float]] = {}
        adjacency: dict[str, list[str]] = {}  # system_id -> list of neighbor system_ids
        player_systems: list[str] = []

        for sys_id, sys_data in galactic_objects.items():
            # Coordinates
            coordinate = sys_data.get("coordinate")
            if isinstance(coordinate, dict):
                x = coordinate.get("x")
                y = coordinate.get("y")
                if x is not None and y is not None:
                    try:
                        coords[sys_id] = (float(x), float(y))
                    except (ValueError, TypeError):
                        pass

            if owner_map.get(sys_id) == player_id:
                player_systems.append(sys_id)

            # Hyperlane adjacency
            hyperlane = sys_data.get("hyperlane", [])
            if isinstance(hyperlane, dict):
                hyperlane = list(hyperlane.values())
            if not isinstance(hyperlane, list):
                hyperlane = []

            neighbors: list[str] = []
            for lane in hyperlane:
                if isinstance(lane, dict):
                    target = lane.get("to")
                    if target is not None and str(target) != str(self.SENTINEL):
                        neighbors.append(str(target))
            adjacency[sys_id] = neighbors

        result["total_player_systems"] = len(player_systems)

        if not player_systems:
            return result

        # Compute centroid
        centroid_x, centroid_y = self._compute_centroid(player_systems, coords)
        if centroid_x is not None:
            result["empire_centroid"] = {"x": round(centroid_x, 1), "y": round(centroid_y, 1)}

        # Border neighbors: non-player empires sharing a hyperlane border
        border_counts: dict[int, int] = {}  # empire_id -> shared border systems

        for sys_id in player_systems:
            for neighbor_id in adjacency.get(sys_id, []):
                neighbor_owner = owner_map.get(neighbor_id)
                if neighbor_owner is not None and neighbor_owner != player_id:
                    border_counts[neighbor_owner] = border_counts.get(neighbor_owner, 0) + 1

        border_neighbors: list[dict[str, Any]] = []
        for empire_id, shared_count in sorted(border_counts.items(), key=lambda x: -x[1]):
            empire_name = country_names.get(empire_id, f"Empire #{empire_id}")
            direction = ""
            if centroid_x is not None:
                direction = self._compute_empire_direction(
                    empire_id, owner_map, coords, centroid_x, centroid_y
                )
            border_neighbors.append(
                {
                    "empire_name": empire_name,
                    "empire_id": empire_id,
                    "direction": direction,
                    "shared_border_systems": shared_count,
                }
            )

        result["border_neighbors"] = border_neighbors[:15]

        # Chokepoints: border entry point analysis.
        # For each enemy empire, find which player systems they border.
        # If an enemy has <=2 entry points, those systems are chokepoints
        # (mandatory bottlenecks the enemy must pass through).
        player_set = set(player_systems)

        # enemy_empire_id -> set of player system IDs bordering that enemy
        enemy_entry_points: dict[int, set[str]] = {}
        for sys_id in player_systems:
            for neighbor_id in adjacency.get(sys_id, []):
                neighbor_owner = owner_map.get(neighbor_id)
                if neighbor_owner is not None and neighbor_owner != player_id:
                    if neighbor_owner not in enemy_entry_points:
                        enemy_entry_points[neighbor_owner] = set()
                    enemy_entry_points[neighbor_owner].add(sys_id)

        # Collect systems that are chokepoints (entry points for enemies with <=2 borders)
        chokepoint_map: dict[str, list[str]] = {}  # sys_id -> [enemy names]
        for empire_id, entry_systems in enemy_entry_points.items():
            if len(entry_systems) <= 2:
                empire_name = country_names.get(empire_id, f"Empire #{empire_id}")
                for sys_id in entry_systems:
                    if sys_id not in chokepoint_map:
                        chokepoint_map[sys_id] = []
                    chokepoint_map[sys_id].append(empire_name)

        chokepoints: list[dict[str, Any]] = []
        for sys_id, enemy_names in chokepoint_map.items():
            name = self._resolve_system_name(int(sys_id))
            friendly_connections = sum(1 for n in adjacency.get(sys_id, []) if n in player_set)
            chokepoints.append(
                {
                    "system_name": name or f"System #{sys_id}",
                    "system_id": int(sys_id),
                    "friendly_connections": friendly_connections,
                    "enemy_neighbors": enemy_names,
                }
            )

        # Sort by fewest friendly connections (most vulnerable first)
        chokepoints.sort(key=lambda c: c["friendly_connections"])
        result["chokepoints"] = chokepoints[:10]

        return result

    def _resolve_system_name(self, system_id: int) -> str | None:
        """Resolve galactic_object ID to a display name."""
        galactic_objects = self._get_galactic_objects_cached()
        sys_data = galactic_objects.get(str(system_id))
        if not isinstance(sys_data, dict):
            return None

        name_block = sys_data.get("name")
        if name_block is None:
            return None

        return self.resolve_name(
            name_block, default=f"System #{system_id}", context="generic"
        ).display

    def _angle_to_compass(self, dx: float, dy: float) -> str:
        """Convert delta-x, delta-y to 8-point compass direction.

        Stellaris galaxy map: positive-x = west, negative-x = east,
        positive-y = south, negative-y = north.  Negate both axes to
        convert to standard compass orientation.
        """
        angle = math.atan2(-dy, -dx)  # negate both: +x=west, +y=south in Stellaris
        degrees = math.degrees(angle) % 360

        # 8-point compass: each sector is 45 degrees, offset by 22.5
        directions = [
            "east",
            "northeast",
            "north",
            "northwest",
            "west",
            "southwest",
            "south",
            "southeast",
        ]
        index = int((degrees + 22.5) / 45) % 8
        return directions[index]

    def _compute_centroid(
        self, system_ids: list[str], coords: dict[str, tuple[float, float]]
    ) -> tuple[float | None, float | None]:
        """Compute average position of given systems."""
        xs, ys = [], []
        for sid in system_ids:
            if sid in coords:
                xs.append(coords[sid][0])
                ys.append(coords[sid][1])
        if not xs:
            return None, None
        return sum(xs) / len(xs), sum(ys) / len(ys)

    def _compute_empire_direction(
        self,
        empire_id: int,
        owner_map: dict[str, int],
        coords: dict[str, tuple[float, float]],
        centroid_x: float,
        centroid_y: float,
    ) -> str:
        """Compute compass direction from player centroid to another empire's centroid."""
        empire_systems = [sid for sid, owner in owner_map.items() if owner == empire_id]
        ex, ey = self._compute_centroid(empire_systems, coords)
        if ex is None:
            return ""
        return self._angle_to_compass(ex - centroid_x, ey - centroid_y)
