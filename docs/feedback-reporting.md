# Feedback reporting (one-click)

The in-app **Report Issue / Feedback** modal supports a one-click submit flow using a Cloudflare Worker.

## Configuration (Vite build-time env)

The renderer is built with Vite, so the report endpoint is configured at build time via env vars:

- `VITE_REPORT_ENDPOINT` (optional): Cloudflare Worker URL that accepts report submissions.
  - If unset, the app will still allow **Copy Report** / **Open GitHub Issue**.
- `VITE_ISSUES_URL` (optional): URL to the GitHub "new issue" page used by **Open GitHub Issue**.

See `electron/renderer/.env.example`.

## Privacy (opt-in)

By default, submitting a report includes only basic environment info (app version, platform, Electron version) plus the user's category/description.

The following are opt-in toggles in the modal:

- Game diagnostics (save metadata, DLC count, empire identity)
- Backend log tail (last ~32KB)
- Screenshot (submitted reports upload a temporary image URL)
- Error stack / LLM prompt-response context (when available)

## Maintainer triage + Jules workflow

Recommended label flow:

1. Report arrives as a GitHub issue labeled `user-report` plus category/platform/version labels.
2. Maintainer reviews and adds label `jules` when ready for automatic fixing.
3. Jules creates a PR for review and merge.
