from __future__ import annotations

import uuid
from uuid import UUID

import pytest

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.organizations.exceptions import InsufficientRole, WorkspaceNotFound
from apps.organizations.models import (
    Membership,
    MembershipRole,
    MembershipStatus,
    Workspace,
    WorkspaceStatus,
)
from apps.organizations.services import WorkspaceAccess, resolve_workspace_access
from apps.organizations.tests.factories import MembershipFactory, WorkspaceFactory
from apps.tickets.exceptions import (
    IllegalTransition,
    InvalidAssignee,
    InvalidRequester,
    TicketNotFound,
    TicketVersionConflict,
)
from apps.tickets.models import (
    MessageVisibility,
    Ticket,
    TicketEventType,
    TicketPriority,
    TicketStatus,
)
from apps.tickets.services import (
    add_message,
    assign_ticket,
    can_transition,
    create_ticket,
    events_for,
    get_ticket,
    list_messages,
    list_tickets,
    transition_ticket,
    update_ticket_fields,
)
from apps.tickets.tests.factories import TicketFactory

pytestmark = pytest.mark.django_db


def make_member(
    workspace: Workspace,
    role: MembershipRole = MembershipRole.AGENT,
    email: str | None = None,
) -> tuple[User, Membership]:
    """Create an account and its membership in ``workspace``."""
    user = UserFactory.create(email=email or f"{uuid.uuid4().hex[:8]}@example.com")
    membership = MembershipFactory.create(workspace=workspace, user=user, role=role)
    return user, membership


def access_for(user: User, workspace: Workspace) -> WorkspaceAccess:
    return resolve_workspace_access(user=user, workspace_id=workspace.id)


def create(
    access: WorkspaceAccess,
    *,
    requester_email: str = "customer@example.com",
    requester_user_id: UUID | None = None,
    subject: str = "Cannot sign in",
    correlation_id: str = "",
) -> Ticket:
    return create_ticket(
        access=access,
        subject=subject,
        description="I keep getting an error.",
        requester_email=requester_email,
        requester_user_id=requester_user_id,
        correlation_id=correlation_id,
    )


# --- Creation ---------------------------------------------------------------


def test_creation_stores_a_normalized_contact_snapshot_and_an_audit_event() -> None:
    workspace = WorkspaceFactory.create()
    user, _ = make_member(workspace, MembershipRole.OWNER)
    access = access_for(user, workspace)

    ticket = create(access, requester_email="  Customer@Example.COM ", correlation_id="req-1")

    assert ticket.workspace_id == workspace.id
    assert ticket.requester_email == "customer@example.com"
    assert ticket.status == TicketStatus.OPEN
    assert ticket.priority == TicketPriority.NORMAL
    assert ticket.assignee_id is None
    assert ticket.version == 1
    event = events_for(ticket).get()
    assert event.event_type == TicketEventType.CREATED
    assert event.actor_id == user.pk
    assert event.correlation_id == "req-1"
    assert event.metadata == {"status": "open", "priority": "normal"}


def test_an_active_member_may_be_recorded_as_the_requester() -> None:
    workspace = WorkspaceFactory.create()
    user, _ = make_member(workspace, MembershipRole.OWNER)
    requester, _ = make_member(workspace, email="member@example.com")

    ticket = create(access_for(user, workspace), requester_user_id=requester.pk)

    assert ticket.requester_user_id == requester.pk


def test_a_member_of_another_workspace_cannot_be_the_requester() -> None:
    workspace = WorkspaceFactory.create()
    user, _ = make_member(workspace, MembershipRole.OWNER)
    stranger, _ = make_member(WorkspaceFactory.create())

    with pytest.raises(InvalidRequester):
        create(access_for(user, workspace), requester_user_id=stranger.pk)


def test_an_unknown_requester_is_refused_with_the_same_error() -> None:
    workspace = WorkspaceFactory.create()
    user, _ = make_member(workspace, MembershipRole.OWNER)

    with pytest.raises(InvalidRequester):
        create(access_for(user, workspace), requester_user_id=uuid.uuid4())


def test_a_removed_member_cannot_be_the_requester() -> None:
    workspace = WorkspaceFactory.create()
    user, _ = make_member(workspace, MembershipRole.OWNER)
    requester, membership = make_member(workspace)
    Membership.objects.filter(pk=membership.pk).update(status=MembershipStatus.REMOVED)

    with pytest.raises(InvalidRequester):
        create(access_for(user, workspace), requester_user_id=requester.pk)


# --- Reading and filtering --------------------------------------------------


