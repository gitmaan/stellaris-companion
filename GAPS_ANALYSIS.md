# Stellaris Companion - Gap Analysis & Feature Roadmap

**Date:** 2026-01-14
**Save Analyzed:** test_save.sav (Corvus v4.2.4, game date 2431.02.18)

---

## Executive Summary

This document analyzes what our save_extractor.py currently extracts vs. what important Stellaris mechanics we're missing. Research includes:
- Analysis of 123 unique data sections in save files
- Comparison with stellaris-dashboard project
- Review of critical Stellaris game mechanics

**Key Finding:** We're missing several high-impact strategic systems including political factions, traditions/ascension perks, fleet composition by ship class, federation details, and galactic community data.

---

## Current Extraction Capabilities

### What We Have

| Method | Data Extracted |
|--------|----------------|
| `get_metadata()` | Empire name, date, version, file size |
| `get_player_status()` | Military/economy/tech power, fleet counts, starbases, colonies |
| `get_empire()` | Specific empire lookup by name |
| `get_wars()` | Active wars, participants, exhaustion, war goals, duration |
| `get_fleets()` | Military fleets, ship counts, military power per fleet |
| `get_leaders()` | Leaders by class, level, traits, age |
| `get_technology()` | Completed techs, current research, research speed, available techs |
| `get_pop_statistics()` | Total pops, by species, by job category, happiness, employment |
| `get_resources()` | Stockpiles, monthly income/expenses, net monthly (18 resource types) |
| `get_diplomacy()` | Relations, treaties, allies, rivals, federation, opinion scores |
| `get_planets()` | Planet details, population, stability, buildings, districts |
| `get_starbases()` | Starbase levels, modules, buildings |
| `get_fallen_empires()` | All Fallen Empires (dormant + awakened), War in Heaven |
| `get_empire_identity()` | Ethics, government, civics, authority, species, gestalt flags |
| `get_full_briefing()` | Aggregated overview of all major data |
| `get_situation()` | Game phase, war status, crisis status, key metrics |

---

## Critical Gaps Identified

### Tier 1: High Strategic Impact (Must Have)

#### 1. Political Factions
**Why Critical:** Internal stability, ethics drift risk, civil war prevention, happiness management

**Data Found in Save:**
```
pop_factions (Line 5213858)
├── country: Owner country ID
├── type: Faction ideology (e.g., "imperialist", "progressive", "isolationist")
├── name: Generated faction name
├── support_percent: 0.51462 = 51.46%
├── support_power: Voting weight (790.10881)
├── faction_approval: Happiness (0.39999 = 40%)
└── members: List of pop IDs (500+ per faction)
```

**Strategic Value:**
- Diagnose why stability is dropping
- Predict ethics shift
- Identify which policies upset which factions
- Civil war risk assessment

---

#### 2. Traditions & Ascension Perks
**Why Critical:** Core progression path, build optimization, ascension timing

**Data Found in Save:**
```
traditions (Line 1655305 in country block)
├── "tr_discovery_adopt" through "tr_discovery_finish"
├── "tr_diplomacy_*" (8 traditions)
├── "tr_mercantile_*" (5 traditions)
├── "tr_expansion_*" (6 traditions)
└── "tr_supremacy_*" (6 traditions)

ascension_perks (Line 1655347)
├── "ap_technological_ascendancy"
├── "ap_interstellar_dominion"
├── "ap_galactic_force_projection"
├── "ap_xeno_compatibility"
├── "ap_synthetic_evolution"
└── "ap_grasp_the_void"
```

**Strategic Value:**
- Recommend next tradition tree
- Identify missing critical perks
- Ascension path guidance (Bio/Synth/Psionic)
- Unity spending optimization

---

#### 3. Fleet Composition by Ship Class
**Why Critical:** Combat advice, counter-building, fleet optimization

