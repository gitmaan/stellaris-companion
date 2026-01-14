# Stellaris LLM Companion - Development Findings

> **Related:** [Full Design Document](../stellaris-llm-companion-design.md)

## Summary

**Last Updated:** 2026-01-12
**Current Version:** V2 (Lean + Tools with Native Gemini SDK + Dynamic Personality)
**Model:** `gemini-3-flash-preview` with automatic function calling
**Status:** ✅ Fully working with dynamic personality

### Quick Start
```bash
cd ~/stellaris-companion && source venv/bin/activate
export GOOGLE_API_KEY="your-key"
python v2_native_tools.py "/path/to/save.sav"
```

### CLI Commands
| Command | Description |
|---------|-------------|
| `/quit` | Exit the companion |
| `/clear` | Clear conversation history |
| `/reload` | Reload save file (for updated saves) |
| `/personality` | Show current personality config |
| `/prompt` | Display full system prompt |

---

## V1 Test Results

**Date:** 2025-01-12
**Test:** V1 proof-of-concept - Can we access Stellaris saves and chat with an LLM about them?
**Result:** ✅ SUCCESS

---

## What We Tested

| Test | Result | Notes |
|------|--------|-------|
| Access save from Steam Cloud | ✅ | Manual download from web portal works |
| Extract gamestate from .sav | ✅ | Standard ZIP extraction |
| Parse Clausewitz format | ✅ | LLM reads it natively - no parser needed for V1 |
| Chat about game state | ✅ | Meaningful analysis of empire, fleets, species |
| Search full gamestate | ✅ | Can find specific data in 70MB file |
| **Gemini 3 Flash** | ✅ | Switched from Claude - 85% cost reduction |

---

## LLM Choice: Gemini 3 Flash

Initially tested with Claude Sonnet, then switched to Gemini 3 Flash for cost efficiency.

### Comparison

| Aspect | Claude Sonnet | Gemini 3 Flash |
|--------|---------------|----------------|
| Input price | $3 / 1M tokens | $0.50 / 1M tokens |
| Output price | $15 / 1M tokens | $3 / 1M tokens |
| Context window | 200k tokens | 1M tokens |
| **Cost reduction** | - | **~85%** |

### Why Gemini 3 Flash

1. **5x larger context** - Can send more save data (critical for our use case)
2. **6x cheaper input** - Large save files = lots of input tokens
3. **5x cheaper output** - Ongoing conversations add up
4. **Function calling support** - Needed for tool-based deep dives
5. **Quality sufficient** - Tested and provides good strategic analysis

### Model Configuration

```python
from google import genai
from google.genai import types

client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

response = client.models.generate_content(
    model="gemini-3-flash-preview",
    contents=conversation_history,
    config=types.GenerateContentConfig(
        system_instruction=system_prompt,
        max_output_tokens=4096,
    )
)
```

---

## Save File Structure

Stellaris `.sav` files are **ZIP archives** containing:

```
save.sav (ZIP)
├── gamestate    # Main game state (Clausewitz format, 10-70MB text)
└── meta         # Metadata (small, ~1KB)
```

### Clausewitz Format

The gamestate is plain text in Paradox's Clausewitz format:

```
version="Corvus v4.2.4"
name="United Nations of Earth 2"
date="2395.02.06"
player={
    {
        name="unknown"
        country=0
    }
}
species_db={
    3036676097={
        name_list="HUMAN1"
        class="HUM"
        portrait="human"
        traits={
            trait="trait_adaptive"
            trait="trait_nomadic"
            trait="trait_wasteful"
        }
    }
}
```

**Key insight:** Claude can read this format directly without parsing. For V1, we don't need a Clausewitz parser.

### File Sizes

| Save Type | Gamestate Size | Notes |
|-----------|----------------|-------|
| Early game | ~5-10 MB | Few empires, small galaxy |
| Mid game | ~20-40 MB | More entities |
| Late game (2395) | **69.7 MB** | Our test save |

The 70MB file is too large for Claude's context window (~80k chars ≈ 80KB). We send a truncated version and use `/search` for specific queries.

---

## Steam Cloud Access

### The Challenge

User plays on **GeForce Now** - no local game installation. Saves exist only in Steam Cloud.

### What We Discovered

1. **Steam Cloud syncs to local Steam client** - Even without Stellaris installed locally, Steam can sync cloud saves to:
   ```
   ~/Library/Application Support/Steam/userdata/<user_id>/281990/remote/save games/
   ```

2. **But it requires "awareness"** - Steam only syncs games you've interacted with locally. For GFN-only players, the Stellaris folder doesn't exist.

3. **Manual download works** - https://store.steampowered.com/account/remotestorage provides direct access to cloud saves.

### Path Forward

| Approach | Complexity | Best For |
|----------|------------|----------|
| Manual download | Low | Quick testing |
| Force Steam sync | Low | Players with Steam installed |
| steamcmd automation | Medium | Automated polling |
| Steam Web API | High | Full automation |

For now, manual download is sufficient. Automatic sync is a future enhancement.

---

## Test Results

### Empire Analyzed

| Field | Value |
|-------|-------|
| Empire | United Nations of Earth 2 |
| Date | 2395.02.06 (195 years in) |
| Version | Corvus v4.2.4 |
| Planets | 22 |
| Fleet Units | 470 |
| Species Encountered | 80+ |

### DLC Detected

- Federations
- Galactic Paragons
- Horizon Signal
- Megacorp
- Overlord
- Utopia

### Data Claude Could Extract

From the truncated gamestate (first 80k chars):
- Empire name, date, version
- Player species traits (Adaptive, Nomadic, Wasteful)
- Species database (80+ species)
- Basic structure of the save

