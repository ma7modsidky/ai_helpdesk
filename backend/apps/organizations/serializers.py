"""HTTP representations for workspaces and memberships.

Serializers validate shape only. Creating a workspace and changing a membership
are service calls, so the invariants they enforce hold for every caller, not just
this API.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from .models import Membership, MembershipRole, MembershipStatus, Workspace


class WorkspaceSerializer(serializers.ModelSerializer[Workspace]):
    class Meta:
        model = Workspace
        fields = ("id", "name", "slug", "timezone", "status", "created_at")
        read_only_fields = fields


class WorkspaceCreateSerializer(serializers.ModelSerializer[Workspace]):
    """Input for workspace creation; the caller becomes its owner."""

    class Meta:
        model = Workspace
        fields = ("name", "slug", "timezone")
        extra_kwargs = {
            "timezone": {"required": False},
        }


class MembershipSerializer(serializers.ModelSerializer[Membership]):
    email = serializers.EmailField(source="user.email", read_only=True)
    user_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Membership
        fields = ("id", "user_id", "email", "role", "status", "created_at")
        read_only_fields = fields


class MembershipUpdateSerializer(serializers.Serializer[Any]):
    """Partial update: change a role, revoke access, or both."""

    role = serializers.ChoiceField(choices=MembershipRole.choices, required=False)
    status = serializers.ChoiceField(choices=MembershipStatus.choices, required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if not attrs:
            raise serializers.ValidationError("Provide a role, a status, or both.")
        return attrs
