from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from django.test import Client, override_settings

from apps.accounts.models import User
from tests.support import CsrfClient

if TYPE_CHECKING:
    from django.test.client import _MonkeyPatchedWSGIResponse

API = "/api/v1"

pytestmark = pytest.mark.django_db

ENVELOPE_KEYS = {"code", "message", "request_id"}


def _assert_envelope(
    response: _MonkeyPatchedWSGIResponse, *, status_code: int, code: str
) -> dict[str, Any]:
    assert response.status_code == status_code
    assert response["Content-Type"].startswith("application/json")
    body: dict[str, Any] = response.json()
    assert set(body) == {"error"}
    error: dict[str, Any] = body["error"]
    assert set(error) >= ENVELOPE_KEYS
    assert error["code"] == code
    assert error["message"]
    assert error["request_id"] == response["X-Request-ID"]
    return error


def test_unauthenticated_request_returns_401_envelope(client: Client) -> None:
    response = client.get(f"{API}/auth/me/")

    error = _assert_envelope(response, status_code=401, code="not_authenticated")
    # A challenge header is what keeps this a 401 instead of DRF's default 403.
    assert response.headers["WWW-Authenticate"] == "Session"
    assert "Traceback" not in error["message"]


def test_unknown_api_path_returns_json_404_envelope(client: Client) -> None:
    _assert_envelope(client.get(f"{API}/does-not-exist/"), status_code=404, code="not_found")


def test_unsupported_api_version_returns_404_envelope(client: Client) -> None:
    _assert_envelope(client.get("/api/v2/auth/me/"), status_code=404, code="not_found")


def test_wrong_method_returns_405_envelope(client: Client, agent_user: User) -> None:
    client.force_login(agent_user)

    _assert_envelope(client.post(f"{API}/auth/me/"), status_code=405, code="method_not_allowed")


def test_validation_error_includes_field_details(client: Client, csrf_client: CsrfClient) -> None:
    response = csrf_client.post_json(
        f"{API}/auth/login/", {"email": "not-an-email", "password": "x"}
    )

    error = _assert_envelope(response, status_code=400, code="validation_error")
    assert "email" in error["details"]
    assert error["request_id"]


def test_unsupported_content_type_returns_envelope(client: Client, csrf_client: CsrfClient) -> None:
    response = csrf_client.post(
        f"{API}/auth/login/",
        data={"email": "a@example.com", "password": "x"},
        headers={"X-CSRFToken": csrf_client.csrf_token},
    )

    # Form encoding is not part of the contract: only JSON bodies are accepted.
    _assert_envelope(response, status_code=415, code="unsupported_media_type")


def test_login_without_csrf_token_returns_403_envelope(
    csrf_client: CsrfClient, agent_user: User
) -> None:
    # Must use a CSRF-enforcing client: Django's default test client sets
    # _dont_enforce_csrf_checks, which would silently bypass the check.
    response = csrf_client.post_json(
        f"{API}/auth/login/",
        {"email": "agent@example.com", "password": "s3cret-password"},
        csrf=False,
    )

    error = _assert_envelope(response, status_code=403, code="csrf_failed")

    assert "CSRF" in error["message"]


@override_settings(ROOT_URLCONF="tests.urls")
def test_unhandled_exception_returns_500_envelope_without_details() -> None:
    client = Client(raise_request_exception=False)

    response = client.get("/test-boom/")

    error = _assert_envelope(response, status_code=500, code="internal_error")
    body = response.content.decode()
    assert "boom-should-never-reach-the-client" not in body
    assert "RuntimeError" not in body
    assert "Traceback" not in body
    assert error["request_id"] != "-"