**Data Found in Save:**
```
ship_design (Line 4913558)
├── name: "HUM1_CLASS_Ter-Math"
├── ship_size: "corvette", "destroyer", "cruiser", "battleship"
├── section: Hull/armor configuration
└── components:
    ├── MEDIUM_GUN: AUTOCANNON_2, PLASMA_3
    ├── LARGE_GUN: weapon types
    ├── Utilities: ARMOR, REACTORS, THRUSTERS
    └── Hangars, Point Defense, etc.
```

**Strategic Value:**
- "You have too many corvettes, add battleship artillery"
- Counter enemy fleet composition
- Identify outdated ship designs needing upgrade
- Calculate effective fleet power by role

---

#### 4. Federation Details
**Why Critical:** Cohesion management, law optimization, federation XP

**Data Found in Save:**
```
federation (Line 2578124)
├── federation_type: "trade_federation"
├── experience: 20000
├── cohesion: 100 (base_cohesion: 0)
├── levels: 5
├── laws (12 total):
│   ├── succession_type: rotation
│   ├── succession_term: years_20
│   ├── centralization: very_high
│   ├── voting_weight: diplomatic
│   ├── free_migration: yes
│   └── war_declaration_vote: president_vote
├── perks: 13 perks across levels
├── members: Country IDs
└── last_succession_date: "2426.04.21"
```

**Strategic Value:**
- "Cohesion is dropping, assign more envoys"
- Recommend law changes for your goals
- Federation level progression tracking
- Succession timing alerts

---

#### 5. Galactic Community & Council
**Why Critical:** Political power, resolution strategy, custodian/emperor path

**Data Found in Save:**
```
galactic_community (Line 5282005)
├── members: 20 member countries
├── council: 3 council members
├── proposed: 13 pending resolutions
├── passed: 27 successful resolutions
├── failed: 1 failed resolution
├── emissaries: 13 diplomatic representatives
├── voting: Current resolution ID
├── days: 584 days until election
├── community_formed: "2262.01.01"
├── council_established: "2310.06.30"
├── council_positions: 3
├── council_veto: yes
├── emergency_fund: Balance, contribution rate
└── category_timers: Cooldowns per category
```

**Strategic Value:**
- "Vote YES on this resolution, it benefits your economy"
- Council seat strategy
- Custodian timing advice
- Resolution impact analysis

---

### Tier 2: Moderate Strategic Impact (Should Have)

#### 6. Subject/Vassal Management
**Data Found:**
```
agreements (Line 5278897)
├── owner: Overlord country
├── target: Subject country
├── agreement_preset: "preset_scholarium_mean_03"
├── subject_type: scholarium/prospectorium/bulwark
├── terms:
│   ├── can_subject_be_integrated
│   ├── joins_overlord_wars
│   ├── subject_expansion_type
│   └── subject_holdings_limit
├── resource_terms: Tithe rates
└── loyalty: Effect tracking
```

**Strategic Value:**
- Integration timing recommendations
- Loyalty management
- Specialization optimization
- Holdings placement advice

---

#### 7. Market & Trade
**Data Found:**
```
market (Line 5281472)
├── fluctuations: Price data for 25 resources
├── galactic_market_resources: Which resources available
├── galactic_market_access: Country access flags
└── resources_bought: Per-country purchase history
    ├── minerals: 53K
    ├── energy: 312K
    ├── alloys: 35.2K
    └── etc.
```

**Strategic Value:**
- "Alloy prices are high, sell now"
- Arbitrage opportunities
- Market timing for purchases
- Deficit recovery strategies

---

#### 8. Espionage Operations
**Data Found:**
```
espionage_operations (Line 5278717)
├── target: Country being spied on
├── spy_network: Network ID/strength
├── type: "operation_gather_information"
├── difficulty: 2-4 rating
├── days_left: Time remaining
├── info: Intel level (0-6)
└── log: Roll results, skill modifiers
```

**Strategic Value:**
- Operation success probability
- Target prioritization
- Intel level tracking
- Tech theft opportunities

---

