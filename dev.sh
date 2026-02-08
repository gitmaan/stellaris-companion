#!/bin/bash
# Development runner - starts Python backend + Electron in one terminal
set -e

cd "$(dirname "$0")"

# Load .env if it exists
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

# Check for API key
if [ -z "$GOOGLE_API_KEY" ]; then
  echo "⚠️  GOOGLE_API_KEY not set. Add it to .env or export it."
  echo "   echo 'GOOGLE_API_KEY=your-key' >> .env"
  exit 1
fi

# Set dev defaults
export STELLARIS_API_TOKEN="${STELLARIS_API_TOKEN:-dev-token-$(date +%s)}"
export STELLARIS_DB_PATH="${STELLARIS_DB_PATH:-./stellaris_history.db}"

echo "🚀 Starting Stellaris Companion (dev mode)"
echo "   API Token: ${STELLARIS_API_TOKEN:0:20}..."
echo "   DB Path: $STELLARIS_DB_PATH"
echo ""

# Kill any orphaned backend processes from previous runs
cleanup_orphans() {
  local pids=$(lsof -ti:8742 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo "🧹 Cleaning up orphaned processes on port 8742..."
    echo "$pids" | xargs kill -9 2>/dev/null || true
    sleep 0.5
  fi
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
  venv/bin/python3 -m backend.electron_main &
else
  python3 -m backend.electron_main &
fi
PYTHON_PID=$!

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
