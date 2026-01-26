from __future__ import annotations

import contextlib
import logging

# Rust bridge for fast Clausewitz parsing - session mode required
from rust_bridge import ParserError, _get_active_session

logger = logging.getLogger(__name__)


class MilitaryMixin:
    """Domain methods extracted from the original SaveExtractor."""

    def _resolve_fleet_name(self, name_block: dict | str | None, fleet_id: str) -> str:
        """Resolve a fleet name from its name block structure.

        Fleet names in Stellaris can be:
        - Simple strings
        - Complex key/variables structures like {key="%SEQ%", variables=[{key="num", value={key="1"}}]}

        Args:
            name_block: The name field from fleet data (dict or string)
            fleet_id: Fleet ID for fallback naming

        Returns:
            Human-readable fleet name
        """
        if name_block is None:
            return f"Fleet {fleet_id}"

        if isinstance(name_block, str):
            fleet_name = name_block
        elif isinstance(name_block, dict):
            fleet_name = name_block.get("key", f"Fleet {fleet_id}")
            variables = name_block.get("variables", [])

            # Handle %SEQ% format - extract num variable for fleet number
            if fleet_name == "%SEQ%":
                for var in variables:
                    if isinstance(var, dict) and var.get("key") == "num":
                        value = var.get("value")
                        if isinstance(value, dict):
                            fleet_num = value.get("key", fleet_id)
                        else:
                            fleet_num = value or fleet_id
                        return f"Fleet #{fleet_num}"
                return f"Fleet {fleet_id}"
        else:
            fleet_name = f"Fleet {fleet_id}"

        # Clean up localization keys
        if fleet_name.startswith("shipclass_"):
            fleet_name = fleet_name.replace("shipclass_", "").replace("_name", "").title()
        elif fleet_name.startswith("NAME_"):
            fleet_name = fleet_name.replace("NAME_", "").replace("_", " ")
        elif fleet_name.startswith("TRANS_"):
            fleet_name = "Transport Fleet"
        elif fleet_name.endswith("_FLEET"):
            fleet_name = fleet_name.replace("_FLEET", "").replace("_", " ").title() + " Fleet"

        return fleet_name

    def get_wars(self) -> dict:
        """Get all active wars involving the player with detailed information.

        Returns:
            Dict with detailed war information including:
            - wars: List of detailed war objects with name, dates, participants, battle stats
            - player_at_war: Boolean indicating if player is at war
            - active_war_count: Number of wars the player is in

        Note: War exhaustion is intentionally NOT included in the default output.
        The game calculates exhaustion using factors (attrition, modifiers) not fully
        stored in the save file, so displayed values would be inaccurate and potentially
        misleading. Battle statistics are provided instead as accurate indicators.

        Requires Rust session mode to be active.
        """
        return self._get_wars_rust()

    def _resolve_war_name(self, name_block: dict | str | None, war_id: str) -> str:
        """Resolve a war name from its name block structure.

        Args:
            name_block: The name field from war data
            war_id: War ID for fallback naming

        Returns:
            Human-readable war name
        """
        if name_block is None:
            return f"War #{war_id}"

        if isinstance(name_block, str):
            return name_block

        if isinstance(name_block, dict):
            key = name_block.get("key", f"War #{war_id}")
            # For complex war names with variables, just use the key
            # (most war names are localization keys that aren't resolved in-game anyway)
            return key

        return f"War #{war_id}"

    def _get_wars_rust(self) -> dict:
        """Get war information using Rust parser.

        Requires Rust session mode to be active.
        """
        from date_utils import days_between

        session = _get_active_session()
        if not session:
            raise ParserError("Rust session mode required for get_wars")

        result = {"wars": [], "player_at_war": False, "active_war_count": 0}

        player_id = self.get_player_empire_id()
        current_date = self.get_metadata().get("date", "")

        # Build a country ID -> name mapping for lookups
        country_names = self._get_country_names_map()

        # Iterate through wars using Rust parser (P031: use session.iter_section directly)
        for war_id, war_data in session.iter_section("war"):
            # Skip null/ended wars (value is "none" string)
            if not isinstance(war_data, dict):
                continue

            # Extract attacker country IDs
            attacker_ids = []
            attackers = war_data.get("attackers", [])
            if isinstance(attackers, list):
                for attacker in attackers:
                    if isinstance(attacker, dict):
                        country = attacker.get("country")
                        if country:
                            attacker_ids.append(str(country))

            # Extract defender country IDs
            defender_ids = []
            defenders = war_data.get("defenders", [])
            if isinstance(defenders, list):
                for defender in defenders:
                    if isinstance(defender, dict):
                        country = defender.get("country")
                        if country:
                            defender_ids.append(str(country))

            # Check if player is involved
            player_id_str = str(player_id)
            player_is_attacker = player_id_str in attacker_ids
            player_is_defender = player_id_str in defender_ids

            if not player_is_attacker and not player_is_defender:
                continue  # Player not involved in this war

            # Extract war name
            war_name = self._resolve_war_name(war_data.get("name"), war_id)

            # Extract start date
            start_date = war_data.get("start_date")

            # Extract war goal
            war_goal_block = war_data.get("attacker_war_goal", {})
            war_goal = (
                war_goal_block.get("type", "unknown")
                if isinstance(war_goal_block, dict)
                else "unknown"
            )

            # Build war info
            our_side = "attacker" if player_is_attacker else "defender"

            # Resolve country names
            attacker_names = [country_names.get(int(cid), f"Empire {cid}") for cid in attacker_ids]
            defender_names = [country_names.get(int(cid), f"Empire {cid}") for cid in defender_ids]

            # Calculate duration
            duration_days = None
            if start_date and current_date:
                duration_days = days_between(start_date, current_date)

            # Extract battle statistics from battles block
            battle_stats = self._extract_battle_stats(
                war_data.get("battles", []),
                player_is_attacker,
                attacker_ids,
                defender_ids,
            )

            war_info = {
                "name": war_name,
                "start_date": start_date,
                "duration_days": duration_days,
                "our_side": our_side,
                "participants": {
                    "attackers": attacker_names,
                    "defenders": defender_names,
                },
                "war_goal": war_goal,
                "battle_stats": battle_stats,
                "status": "in_progress",  # All wars in the war section are active
            }

            result["wars"].append(war_info)

        result["active_war_count"] = len(result["wars"])
        result["count"] = len(result["wars"])  # Backward compatibility
        result["player_at_war"] = len(result["wars"]) > 0

        return result

    def _extract_battle_stats(
        self,
        battles: list,
        player_is_attacker: bool,
        attacker_ids: list[str],
        defender_ids: list[str],
    ) -> dict:
        """Extract battle statistics from the battles block.

        Args:
            battles: List of battle records from war data
            player_is_attacker: True if player is on attacker side
            attacker_ids: List of attacker country IDs
            defender_ids: List of defender country IDs

        Returns:
            Dict with battle statistics:
            - total_battles: Total number of battles
            - our_victories: Battles won by our side
            - their_victories: Battles won by their side
            - our_ship_losses: Ships lost by our side
            - their_ship_losses: Ships lost by their side
            - our_army_losses: Armies lost by our side
            - their_army_losses: Armies lost by their side
        """
        stats = {
            "total_battles": 0,
            "our_victories": 0,
            "their_victories": 0,
            "our_ship_losses": 0,
            "their_ship_losses": 0,
            "our_army_losses": 0,
            "their_army_losses": 0,
        }

        if not isinstance(battles, list):
            return stats

        for battle in battles:
            if not isinstance(battle, dict):
                continue

            stats["total_battles"] += 1

            # Determine battle outcome
            # attacker_victory=yes means the battle's attackers won (not war attackers)
            # We need to check who was attacking in THIS battle
            battle_attackers = battle.get("attackers", [])
            battle_defenders = battle.get("defenders", [])
            attacker_victory = battle.get("attacker_victory") == "yes"

            # Convert to string sets for comparison
            if isinstance(battle_attackers, list):
                battle_attacker_ids = {str(a) for a in battle_attackers}
            else:
                battle_attacker_ids = {str(battle_attackers)} if battle_attackers else set()

            if isinstance(battle_defenders, list):
                battle_defender_ids = {str(d) for d in battle_defenders}
            else:
                battle_defender_ids = {str(battle_defenders)} if battle_defenders else set()

            # Check if our side was attacking or defending in this battle
            our_side_ids = set(attacker_ids) if player_is_attacker else set(defender_ids)
            set(defender_ids) if player_is_attacker else set(attacker_ids)

            our_side_was_battle_attacker = bool(our_side_ids & battle_attacker_ids)
            our_side_was_battle_defender = bool(our_side_ids & battle_defender_ids)

            # Determine if we won this battle
            if (
                our_side_was_battle_attacker
                and attacker_victory
                or our_side_was_battle_defender
                and not attacker_victory
            ):
                stats["our_victories"] += 1
            elif our_side_was_battle_attacker or our_side_was_battle_defender:
                # We were involved but didn't win
                stats["their_victories"] += 1

            # Extract losses
            attacker_losses = 0
            defender_losses = 0
            with contextlib.suppress(ValueError, TypeError):
                attacker_losses = int(battle.get("attacker_losses", 0))
            with contextlib.suppress(ValueError, TypeError):
                defender_losses = int(battle.get("defender_losses", 0))

            battle_type = battle.get("type", "ships")

            # Assign losses to our side vs their side
            if our_side_was_battle_attacker:
                our_losses = attacker_losses
                their_losses = defender_losses
            elif our_side_was_battle_defender:
                our_losses = defender_losses
                their_losses = attacker_losses
            else:
                # Battle between other participants, skip loss counting
                continue

            if battle_type == "armies":
                stats["our_army_losses"] += our_losses
                stats["their_army_losses"] += their_losses
            else:  # ships or other
                stats["our_ship_losses"] += our_losses
                stats["their_ship_losses"] += their_losses

        return stats

    def get_fleets(self) -> dict:
        """Get player's fleet information with proper categorization.

        Returns:
            Dict with military fleets, starbases, and civilian fleet counts.
            The 'fleets' list contains actual military combat fleets, not starbases
            or civilian ships (science, construction, transport).

        Requires Rust session mode to be active.
        """
        return self._get_fleets_rust()

    def _get_fleets_rust(self) -> dict:
        """Get fleet information using Rust parser.

        Requires Rust session mode to be active.
        """
        session = _get_active_session()
        if not session:
            raise ParserError("Rust session mode required for get_fleets")

        result = {
            "fleets": [],
            "count": 0,
            "military_fleet_count": 0,
            "starbase_count": 0,
            "civilian_fleet_count": 0,
            "military_ships": 0,
            "total_military_power": 0.0,
        }

        # Get the player's country block to find owned fleets
        player_id = self.get_player_empire_id()
        country_content = self._find_player_country_content(player_id)
        if not country_content:
            return result

        # Get OWNED fleets (not just visible fleets)
        owned_fleet_ids = self._get_owned_fleet_ids(country_content)
        if not owned_fleet_ids:
            return result

        owned_set = set(owned_fleet_ids)
        military_fleets = []
        total_military_power = 0.0
        military_ships = 0
        civilian_count = 0

        # Iterate through fleets using Rust parser (P031: use session.iter_section directly)
        for fleet_id, fleet_data in session.iter_section("fleet"):
            if fleet_id not in owned_set:
                continue

            # Check if station or civilian
            is_station = fleet_data.get("station") == "yes"
            is_civilian = fleet_data.get("civilian") == "yes"

            # Get military power
            mp_str = fleet_data.get("military_power", "0")
            try:
                mp = float(mp_str)
            except (ValueError, TypeError):
                mp = 0.0

            # Count ships
            ships = fleet_data.get("ships", [])
            ship_count = len(ships) if isinstance(ships, list) else 0

            if is_station:
                # Stations are counted separately via _count_player_starbases
                pass
            elif is_civilian:
                civilian_count += 1
            elif mp > 100:  # Threshold filters out space creatures with tiny mp
                # Extract fleet name
                name_block = fleet_data.get("name")
                fleet_name = self._resolve_fleet_name(name_block, fleet_id)

                military_fleets.append(
                    {
                        "id": fleet_id,
                        "name": fleet_name,
                        "ships": ship_count,
                        "military_power": round(mp, 0),
                    }
                )
                total_military_power += mp
                military_ships += ship_count
            else:
                civilian_count += 1

        # Sort fleets by ID for consistent ordering (regex version uses file order)
        # Use same ordering as baseline: sort by ID numerically
        military_fleets.sort(key=lambda f: int(f["id"]))

        result["count"] = len(military_fleets)
        result["military_fleet_count"] = len(military_fleets)
        result["civilian_fleet_count"] = civilian_count
        result["military_ships"] = military_ships
        result["total_military_power"] = total_military_power
        result["fleets"] = military_fleets
        result["fleet_names"] = [f["name"] for f in military_fleets]

        # Get accurate starbase count from starbase_mgr
        starbase_info = self._count_player_starbases(owned_set)
        result["starbase_count"] = starbase_info["total_upgraded"]
        result["starbases"] = starbase_info

        return result

    def get_fleet_composition(self, limit: int = 50) -> dict:
        """Get ship class composition across the player's fleets.

        Returns:
            Dict with:
              - fleets: list[{fleet_id, name, ship_classes, total_ships}]
              - by_class_total: dict[str,int]
              - fleet_count: int

        Requires Rust session mode to be active.
        """
        return self._get_fleet_composition_rust(limit)

    def _get_fleet_composition_rust(self, limit: int = 50) -> dict:
        """Get fleet composition using Rust parser.

        Requires Rust session mode to be active.
        """
        session = _get_active_session()
        if not session:
            raise ParserError("Rust session mode required for get_fleet_composition")

        result = {
            "fleets": [],
            "by_class_total": {},
            "fleet_count": 0,
        }

        player_id = self.get_player_empire_id()
        country_content = self._find_player_country_content(player_id)
        if not country_content:
            return result

        owned_fleet_ids = self._get_owned_fleet_ids(country_content)
        if not owned_fleet_ids:
            return result

        owned_set = set(owned_fleet_ids)

        # Build design_id -> ship_size mapping from ship_design section (P031)
        design_to_size: dict[str, str] = {}
        for design_id, design_data in session.iter_section("ship_design"):
            if not isinstance(design_data, dict):
                continue
            # ship_size can be directly on design or in growth_stages[0].ship_size
            ship_size = design_data.get("ship_size")
            if not ship_size:
                growth_stages = design_data.get("growth_stages", [])
                if isinstance(growth_stages, list) and growth_stages:
                    first_stage = growth_stages[0]
                    if isinstance(first_stage, dict):
                        ship_size = first_stage.get("ship_size")
            if ship_size:
                design_to_size[str(design_id)] = str(ship_size)

        # Build ship_id -> design_id mapping from ships section (P031)
        ship_to_design: dict[str, str] = {}
        for ship_id, ship_data in session.iter_section("ships"):
            if not isinstance(ship_data, dict):
                continue
            impl = ship_data.get("ship_design_implementation", {})
            if isinstance(impl, dict):
                design_id = impl.get("design")
                if design_id:
                    ship_to_design[str(ship_id)] = str(design_id)
                    continue
            design_id = ship_data.get("ship_design")
            if design_id:
                ship_to_design[str(ship_id)] = str(design_id)

        # Process fleets (P031: use session.iter_section directly)
        fleets: list[dict] = []
        by_class_total: dict[str, int] = {}

        for fleet_id, fleet_data in session.iter_section("fleet"):
            if fleet_id not in owned_set:
                continue

            if not isinstance(fleet_data, dict):
                continue

            # Skip stations and civilian fleets
            if fleet_data.get("station") == "yes":
                continue
            if fleet_data.get("civilian") == "yes":
                continue

            # Check military power threshold
            mp_str = fleet_data.get("military_power", "0")
            try:
                military_power = float(mp_str)
            except (ValueError, TypeError):
                military_power = 0.0
            if military_power <= 100:
                continue

            # Get fleet name
            name_block = fleet_data.get("name")
            name_value = self._resolve_fleet_name(name_block, fleet_id)
            if name_value and name_value.startswith("shipclass_"):
                name_value = name_value.replace("shipclass_", "").replace("_name", "").title()

            # Process ships in this fleet
            ships = fleet_data.get("ships", [])
            if not isinstance(ships, list):
                continue

            ship_classes: dict[str, int] = {}
            for ship_id_val in ships:
                ship_id = str(ship_id_val)
                design_id = ship_to_design.get(ship_id)
                ship_size = design_to_size.get(design_id or "", "") if design_id else ""
                ship_size = ship_size.strip() if ship_size else "unknown"

                ship_classes[ship_size] = ship_classes.get(ship_size, 0) + 1
                by_class_total[ship_size] = by_class_total.get(ship_size, 0) + 1

            total_ships = sum(ship_classes.values())
            fleets.append(
                {
                    "fleet_id": str(fleet_id),
                    "name": name_value,
                    "ship_classes": ship_classes,
                    "total_ships": total_ships,
                }
            )

        fleets.sort(key=lambda f: f.get("total_ships", 0), reverse=True)

        result["fleet_count"] = len(fleets)
        result["by_class_total"] = by_class_total
        result["fleets"] = fleets[: max(0, int(limit))]
        return result

    def get_starbases(self) -> dict:
        """Get the player's starbase information with defense breakdown.

        Returns:
            Dict with starbase locations, levels, modules, and defense analysis:
            - starbases: List of starbase objects with:
                - id, level, type, modules, buildings (existing)
                - defense_modules: list of defense module types (gun_battery, hangar_bay, missile_battery)
                - defense_buildings: list of defense-enhancing buildings
                - defense_platform_count: count of defense platforms
                - defense_score: calculated defense strength score
            - count: Total starbase count
            - by_level: Dict of level -> count
            - total_defense_score: Sum of all starbase defense_scores

        Requires Rust session mode to be active.
        """
        return self._get_starbases_rust()

    def _get_starbases_rust(self) -> dict:
        """Get starbase information using Rust parser.

        Requires Rust session mode to be active.
        """
        session = _get_active_session()
        if not session:
            raise ParserError("Rust session mode required for get_starbases")

        result = {"starbases": [], "count": 0, "by_level": {}, "total_defense_score": 0}

        player_id = self.get_player_empire_id()
        player_id_str = str(player_id)

        # Defense module types to track
        DEFENSE_MODULES = {"gun_battery", "hangar_bay", "missile_battery"}
        # Defense-enhancing building types
        DEFENSE_BUILDINGS = {
            "target_uplink_computer",
            "defense_grid",
            "command_center",
            "communications_jammer",
            "disruption_field",
            "nebula_refinery",
        }
        # Level bonus for defense score
        LEVEL_BONUS = {
            "outpost": 0,
            "starport": 100,
            "starhold": 200,
            "starfortress": 400,
            "citadel": 800,
        }

        # Find player's starbases by scanning galactic_object section (P031)
        # Each system has starbases list and inhibitor_owners list
        player_starbase_ids = set()

        for system_id, system_data in session.iter_section("galactic_object"):
            if not isinstance(system_data, dict):
                continue

            # Check if player owns this system
            inhibitor_owners = system_data.get("inhibitor_owners", [])
            if not isinstance(inhibitor_owners, list):
                inhibitor_owners = [inhibitor_owners] if inhibitor_owners else []

            if player_id_str not in [str(o) for o in inhibitor_owners]:
                continue

            # Get starbase IDs from this system
            starbases = system_data.get("starbases", [])
            if not isinstance(starbases, list):
                starbases = [starbases] if starbases else []

            for sb_id in starbases:
                sb_id_str = str(sb_id)
                if sb_id_str != "4294967295":  # Not null
                    player_starbase_ids.add(sb_id_str)

        # Now get starbase details from starbase_mgr (P031)
        data = session.extract_sections(["starbase_mgr"])
        starbase_mgr = data.get("starbase_mgr", {})
        starbases_section = starbase_mgr.get("starbases", {})

        starbases_found = []
        level_counts = {}
        total_defense_score = 0

        for sb_id, sb_data in starbases_section.items():
            if sb_id not in player_starbase_ids:
                continue

            if not isinstance(sb_data, dict):
                continue

            level = sb_data.get("level", "")
            clean_level = level.replace("starbase_level_", "") if level else "unknown"

            starbase_info = {"id": sb_id, "level": clean_level}

            # Extract type if present
            sb_type = sb_data.get("type")
            if sb_type:
                starbase_info["type"] = sb_type

            # Extract modules
            modules_data = sb_data.get("modules", {})
            modules = list(modules_data.values()) if isinstance(modules_data, dict) else []
            if modules:
                starbase_info["modules"] = modules

            # Extract buildings
            buildings_data = sb_data.get("buildings", {})
            buildings = list(buildings_data.values()) if isinstance(buildings_data, dict) else []
            if buildings:
                starbase_info["buildings"] = buildings

            # Extract orbitals (defense platforms)
            orbitals_data = sb_data.get("orbitals", {})
            orbital_ids = list(orbitals_data.values()) if isinstance(orbitals_data, dict) else []
            # Count non-null orbitals (4294967295 = empty slot)
            defense_platform_count = sum(1 for oid in orbital_ids if str(oid) != "4294967295")

            # Calculate defense-specific fields
            defense_modules = [m for m in modules if m in DEFENSE_MODULES]
            defense_buildings = [b for b in buildings if b in DEFENSE_BUILDINGS]

            # Calculate defense score
            gun_batteries = modules.count("gun_battery")
            hangar_bays = modules.count("hangar_bay")
            missile_batteries = modules.count("missile_battery")
            level_bonus = LEVEL_BONUS.get(clean_level, 0)

            defense_score = (
                (gun_batteries * 100)
                + (hangar_bays * 80)
                + (missile_batteries * 90)
                + (defense_platform_count * 50)
                + level_bonus
            )

            # Add defense fields to starbase info
            starbase_info["defense_modules"] = defense_modules
            starbase_info["defense_buildings"] = defense_buildings
            starbase_info["defense_platform_count"] = defense_platform_count
            starbase_info["defense_score"] = defense_score

            starbases_found.append(starbase_info)
            total_defense_score += defense_score

            # Count by level
            if clean_level not in level_counts:
                level_counts[clean_level] = 0
            level_counts[clean_level] += 1

        # Full list (no truncation); callers that need caps should slice.
        result["starbases"] = starbases_found
        result["count"] = len(starbases_found)
        result["by_level"] = level_counts
        result["starbase_ids"] = list(player_starbase_ids)
        result["total_defense_score"] = total_defense_score

        return result

    def get_megastructures(self) -> dict:
        """Get the player's megastructures (gateways, dyson spheres, ringworlds, etc).

        Returns:
            Dict with:
              - megastructures: List of megastructure objects with type, status
              - count: Total count of player megastructures
              - by_type: Dict mapping type to count
              - ruined_available: List of ruined megastructures player could repair

        Requires Rust session mode to be active.
        """
        return self._get_megastructures_rust()

    def _get_megastructures_rust(self) -> dict:
        """Rust-optimized megastructure extraction using iter_section.

        Benefits over regex:
        - No 3MB chunk size limit (complete megastructure data)
        - No regex parsing errors on nested structures
        - Direct dict access - cleaner and more reliable

        Requires Rust session mode to be active.
        """
        session = _get_active_session()
        if not session:
            raise ParserError("Rust session mode required for get_megastructures")

        result = {
            "megastructures": [],
            "count": 0,
            "by_type": {},
            "ruined_available": [],
        }

        player_id = self.get_player_empire_id()

        player_megas = []
        ruined_megas = []
        by_type: dict[str, int] = {}

        for mega_id, entry in session.iter_section("megastructures"):
            # P010: entry might be string "none" for deleted entries
            if not isinstance(entry, dict):
                continue

            # P011: Use .get() with defaults
            mega_type = entry.get("type")
            if not mega_type:
                continue

            # Owner can be a string number or int
            owner_val = entry.get("owner")
            owner = None
            if owner_val is not None:
                with contextlib.suppress(ValueError, TypeError):
                    owner = int(owner_val)

            # Planet ID (4294967295 means null)
            planet_val = entry.get("planet")
            planet_id = None
            if planet_val is not None and str(planet_val) != "4294967295":
                planet_id = str(planet_val)

            # Check if this is a ruined megastructure (could be repaired)
            is_ruined = "ruined" in mega_type

            # Track ruined megastructures that could potentially be repaired
            if is_ruined:
                ruined_info = {
                    "id": mega_id,
                    "type": mega_type,
                    "owner": owner,
                }
                if planet_id:
                    ruined_info["planet_id"] = planet_id
                ruined_megas.append(ruined_info)

            # Only count megastructures owned by player
            if owner != player_id:
                continue

            # Determine status from type name
            status = "complete"
            if is_ruined:
                status = "ruined"
            elif "_restored" in mega_type:
                status = "restored"
            elif any(x in mega_type for x in ["_0", "_1", "_2", "_3", "_4", "_site"]):
                status = "under_construction"

            # Clean up type name for display
            display_type = mega_type
            # Remove stage suffixes for cleaner grouping
            for suffix in [
                "_ruined",
                "_restored",
                "_0",
                "_1",
                "_2",
                "_3",
                "_4",
                "_5",
                "_site",
            ]:
                if display_type.endswith(suffix):
                    display_type = display_type[: -len(suffix)]
                    break

            mega_info = {
                "id": mega_id,
                "type": mega_type,
                "display_type": display_type,
                "status": status,
            }

            if planet_id:
                mega_info["planet_id"] = planet_id

            player_megas.append(mega_info)

            # Count by display type
            by_type[display_type] = by_type.get(display_type, 0) + 1

        result["megastructures"] = player_megas
        result["count"] = len(player_megas)
        result["by_type"] = by_type
        # Return all ruined megastructures - late-game galaxies can have many
        result["ruined_available"] = ruined_megas

        return result
