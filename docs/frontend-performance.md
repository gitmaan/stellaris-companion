# Frontend performance

The renderer keeps the HUD, text sizing, motion preferences, reading anchors, and
draft behavior described in [Visual quality](visual-quality.md).

## Loading and background work

- Preload retains the latest backend status and replays it to new subscribers.
  Loading a language or mounting a page no longer loses the initial status event
  and waits for the next health poll. This adds no backend requests or polling.
- English is bundled with the shell as an offline fallback. Other language
  catalogs, including the pseudo-locale, are local dynamic imports. Startup waits
  for the selected catalog before showing the UI. A missing startup catalog falls
  back to English; a failed explicit language switch keeps the previous setting.
- Advisor mounts at startup. Settings and Chronicle load on first use and remain
  mounted afterward, preserving unsaved settings, drafts, and reading position.
- Chronicle also mounts when the document becomes hidden, even if it has never
  been opened. Its existing background chapter finalization remains available
  while the user plays Stellaris. Inactive visible tabs defer metadata refreshes
  until the reader is opened. Save ingestion is unchanged.
- Virtual chat rows keep stable ref and action callbacks. Markdown rendering has
  its own memo boundary, so scrolling and Copy feedback do not rebuild unchanged
  response content. Ref and height caches discard messages outside the history
  window.

## Measuring a change

Build each checkout before comparing it. From the candidate's `electron` directory:

```bash
npm run build:renderer
npm run benchmark:renderer -- --app-root /path/to/baseline --output /tmp/before.json
npm run benchmark:renderer -- --output /tmp/after.json
```

The runner creates fresh temporary profiles, a deterministic local mock backend,
and hidden, non-focusable Electron windows. It does not use real saves, provider
credentials, the user's clipboard, or visible desktop windows. Profiles and
processes are removed in `finally` blocks.

Five launch samples report the median time to the shell and to the restored chat.
The latter can expose waits for the main-process health polling interval. The detailed first
sample includes a 150-turn history (300 messages), 180 scroll frames, a three-second
idle period, and a short typing sequence. CDP reports renderer task, script, and
layout duration; Electron reports renderer process memory. Parsed-script events
enumerate local modules because Chromium Resource Timing omits `file://` loads.

Run comparisons on the same machine without concurrent builds or tests. These
are diagnostic measurements with warm OS caches, not timing assertions, visible
window frame-rate claims, or predictions for every user's hardware. Idle CPU
samples are particularly noisy. Use the JSON receipts to retain individual
samples and runtime versions, not just the most favorable number.

`frontend-performance.spec.js` checks actual module loading, saved-language
startup, catalog failure recovery, retained Settings state, hidden chapter
finalization before the first reader visit, bounded chat DOM size, and stable
Markdown nodes during scrolling and Copy feedback. Existing localization,
Chronicle, conversation, and visual-quality journeys cover the other behaviors.

## October 9, 2026 comparison

Baseline: visual-quality commit `2e4a7f8`, Electron 43.2.0. Candidate: this change,
Electron 43.7.9. Both ran on the same Apple M4 Max, macOS 27 arm64 machine using
the procedure above, with no concurrent test/build run.

| Measurement | Before | After |
| --- | ---: | ---: |
| JavaScript loaded for English Advisor startup, minified bytes | 1,108,063 | 615,087 |
| Median launch to shell, five fresh profiles | 1,003 ms | 594 ms |
| Median launch to restored chat with a ready mock backend | 5,708 ms | 607 ms |
| Scripting during the 180-frame long-chat scroll | 706 ms | 128 ms |
| Renderer task time during that scroll | 986 ms | 327 ms |
| Scroll frame interval, 95th percentile | 18.6 ms | 18.5 ms |

The startup-ready improvement removes a missed status event and its subsequent
polling wait; it does not predict Python startup, save ingestion, or AI response
time. The scroll measurements describe one synthetic workload. Idle CPU and
typing samples did not establish a material improvement. Raw JSON receipts retain
individual launches, heap/process-memory samples, runtime versions, and timings.
