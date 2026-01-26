#!/bin/bash
set -e

# Ralph Wiggum Autonomous Development Loop
# Usage: ./ralph.sh [spec-dir]
# Example: ./ralph.sh specs/rust-parser

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SPEC_DIR="${1:-specs/rust-parser}"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Setup logging
LOG_DIR="${SCRIPT_DIR}/.ralph-logs"
mkdir -p "$LOG_DIR"
TIMESTAMP=$(date '+%Y%m%d-%H%M%S')
FEATURE_NAME=$(basename "$SPEC_DIR")
LOG_FILE="${LOG_DIR}/${FEATURE_NAME}-${TIMESTAMP}.log"

# Function to log to both console and file
log() {
  echo -e "$1"
  # Strip color codes for log file
  echo -e "$1" | sed 's/\x1b\[[0-9;]*m//g' >> "$LOG_FILE"
}

log "${BLUE}Starting Ralph Wiggum Loop${NC}"
log "${BLUE}Spec directory: ${SPEC_DIR}${NC}"
log "${BLUE}Log file: ${LOG_FILE}${NC}"
log ""

cd "$SCRIPT_DIR"

# Verify required files exist
if [ ! -f "${SPEC_DIR}/RALPH_BUILD.md" ]; then
  log "${RED}RALPH_BUILD.md not found in ${SPEC_DIR}${NC}"
  log "Run '/ralph plan' first to generate Ralph files."
  exit 1
fi

if [ ! -f "${SPEC_DIR}/fix_plan.json" ]; then
  log "${RED}fix_plan.json not found in ${SPEC_DIR}${NC}"
  log "Run '/ralph plan' first to generate Ralph files."
  exit 1
fi

ITERATION=0
MAX_ITERATIONS=${MAX_ITERATIONS:-100}  # Safety limit
STUCK_COUNT=0
MAX_STUCK=3  # Stop after 3 iterations without progress

while [ $ITERATION -lt $MAX_ITERATIONS ]; do
  ITERATION=$((ITERATION + 1))
  log ""
  log "${YELLOW}═══════════════════════════════════════════════════════════${NC}"
  log "${YELLOW}  RALPH ITERATION $ITERATION - $(date '+%Y-%m-%d %H:%M:%S')${NC}"
  log "${YELLOW}═══════════════════════════════════════════════════════════${NC}"
  log ""

  # Show current status
  log "${BLUE}Stories status:${NC}"
  STATUS_OUTPUT=$(jq -r '.stories[] | "  \(if .passes then "✅" else "⬜" end) [\(.id)] P\(.priority) \(.title)"' "${SPEC_DIR}/fix_plan.json" 2>/dev/null || echo "  (could not read fix_plan.json)")
  log "$STATUS_OUTPUT"
  log ""

  # Count remaining before iteration
  REMAINING_BEFORE=$(jq '[.stories[] | select(.passes == false)] | length' "${SPEC_DIR}/fix_plan.json" 2>/dev/null || echo "?")
  log "${BLUE}Remaining stories: ${REMAINING_BEFORE}${NC}"
  log ""

  # Run headless Claude
  log "${BLUE}Running Claude...${NC}"
  ITERATION_LOG="${LOG_DIR}/${FEATURE_NAME}-${TIMESTAMP}-iter${ITERATION}.log"

  OUTPUT=$(claude -p "$(cat ${SPEC_DIR}/RALPH_BUILD.md)" \
    --allowedTools "Read,Write,Edit,Bash,Grep,Glob,Task" \
    2>&1) || true

  # Save full iteration output to separate log
  echo "$OUTPUT" > "$ITERATION_LOG"

  # Show last 150 lines of output to console
  echo "$OUTPUT" | tail -150

  # Append summary to main log
  echo "--- Iteration $ITERATION output (last 50 lines) ---" >> "$LOG_FILE"
  echo "$OUTPUT" | tail -50 >> "$LOG_FILE"
  echo "--- End iteration $ITERATION ---" >> "$LOG_FILE"

  # Check for completion
  if echo "$OUTPUT" | grep -q "<ralph>PLAN_COMPLETE</ralph>"; then
    log ""
    log "${GREEN}═══════════════════════════════════════════════════════════${NC}"
    log "${GREEN}  ALL STORIES COMPLETE!${NC}"
    log "${GREEN}  Total iterations: $ITERATION${NC}"
    log "${GREEN}  Log file: $LOG_FILE${NC}"
    log "${GREEN}═══════════════════════════════════════════════════════════${NC}"

    # Show final patterns learned
    log ""
    log "${BLUE}Patterns learned:${NC}"
    jq -r '.patterns[]' "${SPEC_DIR}/fix_plan.json" 2>/dev/null | while read -r pattern; do
      log "  - $pattern"
    done

    # Show discovered issues
    DISCOVERED=$(jq -r '.discovered | length' "${SPEC_DIR}/fix_plan.json" 2>/dev/null || echo "0")
    if [ "$DISCOVERED" -gt 0 ]; then
      log ""
      log "${YELLOW}Discovered issues:${NC}"
      jq -r '.discovered[]' "${SPEC_DIR}/fix_plan.json" 2>/dev/null | while read -r issue; do
        log "  - $issue"
      done
    fi

    # Final status
    log ""
    log "${BLUE}Final stories status:${NC}"
    jq -r '.stories[] | "  \(if .passes then "✅" else "⬜" end) [\(.id)] \(.title)"' "${SPEC_DIR}/fix_plan.json" 2>/dev/null

    exit 0
  fi

  # Count remaining after iteration
  REMAINING_AFTER=$(jq '[.stories[] | select(.passes == false)] | length' "${SPEC_DIR}/fix_plan.json" 2>/dev/null || echo "?")

  # Check for iteration done
  if echo "$OUTPUT" | grep -q "<ralph>ITERATION_DONE</ralph>"; then
    log "${GREEN}Iteration $ITERATION complete - stories remaining: ${REMAINING_AFTER}${NC}"
    STUCK_COUNT=0  # Reset stuck counter on success

    # Show which story was completed
    if [ "$REMAINING_BEFORE" != "$REMAINING_AFTER" ]; then
      COMPLETED=$((REMAINING_BEFORE - REMAINING_AFTER))
      log "${GREEN}  → Completed $COMPLETED story/stories this iteration${NC}"
    fi
  else
    log "${YELLOW}No completion signal - Ralph may be stuck${NC}"
    STUCK_COUNT=$((STUCK_COUNT + 1))

    if [ $STUCK_COUNT -ge $MAX_STUCK ]; then
      log "${RED}Ralph stuck for $MAX_STUCK iterations - stopping${NC}"
      log "${RED}Check logs at: $LOG_FILE${NC}"
      log "${RED}Last iteration: $ITERATION_LOG${NC}"
      exit 1
    fi
  fi

  # Brief pause between iterations
  sleep 2
done

log "${RED}Reached maximum iterations ($MAX_ITERATIONS)${NC}"
exit 1
