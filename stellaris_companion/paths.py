from __future__ import annotations

from pathlib import Path


def get_repo_root(start: Path | None = None) -> Path:
    """Best-effort repo root detection.

    In development, shared modules historically lived at repo root and relied on
    `Path(__file__).parent` to locate resources. After moving these modules into
    a package, we still want those paths to resolve to repo root for the dev
    workflow (and for the Electron+PyInstaller bundle build inputs).

    In an installed environment (site-packages), the repo markers won't exist,
    so we fall back to the package directory.
    """
    here = (start or Path(__file__)).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "pyproject.toml").exists() and (parent / "backend").exists():
            return parent
    return here.parent