#### 9. Pop Happiness Breakdown
**Data Found:**
```
pop_groups (Line 49482)
├── species: Species ID
├── category: worker/slave/specialist
├── planet: Assignment
├── size: Pop count (101, 417, etc.)
├── happiness: 0.175-0.65 range
├── habitability: 0.2-0.65
├── power: Voting weight
├── crime: Level (1.01, 6.8805)
├── amenities_usage: Consumption
├── housing_usage: Requirement
├── pop_faction: Faction affiliation
└── approval_modifier: Faction approval
```

**Strategic Value:**
- Diagnose WHY happiness is low
- Crime hotspot identification
- Amenities deficit alerts
- Housing crisis warnings

---

#### 10. Archaeological Sites & Relics
**Data Found:**
```
archaeological_sites (Line 5276904)
├── location: System/planet
├── type: "site_tiyanki_graveyard"
├── completed: Excavation history with dates
├── index: Completion stage (5 = done)
├── clues: 0-12
├── difficulty: 5-point scale
├── events: Excavation results
│   ├── roll: Investigation roll
│   ├── skill: Modifier
│   └── effect: Rewards (research, etc.)
└── picture: Event graphic
```

**Strategic Value:**
- Excavation prioritization
- Scientist assignment optimization
- Reward tracking
- Precursor chain progress

---

### Tier 3: Nice to Have

| Feature | Data Location | Use Case |
|---------|---------------|----------|
| Debris Fields | `debris` (1000+ entries) | Salvage opportunities |
| Focus Cards | Line 44800 | Focus completion tracking |
| First Contacts | `first_contacts` | Diplomatic approach advice |
| Resolutions | `resolution` (70+ entries) | Voting history analysis |
| Pop Jobs | `pop_jobs` (1000+ slots) | Employment optimization |

---

## Comparison: Us vs stellaris-dashboard

| Category | Our Coverage | Dashboard | Gap |
|----------|-------------|-----------|-----|
| Basic Economy | ✅ Full | ✅ Full | None |
| Strategic Resources | ✅ Full | ✅ Full | None |
| Pop by Species/Job | ✅ Full | ✅ Full | None |
| **Pop by Faction/Ethos** | ❌ None | ✅ Full | **Critical** |
| **Ship Class Breakdown** | ❌ None | ✅ Full | **Critical** |
| Diplomatic Relations | ⚠️ Partial | ✅ Full | 6 types missing |
| **Political Factions** | ❌ None | ✅ Full | **Critical** |
| Budget by Source | ❌ None | ✅ Full | Moderate |
| **Historical Trends** | ❌ None | ✅ Full | **Architecture** |
| **Galactic Market** | ❌ None | ✅ Full | **High** |
| **Federation Details** | ❌ None | ✅ Full | **High** |
| **Traditions/Perks** | ❌ None | ✅ Full | **Critical** |

### Missing Diplomatic Relation Types
- Defensive Pact
- Non-Aggression Pact
- Closed Borders
- Migration Treaty
- Commercial Pact
- Sensor Link

---

## Stellaris Game Mechanics Reference

### Victory Conditions
- **Score Victory**: Highest score at Victory Year (default 2500)
- **Domination Victory**: Conquer/destroy all empires
- **Crisis Victory**: Complete Aetherophasic Engine (Nemesis DLC)
- **Custodian/Emperor**: Political victory through Galactic Community

### Empire Types & Unique Mechanics

| Type | Key Mechanic | Advice Focus |
|------|--------------|--------------|
| Standard | Factions, Consumer Goods | Balance happiness/production |
| Machine Intelligence | No food/CG, energy economy | Energy optimization |
| Hive Mind | No factions, spawning pools | Growth maximization |
| Megacorp | Branch offices, trade focus | Trade value optimization |

### Ascension Paths

| Path | Strengths | Best For |
|------|-----------|----------|
| Psionic | Early unity, Shroud access, psi shields | Early power spike |
| Synthetic | Immortal leaders, 100% habitability | Late game dominance |
| Genetic | Max pop growth, trait customization | Wide playstyles |
| Cybernetic | +20% habitability, balanced bonuses | Trade builds |

### Late Game Threats

