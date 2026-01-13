# Prompt Optimization Progress

**Last Updated:** 2026-01-13

## Current Best: Production Personality + Enhanced Data/Tools (v3)

This prompt is **83% faster** than production (14.7s → 2.6s avg) while maintaining personality and accuracy.

### Key Innovation
Instead of building a separate simplified prompt, we now:
1. Use the **production personality system prompt** as the base
2. Replace the TOOLS section with optimized DATA & TOOLS instructions
3. Add RESPONSE STYLE guidance for depth

This ensures personality consistency between production and enhanced modes.

### System Prompt Builder

```python
def build_enhanced_system_prompt(base_personality_prompt: str) -> str:
    """
    Use the PRODUCTION personality prompt and replace the tools section
    with our enhanced data & tools instructions.
    """
    # Remove the outdated TOOLS section from production prompt
    tools_marker = "TOOLS: You have access to tools"
    if tools_marker in base_personality_prompt:
        prompt = base_personality_prompt[:base_personality_prompt.index(tools_marker)]
    else:
        prompt = base_personality_prompt

    # Add our enhanced data & tools section
    prompt += """DATA & TOOLS:
- The game state snapshot is pre-loaded in the user message - use it for most answers.
- CRITICAL: If data is missing or incomplete, you MUST call a tool. Do NOT say "I need more information" without actually calling the tool.
- If you would say "I don't have that data" - STOP and call get_details() or search_save_file() instead.
- Available tools:
  * get_details(categories=["leaders", "diplomacy", "technology", etc.]) - for structured data
  * search_save_file(query="search term") - for finding specific things
- When you see raw IDs without names, call tools to resolve them.

RESPONSE STYLE:
- Maintain your full personality, colorful language, and in-character voice.
- Being efficient with tools does NOT mean being terse - express yourself!
- Proactively mention critical issues (deficits, threats) even if not directly asked.
- For complex questions (strategy, assessments, economy): provide THOROUGH analysis with specific numbers.
- Don't just summarize - explain what the data MEANS and give specific, actionable recommendations.
- Include relevant context: treasury balances, exact deficit amounts, comparative strengths."""

    return prompt
```

### Usage

```python
from core.companion import Companion

companion = Companion(save_path="save.sav")
production_prompt = companion.system_prompt  # Get production personality prompt
enhanced_prompt = build_enhanced_system_prompt(production_prompt)
```

### User Message Format

```python
def build_user_prompt(snapshot_json: str, question: str) -> str:
    return f"GAME STATE:\n```json\n{snapshot_json}\n```\n\n{question}"
```

### Enhanced Snapshot

The snapshot should include:
1. Base `get_full_briefing()` data
2. `allies_resolved` - ally IDs with names (if resolvable)
3. `current_research` - explicit field (even if "None - research slots are idle")

```python
def build_enhanced_snapshot(extractor) -> dict:
    snapshot = extractor.get_full_briefing()

    # Resolve ally IDs to names
    ally_ids = snapshot.get('diplomacy', {}).get('allies', [])
    ally_names = []
    for aid in ally_ids:
        name = get_empire_name_by_id(extractor, aid)  # needs implementation
        ally_names.append({"id": aid, "name": name})

    if 'diplomacy' in snapshot:
        snapshot['diplomacy']['allies_resolved'] = ally_names

    # Add current research explicitly
    tech = extractor.get_technology()
    snapshot['current_research'] = tech.get('current_research', {})
    if not snapshot['current_research']:
        snapshot['current_research'] = "None - research slots are idle"

    return snapshot
```

---

## Benchmark Results (v3 - 19 questions)

### Speed Comparison

| Version | Avg Time | Avg Tools | Avg Words |
|---------|----------|-----------|-----------|
| Production | 14.7s | 1.9 | 286 |
| Enhanced | 2.6s | 0.1 | 116 |
| **Improvement** | **83% faster** | 95% fewer | 59% shorter |

### Quality Assessment

- **3/19 responses rated GOOD** by automated quality check
- However, manual review shows most "CHECK" responses are actually good but more focused
- Strategic assessment: 474 words with thorough analysis, recommendations, specific numbers

