# Model Game Knowledge

Stellaris Companion gives every supported model versioned mechanics context for the player's
save. Complete snapshots provide a factual baseline; focused release-note packs provide partial
coverage when a new game version has not yet been fully audited.

## How It Works

1. The app reads the Stellaris version from the save.
2. The shared resolver selects an exact snapshot, a compatible snapshot and overlays, or a
   notes-only pack for an audited breaking release line.
3. The Advisor selects relevant sections using headings, rule labels, and rule text. Chronicle
   receives the full resolved pack. MCP Advisor Briefing returns the same Advisor prompt and
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

Before shipping, run `tests/test_game_knowledge.py` and record cross-provider responses with
`scripts/experiments/eval_game_knowledge.py` for human review. Test stale premises that a model
with an older knowledge cutoff is likely to answer confidently but incorrectly.

Use `--suite cygnus` for the 4.5.2 cases and `--suite pegasus` (the default) for 4.4.6.
Advisor evaluations use question-based selection just like the app; Chronicle evaluations use
the full pack. `--list` lists the selected suite without making model calls. A unit-test pass
checks prompt assembly, not model accuracy; record provider responses and review them separately.

Official release announcements are available from the
[Stellaris Steam news feed](https://store.steampowered.com/news/posts/?appids=281990).
