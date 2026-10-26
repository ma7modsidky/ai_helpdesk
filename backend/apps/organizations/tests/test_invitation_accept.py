"""Invitee-side tests: preview, acceptance, reactivation, and refusal.

Acceptance is the only path that turns an invitation into a membership, so these
tests check the membership that results, not just the status code.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from django.test import Client
from django.utils import timezone

from apps.accounts.tests.factories import DEFAULT_PASSWORD, UserFactory
from apps.organizations.models import (
    Invitation,
    InvitationStatus,
    Membership,
    MembershipRole,
    MembershipStatus,
    WorkspaceStatus,
)
from apps.organizations.tests.factories import (
    MembershipFactory,
    WorkspaceFactory,
    issued_invitation,
)
from tests.support import CsrfClient, login

if TYPE_CHECKING:
    from django.test.client import _MonkeyPatchedWSGIResponse

pytestmark = pytest.mark.django_db

API = "/api/v1"
PREVIEW = f"{API}/invitations/preview/"
ACCEPT = f"{API}/invitations/accept/"


def preview(client: Client, token: str) -> _MonkeyPatchedWSGIResponse:
    return client.post(PREVIEW, data={"token": token}, content_type="application/json")


def sign_in(client: CsrfClient, email: str) -> CsrfClient:
    return login(client, email=email, password=DEFAULT_PASSWORD)


def test_preview_is_public_and_hides_the_invited_address(client: Client) -> None:
    workspace = WorkspaceFactory.create(name="Acme Support")
    _, token = issued_invitation(workspace=workspace, email="secret@example.com", role="manager")

    response = preview(client, token)

    assert response.status_code == 200
    body = response.json()
    assert body["workspace_name"] == "Acme Support"
    assert body["role"] == "manager"
    assert body["status"] == "pending"
    assert "secret@example.com" not in response.content.decode()
    assert set(body) == {"workspace_name", "role", "status", "expires_at"}


def test_preview_reports_expiry_and_use(client: Client) -> None:
    workspace = WorkspaceFactory.create()
    _, expired_token = issued_invitation(
        workspace=workspace,
        email="late@example.com",
        expires_at=timezone.now() - timedelta(minutes=1),
    )
    _, accepted_token = issued_invitation(
        workspace=workspace,
        email="done@example.com",
        status=InvitationStatus.ACCEPTED,
    )

    assert preview(client, expired_token).json()["status"] == "expired"
    assert preview(client, accepted_token).json()["status"] == "accepted"


def test_preview_of_an_unknown_token_is_not_found(client: Client) -> None:
    response = preview(client, "not-a-real-token")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_preview_of_an_archived_workspace_is_not_found(client: Client) -> None:
    workspace = WorkspaceFactory.create(status=WorkspaceStatus.ARCHIVED)
    _, token = issued_invitation(workspace=workspace)

    assert preview(client, token).status_code == 404


def test_accept_requires_authentication(client: Client) -> None:
    workspace = WorkspaceFactory.create()
    _, token = issued_invitation(workspace=workspace)

    response = client.post(ACCEPT, data={"token": token}, content_type="application/json")

    assert response.status_code == 401


def test_accept_requires_a_csrf_token(csrf_client: CsrfClient) -> None:
    workspace = WorkspaceFactory.create()
    _, token = issued_invitation(workspace=workspace, email="invitee@example.com")
    UserFactory.create(email="invitee@example.com")
    sign_in(csrf_client, "invitee@example.com")

    response = csrf_client.post(ACCEPT, data={"token": token}, content_type="application/json")

    assert response.status_code == 403
    assert Membership.objects.count() == 0


def test_accept_joins_the_workspace_with_the_invited_role(csrf_client: CsrfClient) -> None:
    workspace = WorkspaceFactory.create(name="Acme")
    invitation, token = issued_invitation(
        workspace=workspace, email="invitee@example.com", role="manager"
    )
    invitee = UserFactory.create(email="invitee@example.com")
    sign_in(csrf_client, invitee.email)

    response = csrf_client.post_json(ACCEPT, {"token": token})

    assert response.status_code == 200
    body = response.json()
    assert body["workspace"]["id"] == str(workspace.id)
    assert body["membership"]["role"] == "manager"
    assert body["membership"]["email"] == "invitee@example.com"

    membership = Membership.objects.get(workspace=workspace, user=invitee)
    assert membership.role == MembershipRole.MANAGER
    assert membership.status == MembershipStatus.ACTIVE

    invitation.refresh_from_db()
    assert invitation.status == InvitationStatus.ACCEPTED
    assert invitation.accepted_by_id == invitee.pk
    assert invitation.accepted_at is not None


def test_accepting_from_a_different_address_is_forbidden(csrf_client: CsrfClient) -> None:
    workspace = WorkspaceFactory.create()
    invitation, token = issued_invitation(workspace=workspace, email="invitee@example.com")
    stranger = UserFactory.create(email="stranger@example.com")
    sign_in(csrf_client, stranger.email)

    response = csrf_client.post_json(ACCEPT, {"token": token})

    assert response.status_code == 403
    assert not Membership.objects.filter(workspace=workspace, user=stranger).exists()
    invitation.refresh_from_db()
    assert invitation.status == InvitationStatus.PENDING


def test_an_expired_invitation_is_a_conflict_with_its_own_code(
    csrf_client: CsrfClient,
) -> None:
    workspace = WorkspaceFactory.create()
    _, token = issued_invitation(
        workspace=workspace,
        email="invitee@example.com",
        expires_at=timezone.now() - timedelta(minutes=1),
    )
    sign_in(csrf_client, UserFactory.create(email="invitee@example.com").email)

    response = csrf_client.post_json(ACCEPT, {"token": token})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invitation_expired"
    assert not Membership.objects.filter(workspace=workspace).exists()


def test_a_revoked_invitation_is_not_found(csrf_client: CsrfClient) -> None:
    workspace = WorkspaceFactory.create()
    _, token = issued_invitation(
        workspace=workspace,
        email="invitee@example.com",
        status=InvitationStatus.REVOKED,
    )
    sign_in(csrf_client, UserFactory.create(email="invitee@example.com").email)

    assert csrf_client.post_json(ACCEPT, {"token": token}).status_code == 404


def test_an_unknown_token_is_not_found(csrf_client: CsrfClient) -> None:
    sign_in(csrf_client, UserFactory.create(email="invitee@example.com").email)

    response = csrf_client.post_json(ACCEPT, {"token": "unknown"})

    assert response.status_code == 404


def test_accepting_twice_is_idempotent(csrf_client: CsrfClient) -> None:
    workspace = WorkspaceFactory.create()
    _, token = issued_invitation(workspace=workspace, email="invitee@example.com")
    invitee = UserFactory.create(email="invitee@example.com")
    sign_in(csrf_client, invitee.email)

    first = csrf_client.post_json(ACCEPT, {"token": token})
    second = csrf_client.post_json(ACCEPT, {"token": token})

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["membership"]["id"] == first.json()["membership"]["id"]
    assert Membership.objects.filter(workspace=workspace, user=invitee).count() == 1


def test_a_removed_membership_is_reactivated_with_the_invited_role(
    csrf_client: CsrfClient,
) -> None:
    workspace = WorkspaceFactory.create()
    invitee = UserFactory.create(email="invitee@example.com")
    MembershipFactory.create(
        workspace=workspace,
        user=invitee,
        role=MembershipRole.AGENT,
        status=MembershipStatus.REMOVED,
    )
    _, token = issued_invitation(workspace=workspace, email="invitee@example.com", role="manager")
    sign_in(csrf_client, invitee.email)

    response = csrf_client.post_json(ACCEPT, {"token": token})

    assert response.status_code == 200
    membership = Membership.objects.get(workspace=workspace, user=invitee)
    assert membership.status == MembershipStatus.ACTIVE
    assert membership.role == MembershipRole.MANAGER


def test_an_active_membership_with_a_different_role_is_a_conflict(
    csrf_client: CsrfClient,
) -> None:
    workspace = WorkspaceFactory.create()
    invitee = UserFactory.create(email="invitee@example.com")
    membership = MembershipFactory.create(
        workspace=workspace, user=invitee, role=MembershipRole.AGENT
    )
    invitation, token = issued_invitation(
        workspace=workspace, email="invitee@example.com", role="manager"
    )
    sign_in(csrf_client, invitee.email)

    response = csrf_client.post_json(ACCEPT, {"token": token})

    assert response.status_code == 409
    membership.refresh_from_db()
    assert membership.role == MembershipRole.AGENT
    invitation.refresh_from_db()
    assert invitation.status == InvitationStatus.PENDING


def test_an_active_membership_with_the_same_role_accepts_idempotently(
    csrf_client: CsrfClient,
) -> None:
    workspace = WorkspaceFactory.create()
    invitee = UserFactory.create(email="invitee@example.com")
    MembershipFactory.create(workspace=workspace, user=invitee, role=MembershipRole.AGENT)
    invitation, token = issued_invitation(
        workspace=workspace, email="invitee@example.com", role="agent"
    )
    sign_in(csrf_client, invitee.email)

    response = csrf_client.post_json(ACCEPT, {"token": token})

    assert response.status_code == 200
    invitation.refresh_from_db()
    assert invitation.status == InvitationStatus.ACCEPTED
    assert Membership.objects.filter(workspace=workspace, user=invitee).count() == 1


def test_a_workspace_archived_before_acceptance_is_not_found(
    csrf_client: CsrfClient,
) -> None:
    workspace = WorkspaceFactory.create(status=WorkspaceStatus.ARCHIVED)
    _, token = issued_invitation(workspace=workspace, email="invitee@example.com")
    sign_in(csrf_client, UserFactory.create(email="invitee@example.com").email)

    assert csrf_client.post_json(ACCEPT, {"token": token}).status_code == 404
    assert not Membership.objects.filter(workspace=workspace).exists()


def test_an_invitation_accepted_by_another_account_cannot_be_reused(
    csrf_client: CsrfClient,
) -> None:
    workspace = WorkspaceFactory.create()
    other = UserFactory.create(email="other@example.com")
    _, token = issued_invitation(
        workspace=workspace,
        email="invitee@example.com",
        status=InvitationStatus.ACCEPTED,
        accepted_by=other,
        accepted_at=timezone.now(),
    )
    sign_in(csrf_client, UserFactory.create(email="invitee@example.com").email)

    response = csrf_client.post_json(ACCEPT, {"token": token})

    assert response.status_code == 409
    assert not Membership.objects.filter(workspace=workspace).exists()


def test_the_address_comparison_ignores_case(csrf_client: CsrfClient) -> None:
    workspace = WorkspaceFactory.create()
    invitation, token = issued_invitation(workspace=workspace)
    Invitation.objects.filter(pk=invitation.pk).update(email="INVITEE@Example.COM")
    sign_in(csrf_client, UserFactory.create(email="invitee@example.com").email)

    response = csrf_client.post_json(ACCEPT, {"token": token})

    assert response.status_code == 200


def test_accepting_clears_the_invitation_from_the_pending_list(
    csrf_client: CsrfClient,
) -> None:
    workspace = WorkspaceFactory.create()
    owner = UserFactory.create(email="owner@example.com")
    MembershipFactory.create(workspace=workspace, user=owner, role=MembershipRole.OWNER)
    _, token = issued_invitation(workspace=workspace, email="invitee@example.com")
    sign_in(csrf_client, UserFactory.create(email="invitee@example.com").email)
    csrf_client.post_json(ACCEPT, {"token": token})

    sign_in(csrf_client, owner.email)
    pending = csrf_client.get(f"{API}/workspaces/{workspace.id}/invitations/").json()

    assert pending["results"] == []
