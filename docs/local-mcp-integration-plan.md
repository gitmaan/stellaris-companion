# Local MCP Integration Plan

## Goal

Expose Stellaris Companion as a local MCP server so local AI clients can use current campaign context and, when the user explicitly asks, save Chronicle edits back to the app without requiring a remote service or cloud sync layer.

## Implementation Log

- 2026-05-05: Verified Claude Desktop MCPB can call the local Advisor Briefing and Chronicle writeback tools against the development checkout.
- 2026-05-05: Verified Chronicle create and undo reflect immediately in the Electron app when the app is running.
- 2026-05-05: Identified production release guardrail: the shipped app must rebuild the PyInstaller backend with `--mcp`, package the MCPB, and smoke-test the bundled MCP stdio server before publishing.
- 2026-05-05: Started MCP polish pass for advisor persona consistency, user-facing writeback responses, display-name cleanup for raw Stellaris identifiers, and regression tests against internal ID leaks.
- 2026-05-05: Completed the polish pass and release guardrails; see Progress Log entries for implementation and verification details.
- 2026-05-05: Hardened the production build path so stale `dist-python` bundles fail before packaging, even when a developer runs lower-level Electron packaging commands directly.

The first supported experience is:

- The Electron app continues to ingest saves, maintain sessions, generate/cache Chronicle content, and provide the primary UI.
- Local MCP clients ask Stellaris Companion for rich, structured context.
- Claude/Codex/other local MCP clients produce their responses in their own chat UI.
- Chronicle drafting and revision happens in chat first.
- Chronicle save/edit/create/undo tools are available, but tool guidance tells clients to call them only after explicit user intent such as "save this" or "send this to Stellaris Companion."
- Users should not need to know MCP vocabulary, resource URIs, config JSON, or tool names during normal use.

## Non-Goals

- No remote HTTPS MCP server.
- No Claude.ai or ChatGPT web connector support in this phase.
- No cloud sync of save data, extracted summaries, or Chronicle content.
- No raw save mutation.
- No automatic Chronicle write-back before the user asks to save/apply/send back.
- No hidden settings, flags, or MCP terminology in the user-facing Chronicle editing flow.
- No replacement of the existing Gemini-backed in-app Advisor or Chronicle features.
- No Codex App Server integration. Codex can consume MCP, but the Codex App Server is a separate embedding surface for Codex as a coding agent.

## Target Clients

Local MCP should target clients that can connect to local MCP servers, such as:

- Claude Desktop.
- Claude Code.
- Codex CLI / Codex IDE MCP configuration.
- Cursor or other local MCP-compatible clients.

ChatGPT web is out of scope because it does not connect directly to private localhost/stdio MCP servers. If a future ChatGPT desktop/local client supports local MCP, it can use the same server.

## 2026 MCP UX Findings

Research snapshot as of 2026-05-05:

- The latest stable MCP specification is still `2025-11-25`; there was no newer April/May 2026 spec release to target.
- The official 2026 MCP roadmap is pointing toward transport scalability, event-driven updates, tasks, governance, and enterprise readiness. Those are useful later, but they do not change the local-only v1 architecture.
- Claude Desktop supports MCPB desktop extensions, which are the most seamless install path for a local Claude integration.
- Current MCP clients are increasingly using metadata, clear tool descriptions, prompts, resources, and icons to make connectors feel like product surfaces rather than hidden developer plumbing.
- OpenAI's Apps SDK guidance is not a local MCP client contract, but its metadata advice maps well to this server: use specific titles, "use this when..." descriptions, strict schemas, and output shapes that make tool choice obvious to the model.

What this means for Stellaris Companion:

- Keep the local stdio server as the core transport.
- Package a Claude Desktop MCPB extension as the first "one click" install target.
- Treat the connector as a branded local campaign surface named `Stellaris Companion` or, if we want a more playful connector label, `Galactic Filing Cabinet`.
- Encode as much intent as possible in MCP itself: server instructions, display titles, icons, output schemas, prompts, and resources.
- Do not spend v1 effort on remote MCP, OAuth, remote connector hosting, or ChatGPT web support.

Already encoded:

- Read-only annotations for context tools and write annotations for Chronicle save tools.
- Structured tool results via `structuredContent`.
- A practical Advisor/Chronicle tool split.
- Branded server metadata such as display title, description, website URL, and icons.
- Server `instructions` returned during MCP initialization.
- Display titles/icons and stronger descriptions for each tool.
- Tool `outputSchema` definitions.
- Advisor response guidance now includes an explicit in-universe persona contract and presentation rules.
- Chronicle save/edit/undo results now return user-facing confirmation messages instead of internal operation names or cache targets.
- Common raw Stellaris identifiers in returned values are converted to readable labels before reaching the client.
- Claude Desktop MCPB packaging is implemented and generated during release builds.
- CI smoke checks now launch the bundled backend in `--mcp` mode and verify the expected MCP tools before publishing.

Not yet encoded:

- MCP prompts for branded workflows.
- MCP resources/resource templates for attachable campaign documents.

Current prompt/resource state:

- `tools/list` is implemented and is the real user path today.
- `prompts/list` currently returns an empty array, meaning clients do not see reusable branded prompt recipes such as "Advisor Briefing" or "Write Chronicle Current Era."
- `resources/list` currently returns an empty array, meaning clients do not see attachable campaign documents such as `stellaris://campaign/active/briefing`.
- This is acceptable for the current natural-language flow because clients can discover and call tools directly from normal user asks. Prompts/resources remain optional polish and interoperability surfaces.

Product decision:

