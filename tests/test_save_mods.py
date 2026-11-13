"""A save made with mods says which, and the Advisor is told.

The app's game knowledge describes the unmodded game. A campaign played with
Gigastructural Engineering has megastructures and resources that knowledge does
not cover, and the Advisor had no way to know the game was modded.
"""

from __future__ import annotations

from tests.report_regressions._synthetic import (
    advisor_request,
    country,
    ingest_synthetic_save,
    synthetic_meta,
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