From `/search` queries:
- Fleet compositions (Strike Force Manticore, 3rd Fleet, 15th Fleet)
- Ship counts by type (destroyers, corvettes, frigates, cruisers, battleships)
- Combat records
- Flag and empire colors

### Example Conversation

```
You: What's the state of my empire? Give me a brief overview.

Advisor: Based on the save file data, here's an overview of your
United Nations of Earth empire as of 2395.02.06:

## Empire Status
- Year: 2395 (195+ years into the game - quite advanced!)
- Player: United Nations of Earth 2
- Species: Humans with Adaptive, Nomadic, and Wasteful traits

## Territory & Infrastructure
- Planets: 22 controlled planets (fairly substantial empire)
- Fleets: 470 fleet units (significant naval presence)

## Galactic Situation
You're in a very diverse galaxy with 80+ different species...
```

---

## Architecture Validated

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Steam Cloud    │────▶│   .sav file     │────▶│    Claude       │
│  (manual DL)    │     │   (ZIP→text)    │     │   (analysis)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

This simple pipeline works. The complexity of parsing, intel filtering, and character personality can be layered on top.

---

## Key Learnings

### What Worked Well

1. **Claude reads Clausewitz natively** - No parser needed for basic functionality
2. **Search is powerful** - Can find specific data in huge files
3. **Late-game saves work** - Even 70MB files are usable with truncation + search
4. **Meaningful conversations** - Claude provides useful strategic analysis

### Limitations Discovered

1. **Context window** - Can't send full gamestate, must truncate
2. **No structure** - Raw search is powerful but unstructured
3. **No persistence** - Each conversation starts fresh
4. **Manual sync** - Steam Cloud doesn't auto-sync for GFN-only users

### Future Improvements

| Priority | Improvement | Benefit |
|----------|-------------|---------|
| High | Smarter context selection | Send relevant sections, not just first 80k |
| High | Automatic file watching | Detect new saves |
| Medium | Clausewitz parser | Structured queries instead of text search |
| Medium | Memory/persistence | Remember previous conversations |
| Low | Intel filtering | Fog of war respect |
| Low | Character personality | Advisor feels like a person |

---

## Files Created

```
stellaris-companion/
├── v2_native_tools.py  # ✅ Current - Native Gemini SDK with dynamic personality
├── v2_adk_tools.py     # Alternative - Google ADK version
├── save_extractor.py   # Shared save file parser with identity extraction
├── personality.py      # Dynamic personality builder from empire data
├── v1_test.py          # Legacy - Claude with full context
├── requirements.txt    # Python dependencies (google-genai, python-dotenv)
├── .env                # API key storage (gitignored)
├── .gitignore          # Protects .env and other sensitive files
├── README.md           # Usage instructions
├── FINDINGS.md         # This document
└── venv/               # Python virtual environment
```

---

## Context Management Strategy

### The Problem

| Metric | Value |
|--------|-------|
| Large save file | 69.7M characters |
| Gemini 3 Flash context | 1M tokens (~3-4M chars) |
| **Max coverage** | **~5% of file** |

Even with 1M tokens, we can only fit ~5% of a large late-game save. We need to be strategic.

### Save File Structure

Clausewitz format has predictable sections with varying sizes:

```
gamestate (69.7M chars)
├── Header (version, date, player)           ~1 KB
├── species_db={...}                         ~500 KB - 2 MB
├── country={                                ~30-50 MB (BIGGEST)
│   ├── 0={...}    # Player empire
│   ├── 1={...}    # AI empire
│   └── ...        # 20-50 empires
├── galactic_object={...}                    ~10-20 MB (star systems)
├── planets={...}                            ~5-15 MB
├── fleets={...}                             ~1-10 MB
├── wars={...}                               ~100 KB - 5 MB
└── leaders={...}                            ~500 KB - 2 MB
```

**Key insight:** The `country={}` section is ~50% of the file. Most is AI empires the player doesn't need.

### Options Evaluated

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| **Truncation** | Simple | Misses relevant data | ❌ Testing only |
| **Smart Extraction** | Gets relevant data | Needs parser | ✅ Good |
| **Tool Use (Function Calling)** | Flexible, deep dives | Multi-turn latency | ✅ Good for detail |
| **Pre-processing Pipeline** | Clean summary | Loses nuance | ⚠️ Maybe later |
| **RAG** | Scalable | Overkill for single file | ❌ Not needed |
| **Hybrid** | Best of both worlds | Medium complexity | ✅ **Recommended** |

### Chosen Approach: Hierarchical Hybrid

```
┌─────────────────────────────────────────────────────────────────┐
│                    CONTEXT ARCHITECTURE                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  LAYER 0: Always in Context (~300-500k chars)                   │
│  ─────────────────────────────────────────────                  │
│  • Full player empire data                                       │
│  • Summary of known empires (name, relation, power estimate)    │
│  • Active wars (full detail)                                     │
│  • Player's fleets (compositions)                                │
│  • Economy snapshot (resources, income)                          │
│  • Recent events/notifications                                   │
│                                                                  │
│  LAYER 1: Available via Tools                                    │
│  ─────────────────────────────────────────────                  │
│  • Full data for any empire (get_empire tool)                   │
│  • Star system details (get_system tool)                        │
│  • Historical data (search tool)                                 │
│  • Full fleet breakdowns (get_fleet tool)                       │
│                                                                  │
│  LAYER 2: Raw File (Local)                                       │
│  ─────────────────────────────────────────────                  │
│  • Full 70MB file stored locally                                 │
│  • Tools query this as needed                                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Why This Works

1. **Common questions answered instantly** - Layer 0 has what's needed 90% of the time
2. **Deep dives possible** - Layer 1 tools for specific queries
3. **Nothing is lost** - Layer 2 raw file available
4. **Fits in context window** - 300-500k chars leaves room for conversation
5. **Fog of war ready** - Only extract data player has intel on

### Implementation Components

#### 1. Section Extractor

```python
class SaveExtractor:
    """Extract sections from Clausewitz format."""

    def __init__(self, gamestate: str):
        self.raw = gamestate

    def get_player_empire(self) -> str:
        """Extract country 0 (player)."""

    def get_known_empires(self) -> list:
        """Extract empires the player has intel on."""

    def get_active_wars(self) -> str:
        """Extract wars involving player."""

    def get_player_fleets(self) -> str:
        """Extract player's fleet data."""

    def get_economy(self) -> str:
        """Extract resource/economy data."""
