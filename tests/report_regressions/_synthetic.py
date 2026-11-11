"""Hand-built synthetic saves for user-report regression cases.

A ``SyntheticSession`` is a tiny in-memory gamestate (section -> entries)
served through the same session API the Rust parser exposes. The real
ingestion worker and ``SaveExtractor`` run against it, so the cases exercise
production extraction code without a real save file, extracted save data, or
a parser binary. Every value is hand-written to encode one reported situation.

Only the session primitives that extractors use are implemented. Sections that
a case does not define behave like empty sections in a minimal save.
"""

from __future__ import annotations

import contextlib
import zipfile
from collections.abc import Iterator
from copy import deepcopy
from pathlib import Path
from typing import Any

from stellaris_companion import rust_bridge


class SyntheticSession:
    """In-memory stand-in for ``rust_bridge.RustSession``."""

    def __init__(
        self,
        sections: dict[str, Any],
        *,
        duplicate_values: dict[tuple[str, ...], list[str]] | None = None,
    ) -> None:
        self._sections = deepcopy(sections)
        self._duplicate_values = duplicate_values or {}
        self._streaming = False

    def _section(self, name: str) -> dict[str, Any]:
        value = self._sections.get(name)
        return value if isinstance(value, dict) else {}

    def extract_sections(self, sections: list[str]) -> dict:
        return {name: deepcopy(self._sections[name]) for name in sections if name in self._sections}

    def iter_section(
        self, section: str, batch_size: int = 100, *, timeout: float | None = None
    ) -> Iterator[tuple[str, Any]]:
        # The real session cannot nest streams: a second iter_section drains
        # the first. Fail loudly so a case never passes on an impossible order.
        if self._streaming:
            raise AssertionError(f"nested iter_section({section!r}) is not supported")
        self._streaming = True
        try:
            for key, value in list(self._section(section).items()):
                yield str(key), deepcopy(value)
        finally:
            self._streaming = False

    def get_entry(self, section: str, key: str) -> Any:
        value = self._section(section).get(str(key))
        return deepcopy(value) if value is not None else None

    def get_entries(
        self, section: str, keys: list[str], fields: list[str] | None = None
    ) -> list[dict]:
        entries = []
        data = self._section(section)
        for key in keys:
            if str(key) not in data:
                continue
            value = deepcopy(data[str(key)])
            if fields is None:
                entries.append({"_key": str(key), "_value": value})
            else:
                projected = {"_key": str(key)}
                if isinstance(value, dict):
                    projected.update({field: value[field] for field in fields if field in value})
                entries.append(projected)
        return entries

    def get_duplicate_values(
        self, section: str, key: str, field: str, within: str | None = None
    ) -> list[str]:
        """Mirror the Rust op: entry-wide by default, one child block with ``within``.

        A case that matters for the difference registers both
        ``(section, key, field)`` and ``(section, key, field, within)``. Cases that
        only register the entry-wide list get it for scoped lookups too.
        """
        values = self._duplicate_values
        if within is not None and (section, str(key), field, within) in values:
            return list(values[(section, str(key), field, within)])
        if within is not None and field != "technology":
            return []
        return list(values.get((section, str(key), field), []))

    def get_entry_text(self, section: str, key: str) -> str | None:
        return None

    def get_duplicate_blocks(self, section: str, key: str, field: str) -> list:
        return []

    def count_keys(self, keys: list[str]) -> dict:
        return {"counts": {key: 0 for key in keys}}

    def contains_tokens(self, tokens: list[str]) -> dict:
        return {"matches": {token: False for token in tokens}}

    def contains_kv(self, pairs: list[tuple[str, str]]) -> dict:
        return {"matches": {f"{key}={value}": False for key, value in pairs}}

    def get_country_summaries(self, fields: list[str]) -> dict:
        countries = []
        for country_id, country in self._section("country").items():
            if isinstance(country, dict):
                summary = {"id": str(country_id)}
                summary.update({field: country.get(field) for field in fields})
                countries.append(summary)
        return {"countries": countries}

    def batch_ops(self, ops: list[dict]) -> list[dict]:
        results = []
        for op in ops:
            kind = op.get("op")
            if kind == "get_entry":
                entry = self.get_entry(op["section"], op["key"])
                results.append({"found": entry is not None, "entry": entry})
            elif kind == "get_entries":
                entries = self.get_entries(op["section"], op["keys"], op.get("fields"))
                results.append({"entries": entries})
            elif kind == "extract_sections":
                results.append({"data": self.extract_sections(op["sections"])})
            elif kind == "get_duplicate_values":
                values = self.get_duplicate_values(op["section"], op["key"], op["field"])
                results.append({"values": values})
            else:
                raise AssertionError(f"batch op {kind!r} is not modelled by SyntheticSession")
        return results

    def close(self) -> None:
        return None


def write_meta_only_save(path: Path, meta: str) -> Path:
    """Write a .sav zip whose gamestate is empty; extraction uses the session."""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("meta", meta)
        archive.writestr("gamestate", "")
    return path


