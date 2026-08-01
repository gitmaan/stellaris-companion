# Model Game Knowledge

The model receives a curated current-state mechanics snapshot for an exactly supported
Stellaris version. These files are a factual compatibility layer, not release notes and not a
replacement for save evidence.

## Source Order

1. Final Paradox release notes for the stable game build.
2. Shipped unmodded game data from that exact build for numerical rules.
3. Focused in-app extraction fixtures for campaign-state semantics.
4. Dev diaries only when final notes and shipped data do not define the behavior.

Do not promote open-beta mechanics into a stable snapshot. Keep beta knowledge in a separately
versioned snapshot only when the app explicitly supports that beta build.

Official announcement index:
https://store.steampowered.com/news/posts/?appids=281990

## Snapshot Rules

* Name snapshots with the full verified version, such as `snapshots/4.4.6.md`.
* Describe current behavior, without upgrade history or obsolete values.
* Preserve topic headings so models can navigate the pack reliably.
* Keep foundational mechanics from earlier major-version releases when they remain current. A
  snapshot must be usable by a model whose built-in knowledge predates that major version.
* Avoid subjective benchmarks such as a "typical" empire size unless an authoritative source
  defines them and the relevant galaxy settings are available.
* State applicability and evidence limits alongside mechanics that could otherwise create false
  campaign claims.
* Prefer a fresh stable snapshot over indefinitely accumulating release overlays.

Before shipping a snapshot, verify hard numerical claims against the exact installed build, run
`tests/test_game_knowledge.py`, and manually review the benchmark responses recorded by
`scripts/experiments/eval_game_knowledge.py`. Include stale-premise cases that exercise the major
systems a model with an older knowledge cutoff is most likely to answer incorrectly.
