# Development workflow

## Prerequisites

- Node.js 22.12+ + npm
- Python 3 (recommended: venv)
- Rust toolchain (for `stellaris-parser`)
- Optional: a Gemini API key (`GOOGLE_API_KEY`) when Gemini is selected

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install .
```

Build the Rust parser (required):

```bash
cd stellaris-parser
cargo build --release
cd ..
```

## Run the Electron app (recommended)

The simplest “one command” dev flow:

```bash
./dev.sh
```

What it does:
- starts the backend on `127.0.0.1:8742`
- starts the Electron dev process + renderer

Key env vars:
- `GOOGLE_API_KEY` (required when Gemini is selected)
- `STELLARIS_ADVISOR_PROVIDER` (`gemini`, `ollama`, `lm_studio`, `openrouter`, or `custom`; controls Advisor and Chronicle)
- `STELLARIS_ADVISOR_MODEL` (required for non-Gemini providers)
- `STELLARIS_ADVISOR_BASE_URL` (optional preset override or custom API base)
- `STELLARIS_ADVISOR_API_KEY` (required by OpenRouter; optional for custom endpoints)
- `STELLARIS_API_TOKEN` (dev.sh will generate one if missing)
- `STELLARIS_DB_PATH` (defaults to `./stellaris_history.db`)

## Run Electron + backend separately

Backend:

```bash
python3 -m backend.electron_main --host 127.0.0.1 --port 8742
```

Electron (in a second terminal):

```bash
npm -C electron install
npm -C electron run dev
```

Note: Electron main proxies all backend HTTP calls and attaches the auth token.

## Sanity checks

Python:

```bash
python3 -m compileall -q backend stellaris_companion stellaris_save_extractor
pytest -q
```

Renderer:

```bash
npm -C electron/renderer run build
```

Main process syntax check:

```bash
node --check electron/main.js
```

## Packaged backend build (PyInstaller)

```bash
pyinstaller --clean stellaris-backend.spec
```

## Gemini generation limits

`GeminiAdvisorGenerator.generate` owns recovery for both Advisor and Chronicle.
Keep this policy in one place; Chronicle must not wrap native Gemini in another
retry loop. SDK transport retries are disabled for these calls.

| Generation | Initial output ceiling | Ceiling after `MAX_TOKENS` |
| --- | ---: | ---: |
| Advisor | 4,096 | 8,192 |
| Chronicle | 8,192 | 16,384 |

These are ceilings, not target response lengths. Each answer or Chronicle piece
gets at most two API requests total, including JSON repair and the existing quota
fallback to Flash-Lite. A Chronicle refresh may generate several pieces. Only a
confirmed `MAX_TOKENS` finish increases the ceiling; empty or invalid JSON gets
one repair at the same ceiling. Other provider failures stop immediately unless
the existing quota fallback is available within the two-request allowance.

Gemini 3 Chronicle generation uses low thinking; Flash-Lite retains its default.
Advisor thinking and model selection remain unchanged. After a provider failure,
the Chronicle page pauses automatic generation for that campaign until an
explicit Retry or app reload, and keeps the saved story available.

Local diagnostics record requested/returned model, token counts, output ceiling,
finish reason and attempt number. They add no remote telemetry and do not record
prompts, save contents or API keys. Regression coverage lives in
`tests/test_gemini_recovery.py` and `electron/e2e/chronicle-refresh.spec.js`.
