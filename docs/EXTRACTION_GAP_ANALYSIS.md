# Extraction Gap Analysis

**Date:** 2026-01-15
**Method:** Simulated player questions across game phases + capability audit
**Status:** Analysis Complete

---

## Executive Summary

We analyzed **120+ realistic player questions** across early/mid/late game and 6 specialized playstyles against our **26 extraction methods**.

**Key Finding:** We cover ~60% of what players commonly ask. The remaining 40% falls into three categories:
- **Easy wins** (15%): Data exists in save, just need new extractors
- **Moderate effort** (15%): Complex parsing but feasible
- **Hard/Impossible** (10%): Requires game knowledge DB or unavailable data

---

## Gap Categories

### Legend
- ✅ **HAVE** - Currently extracted
- ⚠️ **PARTIAL** - Have some data but incomplete
- ❌ **MISSING** - Not extracted but feasible
- 🔴 **HARD** - Requires external data or complex logic

---

## Category 1: EXPLORATION & MAP DATA

| Data Point | Status | Player Need | Notes |
|------------|--------|-------------|-------|
| Surveyed systems list | ❌ MISSING | "Which direction should I expand?" | `surveyed={}` in country block |
| System contents (deposits) | ❌ MISSING | "Which system has best resources?" | `deposits={}` per planet |
| Hyperlane connections | ❌ MISSING | "What's my chokepoint?" | `hyperlane={}` in galactic_object |
| Strategic resource locations | ❌ MISSING | "Where's the nearest zro?" | Scan deposits for sr_* types |
| Unexplored systems | ❌ MISSING | "How much is left to survey?" | Compare surveyed vs total |
| Distance calculations | 🔴 HARD | "How far is X from Y?" | Need hyperlane pathfinding |
| Border friction analysis | ❌ MISSING | "Who am I closest to?" | Calculate from owned systems |

**Effort:** Medium - requires parsing `galactic_object` section (~2-5MB)

---

## Category 2: MILITARY & COMBAT

| Data Point | Status | Player Need | Notes |
|------------|--------|-------------|-------|
| Fleet power | ✅ HAVE | Basic fleet strength | `get_fleets()` |
| Fleet composition by class | ✅ HAVE | Ship type breakdown | `get_fleet_composition()` |
| Ship loadouts (weapons/armor) | ❌ MISSING | "Am I built for shields or armor?" | `ship_design={}` section |
| Fleet positioning/location | ❌ MISSING | "Where are my fleets?" | Fleet's `movement` block |
| Enemy fleet composition | ⚠️ PARTIAL | "What's their fleet weakness?" | Have power, not loadouts |
| War exhaustion | ✅ HAVE | War progress | `get_wars()` |
| War goals | ✅ HAVE | What we're fighting for | In war data |
| Army composition | ❌ MISSING | "Can I invade?" | `armies={}` section |
| Starbase defense power | ⚠️ PARTIAL | "Can I break through?" | Have modules, not calculated power |
| Naval capacity used/max | ❌ MISSING | "How much can I build?" | In country block |
| Space creatures/hostiles | ❌ MISSING | "What's blocking expansion?" | `country_type` for hostiles |

**High Value Gaps:**
- **Ship designs/loadouts** - Critical for combat advice
- **Army composition** - Required for invasion planning
- **Naval capacity** - Basic fleet management

---

## Category 3: ECONOMY & RESOURCES

| Data Point | Status | Player Need | Notes |
|------------|--------|-------------|-------|
| Resource stockpiles | ✅ HAVE | Current amounts | `get_resources()` |
| Income/expense breakdown | ✅ HAVE | Budget analysis | `get_budget_breakdown()` |
| Trade value/routes | ✅ HAVE | Trade optimization | `get_trade_value()` |
| Market prices | ✅ HAVE | Buy/sell decisions | `get_market()` |
| Strategic resources | ✅ HAVE | Exotic materials | In resources |
| Pop job distribution | ✅ HAVE | Employment breakdown | `get_pop_statistics()` |
| Building costs | 🔴 HARD | "Can I afford X?" | Needs game data files |
| Upkeep breakdown | ⚠️ PARTIAL | "Why is maintenance high?" | Have total, not itemized |
| Deficit projections | 🔴 HARD | "When will I run out?" | Requires prediction logic |
| Sector automation settings | ❌ MISSING | "What are sectors building?" | `sector={}` block |
| Branch office income | ❌ MISSING | Megacorp tracking | `branch_office={}` |
| Trade route paths | ❌ MISSING | Piracy analysis | `trade_routes` section |

