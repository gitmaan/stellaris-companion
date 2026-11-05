# Trade foundation retrieval — 2026-11-05

## Defect and scope

A 4.3.0 campaign's full resolved reference contained the market-currency rule,
but the Advisor selected Trade & Logistics, Trade & Combat and Origins & Civics
without the introductory table containing that rule. The 4.3.5 snapshot also
placed the rule in an optional topic section. Generic or non-English questions
could omit both currency and stockpile meaning.

The selector already retains `Critical 4.x Baseline` sections. Add a compact
Trade foundation to the 4.0 notes and 4.3.5 snapshot using that existing mechanism.
It identifies the purchasing resource, automatic collection, the removal of
Trade Routes, and the distinction between stock and monthly flow. Keep reference
tables and other mechanics subject to normal topic selection.

Also clarify the older Trade Policy sentence: policy controls a converted portion
and a retained portion. Its previous wording could imply the entire net balance
was converted away. No policy percentage, conversion ordering, spending threshold
or preferred strategy is introduced.

This patch changes two knowledge files. It does not change the section-ranking
algorithm, resource extraction, account presentation, provider adapters or model
selection. Baseline for isolation is the local account-presentation candidate
`2dd791629f55879813c6667f7a9be15372811a04`.

## Sources and version limits

- [Official Phoenix overview](https://store.steampowered.com/news/posts/?appids=281990&enddate=1746539403&feed=steam_community_announcements):
  the May 2 announcement describes Trade as a stored resource used for market
  purchases and the removal of Trade Routes. This is the pre-release overview,
  not an independent audit of all final 4.0 mechanics.
- [Official 4.0.22 release](https://steamstore-a.akamaihd.net/news/externalpost/steam_community_announcements/1808601382441482):
  released policy allocations explicitly include retained Trade as well as other
  outputs. Their exact percentages are not generalized backward to 4.0 or added
  to this patch. Both articles were retrieved from the official Steam news API
  and retained in the local proof artifacts.
- Existing [4.4.6 audit](4.4.6.md) and recorded campaign budgets independently
  support the stockpile/currency distinction in later supported saves. The
  4.4.6 snapshot already includes this foundation and is unchanged.

The existing resolver still labels incomplete older coverage as partial. The
4.5 breaking boundary prevents these older facts from being imported into
Cygnus; unsupported newer and unknown versions remain unsupported. Selection
does not upgrade coverage or establish mod compatibility.

## Verification

- 32 new regression checks cover the older note chain, snapshot and overlays,
  unmatched/non-English questions, zero topic slots, actual Advisor requests
  across four provider adapters, Chronicle and excluded versions.
- Before the change, 27 of these checks failed and the five boundary checks
  passed. After the change, all 32 pass.
- 193 focused knowledge, applicability, consumer, MCP, evaluation-harness and
  resource-account tests pass. One existing test was updated because an unmatched
  4.3.5 question now correctly receives the compact foundation instead of an
  empty topic-selection notice.
- 120 before/after local prompt comparisons cover twelve versions, five question
  forms and two topic limits. The currency rule becomes available in 64 previously
  missing cases. Coverage metadata remains identical. Topic headings other than
  the added baseline are unchanged in this matrix.
- All tested 4.4.6, 4.5, unsupported-newer and unknown-version prompts are byte-for-byte
  unchanged. No new model answers were generated, so this is retrieval proof,
  not evidence of improved answer quality.

## Review handoff

Local artifacts under `artifacts/retrieval-baseline-2026-11-05` retain before/after
prompts, sources, test results and a user review packet. The packet has eight
existing answer pairs from the earlier account experiment: source facts, exact
excerpts, complete responses and unfilled human ratings. A/B ordering varies;
model identities and previous judgments are kept in a separate answer key.
These targeted examples support calibration, not fresh acceptance testing.
Campaign contents and responses remain outside Git.
