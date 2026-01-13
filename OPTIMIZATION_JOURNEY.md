# Optimization Journey - Complete Analysis

**Date:** 2026-01-13

## The Critical Discovery

**ALL our enhanced tests used `gemini-2.0-flash` while production uses `gemini-3-flash-preview`.**

This means we had GOOD PROMPTS that we incorrectly concluded were bad because they produced flat responses on the wrong model.

```
Test Files Using Wrong Model:
- test_prompt_cleanup.py    → gemini-2.0-flash ❌
- test_middle_ground.py     → gemini-2.0-flash ❌
- test_enhanced.py          → gemini-2.0-flash ❌
- test_stress.py            → gemini-2.0-flash ❌
- test_tool_usage.py        → gemini-2.0-flash ❌

Production Code:
- companion.py              → gemini-3-flash-preview ✓
```

---

## The Journey (Chronological)

### Phase 1: Initial Cleanup (`test_prompt_cleanup.py`)

**Goal:** Remove redundancy from production prompt

**What we tried:**
- Stripped personality instructions to bare minimum
- Simplified tool instructions

**Result:**
- 5.7x faster
- BUT wrong personality ("By the Great Spirit" for egalitarian empire)
- Too terse

**Conclusion at the time:** "Simplified prompt loses personality"

**Actual issue:** Wrong model (`gemini-2.0-flash`)

---

### Phase 2: Middle Ground (`test_middle_ground.py`)

**Goal:** Keep personality, trim redundancy

**The prompt was actually GOOD:**
```python
PERSONALITY (critical - stay in character):
Your ethics define your worldview:
- Egalitarian: passionate about freedom, informal, questions authority
- Xenophile: curious about aliens, cooperative, optimistic
- Fanatic versions are MORE intense - let it show!

STRATEGIC DEPTH:
You are an ADVISOR, not just a reporter. For every answer:
- Don't just state facts - interpret what they MEAN for the empire
- Identify problems AND suggest specific solutions
- Connect observations to actionable advice
```

**Result:**
- Faster than production
- Responses still too short
- Added "STRATEGIC DEPTH" section per user request

**Conclusion at the time:** "Need more depth instructions"

**Actual issue:** Wrong model (`gemini-2.0-flash`) gave flat responses regardless of prompt

---

### Phase 3: Tool Usage Investigation (`test_tool_usage.py`)

**Goal:** Understand why enhanced never used tools

**What we found:**
- Enhanced used 0 tools on average
- Model said "I need more information" without calling tools
- Added stronger instruction: "CRITICAL: If data is missing, you MUST call a tool"

**Result:** Tool calls slightly improved but still inconsistent

**Conclusion at the time:** "Need even stronger tool instructions"

**Actual issue:** `gemini-2.0-flash` handles function calling differently than `gemini-3-flash-preview`

---

### Phase 4: Enhanced Snapshot (`test_enhanced.py`)

**Goal:** Pre-resolve data to reduce tool calls

**What we tried:**
- Added all 30 leaders (not truncated 15)
- Resolved ally/rival names
- Added current research explicitly

**The prompt was GOOD:**
```python
DATA & TOOLS:
- CRITICAL: If data is missing or incomplete, you MUST call a tool.
- Do NOT say "I need more information" without actually calling the tool.
- If you would say "I don't have that data" - STOP and call get_details()
```

**Result:**
- Faster (snapshot had data)
- But responses still flat and terse

**Conclusion at the time:** "Need response depth guidance"

**Actual issue:** Wrong model

---

### Phase 5: Stress Test (`test_stress.py`)

**Goal:** Comprehensive comparison (19 questions)

**Results (with wrong model):**
- 83% faster
- 95% fewer tool calls
- 59% shorter responses (problem!)
- 3/19 rated GOOD

**Issues observed:**
- Model asking user to run tools: "Could you run `get_details`?"
- Short, factual responses without advisory tone
- Missing proactive warnings about deficits

**Conclusion at the time:** "Need to fix tool calling bug, add depth"

