# Incremental Chronicle System

> Living history book with persistent chapters that build over time.

**Related Documents**:
- [CHRONICLE_IMPLEMENTATION.md](./CHRONICLE_IMPLEMENTATION.md) - Original implementation (blob-based)
- [CHRONICLE_TESTING.md](./CHRONICLE_TESTING.md) - Prompt validation and voice testing
- [STORYTELLING_OPTIONS.md](./STORYTELLING_OPTIONS.md) - Initial design exploration

---

## Overview

This document specifies an evolution of the chronicle system from "regenerate everything" to "incremental chapters" - a living history book where early chapters are permanent and new chapters are added as the game progresses.

### Problem with Current Approach

The current system regenerates the entire chronicle when cache invalidates:

```
Year 2300: Generate full chronicle (Chapters I-III)
Year 2400: Cache stale → Regenerate everything
           - Chapter I gets rewritten with different title/content
           - Chapter II restructured
           - Chapter III replaced
```

Early history keeps changing. There's no persistence.

### Desired Behavior

```
Year 2250: Generate Chapter I (2200-2250) → Store permanently
Year 2300: Keep Chapter I, generate Chapter II (2250-2300) → Store
Year 2350: Keep I & II, generate Chapter III (2300-2350) → Store
Current:   Show I, II, III + "The Current Era" (regenerating)
```

Early chapters never change (unless user explicitly regenerates). New chapters append. The chronicle grows like a real history book.

---

## Key Design Decisions

### 1. Key by `save_id`, NOT `session_id`

**Critical**: Sessions end and restart for the same campaign. A user might have:
- Session 1: 2200-2300 (ended)
- Session 2: 2300-2400 (current)

If chapters key by `session_id`, Session 2 would start with no chapters - breaking the "living history."

**Solution**: Key chapters by `save_id`, which is stable across sessions. The `save_id` is computed from `campaign_id + player_id` (see `backend/core/history.py:compute_save_id`).

### 2. Escape Hatch for Regeneration

"Permanent" means **no automatic regeneration**, not locked forever. Users can:
- Click "Regenerate" on any finalized chapter
- Confirm: "This will permanently replace Chapter II. Continue?"
- Chapter is regenerated with current LLM, replacing old content

### 3. Cap Chapters Per Request

If a user hasn't played in months, we might need to finalize 5+ chapters. This causes timeout issues.

**Solution**: Cap at 2 chapters finalized per request. Return `pending_chapters` count so UI can prompt user to refresh.

### 4. Structured JSON Output

Use Gemini's JSON mode instead of parsing `SUMMARY:` markers from prose. More reliable.

---

## Feature Streamlining

The current codebase has overlapping features:

| Feature | Current State | New State |
|---------|--------------|-----------|
| **Recap (summary)** | Deterministic bullet points | **Keep** - fast, no LLM |
| **Recap (dramatic)** | LLM "Previously on..." | **Keep** - useful for Discord quick flavor |
| **Chronicle** | Full regeneration, blob storage | **Replace** - incremental chapters |

**Note**: Dramatic recap is kept because "Current Era" in chronicle serves a different purpose (part of full history view vs. standalone quick summary).

---

## Chapter Lifecycle

### States

```
┌─────────────┐      ┌─────────────┐
│   BUILDING  │ ───► │  FINALIZED  │
│  (current)  │      │ (permanent) │
└─────────────┘      └─────────────┘
     │                      │
     │ Era ends             │ Stored in DB
     │ (time/event)         │ (user can regenerate)
     ▼                      ▼
  Generate &             Only changes if
  finalize               user requests
```

### Finalization Triggers

A chapter closes (finalizes) when ANY of these occur:

| Trigger | Condition | Rationale |
|---------|-----------|-----------|
| **Time threshold** | 50+ in-game years since last chapter | Ensures regular chapter breaks |
| **War ends** | Major war concludes | Natural narrative boundary |
| **Crisis defeated** | Prethoryn/Contingency/Unbidden defeated | Major era ending |
| **Awakening** | Fallen empire awakens | Galaxy-changing event |
| **War in Heaven starts** | Ancient empires clash | Defines an era |
| **Federation change** | Joined or left federation | Major diplomatic shift |
| **Session end** | User explicitly ends session | Clean break point |

