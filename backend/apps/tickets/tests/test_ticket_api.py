from __future__ import annotations

import uuid
from typing import Any
from uuid import UUID

import pytest
from django.test import Client
from rest_framework.throttling import ScopedRateThrottle

from apps.accounts.models import User
from apps.accounts.tests.factories import DEFAULT_PASSWORD, UserFactory
from apps.organizations.models import MembershipRole, WorkspaceStatus
from apps.organizations.tests.factories import MembershipFactory, WorkspaceFactory
from apps.tickets.models import (
    MessageVisibility,
    Ticket,
    TicketEventType,
    TicketStatus,
)
from apps.tickets.services import events_for
from apps.tickets.tests.factories import TicketFactory
from tests.support import CsrfClient, login

pytestmark = pytest.mark.django_db

API = "/api/v1"


def tickets_url(workspace_id: UUID) -> str:
    return f"{API}/workspaces/{workspace_id}/tickets/"


def ticket_url(workspace_id: UUID, ticket_id: UUID) -> str:
    return f"{tickets_url(workspace_id)}{ticket_id}/"


def assign_url(workspace_id: UUID, ticket_id: UUID) -> str:
    return f"{ticket_url(workspace_id, ticket_id)}assign/"


def transition_url(workspace_id: UUID, ticket_id: UUID) -> str:
    return f"{ticket_url(workspace_id, ticket_id)}transition/"


def messages_url(workspace_id: UUID, ticket_id: UUID) -> str:
    return f"{ticket_url(workspace_id, ticket_id)}messages/"


def sign_in(client: CsrfClient, user: User) -> CsrfClient:
    return login(client, email=user.email, password=DEFAULT_PASSWORD)


def make_user(email: str) -> User:
    return UserFactory.create(email=email)


@pytest.fixture
def workspace() -> Any:
    return WorkspaceFactory.create()


@pytest.fixture
def owner(workspace: Any) -> User:
    user = make_user("owner@example.com")
    MembershipFactory.create(workspace=workspace, user=user, role=MembershipRole.OWNER)
    return user


@pytest.fixture
def agent(workspace: Any) -> User:
    user = make_user("agent@example.com")
    MembershipFactory.create(workspace=workspace, user=user, role=MembershipRole.AGENT)
    return user


def create_ticket(client: CsrfClient, workspace_id: UUID, **overrides: Any) -> Any:
    payload: dict[str, Any] = {
        "subject": "Cannot sign in",
        "description": "I keep getting an error.",
        "requester_email": "Customer@Example.COM",
    }
    payload.update(overrides)
    return client.post_json(tickets_url(workspace_id), payload)


def patch_ticket(
    client: CsrfClient,
    workspace_id: UUID,
    ticket_id: UUID,
    payload: dict[str, Any],
    *,
    if_match: str | None = "current",
    version: int | None = None,
) -> Any:
    headers = {"X-CSRFToken": client.csrf_token}
    if if_match is not None:
        headers["If-Match"] = f'"{version}"' if if_match == "current" else if_match
    return client.patch(
        ticket_url(workspace_id, ticket_id),
        data=payload,
        content_type="application/json",
        headers=headers,
    )


# --- Access -----------------------------------------------------------------


def test_listing_requires_authentication(client: Client) -> None:
    workspace = WorkspaceFactory.create()

    assert client.get(tickets_url(workspace.id)).status_code == 401


def test_a_non_member_cannot_list_tickets(csrf_client: CsrfClient) -> None:
    workspace = WorkspaceFactory.create()
    sign_in(csrf_client, make_user("stranger@example.com"))

    response = csrf_client.get(tickets_url(workspace.id))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_an_archived_workspace_is_not_addressable(csrf_client: CsrfClient) -> None:
    user = make_user("agent@example.com")
    membership = MembershipFactory.create(
        user=user,
        workspace=WorkspaceFactory.create(status=WorkspaceStatus.ARCHIVED),
    )
    sign_in(csrf_client, user)

    assert csrf_client.get(tickets_url(membership.workspace_id)).status_code == 404


