"""Naval-capacity misreadings reported by players (#15)."""

from __future__ import annotations

from ._synthetic import advisor_request, country, ingest_synthetic_save


def test_issue_15_naval_usage_below_cap_is_not_presented_as_full(monkeypatch, tmp_path):
    """https://github.com/gitmaan/stellaris-companion/issues/15

    The save stores only current naval usage (``used_naval_capacity``); the
    cap is derived from modifiers. Usage of 48 against a fully modelled cap of
    125 was presented to the model as if the empire were at full capacity.
    """
    sections = {
        "player": [{"name": "Reporter", "country": "0"}],
        "galaxy": {"difficulty": "ensign"},
        "country": {
            "0": country(
                "Fleet Union",
                used_naval_capacity="48",
                fleet_size="48",
                government={"civics": []},
                tech_status={
                    "technology": ["tech_doctrine_navy_size_1", "tech_doctrine_navy_size_2"],
                    "level": ["1", "1"],
                },
            )
        },
    }
    payload = ingest_synthetic_save(monkeypatch, tmp_path, sections)

    _, system_prompt, model_briefing = advisor_request(
        monkeypatch, payload, "Am I at full naval capacity?"
    )

    naval = model_briefing["military"]["naval_capacity"]
    assert naval["used"] == 48
    assert naval.get("max") == 125
    assert naval["analysis"]["status"] == "under"
    assert naval["analysis"]["safe_to_claim_over_cap"] is True
    assert "not the empire's naval capacity limit" in naval["_note"]

    assert "it is current usage, not the naval cap ceiling" in system_prompt
    assert "current naval usage is 48; confirmed naval capacity is 125." in system_prompt
    assert "the empire is below naval cap" in system_prompt
