# Stellaris Companion MCP Relay

This MCPB package installs a small local Node.js relay for Claude Desktop.
The relay locates the installed Stellaris Companion backend and launches it in
local MCP stdio mode.

Normal users should install the generated `.mcpb` file by double-clicking it or
dragging it into Claude Desktop. They only need to set the app location if
Stellaris Companion is installed somewhere unusual.

The relay reads the local Stellaris Companion SQLite cache and exposes Advisor
and Chronicle tools to Claude. Chronicle write tools save only to the local
Chronicle cache and are designed to be used after explicit user save intent.
