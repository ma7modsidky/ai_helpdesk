from __future__ import annotations

import pytest
from django.test import Client

from apps.accounts.models import User
from apps.accounts.tests.factories import DEFAULT_PASSWORD
from apps.organizations.models import Membership, MembershipRole, MembershipStatus, WorkspaceStatus
from apps.organizations.tests.factories import (
    MembershipFactory,
    WorkspaceFactory,
)
from tests.support import CsrfClient, login

pytestmark = pytest.mark.django_db

WORKSPACES = "/api/v1/workspaces/"


def test_list_requires_authentication(client: Client) -> None:
    response = client.get(WORKSPACES)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_list_returns_only_the_callers_workspaces(
    csrf_client: CsrfClient, agent_user: User
) -> None:
    own = MembershipFactory.create(user=agent_user)
    foreign = MembershipFactory.create()
    login(csrf_client, email=agent_user.email, password=DEFAULT_PASSWORD)

    response = csrf_client.get(WORKSPACES)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"count", "next", "previous", "results"}
    assert [row["id"] for row in body["results"]] == [str(own.workspace_id)]
    assert str(foreign.workspace_id) not in [row["id"] for row in body["results"]]


def test_list_skips_removed_memberships_and_archived_workspaces(
    csrf_client: CsrfClient, agent_user: User
) -> None:
    active = MembershipFactory.create(user=agent_user)
    MembershipFactory.create(user=agent_user, status=MembershipStatus.REMOVED)
    MembershipFactory.create(
        user=agent_user,
        workspace=WorkspaceFactory.create(status=WorkspaceStatus.ARCHIVED),
    )
    login(csrf_client, email=agent_user.email, password=DEFAULT_PASSWORD)

    response = csrf_client.get(WORKSPACES)

    assert [row["id"] for row in response.json()["results"]] == [str(active.workspace_id)]


def test_create_makes_the_caller_the_owner(csrf_client: CsrfClient, agent_user: User) -> None:
    login(csrf_client, email=agent_user.email, password=DEFAULT_PASSWORD)

    response = csrf_client.post_json(WORKSPACES, {"name": "Acme Support", "slug": "acme-support"})

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Acme Support"
    assert body["slug"] == "acme-support"
    assert body["timezone"] == "UTC"
    membership = Membership.objects.get(workspace_id=body["id"], user=agent_user)
    assert membership.role == MembershipRole.OWNER
    assert membership.status == MembershipStatus.ACTIVE


def test_created_workspace_appears_in_the_list(csrf_client: CsrfClient, agent_user: User) -> None:
    login(csrf_client, email=agent_user.email, password=DEFAULT_PASSWORD)
    created = csrf_client.post_json(WORKSPACES, {"name": "Acme", "slug": "acme"}).json()

    listed = csrf_client.get(WORKSPACES).json()["results"]

    assert [row["id"] for row in listed] == [created["id"]]


def test_create_rejects_a_duplicate_slug(csrf_client: CsrfClient, agent_user: User) -> None:
    WorkspaceFactory.create(slug="taken")
    login(csrf_client, email=agent_user.email, password=DEFAULT_PASSWORD)

    response = csrf_client.post_json(WORKSPACES, {"name": "Acme", "slug": "taken"})

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert "slug" in error["details"]


def test_create_rejects_an_unknown_time_zone(csrf_client: CsrfClient, agent_user: User) -> None:
    login(csrf_client, email=agent_user.email, password=DEFAULT_PASSWORD)

    response = csrf_client.post_json(
        WORKSPACES, {"name": "Acme", "slug": "acme", "timezone": "Mars/Olympus"}
    )

    assert response.status_code == 400
    assert "timezone" in response.json()["error"]["details"]


def test_create_rejects_a_malformed_slug(csrf_client: CsrfClient, agent_user: User) -> None:
    login(csrf_client, email=agent_user.email, password=DEFAULT_PASSWORD)

    response = csrf_client.post_json(WORKSPACES, {"name": "Acme", "slug": "Acme Support!"})

    assert response.status_code == 400
    assert "slug" in response.json()["error"]["details"]


def test_create_requires_authentication(client: Client) -> None:
    response = client.post(
        WORKSPACES,
        data={"name": "Acme", "slug": "acme"},
        content_type="application/json",
    )

    assert response.status_code == 401
