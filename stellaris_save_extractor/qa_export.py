"""QA full-export and extraction-health tooling for Stellaris saves.

Produces a single structured export of everything the extractor sees for a save
(every "full" get_* method, plus raw gamestate sections for ground truth), and
audits extraction health with a "silent-failure" smell check.

This targets the Stellaris 4.x ("Pegasus") failure modes tracked upstream in issue
#32, where the data model changed in ways that make the extractor silently return
empty/wrong data rather than raising.

Every surface (CLI script, the ``stellaris-qa-export`` console command, the backend
endpoint, and tests) is a thin wrapper over the functions in this module.
"""

from __future__ import annotations

import os

# A generous cap passed to limit-based extractor methods so the QA export captures
# everything rather than the LLM-facing top-k slice.
_FULL = 1_000_000

# Every "full" extractor method to dump, with the kwargs that maximise coverage.
# Deliberately uses get_species_full (not the trimmed get_species_for_briefing) and
# large limits. One (method_name, kwargs) tuple per section; a method that needs no
# args gets {}.
EXPORT_METHODS: list[tuple[str, dict]] = [
    ("get_metadata", {}),
    ("get_missing_dlcs", {}),
    ("get_player_status", {}),
    ("get_empire_identity", {}),
    ("get_active_policies", {}),
    ("get_naval_capacity", {}),
    ("get_traditions", {}),
    ("get_ascension_perks", {}),
    ("get_relics", {}),
    ("get_situation", {}),
    ("get_resources", {}),
    ("get_pop_statistics", {}),
    ("get_market", {"top_n": _FULL}),
    ("get_trade_value", {}),
    ("get_budget_breakdown", {"top_n_sources": _FULL}),
    ("get_wars", {}),
    ("get_fleets", {}),
    ("get_fleet_composition", {"limit": _FULL}),
    ("get_starbases", {}),
    ("get_megastructures", {}),
    ("get_armies", {}),
    ("get_diplomacy", {}),
    ("get_federation_details", {}),
    ("get_subjects", {"limit": _FULL}),
    ("get_fallen_empires", {}),
    ("get_espionage", {"limit": _FULL}),
    ("get_claims", {}),
    ("get_crisis_status", {}),
    ("get_lgate_status", {}),
    ("get_menace", {}),
    ("get_great_khan", {}),
    ("get_leaders", {}),
    ("get_strategic_geography", {}),
    ("get_leviathans", {}),
    ("get_planets", {}),
    ("get_archaeology", {"limit": _FULL}),
    ("get_special_projects", {}),
    ("get_species_full", {}),
    ("get_species_rights", {}),
    ("get_factions", {"limit": _FULL}),
    ("get_technology", {}),
]

# Raw gamestate sections to pull for ground-truth entry counts (and, with
# --include-raw, the full dump). Section names match what the extractor itself
# requests from the Rust bridge.
RAW_SECTIONS: list[str] = [
    "country",
    "fleet",
    "ships",
    "planets",
    "pop_groups",
    "pop_factions",
    "species_db",
    "war",
    "leaders",
    "megastructures",
    "starbase_mgr",
    "galactic_object",
]

# Silent-failure smell rules: if the extracted collection is empty while the raw
# section has entries, flag it. Each rule maps (method_name, key) -> raw section.
SMELL_RULES: list[dict] = [
    {"name": "fleets", "extracted": ("get_fleets", "fleets"), "raw_section": "fleet"},
    {"name": "leaders", "extracted": ("get_leaders", "leaders"), "raw_section": "leaders"},
    {"name": "wars", "extracted": ("get_wars", "wars"), "raw_section": "war"},
    {
        "name": "pops",
        "extracted": ("get_pop_statistics", "total_pops"),
        "raw_section": "pop_groups",
    },
]