**High Value Gaps:**
- **Branch offices** - Essential for Megacorp playstyle
- **Sector automation** - Wide empire management

---

## Category 4: DIPLOMACY & POLITICS

| Data Point | Status | Player Need | Notes |
|------------|--------|-------------|-------|
| Relations/opinion | ✅ HAVE | Who likes/hates us | `get_diplomacy()` |
| Treaties active | ✅ HAVE | Pact status | In relations |
| Federation details | ✅ HAVE | Fed management | `get_federation_details()` |
| Galactic Community | ✅ HAVE | Voting/resolutions | `get_galactic_community()` |
| Subjects/vassals | ✅ HAVE | Overlord mechanics | `get_subjects()` |
| Espionage ops | ✅ HAVE | Spy networks | `get_espionage()` |
| Diplomatic weight | ❌ MISSING | "Can I pass this resolution?" | `diplomatic_weight` field |
| Favors owed/held | ❌ MISSING | Vote manipulation | In relations manager |
| Truce timers | ⚠️ PARTIAL | "When can I attack again?" | Have flag, not duration |
| Claims | ❌ MISSING | War planning | `claims={}` section |
| Guarantees/rivalries | ⚠️ PARTIAL | Threat assessment | Have rivals, not guarantees |
| AI personality | ❌ MISSING | "Will they backstab me?" | `personality` field |
| Threat assessment | 🔴 HARD | "Who's dangerous?" | Requires analysis logic |

**High Value Gaps:**
- **Claims** - Critical for war planning
- **Diplomatic weight** - Galactic politics
- **AI personality** - Predicting behavior

---

## Category 5: PLANETS & TERRITORY

| Data Point | Status | Player Need | Notes |
|------------|--------|-------------|-------|
| Planet list with details | ✅ HAVE | Colony management | `get_planets()` |
| Planet districts | ⚠️ PARTIAL | Building slots | Have count, not types |
| Planet modifiers | ❌ MISSING | "Why is output low?" | `planet_modifier={}` |
| Tile blockers | ❌ MISSING | Early game clearing | `deposit={}` blockers |
| Habitability by species | ❌ MISSING | "Who should live here?" | Species preferences vs climate |
| Archaeology sites | ✅ HAVE | Dig management | `get_archaeology()` |
| Megastructures owned | ❌ MISSING | "What have I built?" | `megastructures={}` |
| Megastructure progress | ❌ MISSING | Construction tracking | In megastructures |
| Ruined megastructures | ❌ MISSING | Repair opportunities | `type` contains "ruined" |
| Habitat details | ❌ MISSING | Tall play optimization | Habitats are planets but special |
| Ecumenopolis status | ❌ MISSING | City planet tracking | Planet type check |
| Primitive civilizations | ❌ MISSING | Observation choices | `pre_ftl={}` countries |

**High Value Gaps:**
- **Megastructures** - Major mid/late game feature
- **Planet modifiers** - Understanding output issues
- **District types** - Proper planet optimization

---

## Category 6: TECHNOLOGY & RESEARCH

| Data Point | Status | Player Need | Notes |
|------------|--------|-------------|-------|
| Completed techs | ✅ HAVE | What we've researched | `get_technology()` |
| Current research | ✅ HAVE | Active projects | In tech data |
| Research speed | ✅ HAVE | Monthly output | In tech data |
| Available tech options | ✅ HAVE | Current choices | `available_techs` |
| Tech prerequisites | 🔴 HARD | "What unlocks X?" | Needs game data files |
| Repeatables level | ❌ MISSING | "How many +5% damage?" | Filter completed for `repeatable` |
| Rare tech flags | ❌ MISSING | "Do I have jump drives?" | Check for specific techs |
| Research alternatives | ❌ MISSING | Rolled but not picked | In tech_status |
| Special projects | ❌ MISSING | Event chains | `special_project={}` |
| Scientist bonuses | ⚠️ PARTIAL | Research efficiency | Have traits, not calculated bonus |

**High Value Gaps:**
- **Repeatables** - Critical for crisis prep
- **Special projects** - Event chain management
- **Rare techs** - Strategic capabilities check

---

## Category 7: LEADERS & GOVERNANCE

