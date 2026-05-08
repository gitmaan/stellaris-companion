#!/usr/bin/env python3
"""Package the Claude Desktop MCPB extension for Stellaris Companion."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "mcpb" / "stellaris-companion"
APP_PACKAGE_JSON = ROOT / "electron" / "package.json"
ICON_SOURCE = ROOT / "electron" / "assets" / "icon.png"
DEFAULT_OUTPUT_DIR = ROOT / "electron" / "dist" / "mcpb"


def load_app_version() -> str:
    package = json.loads(APP_PACKAGE_JSON.read_text(encoding="utf-8"))
    version = package.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError(f"Could not read version from {APP_PACKAGE_JSON}")
    return version


def copy_source_tree(destination: Path) -> None:
    def ignore(_: str, names: list[str]) -> set[str]:
        return {
            name
            for name in names
            if name in {"node_modules", ".DS_Store", "__pycache__"}
            or name.endswith((".pyc", ".pyo"))
        }

    shutil.copytree(SOURCE_DIR, destination, ignore=ignore)
    shutil.copy2(ICON_SOURCE, destination / "icon.png")


def stamp_manifest(staging_dir: Path, version: str) -> dict[str, object]:
    manifest_path = staging_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["version"] = version
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest


def validate_staging(staging_dir: Path, manifest: dict[str, object]) -> None:
    required = ["manifest_version", "name", "version", "description", "author", "server"]
    missing = [key for key in required if key not in manifest]
    if missing:
        raise ValueError(f"manifest.json missing required fields: {', '.join(missing)}")

    server = manifest.get("server")
    if not isinstance(server, dict):
        raise ValueError("manifest.json server must be an object")

    entry_point = server.get("entry_point")
    if not isinstance(entry_point, str) or not entry_point:
        raise ValueError("manifest.json server.entry_point must be set")
    if not (staging_dir / entry_point).is_file():
        raise ValueError(f"server.entry_point does not exist in package: {entry_point}")

    if not (staging_dir / "icon.png").is_file():
        raise ValueError("icon.png was not staged")


def write_zip(staging_dir: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(staging_dir.rglob("*")):
            if not file_path.is_file():
                continue
            arcname = file_path.relative_to(staging_dir).as_posix()
            zf.write(file_path, arcname)

    with zipfile.ZipFile(output_path, "r") as zf:
        names = set(zf.namelist())
        for required_name in {"manifest.json", "server/index.js", "icon.png"}:
            if required_name not in names:
                raise ValueError(f"Packaged archive is missing {required_name}")
        json.loads(zf.read("manifest.json").decode("utf-8"))


def package_mcpb(output_dir: Path, version: str | None = None) -> Path:
    resolved_version = version or load_app_version()
    output_path = output_dir / f"stellaris-companion-mcp-relay-{resolved_version}.mcpb"

    with tempfile.TemporaryDirectory(prefix="stellaris-mcpb-") as tmp:
        staging_dir = Path(tmp) / "bundle"
        copy_source_tree(staging_dir)
        manifest = stamp_manifest(staging_dir, resolved_version)
        validate_staging(staging_dir, manifest)
        write_zip(staging_dir, output_path)

    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Package the Stellaris Companion Claude Desktop MCPB."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for the generated .mcpb file, default: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--version",
        default=None,
        help="Override extension version. Defaults to electron/package.json version.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = package_mcpb(args.output_dir, args.version)
    print(output_path)


if __name__ == "__main__":
    main()