def collect_extraction(extractor, methods) -> dict:
    """Call each registered extractor method, capturing results and errors.

    Args:
        extractor: A ``SaveExtractor`` (or compatible double) to call methods on.
        methods: Iterable of ``(method_name, kwargs)`` tuples.

    Returns:
        Dict keyed by method name. A method that raises is recorded as
        ``{"__error__": "<repr>"}`` rather than propagating — a crashing extractor
        is itself a finding, not a reason to abort the whole export.
    """
    result: dict = {}
    for method_name, kwargs in methods:
        try:
            fn = getattr(extractor, method_name)
            result[method_name] = fn(**(kwargs or {}))
        except Exception as exc:  # noqa: BLE001 - capturing is the point
            result[method_name] = {"__error__": repr(exc)}
    return result


def _count(value) -> int:
    """Best-effort count: ints pass through, list/dict give length, else 0.

    Ints let a rule target a scalar total (e.g. pop_statistics.total_pops) and let
    run_full_export feed the smell check a ``{section: count}`` mapping.
    """
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, (list, dict)):
        return len(value)
    return 0


def evaluate_smell(extraction: dict, raw_sections: dict, rules) -> list[dict]:
    """Flag extractor sections that look silently broken.

    A rule is a dict ``{"name", "extracted": (method_name, key), "raw_section"}``.
    If the extracted collection is empty while the raw gamestate section has
    entries, that is a strong signal of a Stellaris-version data-model break
    (flag/enum rename or split id-space) — the issue #32 failure modes.

    Returns:
        A list of flag dicts (empty when nothing looks broken).
    """
    flags: list[dict] = []
    for rule in rules:
        method_name, key = rule["extracted"]
        section = extraction.get(method_name)
        extracted = section.get(key) if isinstance(section, dict) else None
        extracted_count = _count(extracted)
        raw_count = _count(raw_sections.get(rule["raw_section"]))
        if extracted_count == 0 and raw_count > 0:
            flags.append(
                {
                    "name": rule["name"],
                    "extracted_count": extracted_count,
                    "raw_count": raw_count,
                    "message": (
                        f"'{rule['name']}' extracted 0 entries but raw section "
                        f"'{rule['raw_section']}' has {raw_count} — possible extractor "
                        f"break (flag/enum rename or split id-space)."
                    ),
                }
            )
    return flags


def _json_safe(obj):
    """Recursively coerce an export tree into JSON-serialisable form.

    Sets/tuples become lists; bytes decode; anything else json can't handle falls
    back to ``str`` so a single odd value never breaks the whole dump.
    """
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (set, frozenset)):
        # Sets have no stable order — sort so exports are deterministic (baselines).
        return [_json_safe(v) for v in sorted(obj, key=lambda x: (str(type(x)), str(x)))]
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, bytes):
        return obj.decode("utf-8", "replace")
    return str(obj)


def _tool_version() -> str | None:
    try:
        from importlib.metadata import version

        return version("stellaris-companion")
    except Exception:  # noqa: BLE001
        return None


def _apply_player_override(player_name, player_country_id) -> dict:
    """Set player-selection env vars, returning previous values for restoration."""
    prev: dict = {}
    for key, value in (
        ("STELLARIS_PLAYER_NAME", player_name),
        ("STELLARIS_PLAYER_COUNTRY_ID", player_country_id),
    ):
        if value is not None:
            prev[key] = os.environ.get(key)
            os.environ[key] = str(value)
    return prev


def _restore_env(prev: dict) -> None:
    for key, value in prev.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _build_metadata(extractor, save_path, exported_at, player_name, player_country_id) -> dict:
    md: dict = {
        "save_path": str(save_path),
        "exported_at": exported_at,
        "tool_version": _tool_version(),
    }
    # These may not exist on older extractor versions (e.g. before the MP-selection
    # work lands) — probe defensively so the export works either way.
    for out_key, method in (
        ("player_id", "get_player_empire_id"),
        ("empire_name", "get_player_empire_name"),
        ("is_multiplayer", "is_multiplayer_save"),
    ):
        fn = getattr(extractor, method, None)
        if callable(fn):
            try:
                md[out_key] = fn()
            except Exception as exc:  # noqa: BLE001
                md[out_key] = {"__error__": repr(exc)}
    if player_name is not None:
        md["override_player_name"] = player_name
    if player_country_id is not None:
        md["override_player_country_id"] = player_country_id
    return md


