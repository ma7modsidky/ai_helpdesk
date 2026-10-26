"""HTTP representations for workspaces and memberships.

Serializers validate shape only. Creating a workspace and changing a membership
are service calls, so the invariants they enforce hold for every caller, not just
this API.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from .models import (
    INVITABLE_ROLES,
    Invitation,
    Membership,
    MembershipRole,
    MembershipStatus,
    Workspace,
)


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


class OwnershipTransferSerializer(serializers.Serializer[Any]):
    """Input for a handover: the membership that should become the owner."""

    membership_id = serializers.UUIDField()


class OwnershipTransferResultSerializer(serializers.Serializer[Any]):
    """Both memberships, so the client can update its member list in place."""

    owner = MembershipSerializer(read_only=True)
    previous_owner = MembershipSerializer(read_only=True)


class InvitationSerializer(serializers.ModelSerializer[Invitation]):
    """Read representation. The token never appears here, in any read path."""

    invited_by = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = Invitation
        fields = (
            "id",
            "email",
            "role",
            "status",
            "expires_at",
            "created_at",
            "invited_by",
            "delivery_status",
        )
        read_only_fields = fields

    def get_invited_by(self, obj: Invitation) -> dict[str, str] | None:
        if obj.invited_by is None:
            return None
        return {"user_id": str(obj.invited_by_id), "email": obj.invited_by.email}

    def get_status(self, obj: Invitation) -> str:
        return obj.effective_status


class InvitationCreateSerializer(serializers.Serializer[Any]):
    """Input for issuing an invitation; ownership is never grantable here."""

    email = serializers.EmailField(max_length=254)
    role = serializers.ChoiceField(choices=[(role.value, role.label) for role in INVITABLE_ROLES])

    def validate_email(self, value: str) -> str:
        return value.strip().lower()


class InvitationPreviewSerializer(serializers.ModelSerializer[Invitation]):
    """Public view of an invitation: workspace and role, never the address."""

    workspace_name = serializers.CharField(source="workspace.name", read_only=True)
    status = serializers.SerializerMethodField()

    class Meta:
        model = Invitation
        fields = ("workspace_name", "role", "status", "expires_at")
        read_only_fields = fields

    def get_status(self, obj: Invitation) -> str:
        return obj.effective_status


class InvitationTokenSerializer(serializers.Serializer[Any]):
    """The token travels in the body, so it never reaches a request log."""

    token = serializers.CharField(max_length=128, trim_whitespace=True)


class InvitationAcceptanceSerializer(serializers.Serializer[Any]):
    """Response shape for a successful acceptance."""

    workspace = WorkspaceSerializer(read_only=True)
    membership = MembershipSerializer(read_only=True)
