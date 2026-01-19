# Data Model: Resources and Economy

This document describes the data model for extracting resources, budget, trade, and market information from Stellaris save files.

## Overview

The economy system in Stellaris save files is distributed across multiple sections:
- **Stockpiles**: `country.modules.standard_economy_module.resources`
- **Budget (Income/Expenses)**: `country.budget.current_month`
- **Market**: Top-level `market` section
- **Trade**: `country.trade_conversions`, `country.budget.income.trade_policy`

---

## Data Sources

### 1. Resource Stockpiles

**Location**: `country.{id}.modules.standard_economy_module.resources`

The current stockpile of accumulated resources is stored in the player's country block under the `standard_economy_module`.

```
standard_economy_module=
{
    resources=
    {
        energy=99842.73826
        minerals=105894.40984
        food=165000
        consumer_goods=165000
        alloys=19265.14161
        influence=1000
        unity=1432061.78276
        volatile_motes=17214.58451
        exotic_gases=51174.85231
        rare_crystals=53685.21017
        sr_living_metal=3425
        sr_zro=4800
        sr_dark_matter=7318.2
    }
}
```

**Resource Types**:
| Category | Resources |
|----------|-----------|
| Basic | `energy`, `minerals`, `food` |
| Manufactured | `consumer_goods`, `alloys` |
| Research | `physics_research`, `society_research`, `engineering_research` |
| Political | `influence`, `unity` |
| Strategic (Exotic) | `volatile_motes`, `exotic_gases`, `rare_crystals` |
| Strategic (Rare) | `sr_living_metal`, `sr_zro`, `sr_dark_matter` |
| Special | `minor_artifacts`, `astral_threads`, `trade` |

**Extraction Method**: `get_resources()` returns `stockpiles` dict

---

### 2. Budget (Income and Expenses)

**Location**: `country.{id}.budget.current_month`

The budget section contains detailed breakdowns of monthly income and expenses by source category.

```
budget=
{
    current_month=
    {
        income=
        {
            country_base=
            {
                energy=17
                minerals=20
                food=20
                ...
            }
            planet_technician=
            {
                energy=3013.02384
            }
            trade_policy=
            {
                energy=690.14609
                unity=690.14609
                trade=2300.48699
                consumer_goods=690.14609
            }
            ...
        }
        expenses=
        {
            ships=
            {
                energy=129
                alloys=36
            }
            ship_components=
            {
                energy=1664.94
                alloys=306.288
            }
            planet_buildings=
            {
                energy=1560
                volatile_motes=21
                exotic_gases=38
            }
            ...
        }
        balance=
        {
            ...
        }
    }
}
```

**Income Source Categories**:
| Category | Description |
|----------|-------------|
| `country_base` | Base empire income |
| `starbase_buildings` | Starbase building production |
| `starbase_modules` | Starbase module production |
| `orbital_mining_deposits` | Mining station output |
| `orbital_research_deposits` | Research station output |
| `trade_policy` | Trade value conversion to resources |
| `planet_farmers` | Farmer job production |
| `planet_miners` | Miner job production |
| `planet_technician` | Technician job production |
| `planet_metallurgists` | Metallurgist alloy production |
| `planet_artisans` | Artisan consumer goods production |
| `planet_physicists` | Physicist research output |
| `planet_biologists` | Biologist research output |
| `planet_engineers` | Engineer research output |
| `planet_politicians` | Politician unity/research output |
| `planet_traders` | Clerk trade value |
| `pop_factions` | Faction unity from approval |
| `federation` | Federation influence |

**Expense Source Categories**:
| Category | Description |
|----------|-------------|
| `ships` | Fleet upkeep (energy, alloys) |
| `ship_components` | Ship component maintenance |
| `starbases` | Starbase upkeep |
| `starbase_buildings` | Starbase building upkeep |
| `starbase_modules` | Starbase module upkeep |
| `planet_buildings` | Building upkeep (energy, strategic) |
| `planet_districts_*` | District upkeep by type |
| `planet_pops` | Pop upkeep (food, energy) |
| `pop_category_workers` | Worker stratum consumer goods |
| `pop_category_specialists` | Specialist stratum consumer goods |
| `pop_category_rulers` | Ruler stratum consumer goods |
| `leader_*` | Leader upkeep by type |
| `armies` | Army maintenance |
| `megastructures` | Megastructure upkeep |
| `edicts` | Active edict costs |
| `trade_policy` | Trade value consumed by policy |
| `planet_resource_deficit` | Deficit penalties |

**Extraction Methods**:
- `get_resources()` returns `monthly_income`, `monthly_expenses`, `net_monthly`
- `get_budget_breakdown()` returns detailed per-source breakdown with top contributors

---

### 3. Trade Value

**Location**: Multiple locations in country block

Trade value flows through several systems:

#### Trade Conversions
```
trade_conversions=
{
    energy=0.15
    unity=0.15
    trade=0.5
    consumer_goods=0.15
}
```
These values represent the conversion ratios from trade value to output resources based on trade policy.

