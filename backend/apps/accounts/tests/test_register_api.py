"""Tests for open self-registration.

Sign-up creates an identity, never tenancy: the account has no workspace and no
membership, which is what keeps "create or join a workspace" an explicit act.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
from django.conf import settings

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.organizations.models import Membership, Workspace
from tests.support import CsrfClient

if TYPE_CHECKING:
    from django.test.client import _MonkeyPatchedWSGIResponse

pytestmark = pytest.mark.django_db

API = "/api/v1"
REGISTER = f"{API}/auth/register/"
ME = f"{API}/auth/me/"

PASSWORD = "a-strong-password-9"


def register(
    client: CsrfClient, email: str, password: str = PASSWORD
) -> _MonkeyPatchedWSGIResponse:
    return client.post_json(REGISTER, {"email": email, "password": password})


def test_register_requires_a_csrf_token(csrf_client: CsrfClient) -> None:
    response = csrf_client.post(
        REGISTER,
        data={"email": "new@example.com", "password": PASSWORD},
        content_type="application/json",
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"
    assert not User.objects.filter(email="new@example.com").exists()


def test_registration_creates_the_account_and_signs_it_in(csrf_client: CsrfClient) -> None:
    token_before = csrf_client.csrf_token

    response = register(csrf_client, "New@Example.COM ")

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["email"] == "new@example.com"
    assert body["csrf_token"] != token_before

    user = User.objects.get(email="new@example.com")
    assert user.check_password(PASSWORD)
    assert csrf_client.get(ME).json()["email"] == "new@example.com"


def test_registration_creates_no_workspace_or_membership(csrf_client: CsrfClient) -> None:
    register(csrf_client, "lonely@example.com")

    assert User.objects.filter(email="lonely@example.com").exists()
    assert Workspace.objects.count() == 0
    assert Membership.objects.count() == 0


def test_a_duplicate_address_is_a_field_error(csrf_client: CsrfClient) -> None:
    UserFactory.create(email="taken@example.com")

    response = register(csrf_client, "Taken@Example.com")

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert "email" in error["details"]
    assert User.objects.filter(email="taken@example.com").count() == 1


def test_a_weak_password_is_rejected_on_the_password_field(csrf_client: CsrfClient) -> None:
    response = register(csrf_client, "weak@example.com", password="12345678")

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"]["password"]
    assert not User.objects.filter(email="weak@example.com").exists()


def test_a_malformed_address_is_rejected(csrf_client: CsrfClient) -> None:
    response = register(csrf_client, "not-an-email")

    assert response.status_code == 400
    assert "email" in response.json()["error"]["details"]


def test_registration_is_rate_limited(csrf_client: CsrfClient) -> None:
    throttle_rates = cast("dict[str, str]", settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"])
    limit = int(throttle_rates["auth_register"].split("/")[0])

    for _ in range(limit):
        rejected = register(csrf_client, "throttled@example.com", password="short")
        assert rejected.status_code == 400

    response = register(csrf_client, "throttled@example.com", password="short")

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "throttled"
