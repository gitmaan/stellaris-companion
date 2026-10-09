# 1.1.1-beta.1 release validation

This beta candidate combines the visual quality changes in [#66](https://github.com/gitmaan/stellaris-companion/pull/66), frontend performance improvements in [#69](https://github.com/gitmaan/stellaris-companion/pull/69), and transmission startup fixes in [#68](https://github.com/gitmaan/stellaris-companion/pull/68). Stable remains [v1.1.0](https://github.com/gitmaan/stellaris-companion/releases/tag/v1.1.0) until a separate stable release is published.

The candidate has completed automated integration and unpublished package validation. Keep final publishing receipts and package-review results with the release PR; broader gameplay and update/restart checks remain open below.

## Release notes

Use the same bullets in `electron/release-notes.md` and the GitHub Release body:

- Faster startup and more efficient rendering of long conversations.
- Improved HUD layouts, text scaling, and keyboard interactions.
- New transmissions appear once and remain unread while the app is hidden.

The frontend benchmark uses a ready mock backend and warm OS caches. Do not turn its measured startup or scrolling results into universal timing or frame-rate promises.

## Candidate validation

The unpublished [four-platform candidate build](https://github.com/gitmaan/stellaris-companion/actions/runs/37904431373) passed on `f6332aa`. Its [release PR](https://github.com/gitmaan/stellaris-companion/pull/70) records package downloads and review evidence. Publication rebuilds from the final `main` commit; verify that run and its final assets separately.

- [x] Run the combined renderer build, 105 desktop unit tests, 9 localization checks, and Electron journeys; all 10 candidate PR CI checks passed, including native transmission visibility in Linux CI's virtual display.
- [x] Run the release workflow manually with all four platforms and confirm publication is disabled; release validation and all platform builds passed.
- [x] Verify signatures, Gatekeeper assessment, and notarization tickets for both macOS architectures; validate versions, release notes, asset sizes, and SHA-512 checksums in all four platform manifests and the combined macOS feed.
- [x] Check packaged offline Japanese and first-use Settings/Chronicle loading from the archive on Apple silicon with Electron 43.7.9.
- [x] Check fresh startup and isolated fictional saved profiles on Apple silicon; preserve language, text scaling, chat drafts, onboarding completion, and a saved Stable update-track preference.
- [x] Exercise compact HUD layouts, text scaling, keyboard/IME focus, background Chronicle finalization, and transmission startup/reopening through automated Electron journeys; local package windows remain hidden.
- [x] Confirm the actual bundled Apple silicon backend starts in MCP stdio and Electron HTTP modes; CI also smoke-tests each platform backend before packaging.
- [ ] Check packaged offline language/page loading and native keyboard/IME/reduced-motion behavior manually on Windows, Linux, and Intel macOS.
- [ ] Check an isolated copy of a real 1.1.0 campaign profile, including saved chats, reading positions, provider credentials, and database migration.
- [ ] Load a representative save and exercise Advisor and Chronicle with a configured provider before calling the beta gameplay-validated.
- [ ] Check beta update feed eligibility and a controlled download/install/restart. Ordinary Electron journeys disable real updates, so they do not prove this packaged update path.

## Publication and follow-up

1. Integrate #66, replay only #69's own commits after the squash, then integrate #68 with the reviewed import and test adjustments. Keep the final branch checks green; the release PR records the merge commits.
2. Merge beta version/release preparation and confirm the tested source is on `main`. Keep package, renderer, backend, and Python project versions synchronized at `1.1.1-beta.1`; the MCPB version follows the app package.
3. Review unpublished packages from a manual workflow run. A manual run uploads Actions artifacts with `--publish never`; it does not publish a GitHub Release.
4. Only after package review, push `v1.1.1-beta.1` at the approved `main` commit. Tagging starts the publishing workflow: all platform builds upload to a draft, and finalization publishes the prerelease once every required job succeeds.
5. Verify the three beta manifests, both macOS architecture entries, release notes, and upgrade behavior. Stable must still resolve to v1.1.0 and the promo site must remain unchanged.
6. Capture feedback from representative gameplay. Use `1.1.1-beta.2` for corrections, then a new `1.1.1` version/tag for stable promotion; do not merely clear the prerelease flag on a beta build.

Existing users opt in through Config → More Settings → Update Track → Beta. Publishing reaches all users already on that track. Fresh beta profiles default to Beta; saved preferences are preserved. Switching back to Stable does not downgrade an installed beta and takes effect when a newer stable release is available. Test profiles and packaged-app checks must not overwrite the user's installed app or personal campaign data.

## Previous stable release record

The following records the v1.1.0 release and its broader outstanding validation. Those open checks are carried forward; preparing this beta does not mark them complete.

Stable v1.1.0 combines [`v1.1.0-beta.1`](https://github.com/gitmaan/stellaris-companion/releases/tag/v1.1.0-beta.1) with campaign chat restoration and Chronicle continuity improvements. Both update channels receive v1.1.0 after publication.

This list records remaining validation follow-ups. The beta passed release CI and all four platform builds, including macOS signing and notarization. Apple silicon startup, onboarding, saved completion, and the real bundled backend were checked locally; the broader packaged-provider and update/restart checks below remain open.

## Included since v1.0.0

- ChatGPT account connection for Advisor and Chronicle, simpler onboarding, and a shared model picker with saved preferences.
- Broader localization across onboarding, settings, campaign history, and desktop controls.
- More reliable campaign selection, save ingestion, and stored provider credentials.
- Simpler AI setup, stable Gemini model selection, and bounded recovery that preserves saved Chronicles when generation fails.
- Updated Gemini defaults to 3.8 Flash and 3.5 Flash-Lite, with a lower-cost reserve and quota cooldowns for Advisor and Chronicle.
- Guided MCP Relay setup for supported AI apps, with campaign readiness and optional Chronicle writing controls.
- Simpler public Chronicle sharing; existing unlisted publications retain their visibility.
- Provisional Cygnus 4.5/4.5.1 mechanics guidance and selected-policy reporting. Coverage is partial, not full save-format certification.

## Validation follow-ups

- [x] Complete campaign chat restoration and Chronicle coverage, reading, editing, Undo, and manual updates.
- [ ] Validate a real Cygnus 4.5/4.5.1 save through ingestion, briefing, Advisor, and Chronicle; check population/faction and federation data. The current local fixture is Corvus 4.2.4. See [coverage audit](../patches/audits/4.5.1.md).
- [ ] Confirm MCP Relay setup and a campaign query in each advertised client on its supported platform.
- [ ] Run the final CI suite and packaged-app smoke checks, including provider setup, Chronicle refresh/sharing, and update/restart behavior.
- [x] Recheck Gemini model availability and retirement dates: on October 2, 2026, Google's [model catalog](https://ai.google.dev/gemini-api/docs/models) lists 3.8 Flash and 3.5 Flash-Lite as stable, and the [deprecation schedule](https://ai.google.dev/gemini-api/docs/deprecations) lists May 7, 2027 as the earliest shutdown for the 3.1 Flash-Lite reserve.
- [ ] Verify ChatGPT sign-in, protected credential storage, and an Advisor and Chronicle request in packaged macOS, Windows, and Linux builds.
- [x] Prepare `1.1.0` with the beta release bullets and two short continuity notes.
- [x] Review the beta release notes and packaged-build results, then publish the beta when requested.

## What users will see

- Stable and Beta users receive v1.1.0. Their saved channel preference is preserved.
- Fresh beta installations select the Beta update channel by default. A saved channel preference is preserved, and updates never downgrade the app.
- The update dialog shows the version, up to five release bullets, download progress, and an explicit Install & Restart action. The final GitHub Release body and packaged release notes must use the same approved bullets.
- Existing installations keep their saved provider and model preferences. New installations use the simpler First contact onboarding, with ChatGPT leading the provider choices.

Keep the remaining checks current. Do not describe Cygnus support as complete until the save validation above passes.

## Pending visual quality changes

- [x] Verify fixed shell/composer geometry, compact Chronicle reading, shared modal focus, reduced motion, pending drafts, and localized recovery actions with mocked Electron journeys. See [Visual quality conventions](visual-quality.md).
- [ ] During the next packaged release check, exercise native keyboard/IME focus and reduced-motion behavior on macOS, Windows, and Linux; the local visual proof uses an unbundled Electron renderer.

## Pending frontend performance changes

- [x] Verify local language/page chunks, initial backend-status replay, retained drafts and settings, long-chat rendering, and background chapter finalization with hidden Electron journeys. See [Frontend performance](frontend-performance.md).
- [ ] During the next packaged release check, verify offline language switching and first-use page loading from the packaged archive on Electron 43.7.9 across supported platforms.
