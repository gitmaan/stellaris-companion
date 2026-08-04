"""Versioned, provider-neutral Stellaris mechanics for model prompts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .paths import get_repo_root


def _find_default_patches_dir(module_file: Path = Path(__file__)) -> Path:
    """Find source, package-local, or PyInstaller-sibling knowledge resources."""
    package_dir = module_file.resolve().parent
    candidates = (
        get_repo_root(module_file) / "patches",
        package_dir / "patches",
        package_dir.parent / "patches",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return package_dir / "patches"


DEFAULT_PATCHES_DIR = _find_default_patches_dir()
DEFAULT_SNAPSHOTS_DIR = DEFAULT_PATCHES_DIR / "snapshots"

_VERSION_PATTERN = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")

KnowledgeStatus = Literal["exact", "partial", "unsupported_newer", "unavailable"]
KnowledgePurpose = Literal["advisor", "chronicle"]


@dataclass(frozen=True)
class GameKnowledgeContext:
    """Resolved mechanics and their coverage for one game version."""

    requested_version: str
    target_version: str | None
    loaded_through: str | None
    status: KnowledgeStatus
    content: str | None


def parse_version(version: str) -> tuple[int, int, int] | None:
    """Parse a major.minor[.patch] version into a sortable tuple."""
    match = re.fullmatch(r"(\d+)\.(\d+)(?:\.(\d+))?", str(version or "").strip())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)


def extract_version(version: str) -> str | None:
    """Extract the most specific numeric version from a display string."""
    match = _VERSION_PATTERN.search(str(version or ""))
    if not match:
        return None
    parts = [match.group(1), match.group(2)]
    if match.group(3) is not None:
        parts.append(match.group(3))
    return ".".join(parts)


def clean_knowledge_content(content: str) -> str:
    """Remove maintainer comments while retaining model-useful Markdown structure."""
    cleaned = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
    lines = [line.rstrip() for line in cleaned.splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def list_versioned_markdown(directory: Path) -> list[str]:
    """List version-named Markdown files in numeric order."""
    if not directory.exists():
        return []
    versions: list[tuple[tuple[int, int, int], str]] = []
    for file_path in directory.glob("*.md"):
        parsed = parse_version(file_path.stem)
        if parsed is not None:
            versions.append((parsed, file_path.stem))
    versions.sort(key=lambda item: item[0])
    return [version for _, version in versions]


def _load_file(version: str, directory: Path) -> str | None:
    path = directory / f"{version}.md"
    if not path.exists():
        return None
    try:
        return clean_knowledge_content(path.read_text(encoding="utf-8"))
    except OSError:
        return None


def load_game_knowledge(
    version: str,
    *,
    cumulative: bool = True,
    prefer_snapshot: bool = True,
    patches_dir: Path = DEFAULT_PATCHES_DIR,
    snapshots_dir: Path = DEFAULT_SNAPSHOTS_DIR,
) -> GameKnowledgeContext:
    """Resolve mechanics without presenting stale knowledge as current truth."""
    target_version = extract_version(version)
    target_key = parse_version(target_version) if target_version else None
    if target_key is None or target_version is None:
        return GameKnowledgeContext(version, None, None, "unavailable", None)

    patch_versions = list_versioned_markdown(patches_dir)
    snapshot_versions = list_versioned_markdown(snapshots_dir)
    known_versions = patch_versions + snapshot_versions
    known_keys = [parse_version(item) for item in known_versions]
    comparable_keys = [item for item in known_keys if item is not None]
    newest_key = max(comparable_keys, default=None)

    if newest_key is not None and target_key[:2] > newest_key[:2]:
        return GameKnowledgeContext(
            version,
            target_version,
            ".".join(str(part) for part in newest_key),
            "unsupported_newer",
            None,
        )

    if not cumulative:
        content_parts: list[str] = []
        loaded_version: str | None = None
        for patch_version in patch_versions:
            patch_key = parse_version(patch_version)
            if patch_key is None:
                continue
            if patch_key[:2] == target_key[:2] and patch_key <= target_key:
                content = _load_file(patch_version, patches_dir)
                if content:
                    content_parts.append(content)
                    loaded_version = patch_version
        status: KnowledgeStatus = "exact" if loaded_version == target_version else "partial"
        return GameKnowledgeContext(
            version,
            target_version,
            loaded_version,
            status if content_parts else "unavailable",
            "\n\n".join(content_parts) if content_parts else None,
        )

    content_parts = []
    loaded_version = None
    snapshot_key: tuple[int, int, int] | None = None

    if prefer_snapshot:
        eligible = [
            (parsed, snapshot_version)
            for snapshot_version in snapshot_versions
            if (parsed := parse_version(snapshot_version)) is not None and parsed <= target_key
        ]
        if eligible:
            snapshot_key, snapshot_version = eligible[-1]
            content = _load_file(snapshot_version, snapshots_dir)
            if content:
                content_parts.append(content)
                loaded_version = snapshot_version
            else:
                snapshot_key = None

    for patch_version in patch_versions:
        patch_key = parse_version(patch_version)
        if patch_key is None or patch_key > target_key:
            continue
        if snapshot_key is not None and patch_key <= snapshot_key:
            continue
        content = _load_file(patch_version, patches_dir)
        if content:
            content_parts.append(content)
            loaded_version = patch_version

    status = "exact" if loaded_version == target_version else "partial"
    return GameKnowledgeContext(
        version,
        target_version,
        loaded_version,
        status if content_parts else "unavailable",
        "\n\n".join(content_parts) if content_parts else None,
    )


def build_game_knowledge_prompt(
    version: str,
    *,
    purpose: KnowledgePurpose,
    patches_dir: Path = DEFAULT_PATCHES_DIR,
    snapshots_dir: Path = DEFAULT_SNAPSHOTS_DIR,
) -> str:
    """Build shared evidence rules and verified mechanics for a model system prompt."""
    knowledge = load_game_knowledge(
        version,
        patches_dir=patches_dir,
        snapshots_dir=snapshots_dir,
    )
    purpose_rule = (
        "Use mechanics to explain the recorded world, never as evidence that an event "
        "occurred. Do not add a name, identity, participant, place, action, motive, cause, "
        "outcome, or unlocked feature unless the supplied campaign evidence supports it. "
        "Treat 'not recorded' as a limit of the supplied record, not proof that something "
        "never occurred."
        if purpose == "chronicle"
        else "Use mechanics to interpret the save and form advice, but do not invent current "
        "resources, unlocks, settings, borders, or events, or extend a listed rule into an "
        "unstated automatic outcome. Verify arithmetic before using a calculated value to "
        "label the campaign state."
    )

    lines = [
        "[INTERNAL GAME KNOWLEDGE - never mention this block to the user]",
        "Evidence hierarchy:",
        "1. Supplied save observations and recorded events are authoritative for this campaign.",
        "2. Supplied settings and active DLC determine whether a mechanic applies.",
        "3. The verified version mechanics below explain the rules of the game.",
        "4. General model knowledge is a fallback and must not override the sources above.",
        "5. Mods can change baseline mechanics; when they conflict, prefer campaign evidence.",
        purpose_rule,
    ]

    if knowledge.content and knowledge.status == "exact":
        lines.extend(
            [
                "",
                f"Verified mechanics for {version}:",
                "Treat these as the current baseline. Do not discuss patches or changes.",
                "",
                knowledge.content,
            ]
        )
    elif knowledge.content:
        lines.extend(
            [
                "",
                f"Mechanics coverage is verified only through {knowledge.loaded_through}.",
                f"The campaign reports {version}; do not assume older details remained unchanged.",
                "Use the following only when it agrees with supplied campaign evidence:",
                "",
                knowledge.content,
            ]
        )
    else:
        lines.extend(
            [
                "",
                f"No verified mechanics pack covers {version}.",
                "Be conservative about version-specific mechanics and rely on campaign evidence.",
            ]
        )

    return "\n".join(lines)