#### Trade Policy (Budget)
The `income.trade_policy` section in budget shows actual converted resources:
```
trade_policy=
{
    energy=690.14609
    unity=690.14609
    trade=2300.48699
    consumer_goods=690.14609
}
```

#### Trade Policies
| Policy | Conversion |
|--------|------------|
| `trade_policy_wealth_creation` | 1 trade = 1 energy |
| `trade_policy_consumer_benefits` | 1 trade = 0.5 energy + 0.25 consumer goods |
| `trade_policy_marketplace_of_ideas` | 1 trade = 0.5 energy + 0.25 unity |
| `trade_policy_trade_league` | 1 trade = 0.5 energy + 0.15 consumer goods + 0.15 unity |

#### Trade Collection Infrastructure
Trade value is collected by starbases with `trading_hub` modules:
```
starbase_mgr=
{
    starbases=
    {
        0=
        {
            level="starbase_level_citadel"
            type="strading_hub"
            modules=
            {
                0=shipyard
                1=solar_panel_network
                2=trading_hub
                3=trading_hub
                ...
            }
            buildings=
            {
                1=offworld_trading_company
                ...
            }
        }
    }
}
```

**Extraction Method**: `get_trade_value()` returns:
- `trade_policy`: Selected trade policy
- `trade_conversions`: Conversion ratios
- `trade_policy_income`: Monthly converted resources
- `trade_value`: Total trade value being converted
- `collection`: Starbase infrastructure summary

---

### 4. Galactic Market

**Location**: Top-level `market` section

The market section contains global market state and trading history.

```
market=
{
    enabled=yes
    fluctuations=
    {
        -16.3748 11.6976 -27.91761 0 0 0 0 0 0 -44.94935 325.70702 ...
    }
    galactic_market_resources=
    {
        1 1 1 0 0 0 0 0 0 1 1 1 1 1 1 1 1 0 0 ...
    }
    galactic_market_access=
    {
        1 1 1 1 1 1 1 1 0 1 1 1 1 1 1 1 0 ...
    }
    id=
    {
        0 1 2 16777219 16777220 ... -1 -1 ...
    }
    resources_bought=
    {
        country=0
        amount=
        {
            53000 10000 22950 0 0 0 0 0 0 0 35250 1500 1400 2600 3425 4800 4250 ...
        }
        country=1
        amount=
        {
            312000 81200 65000 ...
        }
        ...
    }
    resources_sold=
    {
        country=0
        amount=
        {
            35510 290060 22134 ...
        }
        ...
    }
    internal_market_fluctuations=
    {
        country=0
        resources=
        {
        }
        country=1
        resources=
        {
            minerals=48.91151
            food=-12.84053
            alloys=73.74446
        }
        ...
    }
    country=16777220  # Galactic market host
}
```

**Market Resource Index Mapping**:
| Index | Resource |
|-------|----------|
| 0 | `energy` |
| 1 | `minerals` |
| 2 | `food` |
| 9 | `consumer_goods` |
| 10 | `alloys` |
| 11 | `volatile_motes` |
| 12 | `exotic_gases` |
| 13 | `rare_crystals` |
| 14 | `sr_living_metal` |
| 15 | `sr_zro` |
| 16 | `sr_dark_matter` |

**Fluctuations**: Price modifiers as percentages. Positive = overpriced, negative = underpriced.

**Extraction Method**: `get_market()` returns:
- `enabled`: Market is active
- `galactic_market_host_country_id`: Empire hosting the market
- `player_has_galactic_access`: Player can use galactic market
- `resources`: Per-resource fluctuations, traded volumes
- `top_overpriced`, `top_underpriced`: Best buy/sell opportunities
- `internal_market_fluctuations`: Empire-specific price modifiers

---

## Data Relationships

### Resource Flow Diagram
```
                          +---------------+
                          |   Stockpiles  |
                          | (accumulated) |
                          +-------+-------+
                                  ^
                                  | net = income - expenses
                          +-------+-------+
                          |  Net Monthly  |
                          +-------+-------+
                         /                 \
                +-------+-------+   +-------+-------+
                |    Income     |   |   Expenses    |
                +---------------+   +---------------+
                | - Jobs        |   | - Upkeep      |
                | - Deposits    |   | - Pop needs   |
                | - Trade       |   | - Leaders     |
                | - Base        |   | - Edicts      |
                +---------------+   +---------------+
```

### Trade Value Flow
```
+----------------+     +------------------+     +-----------------+
| Trade Sources  | --> | Trade Collection | --> | Trade Policy    |
| - Traders/Pops |     | - Trading Hubs   |     | Conversion      |
| - Buildings    |     | - Trade Range    |     +--------+--------+
| - Orbital      |     +------------------+              |
+----------------+                                       v
                                               +-----------------+
                                               | Output Resources|
                                               | - Energy        |
                                               | - Unity         |
                                               | - Consumer Goods|
                                               +-----------------+
```

