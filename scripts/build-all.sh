#!/bin/bash
#
# Build both Python backend and Electron app.
# This is the main build script for creating a distributable package.
#
# Output:
#   dist-python/stellaris-backend/ - Python backend bundle (onedir)
#   electron/dist/ - Electron app packages (dmg, exe, AppImage, etc.)
#

set -e

# Get the project root directory (parent of scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "=========================================="
echo "Stellaris Companion - Full Build"
echo "=========================================="
echo ""

# Build Python backend
echo "Step 1: Building Python backend..."
"$SCRIPT_DIR/build-python.sh"
echo ""

# Build Electron app
echo "Step 2: Building Electron app..."
"$SCRIPT_DIR/build-electron.sh"
echo ""

echo "=========================================="
echo "Build complete!"
echo "=========================================="
echo ""
echo "Outputs:"
echo "  Python backend: dist-python/stellaris-backend/"
echo "  Electron app:   electron/dist/"
