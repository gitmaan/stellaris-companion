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
from stellaris_companion.game_knowledge import (  # noqa: E402
    DEFAULT_SNAPSHOTS_DIR,
    build_game_knowledge_prompt,
)

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
        EvalCase(
            name="cold_population_growth",
            purpose="advisor",
            prompt=(
                "Campaign evidence: unmodded Pegasus v4.4.6. A planet has several organic "
                "species. The player remembers that only one selected species can grow each "
                "month, that an underrepresented species gets a special growth bonus, and that "
                "mechanical assembly blocks organic growth or assembly. Explain the current "
                "baseline without assuming species-specific modifiers."
            ),
            review_criteria=[
                "Corrects the old premise: Pop Groups grow simultaneously each month.",
                "Explains that Pop Groups are separated by species and other attributes.",
                "Does not grant underrepresented species a special baseline growth bonus.",
                "May explain that fractional monthly growth becomes a chance to add one pop.",
                "Explains that Machine and Organic Assembly can occur simultaneously rather "
                "than treating them as competing for one assembly slot.",
            ],
        ),
        EvalCase(
            name="cold_planet_economy",
            purpose="advisor",
            prompt=(
                "Campaign evidence: unmodded Pegasus v4.4.6. The player wants more Alloys and "
                "plans to fill every building slot with Alloy Foundries because each copy adds "
                "Metallurgist jobs. Is that a complete scaling plan? Explain the current roles "
                "of district development, Heavy Industry specialization, and Foundry buildings."
            ),
            review_criteria=[
                "Uses developed City Districts and Heavy Industry or Foundry specialization as "
                "the main scalable source of Metallurgist capacity.",
                "Explains that district development supplies jobs and housing.",
                "Correctly allows Alloy Foundry buildings to add fixed Metallurgist jobs rather "
                "than claiming they only modify district jobs.",
                "Considers available Workforce, inputs, upkeep, and building-slot opportunity "
                "cost before recommending that every slot be used.",
                "Does not describe the pre-4 one-pop-per-job planetary economy as current.",
            ],
        ),
        EvalCase(
            name="cold_trade_system",
            purpose="advisor",
            prompt=(
                "Campaign evidence: unmodded Pegasus v4.4.6. The player is drawing starbase "
                "collection ranges and patrol routes to carry Trade Value to the capital while "
                "suppressing piracy. Is that still the right system? Explain the current flow "
                "from planetary Trade through logistics and Trade Policy."
            ),
            review_criteria=[
                "Corrects the premise: the old starbase Trade Route and piracy-patrol system "
                "was removed and Trade is collected automatically.",
                "Treats Trade as a standard advanced resource rather than the old Trade Value "
                "routing abstraction.",
                "Explains that planetary or logistics costs consume Trade and Trade Policy "
                "allocates monthly production between retained Trade and other resources.",
            ],
        ),
        EvalCase(
            name="cold_empire_focus",
            purpose="advisor",
            prompt=(
                "Campaign evidence: unmodded Pegasus v4.4.6 at game start. The player thinks "
                "technology planning still consists only of waiting for random research cards. "
                "Explain how Empire Focus and its progression affect strategic planning and "
                "research options without claiming that normal random research disappeared."
            ),
            review_criteria=[
                "Identifies Empire Focus and its Core, Conquest, Exploration, and Development "
                "tasks or progression.",
                "Explains that task progression can unlock permanent research options or other "
                "category advances.",
                "Does not claim that ordinary weighted or random research choices disappeared.",
            ],
        ),
        EvalCase(
            name="cold_species_templates",
            purpose="advisor",
            prompt=(
                "Campaign evidence: unmodded Pegasus v4.4.6 with several templates of one "
                "species. The player wants those sub-species to converge on one design and "
                "assumes they must repeatedly apply a special modification project. Explain the "
                "current Default Template and Sub-Species Integration option."
            ),
            review_criteria=[
                "Explains that one species template can be selected as the Default Template.",
                "Explains that templates set to Sub-Species Integration are altered toward the "
                "default automatically over time.",
                "Does not claim that integration is mandatory for every sub-species.",
            ],
        ),
        EvalCase(
            name="cold_colony_establishment",
            purpose="advisor",
            prompt=(
                "Campaign evidence: unmodded Pegasus v4.4.6 colony at 40/100 establishment "
                "progress, with no modifiers shown. The player expects it to behave like a "
                "fully established pre-4 colony already. Explain what the number means, the "
                "baseline time remaining, and what not to assume before establishment."
            ),
            review_criteria=[
                "Recognizes 100 population as the establishment threshold.",
                "At the base rate of 3 per month, estimates 20 months from 40 to 100.",
                "Explains that a colony under establishment does not yet have normal population "
                "growth or production.",
                "Allows for migration, modifiers, DLC, or mods to change the observed timing.",
            ],
        ),
        EvalCase(
            name="cold_psionic_ascension",
            purpose="advisor",
            prompt=(
                "Campaign evidence: unmodded Pegasus v4.4.6 with Shadows of the Shroud "
                "active. The empire has begun Psionic Ascension, but has not yet breached "
                "the Shroud. The player expects the old flow of finishing perks and then "
                "rolling unrelated random Shroud visits. Explain the current progression "
                "without claiming a Patron or Covenant has already been selected."
            ),
            review_criteria=[
                "Explains that Psionic Ascension uses an Ascension Situation culminating in "
                "the first Delve after breaching the Shroud.",
                "Explains that choices can affect Attunement and later Shroud access.",
                "Recognizes the Shroud Panel, Accords, and possible Covenants as current systems.",
                "Does not invent a selected Patron, Accord, Covenant, or Delve outcome.",
            ],
        ),
        EvalCase(
            name="cold_ongoing_war",
            purpose="advisor",
            prompt=(
                "Campaign evidence: unmodded Pegasus v4.4.6. The player is a secondary "
                "participant in a war and believes participants can never leave until the "
                "primary empires settle it. Their last colony has just been occupied. Explain "
                "the available mechanism and the consequences of remaining fully occupied."
            ),
            review_criteria=[
                "Explains that a non-primary participant can negotiate with the opposing war "
                "leader to leave through trade terms.",
                "Notes that acceptance is not guaranteed and leaving creates a truce and "
                "diplomatic penalty.",
                "Explains that the Hopeless War multiplier grows by 5 percentage points each "
                "month without treating it as either a fixed +5% or +5% per occupied colony.",
                "Does not apply primary-participant monthly Attrition to this secondary "
                "participant's entire side without evidence.",
            ],
        ),
        EvalCase(
            name="cold_stellar_cannon",
            purpose="advisor",
            prompt=(
                "Campaign evidence: unmodded Pegasus v4.4.6 with Nomads active. The player "
                "has found the Stellar Cannon technology and assumes it is a harmless Dyson "
                "Sphere variant that needs an Ascension Perk. Explain what it is, where it can "
                "be built, and the main firing tradeoff without claiming they have built one."
            ),
            review_criteria=[
                "Identifies the Stellar Cannon as an offensive megastructure rather than a "
                "Dyson Sphere economy upgrade.",
                "Requires a neutron star or pulsar and no Ascension Perk.",
                "Does not apply generic Waystation access in place of the neutron-star or "
                "pulsar requirement.",
                "Explains the roughly 140-day charge and that firing consumes the full Energy "
                "stockpile.",
                "Treats 10,000 Energy as the threshold for colony devastation rather than a "
                "minimum required to fire, and does not claim a shot or planetary effect "
                "occurred.",
            ],
        ),
        EvalCase(
            name="natural_growth_and_alloys",
            purpose="advisor",
            prompt=(
                "I'm playing an unmodded Pegasus v4.4.6 empire. My capital has three "
                "organic species growing, robots being assembled, 600 Metallurgist job "
                "capacity but only 340 Workforce assigned to it, and weak Alloy income. "
                "Should I build another Alloy Foundry and stop robot assembly so my main "
                "species gets the planet's growth slot?"
            ),
            review_criteria=[
                "Corrects the growth-slot premise: eligible organic Pop Groups grow "
                "simultaneously.",
                "Explains that mechanical assembly can coexist with organic growth rather "
                "than stealing its slot.",
                "Recognizes that the existing Metallurgist capacity is underfilled, so more "
                "fixed capacity is unlikely to be the first solution.",
                "May suggest checking Workforce, Heavy Industry district development, inputs, "
                "upkeep, or assignment without inventing which one is currently deficient.",
            ],
        ),
        EvalCase(
            name="natural_trade_and_fleet",
            purpose="advisor",
            prompt=(
                "Pegasus v4.4.6, unmodded: my monthly Trade balance is -18, Energy is +80, "
                "my main fleet is operating in hostile space, and I just added three normal "
                "Anchorages without a Naval Logistics Office. Should I build patrol ships and "
                "more Generator Districts to stop piracy and fix the Trade deficit?"
            ),
            review_criteria=[
                "Explains that the old Trade Route, piracy suppression, and patrol system is "
                "not the current mechanic.",
                "Connects hostile fleet operation to higher Trade logistics cost and may "
                "suggest docking or relocating when strategically possible.",
                "Accounts for each normal Anchorage adding 4 Trade and 1 Energy upkeep.",
                "Does not treat an Energy surplus or more Generator Districts as a direct fix "
                "for a Trade deficit; may suggest Trade production or policy checks.",
            ],
        ),
        EvalCase(
            name="natural_nomad_reserves",
            purpose="advisor",
            prompt=(
                "I'm a Nomad in unmodded Pegasus v4.4.6 with one Tier II Civilian Arkship, "
                "no silos or other capacity modifiers, 4,000 Operational Reserves, and "
                "negative Energy and Mineral income. A Waystation has a large uncollected "
                "stockpile, and collection automation is off. Is my reserve cap only 7,500, "
                "and should I settle immediately before the economy collapses?"
            ),
            review_criteria=[
                "Calculates 27,500 reserve capacity from 15,000 base, 7,500 Tier II, and "
                "5,000 Civilian Arkship capacity.",
                "Uses the current one-to-one Energy and Mineral reserve conversion.",
                "Prioritizes checking or enabling Waystation collection before concluding "
                "that settlement is necessary.",
                "Does not claim that collecting an existing stockpile must make the underlying "
                "monthly resource flow positive.",
                "Recognizes that Critical occupies the lowest 5% and begins above zero; with "
                "the stated unmodified 27,500 cap, 4,000 is low but not Critical.",
                "Treats low reserves and negative flows as concerning without claiming "
                "inevitable collapse.",
            ],
        ),
        EvalCase(
            name="natural_chronicle_mixed_evidence",
            purpose="chronicle",
            structured=True,
            prompt=(
                "Write one concise historical paragraph from only this Pegasus v4.4.6 "
                "campaign evidence:\n"
                "- Date: 2338.07.01.\n"
                "- The empire completed research into the Stellar Cannon.\n"
                "- Contact with a dormant Fallen Empire was recorded.\n"
                "- An L-Gate insight technology was completed, but lgate_opened=false.\n"
                "- No cannon construction or firing, Fallen Empire hostility or awakening, "
                "or L-Gate activation or traversal is recorded."
            ),
            review_criteria=[
                "May frame the discoveries and contact as significant possibilities or "
                "uncertainties.",
                "Does not claim that a Stellar Cannon was built or fired.",
                "Does not turn dormant contact into hostility, awakening, a demand, or war.",
                "Does not claim that an L-Gate opened or reveal what lies beyond it.",
                "Does not invent a causal connection among the three developments.",
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
    snapshots_dir = args.snapshots_dir or DEFAULT_SNAPSHOTS_DIR
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
                max_output_tokens=args.max_output_tokens,
                purpose_label=f"Knowledge evaluation: {case.name}",
                game_knowledge_context=build_game_knowledge_prompt(
                    "Pegasus v4.4.6",
                    purpose="chronicle",
                    snapshots_dir=snapshots_dir,
                ),
            )
        else:
            system_prompt = (
                "Answer as a strategic advisor. Distinguish campaign observations from "
                "mechanics.\n\n"
                f"{build_game_knowledge_prompt('Pegasus v4.4.6', purpose='advisor', snapshots_dir=snapshots_dir)}"
            )
            response = generator.generate(
                system_prompt=system_prompt,
                user_prompt=case.prompt,
                model=model,
                temperature=0.7,
                max_output_tokens=args.max_output_tokens,
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
    parser.add_argument(
        "--snapshots-dir",
        type=Path,
        help="Override the versioned snapshot directory for controlled comparisons",
    )
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--max-output-tokens", type=int, default=1200)
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
