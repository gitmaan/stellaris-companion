from __future__ import annotations

# Rust bridge for Clausewitz parsing (required for session mode)
from rust_bridge import _get_active_session


class BriefingMixin:
    """Domain methods extracted from the original SaveExtractor."""

    def search(self, query: str, max_results: int = 5, context_chars: int = 500) -> dict:
        """Search the full gamestate for specific text.

        Args:
            query: Text to search for
            max_results: Maximum number of results to return (capped at 10)
            context_chars: Characters of context around each match (capped at 500)

        Returns:
            Dict with search results (total output capped at ~4000 chars)
        """
        # Cap parameters to prevent context overflow
        max_results = min(max_results, 10)
        context_chars = min(context_chars, 500)
        MAX_TOTAL_OUTPUT = 4000  # Hard limit on total context returned

        result = {"query": query, "matches": [], "total_found": 0}

        # Sanitize query - remove any potential injection characters
        # Allow only alphanumeric, spaces, underscores, and common punctuation
        sanitized_query = "".join(c for c in query if c.isalnum() or c in " _-.,'\"")
        if not sanitized_query:
            result["error"] = "Query contains no valid search characters"
            return result

        query_lower = sanitized_query.lower()
        gamestate_lower = self.gamestate.lower()

        total_context_size = 0
        start = 0

        while len(result["matches"]) < max_results:
            pos = gamestate_lower.find(query_lower, start)
            if pos == -1:
                break

            result["total_found"] += 1

            # Get context
            context_start = max(0, pos - context_chars // 2)
            context_end = min(len(self.gamestate), pos + len(query) + context_chars // 2)

            context = self.gamestate[context_start:context_end]

            # Sanitize context output - escape special characters that could
            # be interpreted as instructions
            context = context.replace("{{", "{ {").replace("}}", "} }")

            # Check if adding this context would exceed our limit
            if total_context_size + len(context) > MAX_TOTAL_OUTPUT:
                result["truncated"] = True
                break

            total_context_size += len(context)

            result["matches"].append({"position": pos, "context": context})

            start = pos + 1

        # Count total matches (without retrieving context)
        while True:
            pos = gamestate_lower.find(query_lower, start)
            if pos == -1:
                break
            result["total_found"] += 1
            start = pos + 1

        return result

    def get_summary(self) -> str:
        """Get a brief text summary of the save for context.

        Returns:
            Short summary string
        """
        meta = self.get_metadata()
        player = self.get_player_status()
        colonies = player.get("colonies", {})

        summary = f"""Save File Summary:
- Empire: {meta.get("name", "Unknown")}
- Date: {meta.get("date", "Unknown")}
- Version: {meta.get("version", "Unknown")}
- Colonies: {colonies.get("total_count", "Unknown")} ({colonies.get("total_population", 0)} pops)
- Fleets: {player.get("fleet_count", "Unknown")}
- Military Power: {player.get("military_power", "Unknown")}
- Economy Power: {player.get("economy_power", "Unknown")}
- Tech Power: {player.get("tech_power", "Unknown")}
"""
        return summary

    def get_full_briefing(self) -> dict:
        """Get comprehensive empire overview for strategic briefings.

        This aggregates data from all major tools into a single response,
        reducing API round-trips from 6+ to 1 for broad questions.

        Returns:
            Dictionary with player status, resources, diplomacy, planets,
            starbases, and leaders (~4k tokens, optimized for context efficiency)
        """
        # Get all data
        player = self.get_player_status()
        resources = self.get_resources()
        diplomacy = self.get_diplomacy()
        subjects = self.get_subjects()
        if isinstance(diplomacy, dict):
            # Add vassals/subjects/overlord agreements (Overlord DLC style).
            diplomacy = dict(diplomacy)
            diplomacy["subjects"] = subjects
        planets = self.get_planets()
        starbases = self.get_starbases()
        leaders = self.get_leaders()
        technology = self.get_technology()

        # Strip raw_data_preview fields to reduce context size
        player_clean = self._strip_previews(player)

        # Build optimized briefing
        return {
            "meta": {
                "empire_name": player_clean.get("empire_name"),
                "date": player_clean.get("date"),
                "player_id": player_clean.get("player_id"),
            },
            "military": {
                "military_power": player_clean.get("military_power"),
                "military_fleets": player_clean.get("military_fleet_count"),
                "military_ships": player_clean.get("military_ships"),
                "starbases": player_clean.get("starbase_count"),
            },
            "economy": {
                "economy_power": player_clean.get("economy_power"),
                "tech_power": player_clean.get("tech_power"),
                # Use 'net_monthly' (correct key) and 'summary' for pre-computed values
                "net_monthly": resources.get("net_monthly", {}),
                "key_resources": {
                    # net_monthly uses bare keys like 'energy', not 'energy_net'
                    "energy": resources.get("net_monthly", {}).get("energy"),
                    "minerals": resources.get("net_monthly", {}).get("minerals"),
                    "alloys": resources.get("net_monthly", {}).get("alloys"),
                    "consumer_goods": resources.get("net_monthly", {}).get("consumer_goods"),
                    "research_total": resources.get("summary", {}).get("research_total"),
                },
            },
            "territory": {
                "celestial_bodies_in_territory": player_clean.get("celestial_bodies_in_territory"),
                "colonies": player_clean.get("colonies", {}),  # Breakdown by habitats vs planets
                "planets_by_type": planets.get("by_type", {}),
                "top_colonies": planets.get("planets", [])[:10],  # Top 10 colonies with details
            },
            "diplomacy": {
                "relation_count": diplomacy.get("relation_count"),
                "allies": diplomacy.get("allies", []),
                "rivals": diplomacy.get("rivals", []),
                "federation": diplomacy.get("federation"),
                "summary": diplomacy.get("summary", {}),
            },
            "defense": {
                "count": starbases.get("count"),
                "by_level": starbases.get("by_level", {}),
                "starbases": starbases.get("starbases", []),
            },
            "leadership": {
                "count": leaders.get("count"),
                "by_class": leaders.get("by_class", {}),
                "leaders": leaders.get("leaders", [])[:15],  # Top 15 leaders
            },
            "technology": {
                "current_research": technology.get("current_research", {}),
                "tech_count": technology.get("tech_count", 0),
                "by_category": technology.get("by_category", {}),
            },
        }

    def _extract_campaign_id(self) -> str | None:
        """Extract the campaign ID (galaxy name UUID) from the save.

        Dispatches to Rust or regex implementation based on session availability.
        """
        session = _get_active_session()
        if session:
            return self._extract_campaign_id_rust()
        return self._extract_campaign_id_regex()

    def _extract_campaign_id_rust(self) -> str | None:
        """Extract campaign ID using Rust extract_sections (session mode)."""
        session = _get_active_session()
        if not session:
            return self._extract_campaign_id_regex()

        try:
            sections = session.extract_sections(["galaxy"])
            galaxy = sections.get("galaxy", {})
            if isinstance(galaxy, dict):
                name = galaxy.get("name")
                if isinstance(name, str) and name:
                    return name
            return None
        except Exception:
            # Fall back to regex on any error
            return self._extract_campaign_id_regex()

    def _extract_campaign_id_regex(self) -> str | None:
        """Extract campaign ID using regex (fallback)."""
        # Stellaris saves include a top-level galaxy block with name="<uuid>".
        start = self.gamestate.find("\ngalaxy=")
        if start == -1:
            if self.gamestate.startswith("galaxy="):
                start = 0
            else:
                return None
        window = self.gamestate[start : start + 20000]
        key = 'name="'
        pos = window.find(key)
        if pos == -1:
            return None
        end = window.find('"', pos + len(key))
        if end == -1:
            return None
        value = window[pos + len(key) : end].strip()
        return value or None

    def get_complete_briefing(self) -> dict:
        """Get a complete, untruncated briefing for /ask injection.

        This is intended for full precompute (Option B): one background extraction
        produces a single JSON blob that contains the full state needed to answer
        most questions without any tool calls.

        Returns:
            Dictionary containing full lists (leaders, planets, relations, fleets,
            starbases, wars, etc.) with no top-k truncation.
        """
        meta = self.get_metadata()
        player = self.get_player_status()
        identity = self.get_empire_identity()
        resources = self.get_resources()

        # Pre-warm the player country content cache for methods that still use regex
        # This saves ~0.45s as many methods share this data
        # In session mode, skip prewarm - use _get_player_country_entry() for O(1) lookup
        player_id = self.get_player_empire_id()
        if not _get_active_session():
            self._find_player_country_content(player_id)

        # Call methods that get_situation() would call - we'll build situation inline
        diplomacy = self.get_diplomacy()
        fallen = self.get_fallen_empires()
        crisis = self.get_crisis_status()
        wars = self.get_wars()

        # Build situation inline from already-fetched data (saves ~1s vs calling get_situation)
        situation = self._build_situation_from_data(
            meta, wars, diplomacy, resources, crisis, fallen
        )

        planets = self.get_planets()
        starbases = self.get_starbases()
        leaders = self.get_leaders()
        technology = self.get_technology()
        fleets = self.get_fleets()
        naval_capacity = self.get_naval_capacity()
        megastructures = self.get_megastructures()
        species = self.get_species_full()
        species_rights = self.get_species_rights()
        claims = self.get_claims()
        armies = self.get_armies()
        lgate = self.get_lgate_status()
        menace = self.get_menace()
        great_khan = self.get_great_khan()
        projects = self.get_special_projects()
        leviathans = self.get_leviathans()

        player_clean = self._strip_previews(player)

        return {
            "meta": {
                "empire_name": player_clean.get("empire_name") or meta.get("name"),
                "date": player_clean.get("date") or meta.get("date"),
                "version": meta.get("version"),
                "player_id": player_clean.get("player_id"),
                "campaign_id": self._extract_campaign_id(),
            },
            "identity": identity,
            "situation": situation,
            # Preserve the "briefing schema" used elsewhere, but without list truncation.
            "military": {
                "military_power": player_clean.get("military_power"),
                "military_fleets": player_clean.get("military_fleet_count"),
                "military_ships": player_clean.get("military_ships"),
                "fleet_size": player_clean.get("fleet_size"),
                "victory_rank": player_clean.get("victory_rank"),
                "naval_capacity": naval_capacity,
                "fleets": fleets,
                "wars": wars,
                "megastructures": megastructures,
                "armies": armies,
            },
            "economy": {
                "economy_power": player_clean.get("economy_power"),
                "tech_power": player_clean.get("tech_power"),
                "resources": resources,
                "net_monthly": resources.get("net_monthly", {}),
                "key_resources": {
                    "energy": resources.get("net_monthly", {}).get("energy"),
                    "minerals": resources.get("net_monthly", {}).get("minerals"),
                    "alloys": resources.get("net_monthly", {}).get("alloys"),
                    "consumer_goods": resources.get("net_monthly", {}).get("consumer_goods"),
                    "research_total": resources.get("summary", {}).get("research_total"),
                },
            },
            "territory": {
                "celestial_bodies_in_territory": player_clean.get("celestial_bodies_in_territory"),
                "colonies": player_clean.get("colonies", {}),
                "planets": planets,
                "claims": claims,
            },
            "diplomacy": diplomacy,
            "defense": starbases,
            "leadership": leaders,
            "technology": technology,
            "fallen_empires": fallen,
            "species": {
                "all_species": species,
                "rights": species_rights,
            },
            "endgame": {
                "crisis": crisis,
                "lgate": lgate,
                "menace": menace,
                "great_khan": great_khan,
            },
            "leviathans": leviathans,
            "projects": projects,
        }

    def get_slim_briefing(self) -> dict:
        """Get slim empire snapshot with NO truncated lists.

        Unlike get_full_briefing(), this only includes COMPLETE data:
        - Summary counts (leaders, planets, starbases)
        - Key numbers (military power, economy)
        - Headlines (capital planet, ruler, current research)
        - NO truncated lists that could cause hallucination

        This forces the model to call get_details() for specific information
        about leaders, planets, diplomacy, etc.

        Returns:
            Dictionary with ~1.5KB of complete summary data
        """
        player = self.get_player_status()
        resources = self.get_resources()
        diplomacy = self.get_diplomacy()
        planets = self.get_planets()
        starbases = self.get_starbases()
        leaders = self.get_leaders()
        technology = self.get_technology()

        # Find capital planet (first planet, usually homeworld)
        all_planets = planets.get("planets", [])
        capital = all_planets[0] if all_planets else {}

        # Find ruler (official class leader, or first leader)
        all_leaders = leaders.get("leaders", [])
        ruler = next(
            (l for l in all_leaders if l.get("class") == "official"),
            all_leaders[0] if all_leaders else {},
        )

        return {
            "meta": {
                "empire_name": player.get("empire_name"),
                "date": player.get("date"),
            },
            "military": {
                "power": player.get("military_power"),
                "military_fleets": player.get("military_fleet_count"),
                "military_ships": player.get("military_ships"),
                "starbases": player.get("starbase_count"),
            },
            "economy": {
                "power": player.get("economy_power"),
                "tech_power": player.get("tech_power"),
                "net_monthly": resources.get("net_monthly", {}),
            },
            "territory": {
                "total_colonies": player.get("colonies", {}).get("total_count", 0),
                "habitats": player.get("colonies", {}).get("habitats", {}),
                "by_type": planets.get("by_type", {}),
                # HEADLINE: Capital only (not all planets)
                "capital": (
                    {
                        "name": capital.get("name"),
                        "type": capital.get("type"),
                        "population": capital.get("population"),
                        "stability": capital.get("stability"),
                    }
                    if capital
                    else None
                ),
            },
            "leadership": {
                "total_count": leaders.get("count"),
                "by_class": leaders.get("by_class", {}),
                # HEADLINE: Ruler only (not all leaders)
                "ruler": (
                    {
                        "name": ruler.get("name"),
                        "class": ruler.get("class"),
                        "level": ruler.get("level"),
                        "traits": ruler.get("traits", []),
                    }
                    if ruler
                    else None
                ),
                # NO leaders list - forces tool use for details
            },
            "diplomacy": {
                "contact_count": diplomacy.get("relation_count"),
                "ally_count": len(diplomacy.get("allies", [])),
                "rival_count": len(diplomacy.get("rivals", [])),
                "federation": diplomacy.get("federation"),
                # NO relations list - forces tool use for details
            },
            "defense": {
                "starbase_count": starbases.get("count"),
                "by_level": starbases.get("by_level", {}),
                # NO starbases list - forces tool use for details
            },
            "technology": {
                "current_research": technology.get("current_research", {}),
                "tech_count": technology.get("tech_count", 0),
                "by_category": technology.get("by_category", {}),
            },
        }

    def get_details(self, categories: list[str], limit: int = 10) -> dict:
        """Get detailed information for one or more categories.

        This is a unified drill-down tool that replaces multiple narrow tools.
        Use get_full_briefing() first to get the overview, then use this tool
        for additional details on specific categories.

        This function supports batching: request multiple categories in one call
        to reduce LLM tool round-trips.

        Args:
            categories: List of categories to return. Each item must be one of:
                - "leaders"
                - "planets"
                - "starbases"
                - "technology"
                - "wars"
                - "fleets"
                - "resources"
                - "diplomacy"
            limit: Max items to return for list-like fields (default 10, capped at 50)

        Returns:
            Dictionary mapping each category to its detailed data.
            If any categories are invalid, an "errors" field is included.
        """
        valid_categories = {
            "leaders",
            "planets",
            "starbases",
            "technology",
            "wars",
            "fleets",
            "resources",
            "diplomacy",
        }

        if not isinstance(categories, list) or not categories:
            return {"error": "categories must be a non-empty list of strings"}

        # Cap limit to prevent excessive output
        limit = min(max(1, limit), 50)

        results: dict[str, dict] = {}
        errors: dict[str, str] = {}

        for category in categories:
            if category not in valid_categories:
                errors[category] = (
                    f"Invalid category. Must be one of: {', '.join(sorted(valid_categories))}"
                )
                continue

            if category == "leaders":
                data = self.get_leaders()
                if "leaders" in data:
                    data["leaders"] = data["leaders"][:limit]
                results[category] = data
                continue

            if category == "planets":
                data = self.get_planets()
                if "planets" in data:
                    data["planets"] = data["planets"][:limit]
                results[category] = data
                continue

            if category == "starbases":
                data = self.get_starbases()
                if "starbases" in data:
                    data["starbases"] = data["starbases"][:limit]
                results[category] = data
                continue

            if category == "technology":
                data = self.get_technology()
                if "sample_technologies" in data:
                    data["sample_technologies"] = data["sample_technologies"][:limit]
                if "completed_technologies" in data:
                    data["completed_technologies"] = data["completed_technologies"][:limit]
                results[category] = data
                continue

            if category == "wars":
                data = self.get_wars()
                if "wars" in data:
                    data["wars"] = data["wars"][:limit]
                results[category] = data
                continue

            if category == "fleets":
                data = self.get_fleets()
                if "fleet_names" in data:
                    data["fleet_names"] = data["fleet_names"][:limit]
                results[category] = data
                continue

            if category == "resources":
                results[category] = self.get_resources()
                continue

            if category == "diplomacy":
                data = self.get_diplomacy()
                if "relations" in data:
                    data["relations"] = data["relations"][:limit]
                results[category] = data
                continue

        out: dict = {"results": results, "limit": limit}
        if errors:
            out["errors"] = errors
        return out

    def _build_situation_from_data(
        self,
        meta: dict,
        wars: dict,
        diplomacy: dict,
        resources: dict,
        crisis: dict,
        fallen: dict,
    ) -> dict:
        """Build situation dict from pre-fetched data (avoids redundant calls).

        This is an internal optimization for get_complete_briefing() which already
        has all the data needed to compute the situation.
        """
        result = {
            "game_phase": "early",
            "year": 2200,
            "at_war": False,
            "war_count": 0,
            "contacts_made": False,
            "contact_count": 0,
            "rivals": [],
            "allies": [],
            "crisis_active": False,
        }

        # Get game date and calculate year
        date_str = meta.get("date", "2200.01.01")
        try:
            year = int(date_str.split(".")[0])
            result["year"] = year

            # Determine game phase
            if year < 2230:
                result["game_phase"] = "early"
            elif year < 2300:
                result["game_phase"] = "mid_early"
            elif year < 2350:
                result["game_phase"] = "mid_late"
            elif year < 2400:
                result["game_phase"] = "late"
            else:
                result["game_phase"] = "endgame"
        except (ValueError, IndexError):
            pass

        # Check war status
        result["war_count"] = wars.get("count", 0)
        result["at_war"] = wars.get("player_at_war", False)
        result["wars"] = wars.get("wars", [])

        # Check diplomatic situation
        result["contact_count"] = diplomacy.get("relation_count", 0)
        result["contacts_made"] = result["contact_count"] > 0
        result["allies"] = diplomacy.get("allies", [])
        result["rivals"] = diplomacy.get("rivals", [])

        # Get economy data
        net_monthly = resources.get("net_monthly", {})
        result["economy"] = {
            "energy_net": net_monthly.get("energy", 0),
            "minerals_net": net_monthly.get("minerals", 0),
            "alloys_net": net_monthly.get("alloys", 0),
            "consumer_goods_net": net_monthly.get("consumer_goods", 0),
            "research_net": (
                net_monthly.get("physics_research", 0)
                + net_monthly.get("society_research", 0)
                + net_monthly.get("engineering_research", 0)
            ),
            "_note": "Raw monthly net values - interpret based on empire size and game phase",
        }

        # Count negative resources
        negative_resources = sum(
            1
            for v in [
                net_monthly.get("energy", 0),
                net_monthly.get("minerals", 0),
                net_monthly.get("food", 0),
                net_monthly.get("consumer_goods", 0),
                net_monthly.get("alloys", 0),
            ]
            if v < 0
        )
        result["economy"]["resources_in_deficit"] = negative_resources

        # Check for crisis
        result["crisis_active"] = crisis.get("crisis_active", False)
        if result["crisis_active"]:
            result["crisis_type"] = crisis.get("crisis_type")
            result["player_is_crisis_fighter"] = crisis.get("player_is_crisis_fighter", False)

        # Check for Fallen Empires
        if fallen.get("total_count", 0) > 0:
            result["fallen_empires"] = {
                "total_count": fallen["total_count"],
                "dormant_count": fallen["dormant_count"],
                "awakened_count": fallen["awakened_count"],
                "war_in_heaven": fallen["war_in_heaven"],
                "empires": [
                    {
                        "name": e["name"],
                        "status": e["status"],
                        "archetype": e["archetype"],
                        "power_ratio": e["power_ratio"],
                    }
                    for e in fallen.get("fallen_empires", [])
                ],
            }

        return result

    def get_situation(self) -> dict:
        """Analyze current game situation for personality tone modifiers.

        This analyzes the current game state to determine appropriate
        tone adjustments for the advisor personality.

        Returns:
            Dictionary with game phase, war status, economy state, and diplomatic situation
        """
        result = {
            "game_phase": "early",
            "year": 2200,
            "at_war": False,
            "war_count": 0,
            "contacts_made": False,
            "contact_count": 0,
            "rivals": [],
            "allies": [],
            "crisis_active": False,
        }

        # Get game date and calculate year
        meta = self.get_metadata()
        date_str = meta.get("date", "2200.01.01")
        try:
            year = int(date_str.split(".")[0])
            result["year"] = year

            # Determine game phase
            if year < 2230:
                result["game_phase"] = "early"
            elif year < 2300:
                result["game_phase"] = "mid_early"
            elif year < 2350:
                result["game_phase"] = "mid_late"
            elif year < 2400:
                result["game_phase"] = "late"
            else:
                result["game_phase"] = "endgame"
        except (ValueError, IndexError):
            pass

        # Check war status - use the improved player-specific war detection
        wars = self.get_wars()
        result["war_count"] = wars.get("count", 0)
        result["at_war"] = wars.get("player_at_war", False)
        result["wars"] = wars.get("wars", [])

        # Check diplomatic situation
        diplomacy = self.get_diplomacy()
        result["contact_count"] = diplomacy.get("relation_count", 0)
        result["contacts_made"] = result["contact_count"] > 0
        result["allies"] = diplomacy.get("allies", [])
        result["rivals"] = diplomacy.get("rivals", [])

        # Get economy data - provide raw values, let the model interpret
        # based on context (empire size, game phase, stockpiles)
        resources = self.get_resources()
        net_monthly = resources.get("net_monthly", {})

        # Provide key resource net values for the model to interpret
        result["economy"] = {
            "energy_net": net_monthly.get("energy", 0),
            "minerals_net": net_monthly.get("minerals", 0),
            "alloys_net": net_monthly.get("alloys", 0),
            "consumer_goods_net": net_monthly.get("consumer_goods", 0),
            "research_net": (
                net_monthly.get("physics_research", 0)
                + net_monthly.get("society_research", 0)
                + net_monthly.get("engineering_research", 0)
            ),
            "_note": "Raw monthly net values - interpret based on empire size and game phase",
        }

        # Count negative resources as a simple indicator
        negative_resources = sum(
            1
            for v in [
                net_monthly.get("energy", 0),
                net_monthly.get("minerals", 0),
                net_monthly.get("food", 0),
                net_monthly.get("consumer_goods", 0),
                net_monthly.get("alloys", 0),
            ]
            if v < 0
        )

        result["economy"]["resources_in_deficit"] = negative_resources

        # Check for crisis using dedicated extractor
        crisis_status = self.get_crisis_status()
        result["crisis_active"] = crisis_status.get("crisis_active", False)
        if result["crisis_active"]:
            result["crisis_type"] = crisis_status.get("crisis_type")
            result["player_is_crisis_fighter"] = crisis_status.get(
                "player_is_crisis_fighter", False
            )

        # Check for Fallen Empires (both dormant and awakened)
        fallen = self.get_fallen_empires()
        if fallen.get("total_count", 0) > 0:
            result["fallen_empires"] = {
                "total_count": fallen["total_count"],
                "dormant_count": fallen["dormant_count"],
                "awakened_count": fallen["awakened_count"],
                "war_in_heaven": fallen["war_in_heaven"],
                "empires": [
                    {
                        "name": e["name"],
                        "status": e["status"],
                        "archetype": e["archetype"],
                        "power_ratio": e["power_ratio"],
                    }
                    for e in fallen["fallen_empires"]
                ],
            }

        return result