- The external Advisor flow should mirror the in-app Advisor: one main Advisor Briefing call should provide enough current campaign context for nuanced answers.
- Do not break the default Advisor experience into many small required tool calls.
- Section tools/resources are optional detail surfaces for clients, debugging, or constrained context windows. They should not be presented as commands users need to type.
- User prompts should stay natural, for example: `What is hurting my economy?`, `Can I win this war?`, or `What should I do in the next decade?`

## Architecture

```text
Local MCP client
    |
    | MCP tool call
    v
Stellaris Companion local MCP server
    |
    | internal local call / shared Python services
    v
Existing Python backend + database
    |
    +-- active save/session status
    +-- latest briefing JSON
    +-- recent events and snapshots
    +-- cached Chronicle chapters/current era
    +-- advisor custom instructions and compact memory
```

The MCP server should reuse existing backend services instead of parsing saves independently. Save ingestion remains owned by the current Electron-managed Python backend.

## Transport Choice

Prefer a local stdio MCP server for v1.

Reasons:

- It is easiest for Claude Desktop, Claude Code, Codex CLI, and editor clients to launch.
- It avoids exposing another localhost HTTP port by default.
- It keeps auth simpler because the server is launched as a local child process.

An optional localhost Streamable HTTP transport can be added later if it improves client compatibility or debugging.

Streamable HTTP should remain explicitly out of v1 unless a local desktop client requires it. The product goal is "local and private" rather than "network-addressable."

## Backend Shape

Add a small MCP package:

```text
backend/mcp/
  __init__.py
  server.py
  context.py
```

`context.py` should contain client-neutral read helpers. `server.py` should only adapt those helpers into MCP tools.

The context service should call into existing database/backend logic where possible:

- `backend/core/database.py` for sessions, briefings, events, chronicle cache, advisor memory.
- `backend/core/chronicle.py` for cached Chronicle structure only, avoiding generation unless a tool explicitly says it may generate.
- Existing active-save resolution patterns in `backend/api/server.py`.

## Tool Set

The current implementation exposes six core context tools and four Chronicle save/edit tools. The save/edit tools are first-class user capabilities, but their descriptions tell the model not to call them while the user is still drafting or revising in chat.

Tooling principle:

- `get_strategy_context` / `Advisor Briefing` is the primary path for strategic questions.
- It should be generous by default, because richer context produces more nuanced advice and the in-app Advisor already works by passing the full precomputed briefing each turn.
- `get_empire_briefing` should not be a required step before answering. It is a follow-up/detail tool when a client needs a particular section or when payload size becomes a problem.
- `get_recent_events`, advisor memory, and advisor custom instructions are genuinely additive to the briefing and should remain bundled into the main Advisor context where practical.

Suggested display titles:

- `get_active_campaign`: `Campaign Status`
- `get_strategy_context`: `Advisor Briefing`
- `get_empire_briefing`: `Empire Briefing`
- `get_recent_events`: `Recent Dispatches`
- `get_cached_chronicle`: `Chronicle Archive`
- `get_chronicle_source_material`: `Chronicle Source Material`
- `save_chronicle_current_era`: `Save Chronicle Current Era`
- `update_chronicle_chapter`: `Update Chronicle Chapter`
- `create_chronicle_chapter`: `Create Chronicle Chapter`
- `undo_chronicle_edit`: `Undo Chronicle Edit`

Suggested shared description guidance:

- This server reads local Stellaris Companion data only.
- It never calls Gemini or another model.
- It cannot mutate Stellaris save files.
- Chronicle save tools update only the local Chronicle cache and should be called only after explicit user save/apply/send-back intent.
- Use Advisor tools for strategic answers and Chronicle tools for narrative/history answers.
- Prefer the main Advisor Briefing for strategic questions. Use section tools only for follow-up detail or context-budget constraints.

### `get_active_campaign`

Return the currently loaded campaign/session summary.

Suggested output:

```json
{
  "save_loaded": true,
  "save_id": "...",
  "active_session_id": "...",
  "empire_name": "...",
  "game_date": "2254.03.12",
  "snapshot_count": 42,
  "last_ingested_at": "..."
}
```

### `get_strategy_context`

Return rich context for an advisor-style question.

Inputs:

```json
{
  "question": "What should I fix in my economy?",
  "focus": "auto"
}
```

Behavior:

- No LLM call.
- Load the latest cached full briefing from Stellaris Companion.
- Return a generous Advisor context by default, not a tiny slice.
- Preserve `focus` as a prioritization hint, not as a hard limit that hides useful neighboring context.
- Include empire identity, game date, difficulty/version/DLC context if available.
- Include recent events from the history database.
- Include relevant patch/version notes only if the existing app already has that material loaded in a compact form.
- Include advisor custom instructions and compact advisor memory if present.

This is the main Advisor tool. The local MCP client does the reasoning.

### `get_empire_briefing`

Return selected briefing sections for clients that need follow-up detail.

Inputs:

```json
{
  "sections": ["economy", "military", "diplomacy"],
  "max_detail": "compact"
}
```

Allowed sections should mirror existing briefing structure where practical.

This tool should not provide data that is unavailable to the main full briefing. It is a narrower projection of the same cached briefing, useful for:

- follow-up detail after the main Advisor Briefing.
- clients with strict context budgets.
- troubleshooting and manual QA.
- future resource/template implementations.

It should not be described to users as something they need to call directly.

### `get_recent_events`

Return recent campaign events.

Inputs:

```json
{
  "limit": 25,
  "notable_only": false
}
```

Use this for lightweight "what happened recently?" prompts and for Chronicle source context.

### `get_cached_chronicle`

Return the currently cached Chronicle without generating new prose.

Output should include:

- title/empire name.
- finalized chapters.
- current era teaser, if cached.
- cache metadata.
- whether generation is unavailable because no Chronicle has been opened/generated yet.

