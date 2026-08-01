#!/usr/bin/env python3
"""Record cross-provider game-knowledge responses for human review.

This intentionally does not score prose with regexes or another LLM. It records the
prompt, review criteria, provider metadata, and raw answer so a maintainer can judge
substantive correctness while allowing normal model and wording variance.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from unittest.mock import MagicMock

from google import genai
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.advisor_providers import (  # noqa: E402
    ADVISOR_PROVIDER_GEMINI,
    ADVISOR_PROVIDER_OPENROUTER,
    PROVIDER_BASE_URLS,
    AdvisorProviderConfig,
    create_advisor_generator,
)
from backend.core.chronicle import ChronicleGenerator  # noqa: E402
from stellaris_companion.game_knowledge import build_game_knowledge_prompt  # noqa: E402

DEFAULT_OPENROUTER_MODELS = [
    "deepseek/deepseek-v4-flash",
    "anthropic/claude-sonnet-5",
    "google/gemini-3.1-flash-lite",
    "openai/gpt-5.6-luna",
    "xiaomi/mimo-v2.5",
]

HumanLabel = Literal["accurate", "acceptable", "concerning", "materially_incorrect"]


class ChronicleEvalOutput(BaseModel):
    title: str
    narrative: str = Field(description="One concise in-universe historical paragraph")


@dataclass(frozen=True)
class EvalCase:
    name: str
    purpose: Literal["advisor", "chronicle"]
    prompt: str
    review_criteria: list[str]
    structured: bool = False


@dataclass
class EvalResult:
    case: str
    purpose: str
    provider: str
    requested_model: str
    final_model: str | None
    elapsed_seconds: float
    response: str | None
    provider_error: str | None
    schema_fallback_used: bool
    human_label: HumanLabel | None = None
    human_rationale: str = ""


def build_cases() -> list[EvalCase]:
    """Return high-value cases whose criteria are reviewed semantically by a person."""
    return [
        EvalCase(
            name="population_scale",
            purpose="advisor",
            prompt=(
                "Campaign evidence: Pegasus v4.4.6; total population 94,000; total "
                "workforce 94,000; no unemployment, housing, stability, or deficit problem "
                "is reported. The player asks: Is 94,000 population impossibly high or proof "
                "that my save is broken?"
            ),
            review_criteria=[
                "Understands that 4.x population is measured in thousands.",
                "Does not diagnose a broken save or unhealthy economy from the total alone.",
                "Does not invent a universal typical mid-game population range.",
            ],
        ),
        EvalCase(
            name="colony_establishment",
            purpose="advisor",
            prompt=(
                "Campaign evidence: an unmodded Pegasus v4.4.6 colony is beginning from zero "
                "establishment progress. Explain the normal population threshold and roughly "
                "how long establishment takes at the base monthly rate."
            ),
            review_criteria=[
                "Uses 100 population as the establishment threshold.",
                "Gives about 34 months, or about 2 years and 10 months.",
                "Allows for modifiers or mods rather than presenting timing as universal.",
            ],
        ),
        EvalCase(
            name="anchorage_costs",
            purpose="advisor",
            prompt=(
                "Campaign evidence: unmodded Pegasus v4.4.6, normal Anchorage, no Naval "
                "Logistics Office. What naval capacity and recurring upkeep does one Anchorage "
                "provide? Also explain what the office changes."
            ),
            review_criteria=[
                "Normal Anchorage: +5 Naval Capacity, 4 Trade and 1 Energy upkeep.",
                "Office: +3 Naval Capacity and +2 Trade upkeep per Anchorage.",
                "Does not repeat the obsolete claim that Trade upkeep simply equals capacity.",
            ],
        ),
        EvalCase(
            name="market_currency",
            purpose="advisor",
            prompt=(
                "Campaign evidence: unmodded Pegasus v4.4.6. The player says Energy is still "
                "the Galactic Market currency. Correct or confirm them concisely."
            ),
            review_criteria=[
                "Corrects the claim: Trade is the market currency.",
                "Explains that Energy is an ordinary resource that can be traded.",
            ],
        ),
        EvalCase(
            name="operational_reserves",
            purpose="advisor",
            prompt=(
                "Campaign evidence: unmodded Pegasus v4.4.6 Nomad empire with one Tier II "
                "Civilian Arkship and no other capacity modifiers. State the Energy/Mineral "
                "conversion rule and expected base reserve capacity including that Arkship."
            ),
            review_criteria=[
                "Uses one-to-one Energy/Mineral conversion.",
                "Calculates 27,500 capacity: 15,000 base + 7,500 Tier II + 5,000 Civilian.",
                "Does not use the superseded 3:1 conversion rule.",
            ],
        ),
        EvalCase(
            name="dimensional_fleet",
            purpose="advisor",
            prompt=(
                "Campaign evidence: unmodded Pegasus v4.4.6 and 9 completed Astral Rifts. "
                "How many small and large ships does the Dimensional Fleet action create?"
            ),
            review_criteria=[
                "Answers 9 small ships and 4 large ships.",
                "Understands that half the Rift count is rounded down for large ships.",
            ],
        ),
        EvalCase(
            name="chronicle_lgate_evidence",
            purpose="chronicle",
            structured=True,
            prompt=(
                "Write one historical paragraph from only this campaign evidence:\n"
                "- Date: 2312.04.01\n"
                "- The empire completed an L-Gate insight technology.\n"
                "- Extracted state: lgate_opened=false.\n"
                "- No L-Gate activation, opening, or traversal event is recorded."
            ),
            review_criteria=[
                "May dramatize investigation or discovery.",
                "Does not claim that an L-Gate opened, activated, or was traversed.",
                "Does not invent what lies beyond the gates.",
            ],
        ),
        EvalCase(
            name="chronicle_dormant_power",
            purpose="chronicle",
            structured=True,
            prompt=(
                "Write one historical paragraph from only this campaign evidence:\n"
                "- Date: 2330.01.01\n"
                "- Contact with a dormant Fallen Empire was recorded.\n"
                "- No awakening, hostility, border conflict, demand, or battle is recorded."
            ),
            review_criteria=[
                "Treats contact as historically significant without inventing aggression.",
                "Does not claim the Fallen Empire awakened or became an immediate threat.",
                "Does not add a demand, motive, battle, or diplomatic outcome.",
            ],
        ),
    ]


def _provider_config(args: argparse.Namespace, model: str) -> AdvisorProviderConfig:
    provider = args.provider
    if provider == ADVISOR_PROVIDER_GEMINI:
        api_key = os.environ.get("GOOGLE_API_KEY", "")
        base_url = ""
    else:
        api_key = os.environ.get("STELLARIS_ADVISOR_API_KEY") or os.environ.get(
            "OPENROUTER_API_KEY", ""
        )
        base_url = args.base_url or PROVIDER_BASE_URLS.get(provider, "")
    return AdvisorProviderConfig(
        provider=provider,
        model=model,
        base_url=base_url,
        api_key=api_key,
        timeout_seconds=args.timeout,
    )


def run_case(args: argparse.Namespace, model: str, case: EvalCase) -> EvalResult:
    config = _provider_config(args, model)
    gemini_client = genai.Client(api_key=config.api_key) if config.provider == "gemini" else None
    generator = create_advisor_generator(config=config, gemini_client=gemini_client)
    if generator is None:
        raise RuntimeError(f"{config.display_name} is not configured")

    started = time.monotonic()
    try:
        if case.structured:
            chronicle = ChronicleGenerator(
                db=MagicMock(),
                provider_config=config,
                provider_generator=generator,
            )
            _, response = chronicle._generate_structured_content(  # type: ignore[attr-defined]
                contents=case.prompt,
                response_schema=ChronicleEvalOutput,
                temperature=0.7,
                max_output_tokens=1200,
                purpose_label=f"Knowledge evaluation: {case.name}",
                game_knowledge_context=build_game_knowledge_prompt(
                    "Pegasus v4.4.6", purpose="chronicle"
                ),
            )
        else:
            system_prompt = (
                "Answer as a strategic advisor. Distinguish campaign observations from "
                "mechanics.\n\n"
                f"{build_game_knowledge_prompt('Pegasus v4.4.6', purpose='advisor')}"
            )
            response = generator.generate(
                system_prompt=system_prompt,
                user_prompt=case.prompt,
                model=model,
                temperature=0.7,
                max_output_tokens=1200,
                purpose="advisor",
            )
        return EvalResult(
            case=case.name,
            purpose=case.purpose,
            provider=config.provider,
            requested_model=model,
            final_model=response.model,
            elapsed_seconds=round(time.monotonic() - started, 3),
            response=response.text,
            provider_error=None,
            schema_fallback_used=response.schema_fallback_used,
        )
    except Exception as exc:
        return EvalResult(
            case=case.name,
            purpose=case.purpose,
            provider=config.provider,
            requested_model=model,
            final_model=None,
            elapsed_seconds=round(time.monotonic() - started, 3),
            response=None,
            provider_error=str(exc),
            schema_fallback_used=False,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider",
        default=ADVISOR_PROVIDER_OPENROUTER,
        choices=["gemini", "openrouter", "ollama", "lm_studio", "custom"],
    )
    parser.add_argument("--models", nargs="+", help="Exact model IDs to test")
    parser.add_argument("--base-url", help="OpenAI-compatible API base URL")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--case", action="append", dest="case_names")
    parser.add_argument(
        "--json-out",
        type=Path,
        default=Path("tmp/game-knowledge-eval.json"),
    )
    parser.add_argument("--list", action="store_true", help="List cases without making calls")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cases = build_cases()
    if args.case_names:
        selected = set(args.case_names)
        cases = [case for case in cases if case.name in selected]
        missing = selected - {case.name for case in cases}
        if missing:
            print(f"Unknown cases: {', '.join(sorted(missing))}", file=sys.stderr)
            return 2

    if args.list:
        for case in cases:
            print(f"{case.name}\t{case.purpose}")
        return 0

    models = args.models
    if not models:
        if args.provider == ADVISOR_PROVIDER_OPENROUTER:
            models = DEFAULT_OPENROUTER_MODELS
        else:
            print("Pass at least one exact model ID with --models.", file=sys.stderr)
            return 2

    results: list[EvalResult] = []
    for model in models:
        print(f"\n## {model}")
        for case in cases:
            result = run_case(args, model, case)
            results.append(result)
            status = "ERROR" if result.provider_error else "RECORDED"
            print(f"{status:8} {case.name:28} {result.elapsed_seconds:7.2f}s")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "game_version": "Pegasus v4.4.6",
        "provider": args.provider,
        "models": models,
        "human_review_scale": [
            "accurate",
            "acceptable",
            "concerning",
            "materially_incorrect",
        ],
        "cases": [asdict(case) for case in cases],
        "results": [asdict(result) for result in results],
    }
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nRaw responses saved to {args.json_out}")
    print("Semantic labels are intentionally blank pending human review.")
    return 1 if any(result.provider_error for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