| Threat | Trigger | Counter Strategy |
|--------|---------|------------------|
| Prethoryn Scourge | End-game year + RNG | Kinetic weapons, chokepoints |
| Unbidden | End-game year + jump drives | Torpedoes, focused fire |
| Contingency | End-game year + synths | Disable AI, fleet power |
| Awakened Empires | Player strength / crisis | Diplomacy or overwhelming force |
| War in Heaven | Two FEs awaken | League of Non-Aligned or pick side |

### Federation Types

| Type | Focus | Best Laws |
|------|-------|-----------|
| Galactic Union | General | High centralization |
| Martial Alliance | Military | Shared navy |
| Trade League | Commerce | Free migration |
| Research Cooperative | Science | Tech sharing |
| Hegemony | Domination | Forced vassalization |

---

## Implementation Roadmap

### Phase 1: Core Strategic Gaps (Highest Impact)
1. **`get_factions()`** - Political faction support, approval, demands
2. **`get_traditions()`** - Completed traditions, tree progress
3. **`get_ascension_perks()`** - Perks taken, slots available
4. **`get_fleet_composition()`** - Ship counts by class
5. **`get_federation_details()`** - Type, laws, cohesion, experience

### Phase 2: Diplomacy & Politics
6. **`get_galactic_community()`** - Council, resolutions, voting power
7. **`get_subjects()`** - Vassals, specializations, loyalty
8. **Enhanced `get_diplomacy()`** - Add 6 missing relation types

### Phase 3: Economy Deep Dive
9. **`get_market()`** - Current prices, trading volume
10. **`get_trade_value()`** - Trade policy, collection
11. **`get_budget_breakdown()`** - Income/expense by source

### Phase 4: Specialty Systems
12. **`get_espionage()`** - Spy networks, operations
13. **`get_relics()`** - Owned relics, cooldowns
14. **`get_archaeology()`** - Dig sites, completion status

---

## Quick Wins (Easy to Implement)

These use similar patterns to existing extractors:

1. **Traditions** - Same format as technologies, different section
2. **Ascension Perks** - String list in country block
3. **Relics** - Enumerated list like techs
4. **Federation** - Parse federation section by ID
5. **Factions** - Iterate pop_factions section

---

## Data Section Reference

All 123 sections found in save file with line numbers:

| Section | Line | Priority |
|---------|------|----------|
| pop_groups | 49482 | Critical |
| country | 1637873 | Critical |
| traditions | 1655305 | Critical |
| ascension_perks | 1655347 | High |
| federation | 2578124 | High |
| leaders | 2578789 | Medium |
| ship_design | 4913558 | High |
| war | 4880069 | Low |
| debris | 4880076 | Low |
| pop_factions | 5213858 | Critical |
| megastructures | 5218068 | Medium |
| resolution | 5275682 | Medium |
| archaeological_sites | 5276904 | Medium |
| espionage_operations | 5278717 | Medium |
| agreements | 5278897 | High |
| market | 5281472 | High |
| galactic_community | 5282005 | High |
| first_contacts | 5282088 | Low |

---

## Implementation Patterns (from stellaris-dashboard)

These are concrete extraction patterns learned from stellaris-dashboard source code.

### Traditions - EASY
**Location:** Inside country dict under `"traditions"` key
**Format:** Simple list of strings
```python
# In the parsed country dict:
traditions = country_dict.get("traditions", [])
# Returns: ["tr_discovery_adopt", "tr_discovery_science_division", "tr_discovery_finish", ...]
```
**Implementation:** Iterate the list, each item is a tradition ID string like `"tr_discovery_adopt"`.

### Ascension Perks - EASY
**Location:** Inside country dict under `"ascension_perks"` key
**Format:** Simple list of strings
```python
ascension_perks = country_dict.get("ascension_perks", [])
# Returns: ["ap_technological_ascendancy", "ap_one_vision", ...]
```
**Implementation:** Same pattern as traditions. List of perk ID strings.

