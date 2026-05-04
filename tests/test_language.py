from pathlib import Path

from backend.core.database import GameDatabase
from backend.core.language import build_language_policy, language_name, normalize_language


def test_normalize_language_aliases() -> None:
    assert normalize_language("de-DE") == "de"
    assert normalize_language("pt_BR") == "pt-BR"
    assert normalize_language("zh-CN") == "zh-Hans"
    assert normalize_language("unknown") == "en"
    assert language_name("pt-BR") == "Brazilian Portuguese"


def test_language_policy_for_structured_json() -> None:
    policy = build_language_policy(
        "ja",
        structured_json=True,
        user_visible_fields=("title", "sections.text"),
    )

    assert "Japanese (ja)" in policy
    assert "required English schema keys" in policy
    assert "title, sections.text" in policy
    assert "Preserve empire names" in policy


def test_chronicle_cache_is_scoped_by_language(tmp_path: Path) -> None:
    db = GameDatabase(db_path=tmp_path / "chronicle-language.db")
    try:
        assert db.get_schema_version() >= 9

        db.upsert_chronicle_by_save_id(
            save_id="save-123",
            session_id="session-en",
            chronicle_text="English chronicle",
            chapters_json='{"chapters":[]}',
            event_count=1,
            snapshot_count=1,
            language="en",
        )
        db.upsert_chronicle_by_save_id(
            save_id="save-123",
            session_id="session-de",
            chronicle_text="Deutsche Chronik",
            chapters_json='{"chapters":[]}',
            event_count=1,
            snapshot_count=1,
            language="de",
        )

        english = db.get_chronicle_by_save_id("save-123", language="en")
        german = db.get_chronicle_by_save_id("save-123", language="de")

        assert english is not None
        assert german is not None
        assert english["chronicle_text"] == "English chronicle"
        assert german["chronicle_text"] == "Deutsche Chronik"
    finally:
        db.close()


def test_advisor_memory_is_scoped_by_language(tmp_path: Path) -> None:
    db = GameDatabase(db_path=tmp_path / "memory-language.db")
    try:
        db.upsert_advisor_memory_summary(
            save_id="save-123",
            language="en",
            summary_text="English advice",
        )
        db.upsert_advisor_memory_summary(
            save_id="save-123",
            language="fr",
            summary_text="Conseil francais",
        )

        assert db.get_advisor_memory_summary("save-123", language="en") == "English advice"
        assert db.get_advisor_memory_summary("save-123", language="fr") == "Conseil francais"
        assert db.get_advisor_memory_summary("save-123", language="de") is None
    finally:
        db.close()