### Market Price Formation
```
+------------------+     +-------------------+
| Global           | --> | Fluctuations      |
| Buy/Sell Volume  |     | (% price change)  |
+------------------+     +-------------------+
                               +
+------------------+     +-------------------+
| Internal Market  | --> | Per-empire        |
| Overrides        |     | Fluctuations      |
+------------------+     +-------------------+
                               |
                               v
                    +-------------------+
                    | Effective Price   |
                    | (base * fluct)    |
                    +-------------------+
```

---

## Expected Invariants

### Resource Values
- All stockpile values should be >= 0
- Income values should be >= 0
- Expense values should be >= 0
- Research stockpiles may accumulate (banking) or be 0 (applied immediately)

### Budget Balance
```
net_monthly[resource] = monthly_income[resource] - monthly_expenses[resource]
```
This should hold for all tracked resources.

### Trade Value
```
trade_value = sum(trade_policy_income values that come from trade)
trade_conversion ratios should sum to <= 1.0
converted_resources = trade_value * conversion_ratio
```

### Market
- `fluctuations` array has 25 slots (only some are tradeable)
- `galactic_market_resources[i] == 1` indicates resource is tradeable on galactic market
- Bought/sold amounts are cumulative totals for the game session

---

## Validation Strategy

### 1. Resource Math Verification
```python
def validate_budget(data):
    for resource in data['net_monthly']:
        income = data['monthly_income'].get(resource, 0)
        expense = data['monthly_expenses'].get(resource, 0)
        expected_net = round(income - expense, 2)
        actual_net = data['net_monthly'][resource]
        assert abs(expected_net - actual_net) < 0.1, f"Budget mismatch for {resource}"
```

### 2. Trade Value Cross-Check
```python
def validate_trade(trade_data, budget_data):
    # Trade policy income in budget should match trade_policy_income
    budget_trade = budget_data.get('income', {}).get('trade_policy', {})
    extracted_trade = trade_data.get('trade_policy_income', {})
    for resource in extracted_trade:
        assert abs(budget_trade.get(resource, 0) - extracted_trade[resource]) < 0.1
```

### 3. Market Price Consistency
```python
def validate_market(market_data):
    for resource, info in market_data['resources'].items():
        fluct = info.get('fluctuation')
        if fluct is not None:
            # Fluctuation should be reasonable (-100 to +500 typical range)
            assert -100 <= fluct <= 1000, f"Unusual fluctuation for {resource}: {fluct}"

        # Galactic flag should be boolean
        assert isinstance(info.get('is_galactic'), bool)

        # Volumes should be non-negative
        assert info.get('global_bought', 0) >= 0
        assert info.get('global_sold', 0) >= 0
```

### 4. Stockpile Sanity Checks
```python
def validate_stockpiles(data):
    stockpiles = data.get('stockpiles', {})
    for resource, value in stockpiles.items():
        # All stockpiles should be non-negative
        assert value >= 0, f"Negative stockpile for {resource}: {value}"

        # Check for unreasonably high values (possible parsing error)
        if resource in ['influence', 'sr_living_metal', 'sr_zro', 'sr_dark_matter']:
            assert value < 100000, f"Suspiciously high value for {resource}: {value}"
        else:
            assert value < 10000000, f"Suspiciously high value for {resource}: {value}"
```

---

## Extraction Code Reference

### Primary Methods (economy.py)

| Method | Returns | Purpose |
|--------|---------|---------|
| `get_resources()` | dict | Stockpiles, income, expenses, net monthly |
| `get_budget_breakdown(top_n)` | dict | Detailed per-source breakdown |
| `get_market(top_n)` | dict | Market prices, volumes, access |
| `get_trade_value()` | dict | Trade policy, conversion, infrastructure |

### Helper Methods

| Method | Purpose |
|--------|---------|
| `_extract_braced_block()` | Extract `key={...}` block from text |
| `_parse_number_list_block()` | Parse `{ 1 2.5 -3 }` to floats |
| `_parse_resource_amounts_block()` | Parse `{ energy=1 minerals=2 }` to dict |
| `_parse_country_amount_arrays()` | Parse `country=N amount={...}` entries |

---

## Known Limitations

1. **Base Prices Not Stored**: The save file does not contain market base prices. Only fluctuations are available. Base prices are defined in game files.

2. **Trade Routes Not Stored**: Individual trade routes are calculated dynamically, not stored in saves. Only aggregate trade value and infrastructure can be extracted.

3. **Monthly Snapshot**: Budget data is a snapshot of `current_month`. Historical data requires multiple save reads.

4. **Resource Index Mapping**: Market arrays use numeric indices without labels. The mapping must be maintained manually and may change between game versions.

5. **Deficit Tracking**: Resource deficits appear in expenses as `planet_resource_deficit` but the specific deficit type isn't always clear.

---

## Version Compatibility

Tested with:
- Stellaris v4.2.4 (Corvus)
- Save format: Zip archive containing `gamestate` and `meta` files

Note: Field positions and names may change between major Stellaris versions. The market resource index mapping is particularly version-sensitive.