**Note on event types**: These match actual event types in `backend/core/events.py`:
- `war_ended` (not `war_end`)
- `crisis_defeated` (not `crisis_ended`)
- `fallen_empire_awakened`
- `war_in_heaven_started` (no `_ended` event exists currently)
- `federation_joined`, `federation_left`

### Detection Logic

```python
def should_finalize_chapter(
    save_id: str,
    last_chapter_end_date: str,
    last_chapter_end_snapshot_id: int,
    current_date: str,
    current_snapshot_id: int,
) -> tuple[bool, str | None]:
    """Check if current era should become a finalized chapter.

    Returns (should_finalize, trigger_reason).
    """
    # Time threshold: 50+ years
    years_elapsed = parse_year(current_date) - parse_year(last_chapter_end_date)
    if years_elapsed >= 50:
        return True, "time_threshold"

    # Check for era-ending events since last chapter
    events = db.get_events_in_range(
        save_id=save_id,
        from_snapshot_id=last_chapter_end_snapshot_id,
        to_snapshot_id=current_snapshot_id,
    )

    era_ending_types = {
        'war_ended',
        'crisis_defeated',
        'fallen_empire_awakened',
        'war_in_heaven_started',
        'federation_joined',
        'federation_left',
    }

    for event in events:
        if event['event_type'] in era_ending_types:
            # Only finalize if event is at least 5 years ago
            # (avoid finalizing mid-action)
            event_year = parse_year(event['game_date'])
            current_year = parse_year(current_date)
            if current_year - event_year >= 5:
                return True, event['event_type']

    return False, None
```

---

## Implementation Strategy

### Phase 1: Use Existing `chapters_json` Column (Simpler)

The `cached_chronicles` table already has an unused `chapters_json` column. Start here:

```python
# cached_chronicles.chapters_json structure
{
    "format_version": 1,
    "chapters": [
        {
            "number": 1,
            "title": "The Founding Era",
            "start_date": "2200.01.01",
            "end_date": "2248.06.15",
            "start_snapshot_id": 1,
            "end_snapshot_id": 45,
            "narrative": "In the early twilight...",
            "summary": "The UNE expanded to 5 colonies and made first contact.",
            "generated_at": "2026-01-24T10:30:00Z",
            "is_finalized": true,
            "context_stale": false  // True if earlier chapter was regenerated
        },
        {
            "number": 2,
            ...
        }
    ],
    "current_era_start_date": "2301.03.15",
    "current_era_start_snapshot_id": 89
}
```

**Key change**: Also key by `save_id` instead of `session_id`:

```sql
-- Migration 4: Add save_id to cached_chronicles
ALTER TABLE cached_chronicles ADD COLUMN save_id TEXT;
CREATE INDEX idx_cached_chronicles_save ON cached_chronicles(save_id);

-- Note: Keep existing session_id unique constraint - it doesn't hurt anything.
-- SQLite doesn't support DROP CONSTRAINT without table rebuild.
-- The old constraint becomes irrelevant once we query by save_id.
```

### Phase 2: Separate Table (If Needed Later)

If the JSON approach proves limiting, migrate to a proper normalized table:

```sql
CREATE TABLE chronicle_chapters (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    save_id TEXT NOT NULL,          -- Stable across sessions
    chapter_number INTEGER NOT NULL,

    -- Content
    title TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    start_snapshot_id INTEGER,      -- Anchor for reliable slicing
    end_snapshot_id INTEGER,
    narrative_text TEXT NOT NULL,
    summary TEXT NOT NULL,

    -- Metadata
    event_count INTEGER NOT NULL,
    is_finalized BOOLEAN NOT NULL DEFAULT FALSE,
    generated_at TEXT NOT NULL DEFAULT (datetime('now')),
    context_stale BOOLEAN NOT NULL DEFAULT FALSE,  -- True if earlier chapter was regenerated

    -- Constraints
    UNIQUE(save_id, chapter_number)
    -- Note: No FK to sessions table. save_id spans multiple sessions,
    -- so sessions.save_id is not unique. Options for Phase 2:
    -- 1. Rely on application logic (simplest)
    -- 2. Create a dedicated `saves` table keyed by save_id
    -- Decision deferred until Phase 2 is needed.
);

CREATE INDEX idx_chronicle_chapters_save ON chronicle_chapters(save_id);
```

**Migration**: Keep `cached_chronicles` during transition. Don't DROP TABLE until Phase 2 is proven.

---

## Generation Flow

### Full Chronicle Request