### `get_chronicle_source_material`

Return source material for a local MCP client to write Chronicle prose in chat.

Inputs:

```json
{
  "scope": "current_era",
  "chapter_number": null,
  "max_events": 80
}
```

Supported scopes:

- `current_era`
- `latest_session`
- `chapter:<number>`
- `full_summary`

Behavior:

- Advertises that save-back is available, while also telling clients not to save without explicit user intent.
- No raw save data.
- Return event ranges, dates, involved entities, current empire state, and Chronicle style instructions.
- Prefer structured event/source material over generated prose when the user asks the external model to write.

## MCP Prompts

Prompts are the main way to make the connector feel seamless inside clients that surface them. They should be branded, short, and opinionated. Each prompt should tell the client which tools to call and remind the model that the final answer belongs in the external chat UI.

Recommended prompts:

- `advisor_economy_triage`: Calls `get_strategy_context` with `focus="economy"` and asks for the top three economic fixes, the evidence behind each, and the next concrete in-game action.
- `advisor_war_room`: Calls `get_strategy_context` with `focus="military"` and asks whether the empire can safely fight, deter, or should delay.
- `advisor_next_10_years`: Calls `get_strategy_context` with `focus="auto"` and asks for a decade plan across economy, fleets, diplomacy, and expansion.
- `chronicle_continue_current_era`: Calls `get_chronicle_source_material` with `scope="current_era"` and writes a fresh passage in the user's requested tone.
- `chronicle_session_recap`: Calls `get_chronicle_source_material` with `scope="latest_session"` and writes a concise campaign recap.
- `chronicle_recite_archive`: Calls `get_cached_chronicle` and presents the existing archive without inventing missing chapters.

Prompt copy should use the app's existing language:

```text
You are reading from Stellaris Companion's local campaign archive. Use the provided campaign context only. Do not claim to have changed the app, saved a Chronicle passage, or inspected raw save files.
```

Future nicety: expose prompt argument completions for fields such as `focus`, `scope`, and `chapter_number` when the client supports MCP completions.

## MCP Resources

Resources give clients attachable read-only documents. They should be useful infrastructure, not the primary user experience.

Users should not need to type resource syntax such as `@stellaris:briefing/economy`. If a client exposes resources in a picker, labels should be friendly, such as `Economy Briefing`, `Recent Dispatches`, or `Chronicle Archive`.

Resources should mirror the same data returned by tools, not introduce separate business logic.

Recommended static resources:

- `stellaris://campaign/active`: Current campaign/session identity and freshness.
- `stellaris://briefing/economy`: Compact economy briefing.
- `stellaris://briefing/military`: Compact military briefing.
- `stellaris://briefing/diplomacy`: Compact diplomacy briefing.
- `stellaris://events/recent`: Recent dispatches from the active campaign.
- `stellaris://chronicle/archive`: Cached Chronicle chapters/current era.
- `stellaris://chronicle/source/current-era`: Source material for current-era Chronicle writing.

Recommended resource templates:

- `stellaris://briefing/{section}` for known briefing sections.
- `stellaris://chronicle/source/{scope}` for `current_era`, `latest_session`, `full_summary`, and specific chapters.

Resource rules:

- Return `application/json` for structured context.
- Keep resource payloads compact by default.
- Do not expose absolute filesystem paths unless the user is debugging setup.
- Do not expose raw `.sav` data.
- Treat resources as optional browse/attach surfaces. The model should still be able to answer normal Advisor questions by calling the main Advisor Briefing tool.

## Advisor Experience

```text
User in Claude Desktop:
  "Use Stellaris Companion. What is my biggest bottleneck right now?"

Client:
  calls get_strategy_context(question)

MCP server:
  returns a rich Advisor Briefing from the current campaign, plus recent events and advisor memory

Claude:
  answers in Claude Desktop
```

The Electron Advisor tab is unchanged. It still uses the existing in-app backend path and Gemini model when the user asks inside the app.

Important: the in-app Advisor currently passes the full precomputed briefing every turn and does not use tool-calling. The MCP Advisor path should preserve that spirit. Do not make external clients assemble core strategic context from many small section calls unless a client context limit forces that fallback.

## Chronicle Experience

Three supported flows:

1. Ask for the existing archive.

```text
User:
  "Show me the current chronicle for this campaign."

Client:
  calls get_cached_chronicle()

Claude/Codex:
  summarizes or displays the returned chapters in chat.
```

2. Ask an external model to write from source material.

```text
User:
  "Write the next Chronicle passage in a colder imperial tone."

Client:
  calls get_chronicle_source_material(scope="current_era")

Claude/Codex:
  writes the passage in chat.
```

The generated passage is not saved into Stellaris Companion yet. The user can keep revising in chat:

```text
User:
  "Make it shorter and more ominous."

Claude/Codex:
  revises in chat without calling a save tool.
```

3. Save when the user is ready.

```text
User:
  "Save that Chronicle passage back to Stellaris Companion."

Client:
  calls the appropriate save tool only after this explicit request:
    save_chronicle_current_era()
    update_chronicle_chapter()
    create_chronicle_chapter()
    undo_chronicle_edit()

Stellaris Companion:
  updates the local Chronicle cache shown by the Electron app.
```

Save tools do not edit the Stellaris save, regenerate via Gemini, or change Advisor data. The Electron Chronicle page refreshes on focus/resume so saved external edits are picked up when the user returns to the app.

## Branded Experience

The external AI integration should feel like a local intelligence desk for the current campaign, not a developer add-on.

Recommended connector identity:

- Name: `Stellaris Companion`
- Optional extension label: `Galactic Filing Cabinet`
- Short tagline: `Local Stellaris intelligence for your AI advisor.`
- Privacy line: `Reads your local campaign archive. Never edits saves. Never calls Gemini.`