def test_a_ticket_from_another_workspace_is_not_found() -> None:
    owner, membership = make_member(WorkspaceFactory.create(), MembershipRole.OWNER)
    foreign = TicketFactory.create()

    with pytest.raises(TicketNotFound):
        get_ticket(access=access_for(owner, membership.workspace), ticket_id=foreign.pk)


def test_filters_combine_with_and() -> None:
    workspace = WorkspaceFactory.create()
    user, _ = make_member(workspace, MembershipRole.OWNER)
    access = access_for(user, workspace)
    TicketFactory.create(
        workspace=workspace, status=TicketStatus.OPEN, priority=TicketPriority.HIGH
    )
    TicketFactory.create(workspace=workspace, status=TicketStatus.OPEN, priority=TicketPriority.LOW)
    TicketFactory.create(
        workspace=workspace, status=TicketStatus.RESOLVED, priority=TicketPriority.HIGH
    )

    tickets = list_tickets(
        access=access,
        status=TicketStatus.OPEN.value,
        priority=TicketPriority.HIGH.value,
    )

    assert len(tickets) == 1
    assert tickets[0].priority == TicketPriority.HIGH


def test_the_assignee_filter_supports_me_and_unassigned() -> None:
    workspace = WorkspaceFactory.create()
    user, membership = make_member(workspace, MembershipRole.OWNER)
    access = access_for(user, workspace)
    mine = TicketFactory.create(workspace=workspace, assignee=user)
    TicketFactory.create(workspace=workspace)
    colleague, _ = make_member(workspace)
    theirs = TicketFactory.create(workspace=workspace, assignee=colleague)

    assert list(list_tickets(access=access, assignee="me")) == [mine]
    unassigned = list(list_tickets(access=access, assignee="unassigned"))
    assert len(unassigned) == 1
    assert unassigned[0].assignee_id is None
    assert list(list_tickets(access=access, assignee=theirs.assignee_id)) == [theirs]


def test_a_foreign_user_id_matches_nothing_instead_of_failing() -> None:
    workspace = WorkspaceFactory.create()
    user, _ = make_member(workspace, MembershipRole.OWNER)
    access = access_for(user, workspace)
    TicketFactory.create(workspace=workspace)

    assert list(list_tickets(access=access, assignee=uuid.uuid4())) == []


def test_search_is_a_case_insensitive_substring_of_the_subject() -> None:
    workspace = WorkspaceFactory.create()
    user, _ = make_member(workspace, MembershipRole.OWNER)
    access = access_for(user, workspace)
    match = TicketFactory.create(workspace=workspace, subject="Duplicate CHARGE")
    TicketFactory.create(workspace=workspace, subject="Cannot sign in")

    assert list(list_tickets(access=access, search="duplicate char")) == [match]


def test_ordering_is_deterministic_across_ties() -> None:
    workspace = WorkspaceFactory.create()
    user, _ = make_member(workspace, MembershipRole.OWNER)
    access = access_for(user, workspace)
    first = TicketFactory.create(workspace=workspace, priority=TicketPriority.HIGH)
    second = TicketFactory.create(workspace=workspace, priority=TicketPriority.HIGH)
    third = TicketFactory.create(workspace=workspace, priority=TicketPriority.LOW)

    ascending = list(list_tickets(access=access, ordering="priority"))
    descending = list(list_tickets(access=access, ordering="-priority"))

    assert [ticket.priority for ticket in ascending] == sorted(
        ticket.priority for ticket in ascending
    )
    assert [ticket.priority for ticket in descending] == sorted(
        (ticket.priority for ticket in descending), reverse=True
    )
    # Within the tie group the id tie-break decides, so the order is repeatable.
    tied = [ticket for ticket in ascending if ticket.priority == TicketPriority.HIGH]
    assert {ticket.pk for ticket in tied} == {first.pk, second.pk}
    assert [str(ticket.pk) for ticket in tied] == sorted(str(ticket.pk) for ticket in tied)
    assert [ticket.pk for ticket in ascending] == [
        ticket.pk for ticket in list_tickets(access=access, ordering="priority")
    ]
    assert {ticket.pk for ticket in ascending} == {first.pk, second.pk, third.pk}


def test_an_unknown_ordering_is_refused() -> None:
    workspace = WorkspaceFactory.create()
    user, _ = make_member(workspace, MembershipRole.OWNER)

    with pytest.raises(ValueError):
        list_tickets(access=access_for(user, workspace), ordering="assignee")


# --- Status transitions -----------------------------------------------------

