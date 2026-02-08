#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:-${TARGET:-}}"
if [[ -z "${TARGET}" ]]; then
  echo "Usage: scripts/ci-smoke-check.sh <target>"
  echo "  target: linux-x64 | windows-x64 | mac-arm64 | mac-x64"
  exit 2
fi

die() {
  echo "CI smoke check failed: $*" >&2
  exit 1
}

echo "== CI Smoke Check =="
echo "target=${TARGET}"

# Renderer output (bundled into app.asar)
[[ -f "electron/renderer/dist/index.html" ]] || die "missing renderer entrypoint: electron/renderer/dist/index.html"
if ! find "electron/renderer/dist" -type f \( -name "*.js" -o -name "*.css" \) -print -quit | grep -q .; then
  die "renderer dist has no JS/CSS assets (did Vite build run?)"
fi

# Python backend bundle (PyInstaller onedir)
[[ -d "dist-python/stellaris-backend" ]] || die "missing Python bundle dir: dist-python/stellaris-backend/"
if [[ "${TARGET}" == "windows-x64" ]]; then
  [[ -f "dist-python/stellaris-backend/stellaris-backend.exe" ]] || die "missing Python exe: dist-python/stellaris-backend/stellaris-backend.exe"
else
  [[ -f "dist-python/stellaris-backend/stellaris-backend" ]] || die "missing Python executable: dist-python/stellaris-backend/stellaris-backend"
fi

# Rust parser binary (copied into bin/ at repo root)
case "${TARGET}" in
  windows-x64)
    [[ -f "bin/stellaris-parser.exe" ]] || die "missing Rust parser: bin/stellaris-parser.exe"
    ;;
  mac-arm64)
    [[ -f "bin/stellaris-parser-darwin-arm64" ]] || die "missing Rust parser: bin/stellaris-parser-darwin-arm64"
    ;;
  mac-x64)
    [[ -f "bin/stellaris-parser-darwin-x64" ]] || die "missing Rust parser: bin/stellaris-parser-darwin-x64"
    ;;
  linux-x64)
    [[ -f "bin/stellaris-parser-linux-x64" ]] || die "missing Rust parser: bin/stellaris-parser-linux-x64"
    ;;
  *)
    die "unknown target '${TARGET}' (expected linux-x64|windows-x64|mac-arm64|mac-x64)"
    ;;
esac

echo "CI smoke check passed."
