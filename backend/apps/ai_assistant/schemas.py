"""The classification schema: strict parsing of untrusted model output (T6.2, ADR-035).

A model returns text, and text is not a contract. Everything a classification may say is
defined here — the key set, the allowlisted sentiment, the priorities the ticket model already
understands, and the bounds on confidence and rationale — so malformed or hostile output is
refused at the boundary rather than reaching a ticket field.

Parsing is strict on purpose:

- **Unknown keys are refused**, not ignored. They usually mean the model answered a different
  question, and dropping them silently would hide that.
- **Types are checked as well as ranges.** ``json`` accepts ``NaN`` and ``Infinity``, and
  ``True`` is an ``int`` in Python, so both are rejected explicitly.
- **``category`` is checked by shape, not by an allowlist.** Workspaces name their own
  categories (``Ticket.category`` is free text), so the schema bounds the shape while
  ``TicketPriority`` pins the enum the system owns — the only priority values a ticket can hold.

Every message is written here and never quotes the response: the error text ends up in a log
line, and the response can contain customer text (10_SECURITY).
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any

from apps.ai_assistant.providers import AIResponseInvalid
from apps.tickets.models import TicketPriority

from .models import Sentiment

RATIONALE_MAX = 280
CATEGORY_MAX = 100

# Lower case, digits, and single separators. A sentence is not a category name.
_CATEGORY_PATTERN = re.compile(r"^[a-z0-9]+(?:[ _-][a-z0-9]+)*$")
REQUIRED_KEYS = frozenset(
    {"category", "sentiment", "suggested_priority", "confidence", "rationale"}
)


@dataclass(frozen=True)
class Classification:
    """A validated classification, ready to persist.

    Frozen because it is a result, not a draft: nothing downstream may edit an answer and
    still call it what the model said.
    """

    category: str
    sentiment: str
    suggested_priority: str
    confidence: float
    rationale: str


def parse_classification(text: str) -> Classification:
    """Parse one provider response into a :class:`Classification`.

    Raises :class:`AIResponseInvalid` — never a bare ``KeyError`` or ``ValueError`` — so the
    task can treat every rejection the same way and stop instead of retrying.
    """
    payload = _load_object(text)

    missing = REQUIRED_KEYS - payload.keys()
    unknown = payload.keys() - REQUIRED_KEYS
    if missing or unknown:
        raise AIResponseInvalid("The classification did not match the expected schema.")

    return Classification(
        category=_category(payload["category"]),
        sentiment=_sentiment(payload["sentiment"]),
        suggested_priority=_priority(payload["suggested_priority"]),
        confidence=_confidence(payload["confidence"]),
        rationale=_rationale(payload["rationale"]),
    )


def _reject_constant(value: str) -> Any:
    """Refuse ``NaN``/``Infinity``, which ``json`` otherwise parses into float values."""
    raise ValueError(f"Non-finite number {value!r} is not allowed.")


def _strip_code_fence(text: str) -> str:
    """Unwrap a ```json fence, which models add even when asked for JSON only.

    Tolerating the fence costs nothing and rejects nothing: the payload inside is still parsed
    strictly, so this removes formatting noise rather than validating it more loosely.
    """
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped

    body = stripped[3:]
    newline = body.find("\n")
    if newline == -1:
        raise AIResponseInvalid("The classification was not JSON.")
    body = body[newline + 1 :].rstrip()
    if body.endswith("```"):
        body = body[:-3]
    return body.strip()


def _load_object(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(_strip_code_fence(text), parse_constant=_reject_constant)
    except ValueError as exc:  # JSONDecodeError is a ValueError
        raise AIResponseInvalid("The classification was not valid JSON.") from exc

    if not isinstance(payload, dict) or not all(isinstance(key, str) for key in payload):
        raise AIResponseInvalid("The classification was not a JSON object.")
    return payload


def _category(value: Any) -> str:
    if not isinstance(value, str):
        raise AIResponseInvalid("category must be a string.")
    category = value.strip()
    if not category or len(category) > CATEGORY_MAX or not _CATEGORY_PATTERN.match(category):
        raise AIResponseInvalid("category must be a short lower-case slug.")
    return category


def _sentiment(value: Any) -> str:
    if not isinstance(value, str) or value not in Sentiment.values:
        raise AIResponseInvalid("sentiment is not an allowed value.")
    return value


def _priority(value: Any) -> str:
    if not isinstance(value, str) or value not in TicketPriority.values:
        raise AIResponseInvalid("suggested_priority is not an allowed value.")
    return value


def _confidence(value: Any) -> float:
    # `isinstance(True, int)` is True, so a boolean has to be refused before the numeric check.
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise AIResponseInvalid("confidence must be a number.")
    confidence = float(value)
    if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        raise AIResponseInvalid("confidence must be between 0 and 1.")
    return confidence


def _rationale(value: Any) -> str:
    if not isinstance(value, str):
        raise AIResponseInvalid("rationale must be a string.")
    rationale = " ".join(value.split())
    if not rationale or len(rationale) > RATIONALE_MAX:
        raise AIResponseInvalid("rationale must be one short sentence.")
    return rationale
