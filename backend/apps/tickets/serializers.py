"""HTTP shapes for tickets, messages, and list queries.

Serializers validate shape only: range, type, enum membership, and which fields a
request may carry. They never write model fields directly, because every ticket
write has to pass through ``services`` to keep the version counter, the audit
trail, and the cross-table membership rules intact (ADR-022).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from rest_framework import serializers

from .models import (
    MessageVisibility,
    Ticket,
    TicketMessage,
    TicketPriority,
    TicketStatus,
)
from .services import ASSIGNEE_ME, ASSIGNEE_UNASSIGNED, parse_ordering

CREATE_FIELDS = frozenset(
    {
        "subject",
        "description",
        "requester_email",
        "requester_name",
        "requester_user_id",
        "priority",
        "category",
    }
)

# Status, assignment, ``requester_user_id`` and the timestamps are rejected rather
# than ignored: each has its own command or is derived, and silently dropping one
# would let a client believe an edit took effect.
UPDATE_FIELDS = frozenset(
    {"subject", "description", "priority", "category", "requester_email", "requester_name"}
)


class TicketSerializer(serializers.ModelSerializer[Ticket]):
    """Read representation, including the optimistic-concurrency version."""

    requester_user_id = serializers.UUIDField(read_only=True)
    assignee_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Ticket
        fields = (
            "id",
            "subject",
            "description",
            "status",
            "priority",
            "category",
            "requester_email",
            "requester_name",
            "requester_user_id",
            "assignee_id",
            "version",
            "first_response_due_at",
            "first_responded_at",
            "resolved_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class _StrictFieldsSerializer(serializers.Serializer[Any]):
    """Reject fields the endpoint does not accept instead of ignoring them."""

    allowed_fields: frozenset[str] = frozenset()

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        unexpected = set(self.initial_data) - self.allowed_fields
        if unexpected:
            raise serializers.ValidationError(
                {field: ["This field is not allowed."] for field in sorted(unexpected)}
            )
        return attrs


class TicketCreateSerializer(_StrictFieldsSerializer):
    """Input for creating a ticket. Status and assignee are not accepted."""

    allowed_fields = CREATE_FIELDS

    subject = serializers.CharField(max_length=200)
    description = serializers.CharField(max_length=10000, trim_whitespace=False)
    requester_email = serializers.EmailField(max_length=254)
    # Both are optional and default to the empty string, so a client that sends "" for
    # an untouched field is saying the same thing as omitting it. Refusing the empty
    # string would make the default a value this serializer itself rejects.
    requester_name = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )
    requester_user_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    priority = serializers.ChoiceField(choices=TicketPriority.choices, required=False)
    category = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")

    def validate_requester_email(self, value: str) -> str:
        return value.strip().lower()

    def validate_description(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("This field may not be blank.")
        return value


class TicketUpdateSerializer(_StrictFieldsSerializer):
    """Partial field edit. The version comes from ``If-Match``, not the body."""

    allowed_fields = UPDATE_FIELDS

    subject = serializers.CharField(max_length=200, required=False)
    description = serializers.CharField(max_length=10000, trim_whitespace=False, required=False)
    priority = serializers.ChoiceField(choices=TicketPriority.choices, required=False)
    category = serializers.CharField(max_length=100, required=False)
    requester_email = serializers.EmailField(max_length=254, required=False)
    requester_name = serializers.CharField(max_length=200, required=False)

    def validate_requester_email(self, value: str) -> str:
        return value.strip().lower()

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = super().validate(attrs)
        if not attrs:
            raise serializers.ValidationError("Provide at least one field to change.")
        return attrs


class TicketListQuerySerializer(serializers.Serializer[Any]):
    """Validated ticket list query parameters.

    Every rejection is a field error, and no value is checked against the database:
    a foreign-but-well-formed assignee id is a filter that matches nothing, so the
    parameter cannot be used to test whether a user exists (ADR-023).
    """

    status = serializers.ChoiceField(choices=TicketStatus.choices, required=False)
    priority = serializers.ChoiceField(choices=TicketPriority.choices, required=False)
    assignee = serializers.CharField(required=False)
    search = serializers.CharField(required=False)
    ordering = serializers.CharField(required=False)

    def validate_assignee(self, value: str) -> str | UUID:
        if value in {ASSIGNEE_ME, ASSIGNEE_UNASSIGNED}:
            return value
        try:
            return UUID(value)
        except ValueError as exc:
            raise serializers.ValidationError("Use 'me', 'unassigned', or a user id.") from exc

    def validate_search(self, value: str) -> str:
        candidate = value.strip()
        if not 1 <= len(candidate) <= 100:
            raise serializers.ValidationError("Search must be 1 to 100 characters.")
        return candidate

    def validate_ordering(self, value: str) -> str:
        try:
            return parse_ordering(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc


class TicketAssignSerializer(serializers.Serializer[Any]):
    """Command input: the member to assign, or null to release the ticket."""

    assignee_id = serializers.UUIDField(allow_null=True)


class TicketTransitionSerializer(serializers.Serializer[Any]):
    """Command input: the status the ticket should move to."""

    status = serializers.ChoiceField(choices=TicketStatus.choices)


class TicketMessageSerializer(serializers.ModelSerializer[TicketMessage]):
    author = serializers.SerializerMethodField()

    class Meta:
        model = TicketMessage
        fields = ("id", "body", "visibility", "author", "created_at")
        read_only_fields = fields

    def get_author(self, obj: TicketMessage) -> dict[str, str] | None:
        if obj.author is None:
            return None
        return {"user_id": str(obj.author_id), "email": obj.author.email}


class TicketMessageCreateSerializer(serializers.Serializer[Any]):
    """Append-only message input; both visibilities are available to every member."""

    body = serializers.CharField(max_length=20000, trim_whitespace=False)
    visibility = serializers.ChoiceField(
        choices=MessageVisibility.choices,
        required=False,
        default=MessageVisibility.PUBLIC_REPLY.value,
    )

    def validate_body(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("This field may not be blank.")
        return value
