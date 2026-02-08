"""
Read-only accessors for snapshot history data.

ARCHITECTURE:
- signals.py CREATES signals during save ingestion (calls SaveExtractor)
- history.py STORES signals in database snapshots
- snapshot_reader.py READS signals from stored snapshots (this file)
- events.py USES snapshot_reader to detect changes between snapshots

This separation makes the data flow clear:
  SaveExtractor → signals.py → history.py → DB → snapshot_reader.py → events.py

NAMING CONVENTION:
- signals.py: _extract_*_signals() - CREATES data from extractors
- snapshot_reader.py: get_*() - READS data from stored snapshots
"""

from typing import Any


def _get_history(briefing: dict[str, Any]) -> dict[str, Any]:
    """Get history dict from briefing safely."""
    if not isinstance(briefing, dict):
        return {}
    history = briefing.get("history")
    return history if isinstance(history, dict) else {}


# =============================================================================
# GENERIC SIGNAL ACCESSORS
# =============================================================================


def get_signal(briefing: dict[str, Any], key: str, default: Any = None) -> Any:
    """Get a signal from briefing.history with type-safe defaults.

    Args:
        briefing: Snapshot briefing dict containing history
        key: Signal key (e.g., "lgate", "leaders", "wars")
        default: Default value if signal is missing or wrong type

    Returns:
        Signal data or default value if missing/invalid
    """
    history = _get_history(briefing)
    value = history.get(key)

    if value is None:
        return default if default is not None else {}

    # Type validation based on default
    if default is not None:
        if isinstance(default, dict) and not isinstance(value, dict):
            return default
        if isinstance(default, (list, set)) and not isinstance(value, (list, set)):
            return default

    return value


# =============================================================================
# WAR & MILITARY
# =============================================================================


def get_wars(briefing: dict[str, Any]) -> dict[str, Any]:
    """Get war data from history.

    Returns:
        Dict with keys: count, wars (list), names (list)
    """
    return get_signal(briefing, "wars", {"count": 0, "wars": [], "names": []})


def get_war_names(briefing: dict[str, Any]) -> set[str]:
    """Get set of current war names."""
    wars = get_wars(briefing)
    names = wars.get("wars") or wars.get("names") or []
    if not isinstance(names, list):
        return set()
    return {str(n).strip() for n in names if str(n).strip()}


def get_war_battle_locations(briefing: dict[str, Any]) -> dict[str, list[str]]:
    """Get battle location system names per war.

    Returns:
        Dict mapping war name to list of top system names (up to 3).
    """
    wars = get_wars(briefing)
    locs = wars.get("battle_locations", {})
    if not isinstance(locs, dict):
        return {}
    return locs


# =============================================================================
# LEADERS & RULERS
# =============================================================================


def get_leaders(briefing: dict[str, Any]) -> dict[str, Any]:
    """Get leader data including ruler tracking.

    Returns:
        Dict with keys: count, leaders (list), ruler_id, ruler_name
    """
    return get_signal(
        briefing,
        "leaders",
        {"count": 0, "leaders": [], "ruler_id": None, "ruler_name": None},
    )


