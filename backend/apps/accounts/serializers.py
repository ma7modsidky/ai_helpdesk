"""Serializers for identity and session authentication.

Credential checking lives here rather than in the view so the rule (and its
uniform failure message) can be unit tested without HTTP.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed

from .models import User

# The same message for unknown emails, wrong passwords, and inactive accounts so
# the endpoint cannot be used to enumerate accounts.
INVALID_CREDENTIALS_MESSAGE = "Invalid email or password."


class UserSerializer(serializers.ModelSerializer[User]):
    class Meta:
        model = User
        fields = ("id", "email", "is_staff")
        read_only_fields = fields


class LoginSerializer(serializers.Serializer[Any]):
    email = serializers.EmailField()
    password = serializers.CharField(
        trim_whitespace=False,
        write_only=True,
        style={"input_type": "password"},
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        user = authenticate(
            request=self.context.get("request"),
            username=attrs["email"].strip().lower(),
            password=attrs["password"],
        )
        if user is None or not user.is_active:
            raise AuthenticationFailed(INVALID_CREDENTIALS_MESSAGE)

        attrs["user"] = user
        return attrs


class RegisterSerializer(serializers.Serializer[Any]):
    """Open sign-up: an account with no workspace and no membership.

    Uniqueness and password rules are checked here so the failure shape is a field
    error in the standard envelope; the write still goes through the user manager,
    which owns email normalization and hashing.
    """

    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(
        trim_whitespace=False,
        write_only=True,
        style={"input_type": "password"},
    )

    def validate_email(self, value: str) -> str:
        email = value.strip().lower()
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return email

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        # Passing a transient user lets the similarity validator compare the
        # password against the address the account will have.
        candidate = User(email=attrs["email"])
        try:
            validate_password(attrs["password"], candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)}) from exc
        return attrs

    def create(self, validated_data: dict[str, Any]) -> User:
        return User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
        )


class LoginResponseSerializer(serializers.Serializer[Any]):
    user = UserSerializer(read_only=True)
    csrf_token = serializers.CharField(
        read_only=True,
        help_text="Replacement CSRF token; the session rotates on login.",
    )


class AuthResponseSerializer(LoginResponseSerializer):
    """Same shape as login: the user plus the CSRF token for the new session."""


class CsrfTokenSerializer(serializers.Serializer[Any]):
    csrf_token = serializers.CharField(read_only=True)
