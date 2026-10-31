from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest
from django.core.cache import cache

from apps.accounts.models import User
from apps.accounts.tests.factories import DEFAULT_PASSWORD, UserFactory
from apps.common.logging import RequestIdFilter
from tests.support import CsrfClient

AGENT_EMAIL = "agent@example.com"


@pytest.fixture(autouse=True)
def _isolate_throttle_cache() -> Iterator[None]:
    """Throttle counters live in the cache; never let one test leak into another."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def captured_logs() -> Iterator[list[logging.LogRecord]]:
    """Capture log records with the app's filters applied.

    The task harness: tasks run eagerly in this suite, so their log output is directly
    observable. Going through ``RequestIdFilter`` rather than the bare formatter is what makes
    ``request_id``/``task_id`` and the structured task fields assertable the way an aggregator
    would see them (T5.3).
    """

    records: list[logging.LogRecord] = []

    class _Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Collect()
    handler.addFilter(RequestIdFilter())
    root = logging.getLogger()
    previous_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    try:
        yield records
    finally:
        root.removeHandler(handler)
        root.setLevel(previous_level)


@pytest.fixture
def csrf_client() -> CsrfClient:
    return CsrfClient.from_csrf_endpoint()


@pytest.fixture
def user_factory() -> type[UserFactory]:
    """Expose the factory itself for tests that need several users."""
    return UserFactory


@pytest.fixture
def agent_user() -> User:
    return UserFactory.create(email=AGENT_EMAIL, password=DEFAULT_PASSWORD)
