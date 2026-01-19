# Stellaris Save File Data Model: Wars Extraction

This document describes the save file structure for war data extraction, covering active wars, participants, war exhaustion, war goals, and related data.

## Table of Contents

1. [Data Sources Overview](#data-sources-overview)
2. [War Section Structure](#war-section-structure)
3. [War Entry Fields](#war-entry-fields)
4. [Participant Blocks](#participant-blocks)
5. [War Exhaustion](#war-exhaustion)
6. [War Goals](#war-goals)
7. [Data Relationships](#data-relationships)
8. [Expected Invariants](#expected-invariants)
9. [Validation Strategy](#validation-strategy)
10. [Edge Cases and Limitations](#edge-cases-and-limitations)

---

## Data Sources Overview

| Data Type | Save File Location | Extraction Method |
|-----------|-------------------|-------------------|
| Active Wars | `war[id]` (top-level section) | `get_wars()` |
| War Participants | `war[id].attackers[]` and `war[id].defenders[]` | Nested in war entry |
| War Exhaustion | `war[id].attacker_war_exhaustion` and `war[id].defender_war_exhaustion` | Direct fields |
| War Goals | `war[id].war_goal` | Nested block |
| Country Names | `country[id].name` | `_get_country_names_map()` cross-reference |
| Truces (post-war) | `country[id].relations_manager.relation[].truce` | `get_diplomacy()` |
| Casus Belli (available) | `country[id].standard_diplomacy_module.casus_belli[]` | Not currently extracted |

---

## War Section Structure

### Location

Wars are stored in a top-level `war=` section in the gamestate file:

```
war=
{
    0=
    {
        name={
            key="NAME_Conquest_War"
            literal="no"
        }
        start_date="2350.05.15"
        attacker_war_exhaustion=25.5
        defender_war_exhaustion=42.3
        attackers={
            {
                country=0
                call_type="attacker"
                caller=yes
            }
            {
                country=3
                call_type="ally"
                caller=no
            }
        }
        defenders={
            {
                country=1
                call_type="defender"
                caller=yes
            }
        }
        war_goal={
            type="wg_conquest"
            casus_belli="cb_claim"
        }
    }
    1=none    # Ended war (slot freed)
    2=
    {
        # Another active war...
    }
}
```

### Entry States

War entries can be in two states:

| State | Format | Meaning |
|-------|--------|---------|
| Active | `id={ ... }` | War is ongoing with full data block |
| Ended | `id=none` | War has concluded, slot is empty |

---

## War Entry Fields

### Core Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | block or string | Yes | War name (see Name Formats below) |
| `start_date` | string | Yes | Date war began (format: `"YYYY.MM.DD"`) |
| `attacker_war_exhaustion` | float | Yes | Attacker side's war exhaustion (0.0-100.0) |
| `defender_war_exhaustion` | float | Yes | Defender side's war exhaustion (0.0-100.0) |
| `attackers` | block | Yes | List of attacking empire participants |
| `defenders` | block | Yes | List of defending empire participants |
| `war_goal` | block | Yes | Primary war goal definition |

### Name Formats

War names can appear in two formats:

**Simple String Format:**
```
name="The Great War"
```

**Localization Block Format:**
```
name={
    key="NAME_Conquest_War"
    literal="no"
    variable={
        key="[Attacker.GetName]"
        value={
            scope={
                id=0
                type=country
            }
        }
    }
}
```

The extraction code handles both formats:
1. First attempts to match `name="string"`
2. Falls back to extracting `key="..."` from the name block
3. Uses `War #ID` as final fallback

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `end_date` | string | Only present for ended wars (before becoming `none`) |
| `war_score` | float | Calculated war score (deprecated in newer versions) |
| `battles` | block | List of battle records |

---

## Participant Blocks

### Structure

Each participant in the `attackers` or `defenders` block follows this structure:

```
{
    country=0
    call_type="attacker"
    caller=yes
    war_goal={
        type="wg_conquest"
        casus_belli="cb_claim"
    }
}
```

### Participant Fields

| Field | Type | Description |
|-------|------|-------------|
| `country` | int | Country ID (references `country` section) |
| `call_type` | string | How they joined: `"attacker"`, `"defender"`, `"ally"`, `"subject"`, `"overlord"` |
| `caller` | yes/no | Whether this empire started/was targeted in the war |
| `war_goal` | block | Optional - individual war goal for this participant |

### Participant Call Types

| Type | Description |
|------|-------------|
| `attacker` | Primary war initiator |
| `defender` | Primary war target |
| `ally` | Joined via defensive pact or federation |
| `subject` | Vassal/tributary called to war by overlord |
| `overlord` | Overlord drawn into subject's war |
| `independence` | Fighting for independence (subject declaring) |

---

## War Exhaustion

### Storage Model

War exhaustion is stored **per side**, not per participant:

```
attacker_war_exhaustion=25.5
defender_war_exhaustion=42.3
```

This means all empires on the attacker side share the same exhaustion value, and all empires on the defender side share their own value.

### Value Range

| Value | Meaning |
|-------|---------|
| 0.0 | No exhaustion (war just started) |
| 100.0 | Maximum exhaustion (forced status quo available) |

### What Increases Exhaustion

- Ship losses (proportional to naval capacity)
- Army losses (recruited armies only, not defensive armies)
- Occupied planets
- War duration
- Various modifiers (traditions, ethics, civics)

### Extraction Notes

The extraction code determines player's exhaustion based on which side they're on:

```python
our_side = "attacker" if player_is_attacker else "defender"
our_exhaustion = attacker_exhaustion if player_is_attacker else defender_exhaustion
their_exhaustion = defender_exhaustion if player_is_attacker else attacker_exhaustion
```

---

## War Goals

### Structure

```
war_goal={
    type="wg_conquest"
    casus_belli="cb_claim"
    target={
        id=1
        type=country
    }
}
```

### Common War Goal Types

| Type | Description |
|------|-------------|
| `wg_conquest` | Claim conquest - take claimed systems |
| `wg_subjugation` | Make target a vassal |
| `wg_humiliation` | Humiliate enemy (influence gain) |
| `wg_independence` | Subject seeking independence |
| `wg_colossus` | Total war with colossus |
| `wg_end_threat` | Contain threat/empire |
| `wg_take_capital` | Decapitation war |

### Common Casus Belli Types

| Type | Description |
|------|-------------|
| `cb_claim` | Claims on their territory |
| `cb_subjugation` | Subjugation CB |
| `cb_humiliation` | Humiliation/rivalry |
| `cb_ideology` | Ideological differences |
| `cb_proxy_war` | Proxy war (federation ally) |
| `cb_containment` | Threat containment |
| `cb_colossus` | Colossus total war |

---

## Data Relationships

### War Participants to Countries

```
war[id].attackers[].country  -->  country[country_id]
war[id].defenders[].country  -->  country[country_id]
```

The `country` field in participant blocks is an integer ID that references the `country` section:

```python
# Build country ID -> name mapping
country_names = self._get_country_names_map()

# Resolve participant IDs to names
attacker_names = [country_names.get(int(cid), f"Empire {cid}") for cid in attacker_ids]
```

### Post-War Truces

After a war ends, truces are established between belligerents:

```
country[0].relations_manager.relation={
    owner=0
    country=1
    truce=12345678    # Truce record ID
    ...
}
```

The `truce` field references a top-level `truce` section (not currently extracted by `get_wars()`).

### Related Sections

| Section | Relationship |
|---------|-------------|
| `country` | Participant details, names |
| `truce` | Post-war peace periods |
| `agreements` | Subject/overlord relationships drawn into war |
| `federation` | Federation members called to defend |

---

## Expected Invariants

### Must Always Be True

1. **Participant IDs exist**: Every `country` ID in `attackers` and `defenders` blocks MUST reference a valid entry in the `country` section
2. **Non-empty sides**: Active wars MUST have at least one attacker AND one defender
3. **Exhaustion bounds**: `attacker_war_exhaustion` and `defender_war_exhaustion` are in range [0.0, 100.0]
4. **Date format**: `start_date` follows `"YYYY.MM.DD"` format
5. **Unique participation**: A country cannot appear in both `attackers` AND `defenders` for the same war
6. **One primary per side**: Each side has exactly one participant with `caller=yes`

### Should Be True (Soft Constraints)

1. **War name present**: Wars should have a name (extraction has fallback)
2. **War goal defined**: Primary war goal should be defined
3. **Consistent exhaustion**: Exhaustion values should increase over time (never decrease except via event)

---

## Validation Strategy

### Cross-Reference Checks

| Check | Method | Action if Failed |
|-------|--------|------------------|
| Participant exists | Look up `country_names.get(int(cid))` | Use fallback name `"Empire {id}"` |
| Player involvement | Check if `player_id` in attacker_ids or defender_ids | Skip war (not relevant to player) |
| War section exists | `re.search(r'\nwar=\n\{', gamestate)` | Return empty result |

### Verification Approaches

1. **Participant Count Check**
   ```python
   if len(attacker_ids) == 0 or len(defender_ids) == 0:
       # Malformed war entry - log warning
   ```

2. **Exhaustion Sanity Check**
   ```python
   if not 0.0 <= exhaustion <= 100.0:
       # Unexpected value - clamp or warn
   ```

3. **Date Consistency**
   ```python
   duration_days = days_between(start_date, current_date)
   if duration_days < 0:
       # Start date after current date - data inconsistency
   ```

### Bug vs Missing Data

| Symptom | Likely Cause | Resolution |
|---------|--------------|------------|
| No wars in section, all `=none` | Save has no active wars | Return empty result (not a bug) |
| Missing `attackers` block | Save format variation or corruption | Skip this war entry |
| Country ID not in country section | Destroyed/removed empire | Use fallback name |
| Exhaustion > 100 | Mod or event override | Clamp to 100 |
| Missing `war_goal` | Very old save or edge case | Default to `"unknown"` |

---

## Edge Cases and Limitations

### Known Edge Cases

1. **Ended Wars as `none`**
   - Wars that have concluded are marked as `id=none`
   - Current extraction correctly skips these entries
   - Historical war data is not preserved after ending

2. **Multi-War Scenarios**
   - An empire can be in multiple wars simultaneously
   - Player can be attacker in one war, defender in another
   - Each war is processed independently

3. **AI-Only Wars**
   - Wars where player is not involved are skipped
   - `get_wars()` only returns player-relevant wars
   - For galaxy-wide war data, additional extraction needed

4. **Subject/Overlord Wars**
   - Subjects can be dragged into overlord wars
   - `call_type` distinguishes how participant joined
   - Exhaustion still shared across entire side

5. **Total War (Colossus)**
   - Special war type with different mechanics
   - No peace negotiations possible
   - `wg_colossus` war goal type

### Current Limitations

1. **No Battle Details**: Individual battle records not extracted
2. **No War Score**: War score calculation not implemented
3. **No Occupation Status**: Which systems/planets occupied not tracked
4. **No Claim Tracking**: Which claims will be enforced on victory
5. **No Historical Wars**: Only active wars, not past wars
6. **No Surrender Terms**: What each side would gain on victory

### Extraction Performance

- War section can be large in galaxy-spanning conflicts
- Current extraction uses 5MB chunk limit: `war_start:war_start + 5000000`
- Individual war blocks limited to 100KB for parsing
- Country name lookup is cached for efficiency

---

## Output Schema

The `get_wars()` method returns:

```python
{
    'wars': [
        {
            'name': str,              # War name (e.g., "Conquest of the Rim")
            'start_date': str,        # "YYYY.MM.DD" format
            'duration_days': int,     # Days since start (or None)
            'our_side': str,          # "attacker" or "defender"
            'our_exhaustion': float,  # 0.0-100.0, rounded to 1 decimal
            'their_exhaustion': float,# 0.0-100.0, rounded to 1 decimal
            'participants': {
                'attackers': [str],   # List of empire names
                'defenders': [str]    # List of empire names
            },
            'war_goal': str,          # War goal type (e.g., "wg_conquest")
            'status': str             # Always "in_progress" for active wars
        }
    ],
    'player_at_war': bool,            # True if any wars exist
    'active_war_count': int,          # Number of active wars
    'count': int                      # Same as active_war_count (backward compat)
}
```

---

## References

- Extraction implementation: `/stellaris_save_extractor/military.py`
- Country name lookup: `/stellaris_save_extractor/base.py` (`_get_country_names_map()`)
- Date utilities: `/date_utils.py` (`days_between()`)
- Related extraction: `/stellaris_save_extractor/diplomacy.py` (truces)