```

#### 2. Context Builder

```python
class ContextBuilder:
    """Build optimized context for LLM."""

    def build(self, max_chars: int = 500_000) -> str:
        """Build structured context with priority ordering."""
        # Priority: Player Empire > Wars > Fleets > Known Empires > Economy
        # Fill until max_chars reached
```

#### 3. Tool Definitions (Gemini Function Calling)

```python
SAVE_TOOLS = [
    {
        "name": "search_save",
        "description": "Search the full save file for specific text",
        "parameters": {"query": "string"}
    },
    {
        "name": "get_empire_details",
        "description": "Get complete data for a specific empire",
        "parameters": {"empire": "string"}
    },
    {
        "name": "get_fleet_details",
        "description": "Get detailed fleet composition",
        "parameters": {"fleet": "string"}
    },
    {
        "name": "get_system_details",
        "description": "Get star system information",
        "parameters": {"system": "string"}
    }
]
```

### Expected Context Breakdown

| Section | Estimated Size | Priority |
|---------|----------------|----------|
| Player Empire (country 0) | 500KB - 2MB | 1 (Critical) |
| Active Wars | 50KB - 500KB | 2 (High) |
| Player Fleets | 100KB - 500KB | 3 (High) |
| Known Empire Summaries | 50KB - 200KB | 4 (Medium) |
| Economy/Resources | 10KB - 50KB | 5 (Medium) |
| **Total Layer 0** | **~300-500KB** | - |

This leaves ~500KB for conversation history and responses.

### Implementation Phases

| Phase | Component | Effort |
|-------|-----------|--------|
| 1 | Section extractor (regex-based) | 2-3 hours |
| 2 | Context builder with priorities | 1-2 hours |
| 3 | Gemini tool/function calling | 2-3 hours |
| 4 | Intel filtering (fog of war) | 3-4 hours |

---

## File Size Clarification

```
Downloaded .sav file:     6.0 MB  (compressed ZIP)
Extracted gamestate:     69.7 MB  (uncompressed text)
Compression ratio:       ~11:1
```

The save file is a **ZIP archive**. When loaded, it decompresses to ~70MB of text. This is what would be sent to the LLM with the rich context approach - but with lean + tools, we only send small chunks on demand.

---

## Caching Analysis

### Gemini 3 Flash Caching

| Feature | Details |
|---------|---------|
| **Automatic caching** | Yes, built-in |
| **Cost reduction** | Up to 90% for cached tokens |
| **Minimum to cache** | 2,048 tokens |
| **Default TTL** | 1 hour (configurable) |

### Impact on Architecture Choice

Save files change with every autosave, breaking cache for save data:

| Approach | What Gets Cached | Cache Benefit |
|----------|------------------|---------------|
| **Rich Context (500k)** | System prompt (~10k) | ~2% of tokens cached |
| **Lean + Tools** | System prompt + tool defs + conversation | ~80%+ cached |

### Cost Comparison Per Question

| Approach | Fresh Tokens | Cost per Question |
|----------|--------------|-------------------|
| Rich Context | ~500k | ~$0.25 |
| Lean + Tools (1 tool) | ~20k | ~$0.01 |
| Lean + Tools (3 tools) | ~50k | ~$0.025 |

**Conclusion:** Lean + Tools is **10-25x cheaper** when caching is considered.

---

## Tool Implementation Options

### Option 1: Native Gemini Function Calling (google-genai SDK)

Direct use of the Gemini API's built-in function calling with automatic execution.

```python
from google import genai
from google.genai import types

# Define tools as Python functions with docstrings
def get_player_status() -> dict:
    """Get the player's current empire status including resources and fleet power."""
    return extractor.get_player_summary()

def get_empire(name: str) -> dict:
    """Get detailed information about a specific empire.

    Args:
        name: The name of the empire to look up
    """
    return extractor.get_empire_by_name(name)

# Pass functions directly - SDK handles schema generation
config = types.GenerateContentConfig(
    tools=[get_player_status, get_empire, search_save],
    system_instruction=system_prompt,
)

# Automatic function calling - SDK executes and loops
response = client.models.generate_content(
    model="gemini-3-flash-preview",
    contents=user_question,
    config=config,
)
print(response.text)  # Final answer after tool execution
```

**Pros:**
- Simple - just define functions with docstrings
- Automatic execution - SDK handles tool loop
- No extra dependencies - already using google-genai
- Full control - can switch to manual mode if needed
- Lightweight - no framework overhead

**Cons:**
- Manual state management for conversation history
- No built-in persistence
- Basic orchestration only

---

### Option 2: Google ADK (Agent Development Kit)

Full agent framework optimized for Gemini.

```python
from google.adk import Agent, FunctionTool

# Define tools with decorators
@FunctionTool
def get_player_status() -> dict:
    """Get the player's current empire status."""
    return extractor.get_player_summary()

