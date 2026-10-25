from __future__ import annotations

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model

pytestmark = pytest.mark.django_db

API = "/api/v1"
LOGIN = f"{API}/auth/login/"
LOGOUT = f"{API}/auth/logout/"
ME = f"{API}/auth/me/"
CSRF = f"{API}/auth/csrf/"

INVALID_CREDENTIALS = "Invalid email or password."


def test_csrf_bootstrap_sets_httponly_cookie(client, csrf_client) -> None:
    response = client.get(CSRF)

    assert response.status_code == 200
    assert response.json()["csrf_token"]
    cookie = response.cookies[settings.CSRF_COOKIE_NAME]
    assert cookie["httponly"] is True
    assert cookie.value


def test_login_creates_session_and_returns_rotated_csrf_token(csrf_client, agent_user) -> None:
    token_before = csrf_client.csrf_token

    response = csrf_client.post_json(
        LOGIN, {"email": "agent@example.com", "password": "s3cret-password"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == "agent@example.com"
    assert body["csrf_token"] != token_before
    assert settings.SESSION_COOKIE_NAME in response.cookies


def test_email_login_is_case_insensitive(csrf_client, agent_user) -> None:
    response = csrf_client.post_json(
        LOGIN, {"email": "  AGENT@Example.COM ", "password": "s3cret-password"}
    )

    assert response.status_code == 200
    assert response.json()["user"]["email"] == "agent@example.com"


def test_me_returns_the_authenticated_user_without_secrets(csrf_client, agent_user) -> None:
    csrf_client.post_json(LOGIN, {"email": "agent@example.com", "password": "s3cret-password"})

    response = csrf_client.get(ME)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"id", "email", "is_staff"}
    assert body["email"] == "agent@example.com"


def test_logout_ends_the_session(csrf_client, agent_user) -> None:
    login = csrf_client.post_json(
        LOGIN, {"email": "agent@example.com", "password": "s3cret-password"}
    )
    csrf_client.csrf_token = login.json()["csrf_token"]

    # State-changing requests carry a JSON content type even without a payload;
    # the CSRF check parses the body, so a form/multipart request is rejected.
    logout = csrf_client.post(
        LOGOUT,
        data={},
        content_type="application/json",
        headers={"X-CSRFToken": csrf_client.csrf_token},
    )

    assert logout.status_code == 204
    assert csrf_client.get(ME).status_code == 401


def test_logout_requires_authentication(client) -> None:
    response = client.post(LOGOUT)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_wrong_password_and_unknown_email_are_indistinguishable(csrf_client, agent_user) -> None:
    wrong_password = csrf_client.post_json(
        LOGIN, {"email": "agent@example.com", "password": "not-the-password"}
    )
    unknown_email = csrf_client.post_json(
        LOGIN, {"email": "nobody@example.com", "password": "not-the-password"}
    )

    assert wrong_password.status_code == unknown_email.status_code == 401

    wrong = wrong_password.json()["error"]
    unknown = unknown_email.json()["error"]
    assert wrong["code"] == unknown["code"] == "authentication_failed"
    assert wrong["message"] == unknown["message"] == INVALID_CREDENTIALS
    # Only the correlation ID may differ between the two cases.
    assert wrong["request_id"] != unknown["request_id"]


def test_inactive_user_cannot_log_in(csrf_client) -> None:
    get_user_model().objects.create_user("inactive@example.com", "s3cret-password", is_active=False)

    response = csrf_client.post_json(
        LOGIN, {"email": "inactive@example.com", "password": "s3cret-password"}
    )

    assert response.status_code == 401
    assert response.json()["error"]["message"] == INVALID_CREDENTIALS


def test_login_is_rate_limited(csrf_client, agent_user) -> None:
    limit = int(settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["auth_login"].split("/")[0])

    for _ in range(limit):
        throttled_or_invalid = csrf_client.post_json(
            LOGIN, {"email": "agent@example.com", "password": "wrong-password"}
        )
        assert throttled_or_invalid.status_code == 401

    response = csrf_client.post_json(
        LOGIN, {"email": "agent@example.com", "password": "wrong-password"}
    )

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "throttled"
    assert "Retry-After" in response.headers