Suggested server instructions:

```text
Stellaris Companion provides local context about the user's current Stellaris campaign. Use Advisor tools for strategy questions and Chronicle tools for narrative or campaign-history questions. Draft Chronicle prose in chat first. After presenting a Chronicle draft, briefly tell the user they can say "save this to Stellaris Companion" when ready. Only save, update, create, or undo Chronicle content after the user explicitly asks.
```

Suggested user-facing examples:

- `What is my biggest bottleneck right now?`
- `Give me a war-room readout before I attack.`
- `Write a Chronicle passage for the current era.`
- `Summarize the last session in imperial archive style.`

## Electron UX

Add a Settings section named "External AI" or "Local MCP".

Suggested controls:

- Toggle: `Enable local MCP server`.
- Status line: `Read-only local connector`.
- Health line: latest detected campaign, game date, and last ingest time.
- Button: `Install for Claude Desktop`.
- Button: `Copy Claude Desktop config`.
- Button: `Copy Claude Code command`.
- Button: `Copy Codex config`.
- Button: `Copy MCP health check`.
- Link/button: `Open local MCP setup guide`.

If the stdio server is launched by the client rather than kept alive by Electron, the Settings page can instead provide setup snippets and a health check command.

The best first seamless flow is:

1. Detect the packaged backend/MCP executable path.
2. Generate a Claude Desktop MCPB bundle or config snippet.
3. Show a single install/copy action in Settings.
4. Offer a smoke-test command that calls `get_active_campaign`.
5. Explain that answers appear inside Claude/Codex/compatible clients, while Stellaris Companion remains the local source of truth.

## Claude Desktop MCPB Packaging

MCPB should be the preferred Claude Desktop install format once the server metadata is upgraded.

Package goals:

- One user-visible install artifact.
- Branded name, description, version, author, and icon.
- Launch the packaged `stellaris-companion-mcp` or `stellaris-backend --mcp` command.
- Point at the default SQLite database location, with Settings able to regenerate the path if the user moves app data.
- Preserve the manual JSON config fallback for development and troubleshooting.

This remains local-only: MCPB packaging is an installer wrapper for Claude Desktop, not a remote server.

## ChatGPT And Codex Notes

ChatGPT web remains out of scope for local-only MCP because it cannot attach to a private stdio server. If ChatGPT Desktop exposes a local MCP configuration surface in the future, the same server, prompts, resources, and schemas should work.

Codex should consume this as a normal local MCP server. The Codex App Server is still not needed for Advisor or Chronicle because this feature is about giving external AI clients local campaign context, not embedding a coding agent inside Stellaris Companion.

## Client Configuration Snippets

Development command, from this checkout:

```bash
env PYTHONPATH=/Users/avani/stellaris/stellaris-companion \
  /opt/homebrew/bin/python3 -m backend.mcp.server \
  --db-path "$HOME/Library/Application Support/stellaris-companion/stellaris_history.db"
```

Installed package command:

```bash
stellaris-companion-mcp \
  --db-path "$HOME/Library/Application Support/stellaris-companion/stellaris_history.db"
```

Packaged backend command:

```bash
stellaris-backend --mcp \
  --db-path "$HOME/Library/Application Support/stellaris-companion/stellaris_history.db"
```

### Claude Desktop

```json
{
  "mcpServers": {
    "stellaris-companion": {
      "command": "/opt/homebrew/bin/python3",
      "args": [
        "-m",
        "backend.mcp.server",
        "--db-path",
        "/Users/avani/Library/Application Support/stellaris-companion/stellaris_history.db"
      ],
      "env": {
        "PYTHONPATH": "/Users/avani/stellaris/stellaris-companion"
      }
    }
  }
}
```

### Claude Code

```bash
claude mcp add stellaris-companion -- /path/to/stellaris-companion-mcp
```

### Codex

```toml
[mcp_servers.stellaris_companion]
command = "/path/to/stellaris-companion-mcp"
args = []
```

## Manual QA Notes

- Claude Desktop loaded a development config entry named `stellaris-companion-dev`.
- Claude Desktop discovered the local MCP tools and requested permission for `get_active_campaign`.
- After permission, Claude returned the active local campaign: `Glebsig Foundation — 2215.01.01`.
- ChatGPT Desktop could not be driven by Computer Use in this environment because `com.openai.chat` is blocked by the Computer Use safety layer. No local MCP config surface was found under `~/Library/Application Support/com.openai.chat` during this pass.

## Natural-Language Comparison QA

2026-05-05 controlled comparison:

- Method: asked end-user-style questions against saved before/after MCP payloads, using `gemini-3.1-flash-lite-preview` as a stand-in language model. The stripped payloads were identical except for the new guidance fields, so answer differences were caused by the guidance rather than changed campaign data.
- Advisor economy: after guidance produced a clearer diagnosis/evidence/actions/trade-offs answer and avoided the before answer's misleading "100/75 over naval capacity" inference.
- Advisor war-room: after guidance kept the same practical shape but was more cautious about fleet expansion, focused on fortification/upgrades/alloys, and again avoided presenting the naval-capacity data as over-cap.
- Chronicle current era: after guidance was much more in-universe and branded to the Glebsig Foundation's spiritual/bureaucratic identity, but it was shorter and less comprehensive than the before answer. This is additive for tone, but golden tests should ensure it does not omit important events.
- Chronicle archive: after guidance was only modestly different, but slightly better at respecting the existing archive boundary and avoiding invented chapters.

Recommendation from this comparison: keep the guidance fields. They improve end-user answer shape without adding visible complexity, but add golden prompt tests for Chronicle completeness so style does not crowd out substance.

