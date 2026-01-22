#!/bin/bash

# Ralph Wiggum - Rust Parser Migration Loop
# Migrates all extractors to use Rust parser with validation
#
# Usage: ./ralph-migrate.sh
#
# DUAL TERMINAL SETUP:
#   Terminal 1: ./ralph-migrate.sh           (status + control)
#   Terminal 2: tail -f .ralph-logs/latest.log   (full stream with code)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="specs/rust-migration"
LOG_DIR="$SCRIPT_DIR/.ralph-logs"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

mkdir -p "$LOG_DIR"

# Initialize log
TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
LOG_FILE="$LOG_DIR/migration_${TIMESTAMP}.log"
ln -sf "$LOG_FILE" "$LOG_DIR/latest.log"

echo "═══════════════════════════════════════════════════════════" > "$LOG_FILE"
echo "  Ralph Log Started: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG_FILE"
echo "═══════════════════════════════════════════════════════════" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

echo ""
echo -e "${BLUE}══════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  🚀 RALPH WIGGUM - Rust Parser Migration${NC}"
echo -e "${BLUE}══════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${CYAN}📺 To see full output with code being written:${NC}"
echo -e "${CYAN}   Open another terminal and run:${NC}"
echo ""
echo -e "   ${YELLOW}tail -f $LOG_DIR/latest.log${NC}"
echo ""
echo -e "${BLUE}──────────────────────────────────────────────────────────────${NC}"
echo ""

cd "$SCRIPT_DIR"

# Verify required files
if [ ! -f "$WORK_DIR/RALPH_BUILD.md" ]; then
  echo -e "${RED}❌ $WORK_DIR/RALPH_BUILD.md not found${NC}"
  exit 1
fi

if [ ! -f "$WORK_DIR/fix_plan.json" ]; then
  echo -e "${RED}❌ $WORK_DIR/fix_plan.json not found${NC}"
  exit 1
fi

if [ ! -f "test_save.sav" ]; then
  echo -e "${RED}❌ test_save.sav not found - needed for validation${NC}"
  exit 1
fi

ITERATION=0
MAX_ITERATIONS=50  # Safety limit

show_status() {
  echo ""
  echo -e "${BLUE}📋 Current Progress:${NC}"
  jq -r '.stories[] | "  \(if .passes then "✅" else "⬜" end) [\(.id)] \(.title)"' "$WORK_DIR/fix_plan.json" 2>/dev/null || echo "  (could not read fix_plan.json)"

  TOTAL=$(jq '.stories | length' "$WORK_DIR/fix_plan.json" 2>/dev/null || echo 0)
  DONE=$(jq '[.stories[] | select(.passes == true)] | length' "$WORK_DIR/fix_plan.json" 2>/dev/null || echo 0)
  echo ""
  echo -e "${BLUE}   $DONE / $TOTAL stories complete${NC}"

  # Show recent patterns
  PATTERN_COUNT=$(jq '.patterns | length' "$WORK_DIR/fix_plan.json" 2>/dev/null || echo "0")
  if [ "$PATTERN_COUNT" -gt 0 ]; then
    echo ""
    echo -e "${BLUE}📚 Patterns learned (${PATTERN_COUNT}):${NC}"
    jq -r '.patterns[-3:][]' "$WORK_DIR/fix_plan.json" 2>/dev/null | while read -r pattern; do
      echo "  • $pattern"
    done
  fi
}

