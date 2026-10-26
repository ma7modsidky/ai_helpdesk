"""Invitation lifecycle: issue, deliver, resend, revoke, preview, accept.

The rules live here rather than in views so workers and management commands can
reuse them, and so the token handling has exactly one implementation. Two
properties matter more than anything else in this module:

* Only a SHA-256 hash of the token is persisted. A database read must not hand
  out the ability to join a workspace.
* A pending invitation is not a membership. Acceptance is the only path that
  writes a membership, which keeps member lists, counts, and the last-owner rule
  untouched by invitations that were never used.

Delivery is best effort and never the source of truth: the row is created first,
the outcome is recorded in ``delivery_status``, and resend is the retry path.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import timedelta
from uuid import UUID

from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.utils import timezone

from apps.accounts.models import User

from .exceptions import (
    InvitationAlreadyPending,
    InvitationEmailMismatch,
    InvitationEmailTaken,
    InvitationExpired,
    InvitationNotFound,
    InvitationNotPending,
    InvitationRoleNotAllowed,
    MembershipRoleConflict,
)
from .models import (
    INVITABLE_ROLES,
    Invitation,
    InvitationDeliveryStatus,
    InvitationStatus,
    Membership,
    MembershipRole,
    MembershipStatus,
    Workspace,
    WorkspaceStatus,
)

logger = logging.getLogger(__name__)

INVITATION_TTL = timedelta(days=7)


def normalize_email(email: str) -> str:
    """Trim and lowercase an address so uniqueness is not case-sensitive."""
    return email.strip().lower()


def hash_token(token: str) -> str:
    """Return the stored representation of an invitation token."""
    return hashlib.sha256(token.strip().encode()).hexdigest()


def accept_path(token: str) -> str:
    """The SPA route that carries a token, returned to the inviter once."""
    return f"/invite/{token}"


def accept_url(token: str) -> str:
    """Absolute URL for the invitation email."""
    base_url = settings.FRONTEND_BASE_URL or ""
    return f"{base_url.rstrip('/')}{accept_path(token)}"


def _issue_token() -> tuple[str, str]:
    """Return ``(raw token, token hash)``. Only the hash may be stored."""
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def _deliver(invitation: Invitation, token: str) -> InvitationDeliveryStatus:
    """Attempt delivery and record the outcome without failing the request."""
    inviter = (
        invitation.invited_by.email if invitation.invited_by is not None else "An administrator"
    )
    try:
        send_mail(
            subject=f"You are invited to {invitation.workspace.name}",
            message=(
                f"{inviter} invited you to join {invitation.workspace.name} "
                f"as {invitation.role}.\n\n"
                f"Accept the invitation: {accept_url(token)}\n\n"
                f"The link expires on {invitation.expires_at:%Y-%m-%d %H:%M} UTC "
                "and can be used once."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[invitation.email],
            fail_silently=False,
        )
    except Exception:
        # Deliberately broad: a provider outage must not undo a created invitation,
        # and the log line carries identifiers only — never the address or token.
        logger.warning(
            "invitation_delivery_failed",
            extra={
                "invitation_id": str(invitation.pk),
                "workspace_id": str(invitation.workspace_id),
            },
        )
        delivery_status = InvitationDeliveryStatus.FAILED
    else:
        delivery_status = InvitationDeliveryStatus.SENT

    sent_at = timezone.now()
    Invitation.objects.filter(pk=invitation.pk).update(
        delivery_status=delivery_status,
        last_sent_at=sent_at,
    )
    invitation.delivery_status = delivery_status.value
    invitation.last_sent_at = sent_at
    return delivery_status


def invitation_queryset(workspace: Workspace, status: str) -> QuerySet[Invitation]:
    """Invitations in one workspace, newest first, optionally filtered by status.

    ``pending`` includes rows that have expired: both are actionable through
    resend, and each row reports which state it is in.
    """
    queryset = Invitation.objects.filter(workspace=workspace).select_related("invited_by")
    if status == "all":
        return queryset
    return queryset.filter(status=status)


def create_invitation(
    *, workspace: Workspace, inviter: User, email: str, role: str
) -> tuple[Invitation, str]:
    """Create a pending invitation and try to deliver it.

    Returns the invitation and the raw token, which the caller may show exactly
    once. Two simultaneous invitations for one address are arbitrated by the
    partial unique constraint rather than by a pre-check, in the same spirit as
    ADR-019: only the database can decide a race.
    """
    normalized_email = normalize_email(email)
    try:
        invitation_role = MembershipRole(role)
    except ValueError as exc:
        raise InvitationRoleNotAllowed from exc
    if invitation_role not in INVITABLE_ROLES:
        raise InvitationRoleNotAllowed

    already_member = Membership.objects.filter(
        workspace=workspace,
        status=MembershipStatus.ACTIVE,
        user__email=normalized_email,
    ).exists()
    if already_member:
        raise InvitationEmailTaken

    token, token_hash = _issue_token()
    try:
        with transaction.atomic():
            invitation = Invitation.objects.create(
                workspace=workspace,
                email=normalized_email,
                role=invitation_role.value,
                invited_by=inviter,
                token_hash=token_hash,
                expires_at=timezone.now() + INVITATION_TTL,
            )
    except IntegrityError as exc:
        # ``token_hash`` is unique too, but a collision on 32 random bytes is not a
        # real failure mode; the constraint that fires in practice is the pending
        # invitation for this (workspace, email).
        raise InvitationAlreadyPending from exc

    _deliver(invitation, token)
    return invitation, token


def resend_invitation(*, workspace: Workspace, invitation_id: UUID) -> tuple[Invitation, str]:
    """Rotate the token and expiry of a pending invitation, then retry delivery."""
    with transaction.atomic():
        invitation = (
            # ``invited_by`` is nullable, so the join is an outer one and the lock
            # must be limited to this table.
            Invitation.objects.select_for_update(of=("self",))
            .select_related("workspace", "invited_by")
            .filter(workspace=workspace, pk=invitation_id)
            .first()
        )
        if invitation is None:
            raise InvitationNotFound
        if invitation.status != InvitationStatus.PENDING:
            raise InvitationNotPending

        token, token_hash = _issue_token()
        invitation.token_hash = token_hash
        invitation.expires_at = timezone.now() + INVITATION_TTL
        invitation.save(update_fields=["token_hash", "expires_at", "updated_at"])

    _deliver(invitation, token)
    return invitation, token


def revoke_invitation(*, workspace: Workspace, invitation_id: UUID) -> None:
    """Cancel a pending invitation, invalidating its token immediately.

    Revoking an already revoked invitation is a no-op so the command is safe to
    retry; an accepted one cannot be revoked, because the member exists and
    removing them is a membership change.
    """
    with transaction.atomic():
        invitation = (
            Invitation.objects.select_for_update()
            .filter(workspace=workspace, pk=invitation_id)
            .first()
        )
        if invitation is None:
            raise InvitationNotFound
        if invitation.status == InvitationStatus.ACCEPTED:
            raise InvitationNotPending
        if invitation.status == InvitationStatus.REVOKED:
            return
        invitation.status = InvitationStatus.REVOKED
        invitation.save(update_fields=["status", "updated_at"])


def preview_invitation(*, token: str) -> Invitation:
    """Look up an invitation by token without revealing the invited address."""
    invitation = (
        Invitation.objects.select_related("workspace").filter(token_hash=hash_token(token)).first()
    )
    if invitation is None or invitation.workspace.status != WorkspaceStatus.ACTIVE:
        raise InvitationNotFound
    return invitation


def accept_invitation(*, user: User, token: str) -> tuple[Workspace, Membership]:
    """Join the workspace the token belongs to, as the invited role.

    The invitation row is locked so two simultaneous accepts cannot both create a
    membership. An existing active membership with the same role makes the call
    idempotent; a different role is refused rather than silently changed.
    """
    with transaction.atomic():
        invitation = (
            Invitation.objects.select_for_update()
            .select_related("workspace")
            .filter(token_hash=hash_token(token))
            .first()
        )
        if invitation is None or invitation.workspace.status != WorkspaceStatus.ACTIVE:
            raise InvitationNotFound
        if invitation.status == InvitationStatus.REVOKED:
            raise InvitationNotFound
        if invitation.status == InvitationStatus.ACCEPTED:
            membership = Membership.objects.filter(
                workspace=invitation.workspace,
                user=user,
                status=MembershipStatus.ACTIVE,
            ).first()
            if invitation.accepted_by_id == user.pk and membership is not None:
                return invitation.workspace, membership
            raise InvitationNotPending

        if invitation.expires_at <= timezone.now():
            raise InvitationExpired
        if normalize_email(user.email) != normalize_email(invitation.email):
            raise InvitationEmailMismatch

        membership = Membership.objects.filter(
            workspace=invitation.workspace,
            user=user,
        ).first()
        if membership is None:
            membership = Membership.objects.create(
                workspace=invitation.workspace,
                user=user,
                role=invitation.role,
            )
        elif membership.status == MembershipStatus.ACTIVE:
            if membership.role != invitation.role:
                raise MembershipRoleConflict
        else:
            # Re-inviting a removed member is the documented restore path.
            membership.role = invitation.role
            membership.status = MembershipStatus.ACTIVE
            membership.save(update_fields=["role", "status"])

        invitation.status = InvitationStatus.ACCEPTED
        invitation.accepted_at = timezone.now()
        invitation.accepted_by = user
        invitation.save(update_fields=["status", "accepted_at", "accepted_by", "updated_at"])

    return invitation.workspace, membership