def test_a_ticket_from_another_workspace_is_not_found(
    csrf_client: CsrfClient, workspace: Any, owner: User
) -> None:
    sign_in(csrf_client, owner)
    foreign = TicketFactory.create()

    response = csrf_client.get(ticket_url(workspace.id, foreign.pk))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


# --- Creation ---------------------------------------------------------------


def test_creation_returns_an_open_unassigned_ticket(
    csrf_client: CsrfClient, workspace: Any, owner: User
) -> None:
    sign_in(csrf_client, owner)

    response = create_ticket(csrf_client, workspace.id)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "open"
    assert body["priority"] == "normal"
    assert body["assignee_id"] is None
    assert body["version"] == 1
    assert body["requester_email"] == "customer@example.com"
    assert set(body) == {
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
    }


def test_an_agent_can_create_a_ticket(csrf_client: CsrfClient, workspace: Any, agent: User) -> None:
    sign_in(csrf_client, agent)

    response = create_ticket(csrf_client, workspace.id, priority="high")

    assert response.status_code == 201
    assert response.json()["priority"] == "high"


def test_the_requester_may_be_an_active_member(
    csrf_client: CsrfClient, workspace: Any, owner: User, agent: User
) -> None:
    sign_in(csrf_client, owner)

    response = create_ticket(csrf_client, workspace.id, requester_user_id=str(agent.pk))

    assert response.status_code == 201
    assert response.json()["requester_user_id"] == str(agent.pk)


def test_a_foreign_requester_is_refused_without_revealing_whether_the_account_exists(
    csrf_client: CsrfClient, workspace: Any, owner: User
) -> None:
    stranger = make_user("stranger@example.com")
    MembershipFactory.create(user=stranger)
    sign_in(csrf_client, owner)

    foreign = create_ticket(csrf_client, workspace.id, requester_user_id=str(stranger.pk))
    unknown = create_ticket(csrf_client, workspace.id, requester_user_id=str(uuid.uuid4()))

    assert foreign.status_code == unknown.status_code == 400
    assert (
        foreign.json()["error"]["details"]["requester_user_id"]
        == unknown.json()["error"]["details"]["requester_user_id"]
    )


def test_status_and_assignee_are_not_accepted_at_creation(
    csrf_client: CsrfClient, workspace: Any, owner: User
) -> None:
    sign_in(csrf_client, owner)

    response = create_ticket(csrf_client, workspace.id, status="resolved")

    assert response.status_code == 400
    assert "status" in response.json()["error"]["details"]


def test_creation_requires_a_csrf_token(
    csrf_client: CsrfClient, workspace: Any, owner: User
) -> None:
    sign_in(csrf_client, owner)

    response = csrf_client.post(
        tickets_url(workspace.id),
        data={"subject": "No token", "description": "x", "requester_email": "a@example.com"},
        content_type="application/json",
    )

    assert response.status_code == 403
    assert Ticket.objects.filter(workspace_id=workspace.id).count() == 0


def test_creation_records_an_audit_event_with_the_request_id(
    csrf_client: CsrfClient, workspace: Any, owner: User
) -> None:
    sign_in(csrf_client, owner)

    response = create_ticket(csrf_client, workspace.id)

    ticket = Ticket.objects.get(pk=response.json()["id"])
    event = events_for(ticket).get()
    assert event.event_type == TicketEventType.CREATED
    assert event.actor_id == owner.pk
    assert event.correlation_id == response.headers["X-Request-ID"]