## Security And Privacy

- Advisor and campaign context tools are read-only.
- Chronicle save/edit/create/undo tools are write tools and are annotated as non-read-only/destructive so clients can apply their normal permission UX.
- Chronicle write tools update only the local Chronicle cache. They do not edit Stellaris `.sav` files, call Gemini, change Advisor data, or write provider credentials.
- Tool descriptions and result guidance tell clients to draft/revise in chat and save only after explicit user intent.
- Do not expose raw save files.
- Do not expose the existing backend bearer token to the renderer.
- Do not include hidden filesystem paths unless needed for debugging.
- Keep outputs compact and scoped to the requested campaign context.
- Do not return raw writeback operation names, Chronicle cache targets, source tags, or raw game IDs in model-visible content.
- Add an in-app warning that enabled MCP clients can read campaign context through the local server.
- Do not include Gemini API keys or provider credentials in MCP output.

## Implementation Status

Implemented in this repository:

- Local stdio MCP server in `backend/mcp/server.py`.
- Local context service in `backend/mcp/context.py`.
- Python script entrypoint: `stellaris-companion-mcp`.
- Packaged-backend compatible mode: `stellaris-backend --mcp`.
- Rich default `Advisor Briefing` context with focused fallback if a late-game payload exceeds the configured ceiling.
- Branded server initialization metadata and instructions.
- Tool display titles, icons, stronger descriptions, and `outputSchema` definitions.
- Compact Advisor, Chronicle source, and Chronicle archive guidance contracts in MCP tool results.
- Advisor Briefing now carries an explicit persona/presentation contract so external models answer more like the in-app advisor.
- Tool result visible text is now a short human summary; detailed context remains in structured content.
- Chronicle writeback/undo payloads now use user-facing `message`/`saved_item` fields and no longer expose cache targets or operation names.
- MCP context compaction converts common raw Stellaris identifiers in values into player-facing labels, with overrides for high-impact tech names.
- Core context tools:
  - `get_active_campaign`
  - `get_strategy_context`
  - `get_recent_events`
  - `get_empire_briefing`
  - `get_cached_chronicle`
  - `get_chronicle_source_material`
- First-class Chronicle save/edit tools:
  - `save_chronicle_current_era`
  - `update_chronicle_chapter`
  - `create_chronicle_chapter`
  - `undo_chronicle_edit`
- Chronicle source/archive payloads include a save affordance so clients can tell users they may say "save this to Stellaris Companion" when ready.
- Electron Chronicle page refreshes on focus/resume to pick up externally saved edits without exposing MCP details.
- Live Claude Desktop validation against the local app database for current-era save/undo, chapter update/undo, and chapter create/undo.
- Settings `MCP Relay` panel with a local health check, Claude Desktop install action, and copy helpers for Claude Desktop, Claude Code, Codex, and generic MCP JSON.
- Claude Desktop MCPB source bundle and packaging script. The generated `.mcpb` contains a small Node stdio wrapper that locates the installed Stellaris Companion backend and launches it in local MCP mode.
- MCPB wrapper supports configured source checkouts for development verification, and forwards backend stdio one JSON-RPC line at a time so Claude Desktop handles rapid `prompts/list` and `resources/list` startup responses cleanly.
- Installed Claude Desktop MCPB validation: natural Advisor query, Chronicle chapter create, in-app visibility, Chronicle undo, and in-app restoration all passed against the live local campaign archive.
- Release guardrails: local Electron builds now package the MCPB, CI packages the MCPB before smoke checks, smoke checks launch the bundled backend with `--mcp`, and tagged releases upload the MCPB artifact.
- Python backend builds now write `build-info.json` with app version, git/source fingerprint, timestamp, and MCP capability metadata.
- Electron packaging now has a `beforePack` guard that verifies the backend build metadata and runs the MCP stdio smoke test before an app artifact can be produced.
- `npm run build` and `npm run publish` from the Electron package now route through safe root scripts that rebuild the Python backend first.
- Regression coverage now checks for leaked internal IDs/operation names in user-facing MCP payloads.
- Advisor, Empire, Recent Dispatches, and Chronicle tool results now include answer-ready user-facing text in addition to structured MCP payloads, so clients that rely on `content` rather than `structuredContent` still get rich branded context.
- Live production-style Claude validation now runs through the rebuilt `.app` backend via the installed MCPB relay rather than the old direct development server.

Pending/future:

- MCP prompts for Advisor and Chronicle workflows.
- MCP resources and resource templates for attachable campaign context.
- Golden prompt regression tests for tool choice and answer shape.
- Full localized Stellaris string-table resolution beyond the current display-name fallback.
- Optional in-app marker for externally edited Chronicle content.
- Repeat the live Claude natural-language check after each substantial Advisor text-shape change, because client behavior varies in how strongly it uses `content` versus `structuredContent`.

## Progress Log

