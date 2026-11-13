from __future__ import annotations

import contextlib
import logging
import re

# Rust bridge for Clausewitz parsing (required for session mode)
from stellaris_companion.rust_bridge import ParserError, _get_active_session

logger = logging.getLogger(__name__)


class EconomyMixin:
    """Domain methods extracted from the original SaveExtractor."""

    # Observed (Corvus v4.2.4) market arrays include 25 slots, but only 11 are
    # non-zero / tradable in `test_save.sav`. The save does not include a
    # resource-name list for these indices, so we map the commonly-traded set
    # by their observed indices (used consistently across fluctuations/bought/sold).
    _MARKET_RESOURCE_BY_INDEX = {
        0: "energy",
        1: "minerals",
        2: "food",
        9: "consumer_goods",
        10: "alloys",
        11: "volatile_motes",
        12: "exotic_gases",
        13: "rare_crystals",
        14: "sr_living_metal",
        15: "sr_zro",
        16: "sr_dark_matter",
    }

    _BUDGET_TRACKED_RESOURCES = [
        "energy",
        "minerals",
        "food",
        "consumer_goods",
        "alloys",
        "unity",
        "influence",
        "physics_research",
        "society_research",
        "engineering_research",
        "volatile_motes",
        "exotic_gases",
        "rare_crystals",
        "sr_living_metal",
        "sr_zro",
        "sr_dark_matter",
        "minor_artifacts",
        "astral_threads",
        # Appears inside the budget's `trade_policy={...}` breakdown.
        "trade",
    ]

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

    def _parse_number_list_block(self, block: str) -> list[float]:
        """Parse a simple `{ 1 2.5 -3 }` list into floats."""
        if not block:
            return []
        open_brace = block.find("{")
        close_brace = block.rfind("}")
        if open_brace == -1 or close_brace == -1 or close_brace <= open_brace:
            return []
        inner = block[open_brace + 1 : close_brace]
        nums: list[float] = []
        for token in inner.split():
            try:
                nums.append(float(token))
            except ValueError:
                continue
        return nums

    def _parse_country_amount_arrays(self, block: str) -> dict[int, list[int]]:
        """Parse `country=N amount={ ... }` entries into a map."""
        result: dict[int, list[int]] = {}
        if not block:
            return result
        for m in re.finditer(
            r"\bcountry=(\d+)\s*amount=\s*\{\s*([^}]+?)\s*\}",
            block,
            re.DOTALL,
        ):
            try:
                country_id = int(m.group(1))
            except ValueError:
                continue
            nums: list[int] = []
            for token in m.group(2).split():
                try:
                    nums.append(int(token))
                except ValueError:
                    continue
            if nums:
                result[country_id] = nums
        return result

    def _parse_resource_amounts_block(self, block: str) -> dict[str, float]:
        """Parse `{ energy=1 minerals=2.5 }` into a float map (best-effort)."""
        amounts: dict[str, float] = {}
        if not block:
            return amounts
        for key, value in re.findall(r"\b([a-z_]+)=([\d.-]+)", block):
            try:
                amounts[key] = float(value)
            except ValueError:
                continue
        return amounts

    def _extract_block_inner(self, block: str) -> str:
        open_brace = block.find("{")
        close_brace = block.rfind("}")
        if open_brace == -1 or close_brace == -1 or close_brace <= open_brace:
            return ""
        return block[open_brace + 1 : close_brace]

    def get_pop_statistics(self) -> dict:
        """Get detailed population statistics for the player's empire.

        Aggregates pop data across all player-owned planets including:
        - Total pop count
        - Breakdown by species
        - Breakdown by job category (ruler/specialist/worker)
        - Breakdown by stratum
        - Average happiness
        - Employment statistics

        Returns:
            Dict with population statistics:
            {
                "total_pops": 1250,
                "by_species": {"Human": 800, "Blorg": 300, ...},
                "by_job_category": {"ruler": 50, "specialist": 400, ...},
                "by_stratum": {"ruler": 50, "specialist": 400, ...},
                "happiness_avg": 68.5,
                "employed_pops": 1050,
                "unemployed_pops": 200
            }
        """
        session = _get_active_session()
        if not session:
            raise ParserError("Rust session required for get_pop_statistics")

        result = {
            "total_pops": 0,
            "by_species": {},
            "by_job_category": {},
            "by_stratum": {},
            "happiness_avg": 0.0,
            "employed_pops": 0,
            "unemployed_pops": 0,
        }

        # Step 1: Get the player's colony IDs. Pops reference colonies by the
        # country's own colony id space (owned_planets/controlled_colonies),
        # which differs from the planets.planet section keys in 4.x saves.
        planet_ids = self._get_player_colony_ids()
        if not planet_ids:
            return result

        player_planet_set = set(str(pid) for pid in planet_ids)

        # Step 2: Build species ID to name mapping
        species_names = self._get_species_names()

        # Tracking for statistics
        species_counts = {}
        job_category_counts = {}
        stratum_counts = {}
        happiness_sum = 0.0
        happiness_weight = 0
        total_pops = 0

        # Step 3: Iterate over pop_groups section using cached data
        for pop_group_id, entry in self._get_pop_groups_cached().items():
            # Check if this pop group is on a player-owned planet
            planet_id = entry.get("planet")
            if planet_id is None:
                continue
            # Planet ID can be int or string, normalize to string for comparison
            if str(planet_id) not in player_planet_set:
                continue

            # Get the size of this pop group (number of pops)
            size = entry.get("size")
            if size is None:
                continue
            try:
                pop_size = int(size)
            except (ValueError, TypeError):
                continue
            if pop_size == 0:
                continue

            total_pops += pop_size

            # Extract species and category from key nested dict
            key_data = entry.get("key")
            if isinstance(key_data, dict):
                # Extract species ID
                species_id = key_data.get("species")
                if species_id is not None:
                    species_id_str = str(species_id)
                    species_name = species_names.get(species_id_str, f"Species_{species_id_str}")
                    species_counts[species_name] = species_counts.get(species_name, 0) + pop_size

                # Extract category (job category: ruler, specialist, worker, slave, etc.)
                category = key_data.get("category")
                if category:
                    job_category_counts[category] = job_category_counts.get(category, 0) + pop_size
                    # Use category as stratum (they're equivalent in Stellaris)
                    stratum_counts[category] = stratum_counts.get(category, 0) + pop_size

            # Extract happiness (0.0 to 1.0 scale in save, convert to percentage)
            # Use weighted sum for efficiency instead of storing all values
            happiness = entry.get("happiness")
            if happiness is not None:
                try:
                    happiness_val = float(happiness) * 100  # Convert to percentage
                    happiness_sum += happiness_val * pop_size
                    happiness_weight += pop_size
                except (ValueError, TypeError):
                    pass

        # Finalize results
        result["total_pops"] = total_pops
        result["by_species"] = species_counts
        result["by_job_category"] = job_category_counts
        result["by_stratum"] = stratum_counts

        # Employed pops = total minus unemployed category
        unemployed = job_category_counts.get("unemployed", 0)
        result["employed_pops"] = total_pops - unemployed
        result["unemployed_pops"] = unemployed

        # Calculate average happiness
        if happiness_weight > 0:
            result["happiness_avg"] = round(happiness_sum / happiness_weight, 1)

        return result

    def get_resources(self) -> dict:
        """Get the player's resource/economy snapshot.

        Returns:
            Dict with resource stockpiles and monthly income/expenses

        Note:
            Requires active Rust session. Use with rust_bridge.session() context.
        """
        return self._get_resources_rust()

    @staticmethod
    def _resource_amounts(block: object) -> dict[str, float]:
        """Every resource a save block lists with an amount, under the game's own ID for it.

        The game and its mods decide which resources exist. Taking the block as written,
        with no list of expected names, keeps Trade, Nanites and a mod's own resources.
        """
        amounts: dict[str, float] = {}
        if isinstance(block, dict):
            for resource, value in block.items():
                if isinstance(value, (str, int, float)) and not isinstance(value, bool):
                    with contextlib.suppress(ValueError):
                        amounts[resource] = float(value)
        return amounts

    def _get_resources_rust(self) -> dict:
        """Read the player's stockpiles and this month's income and expenses."""
        result = {
            "stockpiles": {},
            "monthly_income": {},
            "monthly_expenses": {},
            "net_monthly": {},
        }

        player_id = self.get_player_empire_id()

        # Use cached player country entry for fast lookup
        player_data = self._get_player_country_entry(player_id)

        if not player_data or not isinstance(player_data, dict):
            result["error"] = "Could not find player country"
            return result

        # Extract stockpiles from modules.standard_economy_module.resources
        modules = player_data.get("modules", {})
        if isinstance(modules, dict):
            econ_module = modules.get("standard_economy_module", {})
            if isinstance(econ_module, dict):
                result["stockpiles"] = self._resource_amounts(econ_module.get("resources"))

        # Extract budget data
        budget = player_data.get("budget", {})
        if not isinstance(budget, dict):
            result["error"] = "Could not find budget section"
            return result

        # The budget has current_month which contains income and expenses
        current_month = budget.get("current_month", {})
        if not isinstance(current_month, dict):
            # Fallback - check for income/expenses directly on budget
            current_month = budget

        # Each side lists its sources (jobs, ships, ...), each with the resources it moves.
        totals: dict[str, dict[str, float]] = {}
        for side in ("income", "expenses"):
            sources = current_month.get(side, {})
            total: dict[str, float] = {}
            for source in sources.values() if isinstance(sources, dict) else ():
                for resource, amount in self._resource_amounts(source).items():
                    total[resource] = total.get(resource, 0) + amount
            totals[side] = total
        income_resources, expenses_resources = totals["income"], totals["expenses"]

        result["monthly_income"] = income_resources
        result["monthly_expenses"] = expenses_resources

        # Calculate net
        for resource in set(list(income_resources.keys()) + list(expenses_resources.keys())):
            income = income_resources.get(resource, 0)
            expense = expenses_resources.get(resource, 0)
            result["net_monthly"][resource] = round(income - expense, 2)

        # Add a summary of key resources
        result["summary"] = {
            "energy_net": result["net_monthly"].get("energy", 0),
            "minerals_net": result["net_monthly"].get("minerals", 0),
            "food_net": result["net_monthly"].get("food", 0),
            "alloys_net": result["net_monthly"].get("alloys", 0),
            "consumer_goods_net": result["net_monthly"].get("consumer_goods", 0),
            "research_total": (
                result["net_monthly"].get("physics_research", 0)
                + result["net_monthly"].get("society_research", 0)
                + result["net_monthly"].get("engineering_research", 0)
            ),
            "volatile_motes_net": result["net_monthly"].get("volatile_motes", 0),
            "exotic_gases_net": result["net_monthly"].get("exotic_gases", 0),
            "rare_crystals_net": result["net_monthly"].get("rare_crystals", 0),
            "living_metal_net": result["net_monthly"].get("sr_living_metal", 0),
            "zro_net": result["net_monthly"].get("sr_zro", 0),
            "dark_matter_net": result["net_monthly"].get("sr_dark_matter", 0),
            "minor_artifacts": result["stockpiles"].get("minor_artifacts", 0),
        }

        # Add strategic resource stockpiles (only if present)
        strategic = {}
        for res in ["sr_living_metal", "sr_zro", "sr_dark_matter"]:
            if res in result["stockpiles"] and result["stockpiles"][res] > 0:
                strategic[res.replace("sr_", "")] = result["stockpiles"][res]
        if strategic:
            result["strategic_stockpiles"] = strategic

        return result

    def get_market(self, top_n: int = 5) -> dict:
        """Get galactic/internal market overview (prices as fluctuations + volumes).

        The save does not embed base prices, so we expose:
        - global fluctuation values (proxy for price pressure)
        - galactic-market availability flags
        - global + player traded volumes (from resources_bought/resources_sold arrays)
        - internal market per-country fluctuation overrides (if present)
        """
        top_n = max(1, min(int(top_n or 5), 10))

        result = {
            "enabled": False,
            "galactic_market_host_country_id": None,
            "galactic_market_host_name": None,
            "player_has_galactic_access": None,
            "resources": {},
            "top_overpriced": [],
            "top_underpriced": [],
            "internal_market_fluctuations": {},
        }

        country_names = self._get_country_names_map()
        market = self._extract_section("market")
        if not market:
            result["error"] = "Could not find market section"
            return result

        enabled_match = re.search(r"\benabled=(yes|no)\b", market)
        if enabled_match:
            result["enabled"] = enabled_match.group(1) == "yes"

        host_match = re.search(r"\n\tcountry=(\d+)\n\}", market)
        if host_match:
            host_id = int(host_match.group(1))
            result["galactic_market_host_country_id"] = host_id
            result["galactic_market_host_name"] = country_names.get(host_id, f"Empire {host_id}")

        fluctuations = self._parse_number_list_block(
            self._extract_braced_block(market, "fluctuations") or ""
        )
        galactic_flags = self._parse_number_list_block(
            self._extract_braced_block(market, "galactic_market_resources") or ""
        )

        # Map access by ID list (id[i] -> access[i]).
        ids = self._parse_number_list_block(self._extract_braced_block(market, "id") or "")
        access_flags = self._parse_number_list_block(
            self._extract_braced_block(market, "galactic_market_access") or ""
        )
        player_id = self.get_player_empire_id()
        try:
            id_to_access = {
                int(ids[i]): int(access_flags[i]) if i < len(access_flags) else 0
                for i in range(len(ids))
                if int(ids[i]) != -1
            }
            result["player_has_galactic_access"] = bool(id_to_access.get(player_id, 0))
        except Exception:
            result["player_has_galactic_access"] = None

        bought_block = self._extract_braced_block(market, "resources_bought") or ""
        sold_block = self._extract_braced_block(market, "resources_sold") or ""
        bought_by_country = self._parse_country_amount_arrays(bought_block)
        sold_by_country = self._parse_country_amount_arrays(sold_block)

        # Compute global totals and player totals for the mapped resources.
        def sum_by_index(country_map: dict[int, list[int]]) -> dict[int, int]:
            totals: dict[int, int] = {}
            for _, nums in country_map.items():
                for i, v in enumerate(nums):
                    if v == 0:
                        continue
                    totals[i] = totals.get(i, 0) + int(v)
            return totals

        global_bought = sum_by_index(bought_by_country)
        global_sold = sum_by_index(sold_by_country)
        player_bought = bought_by_country.get(player_id, [])
        player_sold = sold_by_country.get(player_id, [])

        for idx, resource in self._MARKET_RESOURCE_BY_INDEX.items():
            fluct = None
            if idx < len(fluctuations):
                fluct = float(fluctuations[idx])
            is_galactic = None
            if idx < len(galactic_flags):
                is_galactic = bool(int(galactic_flags[idx]))

            result["resources"][resource] = {
                "fluctuation": fluct,
                "is_galactic": is_galactic,
                "global_bought": int(global_bought.get(idx, 0)),
                "global_sold": int(global_sold.get(idx, 0)),
                "player_bought": (int(player_bought[idx]) if idx < len(player_bought) else 0),
                "player_sold": int(player_sold[idx]) if idx < len(player_sold) else 0,
            }

        # Internal market per-country overrides (if present).
        internal_block = self._extract_braced_block(market, "internal_market_fluctuations") or ""
        if internal_block:
            # Find player's entry: country=<id> resources={ ... }
            m = re.search(
                rf"\bcountry={player_id}\b\s*resources=\s*\{{([^}}]*)\}}",
                internal_block,
                re.DOTALL,
            )
            if m:
                result["internal_market_fluctuations"] = self._parse_resource_amounts_block(
                    m.group(1)
                )

        # Rank by fluctuation if available.
        sortable = [
            (k, v.get("fluctuation"))
            for k, v in result["resources"].items()
            if isinstance(v.get("fluctuation"), (int, float))
        ]
        sortable = [(k, float(v)) for k, v in sortable if v is not None]
        sortable.sort(key=lambda kv: kv[1], reverse=True)
        result["top_overpriced"] = [{"resource": k, "fluctuation": v} for k, v in sortable[:top_n]]
        result["top_underpriced"] = [
            {"resource": k, "fluctuation": v}
            for k, v in sorted(sortable, key=lambda kv: kv[1])[:top_n]
        ]

        return result

    def get_trade_value(self) -> dict:
        """Get trade policy/conversion and a lightweight collection summary."""
        result = {
            "trade_policy": None,
            "trade_conversions": {},
            "trade_policy_income": {},
            "trade_value": None,
            "collection": {
                "starbases_scanned": 0,
                "trade_hub_modules": 0,
                "offworld_trading_companies": 0,
            },
        }

        player_id = self.get_player_empire_id()
        country_content = self._find_player_country_content(player_id)
        if not country_content:
            result["error"] = "Could not find player country block"
            return result

        # Policy selection appears in the policies list.
        policy_match = re.search(
            r'policy="trade_policy"\s*[\r\n\t ]*selected="([^"]+)"',
            country_content,
        )
        if policy_match:
            result["trade_policy"] = policy_match.group(1)

        # Conversions stored as trade_conversions={ energy=... unity=... trade=... consumer_goods=... }
        conversions_block = self._extract_braced_block(country_content, "trade_conversions") or ""
        if conversions_block:
            inner = self._extract_block_inner(conversions_block)
            for k, v in re.findall(r"\b([a-z_]+)=([\d.-]+)", inner):
                try:
                    result["trade_conversions"][k] = float(v)
                except ValueError:
                    continue

        # Budget contains a `trade_policy={...}` category with monthly amounts.
        budget_block = self._extract_braced_block(country_content, "budget") or ""
        if budget_block:
            income_block = self._extract_braced_block(budget_block, "income") or ""
            trade_policy_block = self._extract_braced_block(income_block, "trade_policy") or ""
            if trade_policy_block:
                amounts = self._parse_resource_amounts_block(trade_policy_block)
                result["trade_policy_income"] = amounts
                if "trade" in amounts:
                    result["trade_value"] = amounts.get("trade")

        # Trade collection summary from starbases (best-effort).
        starbases = self.get_starbases()
        sb_list = starbases.get("starbases", []) if isinstance(starbases, dict) else []
        result["collection"]["starbases_scanned"] = len(sb_list)
        hub_count = 0
        offworld_count = 0
        for sb in sb_list:
            modules = sb.get("modules", []) if isinstance(sb, dict) else []
            buildings = sb.get("buildings", []) if isinstance(sb, dict) else []
            hub_count += sum(1 for m in modules if isinstance(m, str) and "trading_hub" in m)
            offworld_count += sum(
                1 for b in buildings if isinstance(b, str) and "offworld_trading_company" in b
            )
        result["collection"]["trade_hub_modules"] = hub_count
        result["collection"]["offworld_trading_companies"] = offworld_count

        return result

    def get_budget_breakdown(self, top_n_sources: int = 5) -> dict:
        """Get budget totals + top sources per resource (compact, non-snapshot)."""
        top_n_sources = max(1, min(int(top_n_sources or 5), 10))

        session = _get_active_session()
        if not session:
            raise ParserError("Rust session required for get_budget_breakdown")

        result = {
            "by_resource": {},
            "tracked_resources": list(self._BUDGET_TRACKED_RESOURCES),
            "income_source_count": 0,
            "expense_source_count": 0,
        }

        player_id = self.get_player_empire_id()
        tracked = set(self._BUDGET_TRACKED_RESOURCES)

        # Get player country entry via Rust session
        player_entry = session.get_entry("country", str(player_id))
        if not player_entry or not isinstance(player_entry, dict):
            result["error"] = "Could not find player country"
            return result

        # Navigate to budget.current_month
        budget = player_entry.get("budget", {})
        if not isinstance(budget, dict):
            result["error"] = "Could not find budget section"
            return result

        current_month = budget.get("current_month", {})
        if not isinstance(current_month, dict):
            # Fallback - check for income/expenses directly on budget
            current_month = budget

        income_section = current_month.get("income", {})
        expenses_section = current_month.get("expenses", {})

        # Build income by category
        income_by_cat: dict[str, dict[str, float]] = {}
        if isinstance(income_section, dict):
            for category, resources in income_section.items():
                if not isinstance(resources, dict):
                    continue
                amounts: dict[str, float] = {}
                for res, val in resources.items():
                    if res not in tracked:
                        continue
                    try:
                        amounts[res] = float(val)
                    except (ValueError, TypeError):
                        continue
                if amounts:
                    income_by_cat[category] = amounts

        # Build expenses by category
        expenses_by_cat: dict[str, dict[str, float]] = {}
        if isinstance(expenses_section, dict):
            for category, resources in expenses_section.items():
                if not isinstance(resources, dict):
                    continue
                amounts: dict[str, float] = {}
                for res, val in resources.items():
                    if res not in tracked:
                        continue
                    try:
                        amounts[res] = float(val)
                    except (ValueError, TypeError):
                        continue
                if amounts:
                    expenses_by_cat[category] = amounts

        result["income_source_count"] = len(income_by_cat)
        result["expense_source_count"] = len(expenses_by_cat)

        # Build per-resource breakdown
        for resource in self._BUDGET_TRACKED_RESOURCES:
            income_total = sum(v.get(resource, 0.0) for v in income_by_cat.values())
            expense_total = sum(v.get(resource, 0.0) for v in expenses_by_cat.values())
            net = round(income_total - expense_total, 2)

            top_income = sorted(
                (
                    {"source": src, "amount": round(vals.get(resource, 0.0), 2)}
                    for src, vals in income_by_cat.items()
                    if vals.get(resource, 0.0) != 0.0
                ),
                key=lambda d: d["amount"],
                reverse=True,
            )[:top_n_sources]

            top_expenses = sorted(
                (
                    {"source": src, "amount": round(vals.get(resource, 0.0), 2)}
                    for src, vals in expenses_by_cat.items()
                    if vals.get(resource, 0.0) != 0.0
                ),
                key=lambda d: d["amount"],
                reverse=True,
            )[:top_n_sources]

            result["by_resource"][resource] = {
                "income_total": round(income_total, 2),
                "expenses_total": round(expense_total, 2),
                "net": net,
                "top_income_sources": top_income,
                "top_expense_sources": top_expenses,
            }

        return result
