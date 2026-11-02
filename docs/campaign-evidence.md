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
