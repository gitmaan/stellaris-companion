"""Tests for the local read-only MCP context/server."""

from __future__ import annotations

import json
import re
from pathlib import Path

from backend.core.database import GameDatabase
from backend.core.json_utils import json_dumps
from backend.mcp.context import StellarisMcpContext
from backend.mcp.server import StellarisMcpServer

LEAK_PATTERN = re.compile(
    r"(tech_[a-z0-9_]+|chronicle\.[a-z0-9_.-]+|mcp_writeback|create_chapter|update_chapter|save_current_era)"
)


def _assert_no_internal_leaks(value: object) -> None:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    assert not LEAK_PATTERN.search(text)


def _make_test_db(tmp_path: Path) -> tuple[GameDatabase, str, list[int]]:
    db = GameDatabase(db_path=tmp_path / "mcp.db")
    session_id = db.get_or_create_active_session(
        save_id="save-mcp",
        save_path="/tmp/test-save.sav",
        empire_name="Kilik Cooperative",
        last_game_date="2235.04.01",
    )

    briefing = {
        "meta": {
            "date": "2235.04.01",
            "version": "Corvus v4.2.4",
            "campaign_id": "campaign-1",
        },
        "identity": {
            "name": "Kilik Cooperative",
            "ethics": ["fanatic_xenophile", "egalitarian"],
            "civics": ["free_haven"],
        },
        "situation": {
            "game_phase": "mid_early",
            "at_war": True,
            "war_count": 1,
            "economy": {
                "energy_net": -12,
                "minerals_net": 40,
                "alloys_net": 18,
            },
        },
        "economy": {
            "key_resources": {
                "energy": -12,
                "minerals": 40,
                "alloys": 18,
                "consumer_goods": 5,
            },
            "net_monthly": {
                "energy": -12,
                "minerals": 40,
                "alloys": 18,
                "consumer_goods": 5,
            },
        },
        "military": {
            "military_power": 4200,
            "military_fleets": 3,
            "naval_capacity": {"used": 72, "analysis": {"limit": 88, "status": "below"}},
        },
        "diplomacy": {"relation_count": 5, "allies": ["Yondarim Union"]},
        "territory": {"colonies": {"total_count": 6}},
        "technology": {
            "research": {"physics": 120, "society": 115, "engineering": 130},
            "recommended_research": [
                "tech_doctrine_fleet_size_1",
                "tech_automated_exploration",
                "tech_mass_drivers_2",
            ],
        },
        "endgame": {"crisis": {"crisis_active": False}},
    }
    db.update_session_latest_briefing(
        session_id=session_id,
        latest_briefing_json=json_dumps(briefing),
        last_game_date="2235.04.01",
    )

    snapshot_ids: list[int] = []
    for idx, game_date in enumerate(("2230.01.01", "2235.04.01"), start=1):
        snapshot_ids.append(
            db.insert_snapshot(
                session_id=session_id,
                game_date=game_date,
                save_hash=f"hash-{idx}",
                military_power=3000 + idx,
                colony_count=5 + idx,
                wars_count=1,
                energy_net=-12,
                alloys_net=18,
                full_briefing_json=json_dumps(briefing),
                event_state_json=json_dumps(briefing),
            )
        )

    db.insert_events(
        session_id=session_id,
        captured_at=100,
        game_date="2233.02.01",
        events=[
            {
                "event_type": "war_started",
                "summary": "The Kilik Cooperative entered the Entente War.",
                "data": {
                    "from_snapshot_id": snapshot_ids[0],
                    "to_snapshot_id": snapshot_ids[1],
                },
            },
            {
                "event_type": "colony_count_change",
                "summary": "A sixth colony was founded.",
                "data": {"to_snapshot_id": snapshot_ids[1]},
            },
        ],
    )

    chapters_json = {
        "format_version": 1,
        "chapters": [
            {
                "number": 1,
                "title": "First Light Beyond the Rim",
                "start_date": "2230.01.01",
                "end_date": "2235.04.01",
                "start_snapshot_id": snapshot_ids[0],
                "end_snapshot_id": snapshot_ids[1],
                "summary": "Expansion and first war shaped the young cooperative.",
                "narrative": "The first chapter opened with bright colonies and ended under war banners.",
                "is_finalized": True,
            }
        ],
        "current_era_start_date": "2235.04.01",
        "current_era_start_snapshot_id": snapshot_ids[1],
        "current_era_cache": {
            "start_date": "2235.04.01",
            "start_snapshot_id": snapshot_ids[1],
            "current_era": {
                "title": "The Wartime Balance",
                "start_date": "2235.04.01",
                "narrative": "The current era balances deficit spending against wartime necessity.",
                "events_covered": 0,
            },
        },
    }
    db.upsert_chronicle_by_save_id(
        save_id="save-mcp",
        session_id=session_id,
        chronicle_text="### CHAPTER 1\nThe first chapter opened...",
        chapters_json=json_dumps(chapters_json),
        event_count=2,
        snapshot_count=2,
        language="en",
    )
    db.update_session_advisor_custom(
        session_id=session_id,
        text="Prefer concise recommendations with concrete trade-offs.",
    )
    db.upsert_advisor_memory_summary(
        save_id="save-mcp",
        summary_text="The player has been prioritizing defensive diplomacy.",
        last_game_date="2235.04.01",
    )
    return db, session_id, snapshot_ids


