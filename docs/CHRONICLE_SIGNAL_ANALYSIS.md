# Chronicle Signal Analysis: Stress Testing for Roleplay Value

**Date**: 2026-01-27
**Purpose**: Evaluate each potential signal for genuine narrative impact, applying the "Stellaris Invicta test" - would this make for a compelling moment in a dramatic chronicle?

## Guiding Principle

From STORYTELLING_OPTIONS.md:
> "The LLM naturally creates 4-7 eras because good storytelling requires meaningful chapters, not micro-chapters."

**The goal is not more data, but better story fuel.**

---

## Evaluation Criteria

| Score | Meaning | Example |
|-------|---------|---------|
| **5** | Chapter-defining moment | "We chose Synthetic Ascension" |
| **4** | Significant era marker | "The Great Khan rose from the steppes" |
| **3** | Good flavor, occasional use | "We acquired the Rubricator" |
| **2** | Minor detail, rarely narrative | "Completed Harmony tradition" |
| **1** | Tactical/advisor data, not chronicle | "Fleet composition changed" |

---

## TIER 1: MUST ADD (Score 5 - Chapter Defining)

### 1. Ascension Perks ✅
**Extractor**: `player.py:439 get_ascension_perks()`
**Frequency**: 8-10 per game
**Narrative Value**: **5/5**

| Perk | Chronicle Moment |
|------|-----------------|
| Synthetic Evolution | "The flesh was weak. We became something greater." |
| Psionic Ascension | "The Shroud opened to us, and we touched the infinite." |
| Biological Mastery | "We reshaped our very flesh to match our will." |
| Become the Crisis | "We chose to become the galaxy's doom." |
| Defender of the Galaxy | "We swore an oath to stand against the darkness." |
| Galactic Wonders | "We built monuments to rival the ancients." |
| Arcology Project | "Our worlds became city-planets, gleaming in the void." |

**Why essential**: Each perk represents a fundamental philosophical choice that defines the empire's identity arc. These are the "We chose our destiny" moments.

**Implementation**: Track list, detect new additions, create `ascension_perk_selected` event.

---

### 2. Become the Crisis Path ✅
**Extractor**: `endgame.py:432 get_menace()`
**Frequency**: 0-1 per game (player choice)
**Narrative Value**: **5/5**

| Stage | Chronicle Moment |
|-------|-----------------|
| Perk taken | "We chose the path of destruction" |
| Level 1 | "The galaxy began to fear our name" |
| Level 2 | "Our ships darkened the stars" |
| Level 3 | "We became an existential threat" |
| Level 4 | "The galaxy united against us" |
| Level 5 | "The Aetherophasic Engine awakened" |

**Why essential**: If a player chooses this path, it IS the story of their late game. Ignoring it would be like writing WWII history without mentioning the war.

**Implementation**: Track `crisis_level` changes, create `crisis_level_increased` event.

---

### 3. L-Gate Opening ✅
**Extractor**: `endgame.py:279 get_lgate_status()`
**Frequency**: 0-1 per game
**Narrative Value**: **5/5**

| Outcome | Chronicle Moment |
|---------|-----------------|
| Gray Tempest | "The L-Gate opened. The Tempest poured through." |
| Dessanu Consonance | "Beyond the gate, we found peaceful ancients." |
| L-Drakes | "Dragons. The L-Cluster held dragons." |
| Gray | "A single being. Alone. For millennia." |

**Why essential**: Single dramatic moment that changes the game. The mystery, the buildup, the reveal - pure narrative gold.

**Implementation**: Track `lgate_opened` boolean change, create `lgate_opened` event with outcome.

---

### 4. First Contact (needs detection)
**Extractor**: Needs to be built from diplomacy/country data
**Frequency**: 1-5 in early game
**Narrative Value**: **5/5**

**Chronicle Moment**: "On 2210.03.15, we learned we were not alone. The Blorg Commonality emerged from the void, their transmission a beacon of friendship... or warning."

**Why essential**: The foundational "we are not alone" moment. Every space opera has this scene. Currently completely missing from chronicles.

**Implementation**: Track known empires list, detect first additions, create `first_contact` event.

---

## TIER 2: SHOULD ADD (Score 4 - Significant Markers)

### 5. Great Khan ✅
**Extractor**: `endgame.py:540 get_great_khan()`
**Frequency**: 0-1 per game
**Narrative Value**: **4/5**

| Event | Chronicle Moment |
|-------|-----------------|
| Khan rises | "From the Marauder clans, a conqueror arose" |
| Khan dies | "The Khan fell, and his empire shattered" |
| Khanate forms | "His successors forged a new nation from chaos" |