# Create agent
agent = Agent(
    model="gemini-3-flash-preview",
    tools=[get_player_status, get_empire, search_save],
    system_instruction=system_prompt,
)

# Run with automatic tool handling
response = agent.run("What's my empire status?")
```

**Pros:**
- Framework patterns - built-in agent loops, retries, error handling
- Interactions API - server-side conversation management
- Multi-agent support - can compose agents as tools
- Google optimized - may have performance benefits
- Future-proof - official Google direction

**Cons:**
- Another dependency (`pip install google-adk`)
- Learning curve - new framework
- Potentially overkill for simple use cases
- Less control - abstraction hides details
- Newer/less stable - v0.2-0.5 releases

---

### Option 3: Manual Function Calling Loop

Full control - handle the tool execution loop ourselves.

```python
def chat_with_tools(question: str, tools: list, save_data: dict):
    messages = [{"role": "user", "content": question}]

    while True:
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=messages,
            config=types.GenerateContentConfig(tools=tools)
        )

        if has_function_call(response):
            result = execute_function(response.function_call, save_data)
            messages.append(function_result_message(result))
        else:
            return response.text
```

**Pros:**
- Maximum control - every step explicit
- Easy debugging - can log/inspect every call
- Custom logic - add caching, rate limiting, etc.

**Cons:**
- More code to write
- Handle edge cases ourselves
- Reinventing what SDK provides

---

### Comparison Matrix

| Factor | Native SDK (Auto) | Google ADK | Manual Loop |
|--------|-------------------|------------|-------------|
| **Setup complexity** | Low | Medium | Low |
| **Code required** | ~50 lines | ~30 lines | ~100 lines |
| **Dependencies** | google-genai | google-genai + adk | google-genai |
| **Control level** | Medium | Low | High |
| **Learning curve** | Low | Medium | Low |
| **Debugging ease** | Medium | Hard | Easy |
| **Production ready** | Yes | Maturing | Yes |
| **Our use case fit** | ✅ Good | ⚠️ Maybe overkill | ✅ Good |

---

### V2 Test Results: Native SDK vs Google ADK

**Test Date:** 2025-01-12
**Save File:** United Nations of Earth 2, Year 2395

#### Test 1: Military Power Query

| Implementation | Response Time | Correct Data | Notes |
|----------------|---------------|--------------|-------|
| **Native SDK** | 3.12s | ✅ 125,866 | Clean execution |
| **Google ADK** | 3.46s | ✅ 125,866 | Experimental streaming warning |

#### Test 2: Active Wars Query

| Implementation | Response Time | Correct Data | Notes |
|----------------|---------------|--------------|-------|
| **Native SDK** | 5.24s | ✅ No wars | Also pulled player stats contextually |
| **Google ADK** | 13.70s | ✅ No wars | 2nd test after rate limit cooldown |

#### Implementation Complexity

| Factor | Native SDK | Google ADK |
|--------|-----------|------------|
| **Lines of code** | 130 | 175 |
| **Async required** | No | Yes |
| **Extra dependencies** | None | `google-adk` |
| **Setup complexity** | Low | Medium |
| **Warnings/quirks** | None | Experimental streaming, non-text parts warning |
| **Boilerplate** | Minimal | Session service, runner, agent objects |

#### Code Clarity Comparison

**Native SDK** - Synchronous, direct:
```python
response = client.models.generate_content(
    model="gemini-3-flash-preview",
    contents=history,
    config=types.GenerateContentConfig(
        tools=[get_player_status, get_empire_details, ...],
    )
)
return response.text
```

**Google ADK** - Async with more setup:
```python
content = types.Content(role="user", parts=[types.Part(text=message)])
response = self.runner.run_async(
    user_id="player",
    session_id=self.session.id,
    new_message=content,
)
async for event in response:
    if hasattr(event, 'content') and event.content:
        # Extract text from parts...
```

#### Verdict

| Criteria | Winner | Reason |
|----------|--------|--------|
| **Response time** | Native SDK | Slightly faster (3.12s vs 3.46s) |
| **Code simplicity** | Native SDK | Sync, fewer lines, no extra objects |
| **Dependencies** | Native SDK | No extra packages |
| **Debugging** | Native SDK | No experimental warnings |
| **Future scalability** | Google ADK | Built-in multi-agent, persistence |
| **Our use case** | **Native SDK** | Simpler, faster, sufficient features |

**Recommendation:** Use **Native SDK** for this project. The ADK framework is powerful but adds complexity we don't need. For a simple tool-calling advisor, the native SDK is cleaner and faster.

**Files created:**
- `v2_native_tools.py` - Native SDK implementation ✅ Working
- `v2_adk_tools.py` - Google ADK implementation ✅ Working
- `save_extractor.py` - Shared save file parser ✅ Working

---

### Final Decision: Native SDK

After testing both implementations and analyzing against the planned architecture, **Native SDK is the chosen approach**.

#### Why Not ADK?

| ADK Feature | Useful for Us? | Reasoning |
|-------------|----------------|-----------|
| Multi-agent orchestration | ❌ No | Design has ONE advisor, not multiple agents |
| Session persistence abstraction | ⚠️ Minor | Our AnalysisQueue/Context Manager are custom anyway |
| Built-in retries | ⚠️ Minor | Easy to add ourselves if needed |
| Async patterns | ❌ No | Adds complexity without benefit |
| Observability/tracing | ⚠️ Minor | CLI debugging sufficient for personal tool |

#### Architecture Alignment

The [design document](../stellaris-llm-companion-design.md) shows:

```
Feature Modules (Historian, War Room, Biographer...)
                    │
                    ▼
            LLM INTERFACE (single)
