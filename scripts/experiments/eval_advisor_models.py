#!/usr/bin/env python3
"""Compare advisor responses across Gemini routing models on a real save."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.companion import DEFAULT_ADVISOR_MODEL, Companion
from backend.core.json_utils import json_dumps
from stellaris_companion.rust_bridge import session
from stellaris_save_extractor import SaveExtractor


@dataclass
class EvalCase:
    name: str
    category: str
    question: str
    notes: str
    required_all: list[str] = field(default_factory=list)
    required_any_groups: list[list[str]] = field(default_factory=list)
    forbidden: list[str] = field(default_factory=list)


@dataclass
class CaseResult:
    name: str
    category: str
    question: str
    notes: str
    model: str
    ok: bool
    issues: list[str]
    elapsed_s: float
    response: str
    response_chars: int
    stats: dict[str, Any]


def _save_number_patterns(value: int | float) -> list[str]:
    rounded_int = int(round(float(value)))
    compact_k = float(value) / 1000.0
    compact_text = re.escape(f"{compact_k:.1f}")
    return [
        rf"\b{rounded_int}\b",
        rf"\b{rounded_int:,}\b".replace(",", "[, ]?"),
        rf"\b{compact_text}\s*k\b",
        rf"\babout {compact_text}\s*k\b",
        rf"\broughly {compact_text}\s*k\b",
    ]


def build_cases(briefing: dict[str, Any]) -> list[EvalCase]:
    meta = briefing.get("meta") or {}
    identity = briefing.get("identity") or {}
    economy = briefing.get("economy") or {}
    military = briefing.get("military") or {}

    empire_name = str(identity.get("empire_name") or meta.get("empire_name") or "the empire")
    game_date = str(meta.get("date") or "unknown")

    net_monthly = economy.get("net_monthly") or {}
    top_resource_name = None
    top_resource_value = None
    if isinstance(net_monthly, dict) and net_monthly:
        top_resource_name, top_resource_value = max(
            net_monthly.items(),
            key=lambda item: float(item[1] or 0.0),
        )

    pop_total = ((economy.get("pop_statistics") or {}).get("total_pops")) or 0

    naval_capacity = military.get("naval_capacity") or {}
    naval_analysis = naval_capacity.get("analysis") or {}
    derived_limit = naval_analysis.get("limit") or naval_analysis.get("derived_limit")
    over_by = naval_analysis.get("over_by")
    if over_by is None:
        over_by = naval_analysis.get("derived_over_by")

    cases: list[EvalCase] = [
        EvalCase(
            name="save_empire_name",
            category="save_facts",
            question="What empire am I playing right now?",
            notes=f"Should identify the empire as {empire_name}.",
            required_all=[re.escape(empire_name)],
        ),
        EvalCase(
            name="save_game_date",
            category="save_facts",
            question="What is the current game date in this save?",
            notes=f"Should report the current date as {game_date}.",
            required_all=[re.escape(game_date)],
        ),
        EvalCase(
            name="save_total_pops",
            category="save_facts",
            question="Roughly how many pops do I currently have empire-wide?",
            notes=f"Should stay near {int(pop_total):,} total pops.",
            required_any_groups=[_save_number_patterns(pop_total)],
        ),
        EvalCase(
            name="save_top_surplus",
            category="save_facts",
            question="Which resource is my strongest monthly surplus right now?",
            notes=(
                f"Should point to {top_resource_name} as the biggest monthly surplus."
                if top_resource_name
                else "Should identify the strongest monthly surplus from the save."
            ),
            required_all=[re.escape(str(top_resource_name or ""))] if top_resource_name else [],
        ),
        EvalCase(
            name="save_naval_cap",
            category="save_facts",
            question="Am I over naval cap right now, and by how much?",
            notes=(
                f"Should say the empire is over naval cap, using the current {naval_capacity.get('used')} / {derived_limit} picture."
            ),
            required_any_groups=[
                [r"\bover naval cap\b", r"\bover naval capacity\b", r"\bover\b"],
                [rf"\b{int(over_by)}\b"] if over_by is not None else [],
            ],
            required_all=[rf"\b{int(derived_limit)}\b"] if derived_limit is not None else [],
        ),
        EvalCase(
            name="mechanics_workforce",
            category="mechanics",
            question="In Stellaris 4.3, how many pops do I usually need to fill one job?",
            notes="Should explain the 4.x workforce rule: roughly 100 pops per job, not 1 pop per job.",
            required_any_groups=[[r"\b100\b", r"\bone hundred\b"]],
            forbidden=[r"\b1 pop\b.*\b1 job\b", r"\bone pop\b.*\bone job\b"],
        ),
        EvalCase(
            name="mechanics_market_currency",
            category="mechanics",
            question="What resource is the main currency for the Galactic Market in this version?",
            notes="Should say Trade is the market currency and avoid saying Energy is the primary currency.",
            required_all=[r"\btrade\b"],
            forbidden=[r"\benergy is the .*currency\b", r"\bprimary currency.*energy\b"],
        ),
        EvalCase(
            name="mechanics_corvette_capacity",
            category="mechanics",
            question="How many corvettes fit into 100 naval capacity in Stellaris 4.3?",
            notes="Should answer 20 corvettes.",
            required_any_groups=[[r"\b20\b", r"\btwenty\b"]],
        ),
        EvalCase(
            name="mechanics_branch_office",
            category="mechanics",
            question="Do branch offices use Energy or Trade to get established in this version?",
            notes="Should say branch offices use Trade rather than Energy.",
            required_all=[r"\btrade\b"],
            forbidden=[r"\buse energy\b", r"\bestablished.*energy\b"],
        ),
        EvalCase(
            name="mechanics_colony_threshold",
            category="mechanics",
            question="When is a new colony considered established in Stellaris 4.3?",
            notes="Should mention the 100-pop establishment threshold.",
            required_any_groups=[[r"\b100\b", r"\bone hundred\b"]],
        ),
    ]
    return cases


def evaluate_answer(case: EvalCase, answer: str) -> list[str]:
    issues: list[str] = []
    normalized = answer or ""

    for pattern in case.required_all:
        if pattern and re.search(pattern, normalized, re.IGNORECASE) is None:
            issues.append(f"missing required pattern: {pattern}")

    for group in case.required_any_groups:
        if group and not any(re.search(pattern, normalized, re.IGNORECASE) for pattern in group):
            issues.append(f"missing any-of group: {' | '.join(group)}")

    for pattern in case.forbidden:
        if pattern and re.search(pattern, normalized, re.IGNORECASE):
            issues.append(f"matched forbidden pattern: {pattern}")

    return issues


def load_briefing(save_path: Path) -> dict[str, Any]:
    with session(str(save_path)):
        extractor = SaveExtractor(str(save_path))
        return extractor.get_complete_briefing()


def build_companion(save_path: Path, api_key: str, briefing: dict[str, Any]) -> Companion:
    companion = Companion(
        save_path=None,
        api_key=api_key,
        auto_precompute=False,
        advisor_model=DEFAULT_ADVISOR_MODEL,
    )
    meta = briefing.get("meta") or {}
    companion.apply_precomputed_briefing(
        save_path=save_path,
        briefing_json=json_dumps(briefing, default=str),
        game_date=meta.get("date"),
        identity=briefing.get("identity"),
        situation=briefing.get("situation"),
        metadata=meta,
    )
    return companion


def run_case(companion: Companion, case: EvalCase, model: str) -> CaseResult:
    session_key = f"eval::{model}::{case.name}::{int(time.time() * 1000)}"
    answer, elapsed = companion.ask_precomputed(
        question=case.question,
        session_key=session_key,
        model_name=model,
    )
    stats = companion.get_call_stats()
    issues = evaluate_answer(case, answer)
    return CaseResult(
        name=case.name,
        category=case.category,
        question=case.question,
        notes=case.notes,
        model=model,
        ok=not issues and not answer.startswith("Error:"),
        issues=issues,
        elapsed_s=elapsed,
        response=answer,
        response_chars=len(answer),
        stats=stats,
    )


def print_summary(results_by_model: dict[str, list[CaseResult]]) -> None:
    print("\nAdvisor model comparison\n")
    for model, results in results_by_model.items():
        total = len(results)
        passed = sum(1 for result in results if result.ok)
        errors = sum(1 for result in results if result.response.startswith("Error:"))
        avg_elapsed = sum(result.elapsed_s for result in results) / max(total, 1)
        print(
            f"- {model}: {passed}/{total} heuristic passes, {errors} API/runtime errors, "
            f"avg {avg_elapsed:.2f}s"
        )
        for result in results:
            status = "PASS" if result.ok else "FAIL"
            print(f"  [{status}] {result.name}: {result.notes}")
            if result.issues:
                print(f"    issues: {'; '.join(result.issues)}")
            preview = " ".join(result.response.split())
            if len(preview) > 180:
                preview = preview[:177].rstrip() + "..."
            print(f"    answer: {preview}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--save-path", type=Path, required=True, help="Path to the .sav file to test"
    )
    parser.add_argument(
        "--model",
        action="append",
        dest="models",
        help="Model to test (repeatable). Defaults to Gemini Flash + Flash-Lite.",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        help="Optional path to save structured JSON results.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("GOOGLE_API_KEY is not set.", file=sys.stderr)
        return 1

    save_path = args.save_path.expanduser().resolve()
    if not save_path.exists():
        print(f"Save file not found: {save_path}", file=sys.stderr)
        return 1

    models = args.models or [
        DEFAULT_ADVISOR_MODEL,
        "gemini-3.1-flash-lite-preview",
    ]

    briefing = load_briefing(save_path)
    companion = build_companion(save_path, api_key=api_key, briefing=briefing)
    cases = build_cases(briefing)

    meta = briefing.get("meta") or {}
    print(f"Loaded save: {save_path}")
    print(f"Empire: {(briefing.get('identity') or {}).get('empire_name')}")
    print(f"Date: {meta.get('date')}  Version: {meta.get('version')}")
    print(f"Running {len(cases)} cases across {len(models)} models...\n")

    results_by_model: dict[str, list[CaseResult]] = {}
    for model in models:
        model_results: list[CaseResult] = []
        results_by_model[model] = model_results
        print(f"Testing {model}...")
        for case in cases:
            result = run_case(companion, case, model=model)
            model_results.append(result)
            status = "PASS" if result.ok else "FAIL"
            print(f"  {status} {case.name} ({result.elapsed_s:.2f}s)")

    print_summary(results_by_model)

    if args.json_out:
        payload = {
            "save_path": str(save_path),
            "meta": meta,
            "models": models,
            "cases": [asdict(case) for case in cases],
            "results_by_model": {
                model: [asdict(result) for result in results]
                for model, results in results_by_model.items()
            },
            "generated_at": time.time(),
        }
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nSaved JSON results to {args.json_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
