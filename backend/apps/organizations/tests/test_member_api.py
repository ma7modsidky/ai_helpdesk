from __future__ import annotations

import uuid

import pytest
from django.test import Client

from apps.accounts.tests.factories import DEFAULT_PASSWORD, UserFactory
from apps.organizations.models import (
    Membership,
    MembershipRole,
    MembershipStatus,
    WorkspaceStatus,
)
from apps.organizations.tests.factories import (
    MembershipFactory,
    WorkspaceFactory,
)
from tests.support import CsrfClient, login

pytestmark = pytest.mark.django_db


def members_url(workspace_id: uuid.UUID) -> str:
    return f"/api/v1/workspaces/{workspace_id}/members/"


def member_url(workspace_id: uuid.UUID, membership_id: uuid.UUID) -> str:
    return f"{members_url(workspace_id)}{membership_id}/"


def sign_in(client: CsrfClient, email: str) -> CsrfClient:
    return login(client, email=email, password=DEFAULT_PASSWORD)


def test_list_requires_authentication(client: Client) -> None:
    workspace = WorkspaceFactory.create()

    response = client.get(members_url(workspace.id))

    assert response.status_code == 401


def test_an_agent_can_list_active_members(csrf_client: CsrfClient) -> None:
    agent = UserFactory.create(email="agent@example.com")
    owner = UserFactory.create(email="owner@example.com")
    removed = UserFactory.create(email="gone@example.com")
    membership = MembershipFactory.create(user=agent, role=MembershipRole.AGENT)
    workspace = membership.workspace
    MembershipFactory.create(workspace=workspace, user=owner, role=MembershipRole.OWNER)
    MembershipFactory.create(workspace=workspace, user=removed, status=MembershipStatus.REMOVED)
    sign_in(csrf_client, agent.email)

    response = csrf_client.get(members_url(workspace.id))

    assert response.status_code == 200
    emails = {row["email"] for row in response.json()["results"]}
    assert emails == {"agent@example.com", "owner@example.com"}


def test_a_non_member_cannot_list_members(csrf_client: CsrfClient) -> None:
    workspace = WorkspaceFactory.create()
    stranger = UserFactory.create(email="stranger@example.com")
    sign_in(csrf_client, stranger.email)

    response = csrf_client.get(members_url(workspace.id))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_a_removed_member_cannot_list_members(csrf_client: CsrfClient) -> None:
    user = UserFactory.create(email="removed@example.com")
    membership = MembershipFactory.create(user=user, status=MembershipStatus.REMOVED)
    sign_in(csrf_client, user.email)

    response = csrf_client.get(members_url(membership.workspace_id))

    assert response.status_code == 404