def synthetic_meta(
    *,
    name: str = "Synthetic Union",
    date: str = "2300.01.01",
    version: str = "Pegasus v4.4.6",
    required_dlcs: list[str] | None = None,
) -> str:
    lines = [f'version="{version}"', f'name="{name}"', f'date="{date}"']
    if required_dlcs is not None:
        quoted = " ".join(f'"{dlc}"' for dlc in required_dlcs)
        lines.append(f"required_dlcs={{ {quoted} }}")
    return "\n".join(lines) + "\n"


def country(name: str, **fields: Any) -> dict[str, Any]:
    """Minimal country entry with a literal name."""
    return {"name": {"key": name, "literal": "yes"}, "type": "default", **fields}


def system(name: str) -> dict[str, Any]:
    return {"name": {"key": name, "literal": "yes"}}


# --- Production pipeline drivers ------------------------------------------------
#
# These run the same functions the app runs on a new save, in-process: the
# ingestion worker (briefing, signals, history enrichment and worker metadata),
# snapshot persistence with event detection, and an Advisor request whose
# provider only records what would have been sent. No model is called.


def run_ingestion_worker(monkeypatch, save_path: Path, session: SyntheticSession) -> dict:
    """Run the ingestion worker's job body against a synthetic session."""
    import logging
    import queue

    from backend.core import ingestion_worker

    @contextlib.contextmanager
    def synthetic_rust_session(path):
        previous = getattr(rust_bridge._tls, "session", None)
        rust_bridge._tls.session = session
        try:
            yield session
        finally:
            rust_bridge._tls.session = previous

    monkeypatch.setattr(rust_bridge, "session", synthetic_rust_session)
    # The worker configures logging for its own subprocess; keep the test's.
    monkeypatch.setattr(logging, "basicConfig", lambda **kwargs: None)
    results: queue.Queue = queue.Queue()
    job = {"tier": "t2", "save_path": str(save_path), "requested_at": 0.0}
    ingestion_worker._process_main(job, results)  # type: ignore[arg-type]
    message = results.get_nowait()
    assert message.get("ok"), message.get("error")
    return message["payload"]


def ingest_synthetic_save(
    monkeypatch,
    tmp_path: Path,
    sections: dict[str, Any],
    *,
    meta: str | None = None,
    duplicate_values: dict[tuple[str, ...], list[str]] | None = None,
    filename: str = "synthetic.sav",
) -> dict:
    """Write a meta-only save and return the worker payload for it."""
    save_path = write_meta_only_save(tmp_path / filename, meta or synthetic_meta())
    session = SyntheticSession(sections, duplicate_values=duplicate_values)
    payload = run_ingestion_worker(monkeypatch, save_path, session)
    payload["save_path"] = save_path
    return payload


def persist_snapshot(db, payload: dict) -> tuple[bool, int | None, str]:
    """Persist a worker payload exactly as the ingestion manager does."""
    import json

    from backend.core.history import record_snapshot_from_briefing

    return record_snapshot_from_briefing(
        db=db,
        save_path=payload["save_path"],
        save_hash=payload.get("save_hash"),
        briefing=json.loads(payload["briefing_json"]),
        briefing_json=payload["briefing_json"],
    )


class RecordingAdvisor:
    """Advisor generator that records the request instead of calling a model."""

    def __init__(self) -> None:
        self.request: dict[str, Any] | None = None

    def generate(self, **kwargs):
        from backend.core.advisor_providers import AdvisorGenerationResult

        self.request = kwargs
        return AdvisorGenerationResult(
            text="Recorded.",
            model="synthetic-model",
            requested_model="synthetic-model",
            provider="openrouter",
            completion={"status": "complete"},
        )


def advisor_request(monkeypatch, payload: dict, question: str):
    """Activate a worker payload in a Companion and capture the Advisor request.

    Returns ``(companion, system_prompt, model_briefing)``, where
    ``model_briefing`` is the JSON campaign snapshot sent in the user prompt.
    """
    import json

    from backend.core.companion import Companion

    monkeypatch.setattr("backend.core.companion.genai.Client", lambda **kwargs: None)
    recorder = RecordingAdvisor()
    companion = Companion(
        auto_precompute=False,
        api_key="synthetic-key",
        advisor_provider="openrouter",
        advisor_model="synthetic-model",
        advisor_api_key="synthetic-key",
        advisor_generator=recorder,
    )
    companion.apply_precomputed_briefing(
        save_path=payload["save_path"],
        briefing_json=payload["briefing_json"],
        game_date=payload.get("game_date"),
        identity=payload.get("identity"),
        situation=payload.get("situation"),
        metadata=payload.get("meta"),
        save_hash=payload.get("save_hash"),
    )
    reply = companion.ask_precomputed_with_context(
        question=question, session_key="report-regression", persist_memory=False
    )
    assert "error" not in reply.stats, reply.stats
    assert recorder.request is not None
    user_prompt = recorder.request["user_prompt"]
    snapshot_json = user_prompt.split("```json\n", 1)[1].split("\n```", 1)[0]
    return companion, recorder.request["system_prompt"], json.loads(snapshot_json)
