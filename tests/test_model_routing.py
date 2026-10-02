import pytest

from backend.core.model_routing import (
    GEMINI_FLASH_LITE_MODEL,
    GEMINI_FLASH_LITE_RESERVE_MODEL,
    GEMINI_FLASH_MODEL,
    GOOGLE_GEMMA_MODEL,
    ModelFailure,
    classify_model_error,
    clear_model_state,
    get_model_unavailable_event,
    is_model_temporarily_unavailable,
    mark_model_failure,
    route_models_for,
)


def test_quality_first_routes_flash_then_lite_then_reserve():
    assert route_models_for(mode="quality_first", purpose="advisor") == [
        GEMINI_FLASH_MODEL,
        GEMINI_FLASH_LITE_MODEL,
        GEMINI_FLASH_LITE_RESERVE_MODEL,
    ]
    assert route_models_for(mode="quality_first", purpose="chronicle") == [
        GEMINI_FLASH_MODEL,
        GEMINI_FLASH_LITE_MODEL,
        GEMINI_FLASH_LITE_RESERVE_MODEL,
    ]


def test_default_routes_like_standard_quota():
    assert route_models_for(mode=None, purpose="advisor") == [
        GEMINI_FLASH_LITE_MODEL,
        GEMINI_FLASH_LITE_RESERVE_MODEL,
    ]
    assert route_models_for(mode=None, purpose="chronicle") == [
        GEMINI_FLASH_MODEL,
        GEMINI_FLASH_LITE_MODEL,
        GEMINI_FLASH_LITE_RESERVE_MODEL,
    ]


def test_conserve_uses_flash_lite_for_advisor_but_flash_for_chronicle():
    assert route_models_for(mode="conserve", purpose="advisor") == [
        GEMINI_FLASH_LITE_MODEL,
        GEMINI_FLASH_LITE_RESERVE_MODEL,
    ]
    assert route_models_for(mode="conserve", purpose="chronicle") == [
        GEMINI_FLASH_MODEL,
        GEMINI_FLASH_LITE_MODEL,
        GEMINI_FLASH_LITE_RESERVE_MODEL,
    ]


def test_quota_saver_alias_maps_to_conserve():
    assert route_models_for(mode="quota_saver", purpose="advisor") == [
        GEMINI_FLASH_LITE_MODEL,
        GEMINI_FLASH_LITE_RESERVE_MODEL,
    ]


def test_gemma_remains_available_as_explicit_override():
    assert route_models_for(
        mode="quality_first",
        purpose="advisor",
        explicit_model=GOOGLE_GEMMA_MODEL,
    ) == [GOOGLE_GEMMA_MODEL]


def test_classify_daily_quota_error():
    failure = classify_model_error(
        "429 RESOURCE_EXHAUSTED Quota exceeded for quotaId': "
        "'GenerateRequestsPerDayPerProjectPerModel-FreeTier', quotaValue': '20'"
    )

    assert failure is not None
    assert failure.reason == "daily_quota"
    assert failure.quota_id == "GenerateRequestsPerDayPerProjectPerModel-FreeTier"
    assert failure.quota_value == "20"


def test_mark_rate_limit_failure_makes_flash_temporarily_unavailable():
    clear_model_state()
    try:
        mark_model_failure(
            GEMINI_FLASH_MODEL,
            ModelFailure(
                reason="rate_limit",
                message="429 RESOURCE_EXHAUSTED",
                retry_after_s=30,
            ),
        )

        assert is_model_temporarily_unavailable(GEMINI_FLASH_MODEL)
        event = get_model_unavailable_event(
            requested_model=GEMINI_FLASH_MODEL,
            skipped_model=GEMINI_FLASH_MODEL,
            final_model=GEMINI_FLASH_LITE_MODEL,
        )

        assert event is not None
        assert event.fallback is True
        assert (
            event.notice == "Gemini 3.8 Flash is cooling down. Routing via Gemini 3.5 Flash-Lite."
        )
    finally:
        clear_model_state()


@pytest.mark.parametrize(
    "message",
    ["429 daily quota exhausted", "429 requests_per_day exceeded", "429 requests per day exceeded"],
)
def test_daily_quota_messages_use_the_daily_cooldown(message):
    assert classify_model_error(message).reason == "daily_quota"


@pytest.mark.parametrize(
    "message",
    [
        "429 spend-based rate limit",
        "429 spending limit exceeded",
        "429 account-wide quota exhausted",
    ],
)
def test_account_limits_are_not_model_quotas(message):
    assert classify_model_error(message).reason == "account_limit"


def test_quota_message_linking_to_billing_is_still_a_model_quota():
    failure = classify_model_error(
        "429 You exceeded your current quota, please check your plan and billing details. "
        "Quota exceeded for GenerateRequestsPerDayPerProjectPerModel-FreeTier"
    )
    assert failure.reason == "daily_quota"
