"""Contract checks for MCP packaging and localized setup UI metadata."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from backend.mcp.server import (
    SERVER_INSTRUCTIONS,
    build_prompt_definitions,
    build_resource_definitions,
    build_tool_definitions,
)

ROOT = Path(__file__).resolve().parents[1]


def test_manifest_tool_catalog_matches_live_server() -> None:
    manifest = json.loads(
        (ROOT / "mcpb" / "stellaris-companion" / "manifest.json").read_text(encoding="utf-8")
    )
    manifest_names = {item["name"] for item in manifest["tools"]}
    server_names = {item["name"] for item in build_tool_definitions()}

    assert manifest_names == server_names
    assert len(build_resource_definitions()) == 4
    assert len(build_prompt_definitions()) == 3


def test_server_instruction_prefix_is_self_contained() -> None:
    prefix = SERVER_INSTRUCTIONS[:512].rstrip()

    assert len(SERVER_INSTRUCTIONS) > 512
    assert prefix.endswith(".")
    assert "Advisor Briefing" in prefix
    assert "never save automatically" in prefix
    assert "campaign_ref" in prefix


def test_every_locale_has_guided_mcp_setup_copy() -> None:
    required = {
        "chooseApp",
        "chooseCampaign",
        "campaignReady",
        "noCampaign",
        "checkFailed",
        "addTo",
        "setupAdded",
        "updateSetup",
        "startChatting",
        "disconnect",
        "copyDiagnostics",
        "disconnectConfirm",
        "advanced",
        "questions",
        "clients",
    }
    locale_root = ROOT / "electron" / "renderer" / "i18n" / "locales"

    for locale_file in sorted(locale_root.glob("*/common.json")):
        messages = json.loads(locale_file.read_text(encoding="utf-8"))
        settings = messages["settings"]
        assert settings["sections"]["mcpRelay"], locale_file
        assert settings["panels"]["mcpRelay"], locale_file
        relay = settings["mcpRelay"]
        assert required <= set(relay), locale_file
        assert set(relay["clients"]) == {"claude", "codex", "cursor"}, locale_file
        assert set(relay["questions"]) == {"priorities", "economy", "chronicle"}, locale_file


def test_mcpb_wrapper_does_not_forward_the_entire_parent_environment() -> None:
    wrapper = (ROOT / "mcpb" / "stellaris-companion" / "server" / "index.js").read_text(
        encoding="utf-8"
    )

    assert "...process.env" not in wrapper
    assert "STELLARIS_LOG_FILE_NAME" in wrapper
    assert "--settings-path" in wrapper


def test_mcpb_wrapper_relays_a_real_protocol_session(tmp_path: Path) -> None:
    node = shutil.which("node")
    python = ROOT / ".venv" / "bin" / "python"
    if not node or not python.is_file():
        return

    messages = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "mcpb-test", "version": "1"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]
    env = {
        **os.environ,
        "STELLARIS_COMPANION_BACKEND_COMMAND": str(python),
        "STELLARIS_COMPANION_BACKEND_ARGS": json.dumps(["-m", "backend.electron_main"]),
        "STELLARIS_COMPANION_USER_DATA_DIR": str(tmp_path),
        "SHOULD_NOT_REACH_MCP_CHILD": "secret-marker",
    }
    process = subprocess.Popen(
        [node, str(ROOT / "mcpb" / "stellaris-companion" / "server" / "index.js")],
        cwd=ROOT,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    process.stdin.write(json.dumps(messages[0]) + "\n")
    process.stdin.flush()
    initialize_line = process.stdout.readline()
    process.stdin.write("\n".join(json.dumps(message) for message in messages[1:]) + "\n")
    process.stdin.flush()
    process.stdin.close()
    process.stdin = None
    remaining_stdout, stderr = process.communicate(timeout=15)
    stdout = initialize_line + remaining_stdout

    assert process.returncode == 0, stderr
    responses = [json.loads(line) for line in stdout.splitlines() if line.strip()]
    by_id = {response.get("id"): response for response in responses}
    assert by_id[1]["result"]["serverInfo"]["title"] == "Stellaris Companion"
    assert 2 in by_id, (stdout, stderr)
    assert len(by_id[2]["result"]["tools"]) == 10


def test_technology_summary_names_every_research_option() -> None:
    """Issue #104: five options were cut to four, under names made up from their IDs."""
    from backend.mcp.server import _technology_summary

    physics = [
        "tech_cryostasis_1",
        "tech_physics_1",
        "tech_sensors_2",
        "tech_shields_2",
        "tech_space_science_1",
    ]
    summary = _technology_summary({"available_techs": {"physics": physics}}, {}, {})

    assert summary == (
        "Technology: available picks physics: Automated Colony Ships, Quantum Computing, "
        "Gravitic Sensors, Improved Deflectors, Zero-G Laboratories."
    )


def test_summaries_say_when_a_list_is_cut_short() -> None:
    from backend.mcp.server import _capped, _event_lines, _render_value

    assert _capped(["a", "b", "c"], 3) == "a, b, c"
    assert _capped(["a", "b", "c"], 2) == "a, b (+1 more)"
    assert _render_value([str(n) for n in range(10)], depth=0).endswith("7 (+2 more)")
    assert _render_value(["x", {"_truncated_items": 4}], depth=0) == "x, +4 more not shown"
    events = [{"summary": f"Event {n}"} for n in range(12)]
    assert _event_lines(events, heading="Recent")[-1] == (
        "- (+2 more events in the structured result)"
    )
