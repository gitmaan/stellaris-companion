# Chronicle & Roleplay Features

## Overview

This document outlines features to make the Stellaris Companion more narrative-driven, inspired by **Stellaris Invicta** (Templin Institute). The goal is to transform the advisor from a factual Q&A bot into an immersive storyteller that chronicles your empire's history.

**Related:** See `docs/RUST_PARSER_ARCHITECTURE.md` for the parsing layer that feeds data into these features.

---

## Current State

| Component | Status | Roleplay Capability |
|-----------|--------|---------------------|
| **Personality System** | ✅ Ethics/civics → tone mapping | Static language style, not narrative |
| **Save Monitoring** | ✅ 50+ event types detected | Tracks wars, deaths, crises but doesn't narrate |
| **History Database** | ✅ Snapshots + events stored | Data exists but isn't woven into storytelling |
| **Electron App** | ✅ Chat, Recap, Settings pages | RecapPage exists but is bullet-point style |
| **Discord Bot** | ✅ /ask /briefing /status /history | Factual focus, minimal dramatic framing |

---

## Proposed Features

### 1. Chronicle System - Narrative Event Layer

Transform raw events into dramatic narrative based on personality.

**New Module:** `backend/core/chronicle.py`

```python
def narrate_event(event_type: str, data: dict, personality: dict) -> str:
    """Transform raw event into in-character narrative."""
    # Example: war_started + militarist personality
    # → "At last, the drums of war sound again! The {enemy} have tested
    #    our patience for the final time."
    # vs pacifist personality
    # → "A dark day. Despite our efforts at diplomacy, conflict with
    #    {enemy} has become inevitable."

def generate_recap(session_id: str, style: str = "narrative") -> str:
    """Generate Stellaris Invicta-style 'Previously on...' summary."""

def get_empire_story_arc(session_id: str) -> list[dict]:
    """Extract major plot points from event history."""
```

**Integration with Rust Parser:**
The Rust parser (see `RUST_PARSER_ARCHITECTURE.md`) extracts raw game state. Chronicle layer transforms that data into narrative after Python extraction logic processes it.

```
.sav file → Rust Parser → Python Extractors → Event Detection → Chronicle Narration
```

---

### 2. Era Naming System

Automatically detect and name significant periods in your empire's history.

| Trigger Event | Example Era Name |
|---------------|-----------------|
| Game start | "The Founding" |
| First contact | "The Awakening" |
| First war | "The Trial by Fire" |
| Major expansion (+5 colonies) | "The Great Expansion" |
| Crisis spawn | "The Long Night" |
| Federation formed | "The Age of Unity" |
| Victory condition met | "The Ascension" |

**Database Addition:**
```sql
eras (
    id INTEGER PRIMARY KEY,
    session_id TEXT,
    name TEXT,              -- "The Long Night"
    start_date TEXT,        -- "2350.1.1"
    end_date TEXT,          -- NULL if current
    trigger_event_id INT,   -- FK to events
    description TEXT        -- AI-generated summary
)
```

**Usage in Responses:**
- "Since the Long Night began, our fleet power has increased by 40%..."
- "The Age of Unity saw unprecedented cooperation with our allies..."

---

### 3. Response Modes

Add a mode toggle that affects how the advisor frames responses.

```python
class ResponseMode(Enum):
    ADVISOR = "advisor"      # Current behavior - factual, strategic
    CHRONICLE = "chronicle"  # Narrative framing, references history
    IMMERSIVE = "immersive"  # Full roleplay, never breaks character
```

**Example - Same Question, Different Modes:**

Question: "How is our military?"

**Advisor Mode:**
> Military power: 45,000. 3 fleets with 87 ships. Fleet power adequate for current threats. Recommend building more alloy production.

**Chronicle Mode:**
> The Grand Fleet stands at 45,000 power—a far cry from the desperate days of 2240 when we faced the Kel-Azaan with barely 8,000. Admiral Chen's reorganization has forged our 87 vessels into three battle-ready strike groups. Since the Treaty of Procyon, we have enjoyed relative peace, though the frontier remains restless.

