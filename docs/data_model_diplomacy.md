# Stellaris Save File Data Model: Diplomacy Extraction

This document describes the save file structure for diplomatic data extraction, covering relations, federations, agreements (subjects/overlords), claims, and the galactic community.

## Table of Contents

1. [Data Sources Overview](#data-sources-overview)
2. [Diplomatic Relations](#diplomatic-relations)
3. [Federations](#federations)
4. [Subject/Overlord Agreements](#subjectoverlord-agreements)
5. [Territorial Claims](#territorial-claims)
6. [Galactic Community](#galactic-community)
7. [Truces](#truces)
8. [Data Relationships](#data-relationships)
9. [Expected Invariants](#expected-invariants)
10. [Validation Strategy](#validation-strategy)

---

## Data Sources Overview

| Data Type | Save File Location | Extraction Method |
|-----------|-------------------|-------------------|
| Bilateral Relations | `country[id].relations_manager.relation[]` | `get_diplomacy()` |
| Federation Details | `federation[id]` (top-level section) | `get_federation_details()` |
| Subject Agreements | `agreements.agreements[id]` | `get_subjects()` |
| Territorial Claims | `galactic_object[id].claims[]` | `get_claims()` |
| Galactic Community | `galactic_community` (top-level section) | `get_galactic_community()` |
| Truces | `truce[id]` (top-level section) | Referenced in `relations_manager` |

---

## Diplomatic Relations

### Location
Each country stores its diplomatic relations in a `relations_manager` block within its country definition:

```
country={
    0={  # Country ID
        ...
        relations_manager={
            relation={
                owner=0          # This country's ID
                country=1        # Target country ID
                ...
            }
            relation={
                owner=0
                country=2
                ...
            }
        }
    }
}
```

### Relation Block Fields

| Field | Type | Description |
|-------|------|-------------|
| `owner` | int | Country ID that owns this relation record |
| `country` | int | Target country ID this relation is with |
| `trust` | int | Trust level (0-200 typical range) |
| `relation_current` | int | Current opinion score (-1000 to +1000) |
| `relation_last_month` | int | Opinion from previous month |
| `contact` | yes/no | Whether contact has been made |
| `communications` | yes/no | Whether communications established |
| `borders` | yes/no | Whether borders are shared |
| `threat` | int | Threat level (0+) |
| `border_range` | int | Distance to border (2147483647 = no border) |
| `shared_rivals` | int | Number of shared rivals |

### Treaty Flags (Boolean Fields)

| Flag | Description |
|------|-------------|
| `alliance=yes` | Defensive pact (older format) |
| `defensive_pact=yes` | Defensive pact |
| `non_aggression_pact=yes` | Non-aggression pact |
| `commercial_pact=yes` | Commercial pact |
| `migration_treaty=yes` | Migration treaty |
| `migration_pact=yes` | Migration treaty (alternate key) |
| `sensor_link=yes` | Sensor link agreement |
| `research_agreement=yes` | Research agreement |
| `embassy=yes` | Embassy established |
| `closed_borders=yes` | Borders closed to this empire |
| `rival=yes` | Declared rival |
| `rivalry=yes` | Declared rival (alternate key) |
| `neutral=yes` | Neutral relation (pre-FTL, etc.) |

### Opinion Modifiers

Relations include stacked opinion modifiers:

```
modifier={
    modifier="opinion_fellow_galcom_member"
    value=50
}
modifier={
    modifier="opinion_first_contact_speak_like_us"
    start_date="2220.12.10"
    value=33.5
    decay=yes
}
```

| Field | Description |
|-------|-------------|
| `modifier` | Modifier type ID |
| `value` | Opinion value contribution |
| `start_date` | When modifier was applied |
| `decay` | Whether modifier decays over time |

### Truce Reference

Relations can reference a truce by ID:
```
truce=184549377  # References truce section entry
```

### Envoy Information

```
foreign_envoys={
    67108882   # Leader IDs of foreign envoys improving relations
}
envoy_opinion_positive=123.65  # Accumulated envoy bonus
num_favors=10                   # Diplomatic favors owed
```

---

## Federations

### Location

Top-level `federation` section with indexed entries:

```
federation={
    0={
        name={...}
        federation_progression={...}
        members={...}
        associates={...}
        leader=0
        start_date="2297.02.08"
        ...
    }
    1={...}
}
```

### Country Reference

Countries reference their federation membership:
```
country={
    0={
        federation=0  # Federation ID (4294967295 = none)
        ...
    }
}
```

### Federation Block Structure

| Field | Type | Description |
|-------|------|-------------|
| `name` | block | Localized federation name |
| `members` | int list | Country IDs of full members |
| `associates` | int list | Country IDs of associate members |
| `leader` | int | Country ID of current president |
| `start_date` | date | When federation was founded |
| `ship_design_collection` | block | Federation fleet designs |

### Federation Progression Block

Located within each federation entry:

```
federation_progression={
    federation_type="trade_federation"
    experience=20000
    base_cohesion=0
    cohesion=100
    levels=5
    laws={
        law_category_succession_term=succession_term_years_20
        law_category_centralization=centralization_very_high
        ...
    }
    perks={...}
    succession_type=rotation
    succession_term=years_20
    last_succession_date="2426.04.21"
    envoy={50332596 301990560}  # Leader IDs of assigned envoys
}
```

| Field | Type | Description |
|-------|------|-------------|
| `federation_type` | string | Type: trade_federation, military_federation, etc. |
| `experience` | float | Federation XP |
| `cohesion` | int | Current cohesion (-100 to 100) |
| `levels` | int | Federation level (1-5) |
| `laws` | block | Current federation laws by category |
| `perks` | list | Unlocked perks with level requirements |
| `succession_type` | string | How president is chosen |
| `succession_term` | string | Term length |
| `last_succession_date` | date | Last election date |

### Federation Types

| Type | Description |
|------|-------------|
| `trade_federation` | Trade League |
| `military_federation` | Martial Alliance |
| `default_federation` | Galactic Union |
| `research_federation` | Research Cooperative |
| `hegemony_federation` | Hegemony |

---

## Subject/Overlord Agreements

### Location

Top-level `agreements` section with nested `agreements` block:

```
agreements={
    agreements={
        0={
            owner=1          # Overlord country ID
            target=16777227  # Subject country ID
            active_status=active
            date_added="2223.09.29"
            term_data={...}
            subject_specialization={...}
        }
        ...
    }
}
```

### Agreement Entry Fields

| Field | Type | Description |
|-------|------|-------------|
| `owner` | int | Overlord country ID |
| `target` | int | Subject country ID |
| `active_status` | string | Status: active, demanded, etc. |
| `date_added` | date | When agreement was created |
| `date_changed` | date | Last modification date |
| `term_data` | block | Agreement terms |
| `subject_specialization` | block | Subject type and level |

### Term Data Block

```
term_data={
    can_subject_be_integrated=no
    can_subject_do_diplomacy=yes
    can_subject_vote=no
    has_cooldown_on_first_renegotiation=yes
    has_access=yes
    has_sensors=yes
    joins_overlord_wars=none
    calls_overlord_to_war=defensive
    subject_expansion_type=can_expand_with_tithe
    agreement_preset="preset_scholarium_mean_03"
    forced_initial_loyalty=-100
    discrete_terms={...}
    resource_terms={...}
}
```

| Field | Type | Description |
|-------|------|-------------|
| `can_subject_be_integrated` | yes/no | Integration allowed |
| `can_subject_do_diplomacy` | yes/no | Subject can conduct diplomacy |
| `can_subject_vote` | yes/no | Subject can vote in GalCom |
| `joins_overlord_wars` | string | none, defensive, all |
| `calls_overlord_to_war` | string | none, defensive, all |
| `subject_expansion_type` | string | can_expand, cannot_expand, can_expand_with_tithe |
| `agreement_preset` | string | Base preset type |
| `forced_initial_loyalty` | int | Starting loyalty modifier |

### Discrete Terms

```
discrete_terms={
    {
        key=specialist_type
        value=specialist_scholarium
    }
    {
        key=subject_integration
        value=subject_can_not_be_integrated
    }
    ...
}
```

### Resource Terms

```
resource_terms={
    {
        key=resource_subsidies_research
        value=0.6
    }
    {
        key=resource_subsidies_basic
        value=0
    }
    ...
}
```

### Subject Specialization Block

```
subject_specialization={
    specialist_type="specialist_scholarium"
    subject_conversion_process={
        progress=30.01725
        in_progress=no
        done=yes
        ...
    }
    level=2
    experience=0
}
```

### Subject Types

| Preset | Specialization | Description |
|--------|---------------|-------------|
| `preset_vassal_*` | none | Vassal |
| `preset_scholarium_*` | specialist_scholarium | Research subject |
| `preset_prospectorium_*` | specialist_prospectorium | Mining subject |
| `preset_bulwark_*` | specialist_bulwark | Military subject |
| `preset_subsidiary` | none | MegaCorp subsidiary |
| `preset_signatory` | none | Awakened Empire signatory |

---

## Territorial Claims

### Location

Claims are stored within each galactic object (star system):

```
galactic_object={
    0={
        coordinate={...}
        type=star
        name={key="NAME_Deneb"}
        claims={
            {
                owner=16777222
                date="2339.07.02"
                claims=1
            }
        }
        starbase_owner=0  # Current owner of the system
        ...
    }
}
```

### Claim Entry Fields

| Field | Type | Description |
|-------|------|-------------|
| `owner` | int | Country ID making the claim |
| `date` | date | When claim was made |
| `claims` | int | Claim strength (1-10, stacks for stronger claims) |

### System Ownership

The current system owner is indicated by:
```
starbase_owner=0  # Country ID owning the starbase
```

---

## Galactic Community

### Location

Top-level `galactic_community` section:

```
galactic_community={
    members={
        1 16777231 0 16777229 ...
    }
    council={
        1 0 16777229
    }
    proposed={
        69 63 7 21 ...
    }
    passed={
        0 4 1 12 9 ...
    }
    failed={
        30
    }
    emissaries={
        67109867 218104388 ...  # Leader IDs
    }
    voting=66                    # Currently voting resolution ID
    last=67                      # Last resolved resolution ID
    days=584                     # Days until next election
    community_formed="2262.01.01"
    council_established="2310.06.30"
    council_positions=3
    council_veto=yes
}
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `members` | int list | Country IDs of GalCom members |
| `council` | int list | Country IDs on the council |
| `proposed` | int list | Resolution IDs in queue |
| `passed` | int list | Resolution IDs that passed |
| `failed` | int list | Resolution IDs that failed |
| `emissaries` | int list | Leader IDs assigned as emissaries |
| `voting` | int | Current resolution being voted on |
| `days` | int | Days until next council election |
| `council_positions` | int | Number of council seats |
| `council_veto` | yes/no | Whether council has veto power |

---

## Truces

### Location

Top-level `truce` section:

```
truce={
    218103808={
        name={key=""}
        start_date="2426.04.29"
        truce_type=alliance
    }
    184549377={
        name={
            key="war_vs_adjectives"
            variables={...}
        }
        start_date="2426.04.20"
        truce_type=war
    }
    100663298=none  # Expired/invalid truce
}
```

### Truce Types

| Type | Description |
|------|-------------|
| `war` | Post-war truce |
| `alliance` | Post-alliance dissolution truce |

---

## Data Relationships

### Relation Country ID Resolution

```
relations_manager.relation.country → country[id]
```

The `country` field in a relation block references another country by ID. This ID must exist in the top-level `country` section.

### Federation Membership Cross-Reference

```
federation[id].members → country[id] list
country[id].federation → federation[id]
```

Membership is stored in both directions:
- Federation stores member list
- Country stores federation reference

### Agreement Relationships

```
agreements.agreements[id].owner → country[id] (overlord)
agreements.agreements[id].target → country[id] (subject)
```

### Claim Relationships

```
galactic_object[id].claims[].owner → country[id] (claimant)
galactic_object[id].starbase_owner → country[id] (current owner)
```

### Special Country IDs

| ID | Meaning |
|----|---------|
| `4294967295` | Null/None (max uint32) |
| `2147483647` | No border/infinite distance (max int32) |

---

## Expected Invariants

### Country ID Validity

1. All `country` references in relation blocks should exist in the country section
2. Country IDs should not be `4294967295` (null marker)
3. Country types include regular empires, fallen empires, enclaves, space fauna, etc.

### Federation Consistency

1. Federation member IDs should be valid country IDs
2. If country A is in federation F's member list, country A's `federation` field should equal F's ID
3. Federation president (`leader`) should be a member of the federation
4. Associates are separate from full members

### Treaty Symmetry

Some treaties are inherently symmetric:

| Treaty | Symmetry |
|--------|----------|
| Defensive Pact | Symmetric - both parties have it |
| Non-Aggression Pact | Symmetric |
| Commercial Pact | Symmetric |
| Migration Treaty | Symmetric |
| Research Agreement | Symmetric |
| Closed Borders | Asymmetric - A can close to B without B closing to A |
| Rivalry | Asymmetric - unilateral declaration |

### Agreement Validity

1. `owner` (overlord) and `target` (subject) should be valid country IDs
2. `owner` != `target` (no self-agreements)
3. Neither should be `4294967295`
4. `active_status` indicates agreement state

### Claim Validity

1. Claim `owner` should be a valid country ID
2. Multiple countries can claim the same system
3. Same country can have multiple claim entries (stacking)
4. Claim strength typically 1-10

### Opinion Range

1. `relation_current` typically ranges from -1000 to +1000
2. `trust` typically ranges from 0 to 200
3. Extreme values possible with certain modifiers

---

## Validation Strategy

### Phase 1: Country ID Validation

```python
def validate_country_ids(extractor):
    """Verify all referenced country IDs exist."""
    valid_ids = set(get_all_country_ids(extractor))

    # Check relations
    diplomacy = extractor.get_diplomacy()
    for rel in diplomacy['relations']:
        assert rel['country_id'] in valid_ids, f"Invalid country ID: {rel['country_id']}"

    # Check federation members
    fed = extractor.get_federation_details()
    if fed['federation_id']:
        for member_id in fed['members']:
            assert member_id in valid_ids, f"Invalid federation member: {member_id}"

    # Check agreements
    subjects = extractor.get_subjects()
    for entry in subjects['as_overlord']['subjects']:
        assert entry['target_id'] in valid_ids
    for entry in subjects['as_subject']['overlords']:
        assert entry['owner_id'] in valid_ids
```

### Phase 2: Cross-Reference Validation

```python
def validate_federation_membership(extractor):
    """Verify federation membership from both directions."""
    player_id = extractor.get_player_empire_id()
    diplomacy = extractor.get_diplomacy()
    fed_details = extractor.get_federation_details()

    if diplomacy['federation'] is not None:
        # Player claims to be in federation
        assert fed_details['federation_id'] == diplomacy['federation']
        assert player_id in fed_details['members']
```

### Phase 3: Treaty Symmetry Validation

```python
def validate_treaty_symmetry(extractor):
    """Check symmetric treaties are mutual."""
    player_id = extractor.get_player_empire_id()
    player_diplomacy = extractor.get_diplomacy()

    symmetric_treaties = ['defensive_pact', 'non_aggression_pact',
                          'commercial_pact', 'migration_treaty']

    for rel in player_diplomacy['relations']:
        other_id = rel['country_id']
        for treaty in symmetric_treaties:
            if rel.get(treaty):
                # Other country should also have this treaty with player
                other_relations = get_country_relations(extractor, other_id)
                player_rel = find_relation_to(other_relations, player_id)
                assert player_rel.get(treaty), \
                    f"Treaty {treaty} not symmetric with country {other_id}"
```

### Phase 4: Claim Validation

```python
def validate_claims(extractor):
    """Verify claim data integrity."""
    claims = extractor.get_claims()
    valid_ids = set(get_all_country_ids(extractor))

    for claim in claims['player_claims']:
        assert claim['claimant_id'] in valid_ids
        assert claim['strength'] >= 1

    for claim in claims['claims_against_player']:
        assert claim['claimant_id'] in valid_ids
```

### Phase 5: Range Validation

```python
def validate_opinion_ranges(extractor):
    """Check opinion values are in valid ranges."""
    diplomacy = extractor.get_diplomacy()

    for rel in diplomacy['relations']:
        opinion = rel.get('opinion', 0)
        assert -1000 <= opinion <= 1000, f"Opinion out of range: {opinion}"

        trust = rel.get('trust', 0)
        assert 0 <= trust <= 300, f"Trust out of range: {trust}"
```

---

## Implementation Notes

### Extraction Methods

| Method | File | Purpose |
|--------|------|---------|
| `get_diplomacy()` | `diplomacy.py` | Player bilateral relations |
| `get_federation_details()` | `diplomacy.py` | Player's federation info |
| `get_galactic_community()` | `diplomacy.py` | GalCom state |
| `get_subjects()` | `diplomacy.py` | Subject/overlord agreements |
| `get_claims()` | `diplomacy.py` | Territorial claims |
| `get_fallen_empires()` | `diplomacy.py` | Fallen Empire status |
| `get_espionage()` | `diplomacy.py` | Espionage operations |

### Performance Considerations

1. Relations are stored per-country, so only player relations are extracted by default
2. Claims scan the entire galactic_object section (can be large in late game)
3. Use `_extract_section()` for targeted section extraction vs full gamestate scan
4. Limit parameters available on methods to cap result sizes

### Special Cases

1. **Null IDs**: `4294967295` is used as a null marker - filter these out
2. **Machine Empires**: May have different relation mechanics
3. **Hive Minds**: Cannot have certain treaties
4. **Fallen Empires**: Have restricted diplomacy options
5. **Awakened Empires**: Use `gov_awakened_ascendancy` type
6. **Enclaves**: Special country types with limited diplomacy
