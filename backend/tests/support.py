"""Shared helpers for HTTP-level tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

from django.test import Client

if TYPE_CHECKING:
    # djangorestframework responses from the test client carry ``json()``; that type is
    # declared in the stubs and only needed while type checking.
    from django.test.client import _MonkeyPatchedWSGIResponse

API = "/api/v1"


class CsrfClient(Client):
    """Test client that enforces CSRF, like a real browser posting a form.

    Django's default client sets ``_dont_enforce_csrf_checks``, which would make a
    "missing token" test pass without exercising the check at all.
    """

    csrf_token: str

    def __init__(self, **defaults: Any) -> None:
        defaults["enforce_csrf_checks"] = True
        super().__init__(**defaults)
        self.csrf_token = ""

    @classmethod
    def from_csrf_endpoint(cls) -> Self:
        client = cls()
        response = client.get(f"{API}/auth/csrf/")
        client.csrf_token = response.json()["csrf_token"]
        return client

    def post_json(
        self, path: str, payload: dict[str, Any], *, csrf: bool = True
    ) -> _MonkeyPatchedWSGIResponse:
        headers = {"X-CSRFToken": self.csrf_token} if csrf else {}
        return self.post(path, data=payload, content_type="application/json", headers=headers)

    def patch_json(self, path: str, payload: dict[str, Any]) -> _MonkeyPatchedWSGIResponse:
        return self.patch(
            path,
            data=payload,
            content_type="application/json",
            headers={"X-CSRFToken": self.csrf_token},
        )


def login(client: CsrfClient, *, email: str, password: str) -> CsrfClient:
    """Log in and adopt the rotated CSRF token, returning the same client."""
    response = client.post_json(f"{API}/auth/login/", {"email": email, "password": password})
    assert response.status_code == 200, response.content
    client.csrf_token = response.json()["csrf_token"]
    return client