- 2026-05-05: Started implementation pass to make Chronicle save-back a normal user-facing MCP capability rather than a hidden flag. Target behavior: external models may draft/revise freely in chat, mention that the user can save back when ready, and only call save/edit/create tools after explicit user save/apply/send-back intent.
- 2026-05-05: Implemented first-class Chronicle save tools in MCP: `save_chronicle_current_era`, `update_chronicle_chapter`, `create_chronicle_chapter`, and `undo_chronicle_edit`. These are always listed in `tools/list`; their descriptions and annotations instruct clients to use them only after explicit user save/apply/send-back/undo intent. Focused MCP tests passed.
- 2026-05-05: Added Electron Chronicle focus/resume refresh so an externally saved Chronicle edit is picked up when the user returns to the app, without exposing cache or MCP mechanics in the UI. Renderer production build passed.
- 2026-05-05: Protocol smoke against `/tmp/stellaris-mcp-edit-flow-test.db` verified the full edit loop through stdio MCP: tools listed, save affordance present, current era saved, chapter 1 updated, chapter 2 created, create undone, and the archive read back with the expected state.
- 2026-05-05: Live Claude Desktop test passed against `/Users/avani/Library/Application Support/stellaris-companion/stellaris_history.db`. Claude used the local `stellaris-companion-dev` MCP server to save a temporary current-era draft, undo it, update Chapter 1, undo it, create Chapter 2, undo it, and re-read the Chronicle after each flow. Independent SQLite marker sweep checked all cached Chronicle rows for `CLAUDE_MCP_LIVE_TEST_DO_NOT_KEEP`, `CLAUDE_MCP_UPDATE_TEST_DO_NOT_KEEP`, and `CLAUDE_MCP_CREATE_TEST_DO_NOT_KEEP`; result: `marker_hits=[]`.
- 2026-05-05: Implemented the Settings `MCP Relay` panel. It generates dev/packaged local MCP launch config, checks Claude Desktop config status, can write the Claude Desktop `mcpServers.stellaris-companion` entry after user confirmation, copies setup snippets for Claude Desktop/Claude Code/Codex/generic MCP clients, and runs a local health check that launches the server and verifies `tools/list`. Verification: Electron main/preload syntax checks passed, renderer production build passed, and the MCP Relay health-check path returned `ok=true` with 10 tools.
- 2026-05-05: Added Claude Desktop MCPB packaging under `mcpb/stellaris-companion/`, plus `scripts/package_mcpb.py` and `npm run build:mcpb`. The MCPB uses manifest spec `0.3`, includes the app icon and a Node relay, and produces `electron/dist/mcpb/stellaris-companion-mcp-relay-0.7.1.mcpb`. Verification: archive contains root `manifest.json`, `server/index.js`, `icon.png`, and `README.md`; wrapper smoke test proxied initialize/tools/list to the dev backend and returned the MCP tool list.
- 2026-05-05: Rebuilt the MCPB relay for live Claude Desktop verification. Fixes: a configured app path may now point to a local source checkout, source checkouts are preferred over stale `dist-python` test bundles, and the Node relay line-splits/paces backend stdout so Claude Desktop does not receive multiple JSON-RPC responses as one invalid message.
- 2026-05-05: Installed the rebuilt `stellaris-companion-mcp-relay-0.7.1.mcpb` in Claude Desktop via Computer Use, configured it to `/Users/avani/stellaris/stellaris-companion`, and verified the user flow end to end. Claude naturally called `get_active_campaign`/Advisor context for "what is my current active campaign and what should I focus on next?", reported `Glebsig Foundation` at `2215.01.01`, then used `create_chronicle_chapter` to save a temporary `MCP Relay Verification` chapter. Stellaris Companion immediately showed `CHAPTERS 2` and the test chapter. Claude then used `undo_chronicle_edit`; returning to the Electron app refreshed the Chronicle to `CHAPTERS 1` with the temporary chapter removed.
- 2026-05-05: Added the production polish pass. Advisor Briefing now includes an explicit persona and presentation contract; server instructions tell clients to keep implementation details hidden; Chronicle save/edit/create/undo results now return user-facing confirmation messages rather than operation names or cache targets; visible tool-result text is summarized instead of dumping raw JSON; common raw Stellaris identifiers in values are converted to display labels; and MCP tests now fail on leaked internal identifiers such as raw tech keys, Chronicle cache targets, source tags, or writeback operation names. Verification: `python3 -m pytest tests/test_mcp_context.py`, `python3 -m py_compile backend/mcp/context.py backend/mcp/server.py scripts/smoke_mcp_stdio.py`, `bash -n scripts/ci-smoke-check.sh scripts/build-electron.sh scripts/build-all.sh scripts/build-python.sh`, `node -c mcpb/stellaris-companion/server/index.js`, `npm run build:mcpb`, and `git diff --check` passed.
- 2026-05-05: Added release guardrails for the next production build. `scripts/smoke_mcp_stdio.py` launches a bundled backend executable with `--mcp` and verifies initialize/tools-list; `scripts/ci-smoke-check.sh` now runs that check and requires the generated MCPB artifact; `scripts/build-electron.sh`, `scripts/build-all.sh`, and `electron/package.json` now package the MCPB during local builds; `.github/workflows/electron-release.yml` packages the MCPB before CI smoke and uploads it to tagged GitHub releases from the Linux release job; and `.github/workflows/windows-artifact-build.yml` now packages/uploads the MCPB for manual Windows artifacts. Local verification also confirmed the existing checked-out `dist-python/stellaris-backend/stellaris-backend` bundle is stale and fails the new smoke because it lacks `--mcp`, which is the exact failure mode the release guardrail is designed to catch after a fresh Python rebuild.
- 2026-05-05: Hardened the release guardrail into a build invariant. `scripts/build-python.sh` now stamps `dist-python/stellaris-backend/build-info.json`; `scripts/backend_build_info.py` records and verifies app version, git/source fingerprint, timestamp, and MCP capability metadata; `scripts/smoke_mcp_stdio.py` verifies that metadata before launching the backend; `electron/scripts/beforePack.js` runs the metadata check plus MCP smoke before electron-builder packages anything; `electron/electron-builder.yml` wires the guard into raw packaging; and `electron/package.json` routes `npm run build`/`npm run publish` through safe root scripts. Verification: Python compile checks, Node syntax checks, shell syntax checks, focused MCP tests, and `git diff --check` passed. The stale local `dist-python` bundle now fails immediately with `Missing build-info.json ... Rebuild the backend with scripts/build-python.sh.`
- 2026-05-05: Ran a fresh production-style `./scripts/build-all.sh` from source. The build rebuilt PyInstaller output, renderer assets, the signed macOS app, DMG/zip, and MCPB. The new `beforePack` guard passed with `MCP stdio smoke passed: 10 tools`, proving the packaged app backend supports `--mcp` before artifacts are produced. Local notarization was skipped because notarization credentials/options were unavailable in the dev environment.
- 2026-05-05: Tested the generated MCPB relay against `electron/dist/mac-arm64/Stellaris Companion.app`. The relay initialized successfully and exposed the 10 branded MCP tools. Claude Desktop was then configured to use the installed MCPB extension with the packaged app path, and the old direct `stellaris-companion-dev` server was removed from local Claude config for an honest production-path test. Backups were saved next to the edited Claude config files.
- 2026-05-05: Live Claude production-path validation found a client behavior issue: Claude could call the packaged MCPB tools, but it leaned on the short MCP `content` summaries and underused the rich `structuredContent`, producing generic strategy advice. Fixed by making tool `content` answer-ready: Advisor Briefing now includes persona, presentation contract, current campaign state, economy, military, territory, technology, diplomacy, and recent events in user-facing prose while still returning the structured payload. Focused MCP tests now assert this text includes useful player-facing evidence and no raw internal identifiers.
- 2026-05-05: Re-ran Claude with the rebuilt packaged app. Natural-language query "Using Stellaris Companion, what is my active campaign and what should I focus on next?" returned a branded `Glebsig Foundation` briefing with concrete economy/military/tech/territory recommendations instead of generic fallback advice. A follow-up tightening removed raw prior Advisor memory from answer-ready text so stale Q&A cannot be treated as current campaign evidence.
- 2026-05-05: Final production-style rebuild and verification completed after the answer-ready text tightening. Checks passed: `python3 -m pytest tests/test_mcp_context.py -q`, Python compile, `scripts/backend_build_info.py verify`, `scripts/smoke_mcp_stdio.py` for both `dist-python` and embedded app backend, packaged Advisor content check (`contains_raw_memory=False`, `contains_fleet_doctrines=True`), MCPB archive inspection, and process verification showing Claude using the packaged backend via `--mcp` while Stellaris Companion runs its packaged HTTP backend.
- 2026-05-05: Follow-up Claude validation caught an Advisor wording trap: "naval usage 100" could still be interpreted as being at/over capacity. The Advisor text now says `capacity limit not confirmed` and explicitly tells clients not to claim over cap, under cap, or at capacity unless a confirmed limit is provided. Final packaged checks passed with `contains_raw_memory=False`, `maxed_out_wording=False`, and the packaged backend/embedded app backend both passing MCP stdio smoke.
- 2026-05-08: Started final production-readiness pass. Local build and publish scripts now clean stale `electron/dist` artifacts before packaging; Electron release notes are wired into `electron-builder` so auto-update users see concise "What's New" copy; the packaged app, bundled Python backend, and generated MCPB all rebuilt successfully with the `beforePack` MCP smoke guard enabled.
- 2026-05-08: Fixed packaged Claude detection in Settings. `MCP Relay` now recognizes Claude Desktop MCPB extension settings, not only direct `claude_desktop_config.json` entries, so users who install the MCPB see `CLAUDE DESKTOP INSTALLED` and `RELAY READY` in the production app. Live packaged-app health check returned `MCP server responded with 10 tools`.
- 2026-05-08: Tightened Advisor military prose after live Claude validation. Answer-ready tool text no longer exposes ambiguous `fleet usage` or `naval usage` values when the capacity limit is unconfirmed; raw capacity data remains available in structured MCP payloads, while user-facing content says the naval capacity limit is not confirmed and forbids over/under/at-cap claims without a confirmed limit.
- 2026-05-08: Final validation after rebuild passed. Checks: focused MCP/database/API pytest suite, ruff, Python compile, shell syntax, Node syntax, `./scripts/build-all.sh`, CI smoke, backend build metadata verify, stdio smoke against both `dist-python` and embedded packaged app backend, MCPB archive inspection, and `latest-mac.yml` release-notes verification. Live Claude Desktop was relaunched so its MCPB extension started the fresh packaged backend; a natural-language campaign query used the packaged tools and produced concrete Advisor guidance without raw IDs or unconfirmed naval-capacity claims.
- 2026-05-05: Started implementation pass for steps 9 and 15: make `Advisor Briefing` generous by default, then add branded MCP initialization metadata, tool titles, stronger descriptions, and output schemas.
- 2026-05-05: Completed step 9. `get_strategy_context` now returns a rich Advisor Briefing by default, with focus-prioritized section ordering and a focused fallback only when the briefing payload exceeds the local ceiling.
- 2026-05-05: Completed step 15. MCP initialization now includes branded `serverInfo` and server instructions; all tools now include display titles, icons, stronger descriptions, read-only/idempotent annotations, and `outputSchema` definitions.
- 2026-05-05: Verification: `python3 -m py_compile backend/mcp/context.py backend/mcp/server.py tests/test_mcp_context.py`, `python3 -m pytest tests/test_mcp_context.py -q`, and `python3 -m ruff check backend/mcp tests/test_mcp_context.py` all passed. A real local DB smoke returned `briefing_mode=rich` with broad sections for an economy question.
- 2026-05-05: Broader regression check passed: `python3 -m pytest tests/test_mcp_context.py tests/test_database_event_ranges.py tests/test_api_sessions.py -q`.
- 2026-05-05: Added compact prompt-contract guidance to tool results: `response_guidance` for Advisor Briefing, `archive_guidance` for Chronicle Archive, and `chronicle_guidance` for Chronicle Source Material. Baseline comparison against `/tmp/stellaris-mcp-before-guidance.json` showed only one new top-level key per affected tool. Real local DB payload deltas: Advisor Briefing `+1707` chars, Chronicle Archive `+590` chars, Chronicle Source Material `+1199` chars.
- 2026-05-05: Ran a natural-language before/after comparison using saved MCP payloads and the same end-user questions for Advisor economy, Advisor war-room, Chronicle current era, and Chronicle archive. Result: Advisor answers became more evidence-led and less prone to naval-capacity misinterpretation; Chronicle answers became more branded and archive-safe, with a follow-up need for completeness regression tests.
- 2026-05-05: Earlier experimental Chronicle current-era write-back proved the basic save/read-back loop against `/tmp/stellaris-mcp-writeback-test.db`. This has now been superseded by the first-class always-discoverable Chronicle save/edit/create/undo tools above.

