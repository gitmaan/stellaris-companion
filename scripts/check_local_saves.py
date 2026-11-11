#!/usr/bin/env python3
"""Run your own Stellaris saves through the companion's real pipeline.

A pre-release check for things synthetic tests can't catch. Each save goes
through the same steps the app uses: the ingestion worker (Rust parser and
extractors), the model briefing, and campaign history (snapshots and events,
in game-date order). The check reports crashes, swallowed errors, and values that
are essentially never legitimately empty. It also fails when the installed game
or a save is newer than the shipped name catalogs, which otherwise go stale
without anyone noticing.

Everything stays on this machine: saves are read in place, history goes into a
temporary database that is deleted afterwards, and nothing is uploaded.

Examples:
    python3 scripts/check_local_saves.py               # newest 2 saves per campaign
    python3 scripts/check_local_saves.py --all         # every save
    python3 scripts/check_local_saves.py path/to/campaign_dir path/to/one.sav
    python3 scripts/check_local_saves.py --json /tmp/save-check.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import queue
import sys
import tempfile
import time
import zipfile
from collections import defaultdict
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@dataclass
class SaveResult:
    path: Path
    campaign: str
    empire: str = ""
    date: str = ""
    version: str = ""
    seconds: float = 0.0
    briefing_kb: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    briefing: dict[str, Any] | None = None
    payload: dict[str, Any] | None = None


class _Collector(logging.Handler):
    """Collect warnings the pipeline logs and otherwise swallows."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def discover_saves(targets: list[Path], *, per_campaign: int | None) -> dict[str, list[Path]]:
    """Group saves by campaign folder, newest last, keeping `per_campaign` newest."""
    groups: dict[str, list[Path]] = defaultdict(list)
    for target in targets:
        if target.is_file() and target.suffix == ".sav":
            groups[target.parent.name].append(target)
            continue
        if not target.is_dir():
            continue
        direct = [p for p in target.glob("*.sav") if p.is_file()]
        if direct:
            groups[target.name].extend(direct)
        for child in target.iterdir():
            if child.is_dir() and not child.name.startswith("_"):
                groups[child.name].extend(p for p in child.glob("*.sav") if p.is_file())
    result = {}
    for campaign, paths in groups.items():
        unique = sorted(set(paths), key=lambda p: (p.stat().st_mtime, p.name))
        result[campaign] = unique[-per_campaign:] if per_campaign else unique
    return dict(sorted(result.items()))


