#!/bin/bash
set -e

# Ralph Wiggum Autonomous Development Loop
# Usage: ./ralph.sh [spec-dir]
# Example: ./ralph.sh specs/electron-app

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SPEC_DIR="${1:-specs/electron-app}"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}Starting Ralph Wiggum Loop${NC}"
echo -e "${BLUE}Spec directory: ${SPEC_DIR}${NC}"
echo ""

cd "$SCRIPT_DIR"

# Verify required files exist
if [ ! -f "${SPEC_DIR}/RALPH_BUILD.md" ]; then
  echo -e "${RED}RALPH_BUILD.md not found in ${SPEC_DIR}${NC}"
  echo "Run '/ralph plan' first to generate Ralph files."
  exit 1
fi

if [ ! -f "${SPEC_DIR}/fix_plan.json" ]; then
  echo -e "${RED}fix_plan.json not found in ${SPEC_DIR}${NC}"
  echo "Run '/ralph plan' first to generate Ralph files."
  exit 1
fi

ITERATION=0
MAX_ITERATIONS=${MAX_ITERATIONS:-100}  # Safety limit

while [ $ITERATION -lt $MAX_ITERATIONS ]; do
  ITERATION=$((ITERATION + 1))
  echo ""
  echo -e "${YELLOW}═══════════════════════════════════════════════════════════${NC}"
  echo -e "${YELLOW}  RALPH ITERATION $ITERATION - $(date '+%Y-%m-%d %H:%M:%S')${NC}"
  echo -e "${YELLOW}═══════════════════════════════════════════════════════════${NC}"
  echo ""

  # Show current status
  echo -e "${BLUE}Stories status:${NC}"
  jq -r '.stories[] | "  \(if .passes then "✅" else "⬜" end) [\(.id)] P\(.priority) \(.title)"' "${SPEC_DIR}/fix_plan.json" 2>/dev/null || echo "  (could not read fix_plan.json)"
  echo ""

  # Count remaining
  REMAINING=$(jq '[.stories[] | select(.passes == false)] | length' "${SPEC_DIR}/fix_plan.json" 2>/dev/null || echo "?")
  echo -e "${BLUE}Remaining stories: ${REMAINING}${NC}"
  echo ""

  # Run headless Claude
  OUTPUT=$(claude -p "$(cat ${SPEC_DIR}/RALPH_BUILD.md)" \
    --allowedTools "Read,Write,Edit,Bash,Grep,Glob,Task" \
    2>&1) || true

  # Show last 150 lines of output
  echo "$OUTPUT" | tail -150

  # Check for completion
  if echo "$OUTPUT" | grep -q "<ralph>PLAN_COMPLETE</ralph>"; then
    echo ""
    echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  ALL STORIES COMPLETE!${NC}"
    echo -e "${GREEN}  Total iterations: $ITERATION${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"

    # Show final patterns learned
    echo ""
    echo -e "${BLUE}Patterns learned:${NC}"
    jq -r '.patterns[]' "${SPEC_DIR}/fix_plan.json" 2>/dev/null | while read -r pattern; do
      echo "  - $pattern"
    done

    # Show discovered issues
    DISCOVERED=$(jq -r '.discovered | length' "${SPEC_DIR}/fix_plan.json" 2>/dev/null || echo "0")
    if [ "$DISCOVERED" -gt 0 ]; then
      echo ""
      echo -e "${YELLOW}Discovered issues:${NC}"
      jq -r '.discovered[]' "${SPEC_DIR}/fix_plan.json" 2>/dev/null | while read -r issue; do
        echo "  - $issue"
      done
    fi

    exit 0
  fi

  # Check for iteration done
  if echo "$OUTPUT" | grep -q "<ralph>ITERATION_DONE</ralph>"; then
    echo -e "${GREEN}Iteration $ITERATION complete${NC}"
  else
    echo -e "${YELLOW}No completion signal - Ralph may be stuck${NC}"
    echo -e "${YELLOW}Check output above for errors${NC}"
  fi

  # Brief pause between iterations
  sleep 2
done

echo -e "${RED}Reached maximum iterations ($MAX_ITERATIONS)${NC}"
exit 1
