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

## Versioned mechanics

Question-based retrieval can also include one section relevant to verified empire
identity. Unknown mod identifiers do not acquire rules through name similarity.
Optional scope annotations filter specialised sections or individual rules before ranking.
Observed identity can support a scope; an explicit question can also request it for a
comparison or hypothetical plan. Unknown conditions remain conditional, and omitted civic
or DLC evidence does not establish unavailability. Gameplay prose stays in Markdown;
`patches/applicability.json` supplies reusable scope metadata without copying the facts.
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

Applicability is intentionally partial. Existing lexical topic selection remains in place,
and unannotated mechanics follow its prior behavior. An explicit `is_nomadic` observation is
supported by the scope interface, but current extraction does not supply that field; it is
never inferred from authority or DLCs. The change adds no generation passes, eligibility
engine, tool loop or required answer template.

## Applicability experiment: 2026-11-03

The candidate adds scope metadata to existing versioned Markdown. The control uses retrieval
and references from commit `0682bb2`; both variants use identical production request
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
