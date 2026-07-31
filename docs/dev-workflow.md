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
