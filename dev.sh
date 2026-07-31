#!/bin/bash
# Development runner - starts Python backend + Electron in one terminal
set -e

cd "$(dirname "$0")"

# Load .env if it exists
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

# AI credentials are optional at boot. Save ingestion and local-provider setup
# still work without a Google key.
if [ -z "$GOOGLE_API_KEY" ]; then
  echo "Note: GOOGLE_API_KEY is not set; Gemini Advisor and Chronicle generation are disabled."
fi

# Set dev defaults
export STELLARIS_API_TOKEN="${STELLARIS_API_TOKEN:-dev-token-$(date +%s)}"
export STELLARIS_DB_PATH="${STELLARIS_DB_PATH:-./stellaris_history.db}"

echo "🚀 Starting Stellaris Companion (dev mode)"
echo "   API Token: ${STELLARIS_API_TOKEN:0:20}..."
echo "   DB Path: $STELLARIS_DB_PATH"
echo ""

# Kill any orphaned backend processes from previous runs
kill_port() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -ti:"$1" 2>/dev/null | xargs kill -9 2>/dev/null || true
  else
    powershell.exe -NoProfile -Command \
      "Get-NetTCPConnection -LocalPort $1 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id \$_.OwningProcess -Force }" \
      >/dev/null 2>&1 || true
  fi
}

cleanup_orphans() {
  echo "🧹 Cleaning up orphaned processes on ports 8742/5173..."
  kill_port 8742
  kill_port 5173
  sleep 0.5
}

# Cleanup function for shutdown
cleanup() {
  echo ""
  echo "🛑 Shutting down..."
  # Kill our backend process
  kill $PYTHON_PID 2>/dev/null || true
  # Also kill any processes on our port (in case of race conditions)
  lsof -ti:8742 2>/dev/null | xargs kill -9 2>/dev/null || true
  exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# Clean up any orphaned processes before starting
cleanup_orphans

# Start Python backend in background (use venv if available)
echo "📦 Starting Python backend on :8742..."
if [ -f "venv/bin/python3" ]; then
  PYTHON="venv/bin/python3"
elif [ -f "venv/Scripts/python.exe" ]; then
  PYTHON="venv/Scripts/python.exe"
else
  PYTHON="${PYTHON:-python3}"
fi

# Multiplayer player-empire override. In dev mode this script launches the
# backend directly, so Electron's env injection is bypassed. Mirror it by
# reading the override the app stored in its settings.json (unless already set
# explicitly via .env / the environment).
if [ -z "$STELLARIS_PLAYER_NAME" ] && [ -z "$STELLARIS_PLAYER_COUNTRY_ID" ]; then
  SETTINGS_JSON=""
  if [ -n "$APPDATA" ] && [ -f "$APPDATA/stellaris-companion/settings.json" ]; then
    SETTINGS_JSON="$APPDATA/stellaris-companion/settings.json"
  elif [ -f "$HOME/.config/stellaris-companion/settings.json" ]; then
    SETTINGS_JSON="$HOME/.config/stellaris-companion/settings.json"
  elif [ -f "$HOME/Library/Application Support/stellaris-companion/settings.json" ]; then
    SETTINGS_JSON="$HOME/Library/Application Support/stellaris-companion/settings.json"
  fi
  if [ -n "$SETTINGS_JSON" ]; then
    PLAYER_NAME="$("$PYTHON" -c "import json,sys; d=json.load(open(sys.argv[1],encoding='utf-8')); print(d.get('playerName') or '')" "$SETTINGS_JSON" 2>/dev/null || true)"
    PLAYER_CID="$("$PYTHON" -c "import json,sys; d=json.load(open(sys.argv[1],encoding='utf-8')); print(d.get('playerCountryId') or '')" "$SETTINGS_JSON" 2>/dev/null || true)"
    if [ -n "$PLAYER_NAME" ]; then
      export STELLARIS_PLAYER_NAME="$PLAYER_NAME"
      echo "   Player override: STELLARIS_PLAYER_NAME=$PLAYER_NAME (from app settings)"
    fi
    if [ -n "$PLAYER_CID" ]; then
      export STELLARIS_PLAYER_COUNTRY_ID="$PLAYER_CID"
      echo "   Player override: STELLARIS_PLAYER_COUNTRY_ID=$PLAYER_CID (from app settings)"
    fi
  fi
fi

"$PYTHON" -m backend.electron_main &

# Wait for backend to be ready
echo "⏳ Waiting for backend..."
for i in {1..30}; do
  if curl -s -H "Authorization: Bearer $STELLARIS_API_TOKEN" http://127.0.0.1:8742/api/health > /dev/null 2>&1; then
    echo "✅ Backend ready!"
    break
  fi
  sleep 1
done

# Start Electron (this blocks)
# Pass token via env so Electron uses the same one
echo "⚡ Starting Electron + React..."
cd electron
STELLARIS_API_TOKEN="$STELLARIS_API_TOKEN" npm run dev

# Cleanup when Electron exits
cleanup