while [ $ITERATION -lt $MAX_ITERATIONS ]; do
  ITERATION=$((ITERATION + 1))

  echo ""
  echo -e "${YELLOW}═══════════════════════════════════════════════════════════${NC}"
  echo -e "${YELLOW}  ITERATION $ITERATION - $(date '+%H:%M:%S')${NC}"
  echo -e "${YELLOW}═══════════════════════════════════════════════════════════${NC}"

  show_status

  # Check if already complete
  REMAINING=$(jq '[.stories[] | select(.passes == false)] | length' "$WORK_DIR/fix_plan.json" 2>/dev/null || echo 1)
  if [ "$REMAINING" -eq 0 ]; then
    echo ""
    echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  🎉 ALL STORIES COMPLETE!${NC}"
    echo -e "${GREEN}  Total iterations: $ITERATION${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"

    echo ""
    echo -e "${BLUE}📚 Final patterns learned:${NC}"
    jq -r '.patterns[]' "$WORK_DIR/fix_plan.json" 2>/dev/null | while read -r pattern; do
      echo "  • $pattern"
    done

    # Show final validation
    echo ""
    echo -e "${BLUE}Running final validation...${NC}"
    python3 v2_native_tools.py test_save.sav --briefing 2>&1 | head -20 || true

    exit 0
  fi

  # Get next story
  NEXT_STORY=$(jq -r '[.stories[] | select(.passes == false)] | sort_by(.priority) | .[0] | "[\(.id)] \(.title)"' "$WORK_DIR/fix_plan.json" 2>/dev/null || echo "unknown")
  echo ""
  echo -e "${CYAN}🎯 Working on: $NEXT_STORY${NC}"
  echo -e "${CYAN}   (watch tail -f .ralph-logs/latest.log for live output)${NC}"

  # Log iteration header
  {
    echo ""
    echo "═══════════════════════════════════════════════════════════"
    echo "  ITERATION $ITERATION - $(date '+%Y-%m-%d %H:%M:%S')"
    echo "  Working on: $NEXT_STORY"
    echo "═══════════════════════════════════════════════════════════"
    echo ""
  } >> "$LOG_FILE"

  # Run headless Claude - stream directly to terminal and log
  echo -e "${BLUE}🤖 Claude is working...${NC}"
  echo ""

  set +e  # Don't exit on error
  # Run claude, stream to terminal AND append to log simultaneously
  claude -p "$(cat $WORK_DIR/RALPH_BUILD.md)" \
    --allowedTools "Read,Write,Edit,Bash,Grep,Glob,Task" \
    2>&1 | while IFS= read -r line; do
      echo "$line"
      echo "$line" >> "$LOG_FILE"
    done
  CLAUDE_EXIT=${PIPESTATUS[0]}
  set -e

  # Read last part of log for signal checking
  OUTPUT=$(tail -300 "$LOG_FILE")

  # Check for errors
  if [ $CLAUDE_EXIT -ne 0 ]; then
    echo ""
    echo -e "${YELLOW}⚠ Claude exited with code $CLAUDE_EXIT${NC}"
    echo "Claude exited with code $CLAUDE_EXIT" >> "$LOG_FILE"
  fi

  # Check output for completion signals
  if echo "$OUTPUT" | grep -q "<ralph>PLAN_COMPLETE</ralph>"; then
    echo ""
    echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  🎉 ALL STORIES COMPLETE!${NC}"
    echo -e "${GREEN}  Total iterations: $ITERATION${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"

    echo ""
    echo -e "${BLUE}📚 Final patterns learned:${NC}"
    jq -r '.patterns[]' "$WORK_DIR/fix_plan.json" 2>/dev/null | while read -r pattern; do
      echo "  • $pattern"
    done

    exit 0
  fi

  if echo "$OUTPUT" | grep -q "<ralph>ITERATION_DONE</ralph>"; then
    echo ""
    echo -e "${GREEN}✓ Iteration $ITERATION complete${NC}"
  else
    echo ""
    echo -e "${YELLOW}⚠ No completion signal detected${NC}"
    # Don't exit - just continue to next iteration
    # The work may have been done even without the signal
  fi

  # Pause between iterations
  echo ""
  echo -e "${BLUE}⏳ Next iteration in 5 seconds... (Ctrl+C to stop)${NC}"
  sleep 5
done

echo ""
echo -e "${RED}❌ Reached max iterations ($MAX_ITERATIONS) without completing${NC}"
exit 1
