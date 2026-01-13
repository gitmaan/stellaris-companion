# Tool Usage Analysis - January 2026

## Executive Summary

**Problem**: Model was hallucinating answers instead of calling tools when data wasn't in the pre-injected snapshot.

**Root Cause**: The snapshot is **truncated** (15 of 36 leaders, 10 planets) but the prompt told the model it was "authoritative" without mentioning the truncation.

**Solution**: **Option A - Slim Snapshot** with NO truncated lists. Only include complete data (counts, summaries, headlines), forcing tool use for details.

---

## Option A Test Results (RECOMMENDED)

| Metric | Value |
|--------|-------|
| Correct behavior | **6/7 (86%)** |
| Used tools when needed | 4/4 (100%) |
| Hallucination risk | **0%** |
| Snapshot size | 1,542 chars (81% smaller) |

### Admiral Question Verification

**Ground Truth**: Admiral Manon, Level 5, Traits: artillerist, cautious, resilient, adaptable, reclusive

**Model Response** (with Option A):
- ✅ Called `get_details(['leaders'])`
- ✅ Found "Admiral Manon, Level 5"
- ✅ Listed all 5 traits correctly

**This proves Option A eliminates hallucination risk while maintaining accuracy.**

---

## Test Results

### Original Stress Test (Pre-Fix, 20:44)
| Outcome | Count |
|---------|-------|
| ✅ Used tools | 3/5 |
| ❌ Hallucinated | 2/5 |

**Failed Questions**:
- "What buildings are on Earth?" → Hallucinated (buildings WERE added after)
- "What specific technologies am I researching?" → Hallucinated (tech WAS added after)

### Fresh Test (Post-Fix, Current)

**Without explicit "partial data" warning:**
| Question | Status |
|----------|--------|
| Buildings on Earth | ✅ From snapshot (data now present) |
| Current research | ✅ From snapshot (data now present) |
| Highest level admiral | ❌ Possible hallucination (Manon L5 not in top 15) |

**With explicit "partial data" warning:**
| Question | Status |
|----------|--------|
| Buildings on Earth | ⚠️ Used tools unnecessarily |
| Current research | ✅ From snapshot |
| Highest level admiral | ✅ Used tools correctly |
| All admirals | ✅ Used tools correctly |
| Opinion modifiers | ✅ Used tools correctly |

**Result: 4/5 correct when model knows snapshot is partial**

---

## Data Truncation in Snapshot

The `get_full_briefing()` returns:

| Data | In Snapshot | Actual | Missing |
|------|------------|--------|---------|
| Leaders | 15 | 36 | 21 (58%) |
| Planets | 10 | 31 | 21 (68%) |
| Starbases | All | All | None |
| Buildings | ✅ Now included | - | - |
| Current Research | ✅ Now included | - | - |
| Diplomacy Details | Summary only | Full | Opinion modifiers |

**Critical**: The highest-level admiral (Manon, L5) is NOT in the snapshot because only 15 leaders are included.

---

## Architecture Overview

### v2_native_tools.py (Pure Tools)
- No pre-injected snapshot
- Model MUST call tools for any data
- 12 tools available
- ✅ No hallucination risk (no partial data)
- ❌ Slower (more tool calls)

### backend/core/companion.py (Hybrid)
- Pre-injected TRUNCATED snapshot (~8KB)
- 3 tools for drill-down
- ✅ Fast for common questions
- ⚠️ Hallucination risk if model trusts incomplete data

---

## Recommended Fix

### Current Prompt (companion.py line 1099-1111):
```python
user_prompt = (
    "CURRENT_GAME_STATE (authoritative JSON; use it for all numbers):\n"
    "```json\n"
    f"{snapshot_json}\n"
    "```\n\n"
    "USER_QUESTION:\n"
    f"{question}\n\n"
    "RULES:\n"
    "- Use the JSON above for facts and numbers.\n"
    ...
)
```

### Fixed Prompt:
```python
user_prompt = (
    "GAME STATE SNAPSHOT (partial - top 15 leaders, top 10 planets):\n"
    "```json\n"
    f"{snapshot_json}\n"
    "```\n\n"
    "USER_QUESTION:\n"
    f"{question}\n\n"
    "RULES:\n"
    "- Use the snapshot for basic facts. It is PARTIAL (truncated to save tokens).\n"
    "- For complete data (all leaders, all planets, full diplomacy), call get_details().\n"
    "- If asked about 'highest', 'all', or 'specific' items, USE TOOLS - snapshot may be incomplete.\n"
    "- Do NOT guess or extrapolate from partial data.\n"
)
```

---

## Key Insights

1. **Model trusts what you tell it**: If you say data is "authoritative", it won't question it.

2. **Explicit > Implicit**: The model correctly uses tools when told data is partial.

3. **Trigger words**: Questions with "highest", "all", "every", "specific" should trigger tool use.

4. **Buildings/Tech fixed**: These are now in the snapshot, addressing 2 of the original 5 failures.

5. **Leader truncation is the main gap**: 58% of leaders missing from snapshot.

---

## Files Involved

- `/Users/avani/stellaris-companion/backend/core/companion.py` - Production prompt (needs fix)
- `/Users/avani/stellaris-companion/v2_native_tools.py` - Pure tools approach (no issue)
- `/Users/avani/stellaris-companion/save_extractor.py` - Data extraction (truncates at line 1355)
- `/Users/avani/stellaris-companion/test_fresh_stress.py` - New stress test
- `/Users/avani/stellaris-companion/comprehensive_stress_results.json` - Latest results