**Why add**: Rare but dramatic galaxy-wide event. When it happens, it's a chapter.

**Implementation**: Track Khan status changes, create `great_khan_spawned`, `great_khan_died` events.

---

### 6. Ruler Changes (needs detection)
**Extractor**: Can derive from `leaders.py get_leaders()` ruler tracking
**Frequency**: 3-8 per long game
**Narrative Value**: **4/5**

| Event | Chronicle Moment |
|-------|-----------------|
| Election | "The people chose their third President" |
| Death | "Emperor Vex fell. His daughter took the throne." |
| Coup | "The admirals seized power in the night" |

**Why add**: Creates generational saga narrative. "Under Emperor Vex, we conquered. Under Empress Lyra, we consolidated."

**Implementation**: Track ruler leader ID, detect changes, create `ruler_changed` event with succession type.

---

### 7. Precursor Homeworld Discovery ✅
**Extractor**: `projects.py:39 get_special_projects()` - `precursor_progress`
**Frequency**: 0-1 per precursor chain (6 chains)
**Narrative Value**: **4/5**

| Precursor | Chronicle Moment |
|-----------|-----------------|
| Cybrex | "We found Cybrex Alpha. The machines had been here before us." |
| First League | "Fen Habbanis stood preserved. A monument to what was lost." |
| Irassian | "The Irassian Concordat fell to plague. Their homeworld was a tomb." |
| Vultaum | "The Vultaum believed reality was simulation. They proved it." |
| Yuht | "The Yuht Empire spanned millions of years. Now, only ruins." |
| Zroni | "The Zroni touched the Shroud. It destroyed them." |

**Why add**: Finding a precursor homeworld is a major archaeological/story moment. The artifacts you gain are game-changing.

**Implementation**: Track precursor completion flags, create `precursor_discovered` event.

---

### 8. Galactic Community Joined ✅
**Extractor**: `diplomacy.py:474 get_galactic_community()`
**Frequency**: 0-1 per game
**Narrative Value**: **4/5**

**Chronicle Moment**: "We took our seat among the stars. The Galactic Community welcomed us—or at least tolerated our presence."

**Why add**: Marks transition from isolated power to galactic player. Single event.

**Implementation**: Track membership boolean, create `galactic_community_joined` event.

---

### 9. Tradition Trees COMPLETED ✅
**Extractor**: `player.py:385 get_traditions()` - `by_tree[].finished`
**Frequency**: 5-7 per game (tree completions, not individual traditions)
**Narrative Value**: **4/5**

| Tree | Chronicle Moment |
|------|-----------------|
| Expansion | "Our expansion doctrine was complete. The stars beckoned." |
| Domination | "We perfected the art of rule. Vassals knelt." |
| Supremacy | "Our military doctrine was refined to perfection." |
| Prosperity | "Our economy became the envy of the galaxy." |
| Diplomacy | "We mastered the art of galactic politics." |
| Harmony | "Internal unity became our greatest strength." |
| Discovery | "Our scientists pushed the boundaries of knowledge." |

**Why add**: Tree completion (not individual traditions) represents cultural evolution. 5-7 events per game is manageable.

**Implementation**: Track `by_tree[].finished` changes, create `tradition_tree_completed` event.

---

## TIER 3: CONSIDER CAREFULLY (Score 3 - Occasional Flavor)

### 10. Major Guardian Defeats
**Extractor**: `leviathans.py:89 get_leviathans()`
**Frequency**: 0-5 per game
**Narrative Value**: **3/5**

| Guardian | Chronicle Potential |
|----------|---------------------|
| Ether Drake | "We slew the dragon and claimed its hoard" |
| Dimensional Horror | "The portal to madness was sealed" |
| Automated Dreadnought | "We captured an ancient war machine" |
| Enigmatic Fortress | "The fortress yielded its secrets" |
| Stellarite Devourer | "The star-eater fell to our fleets" |

**Concern**: Many minor leviathans (Tiyanki, Crystals, etc.) would add noise.

**Recommendation**: Only track MAJOR guardians (Drake, Horror, Dreadnought, Fortress, Stellarite, Voidspawn, Shard). Skip common space fauna.

---

### 11. Major Relics Acquired
**Extractor**: `player.py:534 get_relics()`
**Frequency**: 3-10 per game
**Narrative Value**: **3/5**

| Relic | Chronicle Potential |
|-------|---------------------|
| The Galatron | "The Galatron chose us. The galaxy would never forget." |
| Prethoryn Brood-Queen | "We captured a queen. Her children served us now." |
| The Defragmentor | "Cybrex technology, reborn in our hands." |
| Rubricator | "We held the key to all knowledge." |