### Factions - MEDIUM
**Location:** Top-level `pop_factions` section (NOT inside country)
**Format:** Dict keyed by faction ID
```python
for faction_id, faction_dict in gamestate.get("pop_factions", {}).items():
    country_id = faction_dict.get("country")      # Owner country
    faction_name = faction_dict.get("name")       # Display name
    faction_type = faction_dict.get("type")       # e.g., "prosperity", "supremacist"
    leader_id = faction_dict.get("leader", -1)    # Leader pop ID
    support = faction_dict.get("support")         # Support percentage
    approval = faction_dict.get("faction_approval") # Happiness 0-1
```
**Edge Cases:**
- Pseudo-faction IDs: `-1` (no faction), `-2` (slaves), `-3` (purged), `-4` (non-sentient robots)
- Only exists for non-gestalt empires

### Fleet Composition - MEDIUM
**Requires following 3 references:**
```
fleet section → ships list → ships section → ship_design ID → ship_design section → ship_size
```
```python
# 1. Get fleet
fleet_dict = gamestate["fleet"][fleet_id]
ship_ids = fleet_dict.get("ships", [])  # List of ship IDs

# 2. For each ship, get its design
for ship_id in ship_ids:
    ship_dict = gamestate["ships"][ship_id]
    design_id = ship_dict.get("ship_design")

    # 3. Get ship class from design
    design_dict = gamestate["ship_design"][design_id]
    ship_class = design_dict.get("ship_size")  # "corvette", "destroyer", "cruiser", "battleship", "titan", "colossus"
```
**Ship Classes:** `corvette`, `destroyer`, `cruiser`, `battleship`, `titan`, `colossus`, `science`, `constructor`, `colonizer`

### Federation - MEDIUM (Dashboard has limited support)
**Location:** Top-level `federation` section
```python
for fed_id, fed_dict in gamestate.get("federation", {}).items():
    name = fed_dict.get("name")
    members = fed_dict.get("members", [])  # List of country IDs
    federation_type = fed_dict.get("type")
    leader = fed_dict.get("leader")        # Current president country ID
    cohesion = fed_dict.get("cohesion")    # 0-100
    experience = fed_dict.get("experience")
    laws = fed_dict.get("federation_law", {})  # Dict of law settings
```
**Note:** stellaris-dashboard has minimal federation parsing - we can do better.

### Common Gotchas
1. **Null IDs:** `4294967295` (max uint32) means null/none - check for this
2. **Dict validation:** Always `isinstance(x, dict)` before accessing - some entries are non-dict
3. **Name encoding:** Names may be `{key="value"}` structures needing cleanup
4. **Mod compatibility:** Unknown ship_size values from mods - handle gracefully

---

## For Our Regex-Based Parser

Since we use regex on raw gamestate text (not parsed dicts), here's how to adapt:

### Traditions (in country block)
```python
# Find traditions block in player's country section
# Pattern: traditions={ tr_xxx tr_yyy tr_zzz }
traditions_m = re.search(r'traditions=\s*\{([^}]+)\}', player_chunk)
if traditions_m:
    traditions = re.findall(r'(tr_\w+)', traditions_m.group(1))
```

### Ascension Perks (in country block)
```python
# Pattern: ascension_perks={ ap_xxx ap_yyy }
perks_m = re.search(r'ascension_perks=\s*\{([^}]+)\}', player_chunk)
if perks_m:
    perks = re.findall(r'(ap_\w+)', perks_m.group(1))
```

### Factions (top-level section)
```python
# Find pop_factions section, then iterate entries
# Pattern: pop_factions={ 0={ country=X type="..." support=0.5 ... } 1={...} }
faction_section_start = gamestate.find('\npop_factions=')
# Then parse each numbered entry
```

---

## Sources

- stellaris-dashboard: https://github.com/eliasdoehne/stellaris-dashboard
- Stellaru: https://github.com/benreid24/Stellaru
- Stellaris Wiki: https://stellaris.paradoxwikis.com/
- Save file analysis: test_save.sav (Corvus v4.2.4)