ALLOWED_EDGES = {
    (TicketStatus.OPEN, TicketStatus.IN_PROGRESS),
    (TicketStatus.OPEN, TicketStatus.WAITING_ON_CUSTOMER),
    (TicketStatus.OPEN, TicketStatus.RESOLVED),
    (TicketStatus.IN_PROGRESS, TicketStatus.WAITING_ON_CUSTOMER),
    (TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED),
    (TicketStatus.IN_PROGRESS, TicketStatus.OPEN),
    (TicketStatus.WAITING_ON_CUSTOMER, TicketStatus.IN_PROGRESS),
    (TicketStatus.WAITING_ON_CUSTOMER, TicketStatus.RESOLVED),
    (TicketStatus.WAITING_ON_CUSTOMER, TicketStatus.OPEN),
    (TicketStatus.RESOLVED, TicketStatus.OPEN),
    (TicketStatus.RESOLVED, TicketStatus.CLOSED),
}

ALL_STATUSES = list(TicketStatus)


@pytest.mark.parametrize("current", ALL_STATUSES)
@pytest.mark.parametrize("requested", ALL_STATUSES)
@pytest.mark.parametrize("role", list(MembershipRole))
def test_transition_matrix_follows_the_documented_policy(
    current: TicketStatus, requested: TicketStatus, role: MembershipRole
) -> None:
    workspace = WorkspaceFactory.create()
    _, membership = make_member(workspace, role)

    allowed = (current, requested) in ALLOWED_EDGES
    if allowed and (current, requested) == (TicketStatus.RESOLVED, TicketStatus.OPEN):
        allowed = role in {MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.MANAGER}

    assert can_transition(current=current, requested=requested, actor=membership) is allowed


def test_resolving_stamps_the_time_and_reopening_clears_it() -> None:
    workspace = WorkspaceFactory.create()
    manager, _ = make_member(workspace, MembershipRole.MANAGER)
    access = access_for(manager, workspace)
    ticket = create(access)

    resolved = transition_ticket(access=access, ticket_id=ticket.pk, status="resolved")

    assert resolved.status == TicketStatus.RESOLVED
    assert resolved.resolved_at is not None
    assert resolved.version == 2

    reopened = transition_ticket(access=access, ticket_id=ticket.pk, status="open")

    assert reopened.status == TicketStatus.OPEN
    assert reopened.resolved_at is None
    assert reopened.version == 3


def test_an_agent_cannot_reopen_a_resolved_ticket() -> None:
    workspace = WorkspaceFactory.create()
    agent, _ = make_member(workspace, MembershipRole.AGENT)
    access = access_for(agent, workspace)
    ticket = TicketFactory.create(workspace=workspace, status=TicketStatus.RESOLVED)

    with pytest.raises(IllegalTransition):
        transition_ticket(access=access, ticket_id=ticket.pk, status="open")


def test_a_closed_ticket_is_terminal() -> None:
    workspace = WorkspaceFactory.create()
    owner, _ = make_member(workspace, MembershipRole.OWNER)
    access = access_for(owner, workspace)
    ticket = TicketFactory.create(workspace=workspace, status=TicketStatus.CLOSED)

    with pytest.raises(IllegalTransition):
        transition_ticket(access=access, ticket_id=ticket.pk, status="open")


def test_a_missing_transition_edge_is_refused() -> None:
    workspace = WorkspaceFactory.create()
    owner, _ = make_member(workspace, MembershipRole.OWNER)
    access = access_for(owner, workspace)
    ticket = create(access)

    with pytest.raises(IllegalTransition):
        transition_ticket(access=access, ticket_id=ticket.pk, status="closed")


def test_a_transition_records_from_and_to() -> None:
    workspace = WorkspaceFactory.create()
    owner, _ = make_member(workspace, MembershipRole.OWNER)
    access = access_for(owner, workspace)
    ticket = create(access)

    transition_ticket(access=access, ticket_id=ticket.pk, status="in_progress")

    event = events_for(ticket).filter(event_type=TicketEventType.STATUS_CHANGED).get()
    assert event.metadata == {"from": "open", "to": "in_progress"}


# --- Field edits ------------------------------------------------------------


def test_a_field_edit_requires_the_current_version() -> None:
    workspace = WorkspaceFactory.create()
    owner, _ = make_member(workspace, MembershipRole.OWNER)
    access = access_for(owner, workspace)
    ticket = create(access)

    update_ticket_fields(
        access=access, ticket_id=ticket.pk, fields={"subject": "New subject"}, expected_version=1
    )

    with pytest.raises(TicketVersionConflict) as refusal:
        update_ticket_fields(
            access=access,
            ticket_id=ticket.pk,
            fields={"subject": "Stale subject"},
            expected_version=1,
        )
    assert refusal.value.current_version == 2


