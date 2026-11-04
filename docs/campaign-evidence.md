# Campaign evidence and model selection

The Advisor, Chronicle, and MCP surfaces interpret the same dated campaign evidence.
An omitted save field is unknown, and a reported DLC is evidence of a save requirement,
not a complete inventory of ownership, current unlocks, or achievement eligibility.

## Evidence flow

1. Extraction retains the original DLC list and records whether the field was reported,
   absent, or invalid. Complete stored briefings retain that status.
2. `stellaris_companion/campaign_evidence.py` resolves positive content evidence and
   typed empire identity without modifying the source. Its identity catalog supplies
   names, not mechanical rules; unknown identifiers remain explicit.
3. `backend/core/model_briefing.py` rebuilds derived context whenever a briefing is
   consumed, including older stored briefings. Schema 3 carries content availability,
   identity, and the common evidence policy. The obsolete `missing_dlcs` inference is
   omitted from model-facing copies; the stored source and its hash stay unchanged.
4. The Advisor builds its voice and factual context from the exact captured snapshot.
   Chronicle history retains the full identity and DLC evidence during compaction.
   MCP uses the same adapter and preserves these fields outside ordinary truncation.

`stellaris_companion/evidence_policy.py` distinguishes observed state, versioned
mechanics, eligibility, calculations, and conditional advice. Persona instructions set
voice. They do not decide availability. Chronicle has the additional boundary that a
mechanic or recommendation cannot establish that an event occurred.

