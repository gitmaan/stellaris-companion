# User-report regression set

Each confirmed, fixed user report of the app misreading a game ("I won those
battles", "my Grand Archive is finished") has at least one case here, and every
case runs in CI. Issue #11 was fixed in March and came back as #44 in August;
this directory exists to stop that from happening again.

**Rule: when you fix a user-report issue, add its case here before closing the
issue.**

## Adding a case

1. Find the deterministic layer the fix lives in: extractor, signals/events,
   `backend/core/model_briefing.py`, campaign evidence or the Advisor prompt
   policy, or Chronicle/DB.
2. If an existing test elsewhere in `tests/` already encodes the reported
   situation precisely, register it as `referenced` instead of copying it.
3. Otherwise write `test_issue_<N>_<what>` in a `test_report_*.py` module here,
   with a docstring that links `https://github.com/gitmaan/stellaris-companion/issues/<N>`.
   Build the smallest hand-written synthetic save that shows the reported
   situation (`_synthetic.py`). Never use real or extracted saves; see
   [the save handling guide](../../docs/report-save-sharing.md).
4. Register every case in `registry.py`, with the fix commit or PR and the
   layer.
5. Revert the fix locally (don't commit that), check that the case fails, then
   restore it. Record the result in `verified_against_revert`.

`test_registry.py` runs every registered node ID in a child pytest. It fails
if any is missing, skipped or failing, or if a `test_issue_*` case here is not
registered. A case can't quietly depend on an optional real-save fixture.

## Synthetic saves

`_synthetic.py` serves a hand-written gamestate (section -> entries) through
the Rust session API. With it, a case runs the real production path in-process:

- `ingest_synthetic_save` runs the ingestion worker job (`get_complete_briefing`,
  signals, history enrichment, worker metadata).
- `persist_snapshot` records the payload in a real SQLite `GameDatabase`, which
  also runs event detection.
- `advisor_request` activates the payload in a `Companion` and returns the
  system prompt and model-facing JSON the Advisor would send. The provider
  only records the request; no model is called.

Sections a case leaves out behave like empty sections, so only the facts that
matter to the report need writing.

## Covered reports

| Issue | Report | Layer | Cases |
| --- | --- | --- | --- |
| #11 | Allied battles counted as the player's | extractor | new + referenced |
| #44 | 0:47 "defeats" while winning | extractor + model briefing | new + referenced |
| #12 | Completed Grand Archive "under construction" | extractor + signals/events/DB | new + referenced |
| #15 | Naval usage read as the naval cap | extractor + Advisor prompt policy | new + referenced |
| #16 | Completed Dyson Swarm "under construction" | extractor | referenced |
| #79 | Nomad economy read as failing mining; Festival upkeep labelled as the reserves' monthly change | nomads extractor + briefing identity + model rules + knowledge retrieval | new + referenced |
| #81 | Rogue Servitor denied over a "missing" DLC | metadata + campaign evidence + prompt | new + referenced |
| #83 | Chronicle dates after loading an older save | Chronicle + database | referenced |
| #95 | Story lost after changing the player's empire | ingestion + narrative ancestry + Advisor/Chronicle/MCP | new + referenced |
| #104 | Research options under made-up names; technologies in progress counted as researched | Rust lookup + technology extractor + name catalog + model briefing + events + MCP | new + referenced |

`registry.py` has the node IDs, root causes, fixes, and revert-verification
status. Excluded reports and the reasons are listed in `NOT_COVERED`.
