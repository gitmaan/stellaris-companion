#!/bin/bash
#
# Build the Electron app using electron-builder.
# Requires Python backend to be built first (in dist-python/).
# Output: electron/dist/ (platform-specific packages)
#

set -e

# Get the project root directory (parent of scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "Building Electron app..."

# Check if Python backend exists
if [ ! -d "dist-python" ]; then
    echo "Error: Python backend not found in dist-python/"
    echo "Run ./scripts/build-python.sh first"
    exit 1
fi

# Check if dist-python has the backend bundle (onedir layout)
if [ ! -d "dist-python/stellaris-backend" ]; then
    echo "Error: Python backend bundle not found in dist-python/stellaris-backend/"
    echo "Run ./scripts/build-python.sh first"
    exit 1
fi

cd electron

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
    echo "Installing Electron dependencies..."
    npm install
fi

# Install renderer dependencies if needed
if [ ! -d "renderer/node_modules" ]; then
    echo "Installing renderer dependencies..."
    cd renderer
    npm install
    cd ..
fi

# Build the React renderer
echo "Building React renderer..."
cd renderer
npm run build
cd ..

# Build the Electron app
echo "Running electron-builder..."
npm run build:electron

echo "Electron app build complete!"
echo "Output: electron/dist/"
