# Stellaris Save File Data Model: FLEETS Extraction

This document describes the data model for fleet extraction from Stellaris save files, including data sources, relationships, invariants, and validation strategies.

## Overview

Fleet data in Stellaris saves follows a sparse reference model where ownership is stored in the country section, fleet details are stored in a separate fleet section, and ship details reference designs from yet another section.

## Data Sources

### 1. Fleet Ownership: `country.fleets_manager.owned_fleets`

**Location**: Inside each country block within the `country={}` section

```
country=
{
    0=                              # Country ID (0 = player in single-player)
    {
        ...
        fleets_manager=
        {
            owned_fleets=
            {
                {
                    fleet=0         # Fleet ID
                }
                {
                    fleet=1
                }
                {
                    fleet=129
                }
                ...
            }
        }
        ...
    }
}
```

**Key points**:
- `owned_fleets` contains fleet IDs that the country **owns**
- There is also a `fleets={}` section which contains fleets the country can **see** (has intel on)
- Always use `owned_fleets` for determining ownership, not `fleets`
- Fleet IDs are stored as simple integers within nested blocks

**Extraction code location**: `base.py::_get_owned_fleet_ids()`

### 2. Fleet Details: `fleet={}`

**Location**: Top-level section in gamestate

```
fleet=
{
    0=                              # Fleet ID
    {
        name=
        {
            key="shipclass_starbase_name"
            variables=
            {
                {
                    key="PLANET"
                    value=
                    {
                        key="NAME_Sol"
                    }
                }
            }
        }
        ships=
        {
            0 16786399 16786371 33561548 184555319 ...   # Ship IDs (space-separated)
        }
        station=yes                 # Present if starbase
        civilian=yes                # Present if civilian fleet
        military_power=36421.50000  # Combat strength
        hit_points=184138.69998
        ...
    }
    1=
    {
        name=
        {
            key="PREFIX_NAME_FORMAT"
            variables=
            {
                {
                    key="NAME"
                    value=
                    {
                        key="HUMAN1_SHIP_LeifEricson"
                    }
                }
            }
        }
        ships=
        {
            1
        }
        civilian=yes                # Science ship, constructor, etc.
        military_power=0.00000
        ...
    }
}
```

**Key fields**:
| Field | Type | Description |
|-------|------|-------------|
| `name` | block | Localization key and variables |
| `ships` | block | Space-separated list of ship IDs |
| `station` | boolean | `yes` if this is a starbase fleet |
| `civilian` | boolean | `yes` if science/construction/transport |
| `military_power` | float | Combat power rating |
| `hit_points` | float | Current HP |
| `combat` | block | Position and formation data |
| `movement_manager` | block | Navigation state |

**Fleet types determined by**:
- **Starbase**: `station=yes` present
- **Civilian**: `civilian=yes` present (science, construction, transport ships)
- **Military**: neither `station=yes` nor `civilian=yes`, and `military_power > 100`

**Extraction code location**: `military.py::get_fleets()`, `base.py::_analyze_player_fleets()`

### 3. Ship Details: `ships={}`

**Location**: Top-level section in gamestate

```
ships=
{
    3405=                           # Ship ID
    {
        fleet=1155                  # Back-reference to owning fleet
        name=
        {
            key="PREFIX_NAME_FORMAT"
            variables=
            {
                {
                    key="NAME"
                    value=
                    {
                        key="HUMAN1_SHIP_Rickenbacker"
                    }
                }
            }
        }
        ship_design_implementation=
        {
            design=268436784        # Design ID
            upgrade=4294967295      # Upgrade queue (null = none)
            growth_stage=0
        }
        graphical_culture="mammalian_01"
        section=
        {
            design="CORVETTE_MID_S3"
            slot="mid"
            weapon=
            {
                index=30
                template="SMALL_MASS_DRIVER_5"
                component_slot="SMALL_GUN_01"
            }
            ...
        }
        experience=2220
        hitpoints=250
        shield_hitpoints=250
        armor_hitpoints=130
        max_hitpoints=250
        construction_date="2218.01.20"
        ...
    }
}
```

**Key fields**:
| Field | Type | Description |
|-------|------|-------------|
| `fleet` | int | Fleet ID this ship belongs to |
| `ship_design_implementation.design` | int | Ship design ID |
| `section` | block(s) | Ship sections with equipped weapons |
| `experience` | int | Combat experience |
| `hitpoints` | float | Current hull HP |
| `shield_hitpoints` | float | Current shields |
| `armor_hitpoints` | float | Current armor |
| `construction_date` | string | When ship was built |

**Notes**:
- Ships may use `ship_design_implementation.design` (modern format) or `ship_design` (legacy format)
- The `section` blocks contain the actual equipped components
- `fleet` back-reference allows inverse lookups

**Extraction code location**: `military.py::get_fleet_composition()`

