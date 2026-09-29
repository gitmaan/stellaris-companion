#!/bin/bash
#
# Build the Python backend using PyInstaller.
# Output: dist-python/stellaris-backend/ (onedir bundle on all platforms)
#

set -e

# Get the project root directory (parent of scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "Building Python backend..."

if [ -n "${PYTHON_BIN:-}" ]; then
    :
elif [ -x ".venv/bin/python" ]; then
    PYTHON_BIN=.venv/bin/python
elif [ -x "venv/bin/python" ]; then
    PYTHON_BIN=venv/bin/python
elif [ -f ".venv/Scripts/python.exe" ]; then
    PYTHON_BIN=.venv/Scripts/python.exe
elif [ -f "venv/Scripts/python.exe" ]; then
    PYTHON_BIN=venv/Scripts/python.exe
elif command -v python3 &> /dev/null; then
    PYTHON_BIN=python3
elif command -v python &> /dev/null; then
    PYTHON_BIN=python
else
    echo "Error: Python not found"
    exit 1
fi

# Check for virtual environment
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
fi

# Check if PyInstaller is installed in the selected Python environment.
if ! "$PYTHON_BIN" -m PyInstaller --version &> /dev/null; then
    echo "PyInstaller not found. Installing..."
    if "$PYTHON_BIN" -m pip --version &> /dev/null; then
        "$PYTHON_BIN" -m pip install 'pyinstaller>=6,<7'
    elif command -v uv &> /dev/null; then
        uv pip install --python "$PYTHON_BIN" 'pyinstaller>=6,<7'
    else
        echo "Error: PyInstaller is missing and this Python environment has no pip or uv installer"
        exit 1
    fi
fi

# Clean previous build artifacts
echo "Cleaning previous build..."
rm -rf build/stellaris-backend
rm -rf dist/stellaris-backend
rm -rf dist-python
find backend stellaris_companion stellaris_save_extractor -type d -name __pycache__ -prune -exec rm -rf {} +
find backend stellaris_companion stellaris_save_extractor -type f -name '*.pyc' -delete

# Run PyInstaller with the spec file
echo "Running PyInstaller..."
"$PYTHON_BIN" -m PyInstaller --clean stellaris-backend.spec

# Move output to dist-python (expected by electron-builder)
echo "Moving output to dist-python..."
mkdir -p dist-python
if [ -d "dist/stellaris-backend" ]; then
    mv dist/stellaris-backend dist-python/
    echo "Writing backend build metadata..."
    "$PYTHON_BIN" scripts/backend_build_info.py stamp dist-python/stellaris-backend
    echo "Built: dist-python/stellaris-backend/"
else
    echo "Error: Build output not found"
    exit 1
fi

echo "Python backend build complete!"
