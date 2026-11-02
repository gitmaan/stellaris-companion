"""Conservative family selection from provider catalogs, shared with Electron.

Only known stable naming patterns are eligible. New names fail closed until the
family definition is updated; provider 'latest' aliases can include previews.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from datetime import date, datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

MODEL_CATALOG = json.loads(Path(__file__).with_name("model_catalog.json").read_text())
SELECTION_PREFIX = MODEL_CATALOG["selectionPrefix"]
_UNSTABLE = re.compile(r"\b(?:preview|experimental|exp|beta|alpha|deprecated)\b", re.I)


def selection_family(model: str, provider: str) -> str | None:
    if not model.startswith(SELECTION_PREFIX):
        return None
    family = model.removeprefix(SELECTION_PREFIX)
    if provider not in MODEL_CATALOG["families"].get(family, {}).get("patterns", {}):
        raise ValueError("This latest-stable model family is not supported by the provider.")
    return family


def stable_family_models(
    entries: list[dict[str, Any]], provider: str, family: str, *, today: date | None = None
) -> list[dict[str, Any]]:
    """Return eligible concrete models newest first, never an unverified alias."""
    pattern = MODEL_CATALOG["families"].get(family, {}).get("patterns", {}).get(provider)
    if not pattern:
        return []
    today = today or datetime.now(timezone.utc).date()
    candidates = []
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        model_id = str(entry.get("id") or entry.get("name") or "").removeprefix("models/")
        match = re.fullmatch(pattern, model_id)
        label = str(
            entry.get("display_name") or entry.get("displayName") or entry.get("name") or ""
        )
        if not match or model_id in seen or _UNSTABLE.search(label):
            continue
        expiry = entry.get("expiration_date")
        if expiry:
            try:
                if date.fromisoformat(str(expiry)[:10]) <= today:
                    continue
            except ValueError:
                continue
        if provider == "openrouter":
            architecture = entry.get("architecture")
            modalities = (
                architecture.get("output_modalities") if isinstance(architecture, dict) else None
            )
            endpoints = entry.get("endpoints")
            if isinstance(modalities, list) and "text" not in modalities:
                continue
            if isinstance(endpoints, list) and "/api/v1/chat/completions" not in endpoints:
                continue
        else:
            actions = entry.get("supported_actions") or entry.get("supportedGenerationMethods")
            if not isinstance(actions, list) or "generateContent" not in actions:
                continue
        version = [int(part) for part in match[1].split(".")]
        version = tuple((version + [0, 0, 0])[:3])
        revision = int(match[2] or 0) if len(match.groups()) > 1 else 0
        created = entry.get("created")
        created = (
            created if isinstance(created, (int, float)) and not isinstance(created, bool) else 0
        )
        candidates.append(((version, revision, created, model_id), {**entry, "id": model_id}))
        seen.add(model_id)
    return [entry for _, entry in sorted(candidates, key=lambda item: item[0], reverse=True)]


class ModelCatalogCache:
    """One cache per configured generator; refresh at most hourly, retry errors in a minute."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._expires = 0.0
        self._entries: list[dict[str, Any]] | None = None
        self._lock = Lock()

    def get(self, loader: Callable[[], list[dict[str, Any]]]) -> list[dict[str, Any]]:
        with self._lock:
            now = self._clock()
            if now < self._expires:
                if self._entries is None:
                    raise ValueError("Model catalog is temporarily unavailable.")
                return self._entries
            try:
                entries = loader()
                if not isinstance(entries, list):
                    raise ValueError("Provider returned an empty or invalid model catalog.")
            except Exception:
                self._expires = now + 60
                if self._entries is None:
                    raise
                # Reuse only previously observed entries; eligibility/expiry is
                # checked again by the resolver. Never guess a replacement.
                return self._entries
            self._entries = entries
            self._expires = now + MODEL_CATALOG["refreshSeconds"]
            return entries