## Implementation Steps

1. Add a context service that can resolve the active save/session and fetch compact briefing/event/Chronicle data. Done.
2. Add unit tests for the context service using existing database/session fixtures. Done.
3. Add a stdio MCP server that exposes the core context tool set. Done.
4. Add packaging support for a `stellaris-companion-mcp` executable or script entrypoint. Done.
5. Add Settings UI copy/config helpers for Claude Desktop, Claude Code, and Codex. Done.
6. Add documentation for local setup and the "no ChatGPT web/Claude.ai remote" limitation.
7. Add smoke tests proving MCP context tools do not call Gemini. Done.
8. Add manual QA with a real save: active campaign, strategy context, recent events, cached chronicle, and chronicle source material. Done.
9. Update `get_strategy_context` so the default Advisor Briefing is rich/generous, with `focus` acting as a ranking hint rather than a strict narrow slice. Done.
10. Add `prompts/list` and `prompts/get` for the Advisor and Chronicle workflows.
11. Add `resources/list`, `resources/templates/list`, and `resources/read` for compact campaign documents.
12. Add Electron Settings copy/install helpers, including a real health check. Done.
13. Add Claude Desktop MCPB packaging for one-click local install. Done.
14. Add golden prompt tests that verify clients are nudged toward the right tool for common user asks.
15. Add branded MCP metadata, server instructions, tool display titles, and tool output schemas. Done.
16. Add first-class Chronicle save/edit/create/undo tools that are only used after explicit user intent. Done.
17. Add Electron Chronicle focus/resume refresh so saved external edits are picked up when the user returns to the app. Done.
18. Install the generated MCPB in Claude Desktop and run a reversible live Advisor plus Chronicle create/undo check through the installed extension. Done.
19. Add advisor persona/presentation guidance, leak-safe writeback payloads, and display-name cleanup for raw Stellaris identifiers. Done.
20. Add production release guardrails for bundled `--mcp` smoke testing and MCPB release packaging. Done.
21. Add backend build metadata, source fingerprint verification, safe build/publish scripts, and electron-builder `beforePack` stale-bundle blocking. Done.
22. Make MCP tool `content` answer-ready for clients that do not fully consume `structuredContent`, then validate with Claude against the packaged app backend. Done.

