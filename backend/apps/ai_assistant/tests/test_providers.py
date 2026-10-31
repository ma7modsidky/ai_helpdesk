"""The provider adapter: selection, determinism, failure modelling, and no network (T6.1)."""

from __future__ import annotations

import socket
from typing import Any

import pytest
from django.core.exceptions import ImproperlyConfigured

from apps.ai_assistant.providers import (
    AIProvider,
    AIProviderError,
    AIProviderRateLimited,
    AIProviderTimeout,
    AIProviderUnavailable,
    AIResponseInvalid,
    CompletionRequest,
    FakeAIProvider,
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
