from __future__ import annotations

import contextlib
import logging

# Rust bridge for Clausewitz parsing (required for session mode)
from stellaris_companion.rust_bridge import ParserError, _get_active_session

from .game_vocabulary import WAR_IN_HEAVEN_FLAG
from .save_values import is_yes, repeated

logger = logging.getLogger(__name__)

# Treaties and stances between two empires, as (name here, key in the save's
# relation block). The save keys were read off real 4.2-4.4 saves, except
# defensive_pact and non_aggression_pact, which no available save contains and
# which follow the game's own trigger names (has_defensive_pact, ...).
_TREATY_KEYS = (
    ("defensive_pact", "defensive_pact"),
    ("non_aggression_pact", "non_aggression_pact"),
    ("commercial_pact", "commercial_pact"),
    ("migration_treaty", "migration_access"),
    ("closed_borders", "closed_borders"),
    ("rival", "is_rival"),
)

# Country types that count as diplomatic "empires" for the known-empires tally.
# Everything else in a relations_manager (enclaves, marauders, drones/space fauna,
# pre-FTL primitives, internal event factions) is a relation record but not an
# empire you've made contact with.
DIPLOMATIC_EMPIRE_TYPES = frozenset({"default", "fallen_empire", "awakened_fallen_empire"})


def _is_diplomatic_empire(country_type) -> bool:
    """True if a target country type counts as a known empire (not a special entity)."""
    return country_type in DIPLOMATIC_EMPIRE_TYPES


def _summarize_relation_types(relations: list[dict]) -> dict:
    """Count relations by target country type and how many are real empires.

    Returns ``{"empire_count": int, "by_type": {type: count}}``. ``empire_count`` is
    the count the in-game contacts list roughly reflects; ``relation_count`` (kept
    separately) remains the raw total including special entities.
    """
    by_type: dict[str, int] = {}
    empire_count = 0
    for rel in relations:
        ctype = rel.get("country_type") or "unknown"
        by_type[ctype] = by_type.get(ctype, 0) + 1
        if _is_diplomatic_empire(rel.get("country_type")):
            empire_count += 1
    return {"empire_count": empire_count, "by_type": by_type}


def _format_resolution_name(type_key: str) -> str:
    """Convert a resolution type key to a human-readable name.

    Examples:
        resolution_galactic_market_form → Galactic Market: Form
        resolution_greatergood_workers_rights → Greater Good: Workers Rights
        resolution_mutualdefense_the_readied_shield → Mutual Defense: The Readied Shield
        resolution_sanctions_administrative_2 → Sanctions: Administrative 2
        resolution_commerce_repeal_1 → Commerce: Repeal 1
    """
    # Strip "resolution_" prefix
    key = type_key.removeprefix("resolution_")
    if not key:
        return type_key

    # Known category prefixes (order matters — longest match first)
    categories = [
        ("galactic_market_ban_", "Galactic Market Ban: "),
        ("galactic_market_", "Galactic Market: "),
        ("galacticreforms_", "Galactic Reforms: "),
        ("galacticstudies_", "Galactic Studies: "),
        ("greatergood_", "Greater Good: "),
        ("mutualdefense_", "Mutual Defense: "),
        ("bureaucraticsurveillance_", "Bureaucratic Surveillance: "),
        ("defenseprivatization_", "Defense Privatization: "),
        ("intergalacticdirective_", "Intergalactic Directive: "),
        ("rulesofwar_", "Rules of War: "),
        ("commerce_", "Commerce: "),
        ("ecology_", "Ecology: "),
        ("industry_", "Industry: "),
        ("divinity_", "Divinity: "),
        ("sanctions_", "Sanctions: "),
        ("community_", "Community: "),
        ("development_", "Development: "),
        ("tiyanki_", "Tiyanki: "),
    ]

    for prefix, display in categories:
        if key.startswith(prefix):
            name_part = key[len(prefix) :]
            return display + name_part.replace("_", " ").title()

    # Fallback: just titlecase the whole thing
    return key.replace("_", " ").title()


