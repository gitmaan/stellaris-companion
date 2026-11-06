"""Content-availability and identity misreadings reported by players (#81)."""

from __future__ import annotations

from ._synthetic import advisor_request, country, ingest_synthetic_save, synthetic_meta

# A plausible reported DLC list for a 4.4.6 save that never lists Synthetic Dawn,
# which has been base-game content since 4.3.6.
REPORTED_DLCS = ["Federations", "Nemesis", "Overlord", "The Machine Age"]


def test_issue_81_observed_rogue_servitor_is_not_denied_for_unreported_dlc(monkeypatch, tmp_path):
    """https://github.com/gitmaan/stellaris-companion/issues/81

    A Rogue Servitor machine empire in a Pegasus 4.4.6 save whose reported DLC
    list omits Synthetic Dawn. The app inferred "Synthetic Dawn missing" from
    that list, and the Advisor refused to discuss a civic the save shows.
    """
    sections = {
        "player": [{"name": "Reporter", "country": "0"}],
        "country": {
            "0": country(
                "Omniplex",
                government={
                    "type": "gov_machine_intelligence",
                    "authority": "auth_machine_intelligence",
                    "civics": ["civic_machine_servitor", "civic_machine_replication"],
                },
                ethos={"ethic": "ethic_gestalt_consciousness"},
            )
        },
    }
    payload = ingest_synthetic_save(
        monkeypatch,
        tmp_path,
        sections,
        meta=synthetic_meta(
            name="Omniplex",
            date="2308.04.01",
            version="Pegasus v4.4.6",
            required_dlcs=REPORTED_DLCS,
        ),
    )

    # Worker metadata still carries the legacy inference; it must not deny base-game packs.
    assert "Synthetic Dawn" not in payload["meta"].get("missing_dlcs", [])

    companion, system_prompt, model_briefing = advisor_request(
        monkeypatch, payload, "Rogue Servitor achievements: what is available?"
    )

    assert "missing_dlcs" not in model_briefing["meta"]
    content = model_briefing["model_context"]["content_availability"]
    assert content["dlc_evidence_status"] == "reported"
    assert content["reported_dlcs"] == REPORTED_DLCS
    assert "Synthetic Dawn" in content["base_game_dlcs"]
    assert content["unreported_dlc_status"] == "unknown"

    identity = model_briefing["model_context"]["empire_identity"]
    assert identity["authority"]["name"] == "Machine Intelligence"
    assert identity["civics"][0] == {
        "id": "machine_servitor",
        "name": "Rogue Servitor",
        "kind": "civic",
        "source": "verified_catalog",
    }

    for prompt in (system_prompt, companion.system_prompt):
        assert "do NOT exist" not in prompt
        assert "MISSING" not in prompt
    assert "Rogue Servitor" in system_prompt
    assert "must not be denied because a generic DLC assumption contradicts it" in system_prompt
