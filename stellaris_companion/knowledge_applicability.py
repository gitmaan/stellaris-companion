"""Small, declarative applicability hints for versioned mechanics retrieval.

These hints select reference material. They never decide unlocks, ownership or
achievement eligibility, and an unknown condition is not a negative observation.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .campaign_evidence import resolve_empire_identity

logger = logging.getLogger(__name__)
APPLICABILITY_PATTERN = re.compile(r"<!--\s*applies-to:\s*([a-z][a-z0-9-]*)\s*-->")
Applicability = Literal["supported", "contradicted", "unknown"]


def _words(text: str) -> set[str]:
    words = set(re.findall(r"[^\W_]+", text.casefold()))
    return {
        word[:-3] + "y"
        if len(word) > 4 and word.endswith("ies")
        else word[:-1]
        if len(word) > 3 and word.endswith("s")
        else word
        for word in words
    }


@dataclass(frozen=True)
class KnowledgeScope:
    label: str
    identity: dict[str, str | bool | list[str]]
    topics: tuple[str, ...]

    def requested_by(self, question: str) -> bool:
        """Match explicit concepts, without broad economy/resource query aliases."""
        words = _words(question)
        return any(_words(topic) <= words for topic in self.topics)

    def assess(self, identity: dict[str, Any] | None) -> Applicability:
        raw = identity if isinstance(identity, dict) else {}
        typed = resolve_empire_identity(raw)
        statuses: list[Applicability] = []
        for field, expected in self.identity.items():
            if field == "is_nomadic":
                actual = raw.get(field)
                if not isinstance(actual, bool):
                    statuses.append("unknown")
                else:
                    statuses.append("supported" if actual == expected else "contradicted")
            elif field == "civics":
                entries = typed["civics"]
                observed = {entry["id"] for entry in entries}
                # Civic lists in historical/partial contexts have no completeness
                # guarantee. Positive membership is useful; omission stays unknown.
                statuses.append("supported" if set(expected) <= observed else "unknown")
            else:
                entry = typed[field]
                if entry and entry["id"] == expected:
                    statuses.append("supported")
                elif entry and entry["source"] == "verified_catalog":
                    statuses.append("contradicted")
                else:
                    statuses.append("unknown")
        if "contradicted" in statuses:
            return "contradicted"
        if not statuses or "unknown" in statuses:
            return "unknown"
        return "supported"

    def reference_note(self, status: Applicability) -> str:
        if status == "supported":
            return f"Scope: {self.label}; supported by the supplied identity."
        if status == "contradicted":
            return (
                f"Scope: {self.label}; comparison or hypothetical reference, "
                "not a description of the supplied empire."
            )
        return (
            f"Scope: {self.label}; conditional reference. "
            "The supplied identity does not establish this condition."
        )


def parse_scope_registry(data: Any) -> dict[str, KnowledgeScope]:
    """Validate maintained metadata independently of model behavior."""
    if not isinstance(data, dict) or data.get("format_version") != 1:
        raise ValueError("Applicability registry requires format_version 1")
    entries = data.get("scopes")
    if not isinstance(entries, dict):
        raise ValueError("Applicability registry requires a scopes object")
    scopes = {}
    for name, entry in entries.items():
        if not re.fullmatch(r"[a-z][a-z0-9-]*", name) or not isinstance(entry, dict):
            raise ValueError(f"Invalid applicability scope: {name}")
        if set(entry) != {"label", "identity", "topics"}:
            raise ValueError(f"Scope {name} requires only label, identity and topics")
        label, identity, topics = entry["label"], entry["identity"], entry["topics"]
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"Scope {name} requires a readable label")
        if not isinstance(identity, dict) or set(identity) - {
            "authority",
            "origin",
            "civics",
            "is_nomadic",
        }:
            raise ValueError(f"Scope {name} has unsupported identity fields")
        for field, expected in identity.items():
            if field == "is_nomadic":
                valid = isinstance(expected, bool)
            elif field == "civics":
                valid = (
                    isinstance(expected, list)
                    and bool(expected)
                    and all(isinstance(item, str) and item.strip() for item in expected)
                )
            else:
                valid = isinstance(expected, str) and bool(expected.strip())
            if not valid:
                raise ValueError(f"Scope {name} has invalid {field} condition")
        if (
            not isinstance(topics, list)
            or not topics
            or not all(isinstance(topic, str) and bool(_words(topic)) for topic in topics)
        ):
            raise ValueError(f"Scope {name} requires explicit topic phrases")
        scopes[name] = KnowledgeScope(label.strip(), identity, tuple(topics))
    return scopes


def load_scope_registry(path: Path) -> dict[str, KnowledgeScope]:
    try:
        return parse_scope_registry(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError) as exc:
        # A broken optional registry must not turn its scoped rules into generic
        # facts. Callers omit unresolved scopes; CI validates shipped references.
        logger.warning("Mechanics applicability metadata unavailable: %s", exc)
        return {}
