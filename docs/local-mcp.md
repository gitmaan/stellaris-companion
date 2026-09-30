# MCP Relay

Connect Claude Desktop, ChatGPT desktop or Cursor to your Stellaris campaign. Ask for strategic advice, help with your economy or a draft for your Chronicle. You chat in the connected app; no API key is needed in Companion. Your AI app's plan and usage limits apply.

## Setup

In onboarding or **Config**, select **Connect your AI app** to open **MCP Relay**.

1. Choose your Stellaris save folder. Companion shows the empire and game date when a campaign is ready.
2. Choose your AI app and select **Add to…**. Existing connections are preserved.
3. Open or restart your AI app, start a new chat and paste a question with **Copy question**. Allow access to Stellaris Companion if prompted.

Try: “Use Stellaris Companion to summarize my empire and suggest my next three priorities.”

Keep Companion open while you play so it can read your latest saves. **Setup added** means the app configuration was saved; **Campaign ready** means Companion has campaign data available. Your first question checks that the AI app can use it.

ChatGPT desktop and Codex on the same computer share the connection. ChatGPT web does not read this local configuration. See [OpenAI's MCP documentation](https://learn.chatgpt.com/docs/extend/mcp).

## Troubleshooting and other apps

Select **Check again** after loading a save or installing your AI app. If setup fails, open the AI app and retry. **Advanced MCP setup** contains manual instructions, configuration to copy and diagnostic details. Other desktop apps must support local MCP servers.

The server reads local campaign data and excludes provider credentials and raw save files from its responses. Your AI client controls how received context is sent to its model provider.

## Chronicle editing

Ask your AI app to draft or revise text. Review the draft, then ask it to save the change to your Chronicle.

## Development and packaging

The local stdio server uses the Python MCP SDK in `backend/mcp/`. It provides cached campaign tools, resources and prompts, plus Chronicle read, write and undo tools. Client setup lives in `electron/main/mcpRelay.js` and backs up JSON configuration before changing it. Save ingestion remains managed by the desktop app.

Chronicle writes require the campaign reference and current revision from the read tools. Stale revisions are rejected. The latest external edit can be undone using its receipt if the Chronicle has not changed since.

From `electron/`, run the integration tests and build the desktop extension:

```sh
npm run test:mcp-relay
npm run build:mcpb
```

After building the backend, verify its MCP handshake from the repository root:

```sh
python scripts/smoke_mcp_stdio.py dist-python/stellaris-backend/stellaris-backend
```

On Windows, use the executable path ending in `.exe`. Packaging checks verify backend freshness and include the MCPB extension in the desktop app.
