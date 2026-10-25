"""Serializers for identity and session authentication.

Credential checking lives here rather than in the view so the rule (and its
uniform failure message) can be unit tested without HTTP.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth import authenticate, get_user_model
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed

User = get_user_model()

# The same message for unknown emails, wrong passwords, and inactive accounts so
# the endpoint cannot be used to enumerate accounts.
INVALID_CREDENTIALS_MESSAGE = "Invalid email or password."


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "is_staff")
        read_only_fields = fields


class LoginSerializer(serializers.Serializer):
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


class LoginResponseSerializer(serializers.Serializer):
    user = UserSerializer(read_only=True)
    csrf_token = serializers.CharField(
        read_only=True,
        help_text="Replacement CSRF token; the session rotates on login.",
    )


class CsrfTokenSerializer(serializers.Serializer):
    csrf_token = serializers.CharField(read_only=True)
