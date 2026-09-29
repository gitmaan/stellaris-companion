"""Tests for the local read-only MCP context/server."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pytest
from mcp import Client

from backend.core.database import GameDatabase
from backend.core.json_utils import json_dumps
from backend.mcp.context import McpContextError, StellarisMcpContext
from backend.mcp.server import SERVER_INSTRUCTIONS, StellarisMcpServer, build_tool_definitions

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


def test_recent_events_filters_notable_types_before_display_names(tmp_path: Path) -> None:
    db, _, _ = _make_test_db(tmp_path)
    context = StellarisMcpContext(db=db)

    payload = context.get_recent_events(notable_only=True)

    assert [event["event_type"] for event in payload["events"]] == [
        "Colony Count Change",
        "War Started",
    ]


def test_chronicle_edit_tools_update_create_and_undo(tmp_path: Path) -> None:
    db, _, _ = _make_test_db(tmp_path)
    context = StellarisMcpContext(db=db)

    guard = context.get_cached_chronicle()
    current_era = context.save_chronicle_current_era(
        campaign_ref=guard["campaign_ref"],
        expected_revision=guard["chronicle_revision"],
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
        campaign_ref=current_era["campaign_ref"],
        expected_revision=current_era["chronicle_revision"],
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
        campaign_ref=updated["campaign_ref"],
        expected_revision=updated["chronicle_revision"],
        title="The Second Ledger",
        narrative="A second chapter was imported after careful review in chat.",
        summary="A second externally written chapter.",
    )
    assert created["chapter"]["number"] == 2
    cached = context.get_cached_chronicle()
    assert len(cached["chapters"]) == 2
    assert cached["chapters"][1]["title"] == "The Second Ledger"
    assert "second chapter was imported" in cached["chronicle"]

    undone = context.undo_chronicle_edit(
        campaign_ref=created["campaign_ref"],
        expected_revision=created["chronicle_revision"],
        edit_receipt=created["edit_receipt"],
    )
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

    tools = build_tool_definitions()
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
    assert save_tool["inputSchema"]["required"] == [
        "campaign_ref",
        "expected_revision",
        "narrative",
    ]
    assert len(SERVER_INSTRUCTIONS) > 512
    assert SERVER_INSTRUCTIONS[:512].count(".") >= 5

    called = server.call_tool("get_active_campaign")
    assert called["isError"] is False
    structured = called["structuredContent"]
    assert structured["empire_name"] == "Kilik Cooperative"

    text_payload = called["content"][0]["text"]
    assert "Campaign Status loaded" in text_payload
    assert "Kilik Cooperative" in text_payload

    strategy = server.call_tool(
        "get_strategy_context", {"question": "What should I focus on next?"}
    )
    strategy_text = strategy["content"][0]["text"]
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

    guard = context.get_cached_chronicle()
    saved = server.call_tool(
        "save_chronicle_current_era",
        {
            "campaign_ref": guard["campaign_ref"],
            "expected_revision": guard["chronicle_revision"],
            "narrative": "The current era was saved from chat.",
        },
    )
    assert saved["isError"] is False
    assert saved["structuredContent"]["saved"] is True
    assert "Saved current-era Chronicle draft" in saved["content"][0]["text"]
    _assert_no_internal_leaks(saved)

    saved_payload = saved["structuredContent"]
    updated = server.call_tool(
        "update_chronicle_chapter",
        {
            "campaign_ref": saved_payload["campaign_ref"],
            "expected_revision": saved_payload["chronicle_revision"],
            "chapter_number": 1,
            "title": "A Chapter Saved From Chat",
            "narrative": "The imported Chronicle now stands in the app archive.",
        },
    )
    assert updated["isError"] is False
    assert updated["structuredContent"]["chapter"]["title"] == "A Chapter Saved From Chat"
    _assert_no_internal_leaks(updated)

    updated_payload = updated["structuredContent"]
    created = server.call_tool(
        "create_chronicle_chapter",
        {
            "campaign_ref": updated_payload["campaign_ref"],
            "expected_revision": updated_payload["chronicle_revision"],
            "title": "A New Saved Chapter",
            "narrative": "A newly written chapter has been sent back to the archive.",
        },
    )
    assert created["isError"] is False
    assert created["structuredContent"]["chapter"]["number"] == 2
    assert created["structuredContent"]["saved_item"]["chapter_number"] == 2
    _assert_no_internal_leaks(created)

    created_payload = created["structuredContent"]
    undone = server.call_tool(
        "undo_chronicle_edit",
        {
            "campaign_ref": created_payload["campaign_ref"],
            "expected_revision": created_payload["chronicle_revision"],
            "edit_receipt": created_payload["edit_receipt"],
        },
    )
    assert undone["isError"] is False
    assert undone["structuredContent"]["message"] == (
        "Undid the most recent Chronicle edit for Chapter 2."
    )
    _assert_no_internal_leaks(undone)


def test_chronicle_write_rejects_stale_revision_and_wrong_receipt(tmp_path: Path) -> None:
    db, _, _ = _make_test_db(tmp_path)
    context = StellarisMcpContext(db=db)
    guard = context.get_cached_chronicle()

    saved = context.save_chronicle_current_era(
        campaign_ref=guard["campaign_ref"],
        expected_revision=guard["chronicle_revision"],
        narrative="A guarded Chronicle draft.",
    )

    with pytest.raises(McpContextError, match="Chronicle changed"):
        context.save_chronicle_current_era(
            campaign_ref=guard["campaign_ref"],
            expected_revision=guard["chronicle_revision"],
            narrative="A stale competing draft.",
        )

    with pytest.raises(McpContextError, match="active campaign changed"):
        context.save_chronicle_current_era(
            campaign_ref="campaign_wrong",
            expected_revision=saved["chronicle_revision"],
            narrative="A draft for the wrong campaign.",
        )

    with pytest.raises(McpContextError, match="receipt"):
        context.undo_chronicle_edit(
            campaign_ref=saved["campaign_ref"],
            expected_revision=saved["chronicle_revision"],
            edit_receipt="edit_not-the-right-receipt",
        )


def test_chronicle_revision_guard_holds_across_database_connections(tmp_path: Path) -> None:
    db, _, _ = _make_test_db(tmp_path)
    first = StellarisMcpContext(db=db)
    second_db = GameDatabase(db_path=db.path)
    second = StellarisMcpContext(db=second_db)
    guard = second.get_cached_chronicle()

    first.save_chronicle_current_era(
        campaign_ref=guard["campaign_ref"],
        expected_revision=guard["chronicle_revision"],
        narrative="The winning concurrent Chronicle draft.",
    )

    with pytest.raises(McpContextError, match="Chronicle changed"):
        second.save_chronicle_current_era(
            campaign_ref=guard["campaign_ref"],
            expected_revision=guard["chronicle_revision"],
            narrative="The stale concurrent Chronicle draft.",
        )

    second_db.close()


def test_official_sdk_exposes_tools_resources_and_prompts(tmp_path: Path) -> None:
    db, _, _ = _make_test_db(tmp_path)
    context = StellarisMcpContext(db=db)
    server = StellarisMcpServer(context)

    async def exercise_server() -> None:
        async with Client(server.sdk_server) as client:
            assert client.server_info is not None
            assert client.server_info.title == "Stellaris Companion"
            assert client.instructions == SERVER_INSTRUCTIONS

            tools = await client.list_tools()
            assert {tool.name for tool in tools.tools} == set(server.tools)

            resources = await client.list_resources()
            assert {str(resource.uri) for resource in resources.resources} == {
                "stellaris://campaign/active",
                "stellaris://campaign/briefing",
                "stellaris://campaign/events/recent",
                "stellaris://campaign/chronicle",
            }
            active = await client.read_resource("stellaris://campaign/active")
            assert "Kilik Cooperative" in active.contents[0].text

            prompts = await client.list_prompts()
            assert {prompt.name for prompt in prompts.prompts} == {
                "stellaris-advisor",
                "chronicle-current-era",
                "campaign-recap",
            }
            prompt = await client.get_prompt(
                "stellaris-advisor", {"question": "What should I prioritize?"}
            )
            assert "get_strategy_context" in prompt.messages[0].content.text

    asyncio.run(exercise_server())