## Open Questions

- Should the MCP executable connect to the already-running backend, or should it open the SQLite database directly for read-only context?
- Should local MCP be enabled only while the Electron app is running?
- What is the safest default max payload size for late-game saves?
- Should the public connector label stay `Stellaris Companion`, or should the MCPB use a themed label like `Galactic Filing Cabinet`?
- Should MCP resources be listed only when an active campaign exists, or should they always exist and return a friendly "no campaign loaded" payload?
- What payload ceiling should trigger a fallback from rich Advisor Briefing to focused section selection for unusually large late-game saves?
- Should the app show a subtle "edited externally" marker for Chronicle chapters/current era saved from Claude/ChatGPT?

## Recommended V1

Build the stdio MCP server as a thin local wrapper over existing backend/database context, then expose these context tools:

- `get_active_campaign`
- `get_strategy_context`
- `get_recent_events`
- `get_empire_briefing`
- `get_cached_chronicle`
- `get_chronicle_source_material`

Keep `get_empire_briefing` compact by default because full late-game briefing payloads can become too large for comfortable MCP use.

Expose these Chronicle save/edit tools as normal capabilities, with strict descriptions that prevent automatic saving while the user is still drafting:

- `save_chronicle_current_era`
- `update_chronicle_chapter`
- `create_chronicle_chapter`
- `undo_chronicle_edit`

Recommended next implementation order:

1. Add golden prompt tests and manual QA scripts for natural-language draft, revise, save, create, and undo flows.
2. Consider MCP prompts/resources only if clients expose them in a way that makes the user experience clearer.
3. Consider an optional in-app marker for externally edited Chronicle content if users need clearer provenance.

## Source Links

- [MCP 2025-11-25 changelog](https://modelcontextprotocol.io/specification/2025-11-25/changelog)
- [MCP lifecycle and server instructions](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle)
- [MCP tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
- [MCP prompts](https://modelcontextprotocol.io/specification/2025-11-25/server/prompts)
- [MCP resources](https://modelcontextprotocol.io/specification/2025-11-25/server/resources)
- [2026 MCP roadmap](https://blog.modelcontextprotocol.io/posts/2026-mcp-roadmap/)
- [Claude MCPB desktop extensions](https://claude.com/docs/connectors/building/mcpb)
- [Claude MCP setup guide](https://docs.claude.com/en/docs/claude-code/mcp)
- [OpenAI Apps SDK metadata guidance](https://developers.openai.com/apps-sdk/guides/optimize-metadata)
- [OpenAI Apps SDK UX principles](https://developers.openai.com/apps-sdk/concepts/ux-principles)