**Immersive Mode:**
> *adjusts tactical display* Your Majesty, the Fleet stands ready. Forty-five thousand souls await your command across three battle groups. The spirits of those lost at Proxima watch over us still. *pauses* I confess some concern about our alloy reserves, but that is a matter for the industrial council.

---

### 4. Persistent Entity Memory

Track and personalize references to named entities across the campaign.

**Database Addition:**
```sql
named_entities (
    id INTEGER PRIMARY KEY,
    session_id TEXT,
    entity_type TEXT,       -- "leader", "fleet", "planet", "empire"
    game_id TEXT,           -- In-game ID
    custom_name TEXT,       -- Player-assigned name (optional)
    narrative_notes TEXT,   -- "Survived 3 battles", "Founded in 2225"
    first_seen_date TEXT,
    last_seen_date TEXT
)
```

**Entity Enrichment:**
- **Leaders:** "Admiral Chen, hero of the Proxima Campaign" not just "an admiral"
- **Fleets:** Track fleet history, victories, losses
- **Planets:** "The fortress world of New Terra, founded in 2225"
- **Rival Empires:** Build ongoing narrative around specific AI empires

---

### 5. Reactive Personality Evolution

Make personality shift based on empire history, not just ethics/civics.

| Event Pattern | Personality Shift |
|---------------|------------------|
| Won 3+ wars | More confident, references past glories |
| Lost a war | Somber, references "lessons learned" |
| Crisis active | Existential urgency, unity language |
| Massive expansion | Imperial pride, manifest destiny |
| Long peace (50+ years) | Philosophical, questions purpose |
| Major leader death | Mourning period, legacy references |

**Implementation:**
```python
def compute_personality_modifiers(session_id: str) -> dict:
    """Analyze event history to derive personality shifts."""
    events = db.get_events_for_session(session_id)

    modifiers = {}
    wars_won = count_events(events, "war_ended", outcome="victory")
    if wars_won >= 3:
        modifiers["confidence"] = "high"
        modifiers["historical_references"] = True

    return modifiers
```

---

## Platform Integration

### Electron App

#### Enhanced RecapPage → ChroniclePage

Transform existing RecapPage into a narrative Chronicle view:

```tsx
// renderer/pages/ChroniclePage.tsx
<ChronicleView>
  <EraHeader>
    <EraName>The Long Night</EraName>
    <DateRange>2280.1.1 - Present</DateRange>
    <EraDescription>The Prethoryn have arrived...</EraDescription>
  </EraHeader>

  <Timeline>
    {events.map(e => (
      <NarrativeEvent
        date={e.game_date}
        narrative={e.narrated_text}
        icon={getEventIcon(e.event_type)}
      />
    ))}
  </Timeline>

  <RecapButton onClick={generateRecap}>
    Generate "Previously On..." Recap
  </RecapButton>
</ChronicleView>
```

#### New Tab Structure

```tsx
// App.tsx
<TabNavigation>
  <Tab icon={Chat}>Advisor</Tab>
  <Tab icon={Book}>Chronicle</Tab>    {/* New */}
  <Tab icon={BarChart}>Dashboard</Tab> {/* New - metrics visualization */}
  <Tab icon={Settings}>Settings</Tab>
</TabNavigation>
```

#### Settings Additions

```tsx
// SettingsPage.tsx additions
<SettingsSection title="Response Style">
  <RadioGroup value={responseMode} onChange={setResponseMode}>
    <Radio value="advisor">
      Strategic Advisor
      <Description>Factual, efficient, data-focused</Description>
    </Radio>
    <Radio value="chronicle">
      Chronicle Mode
      <Description>Narrative framing, references history</Description>
    </Radio>
    <Radio value="immersive">
      Full Roleplay
      <Description>Completely in-character, never breaks immersion</Description>
    </Radio>
  </RadioGroup>
</SettingsSection>

<SettingsSection title="Era Naming">
  <Toggle
    label="Auto-name eras"
    description="AI generates names for significant periods"
  />
</SettingsSection>
```

