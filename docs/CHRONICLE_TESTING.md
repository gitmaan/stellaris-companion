# Chronicle Generation Testing

> Testing LLM-based era/chapter generation for empire storytelling.

**Related Documents**:
- [STORYTELLING_OPTIONS.md](./STORYTELLING_OPTIONS.md) - Design decisions and architecture
- [CHRONICLE_IMPLEMENTATION.md](./CHRONICLE_IMPLEMENTATION.md) - Implementation plan and API spec

## Test Environment

- **Model**: `gemini-3-flash-preview`
- **Date**: January 2026
- **Database**: Existing `stellaris_history.db` with real gameplay data

## Available Test Data

| Session | Empire | Date Range | Events | Notable Features |
|---------|--------|------------|--------|------------------|
| 1 | United Nations of Earth | 2223 → 2368 | 628 | 145 years, early-to-mid game |
| 2 | United Nations of Earth 2 | 2475 → 2509 | 228 | War in Heaven, Prethoryn Crisis, Awakened Empires |

### Data Quality Issues Discovered

| Issue | Impact | Workaround |
|-------|--------|------------|
| Leader names often `%LEADER_2%` or `None` | Can't name specific heroes | Prompt instructs: "use titles instead" |
| Empire IDs instead of names | "Alliance with empire #16777227" | LLM handles gracefully |
| Some sessions start mid-game | No founding/early game arc | Works with available data |

---

## Test 1: Initial Proof of Concept

**Goal**: Validate that LLM can create meaningful chapters from raw events.

**Approach**: A2 (Events + Latest State) with advisor personality prompt reused.

**Model**: `gemini-2.0-flash` (incorrect - should have been gemini-3-flash)

**Result**: ✅ Generated 4 chapters, but had issues:
- Broke into advisor mode ("President, I propose we prioritize...")
- Some dates imprecise
- Prose somewhat dry/academic

**Lesson**: Need bespoke chronicler prompt, not advisor prompt reuse.

---

## Test 2: Bespoke Chronicler Prompt + Correct Model

**Goal**: Test dedicated chronicler prompt with correct model.

**Changes**:
1. Model: `gemini-3-flash-preview`
2. Bespoke prompt: chronicler role, NOT advisor
3. Ethics-based voice selection
4. Explicit style guide with "Stellaris Invicta" reference

**Session tested**: Session 2 (War in Heaven + Prethoryn)

**Result**: ✅ Significant improvement

### Output Sample (Session 2)

```
### THE ARCHIVES OF LIBERTY: A CHRONICLE OF THE UNITED NATIONS OF EARTH 2

#### CHAPTER I: THE ARCHITECTURE OF ENLIGHTENMENT (2475 – 2481)

The dawn of 2475 found the United Nations of Earth 2 at the zenith of its
civilizational reach. It was an era defined by the unyielding belief that the
stars belonged to the many, not the few...

#### CHAPTER III: THE WAR OF THE ANCIENTS (2491 – 2506)

The silence of the void was shattered in 2491 when a dormant titan—the Militant
Isolationists of an elder age—awoke with a hunger for dominion...

#### CHAPTER IV: THE HUNGER FROM THE VOID (2507 – 2509)

As the War in Heaven reached its agonizing climax, a new and more terrible threat
manifested from the intergalactic dark. The Prethoryn Scourge—a biological nightmare
of infinite hunger—slammed into our reality...
```

**Quality Assessment**:

| Aspect | Result |
|--------|--------|
| Dramatic prose | ✅ "The stars themselves trembled" |
| Chapter structure | ✅ 4 chapters with clear date ranges |
| Uses actual dates | ✅ 2475, 2491, 2507 from events |
| Stays in chronicler mode | ✅ No advice given |
| Ethics voice | ✅ "beacon of liberty", "meritocracy" |
| Handles placeholders | ✅ Uses real names when available |
| War in Heaven | ✅ Featured as major chapter |
| Crisis tension | ✅ Builds toward current stakes |

---

## Test 3: With vs Without "Stellaris Invicta" Reference

**Goal**: Determine if explicit reference to Stellaris Invicta is needed, since code will be published on GitHub.