### 4. Ship Designs: `ship_design={}`

**Location**: Top-level section in gamestate

```
ship_design=
{
    268436784=                      # Design ID
    {
        name=
        {
            key="HUMAN1_SHIP_Akshay"
        }
        auto_gen_design=yes
        graphical_culture="mammalian_01"
        growth_stages=
        {
            {
                ship_size="corvette"    # Ship class/size
                parent=4294967295
                section=
                {
                    template="CORVETTE_MID_S3"
                    slot="mid"
                    component=
                    {
                        slot="SMALL_GUN_01"
                        template="SMALL_MASS_DRIVER_5"
                    }
                    ...
                }
                required_component="CORVETTE_ZERO_POINT_REACTOR"
                required_component="HYPER_DRIVE_3"
                ...
            }
        }
    }
}
```

**Key fields**:
| Field | Type | Description |
|-------|------|-------------|
| `name` | block | Design name |
| `growth_stages[].ship_size` | string | Ship class (corvette, destroyer, etc.) |
| `growth_stages[].section` | block(s) | Section templates and components |
| `auto_gen_design` | boolean | If auto-generated by game |

**Ship size values** (military):
- `corvette` - Small combat ship
- `frigate` - Light escort (with DLC)
- `destroyer` - Point defense specialist
- `cruiser` - Versatile medium ship
- `battleship` - Heavy capital ship
- `titan` - Massive flagship
- `juggernaut` - Mobile starbase
- `colossus` - Planet killer

**Ship size values** (civilian):
- `science` - Science ship
- `constructor` - Construction ship
- `colonizer` - Colony ship
- `transport` - Army transport

**Ship size values** (starbases):
- `starbase_outpost`
- `starbase_starport`
- `starbase_starhold`
- `starbase_starfortress`
- `starbase_citadel`
- `orbital_ring_tier_1/2/3`

**Extraction code location**: `military.py::get_fleet_composition()`

## Data Relationships

### Ownership Chain

```
country.fleets_manager.owned_fleets
    └── fleet=N (fleet ID)
            └── fleet[N] (in fleet={} section)
                    └── ships={...} (ship IDs)
                            └── ships[ID] (in ships={} section)
                                    └── ship_design_implementation.design
                                            └── ship_design[ID] (in ship_design={} section)
                                                    └── ship_size="corvette"
```

### Inverse References

Ships maintain back-references to their fleet:
```
ships[ID].fleet = fleet_id
```

This allows validation that a ship belongs to the fleet that lists it.

### Classification Logic

```python
def classify_fleet(fleet_block):
    if 'station=yes' in fleet_block:
        return 'starbase'
    elif 'civilian=yes' in fleet_block:
        return 'civilian'
    else:
        mp = extract_military_power(fleet_block)
        if mp > 100:  # Threshold filters space creatures
            return 'military'
        else:
            return 'civilian'  # Low-power non-civilian = special
```

## Expected Invariants

### Ownership Invariants

1. **Every fleet ID in `owned_fleets` should exist in `fleet={}` section**
   - Violation indicates save file corruption or incomplete parsing

2. **Fleet's implicit owner (via `owned_fleets`) should be consistent**
   - A fleet ID should appear in exactly one country's `owned_fleets`

3. **Ship's `fleet` back-reference should match the fleet that lists it**
   ```
   If fleet[F].ships contains S, then ships[S].fleet == F
   ```

### Ship/Design Invariants

4. **Every ship should have a valid design reference**
   - `ship_design_implementation.design` or `ship_design` should exist

5. **Design ID should exist in `ship_design={}` section**
   - Unless the value is `4294967295` (null/none marker)

### Military Power Invariants

6. **Military fleets should have `military_power > 0`**
   - Threshold of 100 used to filter space creatures

7. **Starbases with weapons should have `military_power > 0`**

8. **Civilian fleets should have `military_power = 0`**

## Validation Strategy

### Triangulation Validation

Compare counts from multiple sources:

```python
def validate_fleet_counts(extractor):
    player_id = extractor.get_player_empire_id()
    country_content = extractor._find_player_country_content(player_id)

    # Source 1: owned_fleets list
    owned_fleet_ids = extractor._get_owned_fleet_ids(country_content)

    # Source 2: analyze fleet blocks
    fleet_section = extractor._extract_section('fleet')
    military_count = 0
    civilian_count = 0
    starbase_count = 0

    for fid in owned_fleet_ids:
        fleet_block = find_fleet_block(fleet_section, fid)
        if 'station=yes' in fleet_block:
            starbase_count += 1
        elif 'civilian=yes' in fleet_block:
            civilian_count += 1
        elif get_military_power(fleet_block) > 100:
            military_count += 1

    # Verify totals match get_fleets() output
    result = extractor.get_fleets()
    assert result['military_fleet_count'] == military_count
    assert result['civilian_fleet_count'] == civilian_count
```