```
User requests chronicle for save_id
         │
         ▼
┌─────────────────────────────────────────┐
│ 1. Load chapters_json from              │
│    cached_chronicles WHERE save_id = ?  │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│ 2. Check: Should current era finalize?  │
│    - 50+ years since last chapter?      │
│    - Era-ending event occurred?         │
└─────────────────────────────────────────┘
         │
    ┌────┴────┐
    │ YES     │ NO
    ▼         ▼
┌─────────────────┐  ┌────────────────────────────┐
│ Finalize chapter│  │ 3. Generate "Current Era"  │
│ (max 2 per req) │  │    (not stored, always     │
│                 │  │     regenerates)           │
└─────────────────┘  └────────────────────────────┘
         │                    │
         └────────┬───────────┘
                  ▼
┌─────────────────────────────────────────┐
│ 4. Assemble response:                   │
│    [Finalized Chapters] + [Current Era] │
│    + pending_chapters count if any      │
└─────────────────────────────────────────┘
```

### Chapter Generation with Structured Output

```python
def generate_chapter(
    save_id: str,
    chapter_number: int,
    previous_chapters: list[dict],
    events: list[dict],
    briefing: dict,
) -> dict:
    """Generate a single chapter using Gemini structured output."""

    empire_name = briefing.get('identity', {}).get('empire_name', 'Unknown')
    voice = get_voice_for_ethics(briefing)

    # Build context from previous chapters
    context_lines = []
    for ch in previous_chapters:
        context_lines.append(
            f"- Chapter {ch['number']} \"{ch['title']}\" "
            f"({ch['start_date']} - {ch['end_date']}): {ch['summary']}"
        )
    previous_context = "\n".join(context_lines) if context_lines else "This is the first chapter."

    events_text = format_events(events)

    prompt = f"""You are the Royal Chronicler of {empire_name}.

=== CHRONICLER'S VOICE ===
{voice}

=== PREVIOUS CHAPTERS ===
{previous_context}

=== EVENTS FOR THIS CHAPTER ===
{events_text}

=== YOUR TASK ===

Write Chapter {chapter_number} of the empire's chronicle.

Requirements:
- Title: A dramatic, thematic name for this era
- Narrative: 3-5 paragraphs of dramatic prose (500-800 words)
- Summary: 2-3 sentences summarizing key events for future chapter context
- Continuity: Reference previous chapters where relevant

Do NOT give advice. You are a historian, not an advisor.
Do NOT fabricate events not in the event list.
"""

    # Use Gemini structured output
    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=prompt,
        config={
            "temperature": 1.0,
            "response_mime_type": "application/json",
            "response_schema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "narrative": {"type": "string"},
                    "summary": {"type": "string"}
                },
                "required": ["title", "narrative", "summary"]
            }
        }
    )

    return json.loads(response.text)
```

### Handling Multiple Pending Chapters

```python
MAX_CHAPTERS_PER_REQUEST = 2

def generate_chronicle(save_id: str, force_refresh: bool = False) -> dict:
    """Generate chronicle, capping chapter finalization."""

    chapters_data = load_chapters_json(save_id)
    finalized = [c for c in chapters_data.get("chapters", []) if c["is_finalized"]]

    # Count how many chapters need finalization
    pending = count_pending_chapter_boundaries(save_id, chapters_data)

    chapters_finalized_this_request = 0
    while should_finalize_next_chapter(save_id, chapters_data):
        if chapters_finalized_this_request >= MAX_CHAPTERS_PER_REQUEST:
            break
        finalize_next_chapter(save_id, chapters_data)
        chapters_finalized_this_request += 1

    # Generate current era (always fresh)
    current_era = generate_current_era(save_id, chapters_data)

    remaining_pending = pending - chapters_finalized_this_request

    return {
        "chapters": chapters_data["chapters"],
        "current_era": current_era,
        "pending_chapters": max(0, remaining_pending),
        "message": f"{remaining_pending} more chapters pending. Refresh to continue." if remaining_pending > 0 else None
    }
```

---

## API Changes

### Updated `/api/chronicle` Response

```python
class ChronicleResponse(BaseModel):
    chapters: list[ChapterInfo]
    current_era: CurrentEraInfo | None
    pending_chapters: int  # How many more chapters could be finalized
    message: str | None    # "2 more chapters pending. Refresh to continue."

class ChapterInfo(BaseModel):
    number: int
    title: str
    start_date: str
    end_date: str
    narrative: str
    summary: str
    is_finalized: bool
    can_regenerate: bool   # True for finalized chapters
    context_stale: bool    # True if earlier chapter was regenerated

class CurrentEraInfo(BaseModel):
    start_date: str
    narrative: str
    events_covered: int
```

