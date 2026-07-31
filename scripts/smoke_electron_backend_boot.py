#!/usr/bin/env python3
"""Smoke-test that the bundled Electron HTTP backend can boot."""

from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import tempfile
import time
from pathlib import Path


def _free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _port_is_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return True
    except OSError:
        return False


def _stop_process(proc: subprocess.Popen[str]) -> str:
    if proc.poll() is None:
        if os.name == "nt":
            proc.terminate()
        else:
            proc.send_signal(signal.SIGTERM)
    try:
        output, _ = proc.communicate(timeout=5)
        return output
    except subprocess.TimeoutExpired:
        proc.kill()
        output, _ = proc.communicate(timeout=5)
        return output


def smoke_backend_boot(executable: Path, *, timeout: int = 25) -> None:
    if not executable.is_file():
        raise SystemExit(f"Backend executable not found: {executable}")

    port = _free_local_port()
    deadline = time.monotonic() + timeout

    with tempfile.TemporaryDirectory(prefix="stellaris-electron-smoke-") as tmp:
        tmp_path = Path(tmp)
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        save_dir = tmp_path / "saves"
        save_dir.mkdir()
        log_dir = tmp_path / "logs"
        log_dir.mkdir()

        env = os.environ.copy()
        env.update(
            {
                "STELLARIS_API_TOKEN": "smoke-test-token",
                "STELLARIS_DB_PATH": str(tmp_path / "history.db"),
                "STELLARIS_SAVE_DIR": str(save_dir),
                "STELLARIS_LOG_DIR": str(log_dir),
                "HOME": str(home_dir),
                "USERPROFILE": str(home_dir),
            }
        )
        env.pop("GOOGLE_API_KEY", None)
        env.pop("STELLARIS_ADVISOR_API_KEY", None)
        env.pop("STELLARIS_ADVISOR_MODEL", None)
        env.pop("STELLARIS_SAVE_PATH", None)

        proc = subprocess.Popen(
            [str(executable), "--host", "127.0.0.1", "--port", str(port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )

        try:
            while time.monotonic() < deadline:
                if _port_is_open(port):
                    print(f"Electron backend boot smoke passed on port {port}")
                    return
                if proc.poll() is not None:
                    break
                time.sleep(0.1)

            if proc.poll() is None:
                output = _stop_process(proc)
                raise SystemExit(
                    f"Electron backend boot smoke timed out after {timeout} seconds.\n"
                    + "\n".join(output.splitlines()[-80:])
                )

            output, _ = proc.communicate(timeout=1)
            raise SystemExit(
                f"Electron backend boot smoke failed (exit {proc.returncode}).\n"
                + "\n".join(output.splitlines()[-120:])
            )
        finally:
            if proc.poll() is None:
                _stop_process(proc)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path, help="Path to the bundled backend executable.")
    parser.add_argument("--timeout", type=int, default=25, help="Timeout in seconds.")
    args = parser.parse_args()
    smoke_backend_boot(args.executable, timeout=args.timeout)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit(130)