### Drill-Down Validation

Verify specific fleet details:

```python
def validate_fleet_ships(extractor, fleet_id):
    fleet_section = extractor._extract_section('fleet')
    ships_section = extractor._extract_section('ships')

    fleet_block = find_fleet_block(fleet_section, fleet_id)
    ship_ids = extract_ship_ids(fleet_block)

    for ship_id in ship_ids:
        ship_block = find_ship_block(ships_section, ship_id)
        # Verify back-reference
        assert ship_block['fleet'] == fleet_id
        # Verify design exists
        design_id = extract_design_id(ship_block)
        if design_id != 4294967295:  # Not null
            assert design_exists(design_id)
```

### Inverse Validation

Find all player fleets in raw save and verify capture:

```python
def validate_complete_capture(extractor):
    player_id = extractor.get_player_empire_id()

    # Get claimed ownership
    country_content = extractor._find_player_country_content(player_id)
    owned_fleet_ids = set(extractor._get_owned_fleet_ids(country_content))

    # Scan all fleets and verify none are missed
    fleet_section = extractor._extract_section('fleet')
    all_fleet_ids = extract_all_fleet_ids(fleet_section)

    # No fleet should belong to player but not be in owned_fleets
    # (There's no owner field in fleet blocks, so this validates our source)

    # Verify no duplicate ownership across countries
    for country_id in get_all_country_ids():
        if country_id == player_id:
            continue
        other_owned = get_country_owned_fleets(country_id)
        # No overlap
        assert not (owned_fleet_ids & other_owned)
```

## Edge Cases

### Null Values

The value `4294967295` (2^32 - 1) is used as a null marker:
- `ship_design_implementation.upgrade=4294967295` means no upgrade queued
- `parent=4294967295` in designs means no parent design

### Large Fleet IDs

Fleet IDs can be very large numbers (e.g., `3942649567`), not sequential. Do not assume IDs are small integers.

### Template Names

Fleet and ship names often use localization templates:
- `%SEQ%` - Sequential number placeholder
- `PREFIX_NAME_FORMAT` - Prefix + name format
- `shipclass_starbase_name` - Starbase naming pattern

Clean display names require resolving these templates.

## Implementation Notes

### Performance Considerations

1. **Section caching**: Extract sections once and cache (`_extract_section`)
2. **Lazy parsing**: Don't parse all ships/designs upfront
3. **Chunk sizes**: Fleet section can be 50MB+; use bounded searches
4. **Early termination**: Skip non-player fleets immediately

### Code Locations

| Function | File | Purpose |
|----------|------|---------|
| `get_fleets()` | `military.py` | Main fleet extraction |
| `get_fleet_composition()` | `military.py` | Ship class breakdown |
| `_get_owned_fleet_ids()` | `base.py` | Extract owned fleet IDs |
| `_analyze_player_fleets()` | `base.py` | Categorize fleets |
| `_find_fleet_section_start()` | `base.py` | Locate fleet section |
| `_find_player_country_content()` | `base.py` | Get player country block |

## Sample Extraction Flow

```python
# 1. Get player's owned fleet IDs
player_id = extractor.get_player_empire_id()  # Usually 0
country_content = extractor._find_player_country_content(player_id)
owned_fleet_ids = extractor._get_owned_fleet_ids(country_content)

# 2. Load necessary sections
fleet_section = extractor._extract_section('fleet')
ships_section = extractor._extract_section('ships')
designs_section = extractor._extract_section('ship_design')

# 3. Build design lookup
design_to_size = {}
for design_id, design_block in parse_designs(designs_section):
    ship_size = extract_ship_size(design_block)
    design_to_size[design_id] = ship_size

# 4. Build ship lookup
ship_to_design = {}
for ship_id, ship_block in parse_ships(ships_section):
    design_id = extract_design_id(ship_block)
    ship_to_design[ship_id] = design_id

# 5. Process each owned fleet
for fleet_id in owned_fleet_ids:
    fleet_block = find_fleet_block(fleet_section, fleet_id)

    # Classify
    if is_starbase(fleet_block):
        continue
    if is_civilian(fleet_block):
        continue
    if get_military_power(fleet_block) <= 100:
        continue

    # Extract ships
    ship_ids = extract_ship_ids(fleet_block)

    # Count by class
    class_counts = {}
    for ship_id in ship_ids:
        design_id = ship_to_design.get(ship_id)
        ship_size = design_to_size.get(design_id, 'unknown')
        class_counts[ship_size] = class_counts.get(ship_size, 0) + 1

    # Yield result
    yield {
        'fleet_id': fleet_id,
        'name': extract_name(fleet_block),
        'ship_classes': class_counts,
        'military_power': get_military_power(fleet_block)
    }
```
