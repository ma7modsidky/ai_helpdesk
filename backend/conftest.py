from __future__ import annotations

from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client

User = get_user_model()

API = "/api/v1"


@pytest.fixture(autouse=True)
def _isolate_throttle_cache() -> Any:
    """Throttle counters live in the cache; never let one test leak into another."""
    cache.clear()
    yield
    cache.clear()


class CsrfClient(Client):
    """Test client that enforces CSRF, like a real browser posting a form."""

    csrf_token: str

    def __init__(self, **defaults: Any) -> None:
        defaults["enforce_csrf_checks"] = True
        super().__init__(**defaults)
        self.csrf_token = ""

    @classmethod
    def from_csrf_endpoint(cls) -> CsrfClient:
        client = cls()
        response = client.get(f"{API}/auth/csrf/")
        client.csrf_token = response.json()["csrf_token"]
        return client

    def post_json(self, path: str, payload: dict[str, Any], *, csrf: bool = True) -> Any:
        headers = {"X-CSRFToken": self.csrf_token} if csrf else {}
        return self.post(path, data=payload, content_type="application/json", headers=headers)


@pytest.fixture
def csrf_client() -> CsrfClient:
    return CsrfClient.from_csrf_endpoint()


@pytest.fixture
def agent_user() -> Any:
    return User.objects.create_user("agent@example.com", "s3cret-password")
