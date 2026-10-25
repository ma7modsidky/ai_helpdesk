from __future__ import annotations

from collections.abc import Iterator

import pytest
from django.core.cache import cache

from apps.accounts.models import User
from apps.accounts.tests.factories import DEFAULT_PASSWORD, UserFactory
from tests.support import CsrfClient

AGENT_EMAIL = "agent@example.com"


@pytest.fixture(autouse=True)
def _isolate_throttle_cache() -> Iterator[None]:
    """Throttle counters live in the cache; never let one test leak into another."""
    cache.clear()
    yield
    cache.clear()


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