| Data Point | Status | Player Need | Notes |
|------------|--------|-------------|-------|
| Leader list | ✅ HAVE | All leaders | `get_leaders()` |
| Leader traits | ✅ HAVE | Bonuses | In leader data |
| Leader level/XP | ✅ HAVE | Experience | In leader data |
| Factions | ✅ HAVE | Political support | `get_factions()` |
| Traditions/perks | ✅ HAVE | Ascension progress | `get_traditions()`, `get_ascension_perks()` |
| Relics | ✅ HAVE | Relic management | `get_relics()` |
| Leader assignment | ❌ MISSING | "Who's governing what?" | `leader` field in planets/fleets |
| Council positions | ❌ MISSING | Paragon DLC | `council_position` |
| Agenda progress | ❌ MISSING | Leader agendas | In leader block |
| Experience to level | ❌ MISSING | "When does X level up?" | XP thresholds |
| Leader cap | ❌ MISSING | "Can I recruit more?" | In country block |

**High Value Gaps:**
- **Leader assignments** - Who's where
- **Leader cap** - Recruitment planning

---

## Category 8: CRISIS & ENDGAME

| Data Point | Status | Player Need | Notes |
|------------|--------|-------------|-------|
| Fallen Empires | ✅ HAVE | FE status/power | `get_fallen_empires()` |
| War in Heaven | ✅ HAVE | AE conflict status | In FE data |
| Crisis spawned | ⚠️ PARTIAL | "Is crisis active?" | Basic detection |
| Crisis type | ⚠️ PARTIAL | Which crisis | Pattern matching |
| Crisis progress/stage | ❌ MISSING | "How bad is it?" | Crisis-specific variables |
| Crisis fleet positions | ❌ MISSING | Threat locations | Crisis country fleets |
| Menace level | ❌ MISSING | Become the Crisis | `menace` in country |
| Custodian/Emperor | ❌ MISSING | Galactic politics | `galactic_emperor` |
| Victory score | ❌ MISSING | "Am I winning?" | Score calculations |
| End-game year setting | ❌ MISSING | "When does crisis spawn?" | Galaxy settings |
| L-Gate insights | ❌ MISSING | L-Cluster opening | `lgates` section |
| Colossus status | ❌ MISSING | Planet killer | Ship type = colossus |
| Titan/Juggernaut count | ❌ MISSING | Capital ships | Ship types |

**High Value Gaps:**
- **Crisis details** - Critical endgame info
- **Menace level** - Become the Crisis tracking
- **Victory score** - Win condition tracking
- **L-Gate insights** - Pre-opening planning

---

## Category 9: SPECIES & POPS

| Data Point | Status | Player Need | Notes |
|------------|--------|-------------|-------|
| Species list | ✅ HAVE | Basic species info | Via pop statistics |
| Species traits | ❌ MISSING | "What are my pops good at?" | `species={}` section |
| Species rights | ❌ MISSING | Slavery/citizenship | In species rights |
| Pop happiness | ⚠️ PARTIAL | Have average, not per-pop | Detailed in pops |
| Unemployed pops | ✅ HAVE | Job problems | `get_pop_statistics()` |
| Growth/assembly rates | ❌ MISSING | Pop planning | `pop_growth` field |
| Gene mod templates | ❌ MISSING | Bio ascension | In species |
| Robot/synth ratio | ❌ MISSING | Machine management | Species class filter |
| Bio-trophy count | ❌ MISSING | Rogue Servitor | Pop type filter |
| Assimilation queue | ❌ MISSING | Driven Assimilator | Pop flags |

**High Value Gaps:**
- **Species traits** - Critical for optimization
- **Species rights** - Policy management
- **Pop growth rates** - Expansion planning

---

## Category 10: SPECIAL MECHANICS

| Data Point | Status | Player Need | Notes |
|------------|--------|-------------|-------|
| Caravaneers | ❌ MISSING | Trade options | `caravaneer` country type |
| Marauders | ❌ MISSING | Raid threats | `marauder` country type |
| Great Khan status | ❌ MISSING | Marauder crisis | Event flags |
| Shroud covenant | ❌ MISSING | Psionic path | Event flags |
| Worm-in-Waiting | ❌ MISSING | Horizon Signal | Event chain |
| Precursor progress | ❌ MISSING | Archaeology chain | Special projects |
| First League/Cybrex etc | ❌ MISSING | Precursor identity | Flags |
| Enclave relations | ❌ MISSING | Curator/Artisan | Enclave opinion |
| Galactic storm effects | ❌ MISSING | Active effects | Global modifiers |

---

## Priority Recommendations

