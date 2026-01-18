#!/bin/bash
#
# Build the Python backend using PyInstaller.
# Output: dist-python/stellaris-backend (macOS/Linux) or dist-python/stellaris-backend.exe (Windows)
#

set -e

# Get the project root directory (parent of scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "Building Python backend..."

# Check for virtual environment
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
fi

# Check if PyInstaller is installed
if ! command -v pyinstaller &> /dev/null; then
    echo "PyInstaller not found. Installing..."
    pip install pyinstaller
fi

# Clean previous build artifacts
echo "Cleaning previous build..."
rm -rf build/stellaris-backend
rm -rf dist/stellaris-backend
rm -rf dist-python

# Run PyInstaller with the spec file
echo "Running PyInstaller..."
pyinstaller --clean stellaris-backend.spec

# Move output to dist-python (expected by electron-builder)
echo "Moving output to dist-python..."
mkdir -p dist-python
if [ -f "dist/stellaris-backend" ]; then
    mv dist/stellaris-backend dist-python/
    echo "Built: dist-python/stellaris-backend"
elif [ -f "dist/stellaris-backend.exe" ]; then
    mv dist/stellaris-backend.exe dist-python/
    echo "Built: dist-python/stellaris-backend.exe"
else
    echo "Error: Build output not found"
    exit 1
fi

echo "Python backend build complete!"