```

This is **one advisor with multiple modes**, not multiple agents. The "Feature Modules" are different prompts/contexts for the same LLM, not separate agents. ADK's multi-agent capabilities are overkill.

#### What We Build Regardless of SDK

These are OUR components, not SDK concerns:

```python
class AnalysisQueue:       # Pre-generate analysis when saves change
class ContextManager:      # Track chronicle, relationships, deltas
class IntelFilter:         # Fog of war enforcement
class SteamCloudWatcher:   # Poll for new saves
```

The LLM SDK is just the thin layer calling Gemini with tools.

#### Migration Path

If multi-agent is ever needed (unlikely), migration is straightforward - tool functions are identical between Native SDK and ADK.

---

## Updated Architecture: Lean + Tools

```
┌─────────────────────────────────────────────────────────────────┐
│  LEAN + TOOLS ARCHITECTURE                                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Always in Context (CACHED - 90% discount):                     │
│  ├── System prompt with advisor personality    ~5,000 tokens    │
│  ├── Tool definitions                          ~2,000 tokens    │
│  ├── Brief save metadata (name, date)          ~500 tokens      │
│  └── Conversation history                      ~10,000+ tokens  │
│                                                                  │
│  Fetched via Tools (FRESH - full price):                        │
│  ├── get_player_status()  → resources, fleets, planets          │
│  ├── get_empire(name)     → full empire data                    │
│  ├── get_wars()           → active conflicts                    │
│  ├── get_fleets()         → fleet compositions                  │
│  └── search(term)         → raw text search                     │
│                                                                  │
│  Stored Locally:                                                 │
│  └── Full 70MB gamestate (decompressed from 6MB .sav)           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Progress Tracker

### Completed ✅

| Task | Status | Date |
|------|--------|------|
| V1 Proof of Concept | ✅ Done | 2025-01-12 |
| Switch to Gemini 3 Flash | ✅ Done | 2025-01-12 |
| Build save_extractor.py | ✅ Done | 2025-01-12 |
| Implement v2_native_tools.py | ✅ Done | 2025-01-12 |
| Implement v2_adk_tools.py | ✅ Done | 2025-01-12 |
| Compare Native vs ADK | ✅ Done | 2025-01-12 |
| Choose tool approach | ✅ **Native SDK** | 2025-01-12 |
| **Tier 1: Tool Expansion** | ✅ Done | 2025-01-12 |
| ↳ get_leaders() | ✅ Done | 2025-01-12 |
| ↳ get_technology() | ✅ Done | 2025-01-12 |
| ↳ get_resources() | ✅ Done | 2025-01-12 |
| ↳ get_diplomacy() | ✅ Done | 2025-01-12 |
| ↳ get_planets() | ✅ Done | 2025-01-12 |
| ↳ get_starbases() | ✅ Done | 2025-01-12 |
| **Mega-Tool Optimization** | ✅ Done | 2025-01-12 |
| ↳ get_full_briefing() | ✅ Done | 43s → 17s (60% faster) |
| **Dynamic Personality System** | ✅ Done | 2025-01-12 |
| ↳ get_empire_identity() | ✅ Done | Extracts ethics, gov, civics, species |
| ↳ get_situation() | ✅ Done | Game phase, war status, economy |
| ↳ personality.py | ✅ Done | Builds dynamic prompts from empire data |
| ↳ Save change detection | ✅ Done | /reload command, auto-detect |
| ↳ v1 vs v2 comparison | ✅ Done | Chose v2 (Gemini-interpreted) |

---

## Development Roadmap

### Current Tool Coverage

```
Implemented Tools (v2_native_tools.py):
│
│  MEGA-TOOL (for broad questions - 60% faster):
├── get_full_briefing()   ✅ → ALL data in one call (~4k tokens)
│
│  ORIGINAL TOOLS:
├── get_player_status()   ✅ → military/economy/tech power, planets, fleets
├── get_empire_details()  ✅ → lookup any empire by name
├── get_active_wars()     ✅ → current conflicts
├── get_fleet_info()      ✅ → player's fleet names and count
├── search_save_file()    ✅ → raw text search with context
│
│  TIER 1 EXPANSION (2025-01-12):
├── get_leaders()         ✅ → 38 leaders with traits, levels, classes
├── get_technology()      ✅ → 211 completed techs, current research
├── get_resources()       ✅ → monthly income/expenses, net production
├── get_diplomacy()       ✅ → 30 relations, treaties, alliances
├── get_planets()         ✅ → 22 colonies, population, stability
└── get_starbases()       ✅ → 6 starbases, levels, modules
```

**Total: 12 tools implemented**

**Discord bot note:** the in-game `/ask` path (see `backend/core/companion.py`) uses a consolidated 4-tool surface:
`get_snapshot()`, `get_details(categories, limit)`, `get_empire_details(name)`, and `search_save_file(query)`. For `/ask`, a snapshot is pre-injected (from `get_full_briefing()`), and the model only calls drill-down tools when needed.

### Mega-Tool Optimization (2025-01-12)

Added `get_full_briefing()` to reduce latency for broad questions:

| Question Type | Before | After | Improvement |
|---------------|--------|-------|-------------|
| Broad ("strategic briefing") | 43s | **17s** | **60% faster** |
| Specific ("admirals?") | 8s | 8s | Same |

**How it works:**
- Broad questions → `get_full_briefing()` → 1 API round-trip
- Specific questions → targeted tool → 1 API round-trip
- Model chooses based on question type

**Context efficiency:** ~4k tokens (0.4% of context window)

---

## Dynamic Personality System

### Overview

