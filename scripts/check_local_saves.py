#!/usr/bin/env python3
"""Run your own Stellaris saves through the companion's real pipeline.

A pre-release check for things synthetic tests can't catch. Each save goes
through the same steps the app uses: the ingestion worker (Rust parser and
extractors), the model briefing, and campaign history (snapshots and events,
in game-date order). The check reports crashes, swallowed errors, and values that
are essentially never legitimately empty.

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
import queue
import sys
import tempfile
import time
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
    errors, warnings = check_briefing(briefing)
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
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
