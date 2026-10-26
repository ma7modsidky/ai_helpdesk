"""Tenancy: the workspace boundary and the memberships that grant entry.

A workspace is the tenant. Every future tenant-owned row hangs off one, and a user
reaches it only through a membership row. That makes membership the authorization
primitive rather than a convenience join table: nothing may infer access from a
workspace identifier alone, and a role is only meaningful together with the
membership that carries it.
"""

from __future__ import annotations

import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class WorkspaceStatus(models.TextChoices):
    """Lifecycle of the tenant itself.

    Archived workspaces stay in the database so their history remains readable;
    whether they are reachable over the API is an authorization question, not a
    storage one.
    """

    ACTIVE = "active", "Active"
    ARCHIVED = "archived", "Archived"


class MembershipRole(models.TextChoices):
    """Roles, highest privilege first, as specified for the MVP.

    Customer access is deliberately absent: a portal would need a different access
    model, and widening these roles later is cheaper than narrowing them.
    """

    OWNER = "owner", "Owner"
    ADMIN = "admin", "Admin"
    MANAGER = "manager", "Manager"
    AGENT = "agent", "Agent"


class MembershipStatus(models.TextChoices):
    """Membership lifecycle. Only an active membership grants access."""

    ACTIVE = "active", "Active"
    REMOVED = "removed", "Removed"


# Ownership moves only through an explicit transfer, so a shared invite link can
# never confer it.
INVITABLE_ROLES: tuple[MembershipRole, ...] = (
    MembershipRole.ADMIN,
    MembershipRole.MANAGER,
    MembershipRole.AGENT,
)
INVITABLE_ROLE_VALUES: tuple[str, ...] = tuple(role.value for role in INVITABLE_ROLES)


class InvitationStatus(models.TextChoices):
    """Stored lifecycle of an invitation.

    Expiry is deliberately not a status: it is derived from ``expires_at`` so no
    background job has to rewrite rows, and ``effective_status`` reports it.
    """

    PENDING = "pending", "Pending"
    ACCEPTED = "accepted", "Accepted"
    REVOKED = "revoked", "Revoked"


class InvitationDeliveryStatus(models.TextChoices):
    """Outcome of the last delivery attempt; diagnostic, not a state machine."""

    PENDING = "pending", "Pending"
    SENT = "sent", "Sent"
    FAILED = "failed", "Failed"


def validate_timezone(value: str) -> None:
    """Accept only IANA time zone names the interpreter's database knows.

    The name is stored rather than an offset so that historical timestamps and
    daylight-saving changes resolve correctly later.
    """
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValidationError(
            "%(value)s is not a known IANA time zone.",
            params={"value": value},
        ) from exc


class Workspace(models.Model):
    """Tenant boundary with its display identity and regional settings."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=64, unique=True)
    timezone = models.CharField(
        max_length=64,
        default="UTC",
        validators=[validate_timezone],
        help_text="IANA time zone name, for example Europe/Berlin.",
    )
    settings = models.JSONField(
        default=dict,
        blank=True,
        help_text="Workspace-level preferences; shape is owned by the features that read it.",
    )
    status = models.CharField(
        max_length=16,
        choices=WorkspaceStatus.choices,
        default=WorkspaceStatus.ACTIVE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Stable ordering keeps paginated lists deterministic.
        ordering = ("name", "id")
        constraints = [
            # Choices are enforced in Python; the check keeps raw SQL and fixtures
            # from writing a status nothing recognizes.
            models.CheckConstraint(
                condition=models.Q(status__in=WorkspaceStatus.values),
                name="workspace_status_is_known",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Membership(models.Model):
    """A user's role inside one workspace."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(max_length=16, choices=MembershipRole.choices)
    status = models.CharField(
        max_length=16,
        choices=MembershipStatus.choices,
        default=MembershipStatus.ACTIVE,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("workspace_id", "created_at")
        constraints = [
            models.UniqueConstraint(
                fields=("workspace", "user"),
                name="unique_membership_per_workspace_user",
            ),
            # A role string outside the allowlist would silently widen or narrow
            # access, so the database refuses it rather than trusting the writer.
            models.CheckConstraint(
                condition=models.Q(role__in=MembershipRole.values),
                name="membership_role_is_known",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=MembershipStatus.values),
                name="membership_status_is_known",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} in {self.workspace_id} as {self.role}"


class Invitation(models.Model):
    """A single-use grant of a role in one workspace, addressed to an email.

    A pending invitation is not a membership: it appears in no member list, count,
    or permission check, which keeps member queries and the last-owner rule
    unchanged. Only the SHA-256 hash of the token is stored, so reading the table
    does not hand out access.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="invitations",
    )
    email = models.EmailField(max_length=254)
    role = models.CharField(max_length=16, choices=MembershipRole.choices)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invitations_sent",
    )
    token_hash = models.CharField(max_length=64, unique=True)
    status = models.CharField(
        max_length=16,
        choices=InvitationStatus.choices,
        default=InvitationStatus.PENDING,
    )
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invitations_accepted",
    )
    delivery_status = models.CharField(
        max_length=16,
        choices=InvitationDeliveryStatus.choices,
        default=InvitationDeliveryStatus.PENDING,
    )
    last_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Newest first; the id tie-break keeps pagination deterministic.
        ordering = ("-created_at", "id")
        constraints = [
            # One live invitation per address per workspace. A revoked or accepted
            # row does not block a later invitation, which is what makes re-inviting
            # a removed member possible.
            models.UniqueConstraint(
                fields=("workspace", "email"),
                condition=models.Q(status=InvitationStatus.PENDING),
                name="unique_pending_invitation_per_workspace_email",
            ),
            models.CheckConstraint(
                condition=models.Q(role__in=INVITABLE_ROLE_VALUES),
                name="invitation_role_is_invitable",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=InvitationStatus.values),
                name="invitation_status_is_known",
            ),
            models.CheckConstraint(
                condition=models.Q(delivery_status__in=InvitationDeliveryStatus.values),
                name="invitation_delivery_status_is_known",
            ),
        ]
        indexes = [
            models.Index(fields=("workspace", "status"), name="invitation_ws_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.email} in {self.workspace_id} as {self.role}"

    @property
    def is_expired(self) -> bool:
        """Whether a still-pending invitation is past its expiry."""
        return self.status == InvitationStatus.PENDING and self.expires_at <= timezone.now()

    @property
    def effective_status(self) -> str:
        """Stored status with expiry derived, for reads and API responses."""
        return "expired" if self.is_expired else str(self.status)