#### New API Endpoints

```python
# backend/api/server.py additions

@app.get("/api/chronicle/recap")
async def get_recap(style: str = "narrative", limit: int = 10):
    """Generate narrative recap of recent events."""

@app.get("/api/chronicle/era")
async def get_current_era():
    """Get current era name and description."""

@app.get("/api/chronicle/timeline")
async def get_timeline(limit: int = 50):
    """Get narrative-enriched event timeline."""

@app.post("/api/chronicle/name-entity")
async def name_entity(entity_type: str, game_id: str, name: str):
    """Assign custom name to fleet/leader/planet."""

@app.put("/api/settings/response-mode")
async def set_response_mode(mode: str):
    """Set response mode (advisor/chronicle/immersive)."""
```

---

### Discord Bot

#### New Commands

| Command | Description |
|---------|-------------|
| `/recap [style]` | Generate "Previously on..." summary |
| `/era` | Show current era name and theme |
| `/chronicle [limit]` | Narrative version of `/history` |
| `/name <type> <id> <name>` | Name a fleet/leader/planet |
| `/mode <advisor\|chronicle\|immersive>` | Set response style |

#### Enhanced Existing Commands

**`/briefing`** gains style parameter:
```
/briefing style:narrative
```

**`/ask`** respects mode setting:
```python
# commands/ask.py modification
@bot.tree.command(name="ask")
@app_commands.describe(
    question="Your question about the empire",
    style="Response style override (optional)"
)
async def ask(
    interaction: discord.Interaction,
    question: str,
    style: Optional[str] = None
):
    mode = style or get_user_mode(interaction.user.id)
    response = await companion.ask_precomputed(question, mode=mode)
```

#### Command Implementations

```python
# commands/recap.py
@bot.tree.command(name="recap")
@app_commands.describe(style="Recap style: narrative or tactical")
async def recap(interaction: discord.Interaction, style: str = "narrative"):
    """Generate a 'Previously on...' style recap."""
    await interaction.response.defer(thinking=True)

    recap_text = await asyncio.to_thread(
        chronicle.generate_recap,
        session_id=get_session_id(),
        style=style
    )

    # Split for Discord's 2000 char limit
    chunks = split_response(recap_text)
    for chunk in chunks:
        await interaction.followup.send(chunk)
```

```python
# commands/era.py
@bot.tree.command(name="era")
async def era(interaction: discord.Interaction):
    """Show the current era of your empire's history."""
    await interaction.response.defer()

    era_info = await asyncio.to_thread(chronicle.get_current_era)

    embed = discord.Embed(
        title=f"📜 {era_info['name']}",
        description=era_info['description'],
        color=discord.Color.gold()
    )
    embed.add_field(name="Since", value=era_info['start_date'])
    embed.add_field(name="Duration", value=era_info['duration'])

    await interaction.followup.send(embed=embed)
```

---

## Implementation Phases

### Phase 1: Chronicle Backend (Shared)
**Effort:** 2-3 days

- [ ] Create `backend/core/chronicle.py`
- [ ] Create `backend/core/narrator.py` (event → narrative transformation)
- [ ] Add era detection logic to `events.py`
- [ ] Add `eras` table to `database.py`
- [ ] Add `/api/chronicle/*` endpoints
- [ ] Unit tests for narrative generation

### Phase 2: Response Modes
**Effort:** 1-2 days

- [ ] Add `ResponseMode` enum to companion
- [ ] Create mode-specific system prompt suffixes
- [ ] Add mode parameter to `ask_precomputed()`
- [ ] Add mode persistence (per-user for Discord, app-wide for Electron)
- [ ] Update personality.py with mode handling

### Phase 3: Electron Chronicle UI
**Effort:** 2-3 days

- [ ] Rename/enhance RecapPage → ChroniclePage
- [ ] Add narrative event rendering component
- [ ] Add era header component
- [ ] Add mode toggle to Settings
- [ ] Wire up new API endpoints
- [ ] Add timeline visualization

