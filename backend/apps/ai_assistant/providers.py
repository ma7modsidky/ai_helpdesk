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

Two adapters ship. The deterministic fake keeps tests and an offline demo independent of the
network, and Gemini is what a developer points at a free tier to see real output. Either way the
seam is the same: a vendor is added by writing another :class:`AIProvider` and registering it in
``_PROVIDERS``; its credential is read from the environment by that adapter and never leaves the
backend process (10_SECURITY).
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from config.env import require


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


# --- Gemini ---------------------------------------------------------------

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models"
# The model Google recommends for a new project on the free tier. It is only a default: the
# deployment names its own through AI_MODEL, because a model id is configuration, not code.
GEMINI_DEFAULT_MODEL = "gemini-3.5-flash-lite"

# The value `_opener` calls. Injected rather than referenced directly at the call site so a test
# can answer without a socket, and so the one place a real connection happens is explicit.
Opener = Callable[..., Any]
_DEFAULT_OPENER: Opener = urllib.request.urlopen


class GeminiAIProvider:
    """Google Gemini over its documented REST ``generateContent`` method.

    Standard library rather than the vendor SDK: this is one HTTP request, and an SDK would add a
    dependency, a release cadence, and a second exception hierarchy to re-map onto the modelled
    errors anyway.

    The key is read from the environment when the adapter is built and sent as the
    ``x-goog-api-key`` header. It is never placed in a URL, because URLs reach access logs,
    proxies, and browser history, and this key spends the workspace's quota.
    """

    name = "gemini"

    def __init__(
        self,
        *,
        model: str,
        timeout_seconds: int,
        api_key: str,
        response_mime_type: str = "application/json",
        opener: Opener | None = None,
    ) -> None:
        if not api_key.strip():
            raise ImproperlyConfigured("GEMINI_API_KEY is empty.")
        self.model = _bare_model_name(model)
        self.timeout_seconds = timeout_seconds
        self._api_key = api_key
        self._response_mime_type = response_mime_type
        self._opener: Opener = opener or _DEFAULT_OPENER

    def complete(self, request: CompletionRequest) -> Completion:
        model = _bare_model_name(request.model) or self.model
        # The URL is a constant: a fixed https host, a literal method, and the configured model id.
        # S310 exists to catch a scheme chosen at runtime, which cannot happen here.
        http_request = urllib.request.Request(  # noqa: S310
            f"{GEMINI_ENDPOINT}/{model}:generateContent",
            data=json.dumps(self._payload(request)).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": self._api_key},
            method="POST",
        )

        started = time.monotonic()
        try:
            with self._opener(http_request, timeout=self.timeout_seconds) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            # `from None` on purpose: the vendor's body is never inspected, so no response text
            # — which can quote the prompt, and the prompt contains customer text — can reach a
            # traceback or a log line through chaining.
            raise _status_error(exc.code) from None
        except TimeoutError as exc:
            raise AIProviderTimeout("The Gemini request timed out.") from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise AIProviderTimeout("The Gemini request timed out.") from exc
            raise AIProviderUnavailable("The Gemini API could not be reached.") from exc
        except OSError as exc:
            raise AIProviderUnavailable("The Gemini API could not be reached.") from exc

        return Completion(
            text=_gemini_text(raw),
            model=model,
            provider=self.name,
            latency_ms=round((time.monotonic() - started) * 1000, 3),
        )

    def _payload(self, request: CompletionRequest) -> dict[str, Any]:
        return {
            "contents": [{"role": "user", "parts": [{"text": request.prompt}]}],
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_output_tokens,
                # Both callers here want a JSON object. Asking for one removes the prose
                # preamble that would otherwise be parsed and rejected (T6.2).
                "responseMimeType": self._response_mime_type,
                # Classification and drafting are extraction, not reasoning. A low thinking
                # level keeps the model from spending the small output allowance on a preamble
                # it would then emit as extra parts.
                "thinkingConfig": {"thinkingLevel": "low"},
            },
        }