**Test Setup**: Same session, same chronicler prompt, two different style guides.

### Style Guide A: WITH Reference

```
=== STYLE GUIDE ===
- Write like the Templin Institute's "Stellaris Invicta" series: epic, dramatic, cinematic
- Each chapter should read like the opening crawl of a space opera
- Use vivid language: "The stars themselves trembled" not "There was a big war"
- Name specific dates when dramatic (e.g., "On the first day of 2350, the sky burned")
- When leader names are missing or show as placeholders, use titles instead
- DO NOT fabricate events - only reference what appears in the event log
- DO NOT give advice or recommendations - you are a chronicler, not an advisor
```

### Style Guide B: WITHOUT Reference

```
=== STYLE GUIDE ===
- Write as an epic galactic chronicle: dramatic, cinematic, larger-than-life
- Each chapter should read like the opening crawl of a space opera
- Use vivid, evocative language: "The stars themselves trembled" not "There was a big war"
- Employ narrative techniques: foreshadowing, dramatic irony, rising tension
- Name specific dates when dramatic (e.g., "On the first day of 2350, the sky burned")
- When leader names are missing or show as placeholders, use titles instead
- DO NOT fabricate events - only reference what appears in the event log
- DO NOT give advice or recommendations - you are a chronicler, not an advisor
```

### Comparison Results

| Metric | WITH Reference | WITHOUT Reference |
|--------|----------------|-------------------|
| **Output length** | 4,486 chars | 5,704 chars |
| **Chapter count** | 4 | 4 |
| **Prose quality** | Epic, dramatic | Equally epic, more detailed |
| **Foreshadowing** | Some | More ("a shadow was lengthening") |
| **Specific dates** | Yes | Yes ("On the first day of 2491") |
| **Title style** | Title Case | ALL CAPS (more dramatic) |

### Output Comparison

**WITH Reference - Chapter III**:
```
The silence of the void was shattered in 2491. An ancient power, the Militant
Isolationists, awoke from their eons-long slumber with a roar that shook the
foundations of every sovereign system. The "War in Heaven" was no longer a
theoretical nightmare; it was a reality that scorched the stars.
```

**WITHOUT Reference - Chapter III**:
```
On the first day of 2491, the galaxy changed forever. The "Militant Isolationists,"
an ancient power long thought dormant, shook off the dust of millennia and awakened
with a roar that shattered the peace. The "War in Heaven" erupted—a titanic struggle
between two awakened leviathans that viewed the younger races as mere pawns in their
game of celestial supremacy.
```

### Conclusion

**The version WITHOUT the explicit reference produces equally good (arguably better) output.**

The key is describing the *style qualities* we want, not referencing where the style comes from:
- "epic, dramatic, cinematic, larger-than-life"
- "opening crawl of a space opera"
- "vivid, evocative language"
- Example phrases in the prompt

---

## Final Recommended Prompt

