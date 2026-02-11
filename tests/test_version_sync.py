import json
from pathlib import Path

import tomllib


def test_versions_match_across_python_and_electron_packages():
    """Release safety check: keep the app + backend versions in sync."""
    repo_root = Path(__file__).resolve().parents[1]

    pyproject = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    python_version = pyproject["project"]["version"]

    electron_pkg = json.loads((repo_root / "electron" / "package.json").read_text(encoding="utf-8"))
    electron_version = electron_pkg["version"]

    assert python_version == electron_version, (
        f"Version mismatch: pyproject.toml={python_version} electron/package.json={electron_version}"
    )