def check_briefing(briefing: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for values a real campaign always has."""
    errors: list[str] = []
    warnings: list[str] = []
    meta = briefing.get("meta") if isinstance(briefing.get("meta"), dict) else {}
    identity = briefing.get("identity") if isinstance(briefing.get("identity"), dict) else {}
    if not str(meta.get("date") or "").strip():
        errors.append("Game date is missing.")
    if not str(meta.get("empire_name") or "").strip():
        errors.append("Empire name is blank.")
    if not str(meta.get("version") or "").strip():
        warnings.append("Game version is missing.")
    if not identity:
        errors.append("Empire identity is missing.")
    elif identity.get("is_nomadic") is None:
        warnings.append("Couldn't tell whether the empire is Nomadic.")
    territory = briefing.get("territory") if isinstance(briefing.get("territory"), dict) else {}
    colonies = territory.get("colonies") if isinstance(territory.get("colonies"), dict) else {}
    if colonies.get("total_count") == 0 and identity.get("is_nomadic") is not True:
        warnings.append("Colony count is 0.")
    for section in ("economy", "military", "diplomacy", "technology"):
        value = briefing.get(section)
        if not isinstance(value, dict) or not value:
            errors.append(f"Briefing section '{section}' is empty.")
    if not isinstance(briefing.get("history"), dict) or not briefing.get("history"):
        warnings.append("History enrichment is empty.")
    return errors, warnings


_REGENERATE = (
    "Regenerate them: python3 scripts/generate_identity_catalog.py --game-dir <Stellaris install>"
)


def default_game_dirs() -> list[Path]:
    """Where a Steam install of Stellaris usually lives, plus STELLARIS_GAME_DIR."""
    home = Path.home()
    candidates = [
        home / "Library/Application Support/Steam/steamapps/common/Stellaris",
        Path("C:/Program Files (x86)/Steam/steamapps/common/Stellaris"),
        home / ".steam/steam/steamapps/common/Stellaris",
        home / ".local/share/Steam/steamapps/common/Stellaris",
    ]
    override = os.environ.get("STELLARIS_GAME_DIR")
    return [Path(override)] if override else candidates


def installed_game_version(game_dirs: list[Path]) -> str | None:
    for game_dir in game_dirs:
        try:
            settings = json.loads(
                (game_dir.expanduser() / "launcher-settings.json").read_text(encoding="utf-8-sig")
            )
        except (OSError, ValueError):
            continue
        version = settings.get("version") if isinstance(settings, dict) else None
        if isinstance(version, str) and version.strip():
            return version.strip()
    return None


def check_installed_game(game_dirs: list[Path]) -> str | None:
    """Return a problem if the installed game is newer than the name catalogs."""
    from stellaris_companion.technology_names import (
        TECHNOLOGY_CATALOG_GAME_VERSION,
        catalog_covers_game_version,
    )

    installed = installed_game_version(game_dirs)
    if installed is None or catalog_covers_game_version(installed) is not False:
        return None
    return (
        f"Installed game is {installed}, but the name catalogs are from "
        f"{TECHNOLOGY_CATALOG_GAME_VERSION}. {_REGENERATE}"
    )


def check_game_vocabulary(game_dirs: list[Path]) -> list[str]:
    """Country types and flags the extractors look for that the installed game lacks."""
    from stellaris_save_extractor.game_vocabulary import missing_from_game

    for game_dir in game_dirs:
        if (game_dir / "common" / "country_types").is_dir():
            return missing_from_game(game_dir)
    return []


def check_name_catalogs(briefing: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) about names the catalogs cannot supply for this save."""
    from stellaris_companion.technology_names import (
        TECHNOLOGY_CATALOG_GAME_VERSION,
        catalog_covers_game_version,
        technology_display_name,
    )

    errors: list[str] = []
    warnings: list[str] = []
    meta = briefing.get("meta") if isinstance(briefing.get("meta"), dict) else {}
    version = str(meta.get("version") or "").strip()
    if catalog_covers_game_version(version) is False:
        errors.append(
            f"Save is from {version}, newer than the name catalogs "
            f"({TECHNOLOGY_CATALOG_GAME_VERSION}). {_REGENERATE}"
        )
    technology = briefing.get("technology") if isinstance(briefing.get("technology"), dict) else {}
    identifiers: list[Any] = list(technology.get("researched_techs") or [])
    for group in (technology.get("in_progress"), technology.get("available_techs")):
        for value in (group or {}).values() if isinstance(group, dict) else ():
            identifiers += [value.get("tech")] if isinstance(value, dict) else list(value or [])
    unnamed = sorted(
        {i for i in identifiers if isinstance(i, str) and i and not technology_display_name(i)}
    )
    if unnamed:
        sample = ", ".join(unnamed[:5])
        warnings.append(
            f"{len(unnamed)} technology IDs have no catalog name (modded, or newer than "
            f"the catalog): {sample}"
        )
    return errors, warnings


def check_events(events: list[dict[str, Any]]) -> list[str]:
    """Flag event history that couldn't come from one campaign played forward."""
    warnings = []
    counts: dict[str, int] = defaultdict(int)
    for event in events:
        counts[str(event.get("event_type"))] += 1
    for event_type, count in counts.items():
        if count > 200:
            warnings.append(f"{count} '{event_type}' events between two saves looks spurious.")
    return warnings


def check_parser(save_path: Path) -> list[str]:
    """Compare what the parser returns with an independent reading of the save text.

    Every key and value in the save must be present in the parser's output,
    including keys the save repeats. This catches parser changes that silently
    drop data, whatever the extractors do with it afterwards.
    """
    from stellaris_companion.rust_bridge import session
    from stellaris_save_extractor.clausewitz_reference import differences, parse

    with zipfile.ZipFile(save_path) as archive:
        expected = parse(archive.read("gamestate").decode("utf-8", errors="replace"))
    problems: list[str] = []
    sections = list(expected)
    with session(save_path) as active:
        for start in range(0, len(sections), 8):
            chunk = sections[start : start + 8]
            parsed = active.extract_sections(chunk)
            for section in chunk:
                if section not in parsed:
                    problems.append(f"{section}: section missing from parser output")
                else:
                    problems += differences(expected[section], parsed[section], section)
    shown = [f"Parser differs from the save text: {line}"[:300] for line in problems[:5]]
    if len(problems) > len(shown):
        shown.append(f"Parser differs from the save text in {len(problems)} or more places")
    return shown


def ingest(save_path: Path, collector: _Collector) -> SaveResult:
    from backend.core import ingestion_worker
    from backend.core.model_briefing import build_model_briefing

    result = SaveResult(path=save_path, campaign=save_path.parent.name)
    collector.records.clear()
    started = time.perf_counter()
    out: queue.Queue = queue.Queue()
    job = {"tier": "t2", "save_path": str(save_path), "requested_at": 0.0}
    try:
        ingestion_worker._process_main(job, out)  # type: ignore[arg-type]
        message = out.get_nowait()
    except Exception as exc:  # noqa: BLE001 - report every failure
        message = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    result.seconds = time.perf_counter() - started
    if not message.get("ok"):
        result.errors.append(f"Ingestion failed: {message.get('error')}")
        return result

    payload = message["payload"]
    briefing = json.loads(payload["briefing_json"])
    meta = briefing.get("meta") or {}
    result.payload, result.briefing = payload, briefing
    result.empire = str(meta.get("empire_name") or "")
    result.date = str(meta.get("date") or "")
    result.version = str(meta.get("version") or "")
    for errors, warnings in (check_briefing(briefing), check_name_catalogs(briefing)):
        result.errors += errors
        result.warnings += warnings
    try:
        model = build_model_briefing(briefing)
        result.briefing_kb = round(len(json.dumps(model, default=str)) / 1024)
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"Model briefing failed: {type(exc).__name__}: {exc}")
    for record in collector.records:
        text = f"Logged {record.levelname.lower()}: {record.getMessage()}"[:300]
        (result.errors if is_swallowed_failure(record) else result.warnings).append(text)
    try:
        result.errors += check_parser(save_path)
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"Parser cross-check failed: {type(exc).__name__}: {exc}")
    return result


