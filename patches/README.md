# Model Game Knowledge

Stellaris Companion gives every supported model versioned mechanics context for the player's
save. Complete snapshots provide a factual baseline; focused release-note packs provide partial
coverage when a new game version has not yet been fully audited.

## How It Works

1. The app reads the Stellaris version from the save.
2. The shared resolver selects an exact snapshot, a compatible snapshot and overlays, or a
   notes-only pack for an audited breaking release line.
3. The Advisor selects sections using headings, rule labels, and rule text, plus at
   most one additional section matching verified empire identity. In-app Chronicle uses
   its supplied briefing for topic selection; consumers without a topic query retain the
   full resolved pack. Applicability filtering is experimental and disabled in app defaults.
   When explicitly enabled for evaluation, it prunes specialised rules after selecting
   sections, without filling the freed slots. Explicit comparisons and hypothetical builds
   retain conditional references. MCP Advisor Briefing returns the same Advisor prompt and
   coverage metadata, in both structured output and an untruncated text block.
4. Unknown newer release lines do not receive older mechanics presented as current.

The 4.5, 4.5.1, and 4.5.2 Cygnus files are partial release-note coverage. They do not
establish that the save extractor supports Cygnus. A future snapshot cannot change the
coverage of an earlier save: only readable snapshots at or before its version, on the
same side of a breaking-release boundary, are eligible.

Snapshots describe current behavior rather than patch history. Campaign evidence remains the
authority for what happened in a particular save, and modded mechanics may differ from the
unmodded baseline documented here.

## Why Snapshots

Models of any age can reproduce obsolete Stellaris systems because older information is common in
their training data. A self-contained snapshot supplies the current system from first principles
instead of assuming that the model already understands every earlier redesign.

In a controlled test of six deliberately stale premises across five model families, the compact
patch context produced 1 clearly correct response from 29 usable answers. The self-contained
4.4.6 snapshot produced 30 accurate or acceptable answers from 30 responses. Results were judged
by a maintainer for substantive correctness, allowing normal variation in wording.

## Maintaining Snapshots

- Use final Paradox release notes first, followed by shipped unmodded game data for numerical rules.
- Keep the current stable snapshot self-contained, including foundational mechanics that remain true.
- Keep universal resource and quantity definitions in the always-included baseline, and
  make topic sections understandable when retrieved alone. An unmatched question must
  retain essential meanings without requiring an English topic match. Keep those facts
  within their verified version boundary; inclusion does not prove that a model follows them.
- Add small overlays for hotfixes, then fold them into a fresh snapshot before history accumulates.
- When a new release changes an underlying mechanic before shipped data can be checked, add
  source-backed release-note deltas for that release line. The resolver labels these partial
  and does not import the prior release's snapshot. Publish a complete snapshot only after
  its current-state claims have been checked against the shipped game.
- Do not add open-beta mechanics to a stable snapshot.
- Avoid subjective benchmarks unless authoritative sources and relevant game settings support them.
- Give hotfixes descriptive topic headings and bold rule labels. Selection also searches rule
  text, so a Branch Office question can find a rule under Economy without requiring that exact
  heading. Shared topic words do not supersede an entire older section.
- When a rule replaces an older one, add `<!-- supersedes-rule: Exact older rule label -->`
  to the newer file. The loader removes only matching older top-level `* **Label:** ...`
  or `- **Label:** ...` bullets, including indented continuation lines, before selecting topics.
  The replacement must contain the complete current rule. The directive and other HTML comments
  never reach model prompts. Use a unique, exact label; unrelated older rules remain available.

Source and coverage decisions for each stable snapshot live in `patches/audits/`.

## Applicability annotations

Annotations are inert in the default app path and are stripped without changing the baseline
mechanics prompt. Use `--experimental-applicability` in the evaluation runner to opt into
filtering. Do not enable it for app consumers until repeated comparisons establish useful,
natural and accurate advice beyond the development cases. The initial experiment did not.

Keep gameplay prose in these Markdown files. `applicability.json` contains only reusable
scope names, identity conditions and explicit topic phrases; it does not duplicate rules
or their numerical values. Versions and source audits remain owned by the existing packs.

For a section whose rules all concern the same system, put its scope after the heading:

```markdown
## Operational Reserves & Nomad Economy
<!-- applies-to: nomadic -->
```

For a specialised rule inside a mixed section, keep the annotation on the rule's line:

```markdown
* **Branch Offices:** <!-- applies-to: corporate --> Branch Offices use Trade for establishment.
```

Inline annotations are replaced together with their rule by `supersedes-rule`; they
cannot accidentally attach to the following rule. Use section scopes only when every
rule belongs to that scope. Unannotated rules retain existing retrieval behavior.

Scope conditions use supplied canonical authority, origin, civic membership or an explicit
boolean `is_nomadic`. They are retrieval hints, not complete unlock or eligibility checks.
Missing fields, malformed values, unrecognised identities and omitted civics remain unknown.
Do not infer Nomadic mode from authority, an old origin, an identifier substring or DLC
presence. The current extractor does not establish `is_nomadic`; without such an explicit
observation, direct Nomadic questions still receive conditional reference material.

