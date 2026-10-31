# Feedback reporting (one-click)

The in-app **Report Issue / Feedback** modal supports a one-click submit flow using a Cloudflare Worker.

## Configuration (Vite build-time env)

The renderer is built with Vite, so the report endpoint is configured at build time via env vars:

- `VITE_REPORT_ENDPOINT` (optional): Cloudflare Worker URL that accepts report submissions.
  - If unset, the app will still allow **Copy Report** / **Open GitHub Issue**.
- `VITE_ISSUES_URL` (optional): URL to the GitHub "new issue" page used by **Open GitHub Issue**.

See `electron/renderer/.env.example`.

## Service ownership

The production service is maintained and deployed only from
[`stellaris-companion-site/workers/stellaris-feedback`](https://github.com/gitmaan/stellaris-companion-site/tree/main/workers/stellaris-feedback).
Desktop builds submit to `https://feedback.galacticfilingcabinet.com/report`;
the root path remains a legacy alias. Coordinate payload changes and their runtime
tests in that repository.

The same Worker also serves private website surveys at `/submit-private`, public
website reports at `/submit-web`, and the public feedback board. Deploying a
desktop-only copy overwrites those routes. The duplicate implementation was
retired after issue #78; this repository must not deploy the shared service.

## Privacy (opt-in)

By default, submitting a report includes only basic environment info (app version, platform, Electron version) plus the user's category/description.

The following are opt-in toggles in the modal:

- Game diagnostics (save metadata, DLC count, empire identity, and a bounded war-calculation trace)
- Backend log tail (last ~32KB)
- Screenshot (submitted reports upload a temporary image URL)
- Error stack / LLM prompt-response context (when available)

War diagnostics include country IDs, raw battle-side result/loss fields, and the
calculated player-side result. They do not include or upload the save file.

## Maintainer triage + Jules workflow

Recommended label flow:

1. Report arrives as a GitHub issue labeled `user-report` plus category/platform/version labels.
2. Maintainer reviews and adds label `jules` when ready for automatic fixing.
3. Jules creates a PR for review and merge.
