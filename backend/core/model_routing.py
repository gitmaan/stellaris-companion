"""Model routing helpers for Gemini API calls.

Keeps user-facing model names and quota fallback behavior consistent across
Advisor and Chronicle generation.
"""

from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

GEMINI_FLASH_MODEL = "gemini-3-flash-preview"
GEMINI_FLASH_LITE_MODEL = "gemini-3.1-flash-lite-preview"
GOOGLE_GEMMA_MODEL = "gemma-4-26b-a4b-it"

MODEL_ROUTING_QUALITY_FIRST = "quality_first"
MODEL_ROUTING_CONSERVE = "conserve"
DEFAULT_MODEL_ROUTING_MODE = MODEL_ROUTING_CONSERVE

ModelPurpose = Literal["advisor", "chronicle"]
ModelRoutingMode = Literal["quality_first", "conserve"]

_MODEL_DISPLAY_NAMES = {
    GEMINI_FLASH_MODEL: "Gemini Flash",
    "gemini-3-flash": "Gemini Flash",
    GEMINI_FLASH_LITE_MODEL: "Gemini Flash-Lite",
    "gemini-3.1-flash-lite": "Gemini Flash-Lite",
    GOOGLE_GEMMA_MODEL: "Google Gemma",
    "gemma-4-26b": "Google Gemma",
}


@dataclass
class ModelFailure:
    reason: str
    message: str
    retry_after_s: float | None = None
    quota_id: str | None = None
    quota_value: str | None = None


@dataclass
class ModelRouteEvent:
    requested_model: str
    attempted_model: str
    final_model: str
    fallback: bool
    reason: str | None = None
    notice: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["requested_model_display"] = display_model_name(self.requested_model)
        data["attempted_model_display"] = display_model_name(self.attempted_model)
        data["final_model_display"] = display_model_name(self.final_model)
        return data


@dataclass
class _ModelState:
    unavailable_until: float = 0.0
    reason: str | None = None
    notice: str | None = None


_MODEL_STATE: dict[str, _ModelState] = {}


def display_model_name(model_id: str | None) -> str:
    if not model_id:
        return "Unknown model"
    raw = str(model_id)
    if raw in _MODEL_DISPLAY_NAMES:
        return _MODEL_DISPLAY_NAMES[raw]
    lowered = raw.lower()
    for key, label in _MODEL_DISPLAY_NAMES.items():
        if key in lowered:
            return label
    return raw


def normalize_model_routing_mode(raw_value: Any) -> ModelRoutingMode:
    if not isinstance(raw_value, str):
        return DEFAULT_MODEL_ROUTING_MODE
    normalized = raw_value.strip().lower().replace("-", "_")
    if normalized in {"auto", "quality", "quality_first", "flash_first"}:
        return MODEL_ROUTING_QUALITY_FIRST
    if normalized in {"conserve", "quota_saver", "free_tier", "lite_first", "flash_lite_first"}:
        return MODEL_ROUTING_CONSERVE
    return DEFAULT_MODEL_ROUTING_MODE


def route_models_for(
    *,
    mode: str | None,
    purpose: ModelPurpose,
    explicit_model: str | None = None,
) -> list[str]:
    if explicit_model:
        return [explicit_model]

    routing_mode = normalize_model_routing_mode(mode)
    if routing_mode == MODEL_ROUTING_CONSERVE and purpose == "advisor":
        return [GEMINI_FLASH_LITE_MODEL]
    return [GEMINI_FLASH_MODEL, GEMINI_FLASH_LITE_MODEL]


def is_model_temporarily_unavailable(model_id: str, *, now: float | None = None) -> bool:
    state = _MODEL_STATE.get(model_id)
    if state is None:
        return False
    timestamp = time.time() if now is None else now
    if state.unavailable_until <= timestamp:
        _MODEL_STATE.pop(model_id, None)
        return False
    return True


def get_model_unavailable_event(
    *,
    requested_model: str,
    skipped_model: str,
    final_model: str,
) -> ModelRouteEvent | None:
    state = _MODEL_STATE.get(skipped_model)
    if state is None:
        return None
    return ModelRouteEvent(
        requested_model=requested_model,
        attempted_model=skipped_model,
        final_model=final_model,
        fallback=True,
        reason=state.reason,
        notice=state.notice,
    )


def mark_model_failure(model_id: str, failure: ModelFailure) -> None:
    now = time.time()
    if failure.reason == "daily_quota":
        unavailable_until = _next_pacific_midnight_ts()
    elif failure.reason == "billing":
        unavailable_until = now + 6 * 60 * 60
    else:
        unavailable_until = now + max(float(failure.retry_after_s or 60.0), 5.0)

    _MODEL_STATE[model_id] = _ModelState(
        unavailable_until=unavailable_until,
        reason=failure.reason,
        notice=fallback_notice(model_id, GEMINI_FLASH_LITE_MODEL, reason=failure.reason),
    )


def clear_model_state() -> None:
    """Clear process-local routing state. Intended for tests."""
    _MODEL_STATE.clear()


def classify_model_error(error: BaseException | str) -> ModelFailure | None:
    text = str(error)
    lowered = text.lower()

    if "no available credits" in lowered or "billing" in lowered and "quota" not in lowered:
        return ModelFailure(
            reason="billing",
            message=text,
            retry_after_s=None,
            quota_id=_match(text, r"quotaId': '([^']+)'"),
            quota_value=_match(text, r"quotaValue': '([^']+)'"),
        )

    is_quota = (
        "429" in text
        or "resource_exhausted" in lowered
        or "quota" in lowered
        or "rate limit" in lowered
    )
    if not is_quota:
        return None

    quota_id = _match(text, r"quotaId': '([^']+)'")
    quota_value = _match(text, r"quotaValue': '([^']+)'")
    retry_after_s = _parse_retry_after(text)

    reason = "quota"
    quota_text = f"{quota_id or ''} {lowered}"
    if "perday" in quota_text or "requestsperday" in quota_text:
        reason = "daily_quota"
    elif "perminute" in quota_text or "requestsperminute" in quota_text:
        reason = "rate_limit"

    return ModelFailure(
        reason=reason,
        message=text,
        retry_after_s=retry_after_s,
        quota_id=quota_id,
        quota_value=quota_value,
    )


def fallback_notice(from_model: str, to_model: str, *, reason: str | None = None) -> str:
    from_name = display_model_name(from_model)
    to_name = display_model_name(to_model)
    if reason == "rate_limit":
        return f"{from_name} is cooling down. Routing via {to_name}."
    return f"{from_name} is at capacity. Routing via {to_name}."


def route_event_payload(event: ModelRouteEvent | None) -> dict[str, Any] | None:
    return event.to_dict() if event is not None else None


def _match(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1) if match else None


def _parse_retry_after(text: str) -> float | None:
    for pattern in [
        r"Please retry in ([0-9.]+)s",
        r"'retryDelay': '([0-9.]+)s'",
        r'"retryDelay":\s*"([0-9.]+)s"',
    ]:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
    return None


def _next_pacific_midnight_ts() -> float:
    try:
        pacific = ZoneInfo("America/Los_Angeles")
        now = datetime.now(pacific)
        tomorrow = now.date() + timedelta(days=1)
        reset = datetime.combine(tomorrow, datetime.min.time(), tzinfo=pacific)
        return reset.timestamp()
    except Exception:
        return time.time() + 24 * 60 * 60