### Sample Strategic Assessment (Enhanced)

> "Alright, President! Let's dive into the state of our glorious United Nations of Earth 2..."
> - Covers economy, colonies, diplomacy, military, leadership
> - Lists specific numbers (346.76 energy deficit, 125210.14 military power)
> - Provides 4 actionable recommendations
> - Maintains egalitarian/xenophile personality

### Personality Examples ✅

- "our glorious United Nations of Earth 2"
- "beacon of liberty"
- "it's our duty to ensure prosperity and freedom for all"
- "President" (correct address style for democratic empire)

### Response Depth Examples

| Question | Production | Enhanced |
|----------|------------|----------|
| Strategic assessment | 520 words | 474 words |
| Top priorities | 465 words | 185 words (focused) |
| Military power | 116 words | 49 words (direct answer) |

### Trade-off Summary

- **Production**: Longer, more context, proactively warns about deficits in most responses
- **Enhanced**: More focused, answers the question directly, still proactive on critical issues

---

## Key Learnings

### What Made the Difference (v3)

1. **Use production personality as base** - Don't recreate personality guidance, reuse it:
   - ❌ Building separate simplified prompt with personality hints
   - ✅ Take production system prompt, remove TOOLS section, add enhanced DATA & TOOLS

2. **Stronger tool instruction** - Changed from passive to imperative:
   - ❌ "If the snapshot lacks details, call the tools"
   - ✅ "CRITICAL: If data is missing, you MUST call a tool. Do NOT say 'I need more information' without actually calling the tool."

3. **Response depth guidance** - Added explicit instructions for complex questions:
   - "For complex questions: provide THOROUGH analysis with specific numbers"
   - "Don't just summarize - explain what the data MEANS"
   - "Include relevant context: treasury balances, exact deficit amounts"

4. **Pre-injected snapshot** - Embed game state JSON in user message to avoid tool calls

### What Didn't Work

1. **Separate simplified prompt** - Lost personality nuance, caused wrong persona ("By the Great Spirit" for egalitarian empire)
2. **"Minimize tool usage"** - Made model too hesitant, never used tools even when needed
3. **Generic ethics list** - Listing all ethics types confused the model
4. **"End with engagement"** - Implied AI could take action in game

### Prompt Architecture

| Component | Source |
|-----------|--------|
| Personality | Production system prompt (up to TOOLS section) |
| Data/Tools | Enhanced instructions (pre-injected snapshot, critical tool call instruction) |
| Response Style | Depth guidance, personality reinforcement |

---

## Still To Optimize

1. **Response verbosity tuning** - Enhanced averages 116 words vs production's 286. Consider:
   - Question-specific response length targets
   - More explicit "be thorough" instructions for certain question types

2. **Empire name resolution improvements** - Current implementation works for:
   - Known localization keys (EMPIRE_DESIGN_orbis → United Nations of Earth)
   - Procedural names (%ADJECTIVE% patterns)
   - But may miss some edge cases

3. **Snapshot completeness** - Consider adding more data to reduce tool calls:
   - Top 5 empire relationships with opinion scores
   - Nearby hostile empires
   - Recent significant events

4. **Integration into production** - Apply the enhanced approach to `companion.py`:
   - Replace `ask_simple()` system prompt building
   - Add pre-injected snapshot to user message
   - Test in real usage scenarios

---

## Test Files

- `test_stress.py` - **Current best**: 19 questions, production personality + enhanced data/tools
- `test_enhanced.py` - Enhanced snapshot testing (predecessor to v3)
- `test_middle_ground.py` - Earlier iteration tests
- `test_tool_usage.py` - Tool usage analysis across many questions
- `test_prompt_cleanup.py` - Initial cleanup experiments

## Results Files

- `stress_test_results.json` - Latest v3 benchmark (19 questions)
- `enhanced_results.json` - Earlier benchmark data
- `middle_ground_results.json` - Earlier results
- `tool_usage_results.json` - Detailed tool analysis
