# Model Game Knowledge

Stellaris Companion gives every supported model a curated mechanics snapshot for the version in
the player's save. This provides Gemini, OpenRouter, Ollama, LM Studio, and custom providers with
the same factual baseline even when a model's training cutoff predates the game release.

## How It Works

1. The app reads the Stellaris version from the save.
2. The shared resolver selects an exact snapshot or the newest compatible snapshot and overlays.
3. The context is added to both Advisor and Chronicle prompts alongside extracted campaign facts.
4. Unknown newer release lines do not receive older mechanics presented as current.

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
- Do not add open-beta mechanics to a stable snapshot.
- Avoid subjective benchmarks unless authoritative sources and relevant game settings support them.

Before shipping, run `tests/test_game_knowledge.py` and record cross-provider responses with
`scripts/experiments/eval_game_knowledge.py` for human review. Test stale premises that a model
with an older knowledge cutoff is likely to answer confidently but incorrectly.

Official release announcements are available from the
[Stellaris Steam news feed](https://store.steampowered.com/news/posts/?appids=281990).
