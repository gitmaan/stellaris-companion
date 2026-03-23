from __future__ import annotations

import contextlib
import logging
import re
from collections import Counter, defaultdict

# Rust bridge for Clausewitz parsing (required for session mode)
from stellaris_companion.rust_bridge import ParserError, _get_active_session

logger = logging.getLogger(__name__)

_BASE_NAVAL_CAP = 50.0

_NAVAL_CAP_DIFFICULTY_MULTS = {
    "civilian": 1.0,
    "cadet": 0.5,
    "ensign": 0.0,
    "captain": 0.25,
    "commodore": 0.5,
    "admiral": 0.75,
    "grand_admiral": 1.0,
}

_NAVAL_CAP_TECH_ADDS = {
    "tech_doctrine_navy_size_1": 25.0,
    "tech_doctrine_navy_size_2": 50.0,
    "tech_doctrine_navy_size_3": 75.0,
    "tech_doctrine_navy_size_4": 100.0,
}
_NAVAL_CAP_REPEATABLE_ADD = 20.0

_NAVAL_CAP_TRADITION_ADDS = {
    "tr_supremacy_adopt": 20.0,
}
_NAVAL_CAP_TRADITION_MULTS = {
    "tr_supremacy_fleet_logistical_corps": 0.20,
    "tr_supremacy_fleet_logistical_corps_machine": 0.20,
}

_NAVAL_CAP_ASCENSION_PERK_ADDS = {
    "ap_galactic_force_projection": 150.0,
}

_NAVAL_CAP_POLICY_MULTS = {
    "diplo_stance_belligerent": 0.10,
    "diplo_stance_supremacist": 0.20,
}

_NAVAL_CAP_EDICT_MULTS = {
    "masters_writings_war": 0.10,
    "grand_fleet": 0.20,
    "cybernetic_creed_war_edict": 0.10,
    "nanotech_naval_augmentation": 0.25,
}

_NAVAL_CAP_CIVIC_MULTS = {
    "citizen_service": 0.15,
    "naval_contractors": 0.15,
    "fanatic_purifiers": 0.33,
    "hive_subspace_ephapse": 0.15,
    "hive_devouring_swarm": 0.33,
    "machine_terminator": 0.33,
    "sovereign_guardianship": 0.50,
}

_NAVAL_CAP_MEGASTRUCTURE_ADDS = {
    "strategic_coordination_center_1": 200.0,
    "strategic_coordination_center_2": 200.0,
    "strategic_coordination_center_3": 300.0,
    "strategic_coordination_center_restored": 300.0,
    "galactic_crucible_1": 150.0,
    "galactic_crucible_2": 225.0,
    "galactic_crucible_3": 300.0,
    "galactic_crucible_4": 375.0,
    "crisis_sphere_0": 200.0,
    "crisis_sphere_1": 300.0,
    "crisis_sphere_2": 400.0,
    "crisis_sphere_3": 500.0,
    "shroud_seal": 10.0,
}

_NAVAL_CAP_FEDERATION_PERK_ADDS = {
    "neutral": 20.0,
}

_NAVAL_CAP_SUBJECT_TERM_MULTS = {
    "naval_cap_satrapy": -0.30,
}

_NAVAL_CAP_JOB_BASE_ADDS = {
    "soldier": 2.0,
    "warrior_drone": 4.0,
    "duelist": 2.0,
    "knight": 4.0,
    "knight_commander": 4.0,
}

_NAVAL_CAP_LEADER_TRAIT_HINTS = {
    "leader_trait_armada_logistician",
    "leader_trait_armada_logistician_2",
    "leader_trait_fleet_organizer",
    "leader_trait_fleet_organizer_2",
    "leader_trait_crew_trainer",
    "leader_trait_crew_trainer_2",
    "leader_trait_shroudshaper",
    "leader_trait_has_backup_clone",
}

_NAVAL_CAP_TIMED_MODIFIER_HINTS = {
    "resolution_sanctions_military",
    "resolution_mutualdefense",
    "resolution_defenseprivatization",
    "resolution_commerce_leveraged_privateering",
    "resolution_commerce_holistic_asset_coordination",
    "resolution_rulesofwar_demobilization_initiative",
}