def test_an_agent_cannot_change_a_role(csrf_client: CsrfClient) -> None:
    agent = UserFactory.create(email="agent@example.com")
    membership = MembershipFactory.create(user=agent)
    target = MembershipFactory.create(workspace=membership.workspace)
    sign_in(csrf_client, agent.email)

    response = csrf_client.patch_json(
        member_url(membership.workspace_id, target.id), {"role": "manager"}
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"
    target.refresh_from_db()
    assert target.role == MembershipRole.AGENT


def test_an_admin_can_promote_an_agent(csrf_client: CsrfClient) -> None:
    admin = UserFactory.create(email="admin@example.com")
    membership = MembershipFactory.create(user=admin, role=MembershipRole.ADMIN)
    target = MembershipFactory.create(workspace=membership.workspace)
    sign_in(csrf_client, admin.email)

    response = csrf_client.patch_json(
        member_url(membership.workspace_id, target.id), {"role": "manager"}
    )

    assert response.status_code == 200
    assert response.json()["role"] == "manager"
    target.refresh_from_db()
    assert target.role == MembershipRole.MANAGER


def test_an_admin_cannot_create_a_peer(csrf_client: CsrfClient) -> None:
    admin = UserFactory.create(email="admin@example.com")
    membership = MembershipFactory.create(user=admin, role=MembershipRole.ADMIN)
    target = MembershipFactory.create(workspace=membership.workspace)
    sign_in(csrf_client, admin.email)

    response = csrf_client.patch_json(
        member_url(membership.workspace_id, target.id), {"role": "admin"}
    )

    assert response.status_code == 403


def test_an_admin_cannot_change_another_admin(csrf_client: CsrfClient) -> None:
    admin = UserFactory.create(email="admin@example.com")
    membership = MembershipFactory.create(user=admin, role=MembershipRole.ADMIN)
    peer = MembershipFactory.create(workspace=membership.workspace, role=MembershipRole.ADMIN)
    sign_in(csrf_client, admin.email)

    response = csrf_client.patch_json(
        member_url(membership.workspace_id, peer.id), {"role": "agent"}
    )

    assert response.status_code == 403


def test_an_admin_cannot_touch_the_owner(csrf_client: CsrfClient) -> None:
    admin = UserFactory.create(email="admin@example.com")
    membership = MembershipFactory.create(user=admin, role=MembershipRole.ADMIN)
    owner = MembershipFactory.create(workspace=membership.workspace, role=MembershipRole.OWNER)
    sign_in(csrf_client, admin.email)

    response = csrf_client.patch_json(
        member_url(membership.workspace_id, owner.id), {"role": "agent"}
    )

    assert response.status_code == 403


def test_an_owner_can_promote_to_admin(csrf_client: CsrfClient) -> None:
    owner = UserFactory.create(email="owner@example.com")
    membership = MembershipFactory.create(user=owner, role=MembershipRole.OWNER)
    target = MembershipFactory.create(workspace=membership.workspace, role=MembershipRole.MANAGER)
    sign_in(csrf_client, owner.email)

    response = csrf_client.patch_json(
        member_url(membership.workspace_id, target.id), {"role": "admin"}
    )

    assert response.status_code == 200
    target.refresh_from_db()
    assert target.role == MembershipRole.ADMIN


def test_the_last_owner_cannot_be_demoted(csrf_client: CsrfClient) -> None:
    owner = UserFactory.create(email="owner@example.com")
    membership = MembershipFactory.create(user=owner, role=MembershipRole.OWNER)
    sign_in(csrf_client, owner.email)

    response = csrf_client.patch_json(
        member_url(membership.workspace_id, membership.id), {"role": "agent"}
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"
    membership.refresh_from_db()
    assert membership.role == MembershipRole.OWNER


def test_an_owner_may_step_down_when_another_owner_exists(csrf_client: CsrfClient) -> None:
    owner = UserFactory.create(email="owner@example.com")
    membership = MembershipFactory.create(user=owner, role=MembershipRole.OWNER)
    MembershipFactory.create(workspace=membership.workspace, role=MembershipRole.OWNER)
    sign_in(csrf_client, owner.email)

    response = csrf_client.patch_json(
        member_url(membership.workspace_id, membership.id), {"role": "agent"}
    )

    assert response.status_code == 200
    membership.refresh_from_db()
    assert membership.role == MembershipRole.AGENT


def test_an_archived_workspace_is_not_addressable(csrf_client: CsrfClient) -> None:
    user = UserFactory.create(email="agent@example.com")
    membership = MembershipFactory.create(
        user=user,
        workspace=WorkspaceFactory.create(status=WorkspaceStatus.ARCHIVED),
    )
    sign_in(csrf_client, user.email)

    response = csrf_client.get(members_url(membership.workspace_id))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_an_archived_workspace_refuses_member_changes(csrf_client: CsrfClient) -> None:
    owner = UserFactory.create(email="owner@example.com")
    membership = MembershipFactory.create(
        user=owner,
        role=MembershipRole.OWNER,
        workspace=WorkspaceFactory.create(status=WorkspaceStatus.ARCHIVED),
    )
    target = MembershipFactory.create(workspace=membership.workspace)
    sign_in(csrf_client, owner.email)

    response = csrf_client.patch_json(
        member_url(membership.workspace_id, target.id), {"role": "manager"}
    )

    assert response.status_code == 404
    target.refresh_from_db()
    assert target.role == MembershipRole.AGENT


def test_deactivating_an_account_ends_api_access(csrf_client: CsrfClient) -> None:
    user = UserFactory.create(email="agent@example.com")
    membership = MembershipFactory.create(user=user)
    sign_in(csrf_client, user.email)

    # Django's session authentication stops resolving an inactive user, so the
    # request is anonymous by the time permissions run: 401, not 404.
    user.is_active = False
    user.save(update_fields=["is_active"])

    response = csrf_client.get(members_url(membership.workspace_id))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_a_membership_from_another_workspace_is_not_addressable(csrf_client: CsrfClient) -> None:
    owner = UserFactory.create(email="owner@example.com")
    membership = MembershipFactory.create(user=owner, role=MembershipRole.OWNER)
    foreign = MembershipFactory.create()
    sign_in(csrf_client, owner.email)

    response = csrf_client.patch_json(
        member_url(membership.workspace_id, foreign.id), {"role": "manager"}
    )

    assert response.status_code == 404
    foreign.refresh_from_db()
    assert foreign.role == MembershipRole.AGENT


def test_an_unknown_membership_is_not_found(csrf_client: CsrfClient) -> None:
    owner = UserFactory.create(email="owner@example.com")
    membership = MembershipFactory.create(user=owner, role=MembershipRole.OWNER)
    sign_in(csrf_client, owner.email)

    response = csrf_client.patch_json(
        member_url(membership.workspace_id, uuid.uuid4()), {"role": "manager"}
    )

    assert response.status_code == 404


def test_an_empty_update_is_rejected(csrf_client: CsrfClient) -> None:
    owner = UserFactory.create(email="owner@example.com")
    membership = MembershipFactory.create(user=owner, role=MembershipRole.OWNER)
    sign_in(csrf_client, owner.email)

    response = csrf_client.patch_json(member_url(membership.workspace_id, membership.id), {})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


def test_an_unknown_role_is_rejected(csrf_client: CsrfClient) -> None:
    owner = UserFactory.create(email="owner@example.com")
    membership = MembershipFactory.create(user=owner, role=MembershipRole.OWNER)
    sign_in(csrf_client, owner.email)

    response = csrf_client.patch_json(
        member_url(membership.workspace_id, membership.id), {"role": "superuser"}
    )

    assert response.status_code == 400
    assert "role" in response.json()["error"]["details"]


def test_revoking_access_removes_the_member(csrf_client: CsrfClient) -> None:
    owner = UserFactory.create(email="owner@example.com")
    membership = MembershipFactory.create(user=owner, role=MembershipRole.OWNER)
    agent = UserFactory.create(email="agent@example.com")
    target = MembershipFactory.create(workspace=membership.workspace, user=agent)
    sign_in(csrf_client, owner.email)

    response = csrf_client.patch_json(
        member_url(membership.workspace_id, target.id), {"status": "removed"}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "removed"
    # The row is kept for audit; only access is withdrawn.
    assert Membership.objects.filter(pk=target.pk).exists()

    assert (
        sign_in(csrf_client, agent.email).get(members_url(membership.workspace_id)).status_code
        == 404
    )


def test_a_role_change_without_a_csrf_token_is_rejected(csrf_client: CsrfClient) -> None:
    owner = UserFactory.create(email="owner@example.com")
    membership = MembershipFactory.create(user=owner, role=MembershipRole.OWNER)
    target = MembershipFactory.create(workspace=membership.workspace)
    sign_in(csrf_client, owner.email)

    response = csrf_client.patch(
        member_url(membership.workspace_id, target.id),
        data={"role": "manager"},
        content_type="application/json",
    )

    assert response.status_code == 403
    target.refresh_from_db()
    assert target.role == MembershipRole.AGENT


def test_update_requires_authentication(client: Client) -> None:
    membership = MembershipFactory.create(role=MembershipRole.OWNER)

    response = client.patch(
        member_url(membership.workspace_id, membership.id),
        data={"role": "agent"},
        content_type="application/json",
    )

    assert response.status_code == 401