def _bare_model_name(model: str) -> str:
    """Accept ``gemini-3.5-flash-lite`` and ``models/gemini-3.5-flash-lite`` alike.

    The REST path wants the bare id; the documented model names are printed with the prefix.
    """
    return model.strip().removeprefix("models/")


def _status_error(status: int) -> AIProviderError:
    """Map an HTTP status onto the modelled error, so retryability stays a property of the type.

    The message names what the operator has to check, never what the vendor said.
    """
    if status == 429:
        return AIProviderRateLimited("The Gemini API rejected the request as rate limited.")
    if status >= 500:
        return AIProviderUnavailable("The Gemini API is unavailable.")
    # A bad key, a model the project cannot use, or a malformed request: the same call fails the
    # same way, so retrying only spends quota.
    return AIProviderError(
        f"The Gemini API rejected the request (HTTP {status}); check GEMINI_API_KEY and AI_MODEL."
    )


def _gemini_text(raw: bytes) -> str:
    """Take the first candidate's text, refusing anything that is not usable output.

    Every failure here is :class:`AIResponseInvalid` and therefore not retried: a blocked prompt,
    an empty candidate, and a non-JSON body all produce the same result next time.
    """
    try:
        payload: Any = json.loads(raw)
    except ValueError as exc:
        raise AIResponseInvalid("The provider response was not JSON.") from exc

    if not isinstance(payload, dict):
        raise AIResponseInvalid("The provider response was not a JSON object.")

    # A blocked prompt comes back with no candidate at all, so the feedback is the only thing that
    # can tell a refusal apart from an empty answer. Neither is worth another attempt. The check
    # comes first because a blocked response has nothing that could be read anyway.
    feedback = payload.get("promptFeedback")
    if isinstance(feedback, dict) and feedback.get("blockReason"):
        raise AIResponseInvalid("The provider blocked the request.")

    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise AIResponseInvalid("The provider response had no candidates.")

    for candidate in candidates:
        text = _candidate_text(candidate)
        if text:
            return text

    raise AIResponseInvalid("The provider returned no text.")


def _candidate_text(candidate: Any) -> str:
    """Join one candidate's text parts, tolerating anything that is not a text part.

    Parts marked ``thought`` are skipped. A reasoning model returns its thinking as text parts
    alongside the answer, and joining them would put prose in front of the JSON the caller asked
    for — which parses as invalid on some runs and not others, depending on whether the model
    chose to think aloud.
    """
    if not isinstance(candidate, dict):
        return ""
    content = candidate.get("content")
    if not isinstance(content, dict):
        return ""
    parts = content.get("parts")
    if not isinstance(parts, list):
        return ""
    return "".join(
        part["text"]
        for part in parts
        if isinstance(part, dict) and isinstance(part.get("text"), str) and not part.get("thought")
    ).strip()


def _build_gemini() -> AIProvider:
    """Build the Gemini adapter from settings, failing before any work is queued.

    Two configuration mistakes are worth one clear startup error each: a missing key makes every
    call unauthorized, and an ``AI_MODEL`` left at the fake makes every call a rejection. Both
    would otherwise appear as a job that fails in the queue forever.
    """
    model = settings.AI_MODEL
    if model.strip().lower().startswith("fake"):
        raise ImproperlyConfigured(
            f"AI_MODEL is still the fake model ({model!r}); set it to a Gemini model, "
            f"for example {GEMINI_DEFAULT_MODEL!r}."
        )
    return GeminiAIProvider(
        model=model,
        timeout_seconds=settings.AI_REQUEST_TIMEOUT_SECONDS,
        api_key=require("GEMINI_API_KEY"),
    )


# Registry by name, so the adapter is a configuration value rather than an import scattered
# through the code. Adding a vendor is one adapter plus one line here.
_PROVIDERS: dict[str, Callable[[], AIProvider]] = {
    "fake": _build_fake,
    "gemini": _build_gemini,
}


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
