#!/usr/bin/env python3
"""Stamp and verify the bundled Python backend build metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BUILD_INFO_NAME = "build-info.json"
BUILD_INFO_SCHEMA = 1

FINGERPRINT_PATHS = [
    "backend",
    "stellaris_companion",
    "stellaris-backend.spec",
    "pyproject.toml",
]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _git_commit(root: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None


def _git_dirty(root: Path) -> bool | None:
    try:
        return bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"],
                cwd=root,
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        )
    except Exception:
        return None


def iter_fingerprint_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for rel in FINGERPRINT_PATHS:
        path = root / rel
        if path.is_file():
            files.append(path)
            continue
        if not path.is_dir():
            continue
        for candidate in path.rglob("*.py"):
            parts = set(candidate.relative_to(root).parts)
            if "__pycache__" in parts:
                continue
            files.append(candidate)
    return sorted(files, key=lambda item: item.relative_to(root).as_posix())


def source_fingerprint(root: Path = ROOT) -> str:
    digest = hashlib.sha256()
    for path in iter_fingerprint_files(root):
        rel = path.relative_to(root).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def expected_app_version(root: Path = ROOT) -> str:
    package_json = _read_json(root / "electron" / "package.json")
    version = package_json.get("version")
    if not isinstance(version, str) or not version:
        raise RuntimeError("Could not read electron/package.json version")
    return version


def build_info_payload(root: Path = ROOT) -> dict[str, Any]:
    return {
        "schema_version": BUILD_INFO_SCHEMA,
        "app_version": expected_app_version(root),
        "built_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "git_commit": _git_commit(root),
        "git_dirty": _git_dirty(root),
        "source_fingerprint": source_fingerprint(root),
        "mcp": {
            "enabled": True,
            "protocol_version": "2025-11-25",
            "expected_tools": 10,
        },
    }


def stamp(bundle_dir: Path, root: Path = ROOT) -> Path:
    if not bundle_dir.is_dir():
        raise SystemExit(f"Backend bundle directory not found: {bundle_dir}")
    payload = build_info_payload(root)
    output_path = bundle_dir / BUILD_INFO_NAME
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def verify(bundle_dir: Path, root: Path = ROOT) -> dict[str, Any]:
    info_path = bundle_dir / BUILD_INFO_NAME
    if not info_path.is_file():
        raise SystemExit(
            f"Missing {BUILD_INFO_NAME} in {bundle_dir}. Rebuild the backend with scripts/build-python.sh."
        )

    info = _read_json(info_path)
    errors: list[str] = []
    if info.get("schema_version") != BUILD_INFO_SCHEMA:
        errors.append(
            f"schema_version is {info.get('schema_version')!r}, expected {BUILD_INFO_SCHEMA}"
        )
    if info.get("app_version") != expected_app_version(root):
        errors.append(
            f"app_version is {info.get('app_version')!r}, expected {expected_app_version(root)!r}"
        )
    if info.get("source_fingerprint") != source_fingerprint(root):
        errors.append("source_fingerprint does not match current backend source")
    mcp = info.get("mcp") if isinstance(info.get("mcp"), dict) else {}
    if mcp.get("enabled") is not True:
        errors.append("mcp.enabled is not true")
    if errors:
        raise SystemExit(
            "Backend build metadata is stale or invalid:\n"
            + "\n".join(f"- {error}" for error in errors)
            + "\nRebuild the backend with scripts/build-python.sh."
        )
    return info


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    stamp_parser = subparsers.add_parser("stamp", help="Write build metadata into a backend bundle")
    stamp_parser.add_argument("bundle_dir", type=Path)

    verify_parser = subparsers.add_parser("verify", help="Verify backend bundle metadata")
    verify_parser.add_argument("bundle_dir", type=Path)

    args = parser.parse_args()
    if args.command == "stamp":
        output_path = stamp(args.bundle_dir)
        print(output_path)
    elif args.command == "verify":
        verify(args.bundle_dir)
        print(f"Backend build metadata verified: {args.bundle_dir / BUILD_INFO_NAME}")


if __name__ == "__main__":
    main()
