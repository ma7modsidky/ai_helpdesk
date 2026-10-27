"""Tickets: the unit of support work, its conversation, and its audit trail.

A ticket belongs to one workspace, so every query starts from the workspace the
caller was already authorized for. The requester is a *contact snapshot* rather
than an account (ADR-020): ``requester_email`` is always present, while
``requester_user`` is optional and, when set, must name an active member of the
same workspace. That rule spans two tables and therefore lives in the service
layer; the database still enforces every rule it can, so an unknown status,
priority or visibility cannot be written by raw SQL either.

``version`` is the optimistic-concurrency counter for field edits (ADR-022). It
changes when a ticket field changes and stays put when a message is appended, so
a reply never invalidates an edit a colleague is about to submit.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.conf import settings
from django.db import models


class TicketStatus(models.TextChoices):
    """Lifecycle of a ticket. Transitions are validated in the service layer."""

    OPEN = "open", "Open"
    IN_PROGRESS = "in_progress", "In progress"
    WAITING_ON_CUSTOMER = "waiting_on_customer", "Waiting on customer"
    RESOLVED = "resolved", "Resolved"
    CLOSED = "closed", "Closed"


class TicketPriority(models.TextChoices):
    """Triage urgency, independent of the status."""

    LOW = "low", "Low"
    NORMAL = "normal", "Normal"
    HIGH = "high", "High"
    URGENT = "urgent", "Urgent"


class MessageVisibility(models.TextChoices):
    """Who a message is meant for.

    Both visibilities are readable by any workspace member today because there is
    no customer-facing reader in MVP; the column exists so that adding one is a
    filter rather than a migration.
    """

    PUBLIC_REPLY = "public_reply", "Public reply"
    INTERNAL_NOTE = "internal_note", "Internal note"


class TicketEventType(models.TextChoices):
    """Auditable ticket events. Metadata stays minimal and never holds bodies."""

    CREATED = "ticket.created", "Ticket created"
    UPDATED = "ticket.updated", "Ticket fields updated"
    ASSIGNED = "ticket.assigned", "Ticket assigned"
    UNASSIGNED = "ticket.unassigned", "Ticket unassigned"
    STATUS_CHANGED = "ticket.status_changed", "Ticket status changed"
    MESSAGE_ADDED = "ticket.message_added", "Ticket message added"


def normalize_email(email: str) -> str:
    """Trim and lowercase an address so the snapshot matches membership matching."""
    return email.strip().lower()


class Ticket(models.Model):
    """One customer request, owned by a workspace and worked by its members."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        "organizations.Workspace",
        on_delete=models.CASCADE,
        related_name="tickets",
    )
    requester_email = models.EmailField(max_length=254)
    requester_name = models.CharField(max_length=200, blank=True, default="")
    requester_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requested_tickets",
        help_text="Set only when the requester is also an active member of this workspace.",
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_tickets",
    )
    subject = models.CharField(max_length=200)
    description = models.TextField()
    status = models.CharField(
        max_length=32,
        choices=TicketStatus.choices,
        default=TicketStatus.OPEN,
    )
    priority = models.CharField(
        max_length=16,
        choices=TicketPriority.choices,
        default=TicketPriority.NORMAL,
    )
    category = models.CharField(max_length=100, blank=True, default="")
    first_response_due_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Populated when an SLA policy is applied (Phase 8).",
    )
    first_responded_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Newest activity first; the id tie-break keeps pagination stable.
        ordering = ("-updated_at", "id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=TicketStatus.values),
                name="ticket_status_is_known",
            ),
            models.CheckConstraint(
                condition=models.Q(priority__in=TicketPriority.values),
                name="ticket_priority_is_known",
            ),
            # ``version`` is a counter compared against a client-held value, so a
            # zero or negative row could never match a legitimate If-Match.
            models.CheckConstraint(
                condition=models.Q(version__gte=1),
                name="ticket_version_is_positive",
            ),
        ]
        indexes = [
            # Default list order and the status-filtered inbox.
            models.Index(fields=("workspace", "-updated_at"), name="ticket_ws_updated_idx"),
            models.Index(
                fields=("workspace", "status", "updated_at"),
                name="ticket_ws_status_idx",
            ),
            # "My tickets" and the unassigned queue.
            models.Index(
                fields=("workspace", "assignee", "status"),
                name="ticket_ws_assignee_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.subject

    def save(self, *args: Any, **kwargs: Any) -> None:
        # Enforced here rather than only in the serializer: a management command or
        # a future import path must produce the same stored value.
        self.requester_email = normalize_email(self.requester_email)
        super().save(*args, **kwargs)


class TicketMessage(models.Model):
    """A public reply or an internal note on a ticket. Append-only in MVP."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ticket_messages",
    )
    body = models.TextField()
    visibility = models.CharField(
        max_length=16,
        choices=MessageVisibility.choices,
        default=MessageVisibility.PUBLIC_REPLY,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(visibility__in=MessageVisibility.values),
                name="ticket_message_visibility_is_known",
            ),
            models.CheckConstraint(
                condition=~models.Q(body=""),
                name="ticket_message_body_is_not_empty",
            ),
        ]
        indexes = [
            models.Index(fields=("ticket", "created_at"), name="ticket_message_ticket_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.visibility} on {self.ticket_id}"


class TicketEvent(models.Model):
    """Append-only audit record for a ticket change.

    Deliberately generic (``object_type`` plus ``object_id``) so later phases can
    record membership or AI events without another table. The API exposes no write
    path, and services only insert; nothing updates or deletes a row. Metadata
    names what changed — a status, a member id, a message id — and never copies a
    message body or requester contact details into the audit trail.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        "organizations.Workspace",
        on_delete=models.CASCADE,
        related_name="ticket_events",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ticket_events",
        help_text="Null for a system action.",
    )
    object_type = models.CharField(max_length=64, default="ticket")
    object_id = models.UUIDField()
    event_type = models.CharField(max_length=64, choices=TicketEventType.choices)
    metadata = models.JSONField(default=dict, blank=True)
    correlation_id = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(event_type__in=TicketEventType.values),
                name="ticket_event_type_is_known",
            ),
        ]
        indexes = [
            models.Index(fields=("workspace", "created_at"), name="ticket_event_ws_idx"),
            models.Index(
                fields=("object_type", "object_id", "created_at"),
                name="ticket_event_object_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} on {self.object_type}:{self.object_id}"
