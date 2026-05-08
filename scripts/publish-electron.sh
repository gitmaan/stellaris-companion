#!/usr/bin/env bash
#
# Safe publish entrypoint. Always rebuilds and verifies the bundled Python backend
# before handing off to electron-builder.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "=========================================="
echo "Stellaris Companion - Safe Publish"
echo "=========================================="

echo "Cleaning previous Electron artifacts..."
rm -rf "$PROJECT_ROOT/electron/dist"

echo "Step 1: Rebuilding Python backend..."
"$SCRIPT_DIR/build-python.sh"

echo "Step 2: Building renderer..."
cd "$PROJECT_ROOT/electron/renderer"
npm run build

echo "Step 3: Packaging Claude Desktop MCPB..."
cd "$PROJECT_ROOT/electron"
npm run build:mcpb

echo "Step 4: Publishing Electron app..."
npx electron-builder "$@" --publish always
