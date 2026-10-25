from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

pytestmark = pytest.mark.django_db

User = get_user_model()


def test_auth_user_model_is_the_custom_model() -> None:
    assert User._meta.label == "accounts.User"


def test_primary_key_is_a_uuid() -> None:
    user = User.objects.create_user("agent@example.com", "s3cret-password")

    assert isinstance(user.pk, uuid.UUID)


def test_create_user_normalizes_email_to_lowercase() -> None:
    user = User.objects.create_user("  Agent.Smith@Example.COM ", "s3cret-password")

    assert user.email == "agent.smith@example.com"


def test_password_is_hashed_not_stored_in_plain_text() -> None:
    raw_password = "s3cret-password"
    user = User.objects.create_user("agent@example.com", raw_password)

    assert user.password != raw_password
    assert user.check_password(raw_password) is True


def test_email_is_required() -> None:
    with pytest.raises(ValueError, match="email"):
        User.objects.create_user("   ", "s3cret-password")


def test_duplicate_email_is_rejected_by_the_database() -> None:
    User.objects.create_user("agent@example.com", "s3cret-password")

    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user("AGENT@example.com", "another-password")


def test_create_superuser_sets_staff_and_superuser_flags() -> None:
    admin = User.objects.create_superuser("admin@example.com", "s3cret-password")

    assert admin.is_staff is True
    assert admin.is_superuser is True
    assert admin.is_active is True


def test_create_user_is_not_staff_by_default() -> None:
    user = User.objects.create_user("agent@example.com", "s3cret-password")

    assert user.is_staff is False
    assert user.is_superuser is False


def test_create_superuser_refuses_downgraded_flags() -> None:
    with pytest.raises(ValueError, match="is_staff"):
        User.objects.create_superuser("admin@example.com", "pw", is_staff=False)
