# 1.1.0 release validation

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