class PlayerMixin:
    """Domain methods extracted from the original SaveExtractor."""

    def _extract_braced_block(self, content: str, key: str) -> str | None:
        """Extract the full `key={...}` block from a larger text chunk."""
        match = re.search(rf"\b{re.escape(key)}\s*=\s*\{{", content)
        if not match:
            return None

        start = match.start()
        brace_count = 0
        started = False

        for i, char in enumerate(content[start:], start):
            if char == "{":
                brace_count += 1
                started = True
            elif char == "}":
                brace_count -= 1
                if started and brace_count == 0:
                    return content[start : i + 1]

        return None

    def _parse_simple_string_list_block(self, block: str, prefix: str | None = None) -> list[str]:
        """Parse a simple `{ "a" "b" }` or `{ a b }` block into a de-duped list."""
        if not block:
            return []

        open_brace = block.find("{")
        close_brace = block.rfind("}")
        if open_brace == -1 or close_brace == -1 or close_brace <= open_brace:
            return []

        inner = block[open_brace + 1 : close_brace]

        items = re.findall(r'"([^"]+)"', inner)
        if not items:
            if prefix:
                items = re.findall(rf"\b({re.escape(prefix)}[A-Za-z0-9_]+)\b", inner)
            else:
                items = re.findall(r"\b([A-Za-z0-9_]+)\b", inner)

        deduped: list[str] = []
        seen: set[str] = set()
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            deduped.append(item)

        return deduped

    def get_player_empire_id(self) -> int:
        """Get the player's country ID.

        Requires Rust session mode to be active.

        Returns:
            Player country ID (usually 0)

        Raises:
            ParserError: If no Rust session is active
        """
        session = _get_active_session()
        if not session:
            raise ParserError("Rust session required - use 'with session(save_path):' context")

        data = session.extract_sections(["player"])
        player_list = data.get("player", [])
        if player_list and isinstance(player_list, list) and len(player_list) > 0:
            country_id = player_list[0].get("country", "0")
            return int(country_id)
        return 0

    def get_player_status(self) -> dict:
        """Get the player's current empire status with clear, unambiguous metrics.

        Requires Rust session mode to be active.

        Returns:
            Dict with empire info, military, economy, and territory data.
            All field names are self-documenting to prevent LLM misinterpretation.

        Note:
            Results are cached per-instance since player status is expensive to compute
            and doesn't change within a single save file analysis.

        Raises:
            ParserError: If no Rust session is active
        """
        # Return cached result if available (expensive computation)
        if self._player_status_cache is not None:
            return self._player_status_cache

        # Rust session required
        session = _get_active_session()
        if not session:
            raise ParserError("Rust session required - use 'with session(save_path):' context")

        result = self._get_player_status_rust(session)

        # Cache the result for subsequent calls
        self._player_status_cache = result
        return result

    def _get_player_status_rust(self, session) -> dict:
        """Rust-optimized player status extraction using get_entry.

        Uses get_entry for fast single-entry lookup instead of scanning
        the entire country section with regex.
        """
        player_id = self.get_player_empire_id()

        result = {
            "player_id": player_id,
            "empire_name": self.get_metadata().get("name", "Unknown"),
            "date": self.get_metadata().get("date", "Unknown"),
        }

        # Get player country using cached method (0.004s vs 0.45s with regex)
        player_country = self._get_player_country_entry(player_id)

        if player_country and isinstance(player_country, dict):
            # Extract metrics directly from parsed dict
            metrics = [
                "military_power",
                "economy_power",
                "tech_power",
                "victory_rank",
                "fleet_size",
            ]
            for key in metrics:
                value = player_country.get(key)
                if value is not None:
                    # Values come as strings from jomini, convert to appropriate type
                    with contextlib.suppress(ValueError, TypeError):
                        result[key] = float(value) if "." in str(value) else int(value)

            # Get OWNED fleets from fleets_manager
            fleets_mgr = player_country.get("fleets_manager", {})
            owned_fleets_data = (
                fleets_mgr.get("owned_fleets", []) if isinstance(fleets_mgr, dict) else []
            )
            owned_fleet_ids = []
            for entry in owned_fleets_data:
                if isinstance(entry, dict):
                    fleet_id = entry.get("fleet")
                    if fleet_id is not None:
                        owned_fleet_ids.append(str(fleet_id))

            owned_set = set(owned_fleet_ids)

            if owned_fleet_ids:
                # Analyze the owned fleets (already uses Rust get_entries)
                fleet_analysis = self._analyze_player_fleets(owned_fleet_ids)
                result["military_fleet_count"] = fleet_analysis["military_fleet_count"]
                result["military_ships"] = fleet_analysis["military_ships"]
                # Keep fleet_count for backwards compatibility
                result["fleet_count"] = fleet_analysis["military_fleet_count"]

                # Get accurate starbase count from starbase_mgr
                starbase_info = self._count_player_starbases(owned_set)
                result["starbase_count"] = starbase_info["total_upgraded"]
                result["outpost_count"] = starbase_info["outposts"]
                result["starbases"] = starbase_info

            # Get controlled planets directly from parsed dict
            controlled_planets = player_country.get("controlled_planets", [])
            if isinstance(controlled_planets, list):
                result["celestial_bodies_in_territory"] = len(controlled_planets)

        # Get colonized planets data (already uses Rust when session active)
        planets_data = self.get_planets()
        colonies = planets_data.get("planets", [])
        total_pops = sum(p.get("population", 0) for p in colonies)

        # Separate habitats from planets (different pop capacities)
        habitats = [c for c in colonies if c.get("type", "").startswith("habitat")]
        regular_planets = [c for c in colonies if not c.get("type", "").startswith("habitat")]

        habitat_pops = sum(p.get("population", 0) for p in habitats)
        planet_pops = sum(p.get("population", 0) for p in regular_planets)

        result["colonies"] = {
            "total_count": len(colonies),
            "total_population": total_pops,
            "avg_pops_per_colony": (round(total_pops / len(colonies), 1) if colonies else 0),
            "_note": "These are colonized worlds with population, not all celestial bodies",
            # Breakdown by type for more accurate analysis
            "habitats": {
                "count": len(habitats),
                "population": habitat_pops,
                "avg_pops": round(habitat_pops / len(habitats), 1) if habitats else 0,
            },
            "planets": {
                "count": len(regular_planets),
                "population": planet_pops,
                "avg_pops": (
                    round(planet_pops / len(regular_planets), 1) if regular_planets else 0
                ),
            },
        }

        return result

    def get_empire_identity(self) -> dict:
        """Extract static empire identity for personality generation.

        This extracts ethics, government, civics, and species info from the
        player's country block. This data comes from empire creation and
        only changes via government reform or ethics shift events.

        Requires Rust session mode to be active.

        Returns:
            Dictionary with ethics, government, civics, species, and gestalt flags

        Raises:
            ParserError: If no Rust session is active
        """
        result = {
            "ethics": [],
            "government": None,
            "civics": [],
            "authority": None,
            "species_class": None,
            "species_name": None,
            "is_gestalt": False,
            "is_machine": False,
            "is_hive_mind": False,
            "empire_name": self.get_metadata().get("name", "Unknown"),
        }

        # Rust session required
        player_id = self.get_player_empire_id()
        country = self._get_player_country_entry(player_id)
        if not country or not isinstance(country, dict):
            return result

        # Extract ethics
        ethos = country.get("ethos", {})
        if isinstance(ethos, dict):
            ethic = ethos.get("ethic", [])
            if isinstance(ethic, str):
                ethic = [ethic]
            result["ethics"] = [e.replace("ethic_", "") for e in ethic if isinstance(e, str)]

        # Extract government info
        gov = country.get("government", {})
        if isinstance(gov, dict):
            gov_type = gov.get("type", "")
            if gov_type:
                result["government"] = gov_type.replace("gov_", "")

            authority = gov.get("authority", "")
            if authority:
                result["authority"] = authority.replace("auth_", "")

            civics = gov.get("civics", [])
            if isinstance(civics, list):
                result["civics"] = [c.replace("civic_", "") for c in civics if isinstance(c, str)]

        # Check for gestalt
        if "gestalt_consciousness" in result["ethics"]:
            result["is_gestalt"] = True
        if result["authority"] == "machine_intelligence":
            result["is_gestalt"] = True
            result["is_machine"] = True
        elif result["authority"] == "hive_mind":
            result["is_gestalt"] = True
            result["is_hive_mind"] = True

        # Extract founder species
        founder_ref = country.get("founder_species_ref")
        if founder_ref:
            species_names = self._get_species_names()
            result["species_name"] = species_names.get(str(founder_ref))

        return result

    def get_traditions(self) -> dict:
        """Extract picked traditions and summarize progress by tree.

        Requires Rust session mode to be active.

        Returns:
            Dict with:
              - traditions: list[str]
              - by_tree: dict[str, {picked: list[str], adopted: bool, finished: bool}]
              - count: int

        Raises:
            ParserError: If no Rust session is active
        """
        result = {
            "traditions": [],
            "by_tree": {},
            "count": 0,
        }

        # Rust session required (get_player_empire_id raises if no session)
        player_id = self.get_player_empire_id()
        country = self._get_player_country_entry(player_id)
        if not country or not isinstance(country, dict):
            return result

        traditions = country.get("traditions", [])
        if isinstance(traditions, list):
            result["traditions"] = traditions
            result["count"] = len(traditions)

            # Build by_tree summary
            by_tree: dict[str, dict] = {}
            for tradition_id in traditions:
                tree = "unknown"
                if tradition_id.startswith("tr_"):
                    remainder = tradition_id[3:]
                    parts = remainder.split("_", 1)
                    if parts and parts[0]:
                        tree = parts[0]

                entry = by_tree.setdefault(
                    tree, {"picked": [], "adopted": False, "finished": False}
                )
                entry["picked"].append(tradition_id)
                if tradition_id.endswith("_adopt"):
                    entry["adopted"] = True
                if tradition_id.endswith("_finish"):
                    entry["finished"] = True

            result["by_tree"] = by_tree

        return result

    def get_ascension_perks(self) -> dict:
        """Extract picked ascension perks.

        Requires Rust session mode to be active.

        Returns:
            Dict with:
              - ascension_perks: list[str]
              - count: int

        Raises:
            ParserError: If no Rust session is active
        """
        result = {
            "ascension_perks": [],
            "count": 0,
        }

        # Rust session required (get_player_empire_id raises if no session)
        player_id = self.get_player_empire_id()
        country = self._get_player_country_entry(player_id)
        if not country or not isinstance(country, dict):
            return result

        perks = country.get("ascension_perks", [])
        if isinstance(perks, list):
            result["ascension_perks"] = perks
            result["count"] = len(perks)

        return result

    def get_naval_capacity(self) -> dict:
        """Get the player's naval capacity usage plus a conservative cap verdict.

        Stellaris stores current naval usage directly in saves, but the actual
        naval-cap ceiling is derived from many modifiers. This method computes a
        best-effort verdict and marks whether the result is safe to state as fact.

        Requires Rust session mode to be active.
        """
        result = {
            "used": 0,
            "max": None,
            "max_is_unknown": True,
            "fleet_size": 0,
            "starbase_capacity": None,
            "used_starbase_capacity": None,
            "_note": (
                "used is current naval capacity in use, not the empire's naval capacity limit. "
                "Use analysis.confidence and safe_to_claim_* flags before stating whether the empire "
                "is under or over naval cap."
            ),
            "analysis": {
                "confidence": "unknown",
                "formula": "(base + flat_additions) * (1 + multiplier_total)",
                "limit": None,
                "derived_limit": None,
                "status": "unknown",
                "derived_status": None,
                "over_by": None,
                "derived_over_by": None,
                "upkeep_penalty_applies": None,
                "safe_to_claim_limit": False,
                "safe_to_claim_over_cap": False,
                "safe_to_claim_penalty": False,
                "modeled_source_families": [],
                "unresolved_source_families": [],
                "reasons": [],
                "breakdown": {
                    "base": int(_BASE_NAVAL_CAP),
                    "flat_additions": {},
                    "multiplier_additions": {},
                    "flat_additions_total": 0.0,
                    "multiplier_total": 0.0,
                },
            },
        }

        # Rust session required (get_player_empire_id raises if no session)
        player_id = self.get_player_empire_id()
        player_country = self._get_player_country_entry(player_id)

        if not player_country or not isinstance(player_country, dict):
            return result

        # Extract metrics directly from parsed dict
        used = player_country.get("used_naval_capacity")
        if used is not None:
            with contextlib.suppress(ValueError, TypeError):
                result["used"] = int(float(used))

        fleet_size = player_country.get("fleet_size")
        if fleet_size is not None:
            with contextlib.suppress(ValueError, TypeError):
                result["fleet_size"] = int(fleet_size)

        starbase_cap = player_country.get("starbase_capacity")
        if starbase_cap is not None:
            with contextlib.suppress(ValueError, TypeError):
                result["starbase_capacity"] = int(starbase_cap)

        used_starbase = player_country.get("used_starbase_capacity")
        if used_starbase is not None:
            with contextlib.suppress(ValueError, TypeError):
                result["used_starbase_capacity"] = int(used_starbase)

        try:
            analysis = self._analyze_naval_capacity(
                player_id=player_id,
                player_country=player_country,
                used_capacity=result["used"],
            )
            result["analysis"] = analysis
            if analysis.get("limit") is not None:
                result["max"] = analysis["limit"]
                result["max_is_unknown"] = False
        except Exception as exc:
            logger.warning("Failed to analyze naval capacity limit: %s", exc)

        return result

    def _analyze_naval_capacity(
        self,
        *,
        player_id: int,
        player_country: dict,
        used_capacity: int,
    ) -> dict:
        """Compute a conservative naval-cap verdict from modeled save sources."""
        flat_additions: dict[str, float] = {}
        multiplier_additions: dict[str, float] = {}
        modeled_families: set[str] = set()
        unresolved_families: set[str] = set()

        def add_flat(label: str, amount: float, family: str) -> None:
            if not amount:
                return
            flat_additions[label] = round(flat_additions.get(label, 0.0) + amount, 3)
            modeled_families.add(family)

        def add_mult(label: str, amount: float, family: str) -> None:
            if not amount:
                return
            multiplier_additions[label] = round(multiplier_additions.get(label, 0.0) + amount, 6)
            modeled_families.add(family)

        difficulty = self._get_naval_cap_difficulty()
        if difficulty in _NAVAL_CAP_DIFFICULTY_MULTS:
            add_mult(
                f"Difficulty ({difficulty})",
                _NAVAL_CAP_DIFFICULTY_MULTS[difficulty],
                "difficulty",
            )

        civics = self._get_country_civics(player_country)
        for civic in sorted(civics):
            amount = _NAVAL_CAP_CIVIC_MULTS.get(civic)
            if amount:
                add_mult(f"Civic ({civic})", amount, "civics")
            if civic in {"distinguished_admiralty", "nationalistic_zeal"}:
                unresolved_families.add("councilor_civic_modifiers")

        researched_techs = self._get_researched_technologies(player_id)
        for tech in sorted(set(researched_techs)):
            amount = _NAVAL_CAP_TECH_ADDS.get(tech)
            if amount:
                add_flat(f"Technology ({tech})", amount, "technology")

        repeatables = Counter(t for t in researched_techs if t == "tech_repeatable_naval_cap")
        repeatable_levels = repeatables.get("tech_repeatable_naval_cap", 0)
        if repeatable_levels:
            add_flat(
                "Repeatable naval-cap tech",
                repeatable_levels * _NAVAL_CAP_REPEATABLE_ADD,
                "technology",
            )

        traditions = self._get_country_traditions(player_country)
        for tradition in sorted(traditions):
            add_amount = _NAVAL_CAP_TRADITION_ADDS.get(tradition)
            if add_amount:
                add_flat(f"Tradition ({tradition})", add_amount, "traditions")
            mult_amount = _NAVAL_CAP_TRADITION_MULTS.get(tradition)
            if mult_amount:
                add_mult(f"Tradition ({tradition})", mult_amount, "traditions")

        perks = self._get_country_ascension_perks(player_country)
        for perk in sorted(perks):
            amount = _NAVAL_CAP_ASCENSION_PERK_ADDS.get(perk)
            if amount:
                add_flat(f"Ascension perk ({perk})", amount, "ascension_perks")

        stance = self._get_active_diplomatic_stance(player_country)
        if stance in _NAVAL_CAP_POLICY_MULTS:
            add_mult(f"Diplomatic stance ({stance})", _NAVAL_CAP_POLICY_MULTS[stance], "policies")

        for edict in sorted(self._get_active_edicts(player_country)):
            amount = _NAVAL_CAP_EDICT_MULTS.get(edict)
            if amount:
                add_mult(f"Edict ({edict})", amount, "edicts")

        for starbase in self.get_starbases().get("starbases", []):
            if not isinstance(starbase, dict):
                continue
            modules = starbase.get("modules") or []
            buildings = set(starbase.get("buildings") or [])
            if not isinstance(modules, list):
                continue

            anchorage_count = modules.count("anchorage")
            if anchorage_count:
                add_flat("Anchorages", anchorage_count * 5.0, "starbases")
                if "naval_logistics_office" in buildings:
                    add_flat(
                        "Naval Logistics Office bonus",
                        anchorage_count * 3.0,
                        "starbases",
                    )

            orbital_count = modules.count("orbital_ring_anchorage")
            if orbital_count:
                add_flat("Orbital ring anchorages", orbital_count * 5.0, "starbases")
                if "naval_logistics_office" in buildings:
                    add_flat(
                        "Orbital naval logistics bonus",
                        orbital_count * 3.0,
                        "starbases",
                    )

        for megastructure in self.get_megastructures().get("megastructures", []):
            if not isinstance(megastructure, dict) or megastructure.get("status") != "complete":
                continue
            mega_type = megastructure.get("type")
            amount = _NAVAL_CAP_MEGASTRUCTURE_ADDS.get(str(mega_type))
            if amount:
                add_flat(f"Megastructure ({mega_type})", amount, "megastructures")

        federation_perks = self._get_naval_cap_federation_perk_types(player_country)
        for perk in federation_perks:
            amount = _NAVAL_CAP_FEDERATION_PERK_ADDS.get(perk)
            if amount:
                add_flat(f"Federation perk ({perk})", amount, "federation")

        subject_analysis = self._get_naval_cap_subject_analysis(player_id)
        for term, amount in sorted(subject_analysis["modeled_terms"].items()):
            add_mult(f"Subject term ({term})", amount, "subjects")
        unresolved_families.update(subject_analysis["unresolved_source_families"])

        country_flags = self._get_country_flags(player_country)
        job_analysis = self._get_naval_cap_job_analysis(
            player_country=player_country,
            civics=civics,
            country_flags=country_flags,
            researched_techs=set(researched_techs),
        )
        for job_label, amount in sorted(job_analysis["flat_additions"].items()):
            add_flat(job_label, amount, "jobs")
        unresolved_families.update(job_analysis["unresolved_source_families"])

        resolution_types = self._get_naval_cap_resolution_types()
        if resolution_types:
            unresolved_families.add("galactic_community_resolutions")

        relics = set(self.get_relics().get("relics", []))
        if "r_core_of_the_reckoning" in relics:
            unresolved_families.add("relic_effects")

        relevant_traits = self._get_naval_cap_leader_trait_hits()
        if relevant_traits:
            unresolved_families.add("leader_trait_modifiers")

        active_timed_modifiers = self._get_relevant_timed_naval_modifiers(player_country)
        if active_timed_modifiers:
            unresolved_families.add("timed_modifiers")

        flat_total = round(sum(flat_additions.values()), 3)
        multiplier_total = round(sum(multiplier_additions.values()), 6)
        derived_limit_float = (_BASE_NAVAL_CAP + flat_total) * (1.0 + multiplier_total)
        derived_limit = max(0, int(round(derived_limit_float)))

        if used_capacity > derived_limit:
            derived_status = "over"
        elif used_capacity < derived_limit:
            derived_status = "under"
        else:
            derived_status = "at_limit"

        derived_over_by = max(0, used_capacity - derived_limit)
        can_claim_exact = derived_limit is not None and not unresolved_families
        confidence = "high_derived" if can_claim_exact else "estimated"

        reasons = [f"Base naval cap {_BASE_NAVAL_CAP:.0f}."]
        for label, amount in sorted(flat_additions.items()):
            reasons.append(f"{label}: {self._format_signed_capacity(amount)} flat.")
        for label, amount in sorted(multiplier_additions.items()):
            reasons.append(f"{label}: {self._format_signed_percent(amount)}.")
        if unresolved_families:
            unresolved_list = ", ".join(sorted(unresolved_families))
            reasons.append(
                f"Exact cap is not safe to claim because unresolved source families are active: "
                f"{unresolved_list}."
            )
        else:
            reasons.append("No unresolved naval-cap source families were detected.")

        return {
            "confidence": confidence,
            "formula": "(base + flat_additions) * (1 + multiplier_total)",
            "limit": derived_limit if can_claim_exact else None,
            "derived_limit": derived_limit,
            "status": derived_status if can_claim_exact else "unknown",
            "derived_status": derived_status,
            "over_by": derived_over_by if can_claim_exact and derived_over_by else None,
            "derived_over_by": derived_over_by if derived_over_by else None,
            "upkeep_penalty_applies": (used_capacity > derived_limit) if can_claim_exact else None,
            "safe_to_claim_limit": can_claim_exact,
            "safe_to_claim_over_cap": can_claim_exact,
            "safe_to_claim_penalty": can_claim_exact and used_capacity > derived_limit,
            "modeled_source_families": sorted(modeled_families),
            "unresolved_source_families": sorted(unresolved_families),
            "reasons": reasons,
            "breakdown": {
                "base": int(_BASE_NAVAL_CAP),
                "flat_additions": flat_additions,
                "multiplier_additions": multiplier_additions,
                "flat_additions_total": flat_total,
                "multiplier_total": multiplier_total,
            },
        }

    def _get_naval_cap_difficulty(self) -> str | None:
        """Return the save's galaxy difficulty name when available."""
        session = _get_active_session()
        if not session:
            return None

        galaxy = session.extract_sections(["galaxy"]).get("galaxy", {})
        difficulty = galaxy.get("difficulty") if isinstance(galaxy, dict) else None
        return str(difficulty) if isinstance(difficulty, str) else None

    @staticmethod
    def _get_country_civics(player_country: dict) -> set[str]:
        """Extract cleaned civic IDs from the player country entry."""
        government = player_country.get("government", {})
        civics = government.get("civics", []) if isinstance(government, dict) else []
        if not isinstance(civics, list):
            return set()
        return {civic.replace("civic_", "") for civic in civics if isinstance(civic, str) and civic}

    @staticmethod
    def _get_country_traditions(player_country: dict) -> set[str]:
        """Extract picked traditions from the player country entry."""
        traditions = player_country.get("traditions", [])
        if not isinstance(traditions, list):
            return set()
        return {tradition for tradition in traditions if isinstance(tradition, str)}

    @staticmethod
    def _get_country_ascension_perks(player_country: dict) -> set[str]:
        """Extract picked ascension perks from the player country entry."""
        perks = player_country.get("ascension_perks", [])
        if not isinstance(perks, list):
            return set()
        return {perk for perk in perks if isinstance(perk, str)}

    @staticmethod
    def _get_country_flags(player_country: dict) -> set[str]:
        """Extract active country flag names from the player country entry."""
        flags = player_country.get("flags", {})
        if not isinstance(flags, dict):
            return set()
        return {flag for flag in flags if isinstance(flag, str)}

    def _get_researched_technologies(self, player_id: int) -> list[str]:
        """Return researched technology IDs for the player country."""
        session = _get_active_session()
        if not session:
            return []
        values = session.get_duplicate_values("country", str(player_id), "technology")
        return [value for value in values if isinstance(value, str)]

    @staticmethod
    def _get_active_diplomatic_stance(player_country: dict) -> str | None:
        """Extract the currently selected diplomatic stance."""
        active_policies = player_country.get("active_policies", [])
        if not isinstance(active_policies, list):
            return None

        for policy in active_policies:
            if not isinstance(policy, dict):
                continue
            if policy.get("policy") == "diplomatic_stance":
                selected = policy.get("selected")
                if isinstance(selected, str) and selected:
                    return selected
        return None

    @staticmethod
    def _get_active_edicts(player_country: dict) -> set[str]:
        """Extract active edict IDs from the player country entry."""
        raw_edicts = player_country.get("edicts", [])
        if not isinstance(raw_edicts, list):
            return set()

        edicts: set[str] = set()
        for edict in raw_edicts:
            if not isinstance(edict, dict):
                continue
            edict_name = edict.get("edict")
            if isinstance(edict_name, str) and edict_name:
                edicts.add(edict_name)
        return edicts

    def _get_naval_cap_federation_perk_types(self, player_country: dict) -> list[str]:
        """Extract active federation perk types for the player federation."""
        session = _get_active_session()
        if not session:
            return []

        fed_id = player_country.get("federation")
        if fed_id in (None, "4294967295", 4294967295):
            return []

        with contextlib.suppress(ValueError, TypeError):
            fed_id_str = str(int(fed_id))
            federation = session.get_entry("federation", fed_id_str)
            progression = (
                federation.get("federation_progression") if isinstance(federation, dict) else None
            )
            perks = progression.get("perks") if isinstance(progression, dict) else None
            if not isinstance(perks, list):
                return []

            perk_types: list[str] = []
            for perk in perks:
                if isinstance(perk, dict):
                    perk_type = perk.get("type")
                    if isinstance(perk_type, str) and perk_type:
                        perk_types.append(perk_type)
                elif isinstance(perk, str) and perk:
                    perk_types.append(perk)
            return perk_types
        return []

    def _get_naval_cap_resolution_types(self) -> set[str]:
        """Return active/passed resolution type IDs that can affect naval cap."""
        session = _get_active_session()
        if not session:
            return set()

        gc = session.extract_sections(["galactic_community"]).get("galactic_community")
        if not isinstance(gc, dict):
            return set()

        passed_ids = gc.get("passed", [])
        if not isinstance(passed_ids, list):
            return set()

        resolution_section = session.extract_sections(["resolution"]).get("resolution", {})
        if not isinstance(resolution_section, dict):
            return set()

        relevant_types: set[str] = set()
        for resolution_id in passed_ids:
            with contextlib.suppress(ValueError, TypeError):
                entry = resolution_section.get(str(int(resolution_id)))
                if not isinstance(entry, dict):
                    continue
                type_key = entry.get("type")
                if not isinstance(type_key, str):
                    continue
                if (
                    type_key.startswith("resolution_mutualdefense_")
                    or type_key.startswith("resolution_commerce_")
                    or type_key.startswith("resolution_defenseprivatization_")
                    or type_key.startswith("resolution_sanctions_military")
                    or type_key == "resolution_rulesofwar_demobilization_initiative"
                ):
                    relevant_types.add(type_key)
        return relevant_types

    def _get_naval_cap_subject_analysis(self, player_id: int) -> dict:
        """Extract naval-cap-relevant subject terms and unresolved subject sources."""
        session = _get_active_session()
        if not session:
            return {"modeled_terms": {}, "unresolved_source_families": set()}

        modeled_terms: dict[str, float] = {}
        unresolved_families: set[str] = set()

        data = session.extract_sections(["agreements"])
        agreements_section = data.get("agreements", {})
        inner_agreements = (
            agreements_section.get("agreements", {}) if isinstance(agreements_section, dict) else {}
        )
        if not isinstance(inner_agreements, dict):
            return {
                "modeled_terms": modeled_terms,
                "unresolved_source_families": unresolved_families,
            }

        for agreement in inner_agreements.values():
            if not isinstance(agreement, dict):
                continue
            target = agreement.get("target")
            sender = agreement.get("sender")
            if str(target) != str(player_id) and str(sender) != str(player_id):
                continue

            term_data = agreement.get("term_data")
            if not isinstance(term_data, dict):
                continue

            preset = term_data.get("agreement_preset")
            if isinstance(preset, str) and "scholarium" in preset:
                unresolved_families.add("specialist_subject_penalties")

            discrete_terms = term_data.get("discrete_terms", [])
            if not isinstance(discrete_terms, list):
                continue
            for item in discrete_terms:
                if not isinstance(item, dict) or item.get("key") != "naval_capacity":
                    continue
                value = item.get("value")
                if not isinstance(value, str):
                    continue
                modeled = _NAVAL_CAP_SUBJECT_TERM_MULTS.get(value)
                if modeled is not None:
                    modeled_terms[value] = modeled
                elif value != "naval_cap_unmodified":
                    unresolved_families.add("subject_terms")

        return {
            "modeled_terms": modeled_terms,
            "unresolved_source_families": unresolved_families,
        }

    def _get_naval_cap_job_analysis(
        self,
        *,
        player_country: dict,
        civics: set[str],
        country_flags: set[str],
        researched_techs: set[str],
    ) -> dict:
        """Compute modeled job-based naval cap bonuses and unresolved job families."""
        session = _get_active_session()
        if not session:
            return {"flat_additions": {}, "unresolved_source_families": set()}

        planets = session.extract_sections(["planets"]).get("planets", {}).get("planet", {})
        pop_jobs_section = session.extract_sections(["pop_jobs"]).get("pop_jobs", {})
        if not isinstance(planets, dict) or not isinstance(pop_jobs_section, dict):
            return {"flat_additions": {}, "unresolved_source_families": set()}

        flat_additions: dict[str, float] = defaultdict(float)
        unresolved: set[str] = set()
        soldier_bonus = 1.0 if "tech_ground_defense_planning" in researched_techs else 0.0

        planet_ids = player_country.get("owned_planets", [])
        if isinstance(planet_ids, dict):
            planet_ids = list(planet_ids.values())
        if not isinstance(planet_ids, list):
            return {"flat_additions": {}, "unresolved_source_families": set()}

        for planet_id in planet_ids:
            planet = planets.get(str(planet_id))
            if not isinstance(planet, dict):
                continue
            pop_job_refs = planet.get("pop_jobs", [])
            if isinstance(pop_job_refs, dict):
                pop_job_refs = list(pop_job_refs.values())
            if not isinstance(pop_job_refs, list):
                continue

            for ref in pop_job_refs:
                job = pop_jobs_section.get(str(ref))
                if not isinstance(job, dict):
                    continue
                job_type = job.get("type")
                if not isinstance(job_type, str):
                    continue
                with contextlib.suppress(ValueError, TypeError):
                    workforce = float(job.get("workforce", 0))
                    if abs(workforce) < 1e-6:
                        continue
                    job_units = workforce / 100.0
                    if abs(job_units) < 0.05:
                        continue

                    if job_type == "soldier":
                        flat_additions["Soldier jobs"] += job_units * (2.0 + soldier_bonus)
                    elif job_type == "warrior_drone":
                        flat_additions["Warrior drone jobs"] += job_units * (4.0 + soldier_bonus)
                    elif job_type in {"duelist", "knight", "knight_commander"}:
                        flat_additions[f"{job_type.replace('_', ' ').title()} jobs"] += (
                            job_units * _NAVAL_CAP_JOB_BASE_ADDS[job_type]
                        )
                    elif job_type == "telepath":
                        if "eater_covenant_rank_1" in country_flags:
                            flat_additions["Telepath jobs"] += job_units * 1.5
                        elif "eater_covenant_confirmed" in country_flags:
                            flat_additions["Telepath jobs"] += job_units * 1.0
                    elif job_type == "telepath_drone":
                        if "eater_covenant_rank_1" in country_flags:
                            flat_additions["Telepath drone jobs"] += job_units * 1.5
                        elif "eater_covenant_confirmed" in country_flags:
                            flat_additions["Telepath drone jobs"] += job_units * 1.0
                    elif job_type == "entertainer":
                        if "warrior_culture" in civics:
                            flat_additions["Entertainer/Duelist jobs"] += job_units * 2.0
                        else:
                            unresolved.add("specialist_entertainer_variants")
                    elif job_type in {
                        "experiment_engineer",
                        "skywatcher",
                        "skywatcher_drone",
                        "squire",
                    }:
                        unresolved.add("specialist_job_variants")

        return {
            "flat_additions": {k: round(v, 3) for k, v in flat_additions.items() if v},
            "unresolved_source_families": unresolved,
        }

    def _get_naval_cap_leader_trait_hits(self) -> set[str]:
        """Return any known naval-cap leader traits visible in player leaders."""
        traits: set[str] = set()
        with contextlib.suppress(Exception):
            leaders = self.get_leaders().get("leaders", [])
            for leader in leaders:
                if not isinstance(leader, dict):
                    continue
                for trait in leader.get("traits", []):
                    if isinstance(trait, str) and trait in _NAVAL_CAP_LEADER_TRAIT_HINTS:
                        traits.add(trait)
        return traits

    @staticmethod
    def _get_relevant_timed_naval_modifiers(player_country: dict) -> set[str]:
        """Return active timed modifiers that hint at unresolved naval-cap effects."""
        timed_modifiers = player_country.get("timed_modifier", {})
        items = timed_modifiers.get("items", []) if isinstance(timed_modifiers, dict) else []
        if not isinstance(items, list):
            return set()

        relevant: set[str] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            modifier = item.get("modifier")
            if not isinstance(modifier, str):
                continue
            if any(hint in modifier for hint in _NAVAL_CAP_TIMED_MODIFIER_HINTS):
                relevant.add(modifier)
        return relevant

    @staticmethod
    def _format_signed_capacity(amount: float) -> str:
        """Format a flat naval-cap adjustment with explicit sign."""
        if amount == int(amount):
            return f"{amount:+.0f}"
        return f"{amount:+.2f}"

    @staticmethod
    def _format_signed_percent(amount: float) -> str:
        """Format a naval-cap multiplier as a human-readable percentage."""
        return f"{amount * 100:+.1f}%"

    def get_relics(self) -> dict:
        """Extract owned relics and activation cooldown (best-effort).

        Requires Rust session mode to be active.

        Returns:
            Dict with:
              - relics: list[str]
              - count: int
              - last_activated_relic: str|None
              - last_received_relic: str|None
              - activation_cooldown_days: int|None

        Raises:
            ParserError: If no Rust session is active
        """
        result = {
            "relics": [],
            "count": 0,
            "last_activated_relic": None,
            "last_received_relic": None,
            "activation_cooldown_days": None,
        }

        # Rust session required (get_player_empire_id raises if no session)
        player_id = self.get_player_empire_id()
        country = self._get_player_country_entry(player_id)
        if not country or not isinstance(country, dict):
            return result

        relics = country.get("relics", [])
        if isinstance(relics, list):
            result["relics"] = relics
            result["count"] = len(relics)

        # These fields may not be present in all saves
        result["last_activated_relic"] = country.get("last_activated_relic")
        result["last_received_relic"] = country.get("last_received_relic")

        return result
