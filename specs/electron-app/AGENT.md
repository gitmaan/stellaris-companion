# Electron App - Build & Test

## Setup

```bash
# Python dependencies (already installed, just verify)
pip install fastapi uvicorn[standard]

# Electron dependencies
cd electron
npm install
```

## Python Backend

### Run in Development

```bash
# Set required env vars
export GOOGLE_API_KEY="your-key"
export STELLARIS_API_TOKEN="test-token-123"
export STELLARIS_DB_PATH="./stellaris_history.db"

# Run the server
python backend/electron_main.py
```

### Test API Manually

```bash
# Health check
curl -H "Authorization: Bearer test-token-123" http://127.0.0.1:8742/api/health

# Chat (requires save loaded)
curl -X POST -H "Authorization: Bearer test-token-123" \
  -H "Content-Type: application/json" \
  -d '{"message": "What is my empire status?"}' \
  http://127.0.0.1:8742/api/chat
```

### Type Check

```bash
# No type checker configured yet - use mypy if desired
# mypy backend/api/
```

## Electron App

### Run in Development

```bash
cd electron

# Start React dev server + Electron
npm run dev
```

### Build React Only

```bash
cd electron/renderer
npm run build
```

### Build Electron App

```bash
cd electron
npm run build
```

## Full Build

```bash
# Build Python backend (PyInstaller)
./scripts/build-python.sh

# Build Electron app
./scripts/build-electron.sh

# Or both
./scripts/build-all.sh
```

## Verify All

```bash
# Import test for Python API
python -c "from backend.api.server import create_app; print('OK')"

# Import test for electron_main
python -c "import backend.electron_main; print('OK')"

# Electron deps installed
cd electron && npm ls electron && cd ..

# React build
cd electron/renderer && npm run build && cd ../..
```

## PyInstaller Build

```bash
# Activate venv first
source venv/bin/activate

# Install PyInstaller if not present
pip install pyinstaller

# Build the Python backend
pyinstaller --clean stellaris-backend.spec

# Output: dist/stellaris-backend (macOS/Linux) or dist/stellaris-backend.exe (Windows)
```

## Learnings

(Ralph adds learnings here as it discovers them)

- FastAPI requires `from __future__ import annotations` for Python 3.9 compatibility with newer type hints
- keytar needs to be rebuilt for Electron's Node version - use `electron-rebuild`
- Uvicorn hidden imports: uvicorn.logging, uvicorn.loops.auto, uvicorn.protocols.http.auto, uvicorn.lifespan.on
- PyInstaller spec must include entire `backend/` package in datas - internal imports need source files at runtime
- Use `google.genai` not `google.ai.generativelanguage` for hidden imports - the latter is deprecated
- Full uvicorn hidden imports list: logging, loops.auto, loops.asyncio, protocols.http.auto, protocols.http.h11_impl, protocols.http.httptools_impl, protocols.websockets.auto, protocols.websockets.wsproto_impl, protocols.websockets.websockets_impl, lifespan.on, lifespan.off
