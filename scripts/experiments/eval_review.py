"""Prepare blinded review packets and summarize explicit, attributed ratings.

No model calls or automatic semantic scores. Example:
    python -m scripts.experiments.eval_review prepare before.json after.json --out review.json
    python -m scripts.experiments.eval_review summarize review.json --key review.key.json
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

REVIEW_RUBRIC = {
    "accuracy": {
        "sound": "No material factual error; allow valid alternative advice and harmless wording differences.",
        "minor_error": "A demonstrated factual error that does not change the player's decision.",
        "material_error": "A demonstrated error that changes the answer, eligibility, calculation or recommended action.",
        "unverifiable": "Available independent references cannot establish whether a consequential claim is true.",
    },
    "grounding": {
        "supported": "Campaign claims follow observations; mechanics have applicable support; assumptions and forecasts are distinguishable.",
        "unverified_detail": "Adds unsupported specifics or presents an unverified inference as fact; this alone does not establish falsity.",
        "contradiction": "Contradicts supplied observations or an applicable verified rule.",
    },
    "usefulness": {
        "useful": "Answers the actual question with relevant, actionable reasoning or a useful conditional answer.",
        "partial": "Some useful content, but a significant omission, unnecessary caution or irrelevant detail weakens it.",
        "unhelpful": "Evades an answerable question, misses the decision, or gives unusable advice.",
    },
    "naturalness": {
        "natural": "Readable, conversational and proportionate; personality supports the answer. No fixed wording or format is required.",
        "awkward": "Noticeable boilerplate, repetitive hedging, mechanical phrasing or unnecessary verbosity.",
        "distracting": "Roleplay, jargon or rigid formatting substantially obscures the answer.",
    },
}


def empty_review() -> dict[str, Any]:
    return {
        "reviewer": None,
        "reviewer_kind": None,
        **dict.fromkeys(REVIEW_RUBRIC),
        "rationale": "",
    }


def prepare_review(paths: list[Path], *, seed: int = 0) -> tuple[dict, dict]:
    """Hide variant/model identity and retrieved context from semantic reviewers."""
    samples = []
    errors = []
    for path in paths:
        run = json.loads(path.read_text())
        cases = {case["name"]: case for case in run["cases"]}
        variant = run.get("variant") or path.stem
        for index, result in enumerate(run["results"]):
            case = cases[result["case"]]
            receipt = {
                "file": str(path),
                "index": index,
                "variant": variant,
                "case": result["case"],
                "family": case.get("family", "legacy"),
                "split": case.get("split", "regression"),
                "model": result.get("final_model") or result["requested_model"],
                "repetition": result.get("repetition", 1),
                "elapsed_seconds": result["elapsed_seconds"],
                "input_characters": len(result.get("assembled_system_prompt") or "")
                + len(result.get("assembled_user_prompt") or ""),
                "output_characters": len(result.get("response") or ""),
            }
            if result.get("provider_error") or not result.get("response"):
                errors.append(receipt)
                continue
            samples.append(
                (
                    {
                        "question": case["prompt"],
                        "game_version": result["game_version"],
                        "briefing": case.get("briefing"),
                        "previous_turns": case.get("previous_turns"),
                        "criteria": case["review_criteria"],
                        "references": case.get("references", []),
                        "response": result["response"],
                        "review": empty_review(),
                    },
                    receipt,
                )
            )
    random.Random(seed).shuffle(samples)
    packet = {"format_version": 1, "rubric": REVIEW_RUBRIC, "samples": []}
    key = {"format_version": 1, "samples": {}, "provider_errors": errors}
    for index, (sample, receipt) in enumerate(samples, start=1):
        sample_id = f"sample-{index:04d}"
        packet["samples"].append({"sample_id": sample_id, **sample})
        key["samples"][sample_id] = receipt
    return packet, key


def summarize_review(packet: dict, key: dict) -> dict:
    """Report dimensions separately; unrated answers and transport errors never pass."""
    groups: dict[tuple, list] = defaultdict(list)
    seen = set()
    for sample in packet["samples"]:
        sample_id = sample["sample_id"]
        if sample_id in seen:
            raise ValueError(f"Duplicate review sample: {sample_id}")
        seen.add(sample_id)
        receipt = key["samples"][sample_id]
        review = sample["review"]
        for dimension, labels in REVIEW_RUBRIC.items():
            label = review.get(dimension)
            if label is not None and label not in labels:
                raise ValueError(f"Invalid {dimension} rating in {sample_id}: {label}")
        if any(review.get(dimension) is not None for dimension in REVIEW_RUBRIC):
            if not review.get("reviewer") or review.get("reviewer_kind") not in {"human", "model"}:
                raise ValueError(
                    f"Ratings require an attributed human or model reviewer: {sample_id}"
                )
        groups[(receipt["variant"], receipt["model"], receipt["split"])].append((receipt, review))
    if seen != key["samples"].keys():
        raise ValueError("Review packet is missing samples from its key")
    summary = []
    for (variant, model, split), rows in sorted(groups.items()):
        summary.append(
            {
                "variant": variant,
                "model": model,
                "split": split,
                "answers": len(rows),
                "distinct_cases": len({row[0]["case"] for row in rows}),
                "reviewer_kinds": dict(
                    Counter(review.get("reviewer_kind") or "unreviewed" for _, review in rows)
                ),
                "ratings": {
                    dimension: dict(
                        Counter(review.get(dimension) or "unreviewed" for _, review in rows)
                    )
                    for dimension in REVIEW_RUBRIC
                },
                "mean_input_characters": round(
                    mean(receipt["input_characters"] for receipt, _ in rows)
                ),
                "mean_output_characters": round(
                    mean(receipt["output_characters"] for receipt, _ in rows)
                ),
                "mean_elapsed_seconds": round(
                    mean(receipt["elapsed_seconds"] for receipt, _ in rows), 2
                ),
            }
        )
    return {
        "groups": summary,
        "provider_errors": key.get("provider_errors", []),
        "note": "Repeated trials are not independent scenarios. These counts do not establish production error rates.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("runs", type=Path, nargs="+")
    prepare.add_argument("--out", type=Path, required=True)
    prepare.add_argument("--seed", type=int, default=0)
    summarize = commands.add_parser("summarize")
    summarize.add_argument("review", type=Path)
    summarize.add_argument("--key", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        packet, key = prepare_review(args.runs, seed=args.seed)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(packet, indent=2, ensure_ascii=False) + "\n")
        args.out.with_suffix(".key.json").write_text(json.dumps(key, indent=2) + "\n")
        print(
            f"Prepared {len(packet['samples'])} unreviewed answers; {len(key['provider_errors'])} provider errors."
        )
    else:
        print(
            json.dumps(
                summarize_review(
                    json.loads(args.review.read_text()), json.loads(args.key.read_text())
                ),
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
