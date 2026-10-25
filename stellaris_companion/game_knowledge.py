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

# Cygnus changed the Pop Group data model, so Pegasus' compiled mechanics cannot
# serve as its baseline. Add future release lines here only after a breaking audit.
BREAKING_SNAPSHOT_BOUNDARIES = frozenset({(4, 5)})

_VERSION_PATTERN = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")
_MARKDOWN_SECTION_PATTERN = re.compile(r"(?m)^(#{1,3})\s+(.+?)\s*$")
_SUPERSEDES_RULE_PATTERN = re.compile(r"<!--\s*supersedes-rule:\s*([^\n]+?)\s*-->")
_RULE_PATTERN = re.compile(r"(?m)^[*-]\s+\*\*(?P<label>[^\n*]+):\*\*[^\n]*(?:\n[ \t]+[^\n]*)*")
_SEARCH_STOP_WORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "before",
        "but",
        "by",
        "can",
        "could",
        "current",
        "do",
        "does",
        "for",
        "from",
        "game",
        "get",
        "give",
        "had",
        "has",
        "have",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "me",
        "more",
        "most",
        "my",
        "next",
        "no",
        "not",
        "of",
        "on",
        "or",
        "our",
        "should",
        "so",
        "some",
        "still",
        "than",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "through",
        "to",
        "up",
        "use",
        "using",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "work",
        "would",
        "you",
        "your",
        "prioritize",
        "priority",
        "advice",
        "explain",
        "tell",
    ]
)
_SEARCH_ALIASES: dict[str, tuple[str, ...]] = {
    "pop": ("population", "workforce", "colony"),
    "growth": ("population", "workforce", "colony"),
    "job": ("population", "workforce"),
    "district": ("planet", "development", "production"),
    "building": ("planet", "development", "production"),
    "resource": ("economy", "trade", "production", "reserve"),
    "energy": ("economy", "production", "reserve"),
    "mineral": ("economy", "production", "reserve"),
    "alloy": ("economy", "production"),
    "food": ("economy", "production"),
    "technology": ("research", "science", "focus"),
    "tech": ("research", "science", "focus"),
    "scientist": ("research", "science"),
    "ship": ("naval", "fleet", "starbase"),
    "anchorage": ("naval", "fleet", "starbase"),
    "psi": ("psionic", "shroud"),
    "gaia": ("infernal", "hot"),
    "battle": ("combat", "war", "threat"),
    "army": ("combat", "war", "military"),
    "invasion": ("combat", "war", "military"),
    "occupation": ("combat", "war"),
    "arkship": ("nomad", "logistics"),
    "waystation": ("nomad", "logistics", "contract"),
    "wayline": ("nomad", "logistics"),
    "cargo": ("reserve", "economy", "logistics"),
    "abundance": ("reserve", "economy"),
    "astral": ("automation", "reliability", "science"),
    "rift": ("automation", "reliability", "science"),
    "automated": ("automation", "reliability"),
    "disengage": ("disengagement", "combat"),
    "disappear": ("disengagement", "combat"),
}

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
    notes_only: bool = False


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
        content = path.read_text(encoding="utf-8")
        return content if clean_knowledge_content(content) else None
    except OSError:
        return None


def _combine_knowledge(parts: list[str]) -> str | None:
    """Apply explicit rule replacements without discarding unrelated older facts."""
    content = ""
    for part in parts:
        replaced_labels = set(_SUPERSEDES_RULE_PATTERN.findall(part))
        if replaced_labels:
            content = _RULE_PATTERN.sub(
                lambda match, labels=replaced_labels: "" if match["label"] in labels else match[0],
                content,
            )
        content += f"\n\n{clean_knowledge_content(part)}"
    return clean_knowledge_content(content) or None


def _search_terms(text: str, *, expand_aliases: bool = True) -> set[str]:
    terms = {
        term
        for term in re.findall(r"[^\W_]+", text.lower())
        if term not in _SEARCH_STOP_WORDS and not term.isdigit()
    }
    singular_terms = {
        f"{term[:-3]}y" if term.endswith("ies") else term[:-1]
        for term in terms
        if len(term) > 3 and term.endswith(("ies", "s"))
    }
    terms.update(singular_terms)
    if expand_aliases:
        for term in tuple(terms):
            terms.update(_SEARCH_ALIASES.get(term, ()))
    return terms