def test_creation_is_throttled(
    csrf_client: CsrfClient,
    workspace: Any,
    owner: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # DRF reads its rates from a class attribute captured at import time, so a
    # settings override would not reach it. Lowering the rate directly keeps the
    # test at four requests instead of one hundred and twenty-one.
    monkeypatch.setattr(
        ScopedRateThrottle,
        "THROTTLE_RATES",
        {**ScopedRateThrottle.THROTTLE_RATES, "ticket_create": "3/hour"},
    )
    sign_in(csrf_client, owner)

    for _ in range(3):
        assert create_ticket(csrf_client, workspace.id).status_code == 201

    response = create_ticket(csrf_client, workspace.id)

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "throttled"


def test_listing_is_not_throttled(
    csrf_client: CsrfClient,
    workspace: Any,
    owner: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ScopedRateThrottle,
        "THROTTLE_RATES",
        {**ScopedRateThrottle.THROTTLE_RATES, "ticket_create": "1/hour"},
    )
    sign_in(csrf_client, owner)

    for _ in range(3):
        assert csrf_client.get(tickets_url(workspace.id)).status_code == 200


# --- Listing ----------------------------------------------------------------


def test_listing_returns_the_paginated_envelope(
    csrf_client: CsrfClient, workspace: Any, owner: User
) -> None:
    sign_in(csrf_client, owner)
    TicketFactory.create(workspace=workspace)

    response = csrf_client.get(tickets_url(workspace.id))

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"count", "next", "previous", "results"}
    assert body["count"] == 1


