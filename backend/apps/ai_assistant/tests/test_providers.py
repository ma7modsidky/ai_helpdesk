"""The provider adapters: selection, determinism, failure modelling, and no network (T6.1)."""

from __future__ import annotations

import http.client
import io
import json
import socket
import urllib.error
from collections.abc import Callable
from typing import Any

import pytest
from django.core.exceptions import ImproperlyConfigured

from apps.ai_assistant.providers import (
    GEMINI_ENDPOINT,
    AIProvider,
    AIProviderError,
    AIProviderRateLimited,
    AIProviderTimeout,
    AIProviderUnavailable,
    AIResponseInvalid,
    CompletionRequest,
    FakeAIProvider,
    GeminiAIProvider,
    get_provider,
)


def _request(prompt: str = "Classify: charged twice") -> CompletionRequest:
    return CompletionRequest(prompt=prompt, model="fake-model-v1")


def test_the_default_provider_is_the_deterministic_fake(settings: Any) -> None:
    assert settings.AI_PROVIDER == "fake"

    provider = get_provider()

    assert isinstance(provider, FakeAIProvider)
    assert isinstance(provider, AIProvider)


def test_an_unknown_provider_fails_before_any_work_is_queued() -> None:
    with pytest.raises(ImproperlyConfigured, match="Unknown AI provider") as caught:
        get_provider("not-a-vendor")

    # Actionable: names the bad value and the valid ones.
    assert "not-a-vendor" in str(caught.value)
    assert "fake" in str(caught.value)


def test_the_adapter_carries_the_configured_model_and_timeout(settings: Any) -> None:
    settings.AI_MODEL = "configured-model"
    settings.AI_REQUEST_TIMEOUT_SECONDS = 7

    provider = get_provider()

    assert provider.model == "configured-model"
    assert provider.timeout_seconds == 7


def test_the_fake_provider_is_deterministic() -> None:
    provider = FakeAIProvider()

    first = provider.complete(_request()).text
    second = FakeAIProvider().complete(_request()).text
    other = provider.complete(_request("Classify: refund request")).text

    assert first == second
    assert first != other


def test_scripted_responses_are_returned_in_order_then_fall_back() -> None:
    provider = FakeAIProvider(responses=('{"category": "billing"}', '{"category": "other"}'))

    assert provider.complete(_request()).text == '{"category": "billing"}'
    assert provider.complete(_request()).text == '{"category": "other"}'
    assert provider.complete(_request()).text.startswith("fake-completion:")


def test_the_provider_records_what_it_was_asked() -> None:
    provider = FakeAIProvider()

    provider.complete(_request("A specific prompt"))

    assert [request.prompt for request in provider.calls] == ["A specific prompt"]


def test_a_provider_failure_is_raised_as_the_modelled_error() -> None:
    provider = FakeAIProvider(fail_with=AIProviderTimeout("timed out"))

    with pytest.raises(AIProviderTimeout):
        provider.complete(_request())


def test_retryability_is_a_property_of_the_error_type() -> None:
    # Transient: another attempt may succeed.
    assert AIProviderTimeout().retryable is True
    assert AIProviderUnavailable().retryable is True
    assert AIProviderRateLimited().retryable is True
    # Permanent: the same prompt produces the same bad output.
    assert AIResponseInvalid().retryable is False
    assert AIProviderError().retryable is False


def test_errors_never_quote_the_prompt() -> None:
    prompt = "Customer card 4111 1111 1111 1111 was charged twice"
    provider = FakeAIProvider(fail_with=AIProviderTimeout())

    with pytest.raises(AIProviderTimeout) as caught:
        provider.complete(_request(prompt))

    # A vendor exception can quote the prompt; the adapter's own message must not, because
    # this text reaches logs and, eventually, an API response.
    assert "4111" not in str(caught.value)
    assert "4111" not in repr(caught.value)


