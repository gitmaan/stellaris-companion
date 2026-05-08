#!/usr/bin/env python3
"""Smoke-test a Stellaris Companion backend executable as an MCP stdio server."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
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
        input_text = "\n".join(
            [
                _message(
                    1,
                    "initialize",
                    {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {"name": "stellaris-mcp-smoke", "version": "1.0.0"},
                    },
                ),
                _message(2, "tools/list"),
                "",
            ]
        )
        proc = subprocess.run(
            [
                str(executable),
                "--mcp",
                "--db-path",
                str(db_path),
                "--language",
                "en",
            ],
            input=input_text,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )

    if proc.returncode != 0:
        raise SystemExit(
            f"MCP smoke process failed (exit {proc.returncode}). stderr:\n{proc.stderr.strip()}"
        )

    responses = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    by_id = {response.get("id"): response for response in responses if isinstance(response, dict)}
    initialized = by_id.get(1, {}).get("result", {})
    if initialized.get("serverInfo", {}).get("title") != "Stellaris Companion":
        raise SystemExit(f"MCP initialize returned unexpected serverInfo: {initialized!r}")

    tools = by_id.get(2, {}).get("result", {}).get("tools", [])
    tool_names = {tool.get("name") for tool in tools if isinstance(tool, dict)}
    missing = sorted(EXPECTED_TOOLS - tool_names)
    if missing:
        raise SystemExit(f"MCP tools/list missing expected tools: {', '.join(missing)}")

    print(f"MCP stdio smoke passed: {len(tool_names)} tools")


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
