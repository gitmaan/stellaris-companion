# Tool Return Schemas

This document defines the expected return schemas for each tool in `save_extractor.py`.
Maintaining stable schemas prevents bugs where code expects different key names.

---

## Consolidated Tools (Discord `/ask`)

The Discord bot routes `/ask` through `backend/core/companion.py`, which exposes a consolidated tool surface to the model:

- `get_snapshot()` → returns the `get_full_briefing()` schema (below)
- `get_details(categories, limit)` → returns a dict mapping category → detailed schema (leaders/planets/starbases/technology/wars/fleets/resources/diplomacy)
- `get_empire_details(name)` → returns the `get_empire(name)` schema (below)
- `search_save_file(query)` → returns the `search(query)` schema (below)

The rest of this document describes the underlying extractor return shapes.

---

## get_player_status()

```python
{
    'empire_name': str,           # "United Nations of Earth"
    'date': str,                  # "2342.06.15"
    'player_id': int,             # Usually 0
    'military_power': int,        # Total fleet power
    'economy_power': int,         # Economy score
    'tech_power': int,            # Tech score
    'fleet_count': int,           # Number of fleets
    'fleet_size': int,            # Total ships
    'celestial_bodies_in_territory': int,  # Systems owned
    'colonies': {
        'total_count': int,
        'total_population': int,
        'avg_pops_per_colony': float,
        'habitats': {'count': int, 'population': int},
        'planets': {'count': int, 'population': int},
    }
}
```

---

## get_wars()

```python
{
    'wars': list[str],            # War names (IMPORTANT: used by get_situation)
    'count': int,                 # Number of wars
    'player_at_war': bool,        # True if the player is at war
    'all_wars_count': int,        # Total wars in galaxy (for context/health checks)
    'active_war_ids': list[str],  # IDs if found in player block (may be absent)
}
```

**Note:** The `wars` key must be populated for `get_situation()` to detect war status.

---

## get_fleets()

```python
{
    'count': int,                 # Total fleets detected
    'fleet_names': list[str],     # Fleet names (first ~20)
}
```

---

## get_resources()

```python
{
    'stockpiles': {str: float},       # Current amounts
    'monthly_income': {str: float},   # Income by resource
    'monthly_expenses': {str: float}, # Expenses by resource
    'net_monthly': {str: float},      # KEY NAME: net = income - expense
    'summary': {
        'energy_net': float,
        'minerals_net': float,
        'food_net': float,
        'alloys_net': float,
        'consumer_goods_net': float,
        'research_total': float,
    }
}
```

**Note:** Use `net_monthly` not `monthly_net`. This was a bug that caused missing economy data.

---

## get_diplomacy()

```python
{
    'relations': list[dict],      # All relations
    'treaties': list[str],        # Treaty types
    'allies': list[str],          # Allied empire names
    'rivals': list[str],          # Rival empire names
    'federation': str | None,     # Federation name if member
    'relation_count': int,
}
```

---

## get_leaders()

```python
{
    'leaders': list[{
        'name': str,
        'class': str,             # 'scientist', 'admiral', 'general', 'governor'
        'level': int,
        'age': int,
        'traits': list[str],
    }],
    'count': int,
    'by_class': {str: int},       # Count by leader class
}
```

---

## get_technology()

```python
{
    'completed': list[str],       # Completed tech names
    'completed_count': int,
    'current_research': {
        'physics': str | None,
        'society': str | None,
        'engineering': str | None,
    },
    'by_category': {str: int},    # Count by tech category
}
```

---

## get_planets()

```python
{
    'planets': list[{
        'id': str,
        'name': str,
        'type': str,              # 'continental', 'ocean', 'habitat', etc.
        'population': int,
        'stability': float | None,
        'is_habitat': bool,
    }],
    'count': int,
    'total_population': int,
    'by_type': {str: int},        # Count by planet type
}
```

---

## get_starbases()

```python
{
    'starbases': list[{
        'id': str,
        'level': str,             # 'outpost', 'starport', 'starhold', etc.
        'modules': list[str],
        'buildings': list[str],
    }],
    'count': int,
    'by_level': {str: int},       # Count by level
}
```

---

## get_full_briefing()

Aggregates multiple tools into one response (~4k tokens).

```python
{
    'meta': {
        'empire_name': str,
        'date': str,
        'player_id': int,
    },
    'military': {
        'military_power': int,
        'fleet_count': int,
        'fleet_size': int,
    },
    'economy': {
        'economy_power': int,
        'tech_power': int,
        'net_monthly': dict,      # From get_resources()
        'key_resources': {
            'energy': float,
            'minerals': float,
            'alloys': float,
            'consumer_goods': float,
            'research_total': float,
        },
    },
    'territory': {...},
    'diplomacy': {...},
    'defense': {...},
    'leadership': {...},
}
```

---

## get_empire(name)

```python
{
    'name': str,                  # Name passed in
    'found': bool,                # True if an empire match is found
    'military_power': float,      # If found
    'economy_power': float,       # If found
    'opinion': float,             # If found (best-effort)
    'raw_data_preview': str,      # If found (bounded preview)
    'error': str,                 # If parsing failed
}
```

---

## search(query)

```python
{
    'query': str,
    'matches': list[{
        'position': int,
        'context': str,
    }],
    'total_found': int,
    'truncated': bool,            # Optional: True if output cap hit
    'error': str,                 # Optional: invalid query
}
```

---

## get_situation()

Used for personality tone adaptation.

```python
{
    'game_phase': str,            # 'early', 'mid', 'late', 'endgame'
    'year': int,
    'at_war': bool,               # Based on get_wars()['wars'] length
    'war_count': int,
    'contacts_made': bool,
    'contact_count': int,
    'rivals': list[str],
    'allies': list[str],
    'crisis_active': bool,
    'economy': {
        'energy_net': float,
        'minerals_net': float,
        'alloys_net': float,
        'consumer_goods_net': float,
        'research_net': float,
        'resources_in_deficit': int,
    },
}
```

---

## Key Invariants

1. **`get_wars()` must populate `wars` list** - `get_situation()` depends on it
2. **`get_resources()` uses `net_monthly`** - not `monthly_net`
3. **All ownership checks use `player_id`** - not hardcoded `0`
4. **`get_full_briefing()` keys must match source tools** - or data is lost