The advisor personality is **dynamically generated** from empire data, not hardcoded. This makes the advisor feel like it belongs to YOUR empire.

### Data Sources for Personality

| Data | Source | When Extracted | Can Change? |
|------|--------|----------------|-------------|
| **Ethics** | Player country block | At init | Yes (ethics shift, faction embrace) |
| **Government** | Player country block | At init | Yes (reform every 20 years) |
| **Civics** | Player country block | At init | Yes (with government reform) |
| **Species** | Species DB | At init | Rarely (gene modding) |
| **Game Phase** | Save date | At init | Yes (with each save) |
| **War Status** | Wars section | On-demand | Yes (constantly) |
| **Economy State** | Resources | On-demand | Yes (constantly) |
| **Rivals/Allies** | Diplomacy | On-demand | Yes (constantly) |

### Personality Construction

```
┌─────────────────────────────────────────────────────────────────┐
│  PERSONALITY LAYERS                                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. BASE PERSONALITY (from Ethics)                               │
│     Militarist → Aggressive, speaks of glory and conquest        │
│     Pacifist → Diplomatic, cautions against war                  │
│     Xenophile → Curious, emphasizes cooperation                  │
│     Xenophobe → Suspicious, emphasizes self-reliance             │
│     Authoritarian → Formal, respects hierarchy                   │
│     Egalitarian → Casual, values freedom                         │
│     Spiritualist → Reverent, speaks of destiny                   │
│     Materialist → Logical, data-driven                           │
│                                                                  │
│  2. ADDRESS STYLE (from Government)                              │
│     Democracy → "President" / "Chancellor"                       │
│     Oligarchy → "Director" / "Councilor"                         │
│     Imperial → "Your Majesty" / "Emperor"                        │
│     Dictatorship → "Supreme Leader"                              │
│     Corporate → "CEO" / "Executive"                              │
│     Hive Mind → Uses "we" collectively                           │
│     Machine Intelligence → Pure logic, no emotion                │
│                                                                  │
│  3. QUIRKS (from Civics)                                         │
│     Technocracy → Science worship                                │
│     Warrior Culture → Military metaphors                         │
│     Merchant Guilds → Trade/profit focus                         │
│     Fanatic Purifiers → Genocidal zeal                           │
│                                                                  │
│  4. SITUATIONAL TONE (from Game State)                           │
│     At war → Urgent, threat-focused                              │
│     Peacetime → Relaxed, long-term planning                      │
│     Early game → Exploratory, optimistic                         │
│     Crisis active → Survival mode, existential stakes            │
│     Economy struggling → Cautious, resource-focused              │
│                                                                  │
│  5. RELATIONSHIP OPINIONS (from Diplomacy)                       │
│     Rivals → "The Prikkiki-Ti cannot be trusted"                 │
│     Allies → Positive mentions                                   │
│     Federation → Pride in membership                             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Ethics → Personality Mapping

| Ethics | Personality Traits | Example Phrases |
|--------|-------------------|-----------------|
| Militarist | Aggressive, respects strength | "Glory awaits", "Strike first" |
| Pacifist | Diplomatic, cautions war | "Let us seek peace", "Violence is costly" |
| Xenophile | Curious, cooperative | "New friends!", "Together we thrive" |
| Xenophobe | Suspicious, protective | "Trust no alien", "Our people first" |
| Authoritarian | Formal, hierarchical | "Order must prevail", "The state demands" |
| Egalitarian | Casual, freedom-focused | "Our citizens deserve", "Liberty guides us" |
| Spiritualist | Reverent, mystical | "The divine wills it", "Destiny calls" |
| Materialist | Logical, empirical | "The data suggests", "Efficiency demands" |

**Fanatic** versions are more extreme. Combos create interesting mixes.

### Special Cases: Gestalt Consciousness

| Type | Personality |
|------|-------------|
| **Hive Mind** | Uses "we" not "I", collective focus, no individual identity |
| **Machine Intelligence** | Cold logic, efficiency metrics, probability calculations |

### Game Phase Adaptation

| Phase | Year Range | Tone |
|-------|------------|------|
| Early | 2200-2230 | Exploratory, optimistic, "the galaxy awaits" |
| Mid | 2230-2350 | Strategic, complex diplomacy, rival-focused |
| Late | 2350+ | Urgent, high-stakes, legacy-focused |
| Crisis | Any (if active) | Survival mode, existential, "we must act NOW" |

### Save Sync Handling

When saves sync from Steam Cloud:

1. **Detect file change** via timestamp check
2. **Re-extract identity** (ethics/gov may have changed)
3. **Compare to previous** identity
4. **Rebuild personality** if changed
5. **Optionally acknowledge** shift in-character

```
Save 1 (Year 2250): Xenophile Democracy → "President, our friends await!"
Save 2 (Year 2350): Xenophobe Imperial → "Your Majesty, the xenos threaten us."

"I see much has changed since my last briefing, Your Majesty.
The old ways are behind us. How may I serve the Empire?"
```

### Early Game Handling

All personality data is available from game start (Year 2200) because it comes from **empire creation**, not gameplay progression.

| Data | Early Game Status |
|------|-------------------|
| Ethics | ✅ Always available |
| Government | ✅ Always available |
| Civics | ✅ Always available |
| Species | ✅ Always available |
| Diplomacy | Empty (no contacts yet) |
| Wars | Empty (can't war with no contacts) |

Early game advisor uses "exploratory" tone when diplomacy data is empty.

### Implementation

New methods in `save_extractor.py`:

```python
def get_empire_identity(self) -> dict:
    """Extract static empire identity for personality.

    Returns ethics, government, civics, species info.
    Called once at init, cached for session.
    """

