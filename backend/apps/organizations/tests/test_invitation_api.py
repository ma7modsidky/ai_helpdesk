"""Workspace-side invitation tests: issuing, listing, resending, revoking.

These assert the two properties the contract leans on: a pending invitation is
not a member, and the token is visible exactly once, in the response to the call
that creates or rotates it.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import TYPE_CHECKING, Any, cast

import pytest
from django.conf import settings
from django.core import mail
from django.test import Client
from django.utils import timezone
from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.accounts.tests.factories import DEFAULT_PASSWORD, UserFactory
from apps.organizations.exceptions import InvitationRoleNotAllowed
from apps.organizations.invitations import create_invitation
from apps.organizations.models import (
    Invitation,
    InvitationStatus,
    Membership,
    MembershipRole,
    Workspace,
    WorkspaceStatus,
)
from apps.organizations.tests.factories import (
    InvitationFactory,
    MembershipFactory,
    WorkspaceFactory,
)
from apps.organizations.views import _raise_invitation_error
from tests.support import CsrfClient, login

if TYPE_CHECKING:
    from django.test.client import _MonkeyPatchedWSGIResponse

pytestmark = pytest.mark.django_db

API = "/api/v1"
PREVIEW = f"{API}/invitations/preview/"


def invitations_url(workspace_id: uuid.UUID) -> str:
    return f"{API}/workspaces/{workspace_id}/invitations/"


def invitation_url(workspace_id: uuid.UUID, invitation_id: uuid.UUID) -> str:
    return f"{invitations_url(workspace_id)}{invitation_id}/"


def resend_url(workspace_id: uuid.UUID, invitation_id: uuid.UUID) -> str:
    return f"{invitation_url(workspace_id, invitation_id)}resend/"


def sign_in_as(client: CsrfClient, email: str) -> None:
    login(client, email=email, password=DEFAULT_PASSWORD)


def invite(
    client: CsrfClient,
    workspace_id: uuid.UUID,
    *,
    email: str = "invitee@example.com",
    role: str = "agent",
) -> _MonkeyPatchedWSGIResponse:
    return client.post_json(invitations_url(workspace_id), {"email": email, "role": role})


def preview_token(client: Client, token: str) -> _MonkeyPatchedWSGIResponse:
    return client.post(PREVIEW, data={"token": token}, content_type="application/json")


def post_action(client: CsrfClient, url: str) -> _MonkeyPatchedWSGIResponse:
    """POST with an empty JSON body, as the contract requires, plus CSRF."""
    return client.post(
        url,
        data={},
        content_type="application/json",
        headers={"X-CSRFToken": client.csrf_token},
    )


def delete_action(client: CsrfClient, url: str) -> _MonkeyPatchedWSGIResponse:
    return client.delete(url, headers={"X-CSRFToken": client.csrf_token})


def sent_messages() -> list[Any]:
    return cast("list[Any]", getattr(mail, "outbox", []))


def token_from(accept_path: str) -> str:
    return accept_path.rsplit("/", 1)[-1]


@pytest.fixture
def owner_client(csrf_client: CsrfClient) -> tuple[CsrfClient, Workspace]:
    owner = UserFactory.create(email="owner@example.com")
    membership = MembershipFactory.create(user=owner, role=MembershipRole.OWNER)
    sign_in_as(csrf_client, owner.email)
    return csrf_client, membership.workspace


def test_creating_an_invitation_returns_the_accept_path_once(
    owner_client: tuple[CsrfClient, Workspace],
) -> None:
    client, workspace = owner_client

    response = invite(client, workspace.id, email=" Invitee@Example.com ", role="manager")

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "invitee@example.com"
    assert body["role"] == "manager"
    assert body["status"] == "pending"
    assert body["delivery_status"] == "sent"
    assert body["accept_path"].startswith("/invite/")
    assert "token_hash" not in body
    assert len(sent_messages()) == 1
    assert body["accept_path"] in sent_messages()[0].body

    # The invitation is not a membership.
    assert Membership.objects.filter(workspace=workspace).count() == 1


def test_the_created_token_works_for_preview(
    owner_client: tuple[CsrfClient, Workspace],
) -> None:
    client, workspace = owner_client
    accept_path = invite(client, workspace.id).json()["accept_path"]

    response = preview_token(client, token_from(accept_path))

    assert response.status_code == 200
    assert response.json()["status"] == "pending"


def test_listing_never_exposes_the_token(
    owner_client: tuple[CsrfClient, Workspace],
) -> None:
    client, workspace = owner_client
    invite(client, workspace.id)

    response = client.get(invitations_url(workspace.id))

    assert response.status_code == 200
    row = response.json()["results"][0]
    assert set(row) == {
        "id",
        "email",
        "role",
        "status",
        "expires_at",
        "created_at",
        "invited_by",
        "delivery_status",
    }
    assert row["invited_by"]["email"] == "owner@example.com"
    assert "token" not in str(row)


def test_listing_filters_by_status(owner_client: tuple[CsrfClient, Workspace]) -> None:
    client, workspace = owner_client
    invite(client, workspace.id, email="pending@example.com")
    accepted = InvitationFactory.create(
        workspace=workspace,
        email="accepted@example.com",
        status=InvitationStatus.ACCEPTED,
    )

    pending = client.get(f"{invitations_url(workspace.id)}?status=pending").json()["results"]
    every = client.get(f"{invitations_url(workspace.id)}?status=all").json()["results"]
    wrong = client.get(f"{invitations_url(workspace.id)}?status=expired")

    assert [row["email"] for row in pending] == ["pending@example.com"]
    assert len(every) == 2
    assert len([row for row in every if row["id"] == str(accepted.id)]) == 1
    assert wrong.status_code == 400


def test_agents_and_managers_cannot_manage_invitations(csrf_client: CsrfClient) -> None:
    for role in (MembershipRole.AGENT, MembershipRole.MANAGER):
        user = UserFactory.create(email=f"{role.value}@example.com")
        membership = MembershipFactory.create(user=user, role=role)
        sign_in_as(csrf_client, user.email)

        create = invite(csrf_client, membership.workspace_id)
        listing = csrf_client.get(invitations_url(membership.workspace_id))

        assert create.status_code == 403
        assert listing.status_code == 403


def test_a_non_member_gets_404(csrf_client: CsrfClient) -> None:
    workspace = WorkspaceFactory.create()
    outsider = UserFactory.create(email="outsider@example.com")
    sign_in_as(csrf_client, outsider.email)

    assert invite(csrf_client, workspace.id).status_code == 404
    assert csrf_client.get(invitations_url(workspace.id)).status_code == 404


def test_creating_requires_authentication(client: Client) -> None:
    workspace = WorkspaceFactory.create()

    response = client.post(
        invitations_url(workspace.id),
        data={"email": "invitee@example.com", "role": "agent"},
        content_type="application/json",
    )

    assert response.status_code == 401


def test_an_archived_workspace_is_not_addressable(csrf_client: CsrfClient) -> None:
    owner = UserFactory.create(email="owner@example.com")
    membership = MembershipFactory.create(
        user=owner,
        role=MembershipRole.OWNER,
        workspace=WorkspaceFactory.create(status=WorkspaceStatus.ARCHIVED),
    )
    sign_in_as(csrf_client, owner.email)

    response = invite(csrf_client, membership.workspace_id)

    assert response.status_code == 404


def test_a_second_invitation_for_the_same_address_conflicts(
    owner_client: tuple[CsrfClient, Workspace],
) -> None:
    client, workspace = owner_client
    invite(client, workspace.id)

    response = invite(client, workspace.id)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_an_existing_member_cannot_be_invited(
    owner_client: tuple[CsrfClient, Workspace],
) -> None:
    client, workspace = owner_client
    member = UserFactory.create(email="member@example.com")
    MembershipFactory.create(workspace=workspace, user=member)

    response = invite(client, workspace.id, email="member@example.com")

    assert response.status_code == 400
    assert "email" in response.json()["error"]["details"]


def test_the_owner_role_cannot_be_invited(
    owner_client: tuple[CsrfClient, Workspace],
) -> None:
    client, workspace = owner_client

    response = invite(client, workspace.id, role="owner")

    assert response.status_code == 400
    assert "role" in response.json()["error"]["details"]
    assert Invitation.objects.count() == 0


def test_the_service_refuses_an_owner_or_unknown_role_directly() -> None:
    owner = UserFactory.create(email="owner@example.com")
    membership = MembershipFactory.create(user=owner, role=MembershipRole.OWNER)

    for role in ("owner", "superuser"):
        with pytest.raises(InvitationRoleNotAllowed):
            create_invitation(
                workspace=membership.workspace,
                inviter=owner,
                email="invitee@example.com",
                role=role,
            )


def test_the_view_maps_a_service_role_refusal_to_a_field_error() -> None:
    # The serializer rejects `owner` first, so this keeps the defence-in-depth
    # branch in the service covered through the view's mapping.
    with pytest.raises(DRFValidationError) as error:
        _raise_invitation_error(InvitationRoleNotAllowed())

    assert "role" in error.value.detail


def test_a_malformed_address_is_rejected(
    owner_client: tuple[CsrfClient, Workspace],
) -> None:
    client, workspace = owner_client

    response = invite(client, workspace.id, email="not-an-email")

    assert response.status_code == 400
    assert "email" in response.json()["error"]["details"]


def test_resend_rotates_the_token_and_extends_expiry(
    owner_client: tuple[CsrfClient, Workspace],
) -> None:
    client, workspace = owner_client
    created = invite(client, workspace.id).json()
    invitation_id = created["id"]
    old_token = token_from(created["accept_path"])
    before = Invitation.objects.get(pk=invitation_id).expires_at

    response = post_action(client, resend_url(workspace.id, invitation_id))

    assert response.status_code == 200
    new_path = response.json()["accept_path"]
    assert new_path != created["accept_path"]
    assert preview_token(client, old_token).status_code == 404
    assert preview_token(client, token_from(new_path)).status_code == 200

    invitation = Invitation.objects.get(pk=invitation_id)
    assert invitation.expires_at > before


def test_resending_an_accepted_invitation_conflicts(
    owner_client: tuple[CsrfClient, Workspace],
) -> None:
    client, workspace = owner_client
    created = invite(client, workspace.id).json()
    Invitation.objects.filter(pk=created["id"]).update(status=InvitationStatus.ACCEPTED)

    response = post_action(client, resend_url(workspace.id, created["id"]))

    assert response.status_code == 409


def test_resend_without_an_inviter_uses_a_generic_sender(
    owner_client: tuple[CsrfClient, Workspace],
) -> None:
    client, workspace = owner_client
    invitation = InvitationFactory.create(
        workspace=workspace,
        email="orphan@example.com",
        invited_by=None,
    )

    response = post_action(client, resend_url(workspace.id, invitation.id))

    assert response.status_code == 200
    assert "An administrator" in sent_messages()[0].body


def test_revoking_invalidates_the_token_immediately(
    owner_client: tuple[CsrfClient, Workspace],
) -> None:
    client, workspace = owner_client
    created = invite(client, workspace.id).json()
    token = token_from(created["accept_path"])

    response = delete_action(client, invitation_url(workspace.id, created["id"]))

    assert response.status_code == 204
    # The token is dead for acceptance, but the preview can still explain why.
    revoked = preview_token(client, token)
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    # Repeating the command is safe.
    assert delete_action(client, invitation_url(workspace.id, created["id"])).status_code == 204


def test_an_accepted_invitation_cannot_be_revoked(
    owner_client: tuple[CsrfClient, Workspace],
) -> None:
    client, workspace = owner_client
    invitation = InvitationFactory.create(
        workspace=workspace,
        status=InvitationStatus.ACCEPTED,
    )

    response = delete_action(client, invitation_url(workspace.id, invitation.id))

    assert response.status_code == 409


def test_an_invitation_from_another_workspace_is_not_addressable(
    owner_client: tuple[CsrfClient, Workspace],
) -> None:
    client, workspace = owner_client
    foreign = InvitationFactory.create()

    assert delete_action(client, invitation_url(workspace.id, foreign.id)).status_code == 404
    assert post_action(client, resend_url(workspace.id, foreign.id)).status_code == 404
    foreign.refresh_from_db()
    assert foreign.status == InvitationStatus.PENDING


def test_an_expired_invitation_can_still_be_resent(
    owner_client: tuple[CsrfClient, Workspace],
) -> None:
    client, workspace = owner_client
    invitation = InvitationFactory.create(
        workspace=workspace,
        expires_at=timezone.now() - timedelta(days=1),
    )

    response = post_action(client, resend_url(workspace.id, invitation.id))

    assert response.status_code == 200
    assert response.json()["status"] == "pending"


def test_a_delivery_failure_is_recorded_without_losing_the_invitation(
    owner_client: tuple[CsrfClient, Workspace], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, workspace = owner_client

    def boom(*args: object, **kwargs: object) -> None:
        raise OSError("provider down")

    monkeypatch.setattr("apps.organizations.invitations.send_mail", boom)

    response = invite(client, workspace.id, email="unreachable@example.com")

    assert response.status_code == 201
    assert response.json()["delivery_status"] == "failed"
    invitation = Invitation.objects.get(workspace=workspace)
    assert invitation.delivery_status == "failed"
    assert invitation.last_sent_at is not None


def test_creating_invitations_is_rate_limited(
    owner_client: tuple[CsrfClient, Workspace],
) -> None:
    client, workspace = owner_client
    throttle_rates = cast("dict[str, str]", settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"])
    limit = int(throttle_rates["invitation_create"].split("/")[0])

    for _ in range(limit):
        # Duplicates still consume the budget; only the outcome differs.
        assert invite(client, workspace.id).status_code in {201, 409}

    response = invite(client, workspace.id)

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "throttled"