### Backward Compatibility

For existing consumers expecting `{chronicle: string, ...}`:

```python
@app.post("/api/chronicle")
def generate_chronicle_endpoint(...):
    result = generator.generate_chronicle(...)

    # Assemble full text for backward compatibility
    full_text = assemble_chronicle_text(result["chapters"], result["current_era"])

    return {
        # New structured format
        "chapters": result["chapters"],
        "current_era": result["current_era"],
        "pending_chapters": result["pending_chapters"],

        # Backward compatible
        "chronicle": full_text,
        "cached": any(c["is_finalized"] for c in result["chapters"]),
        "event_count": sum(c.get("event_count", 0) for c in result["chapters"]),
    }
```

### Chapter Regeneration Endpoint

```python
@app.post("/api/chronicle/regenerate-chapter")
def regenerate_chapter(
    save_id: str,
    chapter_number: int,
    confirm: bool = False  # Must be true to proceed
) -> dict:
    """Regenerate a specific finalized chapter."""

    if not confirm:
        return {"error": "Must confirm regeneration", "confirm_required": True}

    # Regenerate the chapter
    new_chapter = generator.regenerate_chapter(save_id, chapter_number)

    return {"chapter": new_chapter, "regenerated": True}
```

### Recap Endpoint (Unchanged)

Keep `/api/recap` with both styles:
- `style="summary"` - Fast deterministic bullet points
- `style="dramatic"` - LLM "Previously on..." narrative

The dramatic recap remains useful for Discord quick-flavor, separate from the full chronicle view.

---

## User Experience

### Chronicle View

```
╔══════════════════════════════════════════════════════════════╗
║  THE CHRONICLES OF THE UNITED NATIONS OF EARTH               ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  CHAPTER I: THE CRADLE'S AWAKENING                    🔒 ↻  ║
║  2200 - 2248                                                 ║
║                                                              ║
║  In the early twilight of the twenty-third century, the     ║
║  United Nations of Earth stood upon the precipice of a      ║
║  vast, silent ocean...                                       ║
║                                                              ║
╠──────────────────────────────────────────────────────────────╣
║                                                              ║
║  CHAPTER II: THE GREAT HANDSHAKE                      🔒 ↻  ║
║  2248 - 2301                                                 ║
║                                                              ║
║  The galaxy, once thought empty, proved to be a crowded     ║
║  stage...                                                    ║
║                                                              ║
╠──────────────────────────────────────────────────────────────╣
║                                                              ║
║  THE CURRENT ERA                                       ⏳    ║
║  2301 - Present                                              ║
║                                                              ║
║  As the fourth century dawns, the Republic faces its        ║
║  greatest test...                                            ║
║                                                              ║
║  The story continues...                                      ║
║                                                              ║
╠──────────────────────────────────────────────────────────────╣
║  ⚠️ 2 more chapters pending. Refresh to continue.            ║
╚══════════════════════════════════════════════════════════════╝

🔒 = Finalized    ↻ = Click to regenerate    ⏳ = Current (auto-refreshes)    ⚠️ = Context may be stale
```

### Regeneration Confirmation

```
╔══════════════════════════════════════════════════════════════╗
║  Regenerate Chapter II?                                      ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  This will permanently replace "The Great Handshake"         ║
║  (2248 - 2301) with a newly generated chapter.              ║
║                                                              ║
║  The new chapter will use the same events but may have      ║
║  different prose, title, and narrative structure.           ║
║                                                              ║
║  This cannot be undone.                                      ║
║                                                              ║
║              [ Cancel ]        [ Regenerate ]                ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
```

---

## Implementation Plan

### Phase 1: Database Updates

| Task | Effort |
|------|--------|
| Add `save_id` column to `cached_chronicles` | Low |
| Create index on `save_id` | Low |
| Update `chapters_json` schema | Low |
| Add migration (schema version 4) | Low |

### Phase 2: Core Logic

| Task | Effort |
|------|--------|
| `save_id` lookup from session context | Low |
| Era-boundary detection with correct event types | Medium |
| Chapter finalization with cap (max 2) | Medium |
| Structured JSON output from Gemini | Low |
| Current era generation | Low |
| Chapter assembly with pending count | Low |