def _collect_raw(section_names) -> dict:
    """Pull raw gamestate sections via the active Rust session."""
    from stellaris_companion.rust_bridge import _get_active_session

    session = _get_active_session()
    if session is None:
        return {}
    try:
        raw = session.extract_sections(list(section_names))
    except Exception as exc:  # noqa: BLE001
        return {"__error__": repr(exc)}
    # extract_sections returns an envelope with extra keys (game, schema_version,
    # tool_version, ...); keep only the sections we asked for.
    return {name: raw[name] for name in section_names if name in raw}


def _run_validation(save_path) -> dict:
    try:
        from .validation import ExtractionValidator

        report = ExtractionValidator(str(save_path)).validate_all()
        if hasattr(report, "to_dict"):
            report = report.to_dict()
        return report
    except Exception as exc:  # noqa: BLE001
        return {"__error__": repr(exc)}


def run_full_export(
    save_path,
    *,
    include_raw: bool = False,
    include_audit: bool = True,
    player_name=None,
    player_country_id=None,
    exported_at=None,
    methods=None,
    raw_sections=None,
    smell_rules=None,
) -> dict:
    """Produce the complete QA export for a save.

    Args:
        save_path: Path to the ``.sav`` file.
        include_raw: Also embed the full raw gamestate sections (large). Entry
            counts are always included regardless.
        include_audit: Run the validator + smell check.
        player_name / player_country_id: Optional MP empire override (applied via
            env for the extractor's selection logic).
        exported_at: Timestamp string to stamp into metadata (caller supplies it;
            this module never reads the clock, to stay deterministic).

    Returns:
        A JSON-serialisable dict with ``metadata``, ``extraction``, ``raw_counts``,
        optional ``raw_sections``, and optional ``audit`` ({validation, smell}).
    """
    from stellaris_companion.rust_bridge import session as rust_session

    from .extractor import SaveExtractor

    methods = methods if methods is not None else EXPORT_METHODS
    section_names = raw_sections if raw_sections is not None else RAW_SECTIONS
    rules = smell_rules if smell_rules is not None else SMELL_RULES

    prev_env = _apply_player_override(player_name, player_country_id)
    try:
        with rust_session(save_path):
            extractor = SaveExtractor(str(save_path))
            extraction = collect_extraction(extractor, methods)
            raw = _collect_raw(section_names)
            raw_counts = {k: _count(v) for k, v in raw.items()}
            export: dict = {
                "metadata": _build_metadata(
                    extractor, save_path, exported_at, player_name, player_country_id
                ),
                "extraction": extraction,
                "raw_counts": raw_counts,
            }
            if include_raw:
                export["raw_sections"] = raw
            if include_audit:
                export["audit"] = {
                    "validation": _run_validation(save_path),
                    "smell": evaluate_smell(extraction, raw_counts, rules),
                }
    finally:
        _restore_env(prev_env)

    return _json_safe(export)


def baseline_payload(export: dict) -> dict:
    """Map baseline filename -> content for regression snapshotting.

    One ``<method>.json`` per extracted section, plus ``_raw_counts.json`` and
    ``_smell.json``. Volatile metadata (exported_at, tool_version, save_path) and
    the validation report are deliberately excluded so baselines stay stable across
    machines and runs.
    """
    payload: dict = {}
    for method, result in export.get("extraction", {}).items():
        payload[f"{method}.json"] = result
    payload["_raw_counts.json"] = export.get("raw_counts", {})
    if "audit" in export:
        payload["_smell.json"] = export["audit"].get("smell", [])
    return payload


# Fields that vary by machine/path/run and must not cause baseline drift.
_VOLATILE_KEYS = frozenset(
    {"file_path", "modified", "save_path", "exported_at", "tool_version", "gamestate_loaded"}
)


