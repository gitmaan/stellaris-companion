from __future__ import annotations

import contextlib
import logging
import re

# Rust bridge for Clausewitz parsing (required for session mode)
from rust_bridge import _get_active_session

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
        # Dispatch to Rust version when session is active
        session = _get_active_session()
        if session:
            return self._get_pop_statistics_rust()
        return self._get_pop_statistics_regex()

    def _get_pop_statistics_rust(self) -> dict:
        """Rust-optimized pop statistics using iter_section.

        Benefits over regex version:
        - No 50MB chunk slicing (memory efficient)
        - No regex parsing on nested structures
        - Complete data without truncation risks
        - Direct dict access for fields
        """
        session = _get_active_session()
        if not session:
            return self._get_pop_statistics_regex()

        result = {
            "total_pops": 0,
            "by_species": {},
            "by_job_category": {},
            "by_stratum": {},
            "happiness_avg": 0.0,
            "employed_pops": 0,
            "unemployed_pops": 0,
        }

        # Step 1: Get player's planet IDs (as set of strings for comparison)
        planet_ids = self._get_player_planet_ids()
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

        # Step 3: Iterate over pop_groups section using Rust session
        for pop_group_id, entry in session.iter_section("pop_groups"):
            # P010: entry might be string "none" for deleted entries
            if not isinstance(entry, dict):
                continue

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

    def _get_pop_statistics_regex(self) -> dict:
        """Original regex implementation - fallback for non-session mode."""
        result = {
            "total_pops": 0,
            "by_species": {},
            "by_job_category": {},
            "by_stratum": {},
            "happiness_avg": 0.0,
            "employed_pops": 0,
            "unemployed_pops": 0,
        }

        # Step 1: Get player's planet IDs (as integers for comparison)
        planet_ids = self._get_player_planet_ids()
        if not planet_ids:
            return result

        player_planet_set = set(int(pid) for pid in planet_ids)

        # Step 2: Build species ID to name mapping
        species_names = self._get_species_names()

        # Step 3: Find pop_groups section (this is where actual pop data lives)
        # Structure: pop_groups=\n{\n\tID=\n\t{ key={ species=X category="Y" } planet=Z size=N happiness=H ... }
        pop_groups_match = re.search(r"\npop_groups=\n\{", self.gamestate)
        if not pop_groups_match:
            # Fallback: try alternate format
            pop_groups_match = re.search(r"^pop_groups=\s*\{", self.gamestate, re.MULTILINE)
            if not pop_groups_match:
                result["error"] = "Could not find pop_groups section"
                return result

        pop_start = pop_groups_match.start()
        # Pop groups section can be large in late game
        pop_chunk = self.gamestate[pop_start : pop_start + 50000000]  # Up to 50MB

        # Tracking for statistics
        species_counts = {}
        job_category_counts = {}
        stratum_counts = {}
        happiness_values = []
        total_pops = 0

        # Parse pop groups - each group represents multiple pops of same type
        # Format: \n\tID=\n\t{ ... key={ species=X category="Y" } ... planet=Z size=N ...
        pop_pattern = r"\n\t(\d+)=\n\t\{"
        groups_processed = 0
        max_groups = 50000  # Safety limit

        for match in re.finditer(pop_pattern, pop_chunk):
            if groups_processed >= max_groups:
                result["_note"] = f"Processed {max_groups} pop groups (limit reached)"
                break

            groups_processed += 1
            block_start = match.start() + 1

            # Get pop group block content
            block_chunk = pop_chunk[block_start : block_start + 2500]

            # Find end of this pop group's block
            brace_count = 0
            block_end = 0
            started = False
            for i, char in enumerate(block_chunk):
                if char == "{":
                    brace_count += 1
                    started = True
                elif char == "}":
                    brace_count -= 1
                    if started and brace_count == 0:
                        block_end = i + 1
                        break

            pop_block = block_chunk[:block_end] if block_end > 0 else block_chunk

            # Check if this pop group is on a player-owned planet
            planet_match = re.search(r"\n\s*planet=(\d+)", pop_block)
            if not planet_match:
                continue

            planet_id = int(planet_match.group(1))
            if planet_id not in player_planet_set:
                continue

            # Get the size of this pop group (number of pops)
            size_match = re.search(r"\n\s*size=(\d+)", pop_block)
            if not size_match:
                continue

            pop_size = int(size_match.group(1))
            if pop_size == 0:
                continue

            total_pops += pop_size

            # Extract species from key={ species=X ... } block
            # Species is inside the nested key block
            key_match = re.search(r"key=\s*\{([^}]+)\}", pop_block)
            if key_match:
                key_block = key_match.group(1)

                # Extract species ID
                species_match = re.search(r"species=(\d+)", key_block)
                if species_match:
                    species_id = species_match.group(1)
                    species_name = species_names.get(species_id, f"Species_{species_id}")
                    species_counts[species_name] = species_counts.get(species_name, 0) + pop_size

                # Extract category (job category: ruler, specialist, worker, slave, etc.)
                category_match = re.search(r'category="([^"]+)"', key_block)
                if category_match:
                    category = category_match.group(1)
                    job_category_counts[category] = job_category_counts.get(category, 0) + pop_size
                    # Use category as stratum (they're equivalent in Stellaris)
                    stratum_counts[category] = stratum_counts.get(category, 0) + pop_size

            # Extract happiness (0.0 to 1.0 scale in save, convert to percentage)
            # Weight by pop size for accurate average
            happiness_match = re.search(r"\n\s*happiness=([\d.]+)", pop_block)
            if happiness_match:
                happiness = float(happiness_match.group(1))
                # Add each pop's happiness (weighted by size)
                happiness_values.extend([happiness * 100] * pop_size)

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
        if happiness_values:
            result["happiness_avg"] = round(sum(happiness_values) / len(happiness_values), 1)

        return result

    def get_resources(self) -> dict:
        """Get the player's resource/economy snapshot.

        Returns:
            Dict with resource stockpiles and monthly income/expenses

        Note:
            Requires active Rust session. Use with rust_bridge.session() context.
        """
        return self._get_resources_rust()

    def _get_resources_rust(self) -> dict:
        """Get resource information using Rust parser."""
        result = {
            "stockpiles": {},
            "monthly_income": {},
            "monthly_expenses": {},
            "net_monthly": {},
        }

        player_id = self.get_player_empire_id()

        # All tracked resources
        ALL_RESOURCES = [
            "energy",
            "minerals",
            "food",
            "consumer_goods",
            "alloys",
            "physics_research",
            "society_research",
            "engineering_research",
            "influence",
            "unity",
            "volatile_motes",
            "exotic_gases",
            "rare_crystals",
            "sr_living_metal",
            "sr_zro",
            "sr_dark_matter",
            "minor_artifacts",
            "astral_threads",
        ]

        # Use cached player country entry for fast lookup
        player_data = self._get_player_country_entry(player_id)

        if not player_data or not isinstance(player_data, dict):
            result["error"] = "Could not find player country"
            return result

        # Extract stockpiles from standard_economy_module.resources
        econ_module = player_data.get("standard_economy_module", {})
        if isinstance(econ_module, dict):
            resources = econ_module.get("resources", {})
            if isinstance(resources, dict):
                for resource in ALL_RESOURCES:
                    if resource in resources:
                        with contextlib.suppress(ValueError, TypeError):
                            result["stockpiles"][resource] = float(resources[resource])

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

        income_section = current_month.get("income", {})
        expenses_section = current_month.get("expenses", {})

        # Sum up income from all sources
        income_resources = {}
        if isinstance(income_section, dict):
            for source, resources in income_section.items():
                if isinstance(resources, dict):
                    for resource, value_str in resources.items():
                        if resource in ALL_RESOURCES:
                            try:
                                value = float(value_str)
                                income_resources[resource] = (
                                    income_resources.get(resource, 0) + value
                                )
                            except (ValueError, TypeError):
                                pass

        result["monthly_income"] = income_resources

        # Sum up expenses from all sources
        expenses_resources = {}
        if isinstance(expenses_section, dict):
            for source, resources in expenses_section.items():
                if isinstance(resources, dict):
                    for resource, value_str in resources.items():
                        if resource in ALL_RESOURCES:
                            try:
                                value = float(value_str)
                                expenses_resources[resource] = (
                                    expenses_resources.get(resource, 0) + value
                                )
                            except (ValueError, TypeError):
                                pass

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
            "player_has_galactic_access": None,
            "resources": {},
            "top_overpriced": [],
            "top_underpriced": [],
            "internal_market_fluctuations": {},
        }

        market = self._extract_section("market")
        if not market:
            result["error"] = "Could not find market section"
            return result

        enabled_match = re.search(r"\benabled=(yes|no)\b", market)
        if enabled_match:
            result["enabled"] = enabled_match.group(1) == "yes"

        host_match = re.search(r"\n\tcountry=(\d+)\n\}", market)
        if host_match:
            result["galactic_market_host_country_id"] = int(host_match.group(1))

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

        # Dispatch to Rust version when session is active
        session = _get_active_session()
        if session:
            return self._get_budget_breakdown_rust(top_n_sources)
        return self._get_budget_breakdown_regex(top_n_sources)

    def _get_budget_breakdown_rust(self, top_n_sources: int = 5) -> dict:
        """Rust-optimized budget breakdown using get_entry for direct dict access.

        Benefits over regex version:
        - No brace counting or regex parsing
        - Direct dict access for budget structure
        - Complete data without truncation risks
        - Cleaner code with less parsing logic
        """
        session = _get_active_session()
        if not session:
            return self._get_budget_breakdown_regex(top_n_sources)

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

    def _get_budget_breakdown_regex(self, top_n_sources: int = 5) -> dict:
        """Original regex implementation - fallback for non-session mode."""

        result = {
            "by_resource": {},
            "tracked_resources": list(self._BUDGET_TRACKED_RESOURCES),
            "income_source_count": 0,
            "expense_source_count": 0,
        }

        player_id = self.get_player_empire_id()
        country_content = self._find_player_country_content(player_id)
        if not country_content:
            result["error"] = "Could not find player country block"
            return result

        budget_block = self._extract_braced_block(country_content, "budget")
        if not budget_block:
            result["error"] = "Could not find budget block"
            return result

        income_block = self._extract_braced_block(budget_block, "income") or ""
        expenses_block = self._extract_braced_block(budget_block, "expenses") or ""

        tracked = set(self._BUDGET_TRACKED_RESOURCES)

        def extract_top_level_categories(block: str) -> dict[str, dict[str, float]]:
            categories: dict[str, dict[str, float]] = {}
            if not block:
                return categories
            inner = self._extract_block_inner(block)
            if not inner:
                return categories

            candidates = list(re.finditer(r"\n\s*([A-Za-z0-9_]+)\s*=\s*\{", inner))
            pos = 0
            depth = 0

            def extract_block_from(start_idx: int) -> tuple[str, int]:
                brace_count = 0
                started = False
                for i, ch in enumerate(inner[start_idx:], start_idx):
                    if ch == "{":
                        brace_count += 1
                        started = True
                    elif ch == "}":
                        brace_count -= 1
                        if started and brace_count == 0:
                            return inner[start_idx : i + 1], i + 1
                return inner[start_idx:], len(inner)

            for m in candidates:
                if m.start() < pos:
                    continue
                depth += inner[pos : m.start()].count("{") - inner[pos : m.start()].count("}")
                pos = m.start()
                if depth != 0:
                    continue

                category = m.group(1)
                cat_block, end_pos = extract_block_from(pos)
                pos = end_pos
                depth = 0

                amounts: dict[str, float] = {}
                for res, val in re.findall(r"\b([a-z_]+)=([\d.-]+)", cat_block):
                    if res not in tracked:
                        continue
                    try:
                        amounts[res] = amounts.get(res, 0.0) + float(val)
                    except ValueError:
                        continue
                if amounts:
                    categories[category] = amounts

            return categories

        income_by_cat = extract_top_level_categories(income_block)
        expenses_by_cat = extract_top_level_categories(expenses_block)
        result["income_source_count"] = len(income_by_cat)
        result["expense_source_count"] = len(expenses_by_cat)

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
