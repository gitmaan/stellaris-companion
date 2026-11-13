# Beta 1.1.3-beta.1 candidate

The first beta after stable 1.1.2. It reads the empire's origin (#127, reported in #125),
shows the empire's ethics, civics, authority and origin in the Advisor panel by their
in-game names (#128), reads every resource the save lists for the player and no longer
only eighteen of them (#129), tells the Advisor which mods a campaign is played with
(#130), and names resources in the Advisor's briefing as the game does (#131). Stable
remains 1.1.2. Merge this after #130 and #131: the release notes describe both.

## Release validation

Done before the tag, on main with #130, #131 and this change merged together locally:

- 1038 tests pass and ruff is clean.
- `scripts/check_local_saves.py`: all 12 sampled real saves pass.
- Briefings of 22 real saves were compared before and after each change. #129 adds the
  Trade stockpile and budget to every save and changes nothing else; #130 changes nothing
  for an unmodded save; #131 changes the keys of the economy tables only.
- On a real modded save (Gigastructural Engineering, attached publicly to #79) the
  Advisor's request names both mods, and the origin reads as "Voidfarers".
- The new live Advisor question about monthly income, 8 campaigns, one run each on the
  ChatGPT plan: 96 of 96 resource names exact with in-game names, 95 of 96 with IDs only,
  and the same numbers in both.
- Three campaigns recorded by the 1.1.2 code and continued by this code record no event
  at the handover. The same pairs of saves record none under either version alone, so
  this shows that nothing is invented, and does not exercise a real change.

Still to do before the tag: the candidate build on four platforms and the installed-app
journeys on Windows.

Not claimed:

- #125 also reports wrong ethics. That does not reproduce on any local save and awaits
  the reporter's save; this beta does not change how ethics are read.
- Whether a mod's own text is found on a player's machine has not been checked against a
  real mod install. Mods packed as archives are not read. A mod's crisis is not
  recognised as a crisis.
- No local save holds a resource whose ID differs from its name beyond the common ones
  ("Valor", a mod's resources); that case is covered by tests with made-up game text.
- The Chronicle is not told about mods.

## Earlier release records

# Stable 1.1.2 candidate

Promote 1.1.2-beta.5 to stable. The app is the beta.5 code with only the version and the
release notes changed, so stable users on 1.1.1 receive all five betas at once (#84 to
#124). The maintainer approved the five lines in `electron/release-notes.md`, including
the thanks to @LightArchon1 and @arseking as the fifth line: the update dialog of the
installed 1.1.1 shows the first five bullets and nothing else. The notes were rendered in
that dialog and fit without scrolling at 1000x700 and at the 800x600 minimum.

## Upgrade from 1.1.1

- Three local campaigns were recorded by the 1.1.1 code and continued in the same history
  database by this code. The database opens and gains `campaign_sources` and
  `story_continuations`; nothing existing is altered. No event was invented at the
  handover. One "Researched" event was skipped at the first save after the update in two
  of the three, as intended: a snapshot from before the corrected technology reading is
  not compared.
- The Advisor briefing, the recap and the Chronicle were built from data stored by 1.1.1
  with a stand-in model, without errors.
- One late-game save took 2.3s against 2.2s, with peak memory about 12% higher.
- Those stretches of play were quiet: no war or federation changed across the handover, so
  those paths rest on the automated tests.

## Validation and publication

- Complete combined Python, Rust, desktop, localization and renderer checks on the
  release pull request, and `scripts/check_local_saves.py` locally.
- Tag the merged main commit as `v1.1.2`. The publishing workflow rebuilds all four
  platforms, repeats the installed Windows journeys, publishes the `latest` feeds with
  matching `beta` aliases, and synchronizes the download site's release facts.
- Verify macOS signing and notarization, package versions, both subscriber tracks and
  every payload checksum.
- Publish the site's 1.1.2 changelog page (English only for now) on the day of release,
  with its date set to that day.
- The 1.1.1 feedback invitation targets exactly 1.1.1 and expires on 2026-11-24; 1.1.2
  ships without an invitation of its own.

Not claimed: everything listed as not claimed for beta.5 below still stands. Each beta was
downloaded 5 to 10 times against about 400 for 1.1.1, and no beta user reported a
regression. Finding the game and reading its text ran on one macOS install only; on
Windows and Linux it is covered by tests with built folders and falls back to the shipped
names when no game is found. Whether 1.1.1 can reopen a database this version has written
was not tested. #83 and #86 still await reporter confirmation.

## Earlier release records

# Beta 1.1.2-beta.5 candidate

This beta reads names from the player's installed game (#115, #118), builds the names
the save stores as keys (planets, leaders, empires, fleets, factions, federations and
wars) the way the game does (#121), keeps every value of a repeated save key and reads
saves as UTF-8 (#110, #117), reads crises, the Khan and the War in Heaven from the
game's own names (#111), reads treaties from the keys the game writes (#112), reads
guardians and space fauna from their country types (#114), stops presenting Festival
upkeep as the Nomad reserves' monthly change (#113, for #79), finds saves, settings and
the game from one list of places (#116), and keeps the player's dig sites, an empire
name with "flag" in it and later tiers of leader traits (#122). A repeatable check of
what the Advisor says about real saves was added for development (#120). Stable remains
1.1.1.

## Release validation

- Complete combined Python, Rust, desktop, localization and renderer checks.
- Run `scripts/check_local_saves.py`; it now also fails if the app's reading of the
  installed game's text disagrees with the shipped name catalogs, or if the installed
  game never defines a crisis, guardian or flag name the app looks for.
- Build all four platforms with publication disabled and inspect their artifacts,
  including the bundled identity and technology catalog smoke checks.
- The Rust parser changed twice (#110, #117) and the Python side depends on its new
  output: the packaged parser must be the one built from this commit, or repeated keys
  silently read as one value.
- No database schema change since beta.4. A snapshot's signals now record a treaty
  reading version, so a corrected treaty reading is not shown as treaties signed or
  ended on the day of the update.
- History now matches wars, neighbours, fallen empires and the player's federation by
  ID (#121). A snapshot from before war IDs were recorded is not compared for wars, so
  the first snapshot pair after the update records no war starting or ending. Events and
  Chronicle text already written keep the names they were written with.
- Run `scripts/check_advisor_answers.py` (or `scripts/advisor_check_chatgpt.cjs`) on the
  candidate and read the answers. Before #121, 18 of 40 answers held a key or
  placeholder where a name belongs; after, 2 of 40.
- Verify macOS signing/notarization, package versions, update manifests and hashes.
- Merge only after the candidate checks pass, then tag the verified main commit.
- Verify final beta assets and feeds, while stable release/feed remains 1.1.1.

Not claimed: names from the installed game were checked on one macOS Steam install in
English, and in German and Simplified Chinese by pointing the app at those text files;
no save from a non-English player was available. Mods are covered by a made-up mod in
tests, not a real one, and mods packed as a `.zip` are not read. Finding the game and
saves on Windows and Linux (Proton libraries on other drives, a Documents folder moved
into OneDrive) is tested with folders built by the tests, not on real installs. The
loss of a leader's last trait under a long non-ASCII name (#117) is shown by a test
save only. Names the save stores as keys (#121) are built from the game's text files
and the rules in them and were not compared with the game's screen; the one outside
check is that all eight built empire names match the save folders the game named. In
languages with gender or case each word is in its plain form, so an adjective can have
the wrong ending. The live Advisor check is 40 questions, one run each, on one model.
The dig-site and "flag" fixes (#122) are shown by tests, since no local save has more
than ten sites; the later-tier trait names follow the pattern of the 65 the game writes
out. Crisis level and a monthly trend for Nomad reserves are still not read: no save
with either was available. #83 and #86 still await reporter confirmation.

## Earlier release records

# Beta 1.1.2-beta.4 candidate

This beta names technologies as the game shows them (#105, for #104), stops counting
research in progress as researched (#106, for #104), fixes save attachment on Windows
(#107, for #79), and carries the Nomad history fix (#101) and GPT-6 reasoning settings
(#103) merged after beta.3. Stable remains 1.1.1.

## Release validation

- Complete combined Python, Rust, desktop, localization and renderer checks.
- Run `scripts/check_local_saves.py`; it now fails if the installed game or a checked
  save is newer than the name catalogs.
- Build all four platforms with publication disabled and inspect their artifacts,
  including the bundled identity and technology catalog smoke checks.
- The Rust parser changed (#106): the packaged parser must be the one built from this
  commit, or the researched list silently keeps the old behaviour.
- No database schema change since beta.3.
- Verify macOS signing/notarization, package versions, update manifests and hashes.
- Merge only after the candidate checks pass, then tag the verified main commit.
- Verify final beta assets and feeds, while stable release/feed remains 1.1.1.

Not claimed: the Windows save attachment fix was reproduced and verified on a Windows
CI runner, not in the installed app. Technology names are English, generated from
Cygnus 4.5.3; no 4.5.3 save was available, and the newest real save checked is 4.5.2.
The Nomad reserve's monthly change reads as 0 in the one real Nomad save seen so far.
#83 and #86 still await reporter confirmation.

# Beta 1.1.2-beta.3 candidate

This beta adds story continuation across player empire changes (#97, for #95)
and Nomad economy support (#98, for #79). Stable remains 1.1.1.

## Release validation

- Complete combined Python, Rust, desktop, localization and renderer checks.
- Build all four platforms with publication disabled and inspect their artifacts,
  including the bundled identity catalog smoke check.
- Database schema 12 adds two story tables without rewriting history. Older apps
  skip newer schemas, so returning to 1.1.1 keeps working and ignores story links.
- Verify macOS signing/notarization, package versions, update manifests and hashes.
- Merge only after the candidate checks pass, then tag the verified main commit.
- Verify final beta assets and feeds, while stable release/feed remains 1.1.1.

Not claimed: Nomad save fields have not been checked against a real Nomad save;
reserves and stockpiles are read defensively and degrade to missing data. #83 and
#86 still await reporter confirmation.

# Beta 1.1.2-beta.2 candidate

This beta adds the Chronicle rewind and
abandoned-timeline fixes (#83), typed Advisor errors with privacy-safe references
(#86), identity names generated from game localisation (#81 follow-up), and the
consented private save attachments from #82. Stable remains 1.1.1.

## Release validation

- Complete combined Python, Rust, desktop, localization and renderer checks. The
  local combined branch passed 848 backend tests (27 optional-fixture skips),
  134 desktop unit tests and the 10 Advisor provider Electron journeys.
- Build all four platforms with publication disabled and inspect their artifacts.
- Confirm the packaged backend loads `stellaris_companion/identity_catalog.json`
  and `stellaris_companion/technology_catalog.json` (a missing file degrades silently
  to raw identifiers, so check a real lookup in each).
- Repeat the packaged ChatGPT bridge checks from beta.1, and confirm an injected
  internal failure shows the localized message, its reference and REPORT.
- Verify macOS signing/notarization, package versions, update manifests and hashes.
- Merge only after the candidate checks pass, then tag the verified main commit.
- Verify final beta assets and feeds, while stable release/feed remains 1.1.1.

Not claimed: Nomad economics (#79), the reporter's exact #86 cause, and #83
reporter confirmation. A save written during a brief look at an old save turns the
return into one coarse diff; see `docs/features/campaign-continuity.md`. Cygnus
4.5 identity IDs stay raw until the catalog is regenerated from a 4.5 install.

## Earlier release records

# Beta 1.1.2-beta.1 candidate

This beta combines the ChatGPT local-bridge repair, campaign identity/DLC evidence
and stable-model improvements, and the older-version Trade foundation correction.
Stable remains 1.1.1. Private save sharing is deferred until its service rollout;
the economic-account experiment is excluded because answer-quality acceptance failed.

## Release validation

- Complete combined Python, Rust, desktop, localization and renderer checks.
- Build all four platforms with publication disabled and inspect their artifacts.
- Exercise the actual bundled backend against an isolated synthetic ChatGPT bridge
  with its normal CA file and with that file temporarily absent. Restore the file
  before packaging; repeat against the installed Windows application.
- Verify macOS signing/notarization, package versions, update manifests and hashes.
- Merge only after the candidate checks pass, then tag the verified main commit.
  The tag workflow repeats validation and installer checks before publication.
- Verify final beta assets and feeds, while stable release/feed remains 1.1.1.

The bridge check uses synthetic replies and no external model credentials. It
proves packaged transport behavior, not the precise cause on the reporting PC.
Advisor evaluation supports a limited beta, not general accuracy certification;
Nomad economics and Chronicle date issue #83 remain unresolved.

## Earlier release records

# Stable 1.1.1 candidate

Promote the validated beta.2 app changes with a new stable version, updated Stellaris 4.5.2 Advisor guidance, and a fresh feedback invitation. The maintainer approved the five bullets in `electron/release-notes.md` plus the introductory patch-update line. PR #77 is merged; finish the final checks for PR #76 before integrating and publishing `v1.1.1`. The maintainer explicitly authorized admin merges for both PRs without a separate review on October 25.

## Feedback invitation

- The new `feedback-1.1.1-2026-10` ID is independent of the previous October invitation's read/dismissed state and targets exactly stable 1.1.1.
- The invitation offers “Share feedback” at the existing feedback page with the `feedback_1_1_1_2026_10` campaign tag. It opens once after onboarding, language initialization, and native window visibility are ready; the existing Transmissions entry remains available afterward.
- The invitation window was refreshed during final release preparation to run from `2026-10-25T03:45:28.000Z` until `2026-11-24T03:45:28.000Z`, exactly 30 days later. Refresh again if publication is materially delayed, and recheck the live feed after publishing.
- The installed Windows gate now includes all four announcement journeys: the real campaign copy/link with a legacy 1.1.0 profile and old campaign already dismissed, once-only behavior across restart, onboarding deferral, and hidden-window/tray refresh behavior. Test scheduling/version bounds are controlled so the UI regression remains valid after the live campaign expires; service tests separately cover release eligibility and expiry.
- The external link is intercepted at Electron's system-browser boundary during testing. No feedback is submitted and no user's browser/profile is changed.

## Validation and publication

1. The [combined candidate](https://github.com/gitmaan/stellaris-companion/actions/runs/40155555177) passed on `20c6b58`: 552 backend tests, 37 Rust tests, 105 desktop tests, 95 Linux Electron journeys, and all eleven installed Windows journeys, with expected optional/fixture/platform skips outside the strict Windows gate. Its installer SHA-256 is `f22dba0430a15deb66e5c5aa710ddd19613c53884c4be28e122114b87f04d9a8`; the popup screenshot, update manifest, and approved five bullets were verified.
2. Linux and both signed/notarized macOS packages passed in [the earlier combined run](https://github.com/gitmaan/stellaris-companion/actions/runs/40152819708). Only the excluded test file changed afterward. The tray test now checks native visibility and persisted read IDs while hidden, then rendered content after reopening, avoiding reliance on background-renderer progress. The earlier Windows failures and intermediate Linux assertion are retained with the final passing evidence. Six checks against the packaged macOS backend also passed.
3. The rebased release preparation has the same source tree as the validated candidate before the final notes/date/documentation update. Complete current-head PR checks, use the approved admin merge for PR #76, and tag the verified main commit as `v1.1.1`. The publishing workflow rebuilds all packages and repeats the installed Windows gate; verify its final installer separately.
4. The stable workflow publishes three `latest` feeds plus matching `beta` aliases and updates the public download site. Verify both subscriber tracks, all payload checksums, the installed Windows proof, and the live feedback invitation.

The automatic checks do not establish physical monitor/GPU behavior, paid-provider gameplay, or a real updater download/install/restart. Reports #71/#72 were closed after beta.2 at the maintainer's request; follow up if reporters still see missing text.

## Previous beta validation record

# Beta 1.1.1-beta.2

This beta combines feedback screenshot improvements (#73) and bounded response completion (#74). Stable remains v1.1.0. The release body is maintained in `electron/release-notes.md`.

## Candidate validation

- Linux and both signed/notarized macOS builds passed in [candidate run 39710758529](https://github.com/gitmaan/stellaris-companion/actions/runs/39710758529). Release validation passed 516 backend tests, 37 Rust tests, 104 desktop tests, and 94 Electron journeys, with expected fixture/platform skips.
- All seven installed Windows journeys passed with no skips or retries in [candidate run 39714035700](https://github.com/gitmaan/stellaris-companion/actions/runs/39714035700). The gate confirms the live bundled backend executable on both launches. The first run exposed a test-only race in capturing an early stdout line; the app payload is identical between the two runs.
- The tested Windows candidate installer has SHA-256 `3b622bc8b1c616814cd4821588355f5baaa172bce071b36405514538a2e3cd1c`. Publication rebuilds from the final main commit and repeats the installed-app gate, so verify that run's installer hash separately.

## Release gate

- Build all four platforms through a manual `electron-release.yml` run with publication disabled.
- On Windows, silently install that run's NSIS executable into a fresh runner directory and launch the installed executable with Playwright; verify `app.isPackaged`, the executable path, archive path, and app version.
- Require real bundled-backend startup, isolated profile restoration, offline Chinese/Japanese catalog and page loading, long Chinese answer scrolling/Copy at three simulated display scales, partial-answer retry after app restart, and screenshot preview/opt-in submission journeys. UI responses use a controlled backend; the separate startup journey uses the packaged backend.
- Save installer hashes, results, logs, and screenshots as `packaged-windows-proof-1.1.1-beta.2`. The same gate runs before a tagged release can be published.
- Deploy the tested feedback Worker before shipping the desktop diagnostics changes.
- Once the candidate and PR checks pass, merge, tag the final main commit, and verify the published beta manifests and unchanged stable release/feed.

Physical monitor/GPU/DPI behavior, paid-provider gameplay, and the original reporters' exact symptoms still need user evidence. Keep #71/#72 open until that evidence or reporter confirmation arrives. The gate does not exercise real update download/install/restart.

## Previous beta and stable validation record

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

## Pending incomplete-response validation (#71 / #72)

- [x] Verify shared two-call recovery, provider-aware budgets, saved partial-answer metadata, retry request IDs, and preservation of complete Chronicle content with local regression tests. See [Provider response completion](provider-completion.md).
- [x] Verify long Chinese answers, scrolling, resize, exact Copy output, and app text size in local Electron at simulated 100%, 125%, and 150% display scaling.
- [x] Run the Windows Actions localization/completion journeys on the completion PR and the feedback capture journeys on the feedback PR.
- [ ] Check a packaged Windows build with both changes, native display scaling, and the affected content/provider. Deploy the feedback worker update before shipping the desktop diagnostics changes.
- [ ] Compare the affected answer's copied text with visible content and use an opted-in unobscured screenshot to confirm whether the original reports are resolved. Keep both issues open pending that evidence or reporter confirmation.
