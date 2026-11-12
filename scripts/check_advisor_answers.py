#!/usr/bin/env python3
"""Ask the real Advisor about your own saves and count what it gets exactly right.

A change to what the Advisor is told can only be judged by what it then says.
For the newest save of each campaign this check builds the briefing the Advisor
is sent, asks questions whose answers are lists in that briefing (the capital's
buildings, the tradition trees taken, a starbase's modules, a leader's traits),
and counts how many of the listed things each answer names exactly as the
player's game shows them. The questions come from the save, so the same command
measures the same thing after every change.

It goes through the app's own ask path with the model you configure, so every
question is one real model call and spends that provider's quota. ``--dry-run``
lists the questions and the number of calls without calling anything.

Answers vary from run to run; a difference of a few names between two runs is
noise. Use ``--runs`` to ask each question more than once.

Everything stays on this machine apart from the model calls the app itself makes.

Examples:
    python3 scripts/check_advisor_answers.py --dry-run
    python3 scripts/check_advisor_answers.py --campaigns 2
    python3 scripts/check_advisor_answers.py --runs 2 --out artifacts/advisor-check
    python3 scripts/check_advisor_answers.py --without-game-names   # a player with no install
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# A save ID shown to the player as it stands: lowercase words joined by underscores.
_RAW_ID = re.compile(r"(?<![A-Za-z0-9_])[a-z][a-z0-9]*(?:_[a-z0-9]+)+(?![A-Za-z0-9_])")


@dataclass
class Case:
    """One question and the things a complete answer names."""

    kind: str
    question: str
    expected: list[str]


@dataclass
class Score:
    exact: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    raw_ids: list[str] = field(default_factory=list)


@dataclass
class Result:
    campaign: str
    kind: str
    question: str
    run: int
    expected: list[str]
    answer: str = ""
    error: str = ""
    seconds: float = 0.0
    score: Score = field(default_factory=Score)


def _distinct(values: Any) -> list[str]:
    """The non-empty strings of a list, once each, in order."""
    if not isinstance(values, list):
        return []
    return list(dict.fromkeys(v.strip() for v in values if isinstance(v, str) and v.strip()))


def _dicts(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _section(briefing: dict[str, Any], *path: str) -> Any:
    value: Any = briefing
    for key in path:
        value = value.get(key) if isinstance(value, dict) else None
    return value


def build_cases(briefing: dict[str, Any]) -> list[Case]:
    """Questions this save can answer, with the names the briefing holds for each.

    ``briefing`` is the model briefing with the installed game's names in it. A
    question is left out when the save has nothing to list for it.
    """
    cases: list[Case] = []

    def add(kind: str, question: str, expected: list[str]) -> None:
        if expected:
            cases.append(Case(kind, question, expected))

    planets = _dicts(_section(briefing, "territory", "planets", "planets"))
    capital = max(
        (p for p in planets if p.get("name") and _distinct(p.get("buildings"))),
        key=lambda p: p.get("population") or 0,
        default=None,
    )
    if capital:
        add(
            "planet_buildings",
            f"What buildings are on {capital['name']} right now? List every one.",
            _distinct(capital.get("buildings")),
        )

    trees = _section(briefing, "progression", "traditions", "by_tree")
    if isinstance(trees, dict):
        add(
            "tradition_trees",
            "Which tradition trees have I adopted so far? List every one.",
            [str(tree) for tree, state in trees.items() if tree != "unknown" and state],
        )

    add(
        "ascension_perks",
        "Which ascension perks have I taken? List every one.",
        _distinct(_section(briefing, "progression", "ascension_perks", "ascension_perks")),
    )

    def fittings(starbase: dict[str, Any]) -> list[str]:
        return _distinct([*(starbase.get("modules") or []), *(starbase.get("buildings") or [])])

    starbase = max(
        (s for s in _dicts(_section(briefing, "defense", "starbases")) if s.get("system_name")),
        key=lambda s: len(fittings(s)),
        default=None,
    )
    if starbase:
        add(
            "starbase_fittings",
            f"What modules and buildings does my starbase in the {starbase['system_name']} "
            "system have? List every one.",
            fittings(starbase),
        )

    leader = max(
        (x for x in _dicts(_section(briefing, "leadership", "leaders")) if x.get("name")),
        key=lambda x: len(_distinct(x.get("traits"))),
        default=None,
    )
    if leader:
        add(
            "leader_traits",
            f"What traits does my leader {leader['name']} have? List every one.",
            _distinct(leader.get("traits")),
        )

    technology_names = _section(briefing, "model_context", "technology", "names") or {}
    in_progress = _section(briefing, "technology", "in_progress") or {}
    researching = [
        technology_names.get(field.get("tech"))
        for field in in_progress.values()
        if isinstance(field, dict)
    ]
    add(
        "current_research",
        "Which technologies am I researching right now?",
        _distinct(researching),
    )

    add(
        "factions",
        "Which factions are there in my empire? List every one by name.",
        _distinct(
            [
                f.get("name")
                for f in _dicts(_section(briefing, "progression", "factions", "factions"))
            ]
        ),
    )
    add(
        "wars",
        "Which wars am I in right now? Give each war's name.",
        _distinct([w.get("name") for w in _dicts(_section(briefing, "situation", "wars"))]),
    )
    return cases


def _words(text: str) -> str:
    """Lowercase letters and digits with single spaces: how two spellings are compared."""
    return " " + " ".join(re.findall(r"[^\W_]+", text.lower())) + " "


def score_answer(answer: str, expected: list[str]) -> Score:
    """Which expected names the answer gives exactly, and which save IDs it shows.

    Case and punctuation are ignored; the words must match. Longer names are
    looked for first and taken out, so "Advanced Research Complexes" in the
    answer does not also count as "Research Complexes".
    """
    remaining = _words(answer)
    found: set[str] = set()
    for name in sorted(dict.fromkeys(expected), key=lambda n: -len(_words(n))):
        words = _words(name)
        if words.strip() and words in remaining:
            found.add(name)
            remaining = remaining.replace(words, " | ")
    ordered = list(dict.fromkeys(expected))
    return Score(
        exact=[name for name in ordered if name in found],
        missing=[name for name in ordered if name not in found],
        raw_ids=sorted(set(_RAW_ID.findall(answer))),
    )


def run_cases(
    campaign: str,
    cases: list[Case],
    ask: Callable[[str], str],
    *,
    runs: int = 1,
    workers: int = 4,
) -> list[Result]:
    """Ask every case ``runs`` times through ``ask`` and score the answers."""

    def one(job: tuple[Case, int]) -> Result:
        case, run = job
        result = Result(campaign, case.kind, case.question, run, case.expected)
        started = time.time()
        try:
            result.answer = ask(case.question)
        except Exception as exc:  # noqa: BLE001 - a failed call is a result, not a crash
            result.error = f"{type(exc).__name__}: {exc}"
        result.seconds = round(time.time() - started, 1)
        result.score = score_answer(result.answer, case.expected)
        return result

    jobs = [(case, run) for case in cases for run in range(runs)]
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        return list(pool.map(one, jobs))


def summarize(results: list[Result]) -> dict[str, dict[str, int]]:
    """Per question kind and in total: names expected, given exactly, IDs shown, errors."""
    summary: dict[str, dict[str, int]] = defaultdict(
        lambda: {"answers": 0, "expected": 0, "exact": 0, "raw_ids": 0, "errors": 0}
    )
    for result in results:
        for key in (result.kind, "total"):
            row = summary[key]
            row["answers"] += 1
            row["errors"] += bool(result.error)
            if not result.error:
                row["expected"] += len(result.score.exact) + len(result.score.missing)
                row["exact"] += len(result.score.exact)
                row["raw_ids"] += len(result.score.raw_ids)
    return dict(summary)


def format_summary(summary: dict[str, dict[str, int]]) -> str:
    lines = [f"{'question':20} {'answers':>7} {'exact names':>14} {'IDs shown':>10} {'errors':>7}"]
    for kind in [*sorted(k for k in summary if k != "total"), "total"]:
        row = summary.get(kind)
        if not row:
            continue
        share = f"{row['exact']}/{row['expected']}"
        percent = f"{100 * row['exact'] / row['expected']:.0f}%" if row["expected"] else "-"
        lines.append(
            f"{kind:20} {row['answers']:>7} {share:>9} {percent:>4} {row['raw_ids']:>10} {row['errors']:>7}"
        )
    return "\n".join(lines)


def _api_key() -> str | None:
    key = os.environ.get("GOOGLE_API_KEY")
    env_file = PROJECT_ROOT / ".env"
    if not key and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("GOOGLE_API_KEY="):
                key = line.split("=", 1)[1].strip().strip("\"'")
    return key or None


def _stored_briefing(save_path: Path) -> dict[str, Any]:
    from stellaris_companion.rust_bridge import session
    from stellaris_save_extractor import SaveExtractor

    with session(str(save_path)):
        return SaveExtractor(str(save_path)).get_complete_briefing()


def _advisor(briefing: dict[str, Any], api_key: str, model: str | None) -> Callable[[str], str]:
    """The app's own ask path for one campaign, as a function from question to answer."""
    from backend.core.companion import DEFAULT_ADVISOR_MODEL, Companion
    from backend.core.json_utils import json_dumps

    companion = Companion(
        save_path=None,
        api_key=api_key,
        auto_precompute=False,
        advisor_model=model or DEFAULT_ADVISOR_MODEL,
    )
    meta = briefing.get("meta") or {}
    companion.apply_precomputed_briefing(
        save_path=None,
        briefing_json=json_dumps(briefing, default=str),
        game_date=meta.get("date"),
        identity=briefing.get("identity"),
        situation=briefing.get("situation"),
        metadata=meta,
    )

    def ask(question: str) -> str:
        reply = companion.ask_precomputed_with_context(
            question=question,
            session_key=f"advisor-check::{time.time_ns()}",
            persist_memory=False,
        )
        return reply.text

    return ask


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("targets", nargs="*", type=Path, help="Save files or campaign folders")
    parser.add_argument("--campaigns", type=int, help="Check only the first N campaigns")
    parser.add_argument("--runs", type=int, default=1, help="Ask each question this many times")
    parser.add_argument("--kinds", help="Only these question kinds, comma-separated")
    parser.add_argument("--model", help="Advisor model (default: the app's default)")
    parser.add_argument(
        "--without-game-names",
        action="store_true",
        help="Send the briefing a player with no installed game gets; score against the game's names",
    )
    parser.add_argument("--dry-run", action="store_true", help="List the questions; call nothing")
    parser.add_argument("--out", type=Path, help="Folder for results.json (answers included)")
    args = parser.parse_args(argv)

    from backend.core.json_utils import json_dumps
    from backend.core.model_briefing import build_model_briefing_json
    from scripts.check_local_saves import discover_saves
    from stellaris_companion import game_names
    from stellaris_companion.save_loader import get_platform_save_paths

    targets = args.targets or [p for p in get_platform_save_paths() if p.exists()]
    campaigns = discover_saves(targets, per_campaign=1)
    if args.campaigns:
        campaigns = dict(list(campaigns.items())[: args.campaigns])
    if not campaigns:
        print("No saves found. Pass a save file or folder.")
        return 2
    if game_names.installed_names() is None:
        print(
            "No installed game found: answers are scored against the save's IDs and the "
            "shipped catalogs, which says less.\n"
        )

    kinds = set(args.kinds.split(",")) if args.kinds else None
    plan: list[tuple[str, dict[str, Any], list[Case]]] = []
    for campaign, paths in campaigns.items():
        stored = _stored_briefing(paths[-1])
        shown = json.loads(build_model_briefing_json(json_dumps(stored, default=str)))
        cases = [case for case in build_cases(shown) if not kinds or case.kind in kinds]
        plan.append((campaign, stored, cases))
        print(f"{campaign[:40]:40} {paths[-1].name:26} {len(cases)} questions")
        if args.dry_run:
            for case in cases:
                print(f"    {case.kind:18} {len(case.expected):3} names  {case.question}")

    calls = sum(len(cases) for _, _, cases in plan) * args.runs
    print(f"\n{calls} model calls ({args.runs} per question).")
    if args.dry_run:
        return 0

    api_key = _api_key()
    if not api_key:
        print("GOOGLE_API_KEY is not set (environment or .env).", file=sys.stderr)
        return 2

    if args.without_game_names:
        game_names.use_names(None)
    results: list[Result] = []
    for campaign, stored, cases in plan:
        ask = _advisor(stored, api_key, args.model)
        done = run_cases(campaign, cases, ask, runs=args.runs)
        results.extend(done)
        for result in done:
            score = result.score
            status = "ERROR" if result.error else f"{len(score.exact)}/{len(result.expected)}"
            print(f"  {campaign[:28]:28} {result.kind:18} run {result.run}  {status}")
            if result.error:
                print(f"      {result.error[:200]}")
            elif score.missing:
                print(f"      not given exactly: {', '.join(score.missing[:8])}")

    summary = summarize(results)
    print("\n" + format_summary(summary))
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "results.json").write_text(
            json.dumps(
                {"summary": summary, "results": [asdict(result) for result in results]},
                indent=1,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(f"\nAnswers written to {args.out / 'results.json'}")
    return 1 if summary.get("total", {}).get("errors") else 0


if __name__ == "__main__":
    raise SystemExit(main())