def is_swallowed_failure(record: logging.LogRecord) -> bool:
    """The pipeline logs some failures as warnings and carries on without that data."""
    message = record.getMessage().lower()
    return (
        record.levelno >= logging.ERROR
        or record.exc_info is not None
        or "error" in message
        or "failed" in message
    )


def replay_history(results: list[SaveResult], db_path: Path) -> tuple[int, list[str]]:
    """Store snapshots in game-date order and return (event count, problems)."""
    from backend.core.database import GameDatabase
    from backend.core.history import record_snapshot_from_briefing

    problems: list[str] = []
    ordered = sorted((r for r in results if r.briefing), key=lambda r: r.date)
    session_id = None
    with closing(GameDatabase(db_path)) as db:
        for item in ordered:
            try:
                _, _, session_id = record_snapshot_from_briefing(
                    db=db,
                    save_path=str(item.path),
                    save_hash=item.payload.get("save_hash") if item.payload else None,
                    briefing=item.briefing,
                    briefing_json=item.payload["briefing_json"] if item.payload else None,
                )
            except Exception as exc:  # noqa: BLE001
                problems.append(f"Storing {item.path.name} failed: {type(exc).__name__}: {exc}")
        events = db.get_recent_events(session_id=session_id, limit=5000) if session_id else []
    return len(events), problems + check_events(events)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("targets", nargs="*", type=Path, help="Save files or folders")
    parser.add_argument(
        "--all", action="store_true", help="Check every save, not just 2 per campaign"
    )
    parser.add_argument("--json", type=Path, help="Also write a summary (no save contents) here")
    parser.add_argument(
        "--game-dir", type=Path, help="Stellaris install to compare the name catalogs against"
    )
    args = parser.parse_args(argv)

    from stellaris_companion.save_loader import get_platform_save_paths

    targets = args.targets or [p for p in get_platform_save_paths() if p.exists()]
    campaigns = discover_saves(targets, per_campaign=None if args.all else 2)
    if not campaigns:
        print("No saves found. Pass a save file or folder.")
        return 2

    logging.basicConfig(level=logging.WARNING)
    collector = _Collector()
    logging.getLogger().addHandler(collector)
    # The worker raises its own logging to DEBUG; keep only what matters here.
    logging.basicConfig = lambda **kwargs: None  # type: ignore[assignment]

    game_dirs = [args.game_dir] if args.game_dir else default_game_dirs()
    stale_catalogs = check_installed_game(game_dirs)
    if stale_catalogs:
        print(f"FAIL name catalogs: {stale_catalogs}\n")
    unknown_names = check_game_vocabulary(game_dirs)
    if unknown_names:
        print(
            "FAIL game vocabulary: the installed game never defines or sets "
            f"{', '.join(unknown_names)}. See stellaris_save_extractor/game_vocabulary.py.\n"
        )

    summary: list[dict[str, Any]] = []
    failed = 0
    with tempfile.TemporaryDirectory(prefix="save-check-") as tmp:
        for index, (campaign, paths) in enumerate(campaigns.items()):
            results = [ingest(path, collector) for path in paths]
            event_count, history_problems = replay_history(results, Path(tmp) / f"{index}.db")
            for r in results:
                status = "FAIL" if r.errors else ("warn" if r.warnings else "ok")
                failed += bool(r.errors)
                print(
                    f"{status:4} {r.campaign[:28]:28} {r.date:10} {r.version[:18]:18} "
                    f"{r.seconds:5.1f}s {r.briefing_kb:4}KB  {r.empire[:30]}"
                )
                for line in r.errors:
                    print(f"       error: {line}")
                for line in r.warnings:
                    print(f"       warn:  {line}")
                summary.append(
                    {
                        "campaign": r.campaign,
                        "save": r.path.name,
                        "date": r.date,
                        "version": r.version,
                        "seconds": round(r.seconds, 2),
                        "model_briefing_kb": r.briefing_kb,
                        "errors": r.errors,
                        "warnings": r.warnings,
                    }
                )
            if len(results) > 1:
                print(f"     history: {event_count} events across {len(results)} saves")
            for line in history_problems:
                failed += line.startswith("Storing")
                print(f"     history: {line}")

    total = len(summary)
    print(f"\n{total - failed}/{total} saves passed." if failed else f"\nAll {total} saves passed.")
    if args.json:
        args.json.write_text(json.dumps(summary, indent=2))
    return 1 if failed or stale_catalogs or unknown_names else 0


if __name__ == "__main__":
    raise SystemExit(main())