def get_player_leaders(briefing: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """Get leaders keyed by ID for efficient lookup.

    Returns:
        Dict mapping leader_id (int) to leader data dict
    """
    leaders = get_leaders(briefing)
    items = leaders.get("leaders")
    if not isinstance(items, list):
        return {}
    out: dict[int, dict[str, Any]] = {}
    for leader in items:
        if not isinstance(leader, dict):
            continue
        lid = leader.get("id")
        try:
            lid_int = int(lid)
        except Exception:
            continue
        out[lid_int] = leader
    return out


def get_ruler_info(briefing: dict[str, Any]) -> dict[str, Any]:
    """Get current ruler info.

    Returns:
        Dict with keys: ruler_id, ruler_name
    """
    leaders = get_leaders(briefing)
    return {
        "ruler_id": leaders.get("ruler_id"),
        "ruler_name": leaders.get("ruler_name"),
    }


# =============================================================================
# DIPLOMACY
# =============================================================================


def get_diplomacy(briefing: dict[str, Any]) -> dict[str, Any]:
    """Get diplomacy data including empire names map.

    Returns:
        Dict with keys: allies, rivals, treaties, empire_names, known_empire_ids
    """
    return get_signal(
        briefing,
        "diplomacy",
        {"allies": [], "rivals": [], "treaties": {}, "empire_names": {}, "known_empire_ids": []},
    )


def get_empire_names(briefing: dict[str, Any]) -> dict[int, str]:
    """Get empire_names mapping from history.diplomacy.

    Returns:
        Dict mapping country_id (int) to empire name (str)
    """
    dip = get_diplomacy(briefing)
    names = dip.get("empire_names")
    if not isinstance(names, dict):
        return {}

    result: dict[int, str] = {}
    for k, v in names.items():
        try:
            cid = int(k)
            if isinstance(v, str) and v.strip():
                result[cid] = v.strip()
        except (ValueError, TypeError):
            continue
    return result


def get_diplomacy_sets(
    briefing: dict[str, Any],
) -> tuple[set[int], set[int], dict[str, set[int]]]:
    """Get allies, rivals, and treaties as sets for comparison.

    Returns:
        Tuple of (allies set, rivals set, treaties dict of sets)
    """
    dip = get_diplomacy(briefing)

    def _to_int_set(value: Any) -> set[int]:
        if not isinstance(value, list):
            return set()
        out: set[int] = set()
        for v in value:
            try:
                out.add(int(v))
            except Exception:
                continue
        return out

    allies = _to_int_set(dip.get("allies"))
    rivals = _to_int_set(dip.get("rivals"))
    treaties_raw = dip.get("treaties") if isinstance(dip.get("treaties"), dict) else {}
    treaties: dict[str, set[int]] = {}
    for k, v in treaties_raw.items():
        treaties[str(k)] = _to_int_set(v)

    return allies, rivals, treaties


def get_known_empire_ids(briefing: dict[str, Any]) -> set[int]:
    """Get set of known empire IDs (for first contact detection).

    Returns:
        Set of country IDs for all known empires
    """
    dip = get_diplomacy(briefing)
    known_ids = dip.get("known_empire_ids")
    if not isinstance(known_ids, list):
        return set()
    result: set[int] = set()
    for cid in known_ids:
        try:
            result.add(int(cid))
        except (ValueError, TypeError):
            continue
    return result


# =============================================================================
# SUBJECTS / VASSALS
# =============================================================================


def get_subjects(briefing: dict[str, Any]) -> dict[str, Any]:
    """Get subjects/vassal data from history.

    Returns:
        Dict with keys: as_overlord, as_subject, subject_details, empire_names
    """
    return get_signal(
        briefing,
        "subjects",
        {"as_overlord": [], "as_subject": [], "subject_details": {}, "empire_names": {}},
    )


def get_subject_sets(
    briefing: dict[str, Any],
) -> tuple[set[int], set[int]]:
    """Get our-subjects and our-overlords as sets for comparison.

    Returns:
        Tuple of (our_subjects set, our_overlords set)
    """
    subj = get_subjects(briefing)

    def _to_int_set(value: Any) -> set[int]:
        if not isinstance(value, list):
            return set()
        out: set[int] = set()
        for v in value:
            try:
                out.add(int(v))
            except Exception:
                continue
        return out

    our_subjects = _to_int_set(subj.get("as_overlord"))
    our_overlords = _to_int_set(subj.get("as_subject"))
    return our_subjects, our_overlords


def get_subject_details(briefing: dict[str, Any]) -> dict[int, dict]:
    """Get subject detail map for event summaries.

    Returns:
        Dict mapping country_id (int) to detail dict with preset/specialization.
    """
    subj = get_subjects(briefing)
    raw = subj.get("subject_details")
    if not isinstance(raw, dict):
        return {}
    result: dict[int, dict] = {}
    for k, v in raw.items():
        try:
            cid = int(k)
            if isinstance(v, dict):
                result[cid] = v
        except (ValueError, TypeError):
            continue
    return result


# =============================================================================
# TECHNOLOGY
# =============================================================================


def get_technology(briefing: dict[str, Any]) -> dict[str, Any]:
    """Get technology data.

    Returns:
        Dict with keys: count, techs (list), in_progress
    """
    default = {"count": 0, "techs": [], "in_progress": {}}
    return get_signal(briefing, "technology", default)


def get_tech_list(briefing: dict[str, Any]) -> set[str]:
    """Get set of completed technology names."""
    techs = get_technology(briefing)
    tech_list = techs.get("techs") or []
    if not isinstance(tech_list, list):
        return set()
    return {str(t).strip() for t in tech_list if str(t).strip()}


# =============================================================================
# TERRITORY & SYSTEMS
# =============================================================================


def get_systems(briefing: dict[str, Any]) -> dict[str, Any]:
    """Get systems data.

    Returns:
        Dict with keys: count (or system_count, celestial_bodies)
    """
    return get_signal(briefing, "systems", {"count": 0})


def get_system_count(briefing: dict[str, Any]) -> int | None:
    """Get total system count."""
    systems = get_systems(briefing)
    count = systems.get("count") or systems.get("system_count") or systems.get("celestial_bodies")
    try:
        return int(count) if count is not None else None
    except Exception:
        return None


# =============================================================================
# GALAXY SETTINGS
# =============================================================================


def get_galaxy(briefing: dict[str, Any]) -> dict[str, Any]:
    """Get galaxy settings (static per game).

    Returns:
        Dict with keys like mid_game_start, end_game_start, etc.
    """
    return get_signal(briefing, "galaxy", {})


# =============================================================================
# POLICIES & EDICTS
# =============================================================================


def get_policies(briefing: dict[str, Any]) -> dict[str, str]:
    """Get active policies as dict.

    Returns:
        Dict mapping policy name to current setting
    """
    policies_data = get_signal(briefing, "policies", {})
    policy_dict = policies_data.get("policies") or policies_data
    if not isinstance(policy_dict, dict):
        return {}
    return {str(k): str(v) for k, v in policy_dict.items()}


def get_edicts(briefing: dict[str, Any]) -> set[str]:
    """Get active edict names as set.

    Returns:
        Set of active edict IDs
    """
    edicts_data = get_signal(briefing, "edicts", {})
    if isinstance(edicts_data, list):
        edict_list = edicts_data
    elif isinstance(edicts_data, dict):
        edict_list = edicts_data.get("edicts") or []
    else:
        return set()
    if not isinstance(edict_list, list):
        return set()
    return {str(e).strip() for e in edict_list if str(e).strip()}


# =============================================================================
# ASCENSION & TRADITIONS
# =============================================================================


def get_ascension_perks(briefing: dict[str, Any]) -> dict[str, Any]:
    """Get ascension perks data.

    Returns:
        Dict with keys: perks (list), count
    """
    return get_signal(briefing, "ascension_perks", {"perks": [], "count": 0})


def get_ascension_perk_set(briefing: dict[str, Any]) -> set[str]:
    """Get set of ascension perk IDs.

    Returns:
        Set of perk IDs (e.g., {'ap_synthetic_evolution', 'ap_colossus'})
    """
    perks = get_ascension_perks(briefing)
    perk_list = perks.get("perks") or []
    if not isinstance(perk_list, list):
        return set()
    return {str(p).strip() for p in perk_list if str(p).strip()}


def get_traditions(briefing: dict[str, Any]) -> dict[str, Any]:
    """Get tradition tree completion status.

    Returns:
        Dict with keys: finished_trees (list), by_tree (dict), total_traditions
    """
    return get_signal(
        briefing, "traditions", {"finished_trees": [], "by_tree": {}, "total_traditions": 0}
    )


def get_finished_traditions(briefing: dict[str, Any]) -> set[str]:
    """Get set of finished tradition tree names.

    Returns:
        Set of finished tree names (e.g., {'expansion', 'supremacy'})
    """
    traditions = get_traditions(briefing)
    finished_list = traditions.get("finished_trees") or []
    if not isinstance(finished_list, list):
        return set()
    return {str(t).strip() for t in finished_list if str(t).strip()}


# =============================================================================
# ENDGAME & CRISIS
# =============================================================================


def get_lgate(briefing: dict[str, Any]) -> dict[str, Any]:
    """Get L-Gate status.

    Returns:
        Dict with keys: enabled, opened, insights_collected, insights_required
    """
    return get_signal(
        briefing, "lgate", {"enabled": False, "opened": False, "insights_collected": 0}
    )


def get_menace(briefing: dict[str, Any]) -> dict[str, Any]:
    """Get menace/Become the Crisis status.

    Returns:
        Dict with keys: has_crisis_perk, menace_level, crisis_level
    """
    return get_signal(
        briefing, "menace", {"has_crisis_perk": False, "menace_level": 0, "crisis_level": 0}
    )


def get_great_khan(briefing: dict[str, Any]) -> dict[str, Any]:
    """Get Great Khan / Marauder status.

    Returns:
        Dict with keys: marauders_present, marauder_count, khan_risen, khan_status, khan_country_id
    """
    return get_signal(
        briefing,
        "great_khan",
        {
            "marauders_present": False,
            "marauder_count": 0,
            "khan_risen": False,
            "khan_status": None,
            "khan_country_id": None,
        },
    )


def get_crisis(briefing: dict[str, Any]) -> dict[str, Any]:
    """Get crisis status.

    Returns:
        Dict with keys: active, type
    """
    return get_signal(briefing, "crisis", {"active": False, "type": None})


def get_galactic_community(briefing: dict[str, Any]) -> dict[str, Any]:
    """Get Galactic Community membership status.

    Returns:
        Dict with keys: exists, member, council_member, members_count
    """
    return get_signal(
        briefing,
        "galactic_community",
        {"exists": False, "member": False, "council_member": False, "members_count": 0},
    )


# =============================================================================
# PRECURSORS
# =============================================================================


def get_precursors(briefing: dict[str, Any]) -> dict[str, Any]:
    """Get precursor discovery status.

    Returns:
        Dict with keys: discovered_homeworlds (list), precursor_progress (dict)
    """
    return get_signal(
        briefing, "precursors", {"discovered_homeworlds": [], "precursor_progress": {}}
    )


def get_discovered_homeworlds(briefing: dict[str, Any]) -> set[str]:
    """Get set of discovered precursor homeworld keys.

    Returns:
        Set of precursor keys where homeworld was found
    """
    precursors = get_precursors(briefing)
    homeworld_list = precursors.get("discovered_homeworlds") or []
    if not isinstance(homeworld_list, list):
        return set()
    return {str(h).strip() for h in homeworld_list if str(h).strip()}


# =============================================================================
# FALLEN EMPIRES
# =============================================================================


def get_fallen_empires(briefing: dict[str, Any]) -> dict[str, Any]:
    """Get fallen empires data.

    Returns:
        Dict with fallen_empires list and metadata
    """
    return get_signal(briefing, "fallen_empires", {"fallen_empires": [], "war_in_heaven": False})


def get_fallen_empires_by_name(briefing: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Get fallen empires keyed by name for comparison.

    Returns:
        Dict mapping empire name to empire data
    """
    fe_data = get_fallen_empires(briefing)
    empire_list = fe_data.get("fallen_empires") or []
    if not isinstance(empire_list, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for e in empire_list:
        if not isinstance(e, dict):
            continue
        name = e.get("name")
        if not name:
            continue
        result[str(name)] = e
    return result


# =============================================================================
# MEGASTRUCTURES
# =============================================================================


def get_megastructures(briefing: dict[str, Any]) -> dict[str, Any]:
    """Get megastructures data.

    Returns:
        Dict with megastructures list
    """
    return get_signal(briefing, "megastructures", {"megastructures": []})


def get_geography(briefing: dict[str, Any]) -> dict[str, Any]:
    """Get strategic geography data from history.

    Returns:
        Dict with keys: border_neighbors, chokepoints, empire_centroid, total_player_systems
    """
    return get_signal(
        briefing,
        "geography",
        {
            "border_neighbors": [],
            "chokepoints": [],
            "empire_centroid": None,
            "total_player_systems": 0,
        },
    )


def get_border_neighbors(briefing: dict[str, Any]) -> list[dict]:
    """Get border neighbor empires with direction and shared border count.

    Returns:
        List of dicts with keys: empire_name, empire_id, direction, shared_border_systems
    """
    return get_geography(briefing).get("border_neighbors", [])


def get_megastructures_by_id(briefing: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """Get megastructures keyed by ID for comparison.

    Returns:
        Dict mapping mega_id (int) to megastructure data
    """
    megas = get_megastructures(briefing)
    mega_list = megas.get("megastructures") or []
    if not isinstance(mega_list, list):
        return {}
    result: dict[int, dict[str, Any]] = {}
    for m in mega_list:
        if not isinstance(m, dict):
            continue
        mid = m.get("id")
        try:
            mid_int = int(mid)
        except Exception:
            continue
        result[mid_int] = m
    return result
