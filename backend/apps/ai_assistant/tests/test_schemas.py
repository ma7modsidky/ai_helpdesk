"""The classification schema refuses anything the product cannot store (T6.2).

Each case here is a way a model can be wrong: unparseable text, a different question, an
invented enum, an out-of-range number, or prose where a slug belongs. All of them end in the
same modelled error, so the task has one thing to handle and the customer never sees a
half-applied suggestion.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from apps.ai_assistant.providers import AIResponseInvalid
from apps.ai_assistant.schemas import Classification, parse_classification
from apps.tickets.models import TicketPriority


def _payload(**overrides: Any) -> str:
    payload: dict[str, Any] = {
        "category": "billing",
        "sentiment": "negative",
        "suggested_priority": "high",
        "confidence": 0.82,
        "rationale": "Customer reports duplicate billing and repeated unsuccessful contact.",
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_a_valid_response_is_parsed_into_the_typed_result() -> None:
    result = parse_classification(_payload())

    assert result == Classification(
        category="billing",
        sentiment="negative",
        suggested_priority=TicketPriority.HIGH.value,
        confidence=0.82,
        rationale="Customer reports duplicate billing and repeated unsuccessful contact.",
    )


def test_a_fenced_response_is_accepted() -> None:
    # Models add a fence even when asked for JSON only; the payload inside is still strict.
    assert parse_classification(f"```json\n{_payload()}\n```").category == "billing"
    assert parse_classification(f"```\n{_payload()}\n```").category == "billing"


def test_whitespace_in_the_rationale_is_collapsed() -> None:
    result = parse_classification(_payload(rationale="  Customer\nreports\tduplicate billing.  "))

    assert result.rationale == "Customer reports duplicate billing."


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("not json at all", id="plain-text"),
        pytest.param("", id="empty"),
        pytest.param("[1, 2, 3]", id="json-array"),
        pytest.param('{"category": "billing"}', id="missing-keys"),
        pytest.param(_payload(extra="unexpected"), id="unknown-key"),
        pytest.param('{"category": "billing", "confidence": NaN}', id="not-json-at-all"),
    ],
)
def test_anything_that_does_not_match_the_schema_is_refused(text: str) -> None:
    with pytest.raises(AIResponseInvalid):
        parse_classification(text)


def test_a_non_finite_confidence_is_refused() -> None:
    # `json` parses NaN into a float, so this is the case that would otherwise slip through a
    # range check written as `0 <= value <= 1` (NaN compares False, but Infinity compares True).
    with pytest.raises(AIResponseInvalid):
        parse_classification(_payload(confidence=float("inf")))


@pytest.mark.parametrize("confidence", [1.5, -0.1, "0.82", None, True])
def test_confidence_must_be_a_number_between_zero_and_one(confidence: Any) -> None:
    with pytest.raises(AIResponseInvalid):
        parse_classification(_payload(confidence=confidence))


@pytest.mark.parametrize("value", [0, 1, 0.0, 1.0])
def test_the_range_ends_are_inclusive(value: float) -> None:
    assert parse_classification(_payload(confidence=value)).confidence == float(value)


@pytest.mark.parametrize(
    "category",
    ["Billing", "billing!", "", "x" * 101, "two words: no thanks", 7],
)
def test_category_must_be_a_short_lower_case_slug(category: Any) -> None:
    with pytest.raises(AIResponseInvalid):
        parse_classification(_payload(category=category))


def test_a_workspace_named_category_is_allowed() -> None:
    assert parse_classification(_payload(category="payments_refund")).category == "payments_refund"


@pytest.mark.parametrize("sentiment", ["angry", "NEGATIVE", "", 1])
def test_sentiment_is_allowlisted(sentiment: Any) -> None:
    with pytest.raises(AIResponseInvalid):
        parse_classification(_payload(sentiment=sentiment))


@pytest.mark.parametrize("priority", ["critical", "urgent!", "", None])
def test_suggested_priority_must_be_a_ticket_priority(priority: Any) -> None:
    with pytest.raises(AIResponseInvalid):
        parse_classification(_payload(suggested_priority=priority))


@pytest.mark.parametrize("rationale", ["", "   ", "x" * 281, 42])
def test_rationale_must_be_short_text(rationale: Any) -> None:
    with pytest.raises(AIResponseInvalid):
        parse_classification(_payload(rationale=rationale))


def test_a_rejection_never_quotes_the_response() -> None:
    text = _payload(confidence=9.9, rationale="Card 4111 1111 1111 1111 was charged twice.")

    with pytest.raises(AIResponseInvalid) as caught:
        parse_classification(text)

    # The message reaches a log line; the response can contain customer data.
    assert "4111" not in str(caught.value)
    assert "charged twice" not in str(caught.value)