### Tier 1: High Impact, Low Effort
These would immediately improve answer quality for common questions:

| Gap | Effort | Impact | Reason |
|-----|--------|--------|--------|
| **Megastructures** | Low | High | Major feature, simple parsing |
| **Naval capacity** | Low | High | Basic fleet management |
| **Claims** | Low | High | War planning essential |
| **District types** | Low | Medium | Planet optimization |
| **Species traits** | Low | High | Pop optimization |
| **Repeatables count** | Low | Medium | Crisis prep |
| **Leader assignments** | Low | Medium | "Who's where?" |

### Tier 2: High Impact, Medium Effort
Worth investing in for complete coverage:

| Gap | Effort | Impact | Reason |
|-----|--------|--------|--------|
| **Ship designs/loadouts** | Medium | High | Combat advice |
| **Army composition** | Medium | High | Invasion planning |
| **System/hyperlane map** | Medium | High | Expansion advice |
| **Crisis details** | Medium | High | Endgame critical |
| **Diplomatic weight** | Medium | Medium | Galactic politics |
| **Branch offices** | Medium | High | Megacorp playstyle |
| **Planet modifiers** | Medium | Medium | Output diagnosis |

### Tier 3: Nice to Have
Complete coverage but not critical:

| Gap | Effort | Impact | Reason |
|-----|--------|--------|--------|
| Surveyed systems | Medium | Medium | Early game only |
| Special projects | Medium | Low | Event tracking |
| Sector settings | Low | Low | Automation oversight |
| Enclave relations | Low | Low | Niche interactions |
| Caravaneers/Marauders | Low | Low | Random events |

### Tier 4: Hard/Not Worth It
Requires external game data or complex logic:

| Gap | Why Hard |
|-----|----------|
| Building costs | Need game definition files |
| Tech prerequisites | Need tech tree data |
| Distance calculations | Need pathfinding algorithm |
| Deficit projections | Need simulation logic |
| Threat assessment | Need AI behavior model |

---

## Recommended Implementation Order

### Phase 1: Quick Wins (1-2 days)
1. `get_megastructures()` - Player-owned megastructures with type/stage
2. `get_naval_capacity()` - Used/max from country block
3. `get_claims()` - Our claims on other empires
4. `get_species_full()` - Species with traits and rights
5. Add `repeatables` count to `get_technology()`

### Phase 2: Combat Enhancement (2-3 days)
1. `get_ship_designs()` - Ship templates with loadouts
2. `get_armies()` - Army composition and strength
3. `get_fleet_locations()` - Where fleets are positioned
4. Enhance starbase data with calculated defense power

### Phase 3: Map & Expansion (3-4 days)
1. `get_galaxy_map()` - Systems with hyperlane connections
2. `get_surveyed_systems()` - Exploration progress
3. `get_strategic_resources()` - Resource deposit locations
4. `get_chokepoints()` - Identify defensive positions

### Phase 4: Endgame & Crisis (2-3 days)
1. Enhance crisis detection with stage/progress
2. `get_menace()` - Become the Crisis tracking
3. `get_victory_status()` - Score and conditions
4. `get_galactic_emperor()` - Imperium status
5. `get_lgate_status()` - Insight count and cluster state

---

## Appendix: Questions We Can Already Answer Well

Based on current extraction, we handle these question types excellently:

- "What's my military/economy/tech power?"
- "Who are my allies and rivals?"
- "What are my current wars and war exhaustion?"
- "What's my resource income/deficit?"
- "Who are my leaders and what are their traits?"
- "What traditions have I picked?"
- "What's my federation status?"
- "Are there Fallen Empires and are they awakened?"
- "What's my current research?"
- "How are my factions doing?"
- "What are my planets producing?"
- "What's the galactic market like?"

These cover roughly 60% of common strategic questions.

---

## Appendix: Sample Unanswerable Questions

Questions we currently cannot answer that players commonly ask:

1. "Should I attack now or wait?" (need enemy loadouts, not just power)
2. "Which system should I expand to next?" (need map/deposits)
3. "Can I beat this crisis?" (need detailed crisis data)
4. "What megastructure should I build?" (don't know what they have)
5. "Why is my planet underperforming?" (need modifiers)
6. "How many repeatables do I have?" (not extracted)
7. "Where should I put my chokepoint?" (need hyperlane map)
8. "Can I vassalize this empire?" (need diplomatic weight)
9. "What's blocking my expansion?" (need hostile entities)
10. "Should I gene-mod my pops?" (need species traits)