def _canonical(value):
    """Normalise for order-insensitive, machine-independent comparison.

    Recursively sorts dict keys and list elements (some extractor sections build
    lists by iterating sets, so element order varies across processes) and drops
    volatile fields (file_path, modified, timestamps) that would otherwise cause
    spurious drift.
    """
    import json

    if isinstance(value, dict):
        return {k: _canonical(value[k]) for k in sorted(value) if k not in _VOLATILE_KEYS}
    if isinstance(value, list):
        return sorted(
            (_canonical(v) for v in value),
            key=lambda x: json.dumps(x, sort_keys=True),
        )
    return value


def write_baselines(export: dict, baseline_dir: str) -> list[str]:
    """Write the baseline payload for ``export`` into ``baseline_dir``."""
    import json
    import os

    os.makedirs(baseline_dir, exist_ok=True)
    payload = baseline_payload(export)
    for name, content in payload.items():
        # Store the canonical form (sorted, volatile fields stripped) so committed
        # baselines are stable and path-independent.
        with open(os.path.join(baseline_dir, name), "w", encoding="utf-8") as fh:
            json.dump(_canonical(content), fh, indent=2, sort_keys=True)
    return sorted(payload)


def compare_baselines(export: dict, baseline_dir: str) -> list[str]:
    """Return baseline filenames that are missing or differ from ``export``."""
    import json
    import os

    payload = baseline_payload(export)
    mismatches: list[str] = []
    for name, content in payload.items():
        path = os.path.join(baseline_dir, name)
        if not os.path.exists(path):
            mismatches.append(name)
            continue
        with open(path, encoding="utf-8") as fh:
            baseline = json.load(fh)
        if _canonical(baseline) != _canonical(content):
            mismatches.append(name)
    return mismatches


def _now_iso() -> str:
    """Wall-clock timestamp for the export header (CLI-only; kept out of
    run_full_export so exports stay deterministic for baselines)."""
    import datetime

    return datetime.datetime.now().isoformat(timespec="seconds")


def main(argv=None) -> int:
    """CLI entry point for ``stellaris-qa-export`` / ``python -m``."""
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(
        prog="stellaris-qa-export",
        description="Full structured QA export + extraction-health audit for a Stellaris save.",
    )
    parser.add_argument("save_path", nargs="?", help="Path to a .sav (default: most recent save).")
    parser.add_argument("-o", "--output", help="Write JSON to this file (default: stdout).")
    parser.add_argument(
        "--raw", action="store_true", help="Embed full raw gamestate sections (large)."
    )
    parser.add_argument("--no-audit", action="store_true", help="Skip the validator + smell check.")
    parser.add_argument("--player-name", help="MP empire override: match by player name.")
    parser.add_argument("--player-country-id", help="MP empire override: explicit country id.")
    parser.add_argument("--indent", type=int, default=2, help="JSON indent (default: 2).")
    parser.add_argument(
        "--update-baselines",
        metavar="DIR",
        help="Write per-section regression baselines into DIR instead of dumping JSON.",
    )
    args = parser.parse_args(argv)

    save_path = args.save_path
    if not save_path:
        from stellaris_companion.save_loader import find_most_recent_save

        save_path = find_most_recent_save()
        if not save_path:
            print("[qa-export] No save file found.", file=sys.stderr)
            return 2

    export = run_full_export(
        save_path,
        include_raw=args.raw,
        include_audit=not args.no_audit,
        player_name=args.player_name,
        player_country_id=args.player_country_id,
        exported_at=_now_iso(),
    )

    if args.update_baselines:
        written = write_baselines(export, args.update_baselines)
        print(
            f"[qa-export] wrote {len(written)} baseline files to {args.update_baselines}",
            file=sys.stderr,
        )
        return 0

    text = json.dumps(export, indent=args.indent, sort_keys=True)
    if args.output:
        from pathlib import Path

        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)

    smell = export.get("audit", {}).get("smell", []) if isinstance(export, dict) else []
    section_count = len(export.get("extraction", {})) if isinstance(export, dict) else 0
    print(
        f"[qa-export] {section_count} extraction sections; {len(smell)} smell flag(s)"
        + (" ⚠" if smell else ""),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