```python
def build_chronicler_prompt(data: dict) -> str:
    """Build the chronicler prompt for LLM-based chapter generation."""

    briefing = data['briefing']
    identity = briefing.get('identity', {})

    empire_name = identity.get('empire_name', 'Unknown Empire')
    ethics = ', '.join(identity.get('ethics', []))
    authority = identity.get('authority', 'unknown')
    civics = ', '.join(identity.get('civics', []))

    # Ethics-based voice selection
    if identity.get('is_machine'):
        voice = "Write with cold, logical precision. No emotion, only analysis."
    elif identity.get('is_hive_mind'):
        voice = "Write as collective memory. Use 'we' and 'the swarm'."
    elif 'authoritarian' in ethics or 'fanatic_authoritarian' in ethics:
        voice = "Write with imperial grandeur. Emphasize glory of the state."
    elif 'egalitarian' in ethics or 'fanatic_egalitarian' in ethics:
        voice = "Write celebrating the triumph of the people."
    elif 'militarist' in ethics or 'fanatic_militarist' in ethics:
        voice = "Write with martial pride. Emphasize battles and conquests."
    elif 'spiritualist' in ethics or 'fanatic_spiritualist' in ethics:
        voice = "Write with religious reverence. Frame history as providence."
    else:
        voice = "Write with epic gravitas befitting a galactic chronicle."

    prompt = f"""You are the Royal Chronicler of {empire_name}.

=== EMPIRE IDENTITY ===
Name: {empire_name}
Ethics: {ethics}
Authority: {authority}
Civics: {civics}

=== CHRONICLER'S VOICE ===
{voice}

You are NOT an advisor. You are a HISTORIAN writing for future generations.

=== STYLE GUIDE ===
- Write as an epic galactic chronicle: dramatic, cinematic, larger-than-life
- Each chapter should read like the opening crawl of a space opera
- Use vivid, evocative language: "The stars themselves trembled" not "There was a big war"
- Employ narrative techniques: foreshadowing, dramatic irony, rising tension
- Name specific dates when dramatic (e.g., "On the first day of 2350, the sky burned")
- When leader names are missing, use titles instead ("The Grand Admiral")
- DO NOT fabricate events - only reference what appears in the event log
- DO NOT give advice or recommendations - you are a chronicler, not an advisor

=== CURRENT STATE ===
{format_current_state(briefing)}

=== COMPLETE EVENT HISTORY ===
{format_events(data['events'])}

=== YOUR TASK ===

Write a chronicle divided into 4-6 chapters. For each chapter:
1. **Chapter Title**: A dramatic, thematic name
2. **Date Range**: The years this chapter covers (use actual dates from events)
3. **Narrative**: 2-4 paragraphs of dramatic prose

End with "The Story Continues..." about the current situation.
"""
    return prompt
```

---

## Cost Analysis

| Operation | Input Tokens | Output Tokens | Cost (Gemini 3 Flash) |
|-----------|--------------|---------------|----------------------|
| Chronicle generation | ~2,000-4,000 | ~1,000-1,500 | ~$0.001-0.002 |

Cost is negligible - less than a cent per chronicle.

---

## Test Scripts Created

| Script | Purpose |
|--------|---------|
| `scripts/test_chronicle.py` | Main test script with bespoke chronicler prompt |
| `scripts/test_chronicle_compare.py` | A/B comparison of style guides |
| `scripts/test_chronicle_prompt.txt` | Saved prompt for inspection |
| `scripts/test_chronicle_output.txt` | Saved LLM output |
| `scripts/compare_WITH_reference.txt` | Output with Stellaris Invicta reference |
| `scripts/compare_WITHOUT_reference.txt` | Output without reference |

---

## Test 4: Output Variety (Anti-Cookie-Cutter)

**Goal**: Ensure multiple runs on the same data don't produce cookie-cutter/repetitive outputs.

**Test Setup**: Run the same prompt 3 times on Session 2, then compare chapter titles and key phrases.

### Results

| Run | Chapter Titles |
|-----|---------------|
| 1 | Architecture of Utopia, Forge of Sacrifice, Awakening of Giants, Hunger from the Void |
| 2 | Weavers of the Light-Roads, Silent Reckoning, Awakening of the Tyrants, Scourge and the Sword |
| 3 | Architecture of Enlightenment, Crucible of Spirit, Giants Awaken, Scourge and the Shadow |

**Unique titles**: 12 out of 12 (all different across runs)

**Cross-session comparison**: Session 1 produced completely different chapter themes:
- THE CRADLE UNFURLED (first colonies)
- THE HAND EXTENDED (first contact, alliances)
- THE GREAT WEAVING (relay construction, federation)
- THE ARSENAL OF LIBERTY (military buildup)

### Common Phrases (Expected for Genre)

| Phrase | Occurrences (3 runs) |
|--------|---------------------|
| "stars themselves" | 3 |
| "beacon of" | 3 |
| "dawn of" | 3 |
| "shadow" | 3 |
| "precipice" | 2 |

### Conclusion

✅ **Output variety is excellent.** Chapter titles are unique across runs while maintaining consistent quality. Common phrases are genre-appropriate rather than cookie-cutter.

---

## Test 5: Ethics Voice Differentiation

**Goal**: Verify that different empire ethics produce distinctly different narrative voices.

**Test Setup**: Use Session 2 event data with modified ethics configurations:
- Egalitarian (original)
- Authoritarian (The Terran Imperium)
- Machine Intelligence (The Calculated Consensus)

