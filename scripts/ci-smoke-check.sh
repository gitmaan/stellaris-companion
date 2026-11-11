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
if [[ -n "${PYTHON_BIN:-}" ]]; then
  command -v "${PYTHON_BIN}" >/dev/null 2>&1 || die "missing Python command: ${PYTHON_BIN}"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN=python
else
  die "missing Python command"
fi

# Renderer output (bundled into app.asar)
[[ -f "electron/renderer/dist/index.html" ]] || die "missing renderer entrypoint: electron/renderer/dist/index.html"
if ! find "electron/renderer/dist" -type f \( -name "*.js" -o -name "*.css" \) -print -quit | grep -q .; then
  die "renderer dist has no JS/CSS assets (did Vite build run?)"
fi

# Python backend bundle (PyInstaller onedir)
[[ -d "dist-python/stellaris-backend" ]] || die "missing Python bundle dir: dist-python/stellaris-backend/"
if [[ "${TARGET}" == "windows-x64" ]]; then
  [[ -f "dist-python/stellaris-backend/stellaris-backend.exe" ]] || die "missing Python exe: dist-python/stellaris-backend/stellaris-backend.exe"
  BACKEND_EXE="dist-python/stellaris-backend/stellaris-backend.exe"
else
  [[ -f "dist-python/stellaris-backend/stellaris-backend" ]] || die "missing Python executable: dist-python/stellaris-backend/stellaris-backend"
  BACKEND_EXE="dist-python/stellaris-backend/stellaris-backend"
fi

# Identity names: a missing catalog silently degrades to raw IDs, so check the
# file sits where campaign_evidence.py looks for it and resolves a known civic.
CATALOG=""
for candidate in dist-python/stellaris-backend/_internal/stellaris_companion/identity_catalog.json \
                 dist-python/stellaris-backend/stellaris_companion/identity_catalog.json; do
  if [[ -f "${candidate}" ]]; then CATALOG="${candidate}"; break; fi
done
[[ -n "${CATALOG}" ]] || die "missing bundled identity catalog (stellaris_companion/identity_catalog.json)"
"${PYTHON_BIN}" - "${CATALOG}" <<'PY' || die "bundled identity catalog does not resolve machine_servitor"
import json, sys
civics = json.load(open(sys.argv[1], encoding="utf-8"))["civic"]
assert civics.get("machine_servitor") == "Rogue Servitor", civics.get("machine_servitor")
print(f"identity catalog ok: {sys.argv[1]} ({len(civics)} civics)")
PY

# Technology names sit beside the identity catalog and degrade the same silent way.
TECH_CATALOG="$(dirname "${CATALOG}")/technology_catalog.json"
[[ -f "${TECH_CATALOG}" ]] || die "missing bundled technology catalog (stellaris_companion/technology_catalog.json)"
"${PYTHON_BIN}" - "${TECH_CATALOG}" <<'PY' || die "bundled technology catalog does not resolve tech_cryostasis_1"
import json, sys
technologies = json.load(open(sys.argv[1], encoding="utf-8"))["technology"]
assert technologies.get("tech_cryostasis_1") == "Automated Colony Ships", technologies.get("tech_cryostasis_1")
print(f"technology catalog ok: {sys.argv[1]} ({len(technologies)} technologies)")
PY

"${PYTHON_BIN}" scripts/smoke_mcp_stdio.py "${BACKEND_EXE}" || die "bundled backend did not pass MCP stdio smoke test"
"${PYTHON_BIN}" scripts/smoke_electron_backend_boot.py "${BACKEND_EXE}" || die "bundled backend did not pass Electron boot smoke test"

# Claude Desktop MCPB extension package
if ! find "electron/dist/mcpb" -type f -name "stellaris-companion-mcp-relay-*.mcpb" -print -quit | grep -q .; then
  die "missing Claude Desktop MCPB package in electron/dist/mcpb/"
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