### Phase 4: Discord Commands
**Effort:** 1-2 days

- [ ] Add `/recap` command
- [ ] Add `/era` command
- [ ] Add `/chronicle` command
- [ ] Add `/mode` command
- [ ] Add `style` parameter to `/briefing`
- [ ] Update `/ask` to respect mode

### Phase 5: Entity Memory
**Effort:** 2-3 days

- [ ] Add `named_entities` table
- [ ] Add entity tracking to event processing
- [ ] Add `/name` command (Discord)
- [ ] Add naming UI (Electron)
- [ ] Integrate named entities into narrative generation

### Phase 6: Reactive Personality
**Effort:** 2 days

- [ ] Add `compute_personality_modifiers()` function
- [ ] Integrate history-based modifiers into personality building
- [ ] Add personality shift notifications
- [ ] Test across different empire histories

---

## Example Outputs

### /recap (Narrative Style)

```
═══════════════════════════════════════════════════════════
           PREVIOUSLY ON: THE GREATER TERRAN UNION
═══════════════════════════════════════════════════════════

The year is 2285. What began as a minor border dispute with the
Kel-Azaan Consciousness has escalated into total war.

Admiral Chen's Third Fleet scored a decisive victory at Procyon,
breaking the enemy's forward momentum—but at great cost. The
legendary battleship "Indomitable" was lost with all hands, and
with her, Vice Admiral Reyes, architect of our defensive doctrine.

On the home front, the war economy strains. Alloy production has
increased 40% since the conflict began, but consumer goods shortages
are testing civilian morale. The Council debates rationing measures.

Meanwhile, our scientists report troubling readings from the galactic
rim. Subspace anomalies consistent with extradimensional incursion
have been detected in three sectors. The Shroud whispers of darkness
to come...

The Third Fleet regroups at Arcturus. The enemy masses at the border.
The galaxy holds its breath.

What happens next is up to you.
═══════════════════════════════════════════════════════════
```

### /era

```
📜 THE LONG NIGHT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Since: 2350.1.1 (35 years)

The Prethoryn Scourge arrived from beyond the galactic rim,
consuming three minor civilizations before the galaxy could
respond. The Greater Terran Union leads a desperate coalition
against the swarm.

Key Events This Era:
• Fall of the Kel-Azaan Consciousness (2351)
• Formation of the Galactic Defense Pact (2352)
• Battle of the Shroud Gate (2358)
• Death of Fleet Admiral Chen (2360)

Military Power: 45,000 → 125,000 (+178%)
Colonies Lost: 3
Allies Gained: 7
```

---

## Technical Notes

### Token Efficiency

Narrative mode uses more tokens per response. Mitigations:
- Cache era descriptions (regenerate only on era change)
- Cache entity narratives (regenerate on significant events)
- Use Gemini 3 Flash's large context efficiently
- Summarize rather than enumerate for long histories

### Personality Prompt Structure

```
[Base personality from ethics/civics/authority]
[Mode-specific suffix]
[Era context if chronicle/immersive mode]
[Recent significant events if chronicle/immersive mode]
[Named entity references if applicable]
```

### Database Considerations

Chronicle features add modest storage:
- Eras: ~10 per campaign, ~500 bytes each
- Named entities: ~50-100 per campaign, ~200 bytes each
- Narrated events: Optional caching, can be regenerated

---

## Open Questions

1. **Era naming**: Should era names be AI-generated or picked from templates?
2. **Entity naming**: Auto-suggest names or require manual input?
3. **Mode persistence**: Per-channel (Discord) or per-user?
4. **Recap length**: Default word count? User configurable?
5. **Historical depth**: How far back should chronicle mode reference?

---

## References

- Stellaris Invicta (YouTube) - Narrative style inspiration
- `docs/RUST_PARSER_ARCHITECTURE.md` - Data extraction layer
- `backend/core/events.py` - Current event detection (50+ types)
- `backend/core/history.py` - Snapshot recording infrastructure
- `personality.py` - Current personality system