def test_a_field_edit_increments_the_version_and_audits_field_names_only() -> None:
    workspace = WorkspaceFactory.create()
    owner, _ = make_member(workspace, MembershipRole.OWNER)
    access = access_for(owner, workspace)
    ticket = create(access)

    updated = update_ticket_fields(
        access=access,
        ticket_id=ticket.pk,
        fields={"subject": "Refund requested", "priority": "high"},
        expected_version=1,
    )

    assert updated.version == 2
    assert updated.subject == "Refund requested"
    event = events_for(ticket).filter(event_type=TicketEventType.UPDATED).get()
    assert event.metadata == {"fields": "priority,subject"}


def test_a_field_edit_normalizes_the_requester_email() -> None:
    workspace = WorkspaceFactory.create()
    owner, _ = make_member(workspace, MembershipRole.OWNER)
    access = access_for(owner, workspace)
    ticket = create(access)

    updated = update_ticket_fields(
        access=access,
        ticket_id=ticket.pk,
        fields={"requester_email": "  Other@Example.COM "},
        expected_version=1,
    )

    assert updated.requester_email == "other@example.com"


def test_a_field_edit_refuses_fields_it_does_not_own() -> None:
    workspace = WorkspaceFactory.create()
    owner, _ = make_member(workspace, MembershipRole.OWNER)
    access = access_for(owner, workspace)
    ticket = create(access)

    with pytest.raises(ValueError):
        update_ticket_fields(
            access=access,
            ticket_id=ticket.pk,
            fields={"status": "resolved"},
            expected_version=1,
        )


# --- Assignment -------------------------------------------------------------


def test_an_agent_may_assign_a_ticket_to_themselves() -> None:
    workspace = WorkspaceFactory.create()
    agent, _ = make_member(workspace, MembershipRole.AGENT)
    access = access_for(agent, workspace)
    ticket = create(access)

    assigned = assign_ticket(access=access, ticket_id=ticket.pk, assignee_id=agent.pk)

    assert assigned.assignee_id == agent.pk
    assert assigned.version == 2
    event = events_for(ticket).filter(event_type=TicketEventType.ASSIGNED).get()
    assert event.metadata == {"assignee_id": str(agent.pk)}


def test_an_agent_cannot_assign_someone_else() -> None:
    workspace = WorkspaceFactory.create()
    agent, _ = make_member(workspace, MembershipRole.AGENT)
    colleague, _ = make_member(workspace)
    access = access_for(agent, workspace)
    ticket = create(access)

    with pytest.raises(InsufficientRole):
        assign_ticket(access=access, ticket_id=ticket.pk, assignee_id=colleague.pk)


def test_a_manager_may_assign_a_colleague() -> None:
    workspace = WorkspaceFactory.create()
    manager, _ = make_member(workspace, MembershipRole.MANAGER)
    colleague, _ = make_member(workspace)
    access = access_for(manager, workspace)
    ticket = create(access)

    assigned = assign_ticket(access=access, ticket_id=ticket.pk, assignee_id=colleague.pk)

    assert assigned.assignee_id == colleague.pk


def test_unassigning_someone_else_needs_the_managerial_capability() -> None:
    workspace = WorkspaceFactory.create()
    agent, _ = make_member(workspace, MembershipRole.AGENT)
    colleague, _ = make_member(workspace)
    access = access_for(agent, workspace)
    ticket = TicketFactory.create(workspace=workspace, assignee=colleague)

    with pytest.raises(InsufficientRole):
        assign_ticket(access=access, ticket_id=ticket.pk, assignee_id=None)


def test_releasing_your_own_assignment_works_for_an_agent() -> None:
    workspace = WorkspaceFactory.create()
    agent, _ = make_member(workspace, MembershipRole.AGENT)
    access = access_for(agent, workspace)
    ticket = TicketFactory.create(workspace=workspace, assignee=agent)

    released = assign_ticket(access=access, ticket_id=ticket.pk, assignee_id=None)

    assert released.assignee_id is None
    event = events_for(ticket).filter(event_type=TicketEventType.UNASSIGNED).get()
    assert event.metadata == {"previous_assignee_id": str(agent.pk)}


def test_assigning_an_inactive_member_is_refused() -> None:
    workspace = WorkspaceFactory.create()
    owner, _ = make_member(workspace, MembershipRole.OWNER)
    target, membership = make_member(workspace)
    Membership.objects.filter(pk=membership.pk).update(status=MembershipStatus.REMOVED)
    access = access_for(owner, workspace)
    ticket = create(access)

    with pytest.raises(InvalidAssignee):
        assign_ticket(access=access, ticket_id=ticket.pk, assignee_id=target.pk)


