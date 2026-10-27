"""Concurrency behaviour of ticket writes.

``transaction=True`` is required: the default pytest-django test runs inside an
uncommitted transaction, so a second thread on another connection could not see
the ticket this test creates.
"""

from __future__ import annotations

import threading
from typing import Any

import pytest
from django.db import connections

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.organizations.models import MembershipRole, Workspace
from apps.organizations.services import resolve_workspace_access
from apps.organizations.tests.factories import MembershipFactory, WorkspaceFactory
from apps.tickets.exceptions import IllegalTransition, TicketVersionConflict
from apps.tickets.models import TicketEventType, TicketStatus
from apps.tickets.services import add_message, events_for, transition_ticket, update_ticket_fields
from apps.tickets.tests.factories import TicketFactory


def make_owner(workspace: Workspace, email: str = "owner@example.com") -> User:
    user = UserFactory.create(email=email)
    MembershipFactory.create(workspace=workspace, user=user, role=MembershipRole.OWNER)
    return user


def run_both(target_a: Any, target_b: Any) -> None:
    """Run two callables on separate threads and wait for both."""
    threads = [threading.Thread(target=target_a), threading.Thread(target=target_b)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert not any(thread.is_alive() for thread in threads)


@pytest.mark.django_db(transaction=True)
def test_simultaneous_field_edits_leave_exactly_one_winner() -> None:
    workspace = WorkspaceFactory.create()
    owner = make_owner(workspace)
    ticket = TicketFactory.create(workspace=workspace)
    barrier = threading.Barrier(2)
    successes: list[str] = []
    conflicts: list[int] = []
    lock = threading.Lock()

    def edit(subject: str) -> None:
        try:
            access = resolve_workspace_access(user=owner, workspace_id=workspace.id)
            # Both requests read version 1, then race to write.
            barrier.wait(timeout=10)
            update_ticket_fields(
                access=access,
                ticket_id=ticket.pk,
                fields={"subject": subject},
                expected_version=1,
            )
            with lock:
                successes.append(subject)
        except TicketVersionConflict as exc:
            with lock:
                conflicts.append(exc.current_version)
        finally:
            connections.close_all()

    run_both(lambda: edit("First edit"), lambda: edit("Second edit"))

    ticket.refresh_from_db()
    assert len(successes) == 1
    assert conflicts == [2]
    assert ticket.version == 2
    assert ticket.subject == successes[0]
    assert events_for(ticket).filter(event_type=TicketEventType.UPDATED).count() == 1


@pytest.mark.django_db(transaction=True)
def test_simultaneous_transitions_allow_only_one_to_resolve() -> None:
    workspace = WorkspaceFactory.create()
    owner = make_owner(workspace)
    ticket = TicketFactory.create(workspace=workspace)
    barrier = threading.Barrier(2)
    successes: list[str] = []
    refusals: list[Exception] = []
    lock = threading.Lock()

    def resolve() -> None:
        try:
            access = resolve_workspace_access(user=owner, workspace_id=workspace.id)
            barrier.wait(timeout=10)
            transition_ticket(access=access, ticket_id=ticket.pk, status="resolved")
            with lock:
                successes.append("resolved")
        except IllegalTransition as exc:
            # The loser sees the winner's status and refuses the repeat.
            with lock:
                refusals.append(exc)
        finally:
            connections.close_all()

    run_both(resolve, resolve)

    ticket.refresh_from_db()
    assert len(successes) == 1
    assert len(refusals) == 1
    assert ticket.status == TicketStatus.RESOLVED
    assert ticket.version == 2
    assert events_for(ticket).filter(event_type=TicketEventType.STATUS_CHANGED).count() == 1


@pytest.mark.django_db(transaction=True)
def test_simultaneous_messages_are_both_kept_and_do_not_bump_the_version() -> None:
    workspace = WorkspaceFactory.create()
    owner = make_owner(workspace)
    ticket = TicketFactory.create(workspace=workspace)
    barrier = threading.Barrier(2)
    bodies: list[str] = []
    lock = threading.Lock()

    def comment(body: str) -> None:
        try:
            access = resolve_workspace_access(user=owner, workspace_id=workspace.id)
            barrier.wait(timeout=10)
            add_message(access=access, ticket_id=ticket.pk, body=body)
            with lock:
                bodies.append(body)
        finally:
            connections.close_all()

    run_both(lambda: comment("First"), lambda: comment("Second"))

    ticket.refresh_from_db()
    assert sorted(bodies) == ["First", "Second"]
    assert ticket.version == 1
    assert ticket.messages.count() == 2