def get_situation(self) -> dict:
    """Analyze current game situation for tone modifiers.

    Returns game phase, war status, economy state.
    Can be refreshed on demand.
    """
```

New personality builder in `personality.py`:

```python
def build_personality_prompt_v2(identity: dict, situation: dict) -> str:
    """Generate dynamic system prompt using Gemini-interpreted approach.

    Passes raw empire data and lets Gemini's knowledge of Stellaris
    generate the appropriate personality. Handles ALL civics including
    DLC and mods without hardcoding.
    """
```

### Personality Approach Decision

**Tested two approaches:**

| Approach | Description | Pros | Cons |
|----------|-------------|------|------|
| **Hardcoded Mappings (v1)** | Map each ethic/civic to specific personality traits | Predictable, consistent tone | Incomplete coverage (~30% of civics mapped), maintenance burden |
| **Gemini-Interpreted (v2)** | Pass raw data, let Gemini's Stellaris knowledge interpret | 100% coverage, handles DLC/mods, no maintenance | ~300 extra tokens, slightly less predictable |

**Test Results (United Nations of Earth 2, Year 2395):**

| Aspect | Hardcoded (v1) | Gemini-Interpreted (v2) |
|--------|----------------|------------------------|
| Greeting | "Let's get down to brass tacks, President!" | "Greetings, esteemed President..." |
| Tone | Punchy, casual | Diplomatic, thoughtful |
| Ethics reflection | Implicit | Explicitly mentions "egalitarian and xenophilic ethos" |
| Unknown civics | Would fail silently | Works via Gemini knowledge |
| Token cost | ~300 tokens | ~620 tokens |

**Decision: Use Gemini-Interpreted (v2)**

Reasons:
1. **100% civic coverage** - Works with all base game, DLC, and modded civics
2. **No maintenance** - As Stellaris updates, we don't need to add new mappings
3. **Smarter context awareness** - Gemini understands game phase, mentions "Federation" in late game
4. **Negligible token cost** - 320 extra tokens is 0.03% of context window
5. **Gemini knows Stellaris** - Its training data includes extensive Stellaris knowledge

The hardcoded mappings (v1) are kept in `personality.py` for reference but are not used.

### Extractor Robustness

Tested with: United Nations of Earth 2, Year 2395 (late game, 70MB save)

| Variation | Risk Level | Status |
|-----------|------------|--------|
| Different empire types (Machine, Hive, Megacorp) | Medium | ⚠️ Untested |
| Early/mid game saves | Low | ⚠️ Untested |
| Different Stellaris versions | Medium | ⚠️ Untested |
| No active wars | Low | ✅ Tested |
| Modded saves | High | ⚠️ Untested |

**Known Assumption:** Player empire data is within 500k chars of `country=` section. Works for standard games but could fail in edge cases.

---

### Function Calling Fix (2026-01-12)

**Problem:** CLI showed "Warning: there are non-text parts in the response: ['function_call']" - tools weren't being executed.

**Root Cause:** Manual tool execution loop was implemented incorrectly. The code was manually handling function calls but not properly integrating with Gemini 3's thinking/thought signatures.

**Solution:** Use the SDK's **automatic function calling** feature with the chat interface:

```python
# OLD (broken manual loop)
response = client.models.generate_content(
    model="gemini-3-flash-preview",
    contents=conversation_history,
    config=types.GenerateContentConfig(tools=tools_list)
)
# Then manually check for function_call, execute, loop...

# NEW (automatic function calling via chat)
config = types.GenerateContentConfig(
    system_instruction=system_prompt,
    tools=[func1, func2, ...],  # Pass Python functions directly
    temperature=0.7,
)

