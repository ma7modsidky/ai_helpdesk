from __future__ import annotations

import logging
from unittest.mock import patch

import pytest
from django.db import OperationalError
from django.test import Client

pytestmark = pytest.mark.django_db


def test_liveness_reports_process_is_up(client: Client) -> None:
    response = client.get("/health/live/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_reports_ok_when_database_answers(client: Client) -> None:
    response = client.get("/health/ready/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_returns_503_without_leaking_internals(
    client: Client, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="apps.common.health")
    leaky_error = OperationalError("connection failed for user resolveai password=hunter2-secret")

    with patch("apps.common.health.connection") as fake_connection:
        fake_connection.cursor.side_effect = leaky_error
        response = client.get("/health/ready/")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}

    body = response.content.decode()
    assert "hunter2-secret" not in body
    assert "OperationalError" not in body
    assert "Traceback" not in body

    assert "hunter2-secret" not in caplog.text
    assert "Readiness check failed" in caplog.text