def _select_relevant_sections(content: str, topics: str, *, limit: int) -> str:
    """Keep safety baselines plus the few mechanics sections relevant to a request."""
    headings = list(_MARKDOWN_SECTION_PATTERN.finditer(content))
    if not headings:
        return content

    topic_terms = _search_terms(topics, expand_aliases=False)
    alias_terms = _search_terms(topics) - topic_terms
    selected: set[int] = set()
    candidates: list[tuple[int, int]] = []

    for index, match in enumerate(headings):
        title = match.group(2).strip()
        normalized_title = title.lower()
        if (
            "critical 4.x baseline" in normalized_title
            or "interpretation guardrails" in normalized_title
        ):
            selected.add(index)
            continue

        end = headings[index + 1].start() if index + 1 < len(headings) else len(content)
        body = content[match.end() : end].strip()
        if not body:
            continue  # Document titles are not mechanics sections.
        title_terms = _search_terms(title, expand_aliases=False)
        body_terms = _search_terms(body, expand_aliases=False)
        label_terms = _search_terms(
            " ".join(rule["label"] for rule in _RULE_PATTERN.finditer(body)),
            expand_aliases=False,
        )
        score = (
            4 * len(topic_terms & title_terms)
            + 3 * len(topic_terms & label_terms)
            + len(topic_terms & body_terms)
            + 2 * len(alias_terms & title_terms)
            + len(alias_terms & label_terms)
        )
        if score:
            candidates.append((score, index))

    # Recency breaks ties; sharing a topic does not make an older section obsolete.
    # Actual superseded rules have already been removed by _combine_knowledge.
    candidates.sort(reverse=True)
    if candidates:
        # An incidental body mention should not fill a spare slot beside a strong
        # rule/title match (e.g. Hedonists mentioning population in an ethics query).
        minimum_score = candidates[0][0] / 4
        selected.update(index for score, index in candidates[:limit] if score >= minimum_score)

    sections: list[str] = []
    for index in sorted(selected):
        start = headings[index].start()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(content)
        sections.append(content[start:end].strip())
    return "\n\n".join(sections)


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
    known_line = any(key[:2] == target_key[:2] for key in comparable_keys)
    earlier_key = max((key for key in comparable_keys if key <= target_key), default=None)
    if not known_line and earlier_key is not None:
        return GameKnowledgeContext(
            version,
            target_version,
            ".".join(str(part) for part in earlier_key),
            "unsupported_newer",
            None,
        )

    # A snapshot is usable only for this save and only on this side of the latest
    # breaking release. Future, unreadable, or empty snapshots cannot relax it.
    boundary = max(
        (
            (major, minor, 0)
            for major, minor in BREAKING_SNAPSHOT_BOUNDARIES
            if (major, minor, 0) <= target_key
        ),
        default=None,
    )
    snapshot_key: tuple[int, int, int] | None = None
    snapshot_content = None
    snapshot_version = None
    if cumulative and prefer_snapshot:
        for candidate in reversed(snapshot_versions):
            key = parse_version(candidate)
            if key is None or key > target_key or (boundary is not None and key < boundary):
                continue
            content = _load_file(candidate, snapshots_dir)
            if content:
                snapshot_key, snapshot_version, snapshot_content = key, candidate, content
                break
    notes_only_line = boundary is not None and snapshot_key is None

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
        status: KnowledgeStatus = (
            "exact" if loaded_version == target_version and not notes_only_line else "partial"
        )
        return GameKnowledgeContext(
            version,
            target_version,
            loaded_version,
            status if content_parts else "unavailable",
            _combine_knowledge(content_parts),
            notes_only=notes_only_line,
        )

    content_parts = []
    loaded_version = None
    if snapshot_content:
        content_parts.append(snapshot_content)
        loaded_version = snapshot_version

    for patch_version in patch_versions:
        patch_key = parse_version(patch_version)
        if patch_key is None or patch_key > target_key:
            continue
        if boundary is not None and patch_key < boundary:
            continue
        if snapshot_key is not None and patch_key <= snapshot_key:
            continue
        content = _load_file(patch_version, patches_dir)
        if content:
            content_parts.append(content)
            loaded_version = patch_version

    status = "exact" if loaded_version == target_version and not notes_only_line else "partial"
    return GameKnowledgeContext(
        version,
        target_version,
        loaded_version,
        status if content_parts else "unavailable",
        _combine_knowledge(content_parts),
        notes_only=notes_only_line,
    )


def build_game_knowledge_prompt(
    version: str,
    *,
    purpose: KnowledgePurpose,
    topics: str | None = None,
    max_topic_sections: int = 3,
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

    knowledge_content = knowledge.content
    if knowledge_content and topics is not None:
        knowledge_content = _select_relevant_sections(
            knowledge_content,
            topics,
            limit=max(0, max_topic_sections),
        )

    if knowledge_content and knowledge.status == "exact":
        lines.extend(
            [
                "",
                f"Verified mechanics for {version}:",
                "Treat these as the current baseline. Do not discuss patches or changes.",
                "",
                knowledge_content,
            ]
        )
    elif knowledge_content:
        if knowledge.notes_only:
            lines.extend(
                [
                    "",
                    f"Only the listed mechanics changes are verified through {knowledge.loaded_through}.",
                    f"The campaign reports {version}; other mechanics remain unverified for this version.",
                    "Do not carry forward older-version rules without campaign evidence.",
                    "Use the following only when it agrees with supplied campaign evidence:",
                    "",
                    knowledge_content,
                ]
            )
        else:
            lines.extend(
                [
                    "",
                    f"Mechanics coverage is verified only through {knowledge.loaded_through}.",
                    f"The campaign reports {version}; do not assume older details remained unchanged.",
                    "Use the following only when it agrees with supplied campaign evidence:",
                    "",
                    knowledge_content,
                ]
            )
    elif knowledge.content and topics is not None:
        lines.extend(
            [
                "",
                f"Mechanics coverage is {knowledge.status}, through {knowledge.loaded_through}.",
                "No topic-specific mechanics section matched this request; this is not proof that no rule applies.",
                "Do not assume unlisted or older-version mechanics are verified.",
                "Rely on supplied campaign evidence and the evidence hierarchy above.",
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
