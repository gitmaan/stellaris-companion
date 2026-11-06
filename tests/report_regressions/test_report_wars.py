"""War-history misreadings reported by players (#11, #44)."""

from __future__ import annotations

from ._synthetic import advisor_request, country, ingest_synthetic_save, synthetic_meta, system

PLAYER = "0"


def _battle(attackers, defenders, *, war_attacker_won, attacker_losses, defender_losses):
    """One battle record. Results and losses are relative to the parent war sides."""
    return {
        "attackers": list(attackers),
        "defenders": list(defenders),
        "attacker_victory": "yes" if war_attacker_won else "no",
        "attacker_losses": str(attacker_losses),
        "defender_losses": str(defender_losses),
        "system": "9",
        "type": "ships",
    }


def _war_save(*, war_attackers, war_defenders, battles, countries, extra=None):
    sections = {
        "player": [{"name": "Reporter", "country": PLAYER}],
        "country": countries,
        "galactic_object": {"8": system("Home Reach"), "9": system("Enemy Prime")},
        "war": {
            "0": {
                "name": {"key": "Synthetic War", "literal": "yes"},
                "start_date": "2290.01.01",
                "attackers": [{"country": cid} for cid in war_attackers],
                "defenders": [{"country": cid} for cid in war_defenders],
                "attacker_war_goal": {"type": "wg_conquest"},
                "battles": battles,
            }
        },
    }
    sections.update(extra or {})
    return sections


def test_issue_11_allied_only_battles_are_not_counted_as_player_defeats(monkeypatch, tmp_path):
    """https://github.com/gitmaan/stellaris-companion/issues/11

    The player and an ally defend against one attacker. The ally loses six
    battles the player never fought in; the player wins all four of its own.
    Coalition-wide attribution reported the ally's defeats as the player's.
    """
    ally, enemy = "1", "15"
    ally_defeats = [
        _battle([enemy], [ally], war_attacker_won=True, attacker_losses=1, defender_losses=8)
        for _ in range(6)
    ]
    player_victories = [
        _battle([PLAYER], [enemy], war_attacker_won=False, attacker_losses=7, defender_losses=2)
        for _ in range(4)
    ]
    sections = _war_save(
        war_attackers=[enemy],
        war_defenders=[PLAYER, ally],
        battles=ally_defeats + player_victories,
        countries={
            PLAYER: country("Reporter Republic"),
            ally: country("Allied Hegemony"),
            enemy: country("Aggressor Imperium"),
        },
    )

    payload = ingest_synthetic_save(monkeypatch, tmp_path, sections)
    _, _, model_briefing = advisor_request(monkeypatch, payload, "How is my war going?")

    [war] = model_briefing["military"]["wars"]["wars"]
    stats = war["battle_stats"]
    assert war["our_side"] == "defender"
    assert stats["player_involved_battles"] == 4
    assert stats["our_side_victories"] == 4
    assert stats["opposing_side_victories"] == 0
    assert stats["our_side_ship_losses"] == 4 * 2
    assert stats["opposing_side_ship_losses"] == 4 * 7
    scope = model_briefing["model_context"]["military"]["wars"]["participation_scope"]
    assert "allied-only engagements are excluded" in scope


def test_issue_44_won_battles_in_reversed_tactical_order_reach_advisor_as_victories(
    monkeypatch, tmp_path
):
    """https://github.com/gitmaan/stellaris-companion/issues/44

    Reported as "0:47 defeats" while every enemy capital was occupied. The
    player started the war, but each battle lists the player as the tactical
    defender. ``attacker_victory`` and losses refer to the parent war's
    attacker, so every one of the 47 battles is a player victory.
    """
    enemy = "15"
    battles = [
        _battle([enemy], [PLAYER], war_attacker_won=True, attacker_losses=1, defender_losses=12)
        for _ in range(47)
    ]
    sections = _war_save(
        war_attackers=[PLAYER],
        war_defenders=[enemy],
        battles=battles,
        countries={
            PLAYER: country("Voor Technocracy 9", capital="1"),
            enemy: country(
                "Occupied Imperium",
                capital="2",
                fleets_manager={
                    "owned_fleets": [
                        {"fleet": "500", "ownership_status": "lost_control", "debtor": PLAYER}
                    ]
                },
            ),
        },
        extra={
            "colony": {
                "1": {
                    "controller": PLAYER,
                    "coordinate": {"origin": "8"},
                    "name": {"key": "Voor Home", "literal": "yes"},
                },
                "2": {
                    "controller": PLAYER,
                    "coordinate": {"origin": "9"},
                    "name": {"key": "Imperial Throneworld", "literal": "yes"},
                },
            },
            "fleet": {
                "500": {"station": "yes", "movement_manager": {"coordinate": {"origin": "9"}}}
            },
        },
    )

    payload = ingest_synthetic_save(
        monkeypatch,
        tmp_path,
        sections,
        meta=synthetic_meta(name="Voor Technocracy 9", date="2303.01.01"),
    )
    _, system_prompt, model_briefing = advisor_request(
        monkeypatch, payload, "Am I winning or losing my war?"
    )

    [war] = model_briefing["military"]["wars"]["wars"]
    stats = war["battle_stats"]
    assert war["our_side"] == "attacker"
    assert stats["player_involved_battles"] == 47
    assert stats["our_side_victories"] == 47
    assert stats["opposing_side_victories"] == 0
    assert stats["our_side_ship_losses"] == 47
    assert stats["opposing_side_ship_losses"] == 47 * 12

    control = war["strategic_control"]
    assert [c["empire"] for c in control["enemy_capital_colonies_occupied_by_our_side"]] == [
        "Occupied Imperium"
    ]
    assert control["player_capital_colony_occupied_by_enemy_side"] is False
    assert (
        "not a complete measure"
        in (model_briefing["model_context"]["military"]["wars"]["assessment_rule"])
    )
    assert "Current EMPIRE STATE overrides SAVE MEMORY" in system_prompt
