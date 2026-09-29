#!/usr/bin/env python3
"""Smoke-test a Stellaris Companion backend executable as an MCP stdio server."""

from __future__ import annotations

import argparse
import json
import queue
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from backend_build_info import verify as verify_backend_build_info

SCRIPT_DIR = Path(__file__).resolve().parent
EXPECTED_TOOLS = {
    "get_active_campaign",
    "get_strategy_context",
    "get_recent_events",
    "get_empire_briefing",
    "get_cached_chronicle",
    "get_chronicle_source_material",
    "save_chronicle_current_era",
    "update_chronicle_chapter",
    "create_chronicle_chapter",
    "undo_chronicle_edit",
}


def _repo_root() -> Path:
    return SCRIPT_DIR.parent


def _message(message_id: int, method: str, params: dict | None = None) -> str:
    payload: dict[str, object] = {
        "jsonrpc": "2.0",
        "id": message_id,
        "method": method,
    }
    if params is not None:
        payload["params"] = params
    return json.dumps(payload, separators=(",", ":"))


def _notification(method: str, params: dict | None = None) -> str:
    payload: dict[str, object] = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        payload["params"] = params
    return json.dumps(payload, separators=(",", ":"))


def smoke_mcp_stdio(
    executable: Path,
    *,
    timeout: int = 15,
    verify_build_info: bool = True,
) -> None:
    if not executable.is_file():
        raise SystemExit(f"Backend executable not found: {executable}")
    if verify_build_info:
        verify_backend_build_info(executable.parent, root=_repo_root())

    with tempfile.TemporaryDirectory(prefix="stellaris-mcp-smoke-") as tmp:
        db_path = Path(tmp) / "smoke.db"
        proc = subprocess.Popen(
            [
                str(executable),
                "--mcp",
                "--db-path",
                str(db_path),
                "--language",
                "en",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        if proc.stdin is None or proc.stdout is None or proc.stderr is None:
            raise SystemExit("MCP smoke process did not expose stdio pipes.")

        stdout_lines: queue.Queue[str | None] = queue.Queue()
        stderr_lines: list[str] = []

        def read_stdout() -> None:
            assert proc.stdout is not None
            for line in proc.stdout:
                stdout_lines.put(line)
            stdout_lines.put(None)

        def read_stderr() -> None:
            assert proc.stderr is not None
            stderr_lines.extend(proc.stderr.readlines())

        threading.Thread(target=read_stdout, daemon=True).start()
        threading.Thread(target=read_stderr, daemon=True).start()
        deadline = time.monotonic() + timeout

        def send(payload: str) -> None:
            assert proc.stdin is not None
            proc.stdin.write(payload + "\n")
            proc.stdin.flush()

        def receive(message_id: int) -> dict:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(str(executable), timeout)
                try:
                    line = stdout_lines.get(timeout=remaining)
                except queue.Empty as exc:
                    raise subprocess.TimeoutExpired(str(executable), timeout) from exc
                if line is None:
                    stderr = "".join(stderr_lines).strip()
                    raise SystemExit(
                        f"MCP server closed stdout before response {message_id}. stderr:\n{stderr}"
                    )
                try:
                    response = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(response, dict) and response.get("id") == message_id:
                    return response

        try:
            send(
                _message(
                    1,
                    "initialize",
                    {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {"name": "stellaris-mcp-smoke", "version": "1.0.0"},
                    },
                )
            )
            responses = {1: receive(1)}
            send(_notification("notifications/initialized", {}))
            for message_id, method, params in [
                (2, "tools/list", None),
                (3, "resources/list", None),
                (4, "prompts/list", None),
                (5, "tools/call", {"name": "get_active_campaign", "arguments": {}}),
            ]:
                send(_message(message_id, method, params))
                responses[message_id] = receive(message_id)
        finally:
            try:
                proc.stdin.close()
            except OSError:
                pass
            try:
                proc.wait(timeout=max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()

    if proc.returncode != 0:
        stderr = "".join(stderr_lines).strip()
        raise SystemExit(f"MCP smoke process failed (exit {proc.returncode}). stderr:\n{stderr}")

    by_id = responses
    initialized = by_id.get(1, {}).get("result", {})
    if initialized.get("serverInfo", {}).get("title") != "Stellaris Companion":
        raise SystemExit(f"MCP initialize returned unexpected serverInfo: {initialized!r}")

    tools = by_id.get(2, {}).get("result", {}).get("tools", [])
    tool_names = {tool.get("name") for tool in tools if isinstance(tool, dict)}
    missing = sorted(EXPECTED_TOOLS - tool_names)
    if missing:
        raise SystemExit(f"MCP tools/list missing expected tools: {', '.join(missing)}")

    resources = by_id.get(3, {}).get("result", {}).get("resources", [])
    if len(resources) < 4:
        raise SystemExit(f"MCP resources/list returned too few resources: {resources!r}")

    prompts = by_id.get(4, {}).get("result", {}).get("prompts", [])
    if len(prompts) < 3:
        raise SystemExit(f"MCP prompts/list returned too few prompts: {prompts!r}")

    campaign_result = by_id.get(5, {}).get("result", {})
    campaign = campaign_result.get("structuredContent", {})
    if campaign_result.get("isError") or campaign.get("save_loaded") is not False:
        raise SystemExit(f"MCP Campaign Status was not callable: {campaign_result!r}")

    print(
        f"MCP stdio smoke passed: {len(tool_names)} tools, "
        f"{len(resources)} resources, {len(prompts)} prompts"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path, help="Path to the bundled backend executable.")
    parser.add_argument("--timeout", type=int, default=15, help="Timeout in seconds.")
    parser.add_argument(
        "--skip-build-info",
        action="store_true",
        help="Skip build-info.json freshness verification.",
    )
    args = parser.parse_args()
    smoke_mcp_stdio(
        args.executable,
        timeout=args.timeout,
        verify_build_info=not args.skip_build_info,
    )


if __name__ == "__main__":
    try:
        main()
    except subprocess.TimeoutExpired as exc:
        print(f"MCP smoke process timed out after {exc.timeout} seconds", file=sys.stderr)
        raise SystemExit(1) from exc
