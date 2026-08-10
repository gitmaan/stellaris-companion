from __future__ import annotations

import contextlib
import logging
import re

# Rust bridge for fast Clausewitz parsing - session mode required
from stellaris_companion.rust_bridge import ParserError, _get_active_session

from .fleet_classification import classify_owned_fleet

logger = logging.getLogger(__name__)

WAR_DIAGNOSTICS_SCHEMA_VERSION = 2


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
        return self.resolve_name(name_block, default=f"Fleet {fleet_id}", context="fleet").display

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

    def get_war_diagnostics(self, *, max_battles: int = 120) -> dict:
        """Return a bounded, privacy-safe record of battle-side calculations.

        This diagnostic deliberately excludes ship designs, coordinates, raw
        country data, and the save itself. It is intended for opt-in feedback
        reports where aggregate output is insufficient to reproduce a side
        attribution problem.
        """
        session = _get_active_session()
        if not session:
            raise ParserError("Rust session mode required for get_war_diagnostics")

        max_battles = max(1, min(int(max_battles), 250))
        player_id = str(self.get_player_empire_id())
        result = {
            "schema_version": WAR_DIAGNOSTICS_SCHEMA_VERSION,
            "player_id": player_id,
            "result_orientation": "parent_war_side",
            "loss_orientation": "parent_war_side",
            "wars": [],
            "included_battles": 0,
            "truncated": False,
        }

        for war_id, war in session.iter_section("war"):
            if not isinstance(war, dict):
                continue
            attacker_ids = self._war_participant_ids(war.get("attackers", []))
            defender_ids = self._war_participant_ids(war.get("defenders", []))
            player_is_war_attacker = player_id in attacker_ids
            if not player_is_war_attacker and player_id not in defender_ids:
                continue

            war_diagnostic = {
                "war_id": str(war_id),
                "our_side": "attacker" if player_is_war_attacker else "defender",
                "attacker_country_ids": sorted(attacker_ids),
                "defender_country_ids": sorted(defender_ids),
                "direct_battle_count": 0,
                "battle_records": [],
                "truncated": False,
            }
            battles = war.get("battles", [])
            if not isinstance(battles, list):
                battles = []
            for battle in battles:
                if not isinstance(battle, dict):
                    continue
                local_attackers = self._battle_participant_ids(battle.get("attackers", []))
                local_defenders = self._battle_participant_ids(battle.get("defenders", []))
                if player_id not in local_attackers and player_id not in local_defenders:
                    continue

                war_diagnostic["direct_battle_count"] += 1
                if result["included_battles"] >= max_battles:
                    war_diagnostic["truncated"] = True
                    result["truncated"] = True
                    continue

                war_diagnostic["battle_records"].append(
                    self._build_battle_diagnostic_record(
                        battle,
                        local_attackers=local_attackers,
                        local_defenders=local_defenders,
                        player_is_war_attacker=player_is_war_attacker,
                    )
                )
                result["included_battles"] += 1
            result["wars"].append(war_diagnostic)

        return result

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
        from stellaris_companion.date_utils import days_between

        session = _get_active_session()
        if not session:
            raise ParserError("Rust session mode required for get_wars")

        result = {"wars": [], "player_at_war": False, "active_war_count": 0}

        player_id = self.get_player_empire_id()
        current_date = self.get_metadata().get("date", "")

        # Build a country ID -> name mapping for lookups
        country_names = self._get_country_names_map()

        # Pre-warm galactic objects cache: _extract_battle_stats calls
        # _resolve_system_name which needs galactic_object data.  Without this,
        # it would trigger iter_section("galactic_object") *inside* the war
        # stream, corrupting the session (nested iter_section is not supported).
        self._get_galactic_objects_cached()

        # Build occupation evidence before streaming the war section. Rust
        # section streams cannot be nested, and these indexes use country,
        # fleet, colony, and planet data referenced by every active war.
        countries = self._get_countries_cached()
        lost_control_records = self._build_lost_control_records(session, countries)
        capital_control = self._build_capital_control_index(session, countries)

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
            our_side_ids = set(attacker_ids if player_is_attacker else defender_ids)
            opposing_side_ids = set(defender_ids if player_is_attacker else attacker_ids)

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
                player_id=player_id,
                player_is_war_attacker=player_is_attacker,
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
                "strategic_control": self._summarize_war_control(
                    lost_control_records=lost_control_records,
                    capital_control=capital_control,
                    our_side_ids=our_side_ids,
                    opposing_side_ids=opposing_side_ids,
                    player_id=player_id_str,
                    country_names=country_names,
                ),
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
        *,
        player_id: int | str,
        player_is_war_attacker: bool,
    ) -> dict:
        """Extract battle statistics from the battles block.

        Args:
            battles: List of battle records from war data
            player_id: Country ID of the player empire
            player_is_war_attacker: Whether the player belongs to the parent
                war's attacker coalition. Stellaris stores battle outcomes and
                loss totals relative to the parent war sides, even when the
                per-battle participant lists use the opposite tactical order.

        Returns:
            Dict with battle statistics for battles where the player empire
            directly participated:
            - total_battles: Total number of player battles
            - our_victories: Battles won by the player's war side
            - their_victories: Battles won by the opposing war side
            - unknown_outcomes: Battles without a recognized result flag
            - our_ship_losses: Ships lost by the player's war side
            - their_ship_losses: Ships lost by the opposing war side
            - our_army_losses: Armies lost by the player's war side
            - their_army_losses: Armies lost by the opposing war side

            The participant lists are used only to restrict the result to
            engagements in which the player country directly participated.
            Loss totals remain coalition-side values for those engagements and
            may include allied casualties in multi-country battles.
        """
        stats = {
            "total_battles": 0,
            "our_victories": 0,
            "their_victories": 0,
            "unknown_outcomes": 0,
            "our_ship_losses": 0,
            "their_ship_losses": 0,
            "our_army_losses": 0,
            "their_army_losses": 0,
        }

        if not isinstance(battles, list):
            return stats

        player_id_str = str(player_id)

        for battle in battles:
            if not isinstance(battle, dict):
                continue

            # The per-battle participant lists identify who directly fought, but
            # attacker_victory and attacker/defender losses are relative to the
            # parent war coalitions. The tactical list order can be the opposite
            # of the parent war side in real saves.
            battle_attackers = self._battle_participant_ids(battle.get("attackers", []))
            battle_defenders = self._battle_participant_ids(battle.get("defenders", []))
            if player_id_str not in battle_attackers and player_id_str not in battle_defenders:
                continue

            stats["total_battles"] += 1

            war_attacker_won = self._parse_battle_outcome(battle.get("attacker_victory"))
            if war_attacker_won is None:
                stats["unknown_outcomes"] += 1
            elif war_attacker_won == player_is_war_attacker:
                stats["our_victories"] += 1
            else:
                stats["their_victories"] += 1

            # Extract losses
            attacker_losses = 0
            defender_losses = 0
            with contextlib.suppress(ValueError, TypeError):
                attacker_losses = int(battle.get("attacker_losses", 0))
            with contextlib.suppress(ValueError, TypeError):
                defender_losses = int(battle.get("defender_losses", 0))

            battle_type = battle.get("type", "ships")

            # Loss fields use the same parent-war orientation as the result flag.
            if player_is_war_attacker:
                our_losses = attacker_losses
                their_losses = defender_losses
            else:
                our_losses = defender_losses
                their_losses = attacker_losses

            if battle_type == "armies":
                stats["our_army_losses"] += our_losses
                stats["their_army_losses"] += their_losses
            else:  # ships or other
                stats["our_ship_losses"] += our_losses
                stats["their_ship_losses"] += their_losses

        # Aggregate battle locations by system
        SENTINEL = 4294967295
        location_counts: dict[str, dict] = {}  # system_name -> {count, losses}
        for battle in battles:
            if not isinstance(battle, dict):
                continue
            battle_attackers = self._battle_participant_ids(battle.get("attackers", []))
            battle_defenders = self._battle_participant_ids(battle.get("defenders", []))
            if player_id_str not in battle_attackers and player_id_str not in battle_defenders:
                continue
            sys_id = battle.get("system")
            if sys_id is None:
                continue
            try:
                sys_id_int = int(sys_id)
            except (ValueError, TypeError):
                continue
            if sys_id_int == SENTINEL:
                continue
            name = self._resolve_system_name(sys_id_int)
            if not name:
                continue
            if name not in location_counts:
                location_counts[name] = {"count": 0, "losses": 0}
            location_counts[name]["count"] += 1
            # Sum all losses for this system
            a_loss = 0
            d_loss = 0
            with contextlib.suppress(ValueError, TypeError):
                a_loss = int(battle.get("attacker_losses", 0))
            with contextlib.suppress(ValueError, TypeError):
                d_loss = int(battle.get("defender_losses", 0))
            location_counts[name]["losses"] += a_loss + d_loss

        # Top 5 systems by battle count
        sorted_locations = sorted(location_counts.items(), key=lambda x: -x[1]["count"])
        stats["battle_locations"] = [
            {"system": name, "battles": data["count"], "total_losses": data["losses"]}
            for name, data in sorted_locations[:5]
        ]

        return stats

    def _build_lost_control_records(self, session, countries: dict[str, dict]) -> list[dict]:
        """Return save-recorded starbases whose owner has lost control."""
        pending: list[dict[str, str]] = []
        for owner_id, country in countries.items():
            if not isinstance(country, dict):
                continue
            fleet_manager = country.get("fleets_manager")
            if not isinstance(fleet_manager, dict):
                continue
            owned_fleets = fleet_manager.get("owned_fleets", [])
            if not isinstance(owned_fleets, list):
                continue
            for entry in owned_fleets:
                if not isinstance(entry, dict) or entry.get("ownership_status") != "lost_control":
                    continue
                fleet_id = entry.get("fleet")
                controller_id = entry.get("debtor")
                if fleet_id is None or controller_id is None:
                    continue
                pending.append(
                    {
                        "owner_id": str(owner_id),
                        "controller_id": str(controller_id),
                        "fleet_id": str(fleet_id),
                    }
                )

        if not pending:
            return []

        fleet_ids = list(dict.fromkeys(record["fleet_id"] for record in pending))
        fleets: dict[str, dict] = {}
        for entry in session.get_entries("fleet", fleet_ids):
            fleet_id = entry.get("_key")
            fleet = entry.get("_value")
            if fleet_id is not None and isinstance(fleet, dict):
                fleets[str(fleet_id)] = fleet

        records: list[dict] = []
        for record in pending:
            fleet = fleets.get(record["fleet_id"])
            if not isinstance(fleet, dict):
                continue
            if fleet.get("station") != "yes" and fleet.get("orbital_station") != "yes":
                continue

            system_id = self._fleet_system_id(fleet)
            enriched: dict = dict(record)
            enriched["system_id"] = system_id
            if system_id is not None:
                with contextlib.suppress(ValueError, TypeError):
                    system_name = self._resolve_system_name(int(system_id))
                    if system_name:
                        enriched["system_name"] = system_name
            records.append(enriched)
        return records

    @staticmethod
    def _fleet_system_id(fleet: dict) -> str | None:
        """Read a stationary fleet's current system from common save shapes."""
        for block_name in ("movement_manager", "combat"):
            block = fleet.get(block_name)
            if not isinstance(block, dict):
                continue
            coordinate = block.get("coordinate")
            if not isinstance(coordinate, dict):
                continue
            origin = coordinate.get("origin")
            if origin is not None and str(origin) != "4294967295":
                return str(origin)
        return None

    def _build_capital_control_index(
        self,
        session,
        countries: dict[str, dict],
    ) -> dict[str, dict]:
        """Resolve capital colony controllers and systems across save schemas."""
        try:
            data = session.extract_sections(["colony", "colonies", "planets"])
        except Exception as exc:
            logger.debug("war_capital_control_unavailable error=%s", exc)
            return {}

        colonies = data.get("colony") or data.get("colonies", {})
        if isinstance(colonies, dict):
            nested_colonies = colonies.get("colony") or colonies.get("colonies")
            if isinstance(nested_colonies, dict):
                colonies = nested_colonies
        else:
            colonies = {}

        planets = data.get("planets", {})
        if isinstance(planets, dict) and isinstance(planets.get("planet"), dict):
            planets = planets["planet"]
        if not isinstance(planets, dict):
            planets = {}

        result: dict[str, dict] = {}
        for country_id, country in countries.items():
            if not isinstance(country, dict):
                continue
            capital_id = country.get("capital")
            if capital_id is None:
                continue
            capital_id_str = str(capital_id)
            colony = colonies.get(capital_id_str)
            carrier: dict = {}
            if isinstance(colony, dict):
                carrier_id = self._capital_carrier_id(colony.get("carrier"))
                if carrier_id is not None and isinstance(planets.get(carrier_id), dict):
                    carrier = planets[carrier_id]
            else:
                colony = {}
                if isinstance(planets.get(capital_id_str), dict):
                    carrier = planets[capital_id_str]

            controller_id = colony.get("controller") or carrier.get("controller")
            coordinate = colony.get("coordinate") or carrier.get("coordinate")
            system_id = (
                str(coordinate.get("origin"))
                if isinstance(coordinate, dict) and coordinate.get("origin") is not None
                else None
            )
            name_block = colony.get("name") or carrier.get("name")
            capital_name = None
            if name_block:
                capital_name = self.resolve_name(
                    name_block,
                    default="Unknown Capital",
                    context="planet",
                ).display

            result[str(country_id)] = {
                "capital_id": capital_id_str,
                "controller_id": str(controller_id) if controller_id is not None else None,
                "system_id": system_id,
                "capital_name": capital_name,
            }
        return result

    @staticmethod
    def _capital_carrier_id(carrier: object) -> str | None:
        """Normalize Pegasus colony carrier references to a planet ID."""
        if isinstance(carrier, (str, int)) and not isinstance(carrier, bool):
            return str(carrier)
        if not isinstance(carrier, dict):
            return None
        for key in ("planet", "reference", "id", "carrier_id", "value"):
            value = carrier.get(key)
            if value is not None and not isinstance(value, (dict, list, bool)):
                return str(value)
        return None

    @staticmethod
    def _summarize_war_control(
        *,
        lost_control_records: list[dict],
        capital_control: dict[str, dict],
        our_side_ids: set[str],
        opposing_side_ids: set[str],
        player_id: str,
        country_names: dict[int, str],
    ) -> dict:
        """Summarize occupation evidence relative to the player's war side."""
        enemy_assets = [
            record
            for record in lost_control_records
            if record.get("owner_id") in opposing_side_ids
            and record.get("controller_id") in our_side_ids
        ]
        our_assets = [
            record
            for record in lost_control_records
            if record.get("owner_id") in our_side_ids
            and record.get("controller_id") in opposing_side_ids
        ]

        def systems(records: list[dict]) -> list[dict]:
            by_id: dict[str, dict] = {}
            for record in records:
                system_id = record.get("system_id")
                if system_id is None:
                    continue
                by_id.setdefault(
                    str(system_id),
                    {
                        "system_id": str(system_id),
                        "system_name": record.get("system_name"),
                    },
                )
            return list(by_id.values())

        enemy_systems = systems(enemy_assets)
        our_systems = systems(our_assets)
        enemy_system_ids = {entry["system_id"] for entry in enemy_systems}
        our_system_ids = {entry["system_id"] for entry in our_systems}

        def empire_name(country_id: str) -> str:
            with contextlib.suppress(ValueError, TypeError):
                return country_names.get(int(country_id), f"Empire {country_id}")
            return f"Empire {country_id}"

        occupied_enemy_capitals: list[dict] = []
        controlled_enemy_capital_systems: list[dict] = []
        for country_id in sorted(opposing_side_ids):
            capital = capital_control.get(country_id, {})
            capital_info = {
                "empire": empire_name(country_id),
                "empire_id": country_id,
                "capital": capital.get("capital_name"),
                "system_id": capital.get("system_id"),
            }
            if capital.get("controller_id") in our_side_ids:
                occupied_enemy_capitals.append(capital_info)
            if capital.get("system_id") in enemy_system_ids:
                controlled_enemy_capital_systems.append(capital_info)

        player_capital = capital_control.get(player_id, {})
        player_capital_system_id = player_capital.get("system_id")
        player_capital_controller = player_capital.get("controller_id")
        player_capital_system_lost = (
            player_capital_system_id in our_system_ids
            if player_capital_system_id is not None
            else None
        )
        player_capital_occupied = (
            player_capital_controller in opposing_side_ids
            if player_capital_controller is not None
            else None
        )

        return {
            "enemy_starbase_assets_controlled_by_our_side": len(enemy_assets),
            "enemy_systems_controlled_by_our_side": enemy_systems,
            "enemy_assets_controlled_by_player": sum(
                record.get("controller_id") == player_id for record in enemy_assets
            ),
            "our_starbase_assets_controlled_by_enemy_side": len(our_assets),
            "our_systems_controlled_by_enemy_side": our_systems,
            "enemy_capital_colonies_occupied_by_our_side": occupied_enemy_capitals,
            "enemy_capital_systems_controlled_by_our_side": controlled_enemy_capital_systems,
            "player_capital_colony_occupied_by_enemy_side": player_capital_occupied,
            "player_capital_system_controlled_by_enemy_side": player_capital_system_lost,
            "evidence_scope": (
                "Save-recorded lost-control starbase assets and capital colony controllers; "
                "this is strategic control evidence, not a complete war-score calculation."
            ),
        }

    @staticmethod
    def _parse_battle_outcome(value: object) -> bool | None:
        """Return whether the parent war attacker won, or None if unknown."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"yes", "true", "1"}:
                return True
            if normalized in {"no", "false", "0"}:
                return False
        if isinstance(value, int) and value in {0, 1}:
            return bool(value)
        return None

    @staticmethod
    def _war_participant_ids(participants: object) -> set[str]:
        """Normalize parent-war participant records into country IDs."""
        if not isinstance(participants, list):
            participants = [participants] if participants else []
        result: set[str] = set()
        for participant in participants:
            if isinstance(participant, dict):
                country_id = participant.get("country")
                if country_id is not None:
                    result.add(str(country_id))
        return result

    def _build_battle_diagnostic_record(
        self,
        battle: dict,
        *,
        local_attackers: set[str],
        local_defenders: set[str],
        player_is_war_attacker: bool,
    ) -> dict:
        """Build one bounded battle calculation record for feedback reports."""
        attacker_losses = 0
        defender_losses = 0
        with contextlib.suppress(ValueError, TypeError):
            attacker_losses = int(battle.get("attacker_losses", 0))
        with contextlib.suppress(ValueError, TypeError):
            defender_losses = int(battle.get("defender_losses", 0))

        war_attacker_won = self._parse_battle_outcome(battle.get("attacker_victory"))
        if war_attacker_won is None:
            computed_result = "unknown"
        elif war_attacker_won == player_is_war_attacker:
            computed_result = "our_side_victory"
        else:
            computed_result = "opposing_side_victory"

        return {
            "local_attacker_country_ids": sorted(local_attackers),
            "local_defender_country_ids": sorted(local_defenders),
            "raw_attacker_victory": battle.get("attacker_victory"),
            "raw_attacker_losses": attacker_losses,
            "raw_defender_losses": defender_losses,
            "battle_type": battle.get("type", "ships"),
            "system_id": str(battle.get("system")) if battle.get("system") is not None else None,
            "computed_result": computed_result,
            "computed_our_side_losses": (
                attacker_losses if player_is_war_attacker else defender_losses
            ),
            "computed_opposing_side_losses": (
                defender_losses if player_is_war_attacker else attacker_losses
            ),
        }

    @staticmethod
    def _battle_participant_ids(participants: object) -> set[str]:
        """Normalize battle participant references into country ID strings."""
        if isinstance(participants, list):
            ids: set[str] = set()
            for participant in participants:
                if isinstance(participant, dict):
                    country_id = participant.get("country") or participant.get("id")
                    if country_id is not None:
                        ids.add(str(country_id))
                elif participant not in (None, ""):
                    ids.add(str(participant))
            return ids

        if isinstance(participants, dict):
            country_id = participants.get("country") or participants.get("id")
            return {str(country_id)} if country_id is not None else set()

        return {str(participants)} if participants not in (None, "") else set()

    @staticmethod
    def _has_active_megastructure_upgrade(upgrade: object) -> bool:
        """Return True when a megastructure is actively upgrading."""
        if not isinstance(upgrade, dict):
            return False

        upgrade_to = upgrade.get("upgrade_to")
        if upgrade_to:
            return True

        progress = upgrade.get("progress")
        if progress in (None, "", 0, 0.0, "0", "0.0"):
            return False

        with contextlib.suppress(ValueError, TypeError):
            return float(progress) > 0
        return True

    @staticmethod
    def _normalize_megastructure_display_type(mega_type: str) -> str:
        """Strip status/stage suffixes for consistent megastructure grouping."""
        if not isinstance(mega_type, str):
            return mega_type
        return re.sub(r"_(?:ruined|restored|site|\d+)$", "", mega_type)

    def _classify_megastructure_status(self, entry: dict, mega_type: str) -> str:
        """Classify a megastructure based on active construction state, not suffixes."""
        if "ruined" in mega_type:
            return "ruined"
        if "_restored" in mega_type:
            return "restored"

        build_queue = entry.get("build_queue")
        queue_active = build_queue not in (None, "", 4294967295, "4294967295")
        site_active = "_site" in mega_type
        upgrade_active = self._has_active_megastructure_upgrade(entry.get("upgrade"))

        if queue_active or site_active or upgrade_active:
            return "under_construction"

        return "complete"

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

        # Get the player's country entry to find owned fleets (fast path: 4ms vs 450ms)
        player_id = self.get_player_empire_id()
        country_entry = self._get_player_country_entry(player_id)
        if not country_entry:
            return result

        # Get OWNED fleets from parsed dict (no regex needed)
        owned_fleet_ids = self._get_owned_fleet_ids_from_entry(country_entry)
        if not owned_fleet_ids:
            return result

        owned_set = set(owned_fleet_ids)
        military_fleets = []
        total_military_power = 0.0
        military_ships = 0
        civilian_count = 0

        # Iterate through fleets using cached fleet section
        for fleet_id, fleet_data in self._get_fleets_cached().items():
            if fleet_id not in owned_set:
                continue

            # Classify by ship_class (4.x) with a legacy fallback. In 4.x saves
            # starbases are ship_class=shipclass_starbase with no station flag,
            # so the old station/power heuristic counted them as military.
            fleet_kind = classify_owned_fleet(fleet_data)

            # Get military power
            mp_str = fleet_data.get("military_power", "0")
            try:
                mp = float(mp_str)
            except (ValueError, TypeError):
                mp = 0.0

            # Count ships
            ships = fleet_data.get("ships", [])
            ship_count = len(ships) if isinstance(ships, list) else 0

            if fleet_kind == "starbase":
                # Stations are counted separately via _count_player_starbases
                pass
            elif fleet_kind == "military":
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

        # Get player's country entry (fast path: 4ms vs 450ms)
        player_id = self.get_player_empire_id()
        country_entry = self._get_player_country_entry(player_id)
        if not country_entry:
            return result

        # Get OWNED fleets from parsed dict (no regex needed)
        owned_fleet_ids = self._get_owned_fleet_ids_from_entry(country_entry)
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

        # Process fleets using cached fleet section
        fleets: list[dict] = []
        by_class_total: dict[str, int] = {}

        for fleet_id, fleet_data in self._get_fleets_cached().items():
            if fleet_id not in owned_set:
                continue

            # Skip starbases and civilian fleets (ship_class-aware; 4.x starbases
            # have no station flag). Only combat fleets contribute to composition.
            if classify_owned_fleet(fleet_data) != "military":
                continue

            # Get fleet name
            name_block = fleet_data.get("name")
            name_value = self._resolve_fleet_name(name_block, fleet_id)

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

        # Find player's starbases via cached system ownership map
        # (starbase chain: system -> starbase -> station ship -> fleet -> country)
        owner_map = self._get_system_owner_map()
        player_starbase_ids = set()
        starbase_to_system: dict[str, str] = {}  # sb_id -> system_id

        for system_id, system_data in self._get_galactic_objects_cached().items():
            if owner_map.get(system_id) != player_id:
                continue

            starbases = system_data.get("starbases", [])
            if not isinstance(starbases, list):
                starbases = [starbases] if starbases else []

            for sb_id in starbases:
                sb_id_str = str(sb_id)
                if sb_id_str != "4294967295":  # Not null
                    player_starbase_ids.add(sb_id_str)
                    starbase_to_system[sb_id_str] = system_id

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

            # Attach system location (resolved from cached galactic objects)
            sys_id = starbase_to_system.get(sb_id)
            if sys_id is not None:
                starbase_info["system_id"] = int(sys_id)
                sys_name = self._resolve_system_name(int(sys_id))
                if sys_name:
                    starbase_info["system_name"] = sys_name

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

            status = self._classify_megastructure_status(entry, mega_type)
            display_type = self._normalize_megastructure_display_type(mega_type)

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