def test_mcp_context_returns_active_campaign(tmp_path: Path) -> None:
    db, _, _ = _make_test_db(tmp_path)
    context = StellarisMcpContext(db=db)

    payload = context.get_active_campaign()

    assert payload["save_loaded"] is True
    assert payload["empire_name"] == "Kilik Cooperative"
    assert payload["game_date"] == "2235.04.01"
    assert payload["snapshot_count"] == 2


def test_strategy_context_is_read_only_and_does_not_require_gemini(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    db, _, _ = _make_test_db(tmp_path)
    context = StellarisMcpContext(db=db)

    payload = context.get_strategy_context(question="What should I fix in my economy?")

    assert payload["focus"] == "economy"
    assert payload["briefing_mode"] == "rich"
    assert payload["privacy"]["write_back_enabled"] is False
    assert payload["briefing"]["economy"]["key_resources"]["energy"] == -12
    assert payload["briefing"]["military"]["military_power"] == 4200
    assert payload["briefing"]["diplomacy"]["relation_count"] == 5
    assert payload["briefing_size_chars"] > 0
    guidance = payload["response_guidance"]
    assert guidance["role"] == "strategic_advisor"
    assert guidance["advisor_voice"]["persona"] == "Strategic advisor to Kilik Cooperative"
    assert guidance["presentation_contract"]["surface"] == "natural_chat"
    assert guidance["facts_policy"]["exact_numbers_only"] is True
    assert guidance["naval_capacity_policy"]["current_usage_path"]
    assert guidance["tool_use_policy"]["main_tool"] == (
        "Advisor Briefing is the preferred context for strategy questions."
    )
    assert "raw_save_file_included" in payload["privacy"]
    assert payload["advisor_custom_instructions"]
    assert payload["advisor_memory"]
    assert payload["briefing"]["technology"]["recommended_research"] == [
        "Fleet Doctrines",
        "Automated Exploration Protocols",
        "Coilguns",
    ]
    _assert_no_internal_leaks(payload)


def test_cached_chronicle_reads_cache_without_generation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    db, _, _ = _make_test_db(tmp_path)
    context = StellarisMcpContext(db=db)

    payload = context.get_cached_chronicle()

    assert payload["cached"] is True
    assert payload["chapters"][0]["title"] == "First Light Beyond the Rim"
    assert payload["current_era"]["title"] == "The Wartime Balance"
    assert payload["archive_guidance"]["role"] == "archive_reader"
    assert payload["archive_guidance"]["do_not_fabricate_missing_chapters"] is True


def test_chronicle_source_material_uses_chapter_event_range(tmp_path: Path) -> None:
    db, _, _ = _make_test_db(tmp_path)
    context = StellarisMcpContext(db=db)

    payload = context.get_chronicle_source_material(scope="chapter", chapter_number=1)

    assert payload["event_range"]["chapter_number"] == 1
    assert [event["event_type"] for event in payload["events"]] == [
        "War Started",
        "Colony Count Change",
    ]
    assert payload["chronicle_guidance"]["role"] == "royal_chronicler"
    assert payload["chronicle_guidance"]["do_not_fabricate_events"] is True
    assert payload["chronicle_guidance"]["not_an_advisor"] is True
    assert payload["write_back_enabled"] is True
    assert payload["save_affordance"]["do_not_save_without_explicit_request"] is True


def test_chronicle_edit_tools_update_create_and_undo(tmp_path: Path) -> None:
    db, _, _ = _make_test_db(tmp_path)
    context = StellarisMcpContext(db=db)

    current_era = context.save_chronicle_current_era(
        narrative="The Kilik archives record a newly imported current era.",
        title="Imported Current Era",
    )

    assert current_era["saved"] is True
    assert current_era["write_back_enabled"] is True
    assert current_era["message"] == (
        'Saved current-era Chronicle draft "Imported Current Era" to Stellaris Companion.'
    )
    assert current_era["saved_item"]["kind"] == "current_era"
    _assert_no_internal_leaks(current_era)

    cached = context.get_cached_chronicle()
    assert cached["current_era"]["title"] == "Imported Current Era"
    assert "newly imported current era" in cached["current_era"]["narrative"]
    assert "newly imported current era" in cached["chronicle"]

    updated = context.update_chronicle_chapter(
        chapter_number=1,
        title="First Light Revised",
        narrative="The revised first chapter now speaks with cooler precision.",
        summary="A revised opening chapter.",
    )
    assert updated["saved"] is True
    cached = context.get_cached_chronicle()
    assert cached["chapters"][0]["title"] == "First Light Revised"
    assert "cooler precision" in cached["chapters"][0]["narrative"]

    created = context.create_chronicle_chapter(
        title="The Second Ledger",
        narrative="A second chapter was imported after careful review in chat.",
        summary="A second externally written chapter.",
    )
    assert created["chapter"]["number"] == 2
    cached = context.get_cached_chronicle()
    assert len(cached["chapters"]) == 2
    assert cached["chapters"][1]["title"] == "The Second Ledger"
    assert "second chapter was imported" in cached["chronicle"]

    undone = context.undo_chronicle_edit()
    assert undone["undone"] is True
    assert undone["message"] == "Undid the most recent Chronicle edit for Chapter 2."
    _assert_no_internal_leaks(undone)
    cached = context.get_cached_chronicle()
    assert len(cached["chapters"]) == 1
    assert cached["chapters"][0]["title"] == "First Light Revised"


def test_mcp_server_lists_and_calls_tools(tmp_path: Path) -> None:
    db, _, _ = _make_test_db(tmp_path)
    context = StellarisMcpContext(db=db)
    server = StellarisMcpServer(context)

    initialized = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {"protocolVersion": "2025-11-25"},
        }
    )
    assert initialized is not None
    assert initialized["result"]["serverInfo"]["title"] == "Stellaris Companion"
    assert initialized["result"]["serverInfo"]["description"]
    assert initialized["result"]["instructions"]

    listed = server.handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert listed is not None
    tools = listed["result"]["tools"]
    tool_names = {tool["name"] for tool in tools}
    assert "get_strategy_context" in tool_names
    assert "get_cached_chronicle" in tool_names
    assert "save_chronicle_current_era" in tool_names
    assert "update_chronicle_chapter" in tool_names
    assert "create_chronicle_chapter" in tool_names
    assert "undo_chronicle_edit" in tool_names
    assert all(tool.get("title") for tool in tools)
    assert all(tool.get("outputSchema", {}).get("type") == "object" for tool in tools)

    strategy_tool = next(tool for tool in tools if tool["name"] == "get_strategy_context")
    assert strategy_tool["title"] == "Advisor Briefing"
    assert strategy_tool["annotations"]["readOnlyHint"] is True
    assert "response_guidance" in strategy_tool["outputSchema"]["properties"]

    archive_tool = next(tool for tool in tools if tool["name"] == "get_cached_chronicle")
    assert "archive_guidance" in archive_tool["outputSchema"]["properties"]

    source_tool = next(tool for tool in tools if tool["name"] == "get_chronicle_source_material")
    assert "chronicle_guidance" in source_tool["outputSchema"]["properties"]

    save_tool = next(tool for tool in tools if tool["name"] == "save_chronicle_current_era")
    assert save_tool["annotations"]["readOnlyHint"] is False
    assert save_tool["annotations"]["destructiveHint"] is True
    assert "explicitly asks" in save_tool["description"]

    called = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "get_active_campaign",
                "arguments": {},
            },
        }
    )
    assert called is not None
    assert called["result"]["isError"] is False
    structured = called["result"]["structuredContent"]
    assert structured["empire_name"] == "Kilik Cooperative"

    text_payload = called["result"]["content"][0]["text"]
    assert "Campaign Status loaded" in text_payload
    assert "Kilik Cooperative" in text_payload

    strategy = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "get_strategy_context",
                "arguments": {"question": "What should I focus on next?"},
            },
        }
    )
    assert strategy is not None
    strategy_text = strategy["result"]["content"][0]["text"]
    assert "Advisor Briefing for Kilik Cooperative" in strategy_text
    assert "answer from it directly" in strategy_text
    assert "Energy -12/mo" in strategy_text
    assert "capacity limit not confirmed" in strategy_text
    assert "do not claim over cap" in strategy_text
    assert "naval usage" not in strategy_text
    assert "fleet usage" not in strategy_text
    assert "maxed out" not in strategy_text
    assert "Fleet Doctrines" in strategy_text
    _assert_no_internal_leaks(strategy_text)