**Actual issue:** `gemini-2.0-flash` behaves fundamentally differently

---

### Phase 6: The Breakthrough

**Discovery:** Production uses `gemini-3-flash-preview`, tests use `gemini-2.0-flash`

**When we switched to `gemini-3-flash-preview`:**

The SAME prompt that gave flat responses suddenly gave rich, advisory output:

**Before (gemini-2.0-flash):**
> "Our military power stands at 125210.14."

**After (gemini-3-flash-preview):**
> "Greetings, President! It's a pleasure to see our citizens thriving under the light of liberty. Our current military power stands at 125,210.14. However, as your advisor, I must point out that our energy reserves are feeling the strain—we're seeing a monthly deficit of -346.76 energy credits. We might want to consider expanding our Dyson capabilities!"

---

## What We Thought vs What Actually Happened

| We Thought | Reality |
|------------|---------|
| "Simplified prompt loses personality" | gemini-2.0-flash gives flat responses regardless |
| "Need stronger tool instructions" | gemini-2.0-flash handles AFC differently |
| "Need response depth guidance" | gemini-3-flash-preview naturally gives depth |
| "Model asks user to run tools" | gemini-2.0-flash doesn't trigger AFC properly |

---

## Prompts We Should Revisit

### Middle Ground Prompt (test_middle_ground.py)
This was a well-designed prompt with:
- Full personality guidance
- Strategic depth instructions
- Specific civics flavor

**Never tested with correct model.** Worth revisiting.

### Enhanced Prompt (test_enhanced.py)
Also well-designed with:
- Strong tool instructions
- Comprehensive snapshot integration
- Personality guidance

**Never tested with correct model.** Worth revisiting.

---

## The Final Solution

Use:
1. **Full production personality prompt** (don't simplify!)
2. **ASK MODE OVERRIDES** with "express yourself" instruction
3. **Comprehensive snapshot** (all leaders, resolved names)
4. **`gemini-3-flash-preview`** (not gemini-2.0-flash!)

```python
# The key line that makes it work:
model="gemini-3-flash-preview"  # NOT gemini-2.0-flash
```

---

## Lessons Learned

1. **Always verify which model you're testing with** - this cost us hours of prompt iteration

2. **Model selection matters more than prompt tweaking** - gemini-2.0-flash vs 3-flash-preview have fundamentally different response styles

3. **"Flat responses" might not be a prompt problem** - could be model capability

4. **Production code is the reference** - always check what it actually uses

5. **Good prompts can look bad on wrong model** - we had working prompts early on

---

## Files Summary

| File | Purpose | Model Used | Prompt Quality |
|------|---------|------------|----------------|
| `test_prompt_cleanup.py` | Initial cleanup | 2.0-flash ❌ | Too minimal |
| `test_middle_ground.py` | Balance personality/efficiency | 2.0-flash ❌ | **GOOD** |
| `test_enhanced.py` | Snapshot + tool instructions | 2.0-flash ❌ | **GOOD** |
| `test_stress.py` | Comprehensive comparison | 2.0-flash ❌ | **GOOD** |
| `test_tool_usage.py` | Tool behavior analysis | 2.0-flash ❌ | GOOD |
| `enhanced_companion.py` | **Final solution** | 3-flash ✓ | **GOOD** |

---

## Recommendation

The `test_middle_ground.py` prompt was actually excellent and should work well with `gemini-3-flash-preview`. It's more concise than using the full production prompt and might be worth testing:

```python
PERSONALITY (critical - stay in character):
Your ethics define your worldview:
- Egalitarian: passionate about freedom, informal
- Xenophile: curious about aliens, cooperative
- Fanatic versions are MORE intense - let it show!

STRATEGIC DEPTH:
You are an ADVISOR, not just a reporter:
- Interpret what facts MEAN for the empire
- Identify problems AND suggest specific solutions
- Connect observations to actionable advice
```

This could be a cleaner solution than using the full 2900-char production prompt.
