"""A save made with mods says which, and the Advisor, the Chronicle and a bug report are told.

The app's game knowledge describes the unmodded game. A campaign played with
Gigastructural Engineering has megastructures and resources that knowledge does
not cover, and the Advisor had no way to know the game was modded.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

import backend.api.server as server
from backend.core.chronicle import _chronicle_game_knowledge
from backend.core.chronicle_store import compact_chronicle_context
from backend.core.ingestion import IngestionManager
from backend.core.model_briefing import build_model_briefing
from tests.report_regressions._synthetic import (
    advisor_request,
    country,
    ingest_synthetic_save,
    synthetic_meta,
    write_meta_only_save,
)

SECTIONS = {
    "player": [{"name": "Reporter", "country": "0"}],
    "country": {
        "0": country(
            "Roaming Concord",
            government={"type": "gov_hive_mind", "authority": "auth_hive_mind", "civics": []},
            ethos={"ethic": "ethic_gestalt_consciousness"},
        )
    },
}
MODS = ["Gigastructural Engineering & More (4.5)", "UI Overhaul Dynamic"]


def _request(monkeypatch, tmp_path, mods):
    payload = ingest_synthetic_save(
        monkeypatch,
        tmp_path,
        SECTIONS,
        meta=synthetic_meta(name="Roaming Concord", version="Cygnus v4.5.2", mods=mods),
    )
    _, system_prompt, model_briefing = advisor_request(
        monkeypatch, payload, "Which megastructure should I build first?"
    )
    return payload, system_prompt, model_briefing


def test_the_advisor_is_told_which_mods_the_campaign_uses(monkeypatch, tmp_path):
    payload, system_prompt, model_briefing = _request(monkeypatch, tmp_path, MODS)

    assert payload["meta"]["mods"] == MODS
    assert model_briefing["meta"]["mods"] == MODS
    content = model_briefing["model_context"]["content_availability"]
    assert content["mods"] == MODS
    assert "go by the save" in content["mods_instruction"]
    # The rules the Advisor answers under name the mods too.
    assert "Gigastructural Engineering & More (4.5)" in system_prompt
    assert "describes the unmodded game" in system_prompt


def test_an_unmodded_campaign_says_nothing_about_mods(monkeypatch, tmp_path):
    _, system_prompt, model_briefing = _request(monkeypatch, tmp_path, None)

    assert "mods" not in model_briefing["meta"]
    assert "mods" not in model_briefing["model_context"]["content_availability"]
    assert '"mods"' not in system_prompt and "unmodded" not in system_prompt


def test_the_chronicle_is_told_which_mods_the_campaign_uses(monkeypatch, tmp_path):
    payload, _, _ = _request(monkeypatch, tmp_path, MODS)

    # The Chronicle writes from the compact context kept with each chapter.
    context = compact_chronicle_context(json.loads(payload["briefing_json"]))
    prompt = _chronicle_game_knowledge(build_model_briefing(context))

    assert context["meta"]["mods"] == MODS
    assert "Gigastructural Engineering & More (4.5)" in prompt
    assert "describes the unmodded game" in prompt


def test_a_bug_report_says_which_mods_the_game_uses(monkeypatch, tmp_path):
    """The quick read of a new save's header is the extractor's own reading of it."""
    monkeypatch.setenv(server.ENV_API_TOKEN, "test-token")
    save = write_meta_only_save(
        tmp_path / "modded.sav", synthetic_meta(name="Flagellant Concord", mods=MODS)
    )
    header = IngestionManager(companion=MagicMock(), db=MagicMock())._read_meta_only(save)
    assert header["name"] == "Flagellant Concord"
    assert header["mods"] == MODS

    app = server.create_app()
    app.state.companion = None
    app.state.ingestion = SimpleNamespace(get_status=lambda: {"t0_meta": header})
    with TestClient(app) as client:
        report = client.get(
            "/api/diagnostics", headers={"Authorization": "Bearer test-token"}
        ).json()

    assert report["mods"] == MODS
    assert report["empireName"] == "Flagellant Concord"