def test_the_fake_provider_needs_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _no_network(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the fake provider must not open a socket")

    monkeypatch.setattr(socket, "socket", _no_network)
    monkeypatch.setattr(socket, "create_connection", _no_network)

    completion = FakeAIProvider().complete(_request())

    assert completion.text.startswith("fake-completion:")
    assert completion.provider == "fake"


def test_the_completion_reports_its_provenance_and_latency() -> None:
    completion = FakeAIProvider(latency_ms=12.5).complete(_request())

    assert completion.provider == "fake"
    assert completion.model == "fake-model-v1"
    assert completion.latency_ms == 12.5


def test_an_empty_prompt_is_rejected() -> None:
    with pytest.raises(ValueError, match="non-empty prompt"):
        CompletionRequest(prompt="   ", model="fake-model-v1")


def test_a_request_needs_room_for_output() -> None:
    with pytest.raises(ValueError, match="max_output_tokens"):
        CompletionRequest(prompt="hello", model="fake-model-v1", max_output_tokens=0)


# --- The Gemini adapter (ADR-037) ----------------------------------------
# Every case answers through the injected opener: a unit test here must not open a socket.


class _FakeResponse:
    """Just enough of ``http.client.HTTPResponse``: the adapter uses it as a context manager."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


def _gemini_payload(text: str | None = '{"category": "billing"}') -> bytes:
    parts = [] if text is None else [{"text": text}]
    return json.dumps({"candidates": [{"content": {"role": "model", "parts": parts}}]}).encode()


def _answering(body: bytes, seen: list[Any] | None = None) -> Callable[..., _FakeResponse]:
    def opener(request: Any, *, timeout: int) -> _FakeResponse:
        if seen is not None:
            seen.append((request, timeout))
        return _FakeResponse(body)

    return opener


def _failing(error: BaseException) -> Callable[..., _FakeResponse]:
    def opener(request: Any, *, timeout: int) -> _FakeResponse:
        raise error

    return opener


def _http_error(status: int, body: bytes = b"") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://example.test",
        status,
        "vendor message",
        http.client.HTTPMessage(),
        io.BytesIO(body),
    )


def _gemini(**overrides: Any) -> GeminiAIProvider:
    options: dict[str, Any] = {
        "model": "gemini-3.5-flash-lite",
        "timeout_seconds": 20,
        "api_key": "test-key",
    }
    options.update(overrides)
    return GeminiAIProvider(**options)


def _gemini_request(model: str = "gemini-3.5-flash-lite") -> CompletionRequest:
    return CompletionRequest(prompt="Classify: charged twice", model=model)


def test_the_gemini_adapter_returns_the_first_candidates_text() -> None:
    completion = _gemini(opener=_answering(_gemini_payload())).complete(_gemini_request())

    assert completion.text == '{"category": "billing"}'
    assert completion.provider == "gemini"
    assert completion.model == "gemini-3.5-flash-lite"
    assert completion.latency_ms >= 0


def test_the_gemini_request_carries_the_key_in_a_header_never_in_the_url() -> None:
    seen: list[Any] = []
    provider = _gemini(opener=_answering(_gemini_payload(), seen))

    provider.complete(
        CompletionRequest(
            prompt="Classify: charged twice",
            model="models/gemini-3.5-flash-lite",
            max_output_tokens=256,
            temperature=0.2,
        )
    )

    request, timeout = seen[0]
    # The documented name carries the `models/` prefix; the REST path wants it bare.
    assert request.full_url == f"{GEMINI_ENDPOINT}/gemini-3.5-flash-lite:generateContent"
    assert "test-key" not in request.full_url
    assert request.get_header("X-goog-api-key") == "test-key"
    assert timeout == 20
    body = json.loads(request.data)
    assert body["contents"] == [{"role": "user", "parts": [{"text": "Classify: charged twice"}]}]
    assert body["generationConfig"] == {
        "temperature": 0.2,
        "maxOutputTokens": 256,
        "responseMimeType": "application/json",
        # Extraction, not reasoning: the thinking budget must not eat the output allowance.
        "thinkingConfig": {"thinkingLevel": "low"},
    }


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (429, AIProviderRateLimited),
        (500, AIProviderUnavailable),
        (503, AIProviderUnavailable),
    ],
)
def test_a_transient_gemini_status_is_retryable(
    status: int, expected: type[AIProviderError]
) -> None:
    with pytest.raises(expected) as caught:
        _gemini(opener=_failing(_http_error(status))).complete(_gemini_request())

    assert caught.value.retryable is True


def test_a_rejected_gemini_request_is_not_retried_and_never_quotes_the_body() -> None:
    # A vendor error body can echo the prompt, and the prompt contains customer text.
    error = _http_error(400, body=b"Customer card 4111 1111 1111 1111 was charged twice")

    with pytest.raises(AIProviderError) as caught:
        _gemini(opener=_failing(error)).complete(_gemini_request())

    assert type(caught.value) is AIProviderError
    assert caught.value.retryable is False
    assert "4111" not in str(caught.value)
    assert "GEMINI_API_KEY" in str(caught.value)


def test_a_gemini_timeout_is_retryable() -> None:
    with pytest.raises(AIProviderTimeout) as caught:
        _gemini(opener=_failing(TimeoutError("timed out"))).complete(_gemini_request())

    assert caught.value.retryable is True


def test_a_url_error_wrapped_timeout_is_reported_as_a_timeout() -> None:
    with pytest.raises(AIProviderTimeout):
        _gemini(opener=_failing(urllib.error.URLError(TimeoutError("timed out")))).complete(
            _gemini_request()
        )


def test_an_unreachable_gemini_host_is_retryable() -> None:
    with pytest.raises(AIProviderUnavailable) as caught:
        _gemini(opener=_failing(urllib.error.URLError(OSError("name resolution")))).complete(
            _gemini_request()
        )

    assert caught.value.retryable is True


def test_a_connection_error_outside_url_error_is_retryable() -> None:
    with pytest.raises(AIProviderUnavailable):
        _gemini(opener=_failing(ConnectionResetError("reset"))).complete(_gemini_request())


@pytest.mark.parametrize(
    "payload",
    [
        b"not json",
        b"[]",
        b'{"candidates": "none"}',
        b'{"candidates": []}',
        _gemini_payload(None),
        json.dumps({"candidates": [{"content": {"parts": [{"text": ""}]}}]}).encode(),
        json.dumps({"candidates": [{"content": {"parts": ["text"]}}]}).encode(),
        json.dumps({"candidates": [{"content": {}}]}).encode(),
        json.dumps({"candidates": [None]}).encode(),
    ],
)
def test_unusable_gemini_output_is_invalid_and_not_retried(payload: bytes) -> None:
    with pytest.raises(AIResponseInvalid) as caught:
        _gemini(opener=_answering(payload)).complete(_gemini_request())

    assert caught.value.retryable is False


def test_gemini_thinking_parts_are_not_mistaken_for_the_answer() -> None:
    # A reasoning model puts its thinking in text parts beside the answer; joining both would
    # prepend prose to the JSON and fail the schema on whichever runs it chose to think aloud.
    payload = json.dumps(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "The customer was charged twice.", "thought": True},
                            {"text": '{"category": "billing"}'},
                        ]
                    }
                }
            ]
        }
    ).encode()

    completion = _gemini(opener=_answering(payload)).complete(_gemini_request())

    assert completion.text == '{"category": "billing"}'


def test_a_blocked_gemini_prompt_is_invalid_not_retried() -> None:
    payload = json.dumps({"promptFeedback": {"blockReason": "SAFETY"}}).encode()

    with pytest.raises(AIResponseInvalid, match="blocked"):
        _gemini(opener=_answering(payload)).complete(_gemini_request())


def test_the_gemini_provider_is_selected_by_name_and_reads_its_key_from_the_environment(
    settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings.AI_MODEL = "gemini-3.5-flash-lite"
    monkeypatch.setenv("GEMINI_API_KEY", "from-the-environment")

    provider = get_provider("gemini")

    assert isinstance(provider, GeminiAIProvider)
    assert provider.name == "gemini"
    assert provider.model == "gemini-3.5-flash-lite"
    assert provider.timeout_seconds == settings.AI_REQUEST_TIMEOUT_SECONDS


def test_gemini_without_a_key_fails_before_any_work_is_queued(
    settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings.AI_MODEL = "gemini-3.5-flash-lite"
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(ImproperlyConfigured, match="GEMINI_API_KEY"):
        get_provider("gemini")


def test_gemini_with_the_fake_model_fails_with_an_actionable_message(
    settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings.AI_MODEL = "fake-model-v1"
    monkeypatch.setenv("GEMINI_API_KEY", "from-the-environment")

    with pytest.raises(ImproperlyConfigured, match="AI_MODEL") as caught:
        get_provider("gemini")

    assert "gemini-3.5-flash-lite" in str(caught.value)


def test_an_empty_gemini_key_is_refused() -> None:
    with pytest.raises(ImproperlyConfigured, match="GEMINI_API_KEY"):
        _gemini(api_key="   ")
