# Visual quality conventions

## Layout

The status bar has a fixed height and two bounded columns. Empire names and
connection labels truncate with their full text available as a title. Navigation
uses three equal columns. Page containers remain mounted, own one scroll region,
and crossfade without scaling text. Inactive pages are inert and pause decorative
CSS animations.

Reserve space before asynchronous content arrives: the Advisor history toolbar,
welcome status, and suggestions area must not move the welcome heading or composer
when readiness, connection, or provider state changes. ChatGPT controls share the
existing toolbar; providers without those controls do not leave an empty footer.
The conversation and composer share a maximum 1000px column. The single-line
composer is 56px tall with aligned 40px controls, including the person icon that
opens advisor customization. Send keeps its idle width and shows a spinner while
waiting, with a localized accessible label. Longer drafts expand upward, including
when window width or language changes reflow an existing draft.

Chronicle keeps a 280px chapter rail above 1100 CSS pixels. At narrower widths,
including windows narrowed by text scaling, Chapters opens a modal drawer over
the reader. Selecting a chapter or campaign closes it. Do not animate reader
width: paragraphs would rewrap every frame. `useReadingAnchor` preserves the
current paragraph across responsive width changes.

At compact widths the Chronicle title, coverage date, and Chapters control share
one header above the reader. Short or narrow windows reduce navigation padding,
ornamental heading sizes, and chapter metadata spacing without reducing narrative
text. Keep the first narrative line within the top two-thirds of the minimum
window, including supported text scales and locales.

Preserve the HUD's scanlines, glowing headings, display fonts, and corner accents.
Apply one global scanline overlay so portals and content use the same texture.
Glow combines a crisp core and a restrained accent-colored halo; compact corner
accents scale with the chrome rather than occupying a large part of the reader.

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
checkboxes. Routine Settings preferences report Applying/Saved beside their
controls in a reserved space. Settings section links precede the display controls.
Errors and actionable notifications use toasts below navigation; dismissal pauses
while the notice is hovered or focused.

## Recovery and drafts

Distinguish connecting, offline, no save, analyzing, and missing provider setup.
Show a matching explanation and a direct configuration action when available.
Settings section links reveal the appropriate section, and help text distinguishes
automatically saved preferences from the provider's explicit save action.
Advisor/narrator save confirmations survive ordinary status updates; a late
initial advisor-style load cannot overwrite instructions already being edited.

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
- Composer alignment and upward expansion at multiple text scales; customization
  can still be saved through the person icon while a reply is pending.
- Inline preference feedback without layout movement and compact Chronicle
  reading space. The comparison journey uses fixed conversation/chapter content
  and captures the same 1000px, 1400px, and 800×600 viewports.

The suite saves screenshots and JSON measurements under `artifacts/visual-quality`.
Linux CI uploads these alongside failure traces. Inspect both screenshots and
geometry: cumulative layout shift alone excludes transforms and many shifts after
input. Frame timings are diagnostic, not a hardware-independent performance
threshold; record the environment when comparing them. Mocked backend journeys
do not establish real-provider latency or packaged-app performance.

Comparison captures are under `artifacts/visual-quality/polish/after`. Before a
visual change, run only the comparison journey with `E2E_VISUAL_PROOF_STAGE=before`
to preserve a `polish/before` set; subsequent runs never overwrite those images.
