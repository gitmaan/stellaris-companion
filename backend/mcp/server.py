"""Minimal stdio MCP server for local Stellaris Companion integrations."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from backend.mcp.context import McpContextError, StellarisMcpContext, _display_identifier

SERVER_NAME = "stellaris-companion"
SERVER_TITLE = "Stellaris Companion"
SERVER_VERSION = "0.1.0"
PROTOCOL_VERSION = "2025-11-25"
SERVER_DESCRIPTION = (
    "Local Stellaris campaign intelligence and Chronicle editing for external AI assistants."
)
SERVER_WEBSITE_URL = "https://github.com/gitmaan/stellaris-companion"
SERVER_ICON = {
    "src": (
        "data:image/svg+xml;base64,"
        "PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA2NCA2NCI+PHJlY3Qgd2lkdGg9IjY0IiBoZWlnaHQ9IjY0IiByeD0iMTIiIGZpbGw9IiMwNjEwMWYiLz48cGF0aCBkPSJNMTAgMjNoNDR2MjhIMTB6IiBmaWxsPSIjMDBkNGZmIiBmaWxsLW9wYWNpdHk9Ii4xNCIgc3Ryb2tlPSIjMDBkNGZmIiBzdHJva2Utd2lkdGg9IjIiLz48cGF0aCBkPSJNMTAgMjNsOC0xMGgxNmw4IDEwIiBmaWxsPSJub25lIiBzdHJva2U9IiMwMGQ0ZmYiIHN0cm9rZS13aWR0aD0iMiIvPjxjaXJjbGUgY3g9IjMyIiBjeT0iMzQiIHI9IjQiIGZpbGw9IiMwMGQ0ZmYiLz48cGF0aCBkPSJNMjIgNDJsMTAtOCAxMSAxMCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSIjNGZkMWM1IiBzdHJva2Utd2lkdGg9IjIiLz48L3N2Zz4="
    ),
    "mimeType": "image/svg+xml",
    "sizes": ["any"],
}
SERVER_INSTRUCTIONS = (
    "Stellaris Companion provides local context about the user's current "
    "Stellaris campaign. For strategy questions, call Advisor Briefing first; it "
    "returns rich current campaign context, recent events, and advisor memory. Use "
    "Empire Briefing only for follow-up detail or context-budget constraints. Use "
    "Chronicle tools for narrative or campaign-history questions. For Chronicle "
    "drafts and revisions, write in chat first and do not save automatically. After "
    "presenting a Chronicle draft, briefly tell the user they can say "
    '"save this to Stellaris Companion" when ready. Only call Chronicle save, '
    "update, create, or undo tools after the user explicitly asks to save, apply, "
    "send back, create, or undo Chronicle content. Save tools update the local "
    "Chronicle cache shown by the Electron app; they do not edit Stellaris save "
    "files, finalize game state, call Gemini, or change Advisor data. Answer in a "
    "Stellaris Companion voice and keep implementation details hidden: do not show "
    "raw game keys, operation names, database targets, source tags, schemas, or "
    "tool plumbing unless the user explicitly asks for debugging."
)

logger = logging.getLogger(__name__)

MAX_TOOL_TEXT_CHARS = 12_000


ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]


def _read_only_annotations(title: str) -> dict[str, Any]:
    return {
        "title": title,
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }


def _write_annotations(title: str) -> dict[str, Any]:
    return {
        "title": title,
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    }


def _campaign_ref_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "save_loaded": {"type": "boolean"},
            "save_id": {"type": "string"},
            "active_session_id": {"type": "string"},
            "empire_name": {"type": ["string", "null"]},
            "game_date": {"type": ["string", "null"]},
            "first_game_date": {"type": ["string", "null"]},
            "snapshot_count": {"type": "integer"},
            "started_at": {"type": ["string", "number", "null"]},
            "ended_at": {"type": ["string", "number", "null"]},
            "is_active": {"type": "boolean"},
            "version": {"type": ["string", "null"]},
            "language": {"type": "string"},
            "message": {"type": "string"},
        },
        "additionalProperties": True,
    }


def _campaign_output_schema() -> dict[str, Any]:
    return _campaign_ref_schema()


def _privacy_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "raw_save_file_included": {"type": "boolean"},
            "write_back_enabled": {"type": "boolean"},
            "remote_sync_enabled": {"type": "boolean"},
        },
        "additionalProperties": False,
    }


def _event_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "id": {"type": ["integer", "string", "null"]},
            "captured_at": {"type": ["integer", "number", "string", "null"]},
            "game_date": {"type": ["string", "null"]},
            "event_type": {"type": ["string", "null"]},
            "summary": {"type": ["string", "null"]},
            "data": {"type": "object", "additionalProperties": True},
        },
        "additionalProperties": True,
    }


def _strategy_context_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "campaign": _campaign_ref_schema(),
            "question": {"type": "string"},
            "focus": {"type": "string"},
            "advisor_mode": {"type": "string"},
            "briefing_mode": {"type": "string", "enum": ["rich", "focused_fallback"]},
            "briefing": {"type": "object", "additionalProperties": True},
            "briefing_note": {"type": "string"},
            "briefing_size_chars": {"type": "integer"},
            "recent_events": {"type": "array", "items": _event_schema()},
            "advisor_custom_instructions": {"type": ["string", "null"]},
            "advisor_memory": {"type": ["string", "null"]},
            "response_guidance": {"type": "object", "additionalProperties": True},
            "privacy": _privacy_schema(),
        },
        "required": ["campaign", "focus", "briefing_mode", "briefing", "privacy"],
        "additionalProperties": True,
    }


def _recent_events_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "campaign": _campaign_ref_schema(),
            "limit": {"type": "integer"},
            "notable_only": {"type": "boolean"},
            "events": {"type": "array", "items": _event_schema()},
        },
        "required": ["campaign", "limit", "notable_only", "events"],
        "additionalProperties": True,
    }


def _empire_briefing_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "campaign": _campaign_ref_schema(),
            "sections": {"type": "object", "additionalProperties": True},
            "detail": {"type": "string", "enum": ["compact", "full"]},
        },
        "required": ["campaign", "sections", "detail"],
        "additionalProperties": True,
    }


def _chapter_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "number": {"type": ["integer", "null"]},
            "title": {"type": ["string", "null"]},
            "start_date": {"type": ["string", "null"]},
            "end_date": {"type": ["string", "null"]},
            "summary": {"type": ["string", "null"]},
            "narrative": {"type": ["string", "null"]},
            "is_finalized": {"type": "boolean"},
            "context_stale": {"type": "boolean"},
            "start_snapshot_id": {"type": ["integer", "null"]},
            "end_snapshot_id": {"type": ["integer", "null"]},
        },
        "additionalProperties": True,
    }


def _chronicle_archive_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "campaign": _campaign_ref_schema(),
            "cached": {"type": "boolean"},
            "save_id": {"type": "string"},
            "session_id": {"type": "string"},
            "language": {"type": "string"},
            "generated_at": {"type": ["string", "number", "null"]},
            "event_count": {"type": ["integer", "null"]},
            "snapshot_count": {"type": ["integer", "null"]},
            "chapters": {"type": "array", "items": _chapter_schema()},
            "current_era": {"type": ["object", "null"], "additionalProperties": True},
            "chronicle": {"type": "string"},
            "message": {"type": "string"},
            "chronicle_custom_instructions": {"type": ["string", "null"]},
            "archive_guidance": {"type": "object", "additionalProperties": True},
        },
        "required": ["campaign", "cached"],
        "additionalProperties": True,
    }


def _chronicle_source_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "campaign": _campaign_ref_schema(),
            "event_range": {"type": "object", "additionalProperties": True},
            "events": {"type": "array", "items": _event_schema()},
            "truncated": {"type": "boolean"},
            "briefing": {"type": "object", "additionalProperties": True},
            "chronicle_custom_instructions": {"type": ["string", "null"]},
            "chronicle_guidance": {"type": "object", "additionalProperties": True},
            "write_back_enabled": {"type": "boolean"},
        },
        "required": ["campaign", "event_range", "events", "write_back_enabled"],
        "additionalProperties": True,
    }


def _chronicle_writeback_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "campaign": _campaign_ref_schema(),
            "saved": {"type": "boolean"},
            "message": {"type": "string"},
            "saved_item": {"type": "object", "additionalProperties": True},
            "write_back_enabled": {"type": "boolean"},
            "narrative_chars": {"type": "integer"},
            "saved_at": {"type": "string"},
            "current_era": {"type": "object", "additionalProperties": True},
            "chapter": _chapter_schema(),
            "app_visibility": {"type": "string"},
        },
        "required": ["campaign", "saved", "message"],
        "additionalProperties": True,
    }


def _chronicle_undo_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "campaign": _campaign_ref_schema(),
            "undone": {"type": "boolean"},
            "message": {"type": "string"},
            "remaining_undo_count": {"type": "integer"},
            "app_visibility": {"type": "string"},
        },
        "required": ["campaign", "undone", "message"],
        "additionalProperties": True,
    }


def _sections_input_schema() -> dict[str, Any]:
    return {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["prose", "quote", "declaration"]},
                "text": {"type": "string"},
                "attribution": {"type": "string"},
            },
            "required": ["type", "text"],
            "additionalProperties": False,
        },
    }


def build_tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "get_active_campaign",
            "title": "Campaign Status",
            "description": (
                "Use this for a quick read on which local Stellaris campaign is active: "
                "empire name, game date, save/session IDs, snapshot count, and version. "
                "This is a lightweight status check, not the main strategy briefing."
            ),
            "icons": [SERVER_ICON],
            "inputSchema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            "outputSchema": _campaign_output_schema(),
            "annotations": _read_only_annotations("Campaign Status"),
        },
        {
            "name": "get_strategy_context",
            "title": "Advisor Briefing",
            "description": (
                "Use this first for normal strategy questions such as economy, fleets, "
                "diplomacy, expansion, crises, or what to do next. It returns rich "
                "read-only campaign context from the latest local briefing, plus recent "
                "events and advisor memory. It never calls the in-app LLM."
            ),
            "icons": [SERVER_ICON],
            "inputSchema": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The user's strategy question.",
                        "default": "",
                    },
                    "focus": {
                        "type": "string",
                        "enum": [
                            "auto",
                            "general",
                            "economy",
                            "military",
                            "diplomacy",
                            "technology",
                            "territory",
                            "chronicle",
                            "crisis",
                        ],
                        "default": "auto",
                    },
                    "event_limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 120,
                        "default": 15,
                    },
                },
                "additionalProperties": False,
            },
            "outputSchema": _strategy_context_output_schema(),
            "annotations": _read_only_annotations("Advisor Briefing"),
        },
        {
            "name": "get_recent_events",
            "title": "Recent Dispatches",
            "description": (
                "Use this when the user asks what changed recently, wants a timeline, "
                "or needs event evidence. For strategy advice, prefer Advisor Briefing "
                "because it already includes recent events."
            ),
            "icons": [SERVER_ICON],
            "inputSchema": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 120,
                        "default": 25,
                    },
                    "notable_only": {
                        "type": "boolean",
                        "default": False,
                    },
                },
                "additionalProperties": False,
            },
            "outputSchema": _recent_events_output_schema(),
            "annotations": _read_only_annotations("Recent Dispatches"),
        },
        {
            "name": "get_empire_briefing",
            "title": "Empire Briefing",
            "description": (
                "Use this only for follow-up detail on specific briefing sections, "
                "debugging, or tight context budgets. It is a narrower projection of "
                "the same cached local briefing used by Advisor Briefing; it does not "
                "provide extra data beyond the full briefing."
            ),
            "icons": [SERVER_ICON],
            "inputSchema": {
                "type": "object",
                "properties": {
                    "sections": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Briefing sections to return, such as economy, military, diplomacy, territory, technology.",
                    },
                    "max_detail": {
                        "type": "string",
                        "enum": ["compact", "full"],
                        "default": "compact",
                    },
                },
                "additionalProperties": False,
            },
            "outputSchema": _empire_briefing_output_schema(),
            "annotations": _read_only_annotations("Empire Briefing"),
        },
        {
            "name": "get_cached_chronicle",
            "title": "Chronicle Archive",
            "description": (
                "Use this when the user asks to view, summarize, or quote the existing "
                "cached Chronicle. It returns saved Chronicle chapters/current era only "
                "and does not generate new prose."
            ),
            "icons": [SERVER_ICON],
            "inputSchema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            "outputSchema": _chronicle_archive_output_schema(),
            "annotations": _read_only_annotations("Chronicle Archive"),
        },
        {
            "name": "get_chronicle_source_material",
            "title": "Chronicle Source Material",
            "description": (
                "Use this when the user asks an external model to write a new Chronicle "
                "passage in chat. It returns event/source material and style context; "
                "it cannot save the generated prose back into Stellaris Companion."
            ),
            "icons": [SERVER_ICON],
            "inputSchema": {
                "type": "object",
                "properties": {
                    "scope": {
                        "type": "string",
                        "enum": ["current_era", "latest_session", "full_summary", "chapter"],
                        "default": "current_era",
                    },
                    "chapter_number": {
                        "type": ["integer", "null"],
                        "minimum": 1,
                        "default": None,
                    },
                    "max_events": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 250,
                        "default": 80,
                    },
                },
                "additionalProperties": False,
            },
            "outputSchema": _chronicle_source_output_schema(),
            "annotations": _read_only_annotations("Chronicle Source Material"),
        },
        {
            "name": "save_chronicle_current_era",
            "title": "Save Chronicle Current Era",
            "description": (
                "Use only after the user explicitly asks to save, apply, import, "
                "or send the current Chronicle draft back to Stellaris Companion. "
                "Do not call this for drafts, previews, or normal chat revisions. "
                "It replaces the cached current-era draft shown in the Electron "
                "Chronicle page and does not edit the Stellaris save file."
            ),
            "icons": [SERVER_ICON],
            "inputSchema": {
                "type": "object",
                "properties": {
                    "narrative": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 20000,
                        "description": "The Chronicle prose to show as the current-era draft.",
                    },
                    "title": {
                        "type": "string",
                        "description": "Optional title for the current-era draft.",
                        "default": "External Chronicle Draft",
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Optional current-era start date. Defaults to the cached era start.",
                    },
                    "events_covered": {
                        "type": "integer",
                        "minimum": 0,
                        "description": "Optional number of source events covered by the draft.",
                    },
                },
                "required": ["narrative"],
                "additionalProperties": False,
            },
            "outputSchema": _chronicle_writeback_output_schema(),
            "annotations": _write_annotations("Save Chronicle Current Era"),
        },
        {
            "name": "update_chronicle_chapter",
            "title": "Update Chronicle Chapter",
            "description": (
                "Use only after the user explicitly asks to save, apply, or send an "
                "edited existing chapter back to Stellaris Companion. Do not call this "
                "for draft rewrites or back-and-forth revisions in chat."
            ),
            "icons": [SERVER_ICON],
            "inputSchema": {
                "type": "object",
                "properties": {
                    "chapter_number": {"type": "integer", "minimum": 1},
                    "narrative": {"type": "string", "minLength": 1, "maxLength": 20000},
                    "title": {"type": "string"},
                    "summary": {"type": "string", "maxLength": 2000},
                    "epigraph": {"type": "string"},
                    "sections": _sections_input_schema(),
                },
                "required": ["chapter_number", "narrative"],
                "additionalProperties": False,
            },
            "outputSchema": _chronicle_writeback_output_schema(),
            "annotations": _write_annotations("Update Chronicle Chapter"),
        },
        {
            "name": "create_chronicle_chapter",
            "title": "Create Chronicle Chapter",
            "description": (
                "Use only after the user explicitly asks to save a newly written "
                "Chronicle chapter back to Stellaris Companion. Do not call this while "
                "the user is still drafting or revising in chat."
            ),
            "icons": [SERVER_ICON],
            "inputSchema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "minLength": 1},
                    "narrative": {"type": "string", "minLength": 1, "maxLength": 20000},
                    "summary": {"type": "string", "maxLength": 2000},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "start_snapshot_id": {"type": "integer", "minimum": 1},
                    "end_snapshot_id": {"type": "integer", "minimum": 1},
                    "epigraph": {"type": "string"},
                    "sections": _sections_input_schema(),
                },
                "required": ["title", "narrative"],
                "additionalProperties": False,
            },
            "outputSchema": _chronicle_writeback_output_schema(),
            "annotations": _write_annotations("Create Chronicle Chapter"),
        },
        {
            "name": "undo_chronicle_edit",
            "title": "Undo Chronicle Edit",
            "description": (
                "Use only when the user asks to undo or revert the last Chronicle edit "
                "saved through Stellaris Companion's external AI tools."
            ),
            "icons": [SERVER_ICON],
            "inputSchema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            "outputSchema": _chronicle_undo_output_schema(),
            "annotations": _write_annotations("Undo Chronicle Edit"),
        },
    ]


class StellarisMcpServer:
    """Small JSON-RPC MCP stdio server."""

    def __init__(self, context: StellarisMcpContext):
        self.context = context
        self.tools: dict[str, ToolHandler] = {
            "get_active_campaign": lambda args: self.context.get_active_campaign(),
            "get_strategy_context": self._get_strategy_context,
            "get_recent_events": self._get_recent_events,
            "get_empire_briefing": self._get_empire_briefing,
            "get_cached_chronicle": lambda args: self.context.get_cached_chronicle(),
            "get_chronicle_source_material": self._get_chronicle_source_material,
            "save_chronicle_current_era": self._save_chronicle_current_era,
            "update_chronicle_chapter": self._update_chronicle_chapter,
            "create_chronicle_chapter": self._create_chronicle_chapter,
            "undo_chronicle_edit": lambda args: self.context.undo_chronicle_edit(),
        }

    def handle_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        message_id = message.get("id")
        method = message.get("method")
        params = message.get("params") if isinstance(message.get("params"), dict) else {}

        if message_id is None:
            return None

        try:
            if method == "initialize":
                return self._response(message_id, self._initialize_result(params))
            if method == "ping":
                return self._response(message_id, {})
            if method == "tools/list":
                return self._response(message_id, {"tools": build_tool_definitions()})
            if method == "tools/call":
                return self._response(message_id, self._call_tool(params))
            if method == "resources/list":
                return self._response(message_id, {"resources": []})
            if method == "prompts/list":
                return self._response(message_id, {"prompts": []})
            return self._error(message_id, -32601, f"Method not found: {method}")
        except McpContextError as exc:
            return self._response(message_id, _tool_error(str(exc)))
        except Exception as exc:
            logger.exception("MCP request failed")
            return self._error(message_id, -32603, str(exc) or "Internal error")

    def _initialize_result(self, params: dict[str, Any]) -> dict[str, Any]:
        requested_version = params.get("protocolVersion")
        protocol_version = (
            requested_version if isinstance(requested_version, str) else PROTOCOL_VERSION
        )
        return {
            "protocolVersion": protocol_version,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
                "prompts": {"listChanged": False},
            },
            "serverInfo": {
                "name": SERVER_NAME,
                "title": SERVER_TITLE,
                "version": SERVER_VERSION,
                "description": SERVER_DESCRIPTION,
                "icons": [SERVER_ICON],
                "websiteUrl": SERVER_WEBSITE_URL,
            },
            "instructions": SERVER_INSTRUCTIONS,
        }

    def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        raw_args = params.get("arguments")
        args = raw_args if isinstance(raw_args, dict) else {}
        if not isinstance(name, str) or name not in self.tools:
            return _tool_error(f"Unknown tool: {name}")

        result = self.tools[name](args)
        return _tool_result(result)

    def _get_strategy_context(self, args: dict[str, Any]) -> dict[str, Any]:
        return self.context.get_strategy_context(
            question=str(args.get("question") or ""),
            focus=str(args.get("focus") or "auto"),
            event_limit=_int_arg(args.get("event_limit"), default=15),
        )

    def _get_recent_events(self, args: dict[str, Any]) -> dict[str, Any]:
        return self.context.get_recent_events(
            limit=_int_arg(args.get("limit"), default=25),
            notable_only=bool(args.get("notable_only", False)),
        )

    def _get_empire_briefing(self, args: dict[str, Any]) -> dict[str, Any]:
        sections_raw = args.get("sections")
        sections = [str(item) for item in sections_raw] if isinstance(sections_raw, list) else None
        return self.context.get_empire_briefing(
            sections=sections,
            max_detail=str(args.get("max_detail") or "compact"),
        )

    def _get_chronicle_source_material(self, args: dict[str, Any]) -> dict[str, Any]:
        chapter_number = args.get("chapter_number")
        return self.context.get_chronicle_source_material(
            scope=str(args.get("scope") or "current_era"),
            chapter_number=_int_arg(chapter_number, default=0) or None,
            max_events=_int_arg(args.get("max_events"), default=80),
        )

    def _save_chronicle_current_era(self, args: dict[str, Any]) -> dict[str, Any]:
        events_covered = args.get("events_covered")
        return self.context.save_chronicle_current_era(
            narrative=str(args.get("narrative") or ""),
            title=str(args.get("title") or "") or None,
            start_date=str(args.get("start_date") or "") or None,
            events_covered=_int_arg(events_covered, default=-1)
            if events_covered is not None
            else None,
        )

    def _update_chronicle_chapter(self, args: dict[str, Any]) -> dict[str, Any]:
        return self.context.update_chronicle_chapter(
            chapter_number=_int_arg(args.get("chapter_number"), default=0),
            narrative=str(args.get("narrative") or ""),
            title=str(args.get("title") or "") or None,
            summary=str(args.get("summary") or "") if "summary" in args else None,
            epigraph=str(args.get("epigraph") or "") if "epigraph" in args else None,
            sections=_sections_arg(args.get("sections")),
        )

    def _create_chronicle_chapter(self, args: dict[str, Any]) -> dict[str, Any]:
        return self.context.create_chronicle_chapter(
            title=str(args.get("title") or ""),
            narrative=str(args.get("narrative") or ""),
            summary=str(args.get("summary") or "") if "summary" in args else None,
            start_date=str(args.get("start_date") or "") or None,
            end_date=str(args.get("end_date") or "") or None,
            start_snapshot_id=_optional_int_arg(args.get("start_snapshot_id")),
            end_snapshot_id=_optional_int_arg(args.get("end_snapshot_id")),
            epigraph=str(args.get("epigraph") or "") if "epigraph" in args else None,
            sections=_sections_arg(args.get("sections")),
        )

    @staticmethod
    def _response(message_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": message_id, "result": result}

    @staticmethod
    def _error(message_id: Any, code: int, message: str) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": message_id,
            "error": {"code": code, "message": message},
        }


def serve_stdio(context: StellarisMcpContext) -> None:
    server = StellarisMcpServer(context)
    try:
        for line in sys.stdin:
            if not line.strip():
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                _write_message(
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32700, "message": f"Parse error: {exc}"},
                    }
                )
                continue
            if not isinstance(message, dict):
                continue
            response = server.handle_message(message)
            if response is not None:
                _write_message(response)
    finally:
        context.close()


def run_stdio_server(
    *,
    db_path: str | Path | None = None,
    language: str = "en",
) -> None:
    context = StellarisMcpContext(
        db_path=db_path,
        language=language,
    )
    serve_stdio(context)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Stellaris Companion local MCP server.")
    parser.add_argument(
        "--db-path",
        default=None,
        help="Path to the Stellaris Companion history SQLite database. Defaults to STELLARIS_DB_PATH or stellaris_history.db.",
    )
    parser.add_argument(
        "--language",
        default="en",
        help="Language scope for localized cached content, default: en.",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        help="stderr log level, default: WARNING.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.WARNING),
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )
    run_stdio_server(
        db_path=args.db_path,
        language=args.language,
    )


def _write_message(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, separators=(",", ":"), ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _tool_result(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": _tool_result_summary(payload)}],
        "structuredContent": payload,
        "isError": False,
    }


def _tool_error(message: str) -> dict[str, Any]:
    payload = {"error": message}
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        "structuredContent": payload,
        "isError": True,
    }


def _tool_result_summary(payload: dict[str, Any]) -> str:
    campaign = payload.get("campaign") if isinstance(payload.get("campaign"), dict) else {}
    game_date = campaign.get("game_date")

    if "briefing" in payload and "response_guidance" in payload:
        return _truncate_tool_text(_advisor_briefing_text(payload))

    if "sections" in payload:
        return _truncate_tool_text(_empire_briefing_text(payload))

    if "events" in payload:
        if "chronicle_guidance" in payload:
            return _truncate_tool_text(_chronicle_source_text(payload))
        return _truncate_tool_text(_recent_events_text(payload))

    if "chronicle" in payload or "chapters" in payload:
        return _truncate_tool_text(_chronicle_archive_text(payload))

    message = payload.get("message")
    if isinstance(message, str) and message.strip():
        app_visibility = payload.get("app_visibility")
        if isinstance(app_visibility, str) and app_visibility.strip():
            return f"{message.strip()} {app_visibility.strip()}"
        return message.strip()

    if "save_loaded" in payload:
        if payload.get("save_loaded") is False:
            return str(payload.get("message") or "No campaign is available in Stellaris Companion.")
        suffix = f" at {game_date}" if game_date else ""
        return f"Campaign Status loaded: {payload.get('empire_name') or 'active campaign'}{suffix}."

    return "Stellaris Companion returned structured local campaign context."


def _advisor_briefing_text(payload: dict[str, Any]) -> str:
    campaign = payload.get("campaign") if isinstance(payload.get("campaign"), dict) else {}
    briefing = payload.get("briefing") if isinstance(payload.get("briefing"), dict) else {}
    guidance = (
        payload.get("response_guidance")
        if isinstance(payload.get("response_guidance"), dict)
        else {}
    )
    voice = guidance.get("advisor_voice") if isinstance(guidance.get("advisor_voice"), dict) else {}

    empire_name = str(campaign.get("empire_name") or "the active campaign")
    game_date = campaign.get("game_date")
    version = campaign.get("version")
    situation = _dict(briefing.get("situation"))
    economy = _dict(briefing.get("economy"))
    military = _dict(briefing.get("military"))
    territory = _dict(briefing.get("territory"))
    technology = _dict(briefing.get("technology"))
    diplomacy = _dict(briefing.get("diplomacy"))
    fallen = _dict(briefing.get("fallen_empires") or situation.get("fallen_empires"))
    progression = _dict(briefing.get("progression"))
    projects = _dict(briefing.get("projects"))

    lines = [
        f"Advisor Briefing for {empire_name}{f' on {game_date}' if game_date else ''}.",
        (
            "This is the primary Stellaris Companion context for the user's strategy question; "
            "answer from it directly and only call another Stellaris Companion tool for a narrow follow-up."
        ),
    ]
    persona = voice.get("persona")
    voice_rule = voice.get("voice")
    if persona or voice_rule:
        lines.append(
            "Voice: "
            + " ".join(
                str(part) for part in [persona, voice_rule] if isinstance(part, str) and part
            )
        )
    lines.append(
        "Presentation: keep the answer player-facing; do not mention tool names, schemas, raw IDs, "
        "database targets, or implementation details."
    )

    identity_bits = []
    if version:
        identity_bits.append(f"version {version}")
    if situation.get("game_phase"):
        identity_bits.append(f"{_label(situation.get('game_phase'))} phase")
    if situation.get("at_war") is not None:
        identity_bits.append("at war" if situation.get("at_war") else "not at war")
    if situation.get("crisis_active") is not None:
        identity_bits.append(
            "crisis active" if situation.get("crisis_active") else "no active crisis"
        )
    if identity_bits:
        lines.append(f"Campaign state: {', '.join(identity_bits)}.")

    economy_line = _economy_summary(economy or _dict(situation.get("economy")))
    if economy_line:
        lines.append(economy_line)

    military_line = _military_summary(military)
    if military_line:
        lines.append(military_line)

    territory_line = _territory_summary(territory, briefing)
    if territory_line:
        lines.append(territory_line)

    tech_line = _technology_summary(technology, progression, projects)
    if tech_line:
        lines.append(tech_line)

    diplomacy_line = _diplomacy_summary(diplomacy, fallen, situation)
    if diplomacy_line:
        lines.append(diplomacy_line)

    recent_lines = _event_lines(payload.get("recent_events"), heading="Recent campaign events")
    if recent_lines:
        lines.extend(recent_lines)

    advisor_memory = payload.get("advisor_memory")
    if isinstance(advisor_memory, str) and advisor_memory.strip():
        lines.append(
            "Advisor memory is available as prior player preference context only; do not use it "
            "as evidence about the current campaign state."
        )
    custom = payload.get("advisor_custom_instructions")
    if isinstance(custom, str) and custom.strip():
        lines.append(f"Player advisor instructions: {custom.strip()}")

    lines.append(
        "Recommended answer shape: brief diagnosis, exact campaign evidence, top next actions, "
        "then trade-offs or risks to check in-game."
    )
    return "\n".join(lines)


def _empire_briefing_text(payload: dict[str, Any]) -> str:
    campaign = _dict(payload.get("campaign"))
    sections = _dict(payload.get("sections"))
    empire_name = campaign.get("empire_name") or "the active campaign"
    game_date = campaign.get("game_date")
    lines = [
        f"Empire Briefing for {empire_name}{f' on {game_date}' if game_date else ''}.",
        "Use these player-facing section details for follow-up only; avoid raw keys or implementation details.",
    ]
    for name, value in sections.items():
        rendered = _render_value(value, depth=0)
        if rendered:
            lines.append(f"{_label(name)}: {rendered}")
    return "\n".join(lines)


def _recent_events_text(payload: dict[str, Any]) -> str:
    campaign = _dict(payload.get("campaign"))
    empire_name = campaign.get("empire_name") or "the active campaign"
    game_date = campaign.get("game_date")
    lines = [f"Recent Dispatches for {empire_name}{f' on {game_date}' if game_date else ''}."]
    event_lines = _event_lines(payload.get("events"), heading="Events")
    if event_lines:
        lines.extend(event_lines)
    else:
        lines.append("No recent events were available in the local cache.")
    return "\n".join(lines)


def _chronicle_source_text(payload: dict[str, Any]) -> str:
    campaign = _dict(payload.get("campaign"))
    event_range = _dict(payload.get("event_range"))
    guidance = _dict(payload.get("chronicle_guidance"))
    empire_name = campaign.get("empire_name") or "the active campaign"
    lines = [
        f"Chronicle Source Material for {empire_name}.",
        "Write in-universe Chronicle prose in chat first. Do not save anything unless the user explicitly asks.",
    ]
    if guidance.get("voice_guidance"):
        lines.append(f"Voice: {guidance.get('voice_guidance')}")
    scope = event_range.get("scope")
    if scope:
        lines.append(f"Scope: {_label(scope)}.")
    custom = payload.get("chronicle_custom_instructions")
    if isinstance(custom, str) and custom.strip():
        lines.append(f"Player Chronicle instructions: {custom.strip()}")
    event_lines = _event_lines(payload.get("events"), heading="Source events")
    if event_lines:
        lines.extend(event_lines)
    save_affordance = _dict(payload.get("save_affordance"))
    suggested = save_affordance.get("suggested_phrase")
    if isinstance(suggested, str) and suggested.strip():
        lines.append(suggested.strip())
    return "\n".join(lines)


def _chronicle_archive_text(payload: dict[str, Any]) -> str:
    campaign = _dict(payload.get("campaign"))
    empire_name = campaign.get("empire_name") or "the active campaign"
    if payload.get("cached") is False:
        return str(payload.get("message") or "No cached Chronicle is available yet.")
    lines = [f"Chronicle Archive for {empire_name}."]
    chapters = payload.get("chapters") if isinstance(payload.get("chapters"), list) else []
    if chapters:
        lines.append("Saved chapters:")
        for chapter in chapters[:8]:
            if not isinstance(chapter, dict):
                continue
            title = chapter.get("title") or "Untitled"
            number = chapter.get("number")
            dates = " - ".join(
                str(part) for part in [chapter.get("start_date"), chapter.get("end_date")] if part
            )
            summary = chapter.get("summary")
            line = f"- Chapter {number}: {title}"
            if dates:
                line += f" ({dates})"
            if isinstance(summary, str) and summary.strip():
                line += f" - {summary.strip()}"
            lines.append(line)
    current_era = _dict(payload.get("current_era"))
    if current_era:
        start_date = current_era.get("start_date")
        date_suffix = f" from {start_date}" if start_date else ""
        lines.append(f"Current era draft: {current_era.get('title') or 'Untitled'}{date_suffix}.")
    save_affordance = _dict(payload.get("save_affordance"))
    suggested = save_affordance.get("suggested_phrase")
    if isinstance(suggested, str) and suggested.strip():
        lines.append(suggested.strip())
    return "\n".join(lines)


def _economy_summary(economy: dict[str, Any]) -> str:
    net = _dict(economy.get("net_monthly") or economy.get("key_resources") or economy)
    stockpiles = _dict(_dict(economy.get("resources")).get("stockpiles"))
    resources = [
        ("energy", "Energy"),
        ("minerals", "Minerals"),
        ("food", "Food"),
        ("consumer_goods", "Consumer goods"),
        ("alloys", "Alloys"),
        ("unity", "Unity"),
        ("research_total", "Research"),
    ]
    monthly = [
        f"{label} {_signed(net.get(key))}/mo"
        for key, label in resources
        if _is_number(net.get(key))
    ]
    if not monthly:
        return ""
    stock = [
        f"{label} {_number(stockpiles.get(key))}"
        for key, label in resources
        if _is_number(stockpiles.get(key))
    ]
    line = "Economy: " + ", ".join(monthly[:8])
    if stock:
        line += ". Stockpiles: " + ", ".join(stock[:6])
    return line + "."


def _military_summary(military: dict[str, Any]) -> str:
    parts = []
    for key, label in [
        ("military_power", "military power"),
        ("military_ships", "military ships"),
        ("military_fleets", "military fleets"),
    ]:
        if _is_number(military.get(key)):
            parts.append(f"{_number(military.get(key))} {label}")
    fleets = _dict(military.get("fleets"))
    if _is_number(fleets.get("total_military_power")) and not any(
        "military power" in part for part in parts
    ):
        parts.append(f"{_number(fleets.get('total_military_power'))} military power")
    naval = _dict(military.get("naval_capacity"))
    analysis = _dict(naval.get("analysis"))
    if _is_number(naval.get("used")):
        if analysis.get("safe_to_claim_limit") and _is_number(analysis.get("limit")):
            naval_text = (
                f"naval capacity {_number(naval.get('used'))} of {_number(analysis.get('limit'))}"
            )
            status = analysis.get("status")
            if isinstance(status, str) and status:
                naval_text += f" ({_label(status)})"
        else:
            naval_text = "naval capacity limit not confirmed"
        parts.append(naval_text)
    if not analysis.get("safe_to_claim_over_cap"):
        parts.append(
            "do not claim over cap, under cap, or at capacity unless a confirmed capacity limit is provided"
        )
    return "Military: " + ", ".join(parts) + "." if parts else ""


def _territory_summary(territory: dict[str, Any], briefing: dict[str, Any]) -> str:
    parts = []
    starbases = _dict(_dict(_dict(briefing.get("military")).get("fleets")).get("starbases"))
    if _is_number(starbases.get("total_systems")):
        parts.append(f"{_number(starbases.get('total_systems'))} controlled systems")
    colonies = _dict(territory.get("colonies"))
    if _is_number(colonies.get("total_count")):
        parts.append(f"{_number(colonies.get('total_count'))} colonies")
    if _is_number(colonies.get("total_population")):
        parts.append(f"{_number(colonies.get('total_population'))} pops")
    planets = _dict(territory.get("planets"))
    planet_items = planets.get("planets") if isinstance(planets.get("planets"), list) else []
    names = [
        str(item.get("name"))
        for item in planet_items
        if isinstance(item, dict) and item.get("name")
    ]
    if names:
        parts.append("notable worlds: " + ", ".join(names[:4]))
    return "Territory: " + ", ".join(parts) + "." if parts else ""


def _technology_summary(
    technology: dict[str, Any],
    progression: dict[str, Any],
    projects: dict[str, Any],
) -> str:
    parts = []
    speed = _dict(technology.get("research_speed") or technology.get("research"))
    if speed:
        values = [
            f"{_label(key)} {_number(value)}" for key, value in speed.items() if _is_number(value)
        ]
        if values:
            parts.append("research speed " + ", ".join(values[:4]))
    completed = technology.get("completed_count") or progression.get("techs_completed")
    if _is_number(completed):
        parts.append(f"{_number(completed)} completed techs")
    available = _dict(technology.get("available_techs") or projects.get("available_techs"))
    available_parts = []
    for field in ["physics", "society", "engineering"]:
        items = available.get(field)
        if isinstance(items, list) and items:
            available_parts.append(f"{field}: {', '.join(_label(item) for item in items[:4])}")
    recommended = technology.get("recommended_research")
    if isinstance(recommended, list) and recommended:
        available_parts.append(
            "recommended: " + ", ".join(_label(item) for item in recommended[:5])
        )
    if available_parts:
        parts.append("available picks " + "; ".join(available_parts))
    return "Technology: " + ". ".join(parts) + "." if parts else ""


def _diplomacy_summary(
    diplomacy: dict[str, Any],
    fallen: dict[str, Any],
    situation: dict[str, Any],
) -> str:
    parts = []
    contacts = diplomacy.get("relation_count") or situation.get("contact_count")
    if _is_number(contacts):
        parts.append(f"{_number(contacts)} known contacts")
    summary = _dict(diplomacy.get("summary"))
    if _is_number(summary.get("positive")):
        parts.append(f"{_number(summary.get('positive'))} positive relations")
    if _is_number(fallen.get("total_count")) or _is_number(fallen.get("dormant_count")):
        count = (
            fallen.get("total_count")
            if _is_number(fallen.get("total_count"))
            else fallen.get("dormant_count")
        )
        parts.append(f"{_number(count)} fallen empires observed")
    empires = fallen.get("empires") if isinstance(fallen.get("empires"), list) else []
    names = []
    for empire in empires[:4]:
        if isinstance(empire, dict):
            name = empire.get("name")
            archetype = empire.get("archetype")
            if name and archetype:
                names.append(f"{name} ({archetype})")
            elif name:
                names.append(str(name))
    if names:
        parts.append("watch " + ", ".join(names))
    return "Diplomacy: " + ", ".join(parts) + "." if parts else ""


def _event_lines(events_value: Any, *, heading: str) -> list[str]:
    events = events_value if isinstance(events_value, list) else []
    if not events:
        return []
    lines = [f"{heading}:"]
    for event in events[:10]:
        if not isinstance(event, dict):
            continue
        summary = event.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            continue
        date = event.get("game_date")
        kind = event.get("event_type")
        prefix = "- "
        if date:
            prefix += f"{date}: "
        if kind:
            prefix += f"{_label(kind)} - "
        lines.append(prefix + summary.strip())
    return lines


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _render_value(value: Any, *, depth: int) -> str:
    if depth > 2:
        return ""
    if isinstance(value, str):
        return _label(value)
    if isinstance(value, int | float | bool):
        return _number(value) if isinstance(value, int | float) else str(value)
    if isinstance(value, list):
        parts = [_render_value(item, depth=depth + 1) for item in value[:8]]
        return ", ".join(part for part in parts if part)
    if isinstance(value, dict):
        parts = []
        for key, item in list(value.items())[:10]:
            rendered = _render_value(item, depth=depth + 1)
            if rendered:
                parts.append(f"{_label(key)}: {rendered}")
        return "; ".join(parts)
    return ""


def _label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return text
    return _display_identifier(text)


def _signed(value: Any) -> str:
    if not _is_number(value):
        return str(value)
    number = float(value)
    sign = "+" if number > 0 else ""
    return f"{sign}{_number(number)}"


def _number(value: Any) -> str:
    if not _is_number(value):
        return str(value)
    number = float(value)
    if number.is_integer():
        return f"{int(number):,}"
    return f"{number:,.2f}".rstrip("0").rstrip(".")


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _truncate_tool_text(text: str) -> str:
    if len(text) <= MAX_TOOL_TEXT_CHARS:
        return text
    return f"{text[:MAX_TOOL_TEXT_CHARS].rstrip()}\n[Additional local context omitted for brevity.]"


def _int_arg(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _optional_int_arg(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sections_arg(value: Any) -> list[dict[str, Any]] | None:
    if not isinstance(value, list):
        return None
    return [item for item in value if isinstance(item, dict)]


if __name__ == "__main__":
    main()