def test_filters_combine_and_search_matches_the_subject(
    csrf_client: CsrfClient, workspace: Any, owner: User
) -> None:
    sign_in(csrf_client, owner)
    match = TicketFactory.create(workspace=workspace, priority="high", subject="Duplicate CHARGE")
    TicketFactory.create(workspace=workspace, priority="low", subject="Duplicate charge")
    TicketFactory.create(workspace=workspace, priority="high", subject="Cannot sign in")

    response = csrf_client.get(
        tickets_url(workspace.id),
        {"priority": "high", "search": "duplicate char"},
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert [row["id"] for row in results] == [str(match.pk)]


def test_the_assignee_filter_accepts_me_unassigned_and_a_user_id(
    csrf_client: CsrfClient, workspace: Any, owner: User
) -> None:
    sign_in(csrf_client, owner)
    mine = TicketFactory.create(workspace=workspace, assignee=owner)
    TicketFactory.create(workspace=workspace)

    me = csrf_client.get(tickets_url(workspace.id), {"assignee": "me"})
    unassigned = csrf_client.get(tickets_url(workspace.id), {"assignee": "unassigned"})

    assert [row["id"] for row in me.json()["results"]] == [str(mine.pk)]
    assert unassigned.json()["count"] == 1
    assert unassigned.json()["results"][0]["assignee_id"] is None


def test_a_well_formed_foreign_assignee_matches_nothing(
    csrf_client: CsrfClient, workspace: Any, owner: User
) -> None:
    sign_in(csrf_client, owner)
    TicketFactory.create(workspace=workspace)

    response = csrf_client.get(tickets_url(workspace.id), {"assignee": str(uuid.uuid4())})

    assert response.status_code == 200
    assert response.json()["results"] == []


@pytest.mark.parametrize(
    "params",
    [
        {"status": "archived"},
        {"priority": "critical"},
        {"ordering": "description"},
        {"ordering": "-"},
        {"assignee": "everyone"},
        {"search": "x" * 101},
        {"search": "  "},
    ],
)
def test_invalid_query_values_are_rejected(
    csrf_client: CsrfClient, workspace: Any, owner: User, params: dict[str, str]
) -> None:
    sign_in(csrf_client, owner)

    response = csrf_client.get(tickets_url(workspace.id), params)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"
    assert set(response.json()["error"]["details"]) & set(params)


def test_pagination_is_stable_across_ties(
    csrf_client: CsrfClient, workspace: Any, owner: User
) -> None:
    sign_in(csrf_client, owner)
    for index in range(3):
        TicketFactory.create(workspace=workspace, subject=f"Ticket {index}")

    pages = [
        csrf_client.get(tickets_url(workspace.id), {"page_size": 1, "page": page})
        for page in (1, 2, 3)
    ]
    ids = [page.json()["results"][0]["id"] for page in pages]

    assert len(set(ids)) == 3
    assert ids == [
        row["id"] for row in csrf_client.get(tickets_url(workspace.id)).json()["results"]
    ]


# --- Detail and field edits -------------------------------------------------


def test_detail_returns_one_ticket(csrf_client: CsrfClient, workspace: Any, owner: User) -> None:
    sign_in(csrf_client, owner)
    ticket = TicketFactory.create(workspace=workspace, subject="Printer offline")

    response = csrf_client.get(ticket_url(workspace.id, ticket.pk))

    assert response.status_code == 200
    assert response.json()["subject"] == "Printer offline"


def test_a_field_edit_with_the_current_version_succeeds(
    csrf_client: CsrfClient, workspace: Any, owner: User
) -> None:
    sign_in(csrf_client, owner)
    ticket = TicketFactory.create(workspace=workspace)

    response = patch_ticket(
        csrf_client,
        workspace.id,
        ticket.pk,
        {"subject": "Refund requested", "requester_email": "Other@Example.COM"},
        version=ticket.version,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["subject"] == "Refund requested"
    assert body["requester_email"] == "other@example.com"
    assert body["version"] == 2


@pytest.mark.parametrize("header", ["1", 'W/"1"'])
def test_if_match_accepts_the_unquoted_and_weak_forms(
    csrf_client: CsrfClient, workspace: Any, owner: User, header: str
) -> None:
    sign_in(csrf_client, owner)
    ticket = TicketFactory.create(workspace=workspace)

    response = patch_ticket(
        csrf_client, workspace.id, ticket.pk, {"subject": "Edited"}, if_match=header
    )

    assert response.status_code == 200
    assert response.json()["version"] == 2


def test_a_missing_if_match_is_a_conflict_reporting_the_current_version(
    csrf_client: CsrfClient, workspace: Any, owner: User
) -> None:
    sign_in(csrf_client, owner)
    ticket = TicketFactory.create(workspace=workspace)

    response = patch_ticket(
        csrf_client, workspace.id, ticket.pk, {"subject": "Nope"}, if_match=None
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"
    assert response.json()["error"]["details"]["version"] == ticket.version


def test_a_malformed_if_match_is_a_conflict(
    csrf_client: CsrfClient, workspace: Any, owner: User
) -> None:
    sign_in(csrf_client, owner)
    ticket = TicketFactory.create(workspace=workspace)

    response = patch_ticket(
        csrf_client, workspace.id, ticket.pk, {"subject": "Nope"}, if_match="not-a-version"
    )

    assert response.status_code == 409
    assert response.json()["error"]["details"]["version"] == ticket.version


def test_a_stale_if_match_is_a_conflict_reporting_the_current_version(
    csrf_client: CsrfClient, workspace: Any, owner: User
) -> None:
    sign_in(csrf_client, owner)
    ticket = TicketFactory.create(workspace=workspace, version=4)

    response = patch_ticket(csrf_client, workspace.id, ticket.pk, {"subject": "Nope"}, version=3)

    assert response.status_code == 409
    assert response.json()["error"]["details"]["version"] == 4


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "resolved"},
        {"assignee_id": None},
        {"requester_user_id": None},
        {"version": 2},
        {"subject": "ok", "unknown": "value"},
        {},
    ],
)
def test_a_field_edit_rejects_what_it_does_not_own(
    csrf_client: CsrfClient, workspace: Any, owner: User, payload: dict[str, Any]
) -> None:
    sign_in(csrf_client, owner)
    ticket = TicketFactory.create(workspace=workspace)

    response = patch_ticket(csrf_client, workspace.id, ticket.pk, payload, version=1)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


def test_a_field_edit_requires_csrf(csrf_client: CsrfClient, workspace: Any, owner: User) -> None:
    sign_in(csrf_client, owner)
    ticket = TicketFactory.create(workspace=workspace)

    response = csrf_client.patch(
        ticket_url(workspace.id, ticket.pk),
        data={"subject": "Nope"},
        content_type="application/json",
        headers={"If-Match": '"1"'},
    )

    assert response.status_code == 403
    ticket.refresh_from_db()
    assert ticket.subject != "Nope"


