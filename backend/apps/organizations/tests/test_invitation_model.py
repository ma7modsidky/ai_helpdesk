"""Model-level guarantees for invitations.

The interesting part is what the database refuses: two live invitations for one
address, and a role that would make a link confer ownership.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.organizations.models import (
    Invitation,
    InvitationDeliveryStatus,
    InvitationStatus,
    MembershipRole,
)
from apps.organizations.tests.factories import InvitationFactory, WorkspaceFactory

pytestmark = pytest.mark.django_db


def test_a_new_invitation_is_pending_and_undelivered() -> None:
    invitation = InvitationFactory.create()

    assert invitation.status == InvitationStatus.PENDING
    assert invitation.delivery_status == InvitationDeliveryStatus.PENDING
    assert not invitation.is_expired
    assert invitation.effective_status == "pending"
    assert invitation.expires_at > timezone.now()


def test_only_one_pending_invitation_exists_per_address() -> None:
    workspace = WorkspaceFactory.create()
    InvitationFactory.create(workspace=workspace, email="dup@example.com")

    with pytest.raises(IntegrityError), transaction.atomic():
        InvitationFactory.create(workspace=workspace, email="dup@example.com")


def test_the_same_address_can_be_invited_again_after_revocation() -> None:
    workspace = WorkspaceFactory.create()
    first = InvitationFactory.create(workspace=workspace, email="again@example.com")
    first.status = InvitationStatus.REVOKED
    first.save(update_fields=["status"])

    second = InvitationFactory.create(workspace=workspace, email="again@example.com")

    assert second.status == InvitationStatus.PENDING


def test_the_same_address_can_be_invited_in_another_workspace() -> None:
    first = InvitationFactory.create(email="shared@example.com")

    second = InvitationFactory.create(email="shared@example.com")

    assert second.workspace_id != first.workspace_id


def test_an_owner_role_is_refused_by_the_database() -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        InvitationFactory.create(role=MembershipRole.OWNER)


def test_an_unknown_status_is_refused_by_the_database() -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        InvitationFactory.create(status="expired")


def test_expiry_is_derived_rather_than_stored() -> None:
    expired = InvitationFactory.create(expires_at=timezone.now() - timedelta(minutes=1))

    assert expired.is_expired
    assert expired.effective_status == "expired"
    # The stored status is untouched: no scheduled job has to rewrite rows.
    assert expired.status == InvitationStatus.PENDING


def test_an_accepted_invitation_does_not_become_expired() -> None:
    accepted = InvitationFactory.create(
        status=InvitationStatus.ACCEPTED,
        expires_at=timezone.now() - timedelta(minutes=1),
    )

    assert not accepted.is_expired
    assert accepted.effective_status == "accepted"


def test_str_identifies_the_invitation() -> None:
    invitation = InvitationFactory.create(email="person@example.com")

    assert "person@example.com" in str(invitation)


def test_tokens_are_stored_as_a_hash() -> None:
    invitation = InvitationFactory.create()

    assert len(invitation.token_hash) == 64
    assert invitation.token_hash == invitation.token_hash.lower()
    assert not hasattr(invitation, "token")
    assert Invitation.objects.filter(token_hash=invitation.token_hash).exists()
