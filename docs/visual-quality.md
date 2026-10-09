# Visual quality conventions

## Layout

The status bar has a fixed height and two bounded columns. Empire names and
connection labels truncate with their full text available as a title. Navigation
uses three equal columns. Page containers remain mounted, own one scroll region,
and crossfade without scaling text. Inactive pages are inert and pause decorative
CSS animations.

Reserve space before asynchronous content arrives: the Advisor history toolbar,
welcome status, suggestions area, and provider footer must not move the welcome
heading or composer when readiness, connection, or provider state changes.
The Send button reserves both its idle and waiting labels. Text can still expand
the composer deliberately while the user types.

Chronicle keeps a 280px chapter rail above 1100 CSS pixels. At narrower widths,
including windows narrowed by text scaling, Chapters opens a modal drawer over
the reader. Selecting a chapter or campaign closes it. Do not animate reader
width: paragraphs would rewrap every frame. `useReadingAnchor` preserves the
current paragraph across responsive width changes.

Chat measurements use message identities rather than array positions. A reader
away from the bottom keeps their anchor as content is measured or a reply arrives;
Jump to latest resumes following the conversation. Restored or remounted messages
do not replay entrance animations.

## Motion and focus

Use `renderer/lib/motion.ts`: feedback 120ms, content 160ms, surfaces 200ms. Page
changes fade; new messages translate 4px, centered dialogs 8px, and drawers 16px.
Avoid scale, animated layout widths, delayed staggered forms, and repeating
decorative movement where it competes with reading.

`MotionConfig` follows the OS reduced-motion preference. CSS animations stop,
chapter scrolling becomes immediate, and dialog translation is removed. Short
opacity changes can remain. Explicit progress transitions also honor the
preference.

Use `Modal` for dialogs and drawers. Its shared focus hook moves focus inside,
traps Tab, makes the background inert, dismisses on Escape when allowed, and
restores the invoking control. Nested dialogs have one focus owner. Composition
keystrokes must not dismiss a dialog. A busy or non-dismissible surface omits its
close callback. Onboarding uses the same hook and retains its step-specific
initial focus. Actionable notifications remain reachable in the focus sequence.

All interactive controls have a visible focus outline, including custom
checkboxes. Toasts appear below navigation, away from the composer and dialog
footers; dismissal pauses while the notice is hovered or focused.

## Recovery and drafts

Distinguish connecting, offline, no save, analyzing, and missing provider setup.
Show a matching explanation and a direct configuration action when available.
Settings section links reveal the appropriate section, and help text distinguishes
automatically saved preferences from the provider's explicit save action.

The composer remains editable during a reply. Sending returns focus immediately;
the eventual response must not move it. A failed request restores its question
only into an empty draft. Retry keeps the original request ID, replaces the error,
and clears a restored question only if it is still the current draft. Copy response
has inline success or failure feedback without changing the button's dimensions.

## Verification

Run `npm -C electron run test:e2e` for the full journey suite. Local Electron
windows are hidden and non-focusable by default; the macOS Dock icon is suppressed.
Use `npm -C electron run test:e2e:headed` only when visible debugging is wanted.
Linux CI exercises visible windows inside Xvfb. See [Development workflow](dev-workflow.md).

`electron/e2e/visual-quality.spec.js` covers:

- At most one CSS pixel of shell, welcome-heading, or composer movement during
  readiness and long status/provider changes.
- The minimum 800×600 window at every supported text scale, all seven production
  languages, and the expansion pseudo-locale.
- Pending drafts and focus, retry identity, copy feedback, long virtualized chat,
  and reading anchors across a Chronicle rail breakpoint.
- Keyboard and nested-dialog focus, composition, Escape, reduced motion,
  notification placement, and visible keyboard outlines.
- Hidden local-window behavior and frame/geometry sampling across tab changes.

The suite saves screenshots and JSON measurements under `artifacts/visual-quality`.
Linux CI uploads these alongside failure traces. Inspect both screenshots and
geometry: cumulative layout shift alone excludes transforms and many shifts after
input. Frame timings are diagnostic, not a hardware-independent performance
threshold; record the environment when comparing them. Mocked backend journeys
do not establish real-provider latency or packaged-app performance.