Experimental filtering preserves the original topic selection, scoring only gameplay text.
It then retains scoped rules when an observed condition supports them or explicit topic
phrases request them for comparisons, plans and explanations. Generated scope notes are
added afterward, marked as conditional or about a different identity where appropriate.
No other section is promoted when a scoped section is removed. Full-reference consumers
retain conditions when the experiment is explicitly enabled too.
These notes are model context, not a required format for the player's answer.

Topic matching is lexical and the maintained phrases currently use English. This is not a
multilingual semantic search layer. Add translated names or a different retrieval strategy
only with representative evaluation; an unmatched phrase must not be presented as proof
that a mechanic is unavailable.

Keep topic phrases specific: names and distinctive concepts such as `operational reserves`,
not broad words such as `energy` that apply to many systems. New scopes should address a
demonstrated ambiguity. Existing scopes can be reused with one annotation, without changing
Python. Tests validate the registry and every shipped annotation; in experimental mode,
an unreadable registry omits affected scoped references rather than treating them as generally
applicable. It cannot affect the default path.

Run `tests/test_knowledge_applicability.py` alongside the existing knowledge tests. Include
positive cases, unknown conditions and questions about other empires when adding a scope.
Do not tighten retrieval just to remove a phrase from one previously failing answer.

Before shipping, run `tests/test_game_knowledge.py` and record cross-provider responses with
`scripts/experiments/eval_game_knowledge.py` for human review. Test stale premises that a model
with an older knowledge cutoff is likely to answer confidently but incorrectly.

Use `--suite cygnus` for the 4.5.2 cases and `--suite pegasus` (the default) for 4.4.6.
Use `--suite evidence` for synthetic campaign identity, eligibility, strategy, and calculation
cases. `--repeats 2` records independent samples; `--snapshots-dir` allows controlled reference
comparisons. Advisor evaluations use question and identity selection just like the app; Chronicle evaluations use
the full pack. `--list` lists the selected suite without making model calls. A unit-test pass
checks prompt assembly, not model accuracy; record provider responses and review them separately.

## Broader answer-quality evaluation

`--suite applicability` loads data-only scenarios from
`scripts/experiments/cases/applicability.json`. They include ordinary advice, calculations,
identity correction, modded identities, comparisons, hypothetical choices and missing data.
The cases carry sourced review criteria and are split into `regression`, `development` and
`holdout` families. `--split` selects one group; `--list` never calls a provider.

Freeze a candidate before running the holdout. If a holdout failure guides an implementation
change, move that family into development and add a fresh holdout family. Avoid putting
paraphrases of the same mechanic on both sides of the split. Review full answers, including
secondary claims, and allow alternative valid strategies and wording.

```sh
python scripts/experiments/eval_game_knowledge.py --suite applicability \
  --provider gemini --models MODEL_ID --repeats 2 --variant baseline \
  --json-out tmp/baseline.json
python scripts/experiments/eval_game_knowledge.py --suite applicability \
  --provider gemini --models MODEL_ID --repeats 2 --variant candidate \
  --experimental-applicability \
  --json-out tmp/candidate.json
python -m scripts.experiments.eval_review prepare tmp/baseline.json tmp/candidate.json \
  --out tmp/review.json
python -m scripts.experiments.eval_review summarize tmp/review.json --key tmp/review.key.json
```

Use exact model IDs for controlled comparisons and retain the baseline's code/reference
revision as well as its recorded requests. The normal runner exercises the production
Advisor assembly. Change one component at a time; a different model or reference pack is
not evidence of a retrieval-only improvement. Chronicle cases still exercise the structured
adapter rather than the full archive assembly.

The review packet hides variant names, model names and retrieved prompts; its separate key
preserves those receipts. Ratings start blank. Attribute each review to a named human or
model and score accuracy, grounding, usefulness and naturalness separately. A plausible but
unverified detail is not automatically false, and a correct refusal may still be unhelpful.
Use independent applicable references when judging correctness, not only what retrieval
selected. The report keeps unrated answers, provider errors and repeated trials visible;
it never promotes transport success or an unreviewed response to a semantic pass.

Run inexpensive deterministic checks on every PR. Run live comparisons for relevant changes
and newly resolved model versions, with a small human spot check of failures and a random
sample when available. Keep automated/model review explicitly labelled. Current synthetic
cases do not establish a production error rate or human preference, and should be expanded
with representative, sanitised campaign fixtures as evidence accumulates.

The first controlled applicability experiment is recorded in
[`docs/campaign-evidence.md`](../docs/campaign-evidence.md#applicability-experiment-2026-11-03).
It verified narrower retrieval but did not demonstrate better overall answer quality.
The [diagnostic rerun](../docs/campaign-evidence.md#retrieval-diagnosis-and-hold-2026-11-03)
also found no overall usefulness benefit. App defaults retain baseline retrieval; the
narrower post-selection experiment requires explicit opt-in.

Official release announcements are available from the
[Stellaris Steam news feed](https://store.steampowered.com/news/posts/?appids=281990).