### Phase 3: API Updates

| Task | Effort |
|------|--------|
| Update `/api/chronicle` response format | Low |
| Add backward-compatible `chronicle` string field | Low |
| Add `/api/chronicle/regenerate-chapter` endpoint | Low |
| Update IPC handlers | Low |

### Phase 4: Electron UI

| Task | Effort |
|------|--------|
| ChronicleViewer component with chapters | Medium |
| Regenerate button per chapter | Low |
| Pending chapters notification | Low |
| Confirmation dialog for regeneration | Low |

---

## Edge Cases

### First Chronicle Request (No Chapters Yet)

- Check if enough time/events for Chapter I
- If yes: Generate and finalize Chapter I, then generate current era
- If no: Just generate current era (no finalized chapters yet)

### Very Short Sessions

- Session with only 10 years of play → No finalized chapters, just current era
- That's fine - chronicles grow with the game

### Session Resumed After Long Break

- User plays 2200-2250, stops for months
- Resumes, plays to 2450
- On next chronicle request: Finalize up to 2 chapters, note "2 more pending"
- User refreshes → 2 more finalized
- Prevents timeout from 4+ LLM calls in one request

### Cross-Session Continuity

- Session 1 (ended): Chapters I, II finalized
- Session 2 (current): Same `save_id`, sees Chapters I, II + current era
- Living history preserved across sessions

### Regeneration of Middle Chapter

- User regenerates Chapter II (of I, II, III)
- Chapter II is regenerated with events from that era
- Chapters I and III unchanged
- Chapter III's prompt included old Chapter II summary - continuity may be slightly off

**Defined Behavior**:

When regenerating Chapter N:
1. Regenerate Chapter N with fresh LLM call using current events
2. Mark chapters N+1, N+2, ... as `context_stale: true`
3. On next chronicle view, show indicator on stale chapters: "⚠️ May reference outdated context"
4. User can choose to regenerate downstream chapters or leave them

This avoids cascading LLM calls (which could timeout) while being transparent about potential continuity drift. Summaries are short (2-3 sentences) so drift is usually minor.

```python
def regenerate_chapter(save_id: str, chapter_number: int) -> dict:
    """Regenerate a finalized chapter and mark downstream as stale."""
    chapters_data = load_chapters_json(save_id)

    # Regenerate the requested chapter
    new_chapter = generate_chapter_content(save_id, chapter_number, ...)
    chapters_data["chapters"][chapter_number - 1] = new_chapter

    # Mark all later chapters as context_stale
    for i in range(chapter_number, len(chapters_data["chapters"])):
        chapters_data["chapters"][i]["context_stale"] = True

    save_chapters_json(save_id, chapters_data)
    return new_chapter
```

---

## Cost Analysis

| Scenario | LLM Calls | Tokens |
|----------|-----------|--------|
| First chronicle (no chapters) | 1 (current era) | ~1,500 |
| Chronicle with 3 finalized chapters | 0 (cached) + 1 (current era) | ~1,500 |
| 2 chapters need finalization | 2 (chapters) + 1 (current era) | ~4,500 |
| User regenerates 1 chapter | 1 (chapter) | ~1,500 |

Incremental approach is **more efficient** long-term:
- Finalized chapters never regenerate (unless user requests)
- Only current era regenerates each view
- vs. current approach: entire chronicle regenerates when stale

---

## Summary of Changes from Original Spec

| Original | Updated |
|----------|---------|
| Key by `session_id` | Key by `save_id` (stable across sessions) |
| Event type `crisis_ended` | `crisis_defeated` (matches actual code) |
| Event type `war_in_heaven_ended` | Removed (doesn't exist) |
| Chapters permanent forever | Escape hatch: user can regenerate |
| Unlimited chapters per request | Cap at 2, return `pending_chapters` |
| Parse `SUMMARY:` from prose | Use Gemini JSON structured output |
| New `chronicle_chapters` table | Start with `chapters_json` column |
| Drop `cached_chronicles` | Keep during migration |
| Remove dramatic recap | Keep it (useful for Discord) |
| No snapshot anchoring | Add `start_snapshot_id`, `end_snapshot_id` |
| Drop session_id constraint | Keep it (SQLite rebuild not worth it) |
| FK to sessions.save_id | No FK (save_id not unique in sessions) |
| Undefined middle chapter regen | Mark downstream as `context_stale` |
