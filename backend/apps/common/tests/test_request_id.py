from __future__ import annotations

import logging
import re
from unittest.mock import patch

import pytest
from django.db import OperationalError
from django.test import Client, RequestFactory

from apps.common.logging import get_request_id
from apps.common.middleware import (
    REQUEST_ID_HEADER,
    RequestIdMiddleware,
    normalize_request_id,
)

pytestmark = pytest.mark.django_db

GENERATED_ID = re.compile(r"^[0-9a-f]{32}$")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("client-request_1.abc", "client-request_1.abc"),
        ("  trimmed-id  ", "trimmed-id"),
        ("a" * 64, "a" * 64),
        (None, None),
        ("", None),
        ("   ", None),
        ("has spaces", None),
        ("a" * 65, None),
        ("injected\nINFO fake line", None),
        ("<script>alert(1)</script>", None),
    ],
)
def test_normalize_request_id_allowlist(raw: str | None, expected: str | None) -> None:
    assert normalize_request_id(raw) == expected


def test_generates_correlation_id_when_header_absent(client: Client) -> None:
    response = client.get("/health/live/")

    generated = response[REQUEST_ID_HEADER]
    assert GENERATED_ID.fullmatch(generated)


def test_echoes_valid_client_correlation_id(client: Client) -> None:
    response = client.get("/health/live/", headers={"X-Request-ID": "client-provided-id-42"})

    assert response[REQUEST_ID_HEADER] == "client-provided-id-42"


def test_ignores_unsafe_client_correlation_id(client: Client) -> None:
    response = client.get("/health/live/", headers={"X-Request-ID": "bad id with spaces"})

    generated = response[REQUEST_ID_HEADER]
    assert generated != "bad id with spaces"
    assert GENERATED_ID.fullmatch(generated)


def test_generates_distinct_ids_per_request(client: Client) -> None:
    first = client.get("/health/live/")[REQUEST_ID_HEADER]
    second = client.get("/health/live/")[REQUEST_ID_HEADER]

    assert first != second


def test_correlation_id_is_cleared_after_the_request(client: Client) -> None:
    client.get("/health/live/")

    assert get_request_id() is None


def test_header_is_present_on_degraded_readiness_response(client: Client) -> None:
    with patch("apps.common.health.connection") as fake_connection:
        fake_connection.cursor.side_effect = OperationalError("database is down")
        response = client.get("/health/ready/", headers={"X-Request-ID": "degraded-1"})

    assert response.status_code == 503
    assert response[REQUEST_ID_HEADER] == "degraded-1"


def test_log_records_emitted_during_request_carry_the_correlation_id(
    client: Client, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="apps.common")

    with patch("apps.common.health.connection") as fake_connection:
        fake_connection.cursor.side_effect = OperationalError("database is down")
        response = client.get("/health/ready/", headers={"X-Request-ID": "trace-me-1"})

    readiness_records = [
        record
        for record in caplog.records
        if record.name == "apps.common.health" and "Readiness check failed" in record.getMessage()
    ]
    assert readiness_records, "expected a readiness failure log record"
    assert readiness_records[0].request_id == response[REQUEST_ID_HEADER]  # type: ignore[attr-defined]
    assert "trace-me-1" == response[REQUEST_ID_HEADER]


def test_completion_log_includes_method_path_status_and_id(
    client: Client, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="apps.common.middleware")

    response = client.get("/health/live/", headers={"X-Request-ID": "completion-1"})

    records = [
        record
        for record in caplog.records
        if record.name == "apps.common.middleware" and "health/live" in record.getMessage()
    ]
    assert records, "expected a request completion log record"
    message = records[0].getMessage()
    assert "GET" in message
    assert "-> 200" in message
    assert records[0].request_id == response[REQUEST_ID_HEADER]  # type: ignore[attr-defined]


def test_completion_log_omits_query_string(
    client: Client, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="apps.common.middleware")

    client.get("/health/live/?search=secret-customer-term")

    messages = [
        record.getMessage() for record in caplog.records if record.name == "apps.common.middleware"
    ]
    assert messages
    assert all("secret-customer-term" not in message for message in messages)


def test_unhandled_error_is_logged_with_id_and_reraised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR, logger="apps.common.middleware")
    request = RequestFactory().get("/boom/", headers={"X-Request-ID": "error-trace-1"})

    def explode(_request: object) -> None:
        raise RuntimeError("kaboom")

    with pytest.raises(RuntimeError, match="kaboom"):
        RequestIdMiddleware(explode)(request)  # type: ignore[arg-type]

    records = [
        record
        for record in caplog.records
        if record.name == "apps.common.middleware" and "500" in record.getMessage()
    ]
    assert records, "expected an error log record"
    assert records[0].request_id == "error-trace-1"  # type: ignore[attr-defined]
    assert get_request_id() is None