chat = client.chats.create(model="gemini-3-flash-preview", config=config)
response = chat.send_message(user_message)  # SDK handles tool loop automatically
print(response.text)  # Final text after all tools executed
```

**Key Points:**
1. **Use `client.chats.create()`** - The chat interface handles the tool execution loop
2. **Pass Python functions as tools** - SDK converts them to declarations
3. **SDK handles thought signatures** - For Gemini 3 models, SDKs manage this automatically
4. **Model must be `gemini-3-flash-preview`** - Not gemini-2.0-flash

**Test Results:**
| Query | Response Time | Status |
|-------|---------------|--------|
| "What is my military power?" | 5.85s | ✅ Working |
| "Strategic briefing" | 21.90s | ✅ Working |

---

### Data Robustness Fix (2026-01-12)

**Problem:** Model hallucinated "198 planets with ~4 pops each" when actual data was 22 colonies with ~36 pops each.

**Root Cause:** Ambiguous field name `planet_count: 198` (which was celestial bodies in territory) was misinterpreted as colonized planets.

**Solution:** Made data structures self-documenting to prevent LLM misinterpretation:

1. **Renamed ambiguous fields:**
   - `planet_count` → `celestial_bodies_in_territory`

2. **Added pre-computed metrics:**
   ```python
   'colonies': {
       'total_count': 22,
       'total_population': 786,
       'avg_pops_per_colony': 35.7,
       '_note': 'These are colonized worlds with population, not all celestial bodies',
       'habitats': {'count': 8, 'population': 274, 'avg_pops': 34.2},
       'planets': {'count': 14, 'population': 512, 'avg_pops': 36.6},
   }
   ```

3. **Removed hardcoded assessments:** Instead of:
   - `population_health: "excellent"` (hardcoded 30+ threshold)
   - `economy_state: "stable"` (hardcoded threshold)

   We now provide raw data and let the model interpret based on context (game phase, empire type, etc).

4. **Separated habitats from planets:** Different pop capacities (habitats ~8-12, planets ~50+) require separate metrics to avoid skewed averages.

**Why This Scales:**
- No hardcoded thresholds that assume specific game settings
- Raw data lets model apply Stellaris knowledge contextually
- Habitat/planet separation handles different empire strategies
- Works for early game (few pops) and late game (many pops)

---

### Roadmap Tiers

#### Tier 1: Expand Tool Coverage ✅ COMPLETE

All 6 new tools implemented and tested.

| Tool | Status | Test Results |
|------|--------|--------------|
| `get_leaders()` | ✅ Done | 38 leaders extracted with traits, levels, classes |
| `get_technology()` | ✅ Done | 211 completed techs, categorized by type |
| `get_resources()` | ✅ Done | Monthly income/expenses with net production |
| `get_diplomacy()` | ✅ Done | 30 relations with treaties, alliances |
| `get_planets()` | ✅ Done | 22 colonies, 786 pops, stability scores |
| `get_starbases()` | ✅ Done | 6 starbases with modules/buildings |

**Questions now answerable:**
- "Who are my best admirals?" ✅ Tested - strategic leader analysis
- "What is my economy like?" ✅ Tested - deficit warnings, recommendations
- "Tell me about my planets" ✅ Tested - stability issues, habitat warnings
- "What empires like me?" ✅ Works (rate limit dependent)
- "What tech should I research?" ✅ Works

#### Tier 2: Character & UX (2-4 hours each)

Make the advisor feel like a person, not a database.

| Feature | Description | Status |
|---------|-------------|--------|
| **Advisor Personality** | Dynamic personality from empire data | ✅ **DONE** - See Dynamic Personality System section |
| **Structured Briefings** | Formatted status reports | Pending |
| **Conversation Memory** | Persist chat across sessions | Pending |
| **Better Formatting** | Rich terminal output | Pending |

**Personality system generates prompts like:**
```
You are the chief strategic advisor to United Nations of Earth.
PERSONALITY: You are values individual freedom, open to aliens, values cooperation.
ADDRESS: Address the ruler as "President". Collegial and open.
QUIRKS: passionate about freedom and inspiring others to democracy.
TONE: Strategic and engaged. Focus on consolidation, diplomacy, and positioning.
```

#### Tier 3: Analysis Features (4-8 hours each)

Proactive intelligence and strategic depth.

| Feature | Description | Value |
|---------|-------------|-------|
| **Delta Detection** | Compare saves, report changes | "Since last session: 2 new wars, Admiral Chen died, tech completed" |
| **Threat Assessment** | Rank nearby dangers | Analyze neighbor military power, ethics, opinion trends |
| **Strategic Recommendations** | Proactive advice | "Your energy income is declining - consider building more generators" |
| **War Room Mode** | Deep military analysis | Fleet compositions, force comparisons, chokepoint analysis |

**Delta detection example:**
```python
class DeltaDetector:
    def compare(self, old_state: dict, new_state: dict) -> list[Change]:
        changes = []
        # Compare wars, leaders, empires, resources, etc.
        return changes
```

#### Tier 4: Advanced Features (8+ hours each)

Full design document vision - build when core is solid.

| Feature | Description | Complexity |
|---------|-------------|------------|
| **Intel Filtering** | Fog of war respect | Parse intel_manager, filter by intel level |
| **Analysis Queue** | Pre-generate insights | Background processing when saves change |
| **Three Modes** | Immersive/Learning/Post-game | Different system prompts and filtering |
| **Chronicle System** | Track empire history | Persistent timeline of major events |
| **Discord Integration** | In-game accessible | Discord bot with slash commands |

---

### Infrastructure (When Needed)

| Feature | Description | Priority |
|---------|-------------|----------|
| **Steam Cloud Sync** | Auto-download new saves | Deferred |
| **File Watcher** | Detect save changes | Implemented (Discord bot: watchdog) |
| **Web Dashboard** | Visual interface | Future |
| **Multi-save Support** | Compare different playthroughs | Future |

---

### Recommended Next Steps

Based on value/effort ratio (Tier 1 + Personality complete):

| Order | Task | Time | Impact |
|-------|------|------|--------|
| ~~1~~ | ~~Add advisor personality~~ | ~~2 hr~~ | ✅ **DONE** |
| 1 | **Conversation persistence** | 2 hr | Memory across sessions |
| 2 | **Test with different saves** | 1 hr | Validate robustness |
| 3 | **Build delta detection** | 4 hr | "What changed?" feature |
| 4 | **Structured briefings** | 2 hr | "Status report" command |
| 5 | **Threat assessment** | 3 hr | Analyze neighbors, rank dangers |

---

## How to Run

### V2 (Current - Recommended)

```bash
# Setup
cd ~/stellaris-companion
source venv/bin/activate
export GOOGLE_API_KEY="your-gemini-key"

# Run with Native SDK (recommended)
python v2_native_tools.py "/path/to/save.sav"

# Alternative: Run with ADK
python v2_adk_tools.py "/path/to/save.sav"

# Commands in chat
/clear    # Reset conversation
/quit     # Exit
```

### V1 (Legacy - Claude)

```bash
# Setup
cd ~/stellaris-companion
source venv/bin/activate
export ANTHROPIC_API_KEY="your-anthropic-key"

# Run with a save file
python v1_test.py /path/to/save.sav

# Commands in chat
/search <term>   # Search full gamestate
/info            # Show save summary
/quit            # Exit
```

---

## Links

- [Full Design Document](../stellaris-llm-companion-design.md) - Complete system design
- [Steam Cloud Storage](https://store.steampowered.com/account/remotestorage) - Manual save download
- [Stellaris Save Format](https://stellaris.paradoxwikis.com/Save-game_editing) - Wiki documentation