def test_mcp_server_chronicle_save_update_create_and_undo(tmp_path: Path) -> None:
    db, _, _ = _make_test_db(tmp_path)
    context = StellarisMcpContext(db=db)
    server = StellarisMcpServer(context)

    saved = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "save_chronicle_current_era",
                "arguments": {"narrative": "The current era was saved from chat."},
            },
        }
    )
    assert saved is not None
    assert saved["result"]["isError"] is False
    assert saved["result"]["structuredContent"]["saved"] is True
    assert "Saved current-era Chronicle draft" in saved["result"]["content"][0]["text"]
    _assert_no_internal_leaks(saved["result"])

    updated = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "update_chronicle_chapter",
                "arguments": {
                    "chapter_number": 1,
                    "title": "A Chapter Saved From Chat",
                    "narrative": "The imported Chronicle now stands in the app archive.",
                },
            },
        }
    )
    assert updated is not None
    assert updated["result"]["isError"] is False
    assert updated["result"]["structuredContent"]["chapter"]["title"] == "A Chapter Saved From Chat"
    _assert_no_internal_leaks(updated["result"])

    created = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "create_chronicle_chapter",
                "arguments": {
                    "title": "A New Saved Chapter",
                    "narrative": "A newly written chapter has been sent back to the archive.",
                },
            },
        }
    )
    assert created is not None
    assert created["result"]["isError"] is False
    assert created["result"]["structuredContent"]["chapter"]["number"] == 2
    assert created["result"]["structuredContent"]["saved_item"]["chapter_number"] == 2
    _assert_no_internal_leaks(created["result"])

    undone = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "undo_chronicle_edit", "arguments": {}},
        }
    )
    assert undone is not None
    assert undone["result"]["isError"] is False
    assert undone["result"]["structuredContent"]["message"] == (
        "Undid the most recent Chronicle edit for Chapter 2."
    )
    _assert_no_internal_leaks(undone["result"])