# --- Assignment -------------------------------------------------------------


def test_an_agent_may_claim_a_ticket(csrf_client: CsrfClient, workspace: Any, agent: User) -> None:
    sign_in(csrf_client, agent)
    ticket = TicketFactory.create(workspace=workspace)

    response = csrf_client.post_json(
        assign_url(workspace.id, ticket.pk), {"assignee_id": str(agent.pk)}
    )

    assert response.status_code == 200
    assert response.json()["assignee_id"] == str(agent.pk)
    assert response.json()["version"] == 2
    event = events_for(ticket).filter(event_type=TicketEventType.ASSIGNED).get()
    assert event.metadata["assignee_id"] == str(agent.pk)


def test_an_agent_cannot_assign_a_colleague(
    csrf_client: CsrfClient, workspace: Any, agent: User
) -> None:
    colleague = make_user("colleague@example.com")
    MembershipFactory.create(workspace=workspace, user=colleague)
    sign_in(csrf_client, agent)
    ticket = TicketFactory.create(workspace=workspace)

    response = csrf_client.post_json(
        assign_url(workspace.id, ticket.pk), {"assignee_id": str(colleague.pk)}
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"
    ticket.refresh_from_db()
    assert ticket.assignee_id is None


def test_a_manager_may_assign_a_colleague(csrf_client: CsrfClient, workspace: Any) -> None:
    manager = make_user("manager@example.com")
    MembershipFactory.create(workspace=workspace, user=manager, role=MembershipRole.MANAGER)
    colleague = make_user("colleague@example.com")
    MembershipFactory.create(workspace=workspace, user=colleague)
    sign_in(csrf_client, manager)
    ticket = TicketFactory.create(workspace=workspace)

    response = csrf_client.post_json(
        assign_url(workspace.id, ticket.pk), {"assignee_id": str(colleague.pk)}
    )

    assert response.status_code == 200
    assert response.json()["assignee_id"] == str(colleague.pk)


def test_unassigning_releases_the_ticket(
    csrf_client: CsrfClient, workspace: Any, agent: User
) -> None:
    sign_in(csrf_client, agent)
    ticket = TicketFactory.create(workspace=workspace, assignee=agent)

    response = csrf_client.post_json(assign_url(workspace.id, ticket.pk), {"assignee_id": None})

    assert response.status_code == 200
    assert response.json()["assignee_id"] is None


def test_assigning_an_inactive_member_is_a_field_error(
    csrf_client: CsrfClient, workspace: Any, owner: User
) -> None:
    target = make_user("gone@example.com")
    MembershipFactory.create(workspace=workspace, user=target, status="removed")
    sign_in(csrf_client, owner)
    ticket = TicketFactory.create(workspace=workspace)

    response = csrf_client.post_json(
        assign_url(workspace.id, ticket.pk), {"assignee_id": str(target.pk)}
    )

    assert response.status_code == 400
    assert "assignee_id" in response.json()["error"]["details"]


def test_assigning_a_ticket_from_another_workspace_is_not_found(
    csrf_client: CsrfClient, workspace: Any, owner: User
) -> None:
    sign_in(csrf_client, owner)
    foreign = TicketFactory.create()

    response = csrf_client.post_json(
        assign_url(workspace.id, foreign.pk), {"assignee_id": str(owner.pk)}
    )

    assert response.status_code == 404


# --- Transitions ------------------------------------------------------------


def test_an_agent_may_move_a_ticket_to_in_progress(
    csrf_client: CsrfClient, workspace: Any, agent: User
) -> None:
    sign_in(csrf_client, agent)
    ticket = TicketFactory.create(workspace=workspace)

    response = csrf_client.post_json(
        transition_url(workspace.id, ticket.pk), {"status": "in_progress"}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"
    assert response.json()["version"] == 2


def test_resolving_returns_the_resolution_time(
    csrf_client: CsrfClient, workspace: Any, agent: User
) -> None:
    sign_in(csrf_client, agent)
    ticket = TicketFactory.create(workspace=workspace)

    response = csrf_client.post_json(
        transition_url(workspace.id, ticket.pk), {"status": "resolved"}
    )

    assert response.status_code == 200
    assert response.json()["resolved_at"] is not None


def test_an_agent_cannot_reopen_a_resolved_ticket(
    csrf_client: CsrfClient, workspace: Any, agent: User
) -> None:
    sign_in(csrf_client, agent)
    ticket = TicketFactory.create(workspace=workspace, status=TicketStatus.RESOLVED)

    response = csrf_client.post_json(transition_url(workspace.id, ticket.pk), {"status": "open"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_a_manager_may_reopen_a_resolved_ticket(csrf_client: CsrfClient, workspace: Any) -> None:
    manager = make_user("manager@example.com")
    MembershipFactory.create(workspace=workspace, user=manager, role=MembershipRole.MANAGER)
    sign_in(csrf_client, manager)
    ticket = TicketFactory.create(workspace=workspace, status=TicketStatus.RESOLVED)

    response = csrf_client.post_json(transition_url(workspace.id, ticket.pk), {"status": "open"})

    assert response.status_code == 200
    assert response.json()["resolved_at"] is None


def test_a_closed_ticket_cannot_be_transitioned(
    csrf_client: CsrfClient, workspace: Any, owner: User
) -> None:
    sign_in(csrf_client, owner)
    ticket = TicketFactory.create(workspace=workspace, status=TicketStatus.CLOSED)

    response = csrf_client.post_json(transition_url(workspace.id, ticket.pk), {"status": "open"})

    assert response.status_code == 409


def test_an_unknown_status_is_a_field_error(
    csrf_client: CsrfClient, workspace: Any, owner: User
) -> None:
    sign_in(csrf_client, owner)
    ticket = TicketFactory.create(workspace=workspace)

    response = csrf_client.post_json(
        transition_url(workspace.id, ticket.pk), {"status": "reopened"}
    )

    assert response.status_code == 400
    assert "status" in response.json()["error"]["details"]


# --- Messages ---------------------------------------------------------------


def test_a_public_reply_is_appended_without_touching_the_version(
    csrf_client: CsrfClient, workspace: Any, agent: User
) -> None:
    sign_in(csrf_client, agent)
    ticket = TicketFactory.create(workspace=workspace)

    response = csrf_client.post_json(
        messages_url(workspace.id, ticket.pk),
        {"body": "We are looking into this."},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["visibility"] == "public_reply"
    assert body["author"] == {"user_id": str(agent.pk), "email": agent.email}
    ticket.refresh_from_db()
    assert ticket.version == 1


def test_an_internal_note_is_stored_with_its_visibility(
    csrf_client: CsrfClient, workspace: Any, agent: User
) -> None:
    sign_in(csrf_client, agent)
    ticket = TicketFactory.create(workspace=workspace)

    response = csrf_client.post_json(
        messages_url(workspace.id, ticket.pk),
        {"body": "Customer is on the enterprise plan.", "visibility": "internal_note"},
    )

    assert response.status_code == 201
    assert response.json()["visibility"] == "internal_note"
    listed = csrf_client.get(messages_url(workspace.id, ticket.pk)).json()["results"]
    assert [row["visibility"] for row in listed] == ["internal_note"]


def test_messages_are_listed_oldest_first(
    csrf_client: CsrfClient, workspace: Any, agent: User
) -> None:
    sign_in(csrf_client, agent)
    ticket = TicketFactory.create(workspace=workspace)
    for body in ("First", "Second"):
        csrf_client.post_json(messages_url(workspace.id, ticket.pk), {"body": body})

    listed = csrf_client.get(messages_url(workspace.id, ticket.pk)).json()["results"]

    assert [row["body"] for row in listed] == ["First", "Second"]


@pytest.mark.parametrize(
    "payload",
    [
        {"body": ""},
        {"body": "   "},
        {"body": "x" * 20001},
        {"body": "ok", "visibility": "whisper"},
        {},
    ],
)
def test_invalid_message_input_is_rejected(
    csrf_client: CsrfClient, workspace: Any, agent: User, payload: dict[str, Any]
) -> None:
    sign_in(csrf_client, agent)
    ticket = TicketFactory.create(workspace=workspace)

    response = csrf_client.post_json(messages_url(workspace.id, ticket.pk), payload)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


def test_messages_of_a_foreign_ticket_are_not_found(
    csrf_client: CsrfClient, workspace: Any, agent: User
) -> None:
    sign_in(csrf_client, agent)
    foreign = TicketFactory.create()

    assert csrf_client.get(messages_url(workspace.id, foreign.pk)).status_code == 404
    assert (
        csrf_client.post_json(messages_url(workspace.id, foreign.pk), {"body": "Hello"}).status_code
        == 404
    )


def test_posting_a_message_records_an_audit_event_with_identifiers_only(
    csrf_client: CsrfClient, workspace: Any, agent: User
) -> None:
    sign_in(csrf_client, agent)
    ticket = TicketFactory.create(workspace=workspace)

    response = csrf_client.post_json(
        messages_url(workspace.id, ticket.pk),
        {"body": "secret customer content", "visibility": "internal_note"},
    )

    event = events_for(ticket).get()
    assert event.event_type == TicketEventType.MESSAGE_ADDED
    assert event.metadata == {
        "message_id": response.json()["id"],
        "visibility": MessageVisibility.INTERNAL_NOTE.value,
    }
    assert "secret customer content" not in str(event.metadata)


# --- Capability matrix over HTTP -------------------------------------------


@pytest.mark.parametrize("role", list(MembershipRole))
def test_every_role_can_work_a_ticket(
    csrf_client: CsrfClient, workspace: Any, role: MembershipRole
) -> None:
    user = make_user(f"{role.value}@example.com")
    MembershipFactory.create(workspace=workspace, user=user, role=role)
    sign_in(csrf_client, user)

    created = create_ticket(csrf_client, workspace.id)
    assert created.status_code == 201
    ticket_id = created.json()["id"]

    assert csrf_client.get(ticket_url(workspace.id, ticket_id)).status_code == 200
    assert (
        patch_ticket(
            csrf_client, workspace.id, ticket_id, {"subject": "Edited"}, version=1
        ).status_code
        == 200
    )
    assert (
        csrf_client.post_json(
            messages_url(workspace.id, ticket_id), {"body": "Note", "visibility": "internal_note"}
        ).status_code
        == 201
    )
    assert (
        csrf_client.post_json(
            transition_url(workspace.id, ticket_id), {"status": "in_progress"}
        ).status_code
        == 200
    )
    assert (
        csrf_client.post_json(
            assign_url(workspace.id, ticket_id), {"assignee_id": str(user.pk)}
        ).status_code
        == 200
    )


def test_only_managers_and_above_may_assign_someone_else(
    csrf_client: CsrfClient, workspace: Any
) -> None:
    colleague = make_user("colleague@example.com")
    MembershipFactory.create(workspace=workspace, user=colleague)
    ticket = TicketFactory.create(workspace=workspace)

    expectations = {
        MembershipRole.AGENT: 403,
        MembershipRole.MANAGER: 200,
        MembershipRole.ADMIN: 200,
        MembershipRole.OWNER: 200,
    }
    for role, expected in expectations.items():
        actor = make_user(f"{role.value}@example.com")
        MembershipFactory.create(workspace=workspace, user=actor, role=role)
        sign_in(csrf_client, actor)

        response = csrf_client.post_json(
            assign_url(workspace.id, ticket.pk), {"assignee_id": str(colleague.pk)}
        )

        assert response.status_code == expected, role

    assert Ticket.objects.get(pk=ticket.pk).assignee_id == colleague.pk
