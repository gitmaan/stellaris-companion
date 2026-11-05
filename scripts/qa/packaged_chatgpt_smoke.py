"""Exercise an installed backend against a synthetic loopback ChatGPT bridge.

Run only against a disposable installation. The missing-CA case temporarily moves
that installation's certifi bundle and restores it in finally. No account, real
campaign, or external model service is used.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import socket
import subprocess
import tempfile
import threading
import time
import uuid
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen


def request_json(url: str, token: str, body: dict | None = None) -> dict:
    request = Request(
        url,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urlopen(request, timeout=15) as response:
        return json.load(response)


def run_case(backend: Path, parser: Path, output: Path, case: str) -> dict:
    seen = []
    capability = uuid.uuid4().hex

    class Bridge(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            if (
                self.path != "/generate"
                or self.headers.get("Authorization") != f"Bearer {capability}"
            ):
                self.send_error(401)
                return
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append(body)
            payload = json.dumps(
                {"text": "Installed bridge smoke passed.", "model": "smoke-model"}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    with tempfile.TemporaryDirectory(prefix="stellaris-bridge-smoke-") as directory:
        root = Path(directory)
        save = root / "synthetic.sav"
        with zipfile.ZipFile(save, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "meta",
                'name="Bridge Smoke"\ndate="2200.01.01"\nversion="Pegasus v4.4.6"\nrequired_dlcs={}\n',
            )
            archive.writestr(
                "gamestate",
                """date="2200.01.01"
version="Pegasus v4.4.6"
player={ { name="Synthetic Commander" country=0 } }
country={
  0={ name="Bridge Smoke" type=default capital=0
      government={ authority=auth_democratic civics={} }
      owned_planets={} resources={energy=100 minerals=100 trade=100}
      budget={current_month={income={} expenses={}}}
  }
}
""",
            )
        with socket.socket() as port_probe:
            port_probe.bind(("127.0.0.1", 0))
            port = port_probe.getsockname()[1]
        api_token = uuid.uuid4().hex
        # Keep OS/runtime variables but remove all inherited game/provider inputs.
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("STELLARIS_", "GOOGLE_", "GEMINI_", "OPENAI_"))
        }
        env.update(
            {
                "STELLARIS_API_TOKEN": api_token,
                "STELLARIS_DB_PATH": str(root / "history.db"),
                "STELLARIS_SAVE_PATH": str(save),
                "STELLARIS_SAVE_DIR": str(root),
                "STELLARIS_ADVISOR_PROVIDER": "chatgpt",
                "STELLARIS_ADVISOR_MODEL": "smoke-model",
                "STELLARIS_CHATGPT_BRIDGE_TOKEN": capability,
                "PARSER_BINARY": str(parser),
            }
        )
        with ThreadingHTTPServer(("127.0.0.1", 0), Bridge) as bridge:
            thread = threading.Thread(target=bridge.serve_forever, daemon=True)
            thread.start()
            env["STELLARIS_CHATGPT_BRIDGE_URL"] = f"http://127.0.0.1:{bridge.server_port}"
            with (output / f"{case}.log").open("w") as log:
                process = subprocess.Popen(
                    [
                        str(backend),
                        "--port",
                        str(port),
                        "--save-path",
                        str(save),
                        "--parent-pid",
                        str(os.getpid()),
                    ],
                    cwd=root,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
                try:
                    endpoint = f"http://127.0.0.1:{port}"
                    deadline = time.monotonic() + 90
                    health = {}
                    while time.monotonic() < deadline:
                        if process.poll() is not None:
                            raise RuntimeError(
                                f"Backend exited: {process.returncode}; see {case}.log"
                            )
                        with contextlib.suppress(OSError):
                            health = request_json(f"{endpoint}/api/health", api_token)
                            if health.get("precompute_ready"):
                                break
                        time.sleep(0.2)
                    else:
                        raise RuntimeError(f"Backend did not become ready: {health}")
                    result = request_json(
                        f"{endpoint}/api/chat",
                        api_token,
                        {
                            "message": "Confirm this synthetic transport check.",
                            "session_key": f"packaged-{case}",
                            "language": "en",
                        },
                    )
                    assert result["text"] == "Installed bridge smoke passed.", result
                    assert result["provider"] == "chatgpt", result
                    assert result["model"] == "smoke-model", result
                    assert result["completion"]["status"] == "complete", result
                    assert len(seen) == 1, len(seen)
                    assert seen[0]["purpose"] == "advisor"
                    assert "Bridge Smoke" in seen[0]["input"]
                    assert seen[0]["instructions"]
                    return {
                        "case": case,
                        "requests": len(seen),
                        "provider": result["provider"],
                        "model": result["model"],
                        "completion": result["completion"]["status"],
                    }
                finally:
                    process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=10)
                    bridge.shutdown()
                    thread.join(timeout=5)


def main() -> None:
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--backend", type=Path, required=True)
    args.add_argument("--parser", type=Path, required=True)
    args.add_argument("--output", type=Path, required=True)
    options = args.parse_args()
    backend, parser, output = (
        options.backend.resolve(),
        options.parser.resolve(),
        options.output.resolve(),
    )
    assert backend.is_file() and parser.is_file()
    bundles = list(backend.parent.rglob("certifi/cacert.pem"))
    assert len(bundles) == 1, f"Expected exactly one installed CA bundle, found {len(bundles)}"
    bundle = bundles[0]
    original_hash = hashlib.sha256(bundle.read_bytes()).hexdigest()
    backup = bundle.with_name(f"cacert.pem.smoke-{uuid.uuid4().hex}")
    output.mkdir(parents=True, exist_ok=True)
    results = [run_case(backend, parser, output, "normal-ca")]
    bundle.rename(backup)
    try:
        results.append(run_case(backend, parser, output, "missing-ca"))
    finally:
        backup.rename(bundle)
    assert hashlib.sha256(bundle.read_bytes()).hexdigest() == original_hash
    receipt = {
        "backend": str(backend),
        "backend_sha256": hashlib.sha256(backend.read_bytes()).hexdigest(),
        "ca_restored": True,
        "synthetic_bridge": True,
        "external_model_calls": 0,
        "cases": results,
    }
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
