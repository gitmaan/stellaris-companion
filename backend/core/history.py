"""
History helpers for Phase 3 snapshot recording.

Milestone 1: record a snapshot on save detection without re-parsing.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from backend.core.database import GameDatabase


def extract_campaign_id_from_gamestate(gamestate: str) -> str | None:
    """Extract a stable campaign identifier from the gamestate text.

    Stellaris saves include a top-level `galaxy={ ... name=\"<uuid>\" ... }`.
    That UUID is a strong campaign discriminator across multiple runs.
    """
    if not gamestate:
        return None

    # Find the galaxy block (near the start of the file in practice).
    start = gamestate.find("\ngalaxy=")
    if start == -1:
        if gamestate.startswith("galaxy="):
            start = 0
        else:
            return None

    # Search a bounded window for the galaxy name UUID.
    window = gamestate[start : start + 20000]
    key = 'name="'
    pos = window.find(key)
    if pos == -1:
        return None
    end = window.find('"', pos + len(key))
    if end == -1:
        return None
    value = window[pos + len(key) : end].strip()
    return value or None


def extract_player_wars_from_gamestate(*, gamestate: str | None, player_id: int | None) -> dict[str, Any] | None:
    """Extract active wars involving the player from gamestate.

    This is a lightweight version of SaveExtractor.get_wars() so snapshot recording
    can capture wars without requiring additional tool calls.
    """
    if not gamestate:
        return None
    if player_id is None:
        return None

    pid = int(player_id)
    result: dict[str, Any] = {"player_at_war": False, "count": 0, "wars": []}

    # Check player's country block for active_wars IDs (fast, bounded window)
    country_start = gamestate.find("\ncountry=")
    if country_start != -1:
        window = gamestate[country_start : country_start + 120000]
        player_block_pos = window.find("\n\t0=")
        if player_block_pos != -1:
            player_window = window[player_block_pos : player_block_pos + 60000]
            aw_pos = player_window.find("active_wars")
            if aw_pos != -1:
                result["player_at_war"] = True

    # Extract war names involving player from war section (bounded)
    war_section_start = gamestate.find("\nwar=")
    if war_section_start == -1:
        if gamestate.startswith("war="):
            war_section_start = 0
        else:
            return result

    war_chunk = gamestate[war_section_start : war_section_start + 2500000]
    # Match blocks where attackers/defenders contain country=<player_id>
    # This is intentionally approximate but works well enough for delta events.
    import re

    pattern = r'name\s*=\s*"([^"]+)"[^}]*?(?:attackers|defenders)\s*=\s*\{[^}]*country=' + str(pid) + r'\b'
    names: list[str] = []
    for m in re.finditer(pattern, war_chunk, re.DOTALL):
        name = (m.group(1) or "").strip()
        if name and name not in names:
            names.append(name)

    result["wars"] = names[:25]
    result["count"] = len(names)
    if names:
        result["player_at_war"] = True

    return result


def extract_galaxy_settings_from_gamestate(gamestate: str | None) -> dict[str, Any] | None:
    """Extract a few stable galaxy/game settings used for milestone events."""
    if not gamestate:
        return None

    start = gamestate.find("\ngalaxy=")
    if start == -1:
        if gamestate.startswith("galaxy="):
            start = 0
        else:
            return None

    window = gamestate[start : start + 25000]

    def _find_int(key: str) -> int | None:
        import re

        m = re.search(rf"\b{key}\s*=\s*(\d+)\b", window)
        return int(m.group(1)) if m else None

    def _find_str(key: str) -> str | None:
        import re

        m = re.search(rf'\b{key}\s*=\s*"([^"]+)"', window)
        return m.group(1).strip() if m and m.group(1).strip() else None

    return {
        "galaxy_name": _find_str("name"),
        "mid_game_start": _find_int("mid_game_start"),
        "end_game_start": _find_int("end_game_start"),
        "victory_year": _find_int("victory_year"),
        "ironman": _find_str("ironman"),
        "difficulty": _find_str("difficulty"),
        "crisis_type": _find_str("crisis_type"),
    }


def extract_player_leaders_from_gamestate(*, gamestate: str | None, player_id: int | None) -> dict[str, Any] | None:
    """Extract a minimal leader roster for the player for diffing (hire/death/changes)."""
    if not gamestate or player_id is None:
        return None

    pid = int(player_id)
    leaders_start = gamestate.find("\nleaders=")
    if leaders_start == -1:
        if gamestate.startswith("leaders="):
            leaders_start = 0
        else:
            return None

    leaders_chunk = gamestate[leaders_start : leaders_start + 4000000]  # up to 4MB

    import re

    leader_start_pattern = r"\n\t(\d+)=\s*\{\s*\n\t\tname="
    leaders: list[dict[str, Any]] = []

    for m in re.finditer(leader_start_pattern, leaders_chunk):
        leader_id = m.group(1)
        block_start = m.start() + 1

        brace_count = 0
        started = False
        block_end = None
        # Bound scanning per leader block.
        for i, ch in enumerate(leaders_chunk[block_start : block_start + 8000], block_start):
            if ch == "{":
                brace_count += 1
                started = True
            elif ch == "}":
                brace_count -= 1
                if started and brace_count == 0:
                    block_end = i + 1
                    break

        if block_end is None:
            continue

        block = leaders_chunk[block_start:block_end]
        cm = re.search(r"\n\s*country=(\d+)", block)
        if not cm:
            continue
        if int(cm.group(1)) != pid:
            continue

        class_m = re.search(r'class="([^"]+)"', block)
        level_m = re.search(r"\n\s*level=(\d+)", block)
        death_m = re.search(r'death_date=\s*"(\d{4}\.\d{2}\.\d{2})"', block)
        added_m = re.search(r'date_added=\s*"(\d{4}\.\d{2}\.\d{2})"', block)
        recruit_m = re.search(r'recruitment_date=\s*"(\d{4}\.\d{2}\.\d{2})"', block)
        # Name key is usually stable even when localized.
        name_key_m = re.search(r'\bkey="([^"]+)"', block)

        leaders.append(
            {
                "id": int(leader_id),
                "class": class_m.group(1) if class_m else None,
                "level": int(level_m.group(1)) if level_m else None,
                "death_date": death_m.group(1) if death_m else None,
                "date_added": added_m.group(1) if added_m else None,
                "recruitment_date": recruit_m.group(1) if recruit_m else None,
                "name_key": name_key_m.group(1) if name_key_m else None,
            }
        )

        # Keep it bounded; player leader counts are typically small.
        if len(leaders) >= 100:
            break

    return {"player_id": pid, "leaders": leaders, "count": len(leaders)}


def extract_player_diplomacy_from_gamestate(*, gamestate: str | None, player_id: int | None) -> dict[str, Any] | None:
    """Extract a minimal diplomacy state for diffing (allies/rivals/treaties)."""
    if not gamestate or player_id is None:
        return None

    pid = int(player_id)
    country_start = gamestate.find("\ncountry=")
    if country_start == -1:
        return None

    # Grab a bounded window around the country section; player block is early within it.
    chunk = gamestate[country_start : country_start + 900000]
    player_block_pos = chunk.find("\n\t0=")
    if player_block_pos == -1:
        return None

    player_chunk = chunk[player_block_pos : player_block_pos + 400000]
    rel_mgr_pos = player_chunk.find("relations_manager=")
    if rel_mgr_pos == -1:
        return None

    rel_chunk = player_chunk[rel_mgr_pos : rel_mgr_pos + 250000]

    import re

    relation_marker = "relation="
    idx = 0
    allies: set[int] = set()
    rivals: set[int] = set()
    treaties: dict[str, set[int]] = {
        "research_agreement": set(),
        "commercial_pact": set(),
        "migration_treaty": set(),
        "non_aggression_pact": set(),
        "defensive_pact": set(),
        "embassy": set(),
        "truce": set(),
    }

    while True:
        idx = rel_chunk.find(relation_marker, idx)
        if idx == -1:
            break

        brace_start = rel_chunk.find("{", idx)
        if brace_start == -1:
            break

        brace_count = 0
        started = False
        end = None
        for j, ch in enumerate(rel_chunk[brace_start : brace_start + 12000], brace_start):
            if ch == "{":
                brace_count += 1
                started = True
            elif ch == "}":
                brace_count -= 1
                if started and brace_count == 0:
                    end = j + 1
                    break

        if end is None:
            idx = brace_start + 1
            continue

        block = rel_chunk[brace_start:end]
        owner_m = re.search(r"\bowner=(\d+)\b", block)
        if not owner_m or int(owner_m.group(1)) != pid:
            idx = end
            continue

        country_m = re.search(r"\bcountry=(\d+)\b", block)
        if not country_m:
            idx = end
            continue
        other_id = int(country_m.group(1))

        def has_yes(key: str) -> bool:
            return re.search(rf"\b{re.escape(key)}=yes\b", block) is not None

        if has_yes("alliance") or has_yes("defensive_pact"):
            allies.add(other_id)
        if has_yes("rivalry") or has_yes("rival") or has_yes("is_rival"):
            rivals.add(other_id)

        for key in list(treaties.keys()):
            if key == "truce":
                if re.search(r"\btruce=\d+\b", block):
                    treaties["truce"].add(other_id)
                continue
            if has_yes(key):
                treaties[key].add(other_id)

        idx = end

    return {
        "player_id": pid,
        "allies": sorted(allies),
        "rivals": sorted(rivals),
        "treaties": {k: sorted(v) for k, v in treaties.items() if v},
    }


def extract_player_techs_from_gamestate(*, gamestate: str | None, player_id: int | None) -> dict[str, Any] | None:
    """Extract the list of completed technologies for diffing individual tech completion."""
    if not gamestate or player_id is None:
        return None

    pid = int(player_id)
    country_start = gamestate.find("\ncountry=")
    if country_start == -1:
        return None

    chunk = gamestate[country_start : country_start + 900000]
    player_block_pos = chunk.find("\n\t0=")
    if player_block_pos == -1:
        return None

    player_chunk = chunk[player_block_pos : player_block_pos + 400000]
    tech_status_pos = player_chunk.find("tech_status=")
    if tech_status_pos == -1:
        return None

    import re

    tech_chunk = player_chunk[tech_status_pos : tech_status_pos + 100000]

    # Find technology={ ... } block containing completed tech names
    tech_block_match = re.search(r'technology=\s*\{([^}]+)\}', tech_chunk)
    techs: list[str] = []
    if tech_block_match:
        block = tech_block_match.group(1)
        # Techs are bare identifiers, one per line
        for line in block.split('\n'):
            t = line.strip()
            if t and not t.startswith('#'):
                techs.append(t)

    return {"player_id": pid, "techs": sorted(techs), "count": len(techs)}


def extract_player_policies_from_gamestate(*, gamestate: str | None, player_id: int | None) -> dict[str, Any] | None:
    """Extract active policies for the player empire."""
    if not gamestate or player_id is None:
        return None

    pid = int(player_id)
    country_start = gamestate.find("\ncountry=")
    if country_start == -1:
        return None

    chunk = gamestate[country_start : country_start + 900000]
    player_block_pos = chunk.find("\n\t0=")
    if player_block_pos == -1:
        return None

    player_chunk = chunk[player_block_pos : player_block_pos + 400000]

    import re

    policies: dict[str, str] = {}

    # Look for policy flags like: economic_policy=civilian_economy
    policy_patterns = [
        r'\n\t*economic_policy\s*=\s*"?(\w+)"?',
        r'\n\t*war_philosophy\s*=\s*"?(\w+)"?',
        r'\n\t*orbital_bombardment\s*=\s*"?(\w+)"?',
        r'\n\t*slavery\s*=\s*"?(\w+)"?',
        r'\n\t*purge\s*=\s*"?(\w+)"?',
        r'\n\t*resettlement\s*=\s*"?(\w+)"?',
        r'\n\t*population_controls\s*=\s*"?(\w+)"?',
        r'\n\t*robots_policy\s*=\s*"?(\w+)"?',
        r'\n\t*ai_rights\s*=\s*"?(\w+)"?',
        r'\n\t*trade_policy\s*=\s*"?(\w+)"?',
        r'\n\t*diplomatic_stance\s*=\s*"?(\w+)"?',
        r'\n\t*food_policy\s*=\s*"?(\w+)"?',
        r'\n\t*leader_enhancement\s*=\s*"?(\w+)"?',
        r'\n\t*first_contact_protocol\s*=\s*"?(\w+)"?',
    ]

    for pat in policy_patterns:
        m = re.search(pat, player_chunk)
        if m:
            policy_name = pat.split(r'\s*=')[0].replace(r'\n\t*', '').strip()
            policies[policy_name] = m.group(1)

    return {"player_id": pid, "policies": policies}


def extract_player_edicts_from_gamestate(*, gamestate: str | None, player_id: int | None) -> dict[str, Any] | None:
    """Extract active edicts for the player empire."""
    if not gamestate or player_id is None:
        return None

    pid = int(player_id)
    country_start = gamestate.find("\ncountry=")
    if country_start == -1:
        return None

    chunk = gamestate[country_start : country_start + 900000]
    player_block_pos = chunk.find("\n\t0=")
    if player_block_pos == -1:
        return None

    player_chunk = chunk[player_block_pos : player_block_pos + 400000]

    import re

    edicts: list[str] = []

    # Find active_edicts block
    edicts_match = re.search(r'active_edicts=\s*\{([^}]+)\}', player_chunk)
    if edicts_match:
        block = edicts_match.group(1)
        # Edicts can be: edict="edict_name" or just edict identifiers
        for m in re.finditer(r'edict\s*=\s*"?(\w+)"?', block):
            edicts.append(m.group(1))

    return {"player_id": pid, "edicts": sorted(set(edicts)), "count": len(set(edicts))}


def extract_megastructures_from_gamestate(*, gamestate: str | None, player_id: int | None) -> dict[str, Any] | None:
    """Extract megastructure status for the player."""
    if not gamestate or player_id is None:
        return None

    pid = int(player_id)

    import re

    mega_start = gamestate.find("\nmegastructures=")
    if mega_start == -1:
        if gamestate.startswith("megastructures="):
            mega_start = 0
        else:
            return None

    mega_chunk = gamestate[mega_start : mega_start + 2000000]

    structures: list[dict[str, Any]] = []

    # Find entries: 0={ type="..." owner=X ... }
    for m in re.finditer(r'\n\t(\d+)=\s*\{', mega_chunk):
        struct_id = m.group(1)
        start = m.start() + 1
        # Extract a bounded block
        block = mega_chunk[start : start + 2000]

        # Check if owned by player
        owner_m = re.search(r'\n\t*owner=(\d+)', block)
        if not owner_m or int(owner_m.group(1)) != pid:
            continue

        type_m = re.search(r'\n\t*type="([^"]+)"', block)
        stage_m = re.search(r'\n\t*stage=(\d+)', block)
        progress_m = re.search(r'\n\t*upgrade_progress=([\d.]+)', block)

        if type_m:
            structures.append({
                "id": int(struct_id),
                "type": type_m.group(1),
                "stage": int(stage_m.group(1)) if stage_m else 0,
                "progress": float(progress_m.group(1)) if progress_m else 0.0,
            })

        if len(structures) >= 50:  # Bound
            break

    return {"player_id": pid, "megastructures": structures, "count": len(structures)}


def extract_crisis_from_gamestate(gamestate: str | None) -> dict[str, Any] | None:
    """Extract crisis status from gamestate."""
    if not gamestate:
        return None

    import re

    result: dict[str, Any] = {"active": False, "type": None, "progress": None}

    # Look for crisis-related global variables or sections
    # The crisis section varies by type but often has markers like:
    # crisis_stage, prethoryn, contingency, unbidden

    # Check for global crisis markers
    crisis_patterns = [
        (r'prethoryn_invasion_stage\s*=\s*(\d+)', "prethoryn"),
        (r'contingency_stage\s*=\s*(\d+)', "contingency"),
        (r'unbidden_stage\s*=\s*(\d+)', "unbidden"),
        (r'aberrant_stage\s*=\s*(\d+)', "aberrant"),
        (r'vehement_stage\s*=\s*(\d+)', "vehement"),
        (r'ai_crisis_stage\s*=\s*(\d+)', "ai_uprising"),
        (r'crisis_spawn_chance\s*>', "pending"),  # Crisis about to spawn
    ]

    for pattern, crisis_type in crisis_patterns:
        m = re.search(pattern, gamestate)
        if m:
            result["active"] = True
            result["type"] = crisis_type
            if m.groups():
                result["progress"] = int(m.group(1))
            break

    return result


def extract_system_count_from_gamestate(*, gamestate: str | None, player_id: int | None) -> dict[str, Any] | None:
    """Extract total system count for the player (beyond just colonies)."""
    if not gamestate or player_id is None:
        return None

    pid = int(player_id)
    country_start = gamestate.find("\ncountry=")
    if country_start == -1:
        return None

    chunk = gamestate[country_start : country_start + 900000]
    player_block_pos = chunk.find("\n\t0=")
    if player_block_pos == -1:
        return None

    player_chunk = chunk[player_block_pos : player_block_pos + 400000]

    import re

    # Look for owned_systems or similar in the player's country block
    systems_m = re.search(r'\n\t*owned_systems\s*=\s*(\d+)', player_chunk)
    if systems_m:
        return {"player_id": pid, "system_count": int(systems_m.group(1))}

    # Fallback: count from celestial_bodies_in_territory if available
    celestial_m = re.search(r'\n\t*celestial_bodies_in_territory\s*=\s*(\d+)', player_chunk)
    if celestial_m:
        return {"player_id": pid, "celestial_bodies": int(celestial_m.group(1))}

    return None


def extract_fallen_empires_from_gamestate(gamestate: str | None) -> dict[str, Any] | None:
    """Extract all fallen empire information (dormant and awakened) for event detection."""
    if not gamestate:
        return None

    import re

    # Find all fallen empire types (both dormant and awakened)
    fe_positions = [(m.start(), 'dormant') for m in re.finditer(r'type="fallen_empire"', gamestate)]
    fe_positions += [(m.start(), 'awakened') for m in re.finditer(r'type="awakened_fallen_empire"', gamestate)]

    if not fe_positions:
        return {"fallen_empires": [], "dormant_count": 0, "awakened_count": 0, "war_in_heaven": False}

    fallen_empires: list[dict[str, Any]] = []

    # Fallen empire type mapping based on ethics
    FE_TYPE_MAP = {
        "xenophile": "Benevolent Interventionists",
        "xenophobe": "Militant Isolationists",
        "materialist": "Ancient Caretakers",
        "spiritualist": "Holy Guardians",
    }

    for pos, status in fe_positions:
        # Find the country block containing this empire
        country_start = gamestate.rfind("\n\t", max(0, pos - 500000), pos)
        if country_start == -1:
            continue

        # Extract a bounded chunk around the country
        chunk_start = max(0, country_start - 1000)
        chunk = gamestate[chunk_start : pos + 200000]

        # Find empire name
        name_match = re.search(r'name="([^"]+)"', chunk)
        name = name_match.group(1) if name_match else "Unknown Fallen Empire"

        # Find military power
        mil_match = re.search(r'\n\t*military_power=([\d.]+)', chunk)
        military_power = float(mil_match.group(1)) if mil_match else None

        # Find ethics (need to search deeper in the country block for ethos={})
        ethics = []
        ethos_match = re.search(r'ethos=\s*\{([^}]+)\}', chunk)
        if ethos_match:
            ethos_block = ethos_match.group(1)
            for e in re.finditer(r'ethic="([^"]+)"', ethos_block):
                ethics.append(e.group(1))

        # Determine FE archetype from ethics
        archetype = "Unknown"
        for ethic in ethics:
            ethic_lower = ethic.lower()
            for key, fe_type in FE_TYPE_MAP.items():
                if key in ethic_lower:
                    archetype = fe_type
                    break

        fallen_empires.append({
            "name": name,
            "status": status,
            "ethics": ethics,
            "military_power": military_power,
            "archetype": archetype,
        })

    dormant_count = sum(1 for fe in fallen_empires if fe['status'] == 'dormant')
    awakened_count = sum(1 for fe in fallen_empires if fe['status'] == 'awakened')

    # Check for War in Heaven (two or more awakened empires)
    war_in_heaven = awakened_count >= 2

    return {
        "fallen_empires": fallen_empires,
        "dormant_count": dormant_count,
        "awakened_count": awakened_count,
        "war_in_heaven": war_in_heaven,
    }


def compute_save_id(
    *,
    campaign_id: str | None,
    player_id: int | None,
    empire_name: str | None,
    save_path: Path | None,
) -> str:
    """Compute an identifier for a playthrough/save source.

    Priority:
    1) campaign_id (galaxy UUID) + player_id: robust across many campaigns in one folder.
    2) empire_name + save folder path: fallback when campaign_id is unavailable.
    """
    if campaign_id:
        pid = "" if player_id is None else str(int(player_id))
        raw = f"campaign:{campaign_id}|player:{pid}".encode("utf-8", errors="replace")
        return hashlib.sha1(raw).hexdigest()[:16]

    empire_part = (empire_name or "unknown").strip().lower()
    root = str(save_path.parent.resolve()) if save_path else "unknown"
    raw = f"empire:{empire_part}|root:{root}".encode("utf-8", errors="replace")
    return hashlib.sha1(raw).hexdigest()[:16]


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def extract_snapshot_metrics(briefing: dict[str, Any]) -> dict[str, Any]:
    meta = briefing.get("meta", {}) if isinstance(briefing, dict) else {}
    military = briefing.get("military", {}) if isinstance(briefing, dict) else {}
    economy = briefing.get("economy", {}) if isinstance(briefing, dict) else {}
    territory = briefing.get("territory", {}) if isinstance(briefing, dict) else {}

    game_date = meta.get("date")
    empire_name = meta.get("empire_name")
    campaign_id = meta.get("campaign_id")
    player_id = meta.get("player_id")

    net = economy.get("net_monthly", {}) if isinstance(economy.get("net_monthly", {}), dict) else {}
    colonies = territory.get("colonies", {}) if isinstance(territory.get("colonies", {}), dict) else {}

    return {
        "game_date": str(game_date) if game_date is not None else None,
        "empire_name": str(empire_name) if empire_name is not None else None,
        "campaign_id": str(campaign_id) if campaign_id is not None else None,
        "player_id": int(player_id) if isinstance(player_id, int) else None,
        "military_power": _safe_int(military.get("military_power")),
        "colony_count": _safe_int(colonies.get("total_count")),
        # wars_count not in get_full_briefing() yet (fill in later milestones)
        "wars_count": None,
        "energy_net": _safe_float(net.get("energy")),
        "alloys_net": _safe_float(net.get("alloys")),
    }


def build_event_state_from_briefing(briefing: dict[str, Any]) -> dict[str, Any]:
    """Build a compact state snapshot used for event detection and reporting.

    This intentionally excludes large, low-signal lists (planets, ship breakdowns, etc.)
    while preserving the keys consumed by `backend.core.events.compute_events()` and
    `backend.core.reporting`.
    """
    if not isinstance(briefing, dict):
        return {}

    meta = briefing.get("meta") if isinstance(briefing.get("meta"), dict) else {}
    military = briefing.get("military") if isinstance(briefing.get("military"), dict) else {}
    economy = briefing.get("economy") if isinstance(briefing.get("economy"), dict) else {}
    territory = briefing.get("territory") if isinstance(briefing.get("territory"), dict) else {}
    technology = briefing.get("technology") if isinstance(briefing.get("technology"), dict) else {}
    diplomacy = briefing.get("diplomacy") if isinstance(briefing.get("diplomacy"), dict) else {}

    net_monthly = economy.get("net_monthly") if isinstance(economy.get("net_monthly"), dict) else {}
    colonies = territory.get("colonies") if isinstance(territory.get("colonies"), dict) else {}

    # Keep only economy nets used by event detection (plus a few high-signal ones).
    economy_state = {
        "net_monthly": {
            k: net_monthly.get(k)
            for k in ("energy", "alloys", "consumer_goods", "food", "minerals")
            if k in net_monthly
        }
    }

    territory_state = {"colonies": {"total_count": colonies.get("total_count")}} if colonies else {"colonies": {}}

    # Military keys used by event detection/reporting.
    military_state = {
        k: military.get(k)
        for k in ("military_power", "military_fleets", "fleet_count")
        if k in military
    }

    technology_state = {k: technology.get(k) for k in ("tech_count",) if k in technology}
    diplomacy_state = {}
    if "federation" in diplomacy:
        diplomacy_state["federation"] = diplomacy.get("federation")

    # History payload is already “small by design” (built by history enrichment helpers).
    history = briefing.get("history") if isinstance(briefing.get("history"), dict) else {}

    event_state: dict[str, Any] = {
        "meta": {k: meta.get(k) for k in ("date", "empire_name", "campaign_id", "player_id") if k in meta},
        "military": military_state,
        "economy": economy_state,
        "territory": territory_state,
        "technology": technology_state,
        "diplomacy": diplomacy_state,
    }
    if history:
        event_state["history"] = history

    return event_state


def build_history_enrichment(*, gamestate: str | None, player_id: int | None) -> dict[str, Any]:
    """Build the optional `history` payload stored with a snapshot.

    This is intentionally best-effort and returns an empty dict when inputs are missing.
    """
    if not gamestate:
        return {}

    resolved_player_id = int(player_id) if isinstance(player_id, int) else None

    wars = extract_player_wars_from_gamestate(gamestate=gamestate, player_id=resolved_player_id)
    leaders = extract_player_leaders_from_gamestate(gamestate=gamestate, player_id=resolved_player_id)
    diplomacy = extract_player_diplomacy_from_gamestate(gamestate=gamestate, player_id=resolved_player_id)
    galaxy = extract_galaxy_settings_from_gamestate(gamestate)

    techs = extract_player_techs_from_gamestate(gamestate=gamestate, player_id=resolved_player_id)
    policies = extract_player_policies_from_gamestate(gamestate=gamestate, player_id=resolved_player_id)
    edicts = extract_player_edicts_from_gamestate(gamestate=gamestate, player_id=resolved_player_id)
    megastructures = extract_megastructures_from_gamestate(gamestate=gamestate, player_id=resolved_player_id)
    crisis = extract_crisis_from_gamestate(gamestate)
    systems = extract_system_count_from_gamestate(gamestate=gamestate, player_id=resolved_player_id)
    fallen_empires = extract_fallen_empires_from_gamestate(gamestate)

    history: dict[str, Any] = {}
    if wars:
        history["wars"] = wars
    if leaders:
        history["leaders"] = leaders
    if diplomacy:
        history["diplomacy"] = diplomacy
    if galaxy:
        history["galaxy"] = galaxy
    if techs:
        history["techs"] = techs
    if policies:
        history["policies"] = policies
    if edicts:
        history["edicts"] = edicts
    if megastructures:
        history["megastructures"] = megastructures
    if crisis:
        history["crisis"] = crisis
    if systems:
        history["systems"] = systems
    if fallen_empires:
        history["fallen_empires"] = fallen_empires

    return history


def record_snapshot_from_briefing(
    *,
    db: GameDatabase,
    save_path: Path | None,
    save_hash: str | None,
    briefing: dict[str, Any],
    briefing_json: str | None = None,
) -> tuple[bool, int | None, str]:
    """Record a snapshot when you already have a full briefing dict.

    This avoids re-parsing gamestate in the main process (useful when ingestion happens
    in a separate worker process). If the briefing already contains a `history` key,
    it will be persisted as-is.
    """
    metrics = extract_snapshot_metrics(briefing)
    resolved_campaign_id = metrics.get("campaign_id")
    resolved_player_id = metrics.get("player_id")

    history = briefing.get("history") if isinstance(briefing.get("history"), dict) else None
    wars = history.get("wars") if isinstance(history, dict) else None

    session_id = db.get_or_create_active_session(
        save_id=compute_save_id(
            campaign_id=resolved_campaign_id,
            player_id=resolved_player_id,
            empire_name=metrics.get("empire_name"),
            save_path=save_path,
        ),
        save_path=str(save_path) if save_path else None,
        empire_name=metrics.get("empire_name"),
        last_game_date=metrics.get("game_date"),
    )

    full_json = briefing_json if isinstance(briefing_json, str) and briefing_json else json.dumps(briefing, ensure_ascii=False, separators=(",", ":"))
    inserted, snapshot_id = db.insert_snapshot_if_new(
        session_id=session_id,
        game_date=metrics.get("game_date"),
        save_hash=save_hash,
        military_power=metrics.get("military_power"),
        colony_count=metrics.get("colony_count"),
        wars_count=(wars.get("count") if isinstance(wars, dict) else metrics.get("wars_count")),
        energy_net=metrics.get("energy_net"),
        alloys_net=metrics.get("alloys_net"),
        # Full briefings are stored on the session row (latest) and only kept per-snapshot for the baseline.
        full_briefing_json=full_json,
        event_state_json=json.dumps(
            build_event_state_from_briefing(briefing),
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    )
    if inserted and snapshot_id is not None:
        try:
            # Persist the latest full briefing once per session (overwrite), not per snapshot row.
            db.update_session_latest_briefing(
                session_id=session_id,
                latest_briefing_json=full_json,
                last_game_date=metrics.get("game_date"),
            )
        except Exception:
            pass
        try:
            db.record_events_for_new_snapshot(session_id=session_id, snapshot_id=snapshot_id, current_briefing=briefing)
        except Exception:
            pass
        try:
            db.enforce_full_briefing_retention(session_id=session_id)
        except Exception:
            pass
        try:
            db.maybe_checkpoint_wal()
        except Exception:
            pass

    return inserted, snapshot_id, session_id


def record_snapshot_from_companion(
    *,
    db: GameDatabase,
    save_path: Path | None,
    save_hash: str | None,
    gamestate: str | None = None,
    player_id: int | None = None,
    campaign_id: str | None = None,
    briefing: dict[str, Any],
) -> tuple[bool, int | None, str]:
    """Record a snapshot and create/reuse an active session.

    Returns:
        (inserted, snapshot_id, session_id)
    """
    metrics = extract_snapshot_metrics(briefing)
    resolved_campaign_id = (
        campaign_id
        or metrics.get("campaign_id")
        or (extract_campaign_id_from_gamestate(gamestate) if gamestate else None)
    )
    resolved_player_id = player_id if player_id is not None else metrics.get("player_id")

    wars = extract_player_wars_from_gamestate(gamestate=gamestate, player_id=resolved_player_id)
    leaders = extract_player_leaders_from_gamestate(gamestate=gamestate, player_id=resolved_player_id)
    diplomacy = extract_player_diplomacy_from_gamestate(gamestate=gamestate, player_id=resolved_player_id)
    galaxy = extract_galaxy_settings_from_gamestate(gamestate)

    # Phase 6: Additional extractions for expanded event detection
    techs = extract_player_techs_from_gamestate(gamestate=gamestate, player_id=resolved_player_id)
    policies = extract_player_policies_from_gamestate(gamestate=gamestate, player_id=resolved_player_id)
    edicts = extract_player_edicts_from_gamestate(gamestate=gamestate, player_id=resolved_player_id)
    megastructures = extract_megastructures_from_gamestate(gamestate=gamestate, player_id=resolved_player_id)
    crisis = extract_crisis_from_gamestate(gamestate)
    systems = extract_system_count_from_gamestate(gamestate=gamestate, player_id=resolved_player_id)
    fallen_empires = extract_fallen_empires_from_gamestate(gamestate)

    # Avoid mutating the live snapshot object used by /ask; store extras in a copy.
    briefing_for_storage = dict(briefing)
    history: dict[str, Any] = {}
    if wars:
        history["wars"] = wars
    if leaders:
        history["leaders"] = leaders
    if diplomacy:
        history["diplomacy"] = diplomacy
    if galaxy:
        history["galaxy"] = galaxy
    # Phase 6 additions
    if techs:
        history["techs"] = techs
    if policies:
        history["policies"] = policies
    if edicts:
        history["edicts"] = edicts
    if megastructures:
        history["megastructures"] = megastructures
    if crisis:
        history["crisis"] = crisis
    if systems:
        history["systems"] = systems
    if fallen_empires:
        history["fallen_empires"] = fallen_empires
    if history:
        briefing_for_storage["history"] = history

    session_id = db.get_or_create_active_session(
        save_id=compute_save_id(
            campaign_id=resolved_campaign_id,
            player_id=resolved_player_id,
            empire_name=metrics.get("empire_name"),
            save_path=save_path,
        ),
        save_path=str(save_path) if save_path else None,
        empire_name=metrics.get("empire_name"),
        last_game_date=metrics.get("game_date"),
    )

    full_json = json.dumps(briefing_for_storage, ensure_ascii=False, separators=(",", ":"))
    inserted, snapshot_id = db.insert_snapshot_if_new(
        session_id=session_id,
        game_date=metrics.get("game_date"),
        save_hash=save_hash,
        military_power=metrics.get("military_power"),
        colony_count=metrics.get("colony_count"),
        wars_count=wars.get("count") if isinstance(wars, dict) else metrics.get("wars_count"),
        energy_net=metrics.get("energy_net"),
        alloys_net=metrics.get("alloys_net"),
        full_briefing_json=full_json,
        event_state_json=json.dumps(
            build_event_state_from_briefing(briefing_for_storage),
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    )
    if inserted and snapshot_id is not None:
        try:
            db.update_session_latest_briefing(
                session_id=session_id,
                latest_briefing_json=full_json,
                last_game_date=metrics.get("game_date"),
            )
        except Exception:
            pass
        try:
            db.record_events_for_new_snapshot(session_id=session_id, snapshot_id=snapshot_id, current_briefing=briefing_for_storage)
        except Exception:
            # Event generation should never break snapshot recording.
            pass
        try:
            db.enforce_full_briefing_retention(session_id=session_id)
        except Exception:
            pass
        try:
            db.maybe_checkpoint_wal()
        except Exception:
            pass

    return inserted, snapshot_id, session_id