class DiplomacyMixin:
    """Domain methods extracted from the original SaveExtractor."""

    def get_diplomacy(self) -> dict:
        """Get the player's diplomatic relations.

        Requires Rust session mode to be active.

        Returns:
            Dict with relations, treaties, and diplomatic status with other empires

        Raises:
            ParserError: If no Rust session is active
        """
        return self._get_diplomacy_rust()

    def _get_diplomacy_rust(self) -> dict:
        """Get the player's relations and treaties from the parsed country entry."""
        result = {
            "relations": [],
            "treaties": [],
            "allies": [],
            "rivals": [],
            "federation": None,
            "defensive_pacts": [],
            "non_aggression_pacts": [],
            "closed_borders": [],
            "migration_treaties": [],
            "commercial_pacts": [],
        }

        player_id = self.get_player_empire_id()

        # Get country name mappings for resolving IDs to empire names
        country_names = self._get_country_names_map()

        # Get country authorities for megacorp detection
        country_authorities = self._get_country_authorities_map()

        # Get country ethics for diplomatic context
        country_ethics = self._get_country_ethics_map()

        # Use cached player country entry for federation ID lookup
        federation_id = None
        player_country = self._get_player_country_entry(player_id)
        if player_country and isinstance(player_country, dict):
            fed_val = player_country.get("federation")
            if fed_val and fed_val != "4294967295" and fed_val != 4294967295:
                with contextlib.suppress(ValueError, TypeError):
                    federation_id = int(fed_val)

        if not _get_active_session():
            raise ParserError("Rust session required for get_diplomacy()")
        if not isinstance(player_country, dict):
            result["error"] = "Could not find player country"
            return result
        relations_manager = player_country.get("relations_manager")
        if not isinstance(relations_manager, dict):
            result["error"] = "Could not find relations_manager section"
            return result

        relations_found: list[dict] = []
        allies: list[dict] = []
        treaties: list[dict] = []
        partners: dict[str, list[dict]] = {name: [] for name, _ in _TREATY_KEYS}

        for relation in repeated(relations_manager.get("relation")):
            if not isinstance(relation, dict) or str(relation.get("owner")) != str(player_id):
                continue
            try:
                target_country_id = int(relation["country"])
            except (KeyError, TypeError, ValueError):
                continue

            empire_name = country_names.get(target_country_id, f"Empire {target_country_id}")
            relation_info: dict = {"country_id": target_country_id, "empire_name": empire_name}

            # Record the target's country type so callers can distinguish real
            # empires from special entities (enclaves, marauders, primitives, etc.).
            target_country = self._get_countries_cached().get(str(target_country_id))
            if isinstance(target_country, dict):
                ctype = target_country.get("type")
                if ctype:
                    relation_info["country_type"] = ctype

            # Add authority and megacorp detection
            authority = country_authorities.get(target_country_id)
            if authority:
                relation_info["authority"] = authority
                relation_info["is_megacorp"] = authority == "auth_corporate"

            # Add ethics
            ethics = country_ethics.get(target_country_id)
            if ethics:
                relation_info["ethics"] = ethics

            with contextlib.suppress(KeyError, TypeError, ValueError):
                relation_info["trust"] = int(float(relation["trust"]))
            with contextlib.suppress(KeyError, TypeError, ValueError):
                relation_info["opinion"] = int(float(relation["relation_current"]))

            partner = {"id": target_country_id, "name": empire_name}
            # `alliance` marks an ally (a fellow federation member); it is not a
            # defensive pact, which has its own key.
            if is_yes(relation.get("alliance")):
                relation_info["alliance"] = True
                allies.append(partner)

            for treaty, save_key in _TREATY_KEYS:
                if not is_yes(relation.get(save_key)):
                    continue
                relation_info[treaty] = True
                partners[treaty].append(partner)
                treaties.append(
                    {"country_id": target_country_id, "empire_name": empire_name, "type": treaty}
                )

            if is_yes(relation.get("research_agreement")):
                relation_info["research_agreement"] = True
                treaties.append(
                    {
                        "country_id": target_country_id,
                        "empire_name": empire_name,
                        "type": "research_agreement",
                    }
                )
            if is_yes(relation.get("embassy")):
                relation_info["embassy"] = True
            if "truce" in relation:
                relation_info["has_truce"] = True
            if is_yes(relation.get("communications")):
                relation_info["has_contact"] = True

            relations_found.append(relation_info)

        # Build result
        result["relations"] = relations_found
        result["allies"] = allies
        result["rivals"] = partners["rival"]
        result["defensive_pacts"] = partners["defensive_pact"]
        result["non_aggression_pacts"] = partners["non_aggression_pact"]
        result["closed_borders"] = partners["closed_borders"]
        result["migration_treaties"] = partners["migration_treaty"]
        result["commercial_pacts"] = partners["commercial_pact"]
        result["treaties"] = treaties
        result["relation_count"] = len(relations_found)
        # Segment relations by target type: empire_count reflects actual known
        # empires (what the in-game contacts list roughly shows), while
        # relation_count stays the raw total including enclaves/marauders/etc.
        type_summary = _summarize_relation_types(relations_found)
        result["empire_count"] = type_summary["empire_count"]
        result["relations_by_type"] = type_summary["by_type"]
        result["federation"] = federation_id

        # Summarize by opinion
        positive_relations = len([r for r in relations_found if r.get("opinion", 0) > 0])
        negative_relations = len([r for r in relations_found if r.get("opinion", 0) < 0])
        neutral_relations = len([r for r in relations_found if r.get("opinion", 0) == 0])

        result["summary"] = {
            "positive": positive_relations,
            "negative": negative_relations,
            "neutral": neutral_relations,
            "total_contacts": len(relations_found),
        }

        return result

    def get_federation_details(self) -> dict:
        """Get details for the player's federation (if any).

        Requires Rust session mode to be active.

        Raises:
            ParserError: If no Rust session is active
        """
        return self._get_federation_details_rust()

    def _get_federation_details_rust(self) -> dict:
        """Rust-optimized version using get_entry.

        Uses direct parsed JSON access instead of regex on raw gamestate.
        Benefits:
        - No regex parsing on raw text
        - No truncation limits
        - Handles nested structures correctly
        """
        session = _get_active_session()
        if not session:
            raise ParserError("Rust session required - use 'with session(save_path):' context")

        result = {
            "federation_id": None,
            "name": None,
            "type": None,
            "level": None,
            "cohesion": None,
            "experience": None,
            "laws": {},
            "members": [],
            "member_names": [],
            "president": None,
            "president_name": None,
        }

        # Get player's country entry via Rust session
        player_id = self.get_player_empire_id()
        player_country = self._get_player_country_entry(player_id)
        if not player_country or not isinstance(player_country, dict):
            return result

        # Get federation ID from player's country data
        fed_id = player_country.get("federation")
        if fed_id is None:
            return result

        try:
            fed_id = int(fed_id)
        except (ValueError, TypeError):
            return result

        # 4294967295 represents "none" in Stellaris
        if fed_id == 4294967295:
            return result

        result["federation_id"] = fed_id

        # Get federation entry directly by ID
        fed_entry = session.get_entry("federation", str(fed_id))
        if not fed_entry or not isinstance(fed_entry, dict):
            return result

        result["name"] = self.resolve_name(fed_entry.get("name"), default=None).display

        # Extract president (try 'leader' first, then 'president')
        leader = fed_entry.get("leader")
        if leader is not None:
            with contextlib.suppress(ValueError, TypeError):
                result["president"] = int(leader)
        president = fed_entry.get("president")
        if president is not None:
            with contextlib.suppress(ValueError, TypeError):
                result["president"] = int(president)

        # Extract members
        members = fed_entry.get("members")
        if members and isinstance(members, list):
            member_ids = []
            for m in members:
                try:
                    member_ids.append(int(m))
                except (ValueError, TypeError):
                    continue
            result["members"] = member_ids

        country_names = self._get_country_names_map()
        result["member_names"] = [
            country_names.get(member_id, f"Empire {member_id}") for member_id in result["members"]
        ]
        if result["president"] is not None:
            result["president_name"] = country_names.get(
                result["president"], f"Empire {result['president']}"
            )

        # Extract federation_progression data
        progression = fed_entry.get("federation_progression")
        if progression and isinstance(progression, dict):
            # Federation type
            fed_type = progression.get("federation_type")
            if not fed_type:
                fed_type = progression.get("type")
            if fed_type and isinstance(fed_type, str):
                result["type"] = fed_type

            # Experience (can be string or number)
            exp = progression.get("experience")
            if exp is not None:
                try:
                    exp_str = str(exp)
                    result["experience"] = float(exp_str) if "." in exp_str else int(exp_str)
                except (ValueError, TypeError):
                    pass

            # Cohesion (can be string or number)
            cohesion = progression.get("cohesion")
            if cohesion is not None:
                try:
                    coh_str = str(cohesion)
                    result["cohesion"] = float(coh_str) if "." in coh_str else int(coh_str)
                except (ValueError, TypeError):
                    pass

            # Level (try 'levels' first, then 'level')
            level = progression.get("levels")
            if level is None:
                level = progression.get("level")
            if level is not None:
                with contextlib.suppress(ValueError, TypeError):
                    result["level"] = int(level)

            # Laws
            laws = progression.get("laws")
            if laws and isinstance(laws, dict):
                for key, value in laws.items():
                    if isinstance(value, str):
                        result["laws"][key] = value
                    else:
                        result["laws"][key] = str(value)

        return result

    def get_galactic_community(
        self,
        limit_members: int = 50,
        limit_resolutions: int = 25,
        limit_council: int = 10,
    ) -> dict:
        """Get a compact summary of the Galactic Community and Council.

        Requires Rust session mode to be active.

        Raises:
            ParserError: If no Rust session is active
        """
        return self._get_galactic_community_rust(limit_members, limit_resolutions, limit_council)

    def _get_galactic_community_rust(
        self,
        limit_members: int = 50,
        limit_resolutions: int = 25,
        limit_council: int = 10,
    ) -> dict:
        """Rust-optimized version using extract_sections.

        Uses direct parsed JSON access instead of regex on raw gamestate.
        Benefits:
        - No regex parsing on raw text
        - No truncation limits
        - Handles nested structures correctly
        """
        session = _get_active_session()
        if not session:
            raise ParserError("Rust session required - use 'with session(save_path):' context")

        result = {
            "members": [],
            "members_count": 0,
            "player_is_member": False,
            "council_members": [],
            "council_positions": None,
            "council_veto": None,
            "emissaries_count": 0,
            "voting_resolution_id": None,
            "last_resolution_id": None,
            "days_until_election": None,
            "community_formed": None,
            "council_established": None,
            "proposed_count": 0,
            "passed_count": 0,
            "failed_count": 0,
            "resolutions": {
                "proposed": [],
                "passed": [],
                "failed": [],
            },
        }

        # Use extract_sections for this small top-level section
        data = session.extract_sections(["galactic_community"])
        gc = data.get("galactic_community")

        # Section might not exist if no galactic community formed
        if not gc or not isinstance(gc, dict):
            return result

        def parse_int_list(value) -> list[int]:
            """Convert parsed list of string IDs to integers, filtering invalid values."""
            if not value:
                return []
            if isinstance(value, list):
                result_list = []
                for v in value:
                    try:
                        int_val = int(v)
                        # Filter out 4294967295 (represents "none" in Stellaris)
                        if int_val != 4294967295:
                            result_list.append(int_val)
                    except (ValueError, TypeError):
                        continue
                return result_list
            return []

        # Extract member lists
        members = parse_int_list(gc.get("members"))
        council = parse_int_list(gc.get("council"))
        proposed = parse_int_list(gc.get("proposed"))
        passed = parse_int_list(gc.get("passed"))
        failed = parse_int_list(gc.get("failed"))
        emissaries = parse_int_list(gc.get("emissaries"))

        result["members_count"] = len(members)
        result["members"] = members[: max(0, int(limit_members))]
        result["council_members"] = council[: max(0, int(limit_council))]

        player_id = self.get_player_empire_id()
        result["player_is_member"] = player_id in members

        result["proposed_count"] = len(proposed)
        result["passed_count"] = len(passed)
        result["failed_count"] = len(failed)

        # Resolve resolution IDs to type names from the `resolution` section
        all_ids = set(proposed + passed + failed)
        voting_raw = gc.get("voting")
        if voting_raw is not None:
            with contextlib.suppress(ValueError, TypeError):
                all_ids.add(int(voting_raw))
        resolution_names = self._resolve_resolution_names(session, all_ids)

        def _named_resolutions(id_list: list[int], limit: int) -> list[dict]:
            """Convert ID list to list of {id, name} dicts."""
            out = []
            for rid in id_list[:limit]:
                entry: dict = {"id": rid}
                name = resolution_names.get(rid)
                if name:
                    entry["name"] = name
                out.append(entry)
            return out

        cap = max(0, int(limit_resolutions))
        result["resolutions"]["proposed"] = _named_resolutions(proposed, cap)
        result["resolutions"]["passed"] = _named_resolutions(passed, cap)
        result["resolutions"]["failed"] = _named_resolutions(failed, cap)

        # Extract scalar values from parsed dict
        voting = gc.get("voting")
        if voting is not None:
            with contextlib.suppress(ValueError, TypeError):
                vid = int(voting)
                result["voting_resolution_id"] = vid
                vname = resolution_names.get(vid)
                if vname:
                    result["voting_resolution_name"] = vname

        last = gc.get("last")
        if last is not None:
            with contextlib.suppress(ValueError, TypeError):
                result["last_resolution_id"] = int(last)

        days = gc.get("days")
        if days is not None:
            with contextlib.suppress(ValueError, TypeError):
                result["days_until_election"] = int(days)

        # String values
        community_formed = gc.get("community_formed")
        if community_formed and isinstance(community_formed, str):
            result["community_formed"] = community_formed

        council_established = gc.get("council_established")
        if council_established and isinstance(council_established, str):
            result["council_established"] = council_established

        # Integer values
        council_positions = gc.get("council_positions")
        if council_positions is not None:
            with contextlib.suppress(ValueError, TypeError):
                result["council_positions"] = int(council_positions)

        # Boolean value (stored as "yes"/"no" string)
        council_veto = gc.get("council_veto")
        if council_veto is not None:
            result["council_veto"] = council_veto == "yes"

        result["emissaries_count"] = len(emissaries)

        return result

    @staticmethod
    def _resolve_resolution_names(session, resolution_ids: set[int]) -> dict[int, str]:
        """Look up resolution type names from the `resolution` section.

        Fetches the resolution section and maps each ID to a cleaned-up
        human-readable name derived from the type key.

        Args:
            session: Active Rust parser session.
            resolution_ids: Set of resolution IDs to resolve.

        Returns:
            Dict mapping resolution ID to display name.
        """
        if not resolution_ids:
            return {}

        try:
            data = session.extract_sections(["resolution"])
            res_section = data.get("resolution")
            if not isinstance(res_section, dict):
                return {}
        except Exception:
            return {}

        names: dict[int, str] = {}
        for rid in resolution_ids:
            entry = res_section.get(str(rid))
            if not isinstance(entry, dict):
                continue
            type_key = entry.get("type")
            if not type_key or not isinstance(type_key, str):
                continue
            names[rid] = _format_resolution_name(type_key)

        return names

    def get_subjects(self, limit: int = 25) -> dict:
        """Get subject/overlord agreements involving the player.

        Parses the top-level `agreements` section (Overlord DLC style).
        Returns compact summaries only (no huge discrete term payloads).

        Requires Rust session mode to be active.

        Raises:
            ParserError: If no Rust session is active
        """
        return self._get_subjects_rust(limit)

    def _get_subjects_rust(self, limit: int = 25) -> dict:
        """Rust-optimized version using extract_sections.

        Uses direct parsed JSON access instead of regex on raw gamestate.
        Benefits:
        - No regex parsing on raw text
        - No truncation limits
        - Handles nested structures correctly
        """
        session = _get_active_session()
        if not session:
            raise ParserError("Rust session required - use 'with session(save_path):' context")

        result = {
            "player_id": self.get_player_empire_id(),
            "as_overlord": {"subjects": [], "count": 0},
            "as_subject": {"overlords": [], "count": 0},
            "count": 0,
        }

        # Use extract_sections for this section
        data = session.extract_sections(["agreements"])
        agreements_section = data.get("agreements")

        # Section might not exist if no agreements
        if not agreements_section or not isinstance(agreements_section, dict):
            return result

        # The inner 'agreements' dict contains the actual entries
        inner_agreements = agreements_section.get("agreements")
        if not inner_agreements or not isinstance(inner_agreements, dict):
            return result

        player_id = result["player_id"]
        overlord_entries: list[dict] = []
        subject_entries: list[dict] = []

        def parse_terms_rust(term_data: dict) -> dict:
            """Parse term_data from parsed dict structure."""
            if not isinstance(term_data, dict):
                return {}

            terms: dict = {}

            # Boolean fields (convert "yes"/"no" to bool)
            for bool_key in [
                "can_subject_be_integrated",
                "can_subject_do_diplomacy",
                "can_subject_vote",
                "has_access",
                "has_sensors",
                "has_cooldown_on_first_renegotiation",
            ]:
                val = term_data.get(bool_key)
                if val is not None:
                    terms[bool_key] = (val == "yes") if isinstance(val, str) else bool(val)

            # String fields
            for str_key in [
                "joins_overlord_wars",
                "calls_overlord_to_war",
                "subject_expansion_type",
            ]:
                val = term_data.get(str_key)
                if val and isinstance(val, str):
                    terms[str_key] = val

            # Agreement preset
            preset = term_data.get("agreement_preset")
            if preset and isinstance(preset, str):
                terms["agreement_preset"] = preset

            # Forced initial loyalty
            fil = term_data.get("forced_initial_loyalty")
            if fil is not None:
                with contextlib.suppress(ValueError, TypeError):
                    terms["forced_initial_loyalty"] = int(fil)

            # Discrete terms (list of {key, value} dicts)
            discrete_terms = term_data.get("discrete_terms")
            if discrete_terms and isinstance(discrete_terms, list):
                parsed_discrete = {}
                for item in discrete_terms:
                    if isinstance(item, dict):
                        k = item.get("key")
                        v = item.get("value")
                        if k and v:
                            parsed_discrete[str(k)] = str(v)
                if parsed_discrete:
                    terms["discrete_terms"] = parsed_discrete

            # Resource terms (list of {key, value} dicts)
            resource_terms = term_data.get("resource_terms")
            if resource_terms and isinstance(resource_terms, list):
                parsed_resource = {}
                for item in resource_terms:
                    if isinstance(item, dict):
                        k = item.get("key")
                        v = item.get("value")
                        if k and v is not None:
                            try:
                                parsed_resource[str(k)] = float(v)
                            except (ValueError, TypeError):
                                continue
                if parsed_resource:
                    terms["resource_terms"] = parsed_resource

            return terms

        # Iterate through all agreements
        for agreement_id, adata in inner_agreements.items():
            if not isinstance(adata, dict):
                continue

            # Get owner and target IDs
            owner = adata.get("owner")
            target = adata.get("target")
            if owner is None or target is None:
                continue

            try:
                owner_id = int(owner)
                target_id = int(target)
            except (ValueError, TypeError):
                continue

            # 4294967295 represents "none" in Stellaris
            if owner_id == 4294967295 or target_id == 4294967295:
                continue

            # Extract basic fields
            active_status = adata.get("active_status")
            date_added = adata.get("date_added")
            date_changed = adata.get("date_changed")

            # Parse term_data
            term_data_dict = adata.get("term_data", {})
            term_data = parse_terms_rust(term_data_dict) if isinstance(term_data_dict, dict) else {}

            # Parse subject_specialization
            specialization = None
            spec_level = None
            spec_data = adata.get("subject_specialization")
            if spec_data and isinstance(spec_data, dict):
                spec_type = spec_data.get("specialist_type")
                if spec_type and isinstance(spec_type, str):
                    specialization = spec_type
                level = spec_data.get("level")
                if level is not None:
                    try:
                        spec_level = int(level)
                    except (ValueError, TypeError):
                        spec_level = 0

            entry = {
                "agreement_id": str(agreement_id),
                "owner_id": owner_id,
                "target_id": target_id,
                "active_status": (active_status if isinstance(active_status, str) else None),
                "date_added": date_added if isinstance(date_added, str) else None,
                "date_changed": date_changed if isinstance(date_changed, str) else None,
                "preset": term_data.get("agreement_preset"),
                "specialization": specialization,
                "specialization_level": spec_level,
                "terms": term_data,
            }

            if owner_id == player_id:
                overlord_entries.append(entry)
            if target_id == player_id:
                subject_entries.append(entry)

        # Sort as in regex version
        overlord_entries.sort(key=lambda e: (e.get("preset") or "", e.get("target_id", 0)))
        subject_entries.sort(key=lambda e: (e.get("preset") or "", e.get("owner_id", 0)))

        result["as_overlord"]["count"] = len(overlord_entries)
        result["as_overlord"]["subjects"] = overlord_entries[: max(0, min(int(limit), 50))]
        result["as_subject"]["count"] = len(subject_entries)
        result["as_subject"]["overlords"] = subject_entries[: max(0, min(int(limit), 50))]
        result["count"] = result["as_overlord"]["count"] + result["as_subject"]["count"]

        return result

    def get_fallen_empires(self) -> dict:
        """Get information about all Fallen Empires in the galaxy (both dormant and awakened).

        Fallen Empires are ancient, powerful civilizations. They start dormant but can
        awaken in the late game, becoming major threats or allies.

        Requires Rust session mode to be active.

        Returns:
            Dict with:
                - fallen_empires: List of all FEs with status
                - dormant_count: Number still dormant
                - awakened_count: Number that have awakened
                - war_in_heaven: Whether War in Heaven is active

        Raises:
            ParserError: If no Rust session is active
        """
        return self._get_fallen_empires_rust()

    def _get_fallen_empires_rust(self) -> dict:
        """Optimized Rust-based implementation of get_fallen_empires.

        Uses iter_section to iterate countries once instead of regex scanning
        the 84MB gamestate multiple times.
        """
        session = _get_active_session()
        if not session:
            raise ParserError("Rust session required - use 'with session(save_path):' context")

        result = {
            "fallen_empires": [],
            "dormant_count": 0,
            "awakened_count": 0,
            "total_count": 0,
            "war_in_heaven": False,
        }

        # Get player military power for comparison
        player_status = self.get_player_status()
        player_military = player_status.get("military_power", 0)
        player_id = self.get_player_empire_id()

        result["war_in_heaven"] = WAR_IN_HEAVEN_FLAG in self._get_global_flags()

        # FE archetype mapping
        FE_ARCHETYPES = {
            "xenophile": (
                "Benevolent Interventionists",
                'May awaken to "guide" younger races',
            ),
            "xenophobe": (
                "Militant Isolationists",
                "Hostile if you colonize near them",
            ),
            "materialist": (
                "Ancient Caretakers",
                "Protect galaxy from synthetic threats",
            ),
            "spiritualist": ("Holy Guardians", "Protect holy worlds, hate tomb worlds"),
        }

        # Iterate countries once and filter for fallen empires
        # Uses cached country section to avoid redundant Rust IPC
        for cid, country in self._get_countries_cached().items():
            ctype = country.get("type")
            if ctype not in ("fallen_empire", "awakened_fallen_empire"):
                continue

            status = "awakened" if ctype == "awakened_fallen_empire" else "dormant"

            empire_info = {
                "country_id": int(cid),
                "name": "Unknown Fallen Empire",
                "status": status,
                "archetype": "Unknown",
                "archetype_behavior": "",
                "military_power": 0,
                "power_ratio": 0.0,
                "ethics": None,
            }

            # Extract name from nested structure
            name_data = country.get("name")
            if isinstance(name_data, dict):
                variables = name_data.get("variables", [])
                for var in variables:
                    if isinstance(var, dict) and var.get("key") == "adjective":
                        value = var.get("value", {})
                        if isinstance(value, dict):
                            raw_name = value.get("key", "")
                            empire_info["name"] = (
                                raw_name.replace("SPEC_", "").replace("_", " ").title()
                            )
                            break

            # Extract ethics
            ethos_data = country.get("ethos")
            if isinstance(ethos_data, dict):
                ethic = ethos_data.get("ethic")
                if isinstance(ethic, list):
                    # Multiple ethics - prefer fanatic
                    for e in ethic:
                        if "fanatic" in str(e):
                            empire_info["ethics"] = e
                            break
                    if not empire_info["ethics"] and ethic:
                        empire_info["ethics"] = ethic[0]
                elif ethic:
                    empire_info["ethics"] = ethic

                # Map to FE archetype
                if empire_info["ethics"]:
                    for key, (archetype, behavior) in FE_ARCHETYPES.items():
                        if key in empire_info["ethics"]:
                            empire_info["archetype"] = archetype
                            empire_info["archetype_behavior"] = behavior
                            break

            # Extract military power
            mil_power = country.get("military_power")
            if mil_power is not None:
                empire_info["military_power"] = float(mil_power)
                if player_military > 0:
                    empire_info["power_ratio"] = round(
                        empire_info["military_power"] / player_military, 1
                    )

            # Extract opinion of player from relations_manager
            rm = country.get("relations_manager")
            if isinstance(rm, dict):
                for rel in repeated(rm.get("relation")):
                    if isinstance(rel, dict) and str(rel.get("country")) == str(player_id):
                        # The save leaves the score out of some relation entries.
                        with contextlib.suppress(KeyError, ValueError, TypeError):
                            empire_info["opinion_of_player"] = int(float(rel["relation_current"]))
                        break

            result["fallen_empires"].append(empire_info)

        # Count by status
        result["dormant_count"] = sum(
            1 for fe in result["fallen_empires"] if fe["status"] == "dormant"
        )
        result["awakened_count"] = sum(
            1 for fe in result["fallen_empires"] if fe["status"] == "awakened"
        )
        result["total_count"] = len(result["fallen_empires"])

        return result

    def get_espionage(self, limit: int = 20) -> dict:
        """Get active espionage operations (summary-first, capped).

        Requires Rust session mode to be active.

        Raises:
            ParserError: If no Rust session is active
        """
        return self._get_espionage_rust(limit)

    def _get_espionage_rust(self, limit: int = 20) -> dict:
        """Rust-optimized version using extract_sections.

        Uses direct parsed JSON access instead of regex on raw gamestate.
        Benefits:
        - No regex parsing on raw text
        - No truncation limits
        - Handles nested structures correctly
        """
        session = _get_active_session()
        if not session:
            raise ParserError("Rust session required - use 'with session(save_path):' context")

        limit = max(1, min(int(limit or 20), 50))

        result = {
            "player_id": self.get_player_empire_id(),
            "operations": [],
            "count": 0,
        }

        # Use extract_sections to get the espionage_operations section
        data = session.extract_sections(["espionage_operations"])
        espionage_section = data.get("espionage_operations")

        # Section might not exist if no espionage operations
        if not espionage_section or not isinstance(espionage_section, dict):
            return result

        # The inner 'operations' dict contains the actual entries
        operations_dict = espionage_section.get("operations")
        if not operations_dict or not isinstance(operations_dict, dict):
            return result

        operations_found: list[dict] = []
        country_names = self._get_country_names_map()

        for op_id, op_data in operations_dict.items():
            # P010: Entry might be string "none" (deleted)
            if not isinstance(op_data, dict):
                continue

            entry = {
                "operation_id": op_id,
                "target_country_id": None,
                "spy_network_id": None,
                "type": None,
                "difficulty": None,
                "days_left": None,
                "info": None,
                "log_entries": 0,
                "last_log": None,
            }

            # Extract target country ID and name
            target_data = op_data.get("target")
            if isinstance(target_data, dict):
                target_id = target_data.get("id")
                if target_id is not None:
                    with contextlib.suppress(ValueError, TypeError):
                        target_id_int = int(target_id)
                        entry["target_country_id"] = target_id_int
                        entry["target_empire_name"] = country_names.get(
                            target_id_int, f"Empire {target_id_int}"
                        )

            # Extract spy_network ID
            spy_network = op_data.get("spy_network")
            if spy_network is not None:
                with contextlib.suppress(ValueError, TypeError):
                    entry["spy_network_id"] = int(spy_network)

            # Extract type
            op_type = op_data.get("type")
            if op_type and isinstance(op_type, str):
                entry["type"] = op_type

            # Extract numeric fields
            for key in ["difficulty", "days_left", "info"]:
                val = op_data.get(key)
                if val is not None:
                    with contextlib.suppress(ValueError, TypeError):
                        entry[key] = int(val)

            # Extract log entries
            log_data = op_data.get("log")
            if log_data and isinstance(log_data, list) and len(log_data) > 0:
                entry["log_entries"] = len(log_data)
                # Get last log entry
                last_entry = log_data[-1]
                if isinstance(last_entry, dict):
                    entry["last_log"] = {
                        "date": last_entry.get("date"),
                        "roll": None,
                        "skill": None,
                        "info": None,
                        "difficulty": None,
                    }
                    for log_key in ["roll", "skill", "info", "difficulty"]:
                        val = last_entry.get(log_key)
                        if val is not None:
                            with contextlib.suppress(ValueError, TypeError):
                                entry["last_log"][log_key] = int(val)

            operations_found.append(entry)
            if len(operations_found) >= limit:
                break

        result["operations"] = operations_found
        result["count"] = len(operations_found)
        return result

    def get_claims(self) -> dict:
        """Get territorial claims for the player empire.

        Requires Rust session mode to be active.

        Returns:
            Dict with:
              - player_claims: List of systems the player has claimed
              - claims_against_player: List of claims other empires have on player systems
              - player_claims_count: Number of systems player has claimed
              - claims_against_count: Number of claims against player

        Raises:
            ParserError: If no Rust session is active
        """
        return self._get_claims_rust()

    def _get_claims_rust(self) -> dict:
        """Rust-optimized version using iter_section('galactic_object').

        Uses direct parsed JSON access instead of regex on raw gamestate.
        Benefits:
        - No regex parsing on raw text
        - No truncation limits (10MB chunk limit in regex version)
        - Handles nested structures correctly
        - Uses sectors data for accurate system ownership (vs missing starbase_owner)
        """
        session = _get_active_session()
        if not session:
            raise ParserError("Rust session required - use 'with session(save_path):' context")

        result = {
            "player_claims": [],
            "claims_against_player": [],
            "player_claims_count": 0,
            "claims_against_count": 0,
        }

        player_id = self.get_player_empire_id()

        # Build system -> owner mapping from sectors
        # This is more reliable than the regex starbase_owner approach
        system_owners: dict[str, int] = {}
        sectors_data = session.extract_sections(["sectors"])
        sectors = sectors_data.get("sectors")
        if sectors and isinstance(sectors, dict):
            for sector_id, sector_data in sectors.items():
                if not isinstance(sector_data, dict):
                    continue
                owner = sector_data.get("owner")
                systems = sector_data.get("systems", [])
                if owner is not None and isinstance(systems, list):
                    try:
                        owner_id = int(owner)
                        for sys_id in systems:
                            system_owners[str(sys_id)] = owner_id
                    except (ValueError, TypeError):
                        continue

        player_claims: list[dict] = []
        claims_against: list[dict] = []
        country_names = self._get_country_names_map()

        # Iterate galactic_object to find all systems with claims
        # Uses cached galactic_object section to avoid redundant Rust IPC
        for sys_id, sys_data in self._get_galactic_objects_cached().items():
            claims = sys_data.get("claims")
            if not claims or not isinstance(claims, list):
                continue

            system_name = self.resolve_name(
                sys_data.get("name"), default=f"System {sys_id}"
            ).display

            # Get system owner from our sectors map
            system_owner = system_owners.get(str(sys_id))

            # Process each claim entry
            for claim in claims:
                if not isinstance(claim, dict):
                    continue

                claim_owner = claim.get("owner")
                if claim_owner is None:
                    continue

                try:
                    claim_owner_id = int(claim_owner)
                except (ValueError, TypeError):
                    continue

                # Skip if owner is 4294967295 (none)
                if claim_owner_id == 4294967295:
                    continue

                claim_date = claim.get("date")
                claim_strength_raw = claim.get("claims")
                try:
                    strength = int(claim_strength_raw) if claim_strength_raw else 1
                except (ValueError, TypeError):
                    strength = 1

                claim_info = {
                    "system_id": str(sys_id),
                    "system_name": system_name,
                    "claimant_id": claim_owner_id,
                    "claimant_name": country_names.get(claim_owner_id, f"Empire {claim_owner_id}"),
                    "date": claim_date if isinstance(claim_date, str) else None,
                    "strength": strength,
                }

                # Is this player claiming someone else's system?
                if claim_owner_id == player_id:
                    claim_info["current_owner"] = system_owner
                    player_claims.append(claim_info)
                # Is this someone claiming a player-owned system?
                elif system_owner == player_id:
                    claims_against.append(claim_info)

        # Sort by system name for readability
        player_claims.sort(key=lambda x: x.get("system_name", ""))
        claims_against.sort(key=lambda x: x.get("system_name", ""))

        result["player_claims"] = player_claims
        result["claims_against_player"] = claims_against
        result["player_claims_count"] = len(player_claims)
        result["claims_against_count"] = len(claims_against)

        return result
