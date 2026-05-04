"""Language helpers for UI-selected LLM output.

The Electron app sends a resolved BCP-47-ish locale for each generated-text
request.  Backend code keeps the whitelist small and turns that locale into a
single prompt block shared by advisor, chronicle, and recap generation.
"""

from __future__ import annotations

from typing import Any

DEFAULT_LANGUAGE = "en"

SUPPORTED_LANGUAGES: dict[str, str] = {
    "en": "English",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "pt-BR": "Brazilian Portuguese",
    "ja": "Japanese",
    "zh-Hans": "Simplified Chinese",
    "en-XA": "English pseudo-locale",
}


def normalize_language(raw_value: Any) -> str:
    """Normalize a renderer-provided language tag to the supported set."""
    if not isinstance(raw_value, str):
        return DEFAULT_LANGUAGE

    value = raw_value.strip()
    if not value or value == "system":
        return DEFAULT_LANGUAGE
    if value == "pt_BR":
        return "pt-BR"
    if value in {"zh-CN", "zh_CN", "zh-Hans-CN"}:
        return "zh-Hans"
    if value in SUPPORTED_LANGUAGES:
        return value

    base = value.split("-")[0].split("_")[0].lower()
    if base in {"en", "de", "fr", "es", "ja"}:
        return base
    if base == "pt":
        return "pt-BR"
    if base == "zh":
        return "zh-Hans"
    return DEFAULT_LANGUAGE


def language_name(language: str | None) -> str:
    return SUPPORTED_LANGUAGES.get(
        normalize_language(language), SUPPORTED_LANGUAGES[DEFAULT_LANGUAGE]
    )


def build_language_policy(
    language: str | None,
    *,
    structured_json: bool = False,
    user_visible_fields: tuple[str, ...] = (),
) -> str:
    """Build the prompt block used to keep generated prose in one language."""
    normalized = normalize_language(language)
    name = language_name(normalized)
    lines = [
        "=== LANGUAGE POLICY ===",
        f"- Respond in {name} ({normalized}).",
        "- Preserve empire names, leader names, planet names, system names, ship names, numeric values, and JSON field names exactly as provided.",
        "- Use localized Stellaris terminology when confident; otherwise keep the original game term.",
        "- Do not mention this language policy.",
    ]
    if structured_json:
        fields = (
            ", ".join(user_visible_fields)
            if user_visible_fields
            else "all user-visible string values"
        )
        lines.extend(
            [
                "- Return valid JSON using the required English schema keys.",
                f"- The values for {fields} must be in the requested language.",
            ]
        )
    return "\n".join(lines)


_LOCALIZED_TEXT: dict[str, dict[str, str]] = {
    "could_not_generate": {
        "en": "Could not generate a response.",
        "de": "Es konnte keine Antwort erzeugt werden.",
        "fr": "Impossible de generer une reponse.",
        "es": "No se pudo generar una respuesta.",
        "pt-BR": "Nao foi possivel gerar uma resposta.",
        "ja": "応答を生成できませんでした。",
        "zh-Hans": "无法生成回复。",
    },
    "no_precomputed_state": {
        "en": "No precomputed game state is available yet. Please wait for a save to be processed.",
        "de": "Es ist noch kein vorberechneter Spielstand verfuegbar. Bitte warte, bis ein Speicherstand verarbeitet wurde.",
        "fr": "Aucun etat de partie pretraite n'est encore disponible. Attendez qu'une sauvegarde soit traitee.",
        "es": "Aun no hay un estado de partida precomputado disponible. Espera a que se procese una partida guardada.",
        "pt-BR": "Ainda nao ha um estado de jogo precomputado disponivel. Aguarde o processamento de um save.",
        "ja": "事前計算されたゲーム状態はまだ利用できません。セーブの処理が終わるまでお待ちください。",
        "zh-Hans": "尚无预计算的游戏状态。请等待存档处理完成。",
    },
    "loaded_from_cache": {
        "en": "Loaded from history cache; live save processing may still be running...",
        "de": "Aus dem Verlaufscache geladen; die Live-Verarbeitung des Speicherstands laeuft moeglicherweise noch...",
        "fr": "Charge depuis le cache d'historique; le traitement en direct de la sauvegarde peut encore etre en cours...",
        "es": "Cargado desde la cache de historial; el procesamiento en vivo del guardado podria seguir en curso...",
        "pt-BR": "Carregado do cache de historico; o processamento ao vivo do save ainda pode estar em andamento...",
        "ja": "履歴キャッシュから読み込みました。ライブのセーブ処理はまだ実行中の可能性があります...",
        "zh-Hans": "已从历史缓存加载；实时存档处理可能仍在运行...",
    },
    "no_events_recap": {
        "en": "No events to recap. The story has yet to begin.",
        "de": "Keine Ereignisse fuer eine Zusammenfassung. Die Geschichte hat noch nicht begonnen.",
        "fr": "Aucun evenement a resumer. L'histoire n'a pas encore commence.",
        "es": "No hay eventos que recapitular. La historia aun no ha comenzado.",
        "pt-BR": "Nao ha eventos para recapitular. A historia ainda nao comecou.",
        "ja": "要約するイベントはありません。物語はまだ始まっていません。",
        "zh-Hans": "没有可回顾的事件。故事尚未开始。",
    },
    "no_events_chronicle": {
        "en": "No events recorded yet. The chronicle awaits the first chapters of history.",
        "de": "Noch keine Ereignisse aufgezeichnet. Die Chronik wartet auf die ersten Kapitel der Geschichte.",
        "fr": "Aucun evenement enregistre. La chronique attend les premiers chapitres de l'histoire.",
        "es": "Aun no hay eventos registrados. La cronica espera los primeros capitulos de la historia.",
        "pt-BR": "Ainda nao ha eventos registrados. A cronica aguarda os primeiros capitulos da historia.",
        "ja": "記録されたイベントはまだありません。年代記は歴史の最初の章を待っています。",
        "zh-Hans": "尚未记录事件。编年史正等待历史的第一章。",
    },
    "current_era_fallback": {
        "en": "The current era unfolds...\n\nThe story continues...",
        "de": "Die aktuelle Aera entfaltet sich...\n\nDie Geschichte geht weiter...",
        "fr": "L'ere actuelle se deploie...\n\nL'histoire continue...",
        "es": "La era actual se despliega...\n\nLa historia continua...",
        "pt-BR": "A era atual se desenrola...\n\nA historia continua...",
        "ja": "現在の時代が展開していく...\n\n物語は続く...",
        "zh-Hans": "当前时代正在展开...\n\n故事仍在继续...",
    },
}


def localized_text(key: str, language: str | None) -> str:
    table = _LOCALIZED_TEXT.get(key, {})
    normalized = normalize_language(language)
    return table.get(normalized) or table.get(DEFAULT_LANGUAGE) or key