Utopia, Synthetic Dawn, and Humanoids became base-game content in **4.3.6**. The resolver
applies that boundary to the reported campaign version; it does not apply it to older
or unknown versions. The source is the
[official Stellaris 4.3.6 announcement](https://store.steampowered.com/news/posts/?appids=281990&enddate=1778509430&feed=steam_community_announcements).
Names in the small identity catalog were checked against shipped English game
localization. A Rogue Servitor is a civic under Machine Intelligence authority.

Legacy empty DLC arrays are ambiguous because older extraction used an empty array
for both absence and an explicitly empty block. They remain unknown unless the source
also records the field's status. No migration invents missing evidence.

## Model selection

`stellaris_companion/model_catalog.json` defines model families shared by Python,
Electron discovery, and the evaluation script. OpenRouter offers **Latest stable**
choices for Gemini Flash-Lite, DeepSeek Flash, and Claude Sonnet. Each request resolves
the selected family to the newest compatible stable version in the provider catalog.
The built-in Gemini route similarly follows stable Flash and Flash-Lite releases while
preserving its quality/conserve preference and quota fallback behavior.

Catalogs are cached per configured generator for one hour. A failed refresh retries
after one minute and can reuse previously observed, still-eligible entries. OpenRouter
fails with an actionable error if no model in the selected family can be resolved.
Native Gemini retains its shipped stable fallback IDs during a cold catalog outage.
A successful catalog with no eligible models fails instead of guessing a replacement.

Known naming patterns exclude previews, experiments, batch/free variants, expired
models, and incompatible endpoints. Version numbers determine ordering within a
family. Providers do not consistently guarantee that their own latest aliases are
stable; see [Google model versions](https://ai.google.dev/gemini-api/docs/models#model-versions)
and [OpenRouter latest resolution](https://openrouter.ai/docs/guides/routing/routers/latest-resolution).
New naming conventions or API changes still require updating family definitions.

Existing explicit IDs and aliases remain pinned. Users opt into automatic updates by
selecting a Latest stable option. Settings and onboarding show its currently resolved
model and available pricing, including a notice that pricing can change. Responses
record the concrete model returned by the provider. Discovery returns the full
searchable catalog and preserves selections omitted by a catalog or resolved by a
connection probe. Onboarding loads saved settings before discovery.

A connection check establishes connectivity and supported response behavior; it does
not certify factual quality.

New ChatGPT connections prefer `gpt-6.1-terra` when the account offers it, with the
previous tested models retained as fallbacks. Direct OpenAI discovery also recommends
Terra when available. Saved and explicitly entered choices remain selected. Advisor
uses low reasoning and Chronicle uses medium; the official Terra Chat Completions
adapter uses its reasoning-inclusive completion allowance. See
[provider completion behavior](provider-completion.md).

## Versioned mechanics

Question-based retrieval can also include one section relevant to verified empire
identity. Unknown mod identifiers do not acquire rules through name similarity.
Applicability filtering is disabled by default pending demonstrated answer-quality benefit.
The evaluation-only `--experimental-applicability` option selects the same sections first,
then prunes scoped rules without promoting replacement sections. Metadata and generated
scope notes never participate in ranking. Observed identity can support a scope; an explicit
question can also request it for a comparison or hypothetical plan. Unknown conditions remain
conditional, and omitted civic or DLC evidence does not establish unavailability. Gameplay
prose stays in Markdown; `patches/applicability.json` supplies reusable scope metadata without
copying the facts.
The 4.4.6 snapshot includes sourced machine/hive civic effects, selected machine
achievement event conditions, and Colossus requirements. These rules remain scoped to
that verified version; 4.5 coverage remains partial release-note context. See the
[source audit](../patches/audits/4.4.6.md) and [maintenance guide](../patches/README.md).

## Validation and remaining limits

Automated checks cover old and current versions, absent and invalid metadata, unknown
mod identifiers, provider-independent prompts, captured-source immutability, historical
compaction, MCP context, and model-selection persistence. Existing extraction and
Chronicle tests remain part of the full suite.

The `evidence` evaluation suite makes synthetic requests through the production Advisor
path, recording exact assembled prompts, actual case version, provider identity,
responses, and errors. For example:

```sh
python scripts/experiments/eval_game_knowledge.py --suite evidence \
  --provider openrouter --models stellaris:latest-stable/claude-sonnet --repeats 2 \
  --json-out tmp/evidence-review.json
```

Set the provider credential in the environment. Use `--list` to inspect cases without
making a paid request. Existing Chronicle evaluation cases exercise the structured
generation adapter, not the complete archive/context assembly; automated consumer
tests cover that context separately. Transport success is never a semantic pass, and
human review labels stay blank until a person fills them in.

The evidence suite covers multiple empire types, current and historical versions,
unknown mod rules, exact mechanics, ordinary strategy, and supported calculations.
Use `--repeats` for independent samples and `--snapshots-dir` for a controlled reference
comparison. Each sample records its repetition and concrete response model, and results
are saved after every request. The shared policy and verified references reduce
contradictory inputs but do not guarantee that generated advice is correct.

The `applicability` suite adds development and held-out scenario families covering direct
and comparative questions, ordinary strategy, changing conversation evidence, modded rules
and player preferences. Its review utility prepares blinded answer packets with independent
ratings for accuracy, grounding, usefulness and naturalness. Reviews identify whether the
reviewer was a human or a model; unreviewed answers and transport errors never count as
semantic passes. See the maintenance guide for comparison and review commands.

Experimental applicability is intentionally partial. Existing lexical topic selection remains
in place, and unannotated mechanics follow its prior behavior. An explicit `is_nomadic` observation is
supported by the scope interface, but current extraction does not supply that field; it is
never inferred from authority or DLCs. The change adds no generation passes, eligibility
engine, tool loop or required answer template.

## Applicability experiment: 2026-11-03

This initial experiment used filtering before ranking; that behavior is now held out of
the app defaults. The candidate added scope metadata to existing versioned Markdown. The control
used retrieval and references from commit `0682bb2`; both variants used identical production request
assembly, fixtures, model IDs and generation limits. There were 20 synthetic scenarios,
two Gemini models (`gemini-3.5-flash-lite`, `gemini-3.8-flash`), and two repetitions per
variant: 160 responses with no provider errors. Claude was excluded from live testing.

Before reading responses, the first repetition was selected for semantic review: all 20
scenarios, both models and both variants, yielding 80 reviewed answers. Variant and model
labels were hidden during a single Codex review. The remaining 80 answers are explicitly
unreviewed, not semantic passes. Review uses the case criteria, audited references and
targeted checks against shipped Pegasus game data; uncertain Cygnus claims are not declared
false solely because an older version differs.

| Whole-answer rating | Baseline (40 reviewed) | Candidate (40 reviewed) |
| --- | ---: | ---: |
| No material factual error found, with supported claims | 15 | 10 |
| Demonstrated material error | 6 | 7 |
| Demonstrated minor error | 3 | 1 |
| Consequential claim not verifiable from review evidence | 16 | 22 |
| Useful answer | 20 | 16 |
| Partially useful answer | 19 | 24 |
| Unhelpful answer | 1 | 0 |
| Natural presentation | 14 | 14 |
| Awkward presentation | 23 | 24 |
| Distracting presentation | 3 | 2 |

Accuracy, grounding, usefulness and naturalness are independent dimensions. These are
subjective, uncalibrated model-review counts, not production error rates, human preference
or a statistical model ranking. Repetitions are not independent scenario families. Some
control questions produced identical prompts in both variants; different answers there
also demonstrate sampling variability. The holdout families were evaluated after freezing
the implementation, and their observed answers were not used to tune it.

Deterministic checks confirm that generic Energy questions no longer receive Nomadic reserve
rules, Servitor questions do not acquire unrelated civic bonuses, and explicit comparisons,
hypotheticals and unknown identities retain conditional references. Average assembled input
fell from 18,933 to 18,000 characters, about 5%; this is not a token-cost or latency claim.

The broader review **does not establish an overall improvement**. Both variants still add
unsupported mechanics, infer familiar archetypes from unknown mod identifiers, overstate
what incomplete evidence proves, and use excessive persona boilerplate. The narrower
retrieval result should not be promoted to an answer-quality pass or used to justify another
generation/checking layer without further evidence. Next evaluations should include
sanitised real campaigns, non-English questions and human calibration of a small sample.

Task-owned local proof is retained under `artifacts/rule-applicability-2026-11-03/`:
the exact requests/responses and source hashes, blinded review packets and attribution,
separate variant keys, primary-reference receipts, unreviewed repetitions, and test logs.

## Retrieval diagnosis and hold: 2026-11-03

The original change is disabled in app defaults. Default mechanics prompts match the
pre-experiment baseline byte-for-byte across all 22 evaluation cases. The broader evaluation
suite and attributed review tooling remain available. A single explicit Python keyword,
exposed as `--experimental-applicability` only in the evaluation runner, permits further
testing without a new app setting, dependency or generation pass.

The first comparison's four-answer net usefulness decline comprised nine losses and five
gains. Inspection found three reasons to avoid interpreting that net count as a clean
retrieval effect:

- Filtering before ranking changed entire section membership. The Energy question gained
  planet-development and automation material; the neighbor question lost general combat
  guidance and gained economy material. The risk-taking question gained a logistics rule
  that one response overgeneralized to all ship upkeep. Generated scope notes also entered
  lexical ranking. These are plausible mechanisms, not proof of causation for an individual
  sampled answer.
- One lost useful rating came from a peaceful-development question whose complete inputs
  were identical. Generation variability and subjective review therefore contribute too.
- Removing reference material does not prevent inference from raw mod identifiers, and
  changing retrieval does not change the existing persona instructions or guarantee that
  a model correctly applies a supplied rule.

The diagnostic rerun compared the restored baseline, the frozen original change from
`4ed37f8`, and a narrower variant that selects sections first and then prunes scoped rules.
The narrower variant never adds replacement sections, and neither annotations nor generated
scope notes affect its ranking. Prompts and source hashes were retained.

Eight synthetic scenarios were evaluated with the same two exact Gemini model IDs, two
repetitions and three variants: **96 responses**, all completed and reviewed. Requests were
randomized within each repetition and interleaved across variants using isolated workers.
Production request assembly, persona and generation settings were unchanged. The set includes
the diagnosed cases, an explicit Nomad comparison, an identical-input control, and two fresh
mechanic families (colony growth and job automation). Earlier failure-guided families moved
to development before generation. The fresh cases did not guide implementation changes.

| Whole-answer rating | Baseline (32) | Original filtering (32) | Select, then filter (32) |
| --- | ---: | ---: | ---: |
| Useful answer | 21 | 21 | 21 |
| Natural presentation | 9 | 8 | 9 |
| Demonstrated material error | 5 | 3 | 4 |
| Consequential claim not verifiable | 12 | 9 | 10 |

Useful counts by repetition were 10/11 for baseline, 11/10 for the original change, and
9/12 for select-then-filter (16 answers per variant in each repetition). Both experimental
variants had three paired gains and three losses against baseline. On the two fresh families,
useful counts were 4/8, 5/8 and 5/8 respectively. All variants still produced unsupported
modded-identity inferences; job-automation answers often confused artificial Workforce with
assignment of existing pops. Excessive persona framing persisted.

Model and variant labels stayed hidden until all 96 ratings were frozen. A single Codex
reviewer checked disputed mechanics against shipped 4.4.6 files; provisional labels were
corrected before unblinding. In particular, half-Trade-to-Energy production conversion is
current, and natural/logistic Pop Growth is distinct from assembly and bonus organic growth.
These checks improve review discipline but do not replace human calibration.

This focused rerun did **not reproduce the earlier usefulness decline**, and it also did
**not demonstrate a retrieval benefit**. It covers fewer, deliberately selected scenarios
than the initial experiment, so raw counts cannot be compared across experiments or treated
as production quality rates. The apparent material-error differences are too small and
scenario-dependent to justify promotion. Keep filtering disabled; retain the narrow opt-in
for future repeated comparisons and human spot checks rather than adding another runtime
checking layer.

Validation: 695 Python tests passed, 27 optional-fixture tests skipped; Ruff lint and format
checks passed. Task-owned proof is retained in `artifacts/retrieval-diagnosis-2026-11-03/`,
including all requests/responses, the randomized schedule, source and prompt equivalence
receipts, frozen blinded ratings, primary-reference checks, paired summaries and test logs.

## Shipping configuration accuracy pass: 2026-11-04

This pass used production Advisor prompt assembly and unmodified provider settings:
ChatGPT `gpt-6.1-terra` and Gemini automatic **conserve** routing, which resolved to
`gemini-3.5-flash-lite`. The earlier Flash personality experiments did not establish
the quality of that Gemini default. Pre-PR and candidate prompts used the same current
transports and models, so this comparison measures prompt/reference changes rather
than historical default-model differences. Experimental applicability filtering and
experimental style prompts remained disabled.

The 4.4.6 references now explain artificial Workforce, planetary automation coverage,
naval-capacity units, Trade logistics versus ordinary ship upkeep, assembly inputs,
organic care under Rogue Servitor, and the scope of Nomadic reserves. Selected sections
carry their own necessary definitions. Market currency and the distinction between
population, Workforce and filled jobs also appear in the always-included baseline,
so unmatched or non-English questions receive those facts. These are shared mechanic
definitions, with no question recognizers, translated keyword lists or extra model calls.
Older versions and the partial 4.5 coverage retain their existing boundaries.

The initial ten cases used two samples per provider. An original held-out Chinese case
failed after the first corrections: all four candidate answers used obsolete market
currency, and two also inferred employment from total Workforce. Those cases became
regression cases before the baseline-definition change. Four additional inputs were
frozen before that change: Spanish market spending, Japanese Workforce interpretation,
ordinary research planning and a positive Nomadic-reserve control. They test transfer
and controls within related domains, not entirely unseen gameplay families. No changes
were made in response to their answers.

Across three reference revisions, 176 requests completed without provider errors. The
final configuration has 56 reviewed answers: 32 rerun original answers, all eight
unchanged original answers reused by exact payload equivalence regardless of rating,
and 16 fresh answers. Complete-answer ratings were frozen before revealing model and
variant labels. A single Codex reviewer scored accuracy, grounding, usefulness and
naturalness separately, allowing valid alternative strategies and minor variation.
Unsupported repair costs were not called disproved; selling Energy to obtain Trade
was not confused with treating Energy as the purchase currency.

| Configuration and sample | Material errors | Useful answers |
| --- | ---: | ---: |
| Pre-PR prompts, original cases, Terra | 4/20 | 16/20 |
| Final prompts, original cases, Terra | 0/20 | 20/20 |
| Pre-PR prompts, original cases, Flash-Lite | 6/20 | 3/20 |
| Final prompts, original cases, Flash-Lite | 2/20 | 9/20 |
| Final prompts, fresh inputs, Terra | 0/8 | 8/8 |
| Final prompts, fresh inputs, Flash-Lite | 2/8 | 6/8 |

**The shipping configuration does not pass the accuracy gate.** Flash-Lite still
misstates market currency in English, Chinese and both fresh Spanish answers. It also
falls below the predeclared 80% usefulness threshold per provider. Terra's 28 final
answers had no material errors found and were useful, with one unverified secondary
detail. This supports the Terra path within this sample; it does not establish universal
accuracy or justify more tuning against the same holdout. The next decision concerns
Gemini default suitability and needs a separate representative evaluation.

These synthetic, error-enriched samples and repeated model review do not estimate
production error rates or replace human calibration. Claude and direct OpenAI Chat
Completions were not live-tested; controlled tests cover the direct OpenAI contract.
Chronicle remains covered by shared-policy and provider-contract tests, not this live
Advisor sample. Local validation passed 710 Python tests (27 optional-fixture skips),
117 desktop unit tests, five targeted desktop journeys, TypeScript/Vite and Ruff checks.
Source hashes, frozen designs and amendments, all responses, review rationales and test
receipts are retained in `artifacts/shipping-accuracy-2026-11-04/`.

## Gemini default suitability: 2026-11-04

A separate bounded comparison tested the native Gemini Advisor at shipping commit
`94ce6d64b07824ba8d90a2ae775d8046155e2f16`. It compared the automatic conserve route
(`gemini-3.5-flash-lite`, provider-default thinking), that same route with **low**
thinking, the default route with one **79-word evidence-adherence prefix**, and the
automatic quality-first route (`gemini-3.8-flash`, provider-default thinking).
The prefix contained no game facts, example answers, language-specific rules or
persona rewrite. It asked the model to prefer supplied versioned references, preserve
units and exceptions, and distinguish verified actions from conditional plans.

Production Companion assembly supplied all prompts. Model and thinking comparisons
used identical system/user text; only the prefix arm changed the system text. The
native adapter, temperature 1.0, 8,192-token output allowance and bounded recovery
were unchanged. Request observations confirmed low thinking was sent and produced
reported reasoning tokens. The catalog and resolved model IDs were checked, and the
live run used the shipping `google-genai` 1.57.0 pin. See Google's
[thinking defaults](https://aistudio.google.com/docs/thinking#thinking-levels) and
[prompt guidance](https://aistudio.google.com/docs/prompting-strategies#gemini-3).

Before generation, the design froze six known development cases, six fresh cases,
four configurations and two samples per case: **96 answers**. Calls were interleaved
in randomized repetition blocks with concurrency two. All completed in one generation
attempt each, without transport errors, fallback models or incomplete responses.
Fresh cases varied empire identity and language and covered French market budgeting,
Portuguese organic care, Colossus prerequisites, Empire Focus, a dormant neighbor,
and a changed Hive economy. They include transfer within known failure families;
they are not six wholly unseen domains.

| Configuration | Development material errors | Development useful | Fresh material errors | Fresh useful |
| --- | ---: | ---: | ---: | ---: |
| Flash-Lite, shipping default | 5/12 | 2/12 | 5/12 | 5/12 |
| Flash-Lite, low thinking | 5/12 | 5/12 | 5/12 | 5/12 |
| Flash-Lite, short evidence prefix | 4/12 | 5/12 | 3/12 | 7/12 |
| Flash, provider defaults | 2/12 | 6/12 | 1/12 | 10/12 |

The predeclared selection rule required at least 10/12 useful development answers and
no recurring decision-changing failure. **No configuration qualified.** That decision
was frozen before fresh generation. The fresh comparison therefore supplies diagnostic
evidence, not independent validation of a selected replacement. No further prompt
iterations or post-holdout winner selection were performed.

The prefix did not resolve the glaring failure: both fresh French answers still used
Energy for market purchases. Low thinking also retained this pattern. Flash handled
the direct Spanish and French currency questions, but still used Energy-funded buying
advice in Chinese mineral planning, English food planning and Portuguese organic care.
Across all cases, Flash had 3/24 material errors and 16/24 useful answers, compared with
10/24 and 7/24 for the shipping Flash-Lite route. Mean observed response time was 15.65
seconds for Flash and 3.85 seconds for the default Flash-Lite route. These are run-specific
observations, not a production accuracy, latency or cost guarantee.

**No production prompt layer, thinking change or default-model change is justified by
this gate. The PR's Gemini accuracy hold remains.** The experimental prefix stays in
local evaluation artifacts; adding a production profile registry or additional inference
pass would add maintenance without a validated fix. Shared, versioned mechanics remain
the source of game facts. Any future provider-specific exception should be small,
centralized, tied to a reproduced consequential failure and tested against the shared
prompt on separate inputs before adoption.

All 96 complete answers received separate accuracy, grounding, usefulness and naturalness
ratings with configuration labels hidden. Each phase's attributed ratings were frozen
before opening its key. Review allowed minor errors, alternative sound strategies and
loose wording; unsupported repair costs, unknown mod effects and unverified causal links
were distinguished from demonstrated contradictions. Installed 4.4.6 scripts supplied
independent checks for market currency, organic care, focus progression and Colossus
requirements. A single Codex reviewer is not independent human calibration; synthetic,
error-enriched cases and repeated samples do not estimate production failure rates.
This pass does not evaluate Chronicle, Claude, direct OpenAI or other Gemini deployments.

The source code and user settings remained unchanged. Source/request hashes, frozen
design and selection, all raw answers, explicit review rationales, request settings and
usage, additional source checks and summaries are retained under
`artifacts/gemini-default-2026-11-04/`. Only this evaluation record is added to the PR;
the software validation recorded above applies to the unchanged runtime code.

## Flash default and upgrade behavior (2026-11-04)

The product default now prefers the latest available stable Gemini Flash for new
installations. Flash-Lite remains an explicit faster, quota-saving choice, and the
existing quota fallback remains in place. Settings and setup copy explain that
Flash can take longer and use more quota. A fallback label appears beneath an
Advisor answer without requiring the player to open response details.

This is a product decision informed by the comparison above, not a retrospective
pass of that experiment's selection gate. Its failed gate and all recorded model
errors remain valid. The tested short prompt layer and reasoning override were
not adopted; the Advisor voice and disabled applicability experiment are unchanged.

Before `electron-store` applies defaults, startup checks whether `settings.json`
already exists. Existing installations retain their saved routing preference;
legacy installations without that field retain the former Lite-first behavior.
Aliases are normalized, explicit model IDs are untouched, and an invalid legacy
value retains the former fallback. A fresh profile saves Flash-first immediately,
so restarting or later choosing Lite does not repeat the migration.

Local validation: 710 Python tests passed with 27 optional-fixture skips; all 128
desktop unit tests passed with the checkout's Python environment configured. Three
new Electron journeys verify fresh defaults, upgrade persistence, explicit model
preservation and the visible Lite fallback. All 13 onboarding journeys passed,
with one keyboard-focus test requiring an isolated rerun. TypeScript/Vite, scoped
Ruff and all production locale completeness checks passed. These software checks
do not establish model-answer accuracy; the focused campaign acceptance results
will be recorded separately.