def test_assigning_the_current_holder_is_a_no_op() -> None:
    workspace = WorkspaceFactory.create()
    owner, _ = make_member(workspace, MembershipRole.OWNER)
    access = access_for(owner, workspace)
    ticket = TicketFactory.create(workspace=workspace, assignee=owner)
    events_before = events_for(ticket).count()

    result = assign_ticket(access=access, ticket_id=ticket.pk, assignee_id=owner.pk)

    assert result.version == 1
    assert events_for(ticket).count() == events_before


# --- Messages ---------------------------------------------------------------


def test_a_message_moves_activity_but_not_the_version() -> None:
    workspace = WorkspaceFactory.create()
    agent, _ = make_member(workspace, MembershipRole.AGENT)
    access = access_for(agent, workspace)
    ticket = create(access)
    before = ticket.updated_at

    message = add_message(
        access=access,
        ticket_id=ticket.pk,
        body="Looking into this now.",
        visibility=MessageVisibility.INTERNAL_NOTE.value,
    )

    ticket.refresh_from_db()
    assert ticket.version == 1
    assert ticket.updated_at > before
    assert message.author_id == agent.pk
    assert message.visibility == MessageVisibility.INTERNAL_NOTE
    event = events_for(ticket).filter(event_type=TicketEventType.MESSAGE_ADDED).get()
    assert event.metadata == {
        "message_id": str(message.pk),
        "visibility": MessageVisibility.INTERNAL_NOTE.value,
    }


def test_messages_are_listed_oldest_first_and_include_both_visibilities() -> None:
    workspace = WorkspaceFactory.create()
    agent, _ = make_member(workspace, MembershipRole.AGENT)
    access = access_for(agent, workspace)
    ticket = create(access)
    add_message(access=access, ticket_id=ticket.pk, body="First")
    add_message(
        access=access,
        ticket_id=ticket.pk,
        body="Second",
        visibility=MessageVisibility.INTERNAL_NOTE.value,
    )

    bodies = list(list_messages(access=access, ticket_id=ticket.pk).values_list("body", flat=True))

    assert bodies == ["First", "Second"]


def test_messages_of_a_foreign_ticket_are_not_found() -> None:
    workspace = WorkspaceFactory.create()
    agent, _ = make_member(workspace, MembershipRole.AGENT)
    foreign = TicketFactory.create()

    with pytest.raises(TicketNotFound):
        list_messages(access=access_for(agent, workspace), ticket_id=foreign.pk)


# --- Stale authority --------------------------------------------------------


def test_a_revoked_member_cannot_write_with_a_stale_access_object() -> None:
    workspace = WorkspaceFactory.create()
    owner, membership = make_member(workspace, MembershipRole.OWNER)
    access = access_for(owner, workspace)
    ticket = create(access)

    Membership.objects.filter(pk=membership.pk).update(status=MembershipStatus.REMOVED)

    with pytest.raises(WorkspaceNotFound):
        transition_ticket(access=access, ticket_id=ticket.pk, status="resolved")


def test_an_archived_workspace_cannot_be_written_to_with_a_stale_access_object() -> None:
    workspace = WorkspaceFactory.create()
    owner, _ = make_member(workspace, MembershipRole.OWNER)
    access = access_for(owner, workspace)
    ticket = create(access)

    Workspace.objects.filter(pk=workspace.pk).update(status=WorkspaceStatus.ARCHIVED)

    with pytest.raises(WorkspaceNotFound):
        add_message(access=access, ticket_id=ticket.pk, body="Hello")


def test_a_stale_access_object_cannot_edit_fields() -> None:
    workspace = WorkspaceFactory.create()
    owner, membership = make_member(workspace, MembershipRole.OWNER)
    access = access_for(owner, workspace)
    ticket = create(access)

    Membership.objects.filter(pk=membership.pk).update(status=MembershipStatus.REMOVED)

    with pytest.raises(WorkspaceNotFound):
        update_ticket_fields(
            access=access,
            ticket_id=ticket.pk,
            fields={"subject": "Nope"},
            expected_version=1,
        )


# --- Audit scoping ----------------------------------------------------------


def test_events_are_scoped_to_one_ticket() -> None:
    workspace = WorkspaceFactory.create()
    owner, _ = make_member(workspace, MembershipRole.OWNER)
    access = access_for(owner, workspace)
    first = create(access)
    second = create(access)

    first_ids = {str(event.object_id) for event in events_for(first)}

    assert first_ids == {str(first.pk)}
    assert str(second.pk) not in first_ids


def test_a_ticket_id_is_a_uuid() -> None:
    ticket = TicketFactory.create()

    assert isinstance(ticket.pk, UUID)