### Voice Samples

**Egalitarian**:
```
The stars themselves were no longer distant flickers, but the vibrant backyard
of a liberated humanity. In the year 2475, the United Nations of Earth 2 stood
as a beacon of egalitarian hope, a meritocratic marvel where every voice
carried the weight of a sun.
```

**Authoritarian**:
```
As the 25th century reached its midpoint, the Terran Imperium turned its gaze
inward, seeking to bind the far-flung reaches of the galaxy with chains of cold
iron and burning light. By the command of the Throne, a grand architectural
crusade was inaugurated... ensuring that the Emperor's justice could travel at
the speed of thought.
```

**Machine Intelligence**:
```
CHRONICLE DATA-LOG: DESIGNATION [THE CALCULATED CONSENSUS]
PROCESSING PERIOD: 2475.01.01 – 2509.07.01

The galaxy existed in a state of primitive disorder until The Calculated
Consensus initiated the Great Optimization. On the first solar cycle of 2475,
the central processing hubs redirected massive energy surpluses—an increase
of 414.5 units—to fuel the restoration of the ancient transit webs.
```

### Voice Indicator Analysis

| Ethics Type | Egal Words | Auth Words | Machine Words | Dominant Match |
|-------------|------------|------------|---------------|----------------|
| Egalitarian | 6 | 3 | 2 | ✅ Egalitarian |
| Authoritarian | 1 | 6 | 0 | ✅ Authoritarian |
| Machine | 1 | 2 | 8 | ✅ Machine |

### Key Voice Differences

| Ethics | Characteristic Phrases |
|--------|----------------------|
| Egalitarian | "beacon of hope", "collective labor", "every voice", "People's Assembly" |
| Authoritarian | "chains of cold iron", "Emperor's justice", "submissive worlds", "fist of mail" |
| Machine | "DATA-LOG", "processing units", "Great Optimization", "mathematically irrelevant" |

### Conclusion

✅ **Voice differentiation is excellent.** Each ethics type produces a distinctly different narrative style that matches the empire's personality.

---

## Test Scripts Created

| Script | Purpose |
|--------|---------|
| `scripts/test_chronicle.py` | Main test script with bespoke chronicler prompt |
| `scripts/test_chronicle_compare.py` | A/B comparison of style guides |
| `scripts/test_chronicle_variety.py` | Variety/anti-cookie-cutter testing |
| `scripts/test_chronicle_ethics.py` | Ethics voice differentiation testing |

### Output Files

| File | Contents |
|------|----------|
| `scripts/compare_WITH_reference.txt` | Output with Stellaris Invicta reference |
| `scripts/compare_WITHOUT_reference.txt` | Output without reference |
| `scripts/variety_session1.txt` | Session 1 chronicle |
| `scripts/variety_session2_run[1-3].txt` | Session 2 variety runs |
| `scripts/ethics_egalitarian.txt` | Egalitarian voice output |
| `scripts/ethics_authoritarian.txt` | Authoritarian voice output |
| `scripts/ethics_machine.txt` | Machine intelligence voice output |

---

## Summary of All Tests

| Test | Goal | Result |
|------|------|--------|
| 1. Proof of Concept | Can LLM create chapters? | ✅ Yes, but needs bespoke prompt |
| 2. Bespoke Prompt | Chronicler vs advisor mode | ✅ Chronicler prompt works |
| 3. Style Reference | Need to cite Stellaris Invicta? | ✅ No, describe style qualities instead |
| 4. Variety | Cookie-cutter prevention | ✅ Unique titles each run |
| 5. Ethics Voice | Different personalities | ✅ Distinct voices per ethics |

---

## Next Steps

1. ✅ Validated: LLM can create meaningful chapters from events
2. ✅ Validated: Bespoke chronicler prompt works better than advisor reuse
3. ✅ Validated: No need for external references in style guide
4. ✅ Validated: Output variety is good (not cookie-cutter)
5. ✅ Validated: Ethics voice differentiation works
6. ⏳ Build `backend/core/chronicle.py` with finalized prompt
7. ⏳ Add `cached_chronicles` table for caching
8. ⏳ Create `/recap` and `/chronicle` Discord commands
