from __future__ import annotations

from stellaris_save_extractor import endgame
from stellaris_save_extractor.endgame import EndgameMixin


class _RegexLgateExtractor(EndgameMixin):
    def __init__(self, gamestate: str) -> None:
        self.gamestate = gamestate

    def get_player_empire_id(self) -> int:
        return 0

    def _find_player_country_content(self, _player_id: int) -> str:
        return ""


def test_repeatable_lcluster_technology_does_not_mean_lgate_opened(monkeypatch) -> None:
    monkeypatch.setattr(endgame, "_get_active_session", lambda: None)
    extractor = _RegexLgateExtractor(
        'galaxy={ lgate_enabled=yes } potential={ technology="tech_repeatable_lcluster_clue" }'
    )

    result = extractor.get_lgate_status()

    assert result["lgate_enabled"] is True
    assert result["lgate_opened"] is False


def test_explicit_lcluster_opened_flag_is_detected(monkeypatch) -> None:
    monkeypatch.setattr(endgame, "_get_active_session", lambda: None)
    extractor = _RegexLgateExtractor("lgate_enabled=yes flags={ l_cluster_opened=yes }")

    assert extractor.get_lgate_status()["lgate_opened"] is True
