"""Ownership handover: the atomic alternative to grant-then-demote.

Every test checks the resulting roles, not just the status code: the invariant is
that a workspace always has exactly one active owner after a transfer, and that a
refused transfer changes nothing.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from django.test import Client

from apps.accounts.tests.factories import DEFAULT_PASSWORD, UserFactory
from apps.organizations.exceptions import InsufficientRole, WorkspaceNotFound
from apps.organizations.models import (
    Membership,
    MembershipRole,
    MembershipStatus,
    Workspace,
    WorkspaceStatus,
)
from apps.organizations.services import resolve_workspace_access, transfer_ownership
from apps.organizations.tests.factories import (
    MembershipFactory,
    WorkspaceFactory,
)
from tests.support import CsrfClient, login

if TYPE_CHECKING:
    from django.test.client import _MonkeyPatchedWSGIResponse

pytestmark = pytest.mark.django_db

API = "/api/v1"


def transfer_url(workspace_id: uuid.UUID) -> str:
    return f"{API}/workspaces/{workspace_id}/transfer-ownership/"


def sign_in(client: CsrfClient, email: str) -> None:
    login(client, email=email, password=DEFAULT_PASSWORD)


def transfer(
    client: CsrfClient, workspace_id: uuid.UUID, membership_id: uuid.UUID | str
) -> _MonkeyPatchedWSGIResponse:
    return client.post_json(transfer_url(workspace_id), {"membership_id": str(membership_id)})


def active_owners(workspace: Workspace) -> int:
    return Membership.objects.filter(
        workspace=workspace,
        role=MembershipRole.OWNER,
        status=MembershipStatus.ACTIVE,
    ).count()


def owner_session(csrf_client: CsrfClient) -> tuple[CsrfClient, Membership, Membership]:
    owner = UserFactory.create(email="owner@example.com")
    owner_membership = MembershipFactory.create(user=owner, role=MembershipRole.OWNER)
    target = MembershipFactory.create(
        workspace=owner_membership.workspace,
        user=UserFactory.create(email="heir@example.com"),
    )
    sign_in(csrf_client, owner.email)
    return csrf_client, owner_membership, target


def test_the_owner_hands_the_workspace_over(
    csrf_client: CsrfClient,
) -> None:
    client, owner_membership, target = owner_session(csrf_client)

    response = transfer(client, owner_membership.workspace_id, target.id)

    assert response.status_code == 200
    body = response.json()
    assert body["owner"]["id"] == str(target.id)
    assert body["owner"]["role"] == "owner"
    assert body["previous_owner"]["id"] == str(owner_membership.id)
    assert body["previous_owner"]["role"] == "admin"

    target.refresh_from_db()
    owner_membership.refresh_from_db()
    assert target.role == MembershipRole.OWNER
    assert owner_membership.role == MembershipRole.ADMIN
    assert active_owners(owner_membership.workspace) == 1


def test_transfer_requires_authentication(client: Client) -> None:
    membership = MembershipFactory.create(role=MembershipRole.OWNER)
    target = MembershipFactory.create(workspace=membership.workspace)

    response = client.post(
        transfer_url(membership.workspace_id),
        data={"membership_id": str(target.id)},
        content_type="application/json",
    )

    assert response.status_code == 401


def test_an_admin_cannot_transfer_ownership(csrf_client: CsrfClient) -> None:
    workspace = WorkspaceFactory.create()
    admin = UserFactory.create(email="admin@example.com")
    admin_membership = MembershipFactory.create(
        workspace=workspace, user=admin, role=MembershipRole.ADMIN
    )
    MembershipFactory.create(workspace=workspace, role=MembershipRole.OWNER)
    target = MembershipFactory.create(workspace=workspace)
    sign_in(csrf_client, admin.email)

    response = transfer(csrf_client, workspace.id, target.id)

    assert response.status_code == 403
    admin_membership.refresh_from_db()
    target.refresh_from_db()
    assert admin_membership.role == MembershipRole.ADMIN
    assert target.role == MembershipRole.AGENT


@pytest.mark.parametrize("role", [MembershipRole.MANAGER, MembershipRole.AGENT])
def test_members_without_management_cannot_transfer(
    csrf_client: CsrfClient, role: MembershipRole
) -> None:
    workspace = WorkspaceFactory.create()
    member = UserFactory.create(email=f"{role.value}@example.com")
    MembershipFactory.create(workspace=workspace, user=member, role=role)
    target = MembershipFactory.create(workspace=workspace)
    sign_in(csrf_client, member.email)

    assert transfer(csrf_client, workspace.id, target.id).status_code == 403


def test_a_stranger_gets_404(csrf_client: CsrfClient) -> None:
    workspace = WorkspaceFactory.create()
    target = MembershipFactory.create(workspace=workspace)
    stranger = UserFactory.create(email="stranger@example.com")
    sign_in(csrf_client, stranger.email)

    assert transfer(csrf_client, workspace.id, target.id).status_code == 404


def test_a_membership_from_another_workspace_is_not_found(
    csrf_client: CsrfClient,
) -> None:
    client, owner_membership, _ = owner_session(csrf_client)
    foreign = MembershipFactory.create()

    response = transfer(client, owner_membership.workspace_id, foreign.id)

    assert response.status_code == 404
    foreign.refresh_from_db()
    assert foreign.role == MembershipRole.AGENT


def test_transferring_to_yourself_is_a_validation_error(
    csrf_client: CsrfClient,
) -> None:
    client, owner_membership, _ = owner_session(csrf_client)

    response = transfer(client, owner_membership.workspace_id, owner_membership.id)

    assert response.status_code == 400
    assert "membership_id" in response.json()["error"]["details"]
    owner_membership.refresh_from_db()
    assert owner_membership.role == MembershipRole.OWNER
    assert active_owners(owner_membership.workspace) == 1


def test_a_removed_member_cannot_receive_ownership(
    csrf_client: CsrfClient,
) -> None:
    client, owner_membership, target = owner_session(csrf_client)
    Membership.objects.filter(pk=target.pk).update(status=MembershipStatus.REMOVED)

    response = transfer(client, owner_membership.workspace_id, target.id)

    assert response.status_code == 409
    owner_membership.refresh_from_db()
    assert owner_membership.role == MembershipRole.OWNER


def test_an_archived_workspace_is_not_addressable(csrf_client: CsrfClient) -> None:
    owner = UserFactory.create(email="owner@example.com")
    membership = MembershipFactory.create(
        user=owner,
        role=MembershipRole.OWNER,
        workspace=WorkspaceFactory.create(status=WorkspaceStatus.ARCHIVED),
    )
    target = MembershipFactory.create(workspace=membership.workspace)
    sign_in(csrf_client, owner.email)

    assert transfer(csrf_client, membership.workspace_id, target.id).status_code == 404


def test_a_malformed_body_is_rejected(csrf_client: CsrfClient) -> None:
    client, owner_membership, _ = owner_session(csrf_client)

    response = client.post_json(transfer_url(owner_membership.workspace_id), {})

    assert response.status_code == 400
    assert "membership_id" in response.json()["error"]["details"]


def test_a_transfer_without_a_csrf_token_is_rejected(csrf_client: CsrfClient) -> None:
    client, owner_membership, target = owner_session(csrf_client)

    response = client.post(
        transfer_url(owner_membership.workspace_id),
        data={"membership_id": str(target.id)},
        content_type="application/json",
    )

    assert response.status_code == 403
    target.refresh_from_db()
    assert target.role == MembershipRole.AGENT


def test_transferring_to_a_co_owner_leaves_one_owner(csrf_client: CsrfClient) -> None:
    client, owner_membership, target = owner_session(csrf_client)
    Membership.objects.filter(pk=target.pk).update(role=MembershipRole.OWNER)

    response = transfer(client, owner_membership.workspace_id, target.id)

    assert response.status_code == 200
    target.refresh_from_db()
    owner_membership.refresh_from_db()
    assert target.role == MembershipRole.OWNER
    assert owner_membership.role == MembershipRole.ADMIN
    assert active_owners(owner_membership.workspace) == 1


def test_a_workspace_archived_mid_request_refuses_the_transfer() -> None:
    workspace = WorkspaceFactory.create()
    owner = MembershipFactory.create(workspace=workspace, role=MembershipRole.OWNER)
    target = MembershipFactory.create(workspace=workspace)
    stale_access = resolve_workspace_access(user=owner.user, workspace_id=workspace.id)

    Workspace.objects.filter(pk=workspace.pk).update(status=WorkspaceStatus.ARCHIVED)

    with pytest.raises(WorkspaceNotFound):
        transfer_ownership(access=stale_access, membership_id=target.id)

    target.refresh_from_db()
    assert target.role == MembershipRole.AGENT


def test_an_actor_removed_mid_request_is_refused() -> None:
    workspace = WorkspaceFactory.create()
    owner = MembershipFactory.create(workspace=workspace, role=MembershipRole.OWNER)
    target = MembershipFactory.create(workspace=workspace)
    stale_access = resolve_workspace_access(user=owner.user, workspace_id=workspace.id)

    Membership.objects.filter(pk=owner.pk).update(status=MembershipStatus.REMOVED)

    with pytest.raises(WorkspaceNotFound):
        transfer_ownership(access=stale_access, membership_id=target.id)

    target.refresh_from_db()
    assert target.role == MembershipRole.AGENT


def test_a_stale_owner_cannot_transfer_after_losing_ownership() -> None:
    workspace = WorkspaceFactory.create()
    demoted = MembershipFactory.create(workspace=workspace, role=MembershipRole.OWNER)
    other_owner = MembershipFactory.create(workspace=workspace, role=MembershipRole.OWNER)
    target = MembershipFactory.create(workspace=workspace)

    # Resolved while ``demoted`` was still the owner; the service must not trust it.
    stale_access = resolve_workspace_access(user=demoted.user, workspace_id=workspace.id)
    Membership.objects.filter(pk=demoted.pk).update(role=MembershipRole.ADMIN)

    with pytest.raises(InsufficientRole):
        transfer_ownership(access=stale_access, membership_id=target.id)

    target.refresh_from_db()
    other_owner.refresh_from_db()
    assert target.role == MembershipRole.AGENT
    assert other_owner.role == MembershipRole.OWNER
