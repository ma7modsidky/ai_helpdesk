"""The AI provider adapter (T6.1, ADR-034).

Everything that talks to a model goes through :class:`AIProvider`. The rest of the application
knows only four things about it: it takes a prompt, it returns text plus metadata, it can fail
with a small set of modelled errors, and it has a timeout. That is deliberate — prompts,
schemas, and validation belong to the calling code (T6.2), so swapping a vendor never moves a
business rule and a test never needs a network or an API key.

Two rules shape this module:

- **No provider text reaches a caller.** Error messages are written here, not copied from a
  vendor: a provider exception can quote the prompt, and the prompt contains ticket content.
- **Retryability is a property of the error type**, not a judgement each task makes. A timeout
  or an unavailable provider is worth another attempt; malformed output is not, because the
  same prompt will produce the same failure.

Only the fake provider ships in the MVP. A real one is added by writing another
:class:`AIProvider` and registering it in ``_PROVIDERS``; its credentials are read from the
environment by that adapter and never leave the backend process (10_SECURITY).
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class AIProviderError(RuntimeError):
    """Base class for every failure the adapter models.

    ``retryable`` is the contract a task reads (T6.3): a transient failure is retried with
    backoff, a permanent one ends the attempt so the operator sees it instead of a queue that
    spins. Subclasses set it; callers never infer it from a status code.
    """

    retryable = False


class AIProviderTimeout(AIProviderError):
    """The provider did not answer within the configured timeout."""

    retryable = True


class AIProviderUnavailable(AIProviderError):
    """The provider refused or the network failed; usually transient."""

    retryable = True


class AIProviderRateLimited(AIProviderError):
    """A quota or rate limit was hit. Retrying too soon makes it worse, so callers back off."""

    retryable = True


class AIResponseInvalid(AIProviderError):
    """The response could not be used: empty, unparseable, or failing the output schema.

    Not retryable. The same prompt against the same model fails the same way, so a retry only
    burns quota and delays the operator's decision (05 §6).
    """

    retryable = False


@dataclass(frozen=True)
class CompletionRequest:
    """One request to a model: the prompt, which model, and the bounds.

    The bounds live here rather than on the provider so a caller can be stricter than the
    deployment default for one call. ``prompt`` is untrusted by construction — it contains
    ticket text — and is never logged.
    """

    prompt: str
    model: str
    max_output_tokens: int = 512
    temperature: float = 0.0

    def __post_init__(self) -> None:
        if not self.prompt.strip():
            raise ValueError("A completion request needs a non-empty prompt.")
        if self.max_output_tokens < 1:
            raise ValueError("max_output_tokens must be positive.")


@dataclass(frozen=True)
class Completion:
    """What a provider returns: text plus the metadata worth persisting (FR-026).

    ``provider`` and ``model`` are stored with a result so a later quality question can be
    answered from data rather than from what the deployment happened to run at the time.
    """

    text: str
    model: str
    provider: str
    latency_ms: float


@runtime_checkable
class AIProvider(Protocol):
    """The whole surface a vendor has to implement."""

    name: str
    model: str
    timeout_seconds: int

    def complete(self, request: CompletionRequest) -> Completion: ...


class FakeAIProvider:
    """A deterministic provider: same prompt in, same text out.

    Determinism is the point. A test can assert on output without pinning a vendor, and a
    developer can run the whole ticket flow without a key. Two knobs make it useful for the
    failure paths: ``responses`` scripts specific answers in order (for schema and prompt
    tests in T6.2), and ``fail_with`` raises a modelled error so a retry path can be exercised
    without waiting for a real outage.

    Every request is recorded in ``calls`` so a test can assert what the application asked
    for — including that ticket text was bounded and that nothing secret was appended.
    """

    name = "fake"

    def __init__(
        self,
        *,
        model: str = "fake-model-v1",
        timeout_seconds: int = 20,
        responses: tuple[str, ...] = (),
        latency_ms: float = 0.0,
        fail_with: AIProviderError | None = None,
    ) -> None:
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._responses = list(responses)
        self._latency_ms = latency_ms
        self._fail_with = fail_with
        self.calls: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> Completion:
        self.calls.append(request)
        if self._fail_with is not None:
            raise self._fail_with

        started = time.monotonic()
        text = self._responses.pop(0) if self._responses else _deterministic_text(request)
        elapsed_ms = (time.monotonic() - started) * 1000

        return Completion(
            text=text,
            model=request.model or self.model,
            provider=self.name,
            latency_ms=self._latency_ms or round(elapsed_ms, 3),
        )


def _deterministic_text(request: CompletionRequest) -> str:
    """Derive stable output from the prompt, so equal input gives equal text."""
    digest = hashlib.sha256(f"{request.model}\n{request.prompt}".encode()).hexdigest()
    return f"fake-completion:{digest[:16]}"


def _build_fake() -> AIProvider:
    return FakeAIProvider(
        model=settings.AI_MODEL,
        timeout_seconds=settings.AI_REQUEST_TIMEOUT_SECONDS,
    )


# Registry by name, so the adapter is a configuration value rather than an import scattered
# through the code. Adding a vendor is one adapter plus one line here.
_PROVIDERS: dict[str, Callable[[], AIProvider]] = {"fake": _build_fake}


def get_provider(name: str | None = None) -> AIProvider:
    """Return the configured adapter, raising for an unknown name.

    Failing here — at the call, before any work is queued — means a typo in ``AI_PROVIDER``
    is a startup-time error the operator sees, not a task that fails forever in the queue.
    """
    key = settings.AI_PROVIDER if name is None else name
    factory = _PROVIDERS.get(key)
    if factory is None:
        available = ", ".join(sorted(_PROVIDERS))
        # The name is configuration, not a secret, so naming it is safe; the list of valid
        # values is what makes the message actionable.
        raise ImproperlyConfigured(f"Unknown AI provider {key!r}. Available: {available}.")
    return factory()
