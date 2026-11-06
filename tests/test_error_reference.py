"""Unexpected Advisor failures become typed errors with privacy-safe references (#86)."""

import json
from types import SimpleNamespace

import httpx
import pytest

from backend.core.advisor_providers import AdvisorProviderError
from backend.core.companion import Companion
from backend.core.error_reference import error_reference, local_failure_cause

SECRET_PATH = "C:/Users/private-name/AppData/certifi/cacert.pem"


def _raise_missing_file():
    raise FileNotFoundError(2, "No such file or directory", SECRET_PATH)


def test_reference_names_type_errno_and_frame_without_message_or_path():
    with pytest.raises(FileNotFoundError) as caught:
        _raise_missing_file()

    reference = error_reference(caught.value)

    assert reference.startswith("FileNotFoundError errno=2 @ test_error_reference.py:")
    assert reference.endswith(" _raise_missing_file")
    assert "private-name" not in reference
    assert "No such file" not in reference
    assert len(reference) <= 160


def test_local_failure_cause_finds_os_errors_but_not_http_failures():
    try:
        try:
            _raise_missing_file()
        except OSError as exc:
            raise AdvisorProviderError("unavailable", code="CHATGPT_UNAVAILABLE") from exc
    except AdvisorProviderError as exc:
        assert isinstance(local_failure_cause(exc), FileNotFoundError)

    request = httpx.Request("POST", "http://127.0.0.1:1/generate")
    try:
        try:
            raise httpx.HTTPStatusError(
                "429", request=request, response=httpx.Response(429, request=request)
            )
        except httpx.HTTPError as exc:
            raise AdvisorProviderError("limited", code="PROVIDER_RATE_LIMITED") from exc
    except AdvisorProviderError as exc:
        assert local_failure_cause(exc) is None


class _FailingGenerator:
    def __init__(self, exc):
        self.exc = exc

    def generate(self, **kwargs):
        raise self.exc


def _companion(monkeypatch, generator):
    monkeypatch.setattr(
        "backend.core.companion.genai.Client", lambda **kwargs: SimpleNamespace(models=None)
    )
    companion = Companion(
        auto_precompute=False,
        api_key="test-key",
        advisor_provider="chatgpt",
        advisor_model="test-model",
        advisor_api_key="test-key",
        advisor_generator=generator,
    )
    briefing = {
        "meta": {"version": "Pegasus v4.4.6", "date": "2300.01.01"},
        "identity": {"empire_name": "Test Empire", "authority": "democratic"},
        "situation": {},
    }
    companion.apply_precomputed_briefing(
        save_path=None,
        briefing_json=json.dumps(briefing),
        game_date="2300.01.01",
        identity=briefing["identity"],
        situation=briefing["situation"],
        metadata=briefing["meta"],
    )
    return companion


def _ask(companion):
    return companion.ask_precomputed_with_context(
        question="How is the economy?", session_key="errors", persist_memory=False
    )


def test_unexpected_failure_is_typed_not_returned_as_advisor_prose(monkeypatch, caplog):
    def explode(**kwargs):
        _raise_missing_file()

    generator = _FailingGenerator(None)
    generator.generate = explode
    companion = _companion(monkeypatch, generator)

    with caplog.at_level("ERROR", logger="stellaris.companion"):
        with pytest.raises(AdvisorProviderError) as caught:
            _ask(companion)

    error = caught.value
    assert error.code == "ADVISOR_INTERNAL_ERROR"
    assert error.status_code == 500
    assert error.reference.startswith("FileNotFoundError errno=2 @ ")
    assert "Errno" not in str(error) and SECRET_PATH not in str(error)
    assert isinstance(error.__cause__, FileNotFoundError)
    # The full traceback stays in the local log for opted-in diagnostics.
    assert any(record.exc_info for record in caplog.records)
    assert companion.get_call_stats()["error"]


def test_provider_error_from_local_os_failure_gains_reference(monkeypatch):
    def unavailable(**kwargs):
        try:
            _raise_missing_file()
        except OSError as exc:
            raise AdvisorProviderError(
                "ChatGPT is temporarily unavailable. Please try again.",
                code="CHATGPT_UNAVAILABLE",
                status_code=503,
            ) from exc

    generator = _FailingGenerator(None)
    generator.generate = unavailable
    companion = _companion(monkeypatch, generator)

    with pytest.raises(AdvisorProviderError) as caught:
        _ask(companion)

    assert caught.value.code == "CHATGPT_UNAVAILABLE"
    assert caught.value.reference.startswith("FileNotFoundError errno=2 @ ")


def test_provider_error_without_local_cause_has_no_reference(monkeypatch):
    companion = _companion(
        monkeypatch,
        _FailingGenerator(
            AdvisorProviderError("Limited", code="PROVIDER_RATE_LIMITED", status_code=429)
        ),
    )

    with pytest.raises(AdvisorProviderError) as caught:
        _ask(companion)

    assert caught.value.reference is None