**Concern**: Many relics are minor (+5% research, etc.).

**Recommendation**: Only track "legendary" relics: Galatron, Brood-Queen, Defragmentor, Extradimensional Warlock, Khan's Throne. Skip common relics.

---

### 12. Subject Empire Acquired/Released
**Extractor**: `diplomacy.py:627 get_subjects()`
**Frequency**: 0-10 per game
**Narrative Value**: **3/5**

| Event | Chronicle Potential |
|-------|---------------------|
| Vassal gained | "The Blorg knelt. They chose subjugation over extinction." |
| Subject released | "We granted the Blorg their freedom. They had earned it." |
| Integration | "The Blorg ceased to exist. They became us." |

**Concern**: Can be frequent in domination-focused games.

**Recommendation**: Add, but cap at 3-5 subject events per chapter to prevent noise.

---

## TIER 4: DO NOT ADD (Score 1-2 - Noise)

### ❌ Individual Traditions
**Reason**: 20+ per game, individually minor. Tree completion is sufficient.

### ❌ Archaeological Sites
**Reason**: Too many individual discoveries. Precursor homeworlds capture the important ones.

### ❌ Fleet Composition
**Reason**: Tactical data, not narrative. "We switched to battleships" isn't chronicle material.

### ❌ Individual Factions
**Reason**: Internal politics are noise in an epic chronicle. Maybe if civil war triggers.

### ❌ Claims
**Reason**: Pre-war positioning, too tactical.

### ❌ Espionage Operations
**Reason**: Many small operations, hard to narrativize compellingly.

### ❌ Market Trades
**Reason**: Economic minutiae.

### ❌ Common Space Fauna (Tiyanki, Crystals, Amoebas)
**Reason**: Common encounters, not epic battles.

### ❌ Individual Policy Changes
**Reason**: Already tracked, but most are minor administrative changes.

---

## Summary: Recommended Signal Additions

### Must Add (Original Design + Critical Gaps)
| Signal | Events | Frequency/Game |
|--------|--------|----------------|
| Ascension Perks | `ascension_perk_selected` | 8-10 |
| Become Crisis | `crisis_level_increased` | 0-5 |
| L-Gate | `lgate_opened` | 0-1 |
| First Contact | `first_contact` | 1-5 |

### Should Add (Significant Markers)
| Signal | Events | Frequency/Game |
|--------|--------|----------------|
| Great Khan | `great_khan_spawned`, `great_khan_died` | 0-2 |
| Ruler Changes | `ruler_changed` | 3-8 |
| Precursor Discovery | `precursor_discovered` | 0-6 |
| Galactic Community | `galactic_community_joined` | 0-1 |
| Tradition Trees | `tradition_tree_completed` | 5-7 |

### Consider (With Filtering)
| Signal | Events | Filtering |
|--------|--------|-----------|
| Major Guardians | `guardian_defeated` | Only 6 major guardians |
| Legendary Relics | `relic_acquired` | Only ~5 legendary relics |
| Subjects | `subject_acquired` | Cap at 3-5 per chapter |

---

## Total Event Budget

**Current events per long game**: ~600-1000
**Proposed additions**: ~30-60 events
**Increase**: ~5%

This is well within the LLM's ability to filter and doesn't risk "event noise" overwhelming the narrative.

---

## Implementation Priority

### Phase 1: Originally Designed (3-5 days)
1. `ascension_perk_selected` - Extractor exists
2. `first_contact` - Needs detection logic
3. `ruler_changed` - Needs detection logic

### Phase 2: Galaxy Events (2-3 days)
4. `lgate_opened` - Extractor exists
5. `great_khan_spawned/died` - Extractor exists
6. `galactic_community_joined` - Extractor exists
7. `tradition_tree_completed` - Extractor exists

### Phase 3: Crisis Path (1-2 days)
8. `crisis_level_increased` - Extractor exists (menace)

### Phase 4: Optional Flavor (2-3 days)
9. `precursor_discovered` - Extractor exists
10. `guardian_defeated` - Needs filtering logic
11. `legendary_relic_acquired` - Needs filtering logic

---

## What NOT to Do

> "The LLM naturally creates 4-7 eras because good storytelling requires meaningful chapters, not micro-chapters."

- Don't add signals just because extractors exist
- Don't track every game mechanic
- Don't add frequent low-impact events
- Don't duplicate what's already captured (tech, wars, diplomacy)

The chronicle should read like an epic, not a changelog.
