# Local MCP integration

Stellaris Companion exposes its cached campaign context and Chronicle through a local stdio MCP server. Save ingestion remains managed by the desktop app.

## Setup

Load a campaign, then open **Config → AI APP CONNECTIONS**. Select your client, click **CONNECT**, and restart the client. For other MCP clients, copy the configuration under **SHOW MANUAL MCP SETUP**.

Connection setup preserves unrelated client configuration and backs up JSON files before changing them. Use the connection status and manual health check to diagnose setup problems.

The server reads local campaign data and excludes provider credentials and raw save files from its responses. Your AI client controls how received context is sent to its model provider.

## Chronicle editing

Ask the AI client to draft or revise text, then explicitly request that it save the change. Writes require the campaign reference and current Chronicle revision returned by the read tools. Stale revisions are rejected. The latest external edit can be undone using its returned receipt, provided the Chronicle has not changed since.

## Development and packaging

The server uses the Python MCP SDK in `backend/mcp/`. It provides campaign tools, resources and prompts, plus Chronicle read, write and undo tools. Client setup lives in `electron/main/mcpRelay.js`.

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
