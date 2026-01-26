# Release Readiness (Public Electron App)

> Scope: assess how close the project is to a public release (Windows + macOS) with a “downloadable Electron app”, and what remains for open-source hygiene and low-fuss distribution.

## Summary

The core architecture (Rust parser + session mode + Python extractors + Electron shell) is in a good place for a public release from a performance/robustness perspective. The main remaining work is distribution polish: ensuring the packaged app always contains the correct platform binaries, adding a reproducible CI release pipeline, and cleaning up open-source essentials (license, contribution docs, CI checks).

## Release Bars (Pick One)

### A) Public Beta (fastest path)
Good for early releases where users manually install, OS warnings may appear, and you ship a simple in-app “update available” flow. Code signing is optional.

**Characteristics**
- Unsigned installers are acceptable (users may see Gatekeeper/SmartScreen warnings).
- No silent auto-update required (but app can notify users and deep-link to downloads).
- Focus on correctness + crash-free behavior + reproducible builds.

**Estimated time**: ~1–3 focused days to make reliable.

### B) “Consumer Seamless” Release
Good for mainstream distribution where install/update is low-friction and warnings are minimized.

**Characteristics**
- macOS: signed + (ideally) notarized.
- Windows: signed (reduces SmartScreen warnings over time).
- Auto-update via `electron-updater` (or a clear manual update path).

**Estimated time**: ~1–2+ weeks (certs + notarization + pipeline iterations).

## What’s Already in Good Shape

- **Parser architecture**: session mode + generic Rust primitives is the right design for fast processing across many save variants (mods, different game stages).
- **Electron packaging model**: `electron/electron-builder.yml` includes `dist-python/` (PyInstaller backend) and `bin/` (Rust parser) as `extraResources`.
- **Backend API auth**: `backend/api/server.py` requires a Bearer token (`STELLARIS_API_TOKEN`), reducing risk of other local processes calling the backend.
- **Secrets handling**: Electron uses `keytar` for secrets and `electron-store` for non-secrets; `.env` is gitignored.

## Key Gaps Before Public Release

### 1) Platform binaries completeness (blocker)
The packaged app must always include the correct Rust parser binary for the user’s OS/arch.

Current risk indicators:
- `bin/` appears to have only `stellaris-parser-darwin-arm64` tracked.
- `rust_bridge.py` expects these names in production resources:
  - Windows: `stellaris-parser.exe`
  - macOS arm64: `stellaris-parser-darwin-arm64`
  - macOS x64: `stellaris-parser-darwin-x64`

**Action**
- Ensure Windows + macOS x64 binaries are built and shipped with their installers (either checked into the repo for now, or pulled in during CI packaging).

### 2) Reproducible release pipeline for Electron
You already have `.github/workflows/rust-parser.yml` for the Rust parser, but you need an Electron build/release workflow that:
- builds PyInstaller backend on each OS
- builds the renderer
- packages with `electron-builder`
- uploads installers to GitHub Releases

**Action**
- Add a GitHub Actions workflow: matrix (macos, windows) that runs `scripts/build-python.sh` + `scripts/build-electron.sh` and publishes artifacts.

### 3) Signing / Gatekeeper / SmartScreen (polish)
`electron/electron-builder.yml` currently disables signing and notarization:
- mac: `identity: null`, `hardenedRuntime: false`, `gatekeeperAssess: false`
- win: `signAndEditExecutable: false`

**Action**
- For “beta”: document expected warnings and how users can open the app anyway.
- For “seamless”: set up signing for both OSes and iterate until installers launch without scary prompts.

### 4) Updates
Electron has update IPC handlers but they’re placeholders (`electron/main.js`).

**Action**
- For “beta”: implement an in-app update notification that opens the download page (no silent update install needed).
- For “seamless”: implement full updates with `electron-updater` and verify GitHub Releases publishing works.

## Beta Updates + Website (Recommended)

You can make beta distribution feel “seamless” without full signing by ensuring users never need to “check GitHub” manually.

### Website + Download Buttons
- Host a simple landing page (GitHub Pages is fine) with “Download for macOS” / “Download for Windows” buttons.
- The buttons can link directly to GitHub Release assets (so you don’t need to host large files yourself).

### In-App Update Checks (Beta-Friendly)
Implement a lightweight update check and present a banner/button:
- App checks the latest version on startup (and optionally once/day).
- If newer: show “Update available” + “Download” button.
- “Download” opens the website (or GitHub Release URL) in the system browser.

This avoids fragile “silent updates” for unsigned apps and still keeps updates easy for users.

### Auto-Update (Later)
Silent or one-click in-app updates are much more reliable once:
- macOS is signed + notarized
- Windows is code-signed
At that point, enabling `electron-updater` becomes the path to true “consumer seamless”.

## Trust Signals (Especially Important for Beta)

When apps are unsigned, user trust comes primarily from transparency and repeatability:
- Publish SHA256 checksums in each release notes (and/or as `*.sha256` assets).
- Build installers via CI (not local) so releases have consistent provenance.
- Keep secrets out of the repo (`.env` is already gitignored; Electron uses `keytar`).

### 5) Open-source hygiene (required for GitHub)

**Missing/Recommended**
- Add a root `LICENSE` file (repo claims MIT in `electron/package.json` but no LICENSE is present).
- Add `CONTRIBUTING.md` (optional but strongly recommended if you want PRs).
- Add `SECURITY.md` (recommended: how to report vulnerabilities).
- Add CI checks (at least): Rust `fmt`/`clippy`/tests, Python tests, and an Electron build smoke test.

**Repo cleanliness**
- Avoid committing large binary artifacts and build outputs in git long-term:
  - don’t check in `stellaris-parser/target/`
  - consider keeping `bin/` as CI-produced release assets rather than tracked files

## Performance/Architecture Readiness

### Where you are now
- If your briefing generation is consistently ~5–10s on large late-game saves, that is already competitive for a “local desktop companion”.
- Remaining performance work (regex elimination, ID-based `get_entries`, `contains_kv` for formatting-safe checks) is incremental and can continue post-beta.

### What must be true before release
- “Works on every save” really means: graceful handling of missing/extra fields and schema differences without crashing. The Rust parser (jomini) helps; remaining risk is Python assumptions about field shapes.
- Ensure the Rust primitives stay **generic** (data access), keeping game logic in Python to remain mod/version tolerant.

## Recommended Milestones

### Milestone 1 — Public Beta (manual updates)
- Confirm Windows + macOS x64 + macOS arm64 packages include correct Rust binary.
- Add Electron CI build workflow (Windows + macOS) that produces installers and attaches them to GitHub Releases.
- Add `LICENSE`.
- Add a website landing page with download buttons (links to Releases).
- Implement in-app update notifications (opens the website/download) so users don’t need to check GitHub.
- Add a short “Troubleshooting” section to README for Gatekeeper/SmartScreen warnings and “backend not configured” cases.

### Milestone 2 — “Seamless” Release
- Implement full updater (`electron-updater`) and validate update flow end-to-end.
- Add code signing and (for macOS) notarization.
- Add CI checks and a minimal release checklist.

## Practical Definition of “Release Ready”

You’re “public beta ready” when:
- A fresh user can download the app, paste an API key, select save folder, and get a briefing without installing Python/Rust/Node.
- The app starts reliably and doesn’t crash on common saves (including heavily modded ones).
- Errors are actionable (missing key, missing save, parsing failure) and visible in the UI/logs.
